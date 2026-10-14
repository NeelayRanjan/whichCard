from datetime import date
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from whichcard.api import app
from whichcard.data_layer import Catalog
from whichcard.data_layer.models import Offer, WalletCard
from whichcard.engine import Context, bonus_status, card_rate, matches, period, recommend, resolve
from whichcard.importers import import_file
from whichcard.inference import enrich
from whichcard.storage import connect, transactions

CASES = yaml.safe_load(Path("backend/tests/golden_recommendations.yaml").read_text())


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden(case, catalog):
    db = connect(":memory:")
    for c in catalog.wallet.cards:
        c.opened_on = date(2020, 1, 1)
        c.signup_bonus = None
    scene = case.get("scene", "empty")
    if scene in {"cap", "sub", "rotation_cap"}:
        for c in catalog.wallet.cards:
            import_file(db, Path("backend/tests/fixtures") / f"{c.card}.csv", c.card)
        enrich(db, catalog)
    if scene == "offer":
        catalog.offers = [
            Offer(
                wallet_card="bofa-customized-cash",
                merchant_pattern="CHIPOTLE",
                type="fixed",
                value=20,
                expires="2026-12-31",
            )
        ]
    if scene == "sub":
        from whichcard.data_layer.models import WalletBonus

        catalog.wallet.cards[0].opened_on = date(2026, 9, 1)
        catalog.wallet.cards[0].signup_bonus = WalletBonus(min_spend=4000, deadline=date(2026, 11, 30))
    if scene.startswith("rotation"):
        flex = WalletCard(
            card="chase-freedom-flex",
            opened_on=date(2020, 1, 1),
            credit_limit=5000,
            statement_day=10,
            settings={"activated_3": scene != "rotation_off"},
        )
        catalog.wallet.cards.append(flex)
        if scene == "rotation_cap":
            import_file(db, Path("backend/tests/fixtures/rotation.csv"), flex.card)
            enrich(db, catalog)
    if scene == "tie":
        for c in catalog.wallet.cards:
            if c.card != "amex-platinum":
                db.execute(
                    "INSERT INTO statement(wallet_card_id,close_date,statement_balance,source) VALUES(?,?,?,?)",
                    (c.card, "2026-10-01", 10000, "manual"),
                )
    result = recommend(Context(**case["context"]), catalog, db)
    assert result["ranked"][0]["card_id"] == case["top"]
    assert result["ranked"][0]["effective_rate_pct"] == case["rate"]
    assert result["override"] == case["override"]
    assert result["ranked"][0]["reasons"] and result["ranked"][0]["range"]


def test_partial_caps_and_matching(catalog, db):
    from whichcard.data_layer.models import Match

    instance = catalog.wallet.cards[1]
    context = Context(category="online_shopping", amount_cents=300000, date=date(2026, 7, 1))
    resolved, _ = resolve(context, catalog)
    result = card_rate(catalog.cards[instance.card], instance, resolved, [], catalog)
    assert result["effective_rate_pct"] == pytest.approx(2.666667)
    assert any("split" in w for w in result["warnings"])
    assert not matches(Match(mcc=[1234]), {"mcc": 5678})
    assert matches(Match(merchant_pattern="CAFE"), {"normalized_description": "CAFE PARIS"})
    assert not matches(Match(merchant_pattern="CAFE"), {"normalized_description": "SHOP"})
    assert not matches(Match(category="chosen"), {"category": "gas"})
    assert period(date(2026, 1, 5), "annual", "anniversary", date(2020, 11, 10))[0] == date(2025, 11, 10)
    flex = WalletCard(
        card="chase-freedom-flex",
        opened_on=date(2020, 1, 1),
        credit_limit=1000,
        statement_day=1,
        settings={"activated_3": True},
    )
    result = card_rate(
        catalog.cards[flex.card],
        flex,
        resolve(Context(category="gas", date=date(2027, 1, 1)), catalog)[0],
        [],
        catalog,
    )
    assert result["effective_rate_pct"] == 1.5


@given(st.integers(0, 1000000), st.sampled_from(["dining", "grocery", "other", "gas"]))
@settings(max_examples=30, deadline=None)
def test_rate_bound(amount, category):
    catalog = Catalog()
    for c in catalog.wallet.cards:
        ctx, _ = resolve(Context(category=category, amount_cents=amount), catalog)
        result = card_rate(catalog.cards[c.card], c, ctx, [], catalog)
        assert (
            result["reward_rate_pct"]
            <= max(r.rate for r in catalog.cards[c.card].earn)
            * catalog.valuation(catalog.cards[c.card].currency).optimized
        )


def test_bonus_fixture_and_purchase_monotonicity(catalog, db):
    rows = transactions(db)
    c = catalog.wallet.cards[0]
    before = bonus_status(c, rows, date(2026, 10, 14))
    after = bonus_status(c, rows, date(2026, 10, 20))
    assert before["status"] == "at_risk" and after["status"] == "on_track"
    assert after["spend_cents"] >= before["spend_cents"]
    assert bonus_status(c, rows, date(2027, 1, 1))["status"] == "missed"
    c.signup_bonus.completed = True
    assert bonus_status(c, rows, date(2026, 10, 14))["status"] == "done"


def test_recommend_api():
    client = TestClient(app)
    assert client.post("/api/recommend", json={"category": "dining"}).status_code == 200
    assert client.post("/api/recommend", json={"amount_cents": -1}).status_code == 422
    assert client.post("/api/recommend", json={"category": "bogus"}).status_code == 422
