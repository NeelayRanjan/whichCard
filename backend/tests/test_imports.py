import importlib.util
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from whichcard.importers import HEADERS, CSVSource, OFXSource, cents, import_file, parse_date
from whichcard.storage import connect, migrate, transactions

FIX = Path("backend/tests/fixtures")


@pytest.mark.parametrize("adapter", HEADERS)
def test_adapter(adapter):
    rows = list(CSVSource().read(FIX / f"adapter-{adapter}.csv"))
    assert len(rows) == 13
    assert rows[0].amount == -5000
    assert rows[0].is_refund
    assert any(r.is_fee for r in rows)
    assert any(r.is_payment for r in rows)
    assert rows[-1].amount == 1999


def test_ofx_and_dedupe():
    assert len(list(OFXSource().read(FIX / "sample.ofx"))) == 13
    db = connect(":memory:")
    migrate(db)
    result = import_file(db, FIX / "bofa-customized-cash.csv", "bofa-customized-cash")
    assert result["added"] > 200
    assert import_file(db, FIX / "bofa-customized-cash.csv", "bofa-customized-cash")["added"] == 0
    assert import_file(db, FIX / "duplicate.csv", "bofa-customized-cash")["added"] == 0
    assert any(r["is_foreign"] for r in transactions(db))
    assert db.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == 1


@given(st.integers(min_value=1, max_value=5))
@settings(max_examples=5)
def test_dedupe_property(repeats):
    db = connect(":memory:")
    for _ in range(repeats):
        import_file(db, FIX / "adapter-chase.csv", "test")
    assert len(transactions(db)) == 13


def test_generic_and_errors(tmp_path):
    p = tmp_path / "odd.csv"
    p.write_text("when,thing,value\n2026-01-01,Example,12.34\n")
    assert list(CSVSource().read(p))[0].amount == 1234
    p.write_text("description,amount\nExample,12.34\n")
    with pytest.raises(ValueError, match="missing date column"):
        list(CSVSource().read(p))
    p.write_text("Date,Description,Amount\n2026-01-01,Example,12\ninvalid,Example,2\n")
    db = connect(":memory:")
    with pytest.raises(ValueError, match="row 3"):
        import_file(db, p, "test")
    assert not transactions(db)
    assert cents("($1,000.50)") == -100050
    assert parse_date("01/02/2026") == "2026-01-02"


def test_fixture_generation_is_deterministic():
    spec = importlib.util.spec_from_file_location("fixtures", "backend/scripts/gen_fixtures.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first = (FIX / "combined.json").read_bytes()
    module.generate()
    assert first == (FIX / "combined.json").read_bytes()


def test_headerless_wells(tmp_path):
    p = tmp_path / "wells.csv"
    p.write_text("10/01/2026,-25.10,*,0,STARBUCKS\n10/02/2026,5.00,*,0,REFUND\n")
    rows = list(CSVSource().read(p))
    assert [r.amount for r in rows] == [2510, -500]
    assert rows[1].is_refund
