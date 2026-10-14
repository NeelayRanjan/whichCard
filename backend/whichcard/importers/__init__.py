from __future__ import annotations

import csv
import hashlib
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Protocol


@dataclass
class RawTransaction:
    transaction_date: str
    amount: int
    raw_description: str
    posted_date: str | None = None
    currency: str = "USD"
    issuer_category: str = ""
    is_refund: bool = False
    is_fee: bool = False
    is_payment: bool = False
    is_foreign: bool = False


class ImportSource(Protocol):
    def read(self, path: Path) -> Iterable[RawTransaction]: ...


def parse_date(value: str) -> str:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y%m%d", "%d/%m/%Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"invalid date {value!r}")


def cents(value: str) -> int:
    clean = value.strip().replace("$", "").replace(",", "")
    if not clean:
        return 0
    if clean.startswith("(") and clean.endswith(")"):
        clean = "-" + clean[1:-1]
    try:
        return int((Decimal(clean) * 100).quantize(Decimal("1")))
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount {value!r}") from exc


HEADERS = {
    "chase": ["Transaction Date", "Post Date", "Description", "Category", "Type", "Amount", "Memo"],
    "amex": ["Date", "Description", "Amount", "Extended Details", "Category"],
    "capitalone": [
        "Transaction Date",
        "Posted Date",
        "Card No.",
        "Description",
        "Category",
        "Debit",
        "Credit",
    ],
    "citi": ["Status", "Date", "Description", "Debit", "Credit"],
    "bofa": ["Posted Date", "Reference Number", "Payee", "Address", "Amount"],
    "discover": ["Trans. Date", "Post Date", "Description", "Amount", "Category"],
    "wellsfargo": ["Date", "Amount", "Star", "Check Number", "Description"],
    "apple": [
        "Transaction Date",
        "Clearing Date",
        "Description",
        "Merchant",
        "Category",
        "Type",
        "Amount (USD)",
        "Purchased By",
    ],
    "generic": ["Date", "Description", "Amount", "Category", "Currency"],
}


def detect(headers: list[str]) -> str:
    names = set(headers)
    for marker, adapter in [
        ("Purchased By", "apple"),
        ("Card No.", "capitalone"),
        ("Extended Details", "amex"),
        ("Trans. Date", "discover"),
        ("Reference Number", "bofa"),
        ("Status", "citi"),
        ("Check Number", "wellsfargo"),
        ("Memo", "chase"),
    ]:
        if marker in names:
            return adapter
    return "generic"


class CSVSource:
    def __init__(self, adapter: str | None = None):
        self.adapter = adapter

    def read(self, path: Path) -> Iterable[RawTransaction]:
        text = path.read_text(encoding="utf-8-sig")
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(text.splitlines(), dialect=dialect)
        headers = list(reader.fieldnames or [])
        adapter = self.adapter or detect(headers)
        if adapter not in HEADERS:
            raise ValueError(f"unknown adapter: {adapter}")
        self.adapter = adapter
        rows = list(reader)
        lower = {h.lower().strip(): h for h in headers}

        def column(*names):
            return next((lower[n] for n in names if n in lower), None)

        date_col = column("transaction date", "trans. date", "date", "posted date", "post date")
        desc_col = column("description", "payee", "merchant", "name", "memo", "details")
        amount_col = column("amount", "amount (usd)", "transaction amount", "total")
        debit_col, credit_col = column("debit", "debit amount"), column("credit", "credit amount")
        # Unknown headings: infer dates/numbers from values, then the remaining text column.
        sample = rows[:10]
        if sample and not date_col:
            for h in headers:
                try:
                    for r in sample:
                        parse_date(r[h])
                    date_col = h
                    break
                except (ValueError, TypeError):
                    pass
        if sample and not amount_col and not debit_col:
            for h in headers:
                if h == date_col:
                    continue
                try:
                    for r in sample:
                        cents(r[h])
                    amount_col = h
                    break
                except (ValueError, TypeError):
                    pass
        if not desc_col:
            desc_col = next(
                (h for h in headers if h not in {date_col, amount_col, debit_col, credit_col}), None
            )
        for name, found in [
            ("date", date_col),
            ("description", desc_col),
            ("amount", amount_col or debit_col),
        ]:
            if not found:
                raise ValueError(f"missing {name} column; headers: {headers}")
        for index, row in enumerate(rows, 2):
            try:
                description = row[str(desc_col)].strip()
                if not description:
                    raise ValueError("missing description")
                amount = (
                    cents(row.get(debit_col or "", "")) - cents(row.get(credit_col or "", ""))
                    if debit_col
                    else cents(row[str(amount_col)])
                )
                if not debit_col and adapter in {"chase", "bofa", "wellsfargo"}:
                    amount *= -1
                currency = row.get(column("currency") or "", "USD") or "USD"
                payment = bool(re.search(r"PAYMENT|AUTOPAY|THANK YOU", description, re.I))
                fee = bool(re.search(r"INTEREST|ANNUAL FEE|LATE FEE|FINANCE CHARGE", description, re.I))
                yield RawTransaction(
                    parse_date(row[str(date_col)]),
                    amount,
                    description,
                    parse_date(row[column("post date", "posted date", "clearing date")])
                    if column("post date", "posted date", "clearing date")
                    and row.get(column("post date", "posted date", "clearing date"))
                    else None,
                    currency,
                    row.get(column("category") or "", ""),
                    amount < 0 and not payment,
                    fee,
                    payment,
                    currency != "USD",
                )
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"{path.name}: row {index}: {exc}") from exc


