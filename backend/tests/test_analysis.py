from datetime import date
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from whichcard.analysis import (
    Award,
    Redemption,
    airport,
    distance,
    gap_analysis,
    now,
    redemption,
    simulate_card,
    spend_profile,
)
from whichcard.api import app
from whichcard.api.service import catalog as api_catalog
from whichcard.data_layer.models import Place, Transfer
from whichcard.engine import Context
from whichcard.storage import connect


def test_profile_gap(catalog, db):
    profile = spend_profile(catalog, db, date(2026, 10, 14))
    assert profile["total_cents"] > 0
    assert profile["by_category"]["dining"] > profile["by_category"]["gas"]
    result = gap_analysis(catalog, db, date(2026, 10, 14))
    assert len(result["candidates"]) == 5
    row = result["candidates"][0]
    assert (
        row["net_annual_cents"]
        == row["earning_uplift_cents"] + row["credit_value_cents"] - row["annual_fee_cents"]
    )
    assert row["swap"] and row["sensitivity"] and row["costs"]["hard_inquiries"] == 1
    same = simulate_card(catalog.wallet.cards[0].card, catalog, db)
    assert same["net_annual_cents"] == 0
    empty = connect(":memory:")
    assert gap_analysis(catalog, empty)["no_positive_candidate"]
    with pytest.raises(ValueError):
        simulate_card("missing", catalog, db)
    # Increasing gas spend favors a gas specialist over the flat-rate baseline.
    base = dict(
        profile,
        by_category={"gas": 1000000},
        segments=[
            dict(
                month="2026-09",
                category="gas",
                channel="in_person",
                weighted_cents=1000000,
                spend_cents=1000000,
            )
        ],
    )
    gas = simulate_card("citi-costco", catalog, db, date(2026, 10, 14), base)
    flat = simulate_card("capitalone-quicksilver", catalog, db, date(2026, 10, 14), base)
    assert gas["net_annual_cents"] > flat["net_annual_cents"]


def test_redemption(catalog, db):
    result = redemption(
        Redemption(cash_price_cents=40000, awards=[Award(program="united", points=20000)]), catalog, db
    )
    assert result["recommended"] == "award"
    assert result["options"][0]["cpp"] == 2
    result = redemption(
        Redemption(cash_price_cents=18000, awards=[Award(program="united", points=20000)]), catalog, db
    )
    assert result["recommended"] == "cash"
    assert result["options"][0]["forgone_earning_cents"] > 0
    catalog.transfers["chase-ur"] = [Transfer(partner="test-air", ratio=0.5, typical_days=2)]
    result = redemption(
        Redemption(cash_price_cents=40000, awards=[Award(program="test-air", points=20000)]), catalog, db
    )
    path = result["options"][0]["transfer_paths"][0]
    assert path["source_points"] == 40000
    assert path["adjusted_cpp"] == pytest.approx(result["options"][0]["net_cpp"] * 0.5, abs=0.0001)
    result = redemption(
        Redemption(
            cash_price_cents=40000,
            awards=[Award(program="united", points=20000)],
            portal_price_cents=10000,
            portal="chase",
            portal_card="chase-sapphire-preferred",
        ),
        catalog,
        db,
    )
    assert result["recommended"] == "portal"
    with pytest.raises(ValueError, match="no valuation"):
        redemption(Redemption(cash_price_cents=1, awards=[Award(program="unknown", points=1)]), catalog, db)
    with pytest.raises(ValueError, match="portal card"):
        redemption(
            Redemption(
                cash_price_cents=1,
                awards=[Award(program="united", points=1)],
                portal_price_cents=1,
                portal_card="missing",
            ),
            catalog,
            db,
        )


def test_location_and_latency(catalog, db):
    contexts = [
        Context(app_context="ubereats"),
        Context(category="dining"),
        Context(merchant_query="costco"),
        Context(lat=37.619, lon=-122.375),
    ]
    for context in contexts:
        start = perf_counter()
        result = now(context, catalog, db)
        elapsed = perf_counter() - start
        assert len(result["notification_text"]) < 120
        assert elapsed < 0.1
    assert "lounges" in result
    assert airport("SFO", catalog)["lounges"][0]["access"]
    catalog.places = [Place(name="Home coffee", lat=0, lon=0, merchant_id="starbucks", radius_m=100)]
    assert now(Context(lat=0, lon=0), catalog, db)["category"] == "dining"
    assert "ranked" in now(Context(lat=10, lon=10), catalog, db)
    assert airport("ZZZ", catalog)["lounges"] == []
    assert distance(0, 0, 0, 0) == 0


def test_analysis_api(catalog, db, monkeypatch):
    from whichcard.api.service import database

    app.dependency_overrides[database] = lambda: db
    monkeypatch.setattr("whichcard.api.catalog", lambda: catalog)
    try:
        client = TestClient(app)
        for url in [
            "/api/spend",
            "/api/gap",
            "/api/airport/SFO",
            "/api/now?app=ubereats",
            "/api/now?category=dining",
            "/api/now?merchant=costco",
            "/api/now?lat=37.619&lon=-122.375",
        ]:
            assert client.get(url).status_code == 200
        assert client.get("/api/now?lat=100").status_code == 422
        assert (
            client.post(
                "/api/redeem/evaluate",
                json={"cash_price_cents": 42000, "awards": [{"program": "united", "points": 28000}]},
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/redeem/evaluate",
                json={"cash_price_cents": 42000, "awards": [{"program": "unknown", "points": 28000}]},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/places",
                json={"name": "Test", "lat": 0, "lon": 0, "merchant_id": "starbucks", "radius_m": 100},
            ).status_code
            == 200
        )
    finally:
        app.dependency_overrides.clear()
        api_catalog.cache_clear()


@given(st.sampled_from(["chase-sapphire-preferred", "amex-gold", "amex-platinum", "bofa-customized-cash"]))
@settings(max_examples=4)
def test_owned_zero(card):
    from whichcard.data_layer import Catalog

    assert simulate_card(card, Catalog(), connect(":memory:"))["net_annual_cents"] == 0
