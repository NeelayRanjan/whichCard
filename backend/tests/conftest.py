import shutil
from pathlib import Path

import pytest
from whichcard.data_layer import Catalog
from whichcard.importers import import_file
from whichcard.inference import enrich
from whichcard.storage import connect


@pytest.fixture
def catalog(tmp_path):
    for directory in ["data", "config"]:
        shutil.copytree(
            directory, tmp_path / directory, ignore=shutil.ignore_patterns("*.local.yaml", "wallet.yaml")
        )
    return Catalog(tmp_path)


@pytest.fixture
def db(catalog):
    connection = connect(":memory:")
    for c in catalog.wallet.cards:
        import_file(connection, Path("backend/tests/fixtures") / f"{c.card}.csv", c.card)
    enrich(connection, catalog)
    connection.execute(
        "INSERT INTO statement(wallet_card_id,close_date,statement_balance,source) VALUES(?,?,?,?)",
        ("bofa-customized-cash", "2026-10-12", 120000, "manual"),
    )
    connection.commit()
    yield connection
    connection.close()
