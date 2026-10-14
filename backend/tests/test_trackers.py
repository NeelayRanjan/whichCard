from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from whichcard.data_layer import Catalog
from whichcard.engine import bonus_status
from whichcard.storage import transactions
from whichcard.trackers import account_timeline, mark_credit, trackers, utilization


def test_fixture_trackers(catalog, db):
    result = trackers(catalog, db, date(2026, 10, 14))
    assert result["bonuses"][0]["status"] == "at_risk"
    credit = next(c for c in result["credits"] if c["credit_id"] == "uber")
    assert credit["remaining_cents"] == 1000
    fees = {r["card"]: r for r in result["fees"]}
    assert fees["amex-platinum"]["verdict"] == "cancel"
    assert fees["amex-gold"]["verdict"] == "keep"
    assert (
        fees["amex-gold"]["net_cents"]
        == sum(
            fees["amex-gold"][k] for k in ["earning_uplift_cents", "credits_used_cents", "perk_value_cents"]
        )
        - fees["amex-gold"]["annual_fee_cents"]
    )
    assert next(r for r in result["utilization"]["cards"] if r["card"] == "bofa-customized-cash")["alert"]
    assert next(r for r in result["dormancy"] if r["card"] == "amex-platinum")["dormant"]
    mark_credit(db, catalog, "amex-gold", "uber", 1000, date(2026, 10, 14))
    assert (
        next(c for c in trackers(catalog, db, date(2026, 10, 14))["credits"] if c["credit_id"] == "uber")[
            "remaining_cents"
        ]
        == 0
    )
    for args in [("bad", "uber", 1000), ("amex-gold", "bad", 1000), ("amex-gold", "uber", 1001)]:
        with pytest.raises(ValueError):
            mark_credit(db, catalog, *args, date(2026, 10, 14))


def test_timeline_and_statement(catalog, db):
    from whichcard.data_layer.models import WalletCard

    for i in range(5):
        catalog.wallet.cards.append(
            WalletCard(
                card=f"additional-{i}", opened_on=date(2026, i + 1, 1), credit_limit=1000, statement_day=31
            )
        )
    result = account_timeline(catalog, date(2026, 10, 14))
    assert result["count_5_24"] == 6 and result["next_under_5_24"] == "2028-02-01"
    assert result["inquiries_12m"] >= 6
    assert (
        utilization(catalog, db, transactions(db), date(2026, 2, 28))["cards"][-1]["next_statement"]
        == "2026-03-31"
    )


@given(st.integers(0, 100000))
@settings(max_examples=15, deadline=None)
def test_bonus_purchase_monotone(amount):
    c = Catalog().wallet.cards[0]
    day = date(2026, 10, 14)
    before = bonus_status(c, [], day)["spend_cents"]
    row = dict(
        wallet_card_id=c.card, transaction_date="2026-10-14", amount=amount, is_fee=False, is_payment=False
    )
    assert bonus_status(c, [row], day)["spend_cents"] >= before


def test_tracker_api(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from whichcard.api import app

    monkeypatch.setenv("WHICHCARD_DB", str(tmp_path / "test.db"))
    client = TestClient(app)
    assert client.get("/api/trackers").status_code == 200
    assert client.post("/api/credits/amex-gold/uber", json={"amount_cents": 1000}).status_code == 200
    assert client.post("/api/credits/bad/bad", json={"amount_cents": 1000}).status_code == 422


def test_computed_statements_refresh_and_month_end(catalog):
    from whichcard.storage import connect

    db = connect(":memory:")
    card = catalog.wallet.cards[0]
    card.statement_day = 31
    day = date(2026, 2, 15)
    result = utilization(catalog, db, [], day)["cards"][0]
    assert result["next_statement"] == "2026-02-28"
    rows = [dict(wallet_card_id=card.card, transaction_date="2026-01-30", amount=10000)]
    assert utilization(catalog, db, rows, day)["cards"][0]["balance_cents"] == 10000
    assert (
        db.execute("SELECT close_date FROM statement WHERE wallet_card_id=?", (card.card,)).fetchone()[0]
        == "2026-01-31"
    )
