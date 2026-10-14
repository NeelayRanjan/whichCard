"""Deterministic synthetic exports. No real user data is read or copied."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml
from whichcard.data_layer import ROOT
from whichcard.importers import HEADERS, import_file
from whichcard.storage import connect

OUT = ROOT / "backend/tests/fixtures"


def export(path, adapter, rows):
    headers = HEADERS[adapter] + ["Currency"] if "Currency" not in HEADERS[adapter] else HEADERS[adapter]
    with path.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            amount = r["amount"] / 100
            line = {h: "" for h in headers}
            for h in headers:
                if h in {
                    "Transaction Date",
                    "Date",
                    "Trans. Date",
                    "Post Date",
                    "Posted Date",
                    "Clearing Date",
                }:
                    line[h] = r["date"]
                elif h in {"Description", "Payee", "Merchant"}:
                    line[h] = r["description"]
                elif h in {"Amount", "Amount (USD)"}:
                    line[h] = f"{-amount if adapter in {'chase', 'bofa', 'wellsfargo'} else amount:.2f}"
                elif h == "Debit":
                    line[h] = f"{max(amount, 0):.2f}"
                elif h == "Credit":
                    line[h] = f"{max(-amount, 0):.2f}"
                elif h == "Category":
                    line[h] = r.get("category", "Other")
                elif h == "Currency":
                    line[h] = r.get("currency", "USD")
            writer.writerow(line)


def generate():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []

    def add(card, date, amount, description, category="Other", currency="USD"):
        rows.append(
            dict(
                card=card,
                date=date,
                amount=amount,
                description=description,
                category=category,
                currency=currency,
            )
        )

    # Four-card example wallet; cap/rotation stress cases use an additional isolated test export.
    for index in range(12):
        month = (index + 10) % 12 + 1
        year = 2025 if month >= 11 else 2026
        date = f"{year}-{month:02}"
        for day in range(1, 21):
            add("amex-gold", f"{date}-{day:02}", 12000, "CHIPOTLE #102 SAN FRANCISCO CA", "Restaurants")
            add(
                "bofa-customized-cash", f"{date}-{day:02}", 4500, "SAFEWAY #202 SAN FRANCISCO CA", "Groceries"
            )
        add("amex-gold", f"{date}-22", 1599, "NETFLIX.COM", "Streaming")
        if month not in {2, 6, 10}:
            add("amex-gold", f"{date}-23", 2000, "UBER EATS", "Restaurants")
        add("bofa-customized-cash", f"{date}-24", 3500, "AMAZON.COM ORDER 123456", "Shopping")
        if date < "2026-04":
            add("amex-platinum", f"{date}-05", 5000, "SHELL #101", "Gas")
    for day in [5, 15, 25]:
        add("chase-sapphire-preferred", f"2026-09-{day:02}", 10000, "STARBUCKS #122", "Restaurants")
    add("chase-sapphire-preferred", "2026-10-05", 10000, "STARBUCKS #122", "Restaurants")
    add("chase-sapphire-preferred", "2026-10-20", 350000, "UNITED AIRLINES", "Airlines")
    for day in [2, 6, 10]:
        add("bofa-customized-cash", f"2026-10-{day:02}", 90000, "AMZN DIGITAL", "Shopping")
    for amount, desc in [
        (-5000, "TARGET REFUND"),
        (-2000, "TARGET PARTIAL REFUND"),
        (-3000, "DISPUTED REVERSAL"),
        (1299, "INTEREST CHARGE"),
        (9500, "ANNUAL FEE"),
        (-100000, "PAYMENT THANK YOU"),
        (4500, "COSTCO GAS #0123"),
        (8000, "WALMART SUPERCENTER #22"),
        (3000, "TARGET #45"),
        (600, "SQ * BLUE BOTTLE"),
        (1400, "STARBUCKS.COM"),
        (1500, "STARBUCKS #99"),
        (1999, "MYSTERY XYZ"),
    ]:
        add("bofa-customized-cash", "2026-10-11", amount, desc)
    add("bofa-customized-cash", "2026-10-12", 7000, "CAFE PARIS", "Restaurants", "EUR")
    (OUT / "combined.json").write_text(json.dumps(rows, indent=2) + "\n")
    for card, adapter in [
        ("chase-sapphire-preferred", "chase"),
        ("bofa-customized-cash", "bofa"),
        ("amex-gold", "amex"),
        ("amex-platinum", "amex"),
    ]:
        export(OUT / f"{card}.csv", adapter, [r for r in rows if r["card"] == card])
    sample = [
        r
        for r in rows
        if r["date"] == "2026-10-11" and not r["description"].startswith(("CHIPOTLE", "SAFEWAY"))
    ]
    for adapter in HEADERS:
        export(OUT / f"adapter-{adapter}.csv", adapter, sample)
    duplicate = [r for r in rows if r["card"] == "bofa-customized-cash"][:1]
    export(OUT / "duplicate.csv", "bofa", duplicate)
    ofx = "<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>"
    for r in sample:
        ofx += (
            f"<STMTTRN><TRNTYPE>{'PAYMENT' if 'PAYMENT' in r['description'] else 'DEBIT'}"
            f"<DTPOSTED>{r['date'].replace('-', '')}<TRNAMT>{-r['amount'] / 100:.2f}"
            f"<NAME>{r['description']}</STMTTRN>"
        )
    (OUT / "sample.ofx").write_text(ofx + "</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>")
    export(
        OUT / "rotation.csv",
        "chase",
        [
            dict(date=f"2026-10-{d:02}", amount=80000, description="SHELL GAS", category="Gas")
            for d in [3, 10]
        ],
    )
    manifest = {
        "as_of": "2026-10-14",
        "start": "2025-11-01",
        "end": "2026-10-31",
        "cap_date": "2026-10-10",
        "rotation_active": "2026-10-01",
        "rotation_inactive": "2027-01-01",
        "bonus_at_risk": "2026-10-14",
        "bonus_on_track": "2026-10-20",
        "missed_credit_months": [2, 6, 10],
        "last_platinum_purchase": "2026-03-05",
        "utilization": {
            "wallet_card_id": "bofa-customized-cash",
            "close_date": "2026-10-12",
            "balance_cents": 120000,
        },
        "expected_rows": len(rows),
        "rotation_card": "chase-freedom-flex",
    }
    (ROOT / "backend/tests/fixture_manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))
    return rows


def fixture_db(path: Path):
    db = connect(path)
    for card in ["chase-sapphire-preferred", "bofa-customized-cash", "amex-gold", "amex-platinum"]:
        import_file(db, OUT / f"{card}.csv", card)
    import_file(db, OUT / "duplicate.csv", "bofa-customized-cash")
    with db:
        db.execute(
            "INSERT OR REPLACE INTO statement(wallet_card_id,close_date,statement_balance,source) VALUES(?,?,?,?)",
            ("bofa-customized-cash", "2026-10-12", 120000, "manual"),
        )
    from whichcard.data_layer import Catalog
    from whichcard.inference import enrich

    enrich(db, Catalog())
    return db


if __name__ == "__main__":
    generate()
    db = fixture_db(ROOT / "var/fixtures.db")
    print(
        f"Synthetic fixture database: {ROOT}/var/fixtures.db; {db.execute('SELECT COUNT(*) FROM [transaction]').fetchone()[0]} rows"
    )
    db.close()
