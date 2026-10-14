import pytest
from whichcard.inference import enrich, infer, normalize, override, review_queue
from whichcard.storage import transactions


def test_fixture_coverage(db, catalog):
    rows = transactions(db)
    assert sum(r["confidence"] >= 0.7 for r in rows) / len(rows) >= 0.9
    assert len(catalog.patterns) >= 250
    for name in ["COSTCO GAS #123", "WALMART SUPERCENTER", "TARGET", "AMAZON.COM"]:
        assert infer(name, catalog)["confidence"] <= 0.5
    assert any("AMAZON" in r["raw_description"] for r in review_queue(db))
    assert all(r["channel"] == "recurring" for r in rows if "NETFLIX" in r["raw_description"])


def test_normalizer_and_signals(catalog):
    assert normalize("SQ * BLUE BOTTLE #22 SAN FRANCISCO CA") == "BLUE BOTTLE"
    assert infer("SQ * BLUE BOTTLE", catalog)["channel"] == "online"
    assert infer("UNMATCHED", catalog, "Restaurants")["confidence"] == 0.7
    assert infer("CAFE EXAMPLE", catalog)["confidence"] == 0.4
    assert infer("MYSTERY XYZ", catalog)["confidence"] == 0


def test_override_future(db, catalog):
    row = next(r for r in transactions(db) if "AMAZON.COM" in r["raw_description"])
    override(db, catalog, row["id"], "category", "grocery")
    assert next(r for r in transactions(db) if r["id"] == row["id"])["category"] == "grocery"
    assert infer("AMAZON.COM ORDER 987654", catalog, db=db)["category"] == "grocery"
    assert (catalog.root / "data/merchants/learned.local.yaml").exists()
    enrich(db, catalog)
    override(db, catalog, row["id"], "channel", "online")
    assert next(r for r in transactions(db) if r["id"] == row["id"])["confidence"] == 1
    for field, value in [("amount", "1"), ("category", "bad"), ("channel", "bad")]:
        with pytest.raises(ValueError):
            override(db, catalog, row["id"], field, value)
    with pytest.raises(ValueError, match="not found"):
        override(db, catalog, 999999, "category", "other")
