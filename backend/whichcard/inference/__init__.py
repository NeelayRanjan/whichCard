from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from datetime import date
from typing import Any

from whichcard.data_layer import Catalog, write_yaml
from whichcard.data_layer.models import Pattern


def normalize(description: str) -> str:
    value = description.upper().strip()
    value = re.sub(r"^(SQ\s*\*|TST\s*\*|PAYPAL\s*\*|PY\s*\*)\s*", "", value)
    value = re.sub(
        r"\s+(SAN FRANCISCO|NEW YORK|LOS ANGELES|CHICAGO|SEATTLE|AUSTIN|BOSTON)\s+[A-Z]{2}$", "", value
    )
    value = re.sub(r"\s+#?\d{2,}\b", "", value)
    value = re.sub(r"\s+(ORDER|REF|REFERENCE)\s*[A-Z0-9-]*$", "", value)
    return re.sub(r"\s+", " ", value).strip()


def infer(
    description: str, catalog: Catalog, issuer_category: str = "", db: sqlite3.Connection | None = None
) -> dict[str, Any]:
    normalized = normalize(description)
    channel = (
        "online"
        if any(s in description.upper() for s in [".COM", "AMZN", "*", "UBER EATS", "DOORDASH"])
        else "in_person"
    )
    result: dict[str, Any] = dict(
        normalized_description=normalized,
        merchant_id=None,
        category="other",
        mcc=None,
        confidence=0.0,
        channel=channel,
        source="unknown",
    )
    if db is not None:
        alias = db.execute(
            "SELECT * FROM merchant_alias WHERE normalized_description=?", (normalized,)
        ).fetchone()
        if alias:
            result.update({k: alias[k] for k in ["merchant_id", "category", "mcc", "confidence", "source"]})
            return result
    for pattern in catalog.learned + catalog.patterns:
        if re.search(pattern.pattern, normalized, re.I):
            result.update(
                merchant_id=pattern.merchant_id,
                category=pattern.category,
                mcc=pattern.mcc,
                confidence=pattern.confidence,
                source="learned" if pattern in catalog.learned else "pattern",
            )
            break
    else:
        for category, definition in catalog.categories.items():
            if issuer_category and any(
                issuer_category.casefold() == alias.casefold()
                for aliases in definition.issuer_names.values()
                for alias in aliases
            ):
                result.update(category=category, confidence=0.7, source="issuer")
                break
        if not result["confidence"]:
            for word, category in {
                "COFFEE": "dining",
                "CAFE": "dining",
                "RESTAURANT": "dining",
                "GAS": "gas",
                "HOTEL": "lodging",
                "GROCERY": "grocery",
            }.items():
                if word in normalized:
                    result.update(category=category, confidence=0.4, source="keyword")
                    break
    if db is not None:
        db.execute(
            "INSERT OR IGNORE INTO merchant_alias(normalized_description,merchant_id,category,mcc,source,confidence) VALUES(?,?,?,?,?,?)",
            tuple(
                result[k]
                for k in ["normalized_description", "merchant_id", "category", "mcc", "source", "confidence"]
            ),
        )
    return result


def enrich(db: sqlite3.Connection, catalog: Catalog) -> None:
    rows = db.execute('SELECT * FROM "transaction" ORDER BY transaction_date').fetchall()
    recurring: dict[tuple[str, int], list[date]] = defaultdict(list)
    with db:
        for row in rows:
            result = infer(row["raw_description"], catalog, row["issuer_category"] or "", db)
            db.execute(
                'UPDATE "transaction" SET normalized_description=?,merchant_id=?,category=?,mcc=?,confidence=?,channel=? WHERE id=?',
                tuple(
                    result[k]
                    for k in [
                        "normalized_description",
                        "merchant_id",
                        "category",
                        "mcc",
                        "confidence",
                        "channel",
                    ]
                )
                + (row["id"],),
            )
            if row["amount"] > 0 and not row["is_fee"] and not row["is_payment"]:
                recurring[(result["normalized_description"], row["amount"])].append(
                    date.fromisoformat(row["transaction_date"])
                )
        for (description, amount), dates in recurring.items():
            dates = sorted(set(dates))
            gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
            if len(gaps) >= 2 and all(26 <= gap <= 35 for gap in gaps):
                db.execute(
                    'UPDATE "transaction" SET channel="recurring" WHERE normalized_description=? AND amount=?',
                    (description, amount),
                )


def override(
    db: sqlite3.Connection, catalog: Catalog, transaction_id: int, field: str, value: str
) -> dict[str, str]:
    if field not in {"merchant_id", "category", "channel"}:
        raise ValueError("override field must be merchant_id, category or channel")
    if field == "category" and value not in catalog.categories:
        raise ValueError("unknown category")
    if field == "channel" and value not in {"online", "in_person", "recurring"}:
        raise ValueError("unknown channel")
    row = db.execute('SELECT * FROM "transaction" WHERE id=?', (transaction_id,)).fetchone()
    if not row:
        raise ValueError("transaction not found")
    with db:
        db.execute(
            "INSERT INTO transaction_override(transaction_id,field,value) VALUES(?,?,?) "
            "ON CONFLICT(transaction_id,field) DO UPDATE SET value=excluded.value,set_at=CURRENT_TIMESTAMP",
            (transaction_id, field, value),
        )
        repeated = db.execute(
            'SELECT COUNT(*) FROM "transaction" WHERE normalized_description=?',
            (row["normalized_description"],),
        ).fetchone()[0]
        if repeated > 1 and field != "channel":
            values = dict(row)
            # Incorporate earlier corrections before generalizing.
            for correction in db.execute(
                "SELECT field,value FROM transaction_override WHERE transaction_id=?", (transaction_id,)
            ):
                values[correction["field"]] = correction["value"]
            pattern = Pattern(
                pattern="^" + re.escape(row["normalized_description"]) + "$",
                merchant_id=values["merchant_id"]
                or normalize(values["raw_description"]).lower().replace(" ", "-"),
                display_name=values["normalized_description"],
                category=values["category"],
                mcc=values["mcc"],
                confidence=1,
            )
            catalog.learned = [pattern] + [p for p in catalog.learned if p.pattern != pattern.pattern]
            write_yaml(
                catalog.root / "data/merchants/learned.local.yaml", [p.model_dump() for p in catalog.learned]
            )
            db.execute(
                "DELETE FROM merchant_alias WHERE normalized_description=?", (row["normalized_description"],)
            )
    return {"status": "saved"}


def review_queue(db: sqlite3.Connection) -> list[dict[str, Any]]:
    from whichcard.storage import transactions

    return [r for r in transactions(db) if r["confidence"] < 0.7 and not r["is_fee"] and not r["is_payment"]]
