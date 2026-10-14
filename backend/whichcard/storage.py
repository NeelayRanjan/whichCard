from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from whichcard.data_layer import ROOT


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = path or os.environ.get("WHICHCARD_DB", str(ROOT / "var/whichcard.db"))
    assert path is not None
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    migrate(db)
    return db


def migrate(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, "
        "applied_at TEXT DEFAULT CURRENT_TIMESTAMP, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    for p in sorted((ROOT / "backend/migrations").glob("*.sql")):
        version = int(p.name.split("_")[0])
        if not db.execute("SELECT 1 FROM schema_version WHERE version=?", (version,)).fetchone():
            db.executescript(
                "BEGIN;\n"
                + p.read_text()
                + f"\nINSERT INTO schema_version(version) VALUES({version});\nCOMMIT;"
            )


def transactions(
    db: sqlite3.Connection, card: str | None = None, before: str | None = None
) -> list[dict[str, Any]]:
    rows = [dict(r) for r in db.execute('SELECT * FROM "transaction" ORDER BY transaction_date, id')]
    overrides = db.execute("SELECT transaction_id,field,value FROM transaction_override").fetchall()
    by_id = {r["id"]: r for r in rows}
    for override in overrides:
        if override["transaction_id"] in by_id:
            row = by_id[override["transaction_id"]]
            row[override["field"]] = override["value"]
            row["confidence"] = 1.0
    return [
        r
        for r in rows
        if (card is None or r["wallet_card_id"] == card)
        and (before is None or r["transaction_date"] <= before)
    ]