class OFXSource:
    def read(self, path: Path) -> Iterable[RawTransaction]:
        text = path.read_text(encoding="utf-8-sig")
        for block in re.findall(
            r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>|</BANKTRANLIST>))", text, re.S | re.I
        ):

            def tag(name: str) -> str:
                match = re.search(rf"<{name}>([^<\r\n]+)", block, re.I)
                return match.group(1).strip() if match else ""

            amount = -cents(tag("TRNAMT"))
            description = " ".join(x for x in [tag("NAME"), tag("MEMO")] if x)
            if not description or not tag("DTPOSTED") or not tag("TRNAMT"):
                raise ValueError(f"{path.name}: OFX requires date, amount and description")
            payment = tag("TRNTYPE") == "PAYMENT" or "PAYMENT" in description.upper()
            yield RawTransaction(
                parse_date(tag("DTPOSTED")[:8]),
                amount,
                description,
                is_refund=amount < 0 and not payment,
                is_fee=tag("TRNTYPE") in {"FEE", "INT"},
                is_payment=payment,
            )
        if "<STMTTRN>" not in text.upper():
            raise ValueError(f"{path.name}: no OFX transaction rows")


def import_file(
    db: sqlite3.Connection, path: Path, card: str, adapter: str | None = None
) -> dict[str, int | str]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if db.execute(
        "SELECT 1 FROM import_batch WHERE file_hash=? AND wallet_card_id=?", (digest, card)
    ).fetchone():
        return {"added": 0, "duplicate": "file"}
    source: CSVSource | OFXSource = (
        OFXSource() if adapter == "ofx" or path.suffix.lower() in {".ofx", ".qfx"} else CSVSource(adapter)
    )
    rows = list(source.read(path))  # Parse the whole input before mutating storage.
    name = source.adapter if isinstance(source, CSVSource) else "ofx"
    with db:
        cursor = db.execute(
            "INSERT INTO import_batch(source_file,file_hash,adapter,wallet_card_id) VALUES(?,?,?,?)",
            (path.name, digest, name, card),
        )
        added = 0
        for raw in rows:
            row = asdict(raw)
            key = "\x1f".join([card, raw.transaction_date, str(raw.amount), raw.raw_description])
            row.update(
                wallet_card_id=card,
                import_batch_id=cursor.lastrowid,
                normalized_description=raw.raw_description.upper(),
                dedupe_hash=hashlib.sha256(key.encode()).hexdigest(),
            )
            fields = ",".join(row)
            result = db.execute(
                f'INSERT OR IGNORE INTO "transaction"({fields}) VALUES({",".join("?" for _ in row)})',
                list(row.values()),
            )
            added += result.rowcount
        db.execute("UPDATE import_batch SET row_count=? WHERE id=?", (added, cursor.lastrowid))
    return {"added": added, "parsed": len(rows), "adapter": name or "generic"}
