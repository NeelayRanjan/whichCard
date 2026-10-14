from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections import defaultdict
from datetime import date
from typing import Any

from whichcard.data_layer import Catalog
from whichcard.engine import Context, money, recommend, shift_month, today
from whichcard.storage import transactions
from whichcard.trackers import trackers


def generate_findings(
    catalog: Catalog, db: sqlite3.Connection, day: date | None = None
) -> list[dict[str, Any]]:
    day = day or today()
    rows = transactions(db, before=day.isoformat())
    rows = [r for r in rows if r["transaction_date"] > shift_month(day, -12).isoformat()]
    tracking = trackers(catalog, db, day)
    findings = []

    def add(kind, key, title, detail, impact=None, evidence=None, severity="info"):
        fingerprint = hashlib.sha256(f"{kind}:{key}".encode()).hexdigest()[:24]
        findings.append(
            dict(
                fingerprint=fingerprint,
                kind=kind,
                title=title,
                detail=detail,
                dollar_impact=impact,
                evidence=evidence or {},
                severity=severity,
            )
        )

    misrouted: dict[str, dict[str, Any]] = defaultdict(
        lambda: dict(loss_cents=0, transaction_ids=[], best_cards=set())
    )
    for row in rows:
        if row["is_fee"] or row["is_payment"] or row["amount"] <= 0 or row["confidence"] < 0.7:
            continue
        prior = [r for r in rows if (r["transaction_date"], r["id"]) < (row["transaction_date"], row["id"])]
        result = recommend(
            Context(
                category=row["category"],
                merchant_id=row["merchant_id"],
                merchant_query=row["normalized_description"],
                channel=row["channel"],
                amount_cents=row["amount"],
                date=date.fromisoformat(row["transaction_date"]),
                is_foreign=bool(row["is_foreign"]),
            ),
            catalog,
            db,
            use_bonus=False,
            use_offers=False,
            rows=prior,
        )
        actual = next((r for r in result["ranked"] if r["card_id"] == row["wallet_card_id"]), None)
        if not actual or not result["ranked"]:
            continue
        delta = result["ranked"][0]["est_value_cents"] - actual["est_value_cents"]
        if delta > 0:
            group = misrouted[row["merchant_id"] or row["normalized_description"]]
            group["loss_cents"] += delta
            group["transaction_ids"].append(row["id"])
            group["best_cards"].add(result["ranked"][0]["card_id"])
    observed = max(
        1,
        (day - date.fromisoformat(min((r["transaction_date"] for r in rows), default=day.isoformat()))).days
        + 1,
    )
    factor = 365 / max(30, observed)
    for merchant, group in misrouted.items():
        group["best_cards"] = sorted(group["best_cards"])
        group["annualization_factor"] = factor
        annual = money(group["loss_cents"] * factor) / 100
        add(
            "misrouted_spend",
            merchant,
            f"Route {merchant} spending differently",
            f"${group['loss_cents'] / 100:.2f} estimated missed rewards in observed data; ${annual:.2f} annualized. Excludes uncertain merchants, offers and bonus goals.",
            annual,
            group,
        )
    for credit in tracking["credits"]:
        if credit["remaining_cents"]:
            add(
                "unused_credit",
                credit["card"] + credit["credit_id"] + credit["period_start"],
                f"{credit['name']} remains unused",
                f"${credit['remaining_cents'] / 100:.2f} remains; resets in {credit['days_until_reset']} days.",
                credit["remaining_cents"] / 100,
                credit,
                "warning",
            )
    for fee in tracking["fees"]:
        add(
            "fee_verdict",
            fee["card"],
            f"{fee['card']}: {fee['verdict']}",
            fee["arithmetic"],
            max(0, -fee["net_cents"]) / 100,
            fee,
        )
    for bonus in tracking["bonuses"]:
        if bonus["status"] in {"at_risk", "missed"}:
            add(
                "signup_bonus_risk",
                bonus["card"],
                f"Bonus {bonus['status'].replace('_', ' ')}",
                f"${bonus['remaining_cents'] / 100:.2f} still required.",
                None,
                bonus,
                "warning",
            )
    for utilization in tracking["utilization"]["cards"]:
        if utilization["alert"]:
            add(
                "utilization",
                utilization["card"],
                "Statement utilization above target",
                f"{utilization['card']} is at {utilization['utilization_pct']}%. This is a heuristic, not score prediction.",
                None,
                utilization,
                "warning",
            )
    if tracking["utilization"]["total_alert"]:
        add(
            "utilization",
            "total",
            "Total utilization above target",
            "Review the pay-down plan before statement dates.",
            None,
            tracking["utilization"],
            "warning",
        )
    for dormant in tracking["dormancy"]:
        if dormant["dormant"]:
            add(
                "dormancy",
                dormant["card"],
                "Card has been idle for 180+ days",
                "Consider a small recurring purchase if keeping this account.",
                None,
                dormant,
            )
    for instance in catalog.wallet.cards:
        card = catalog.cards[instance.card]
        for index, rule in enumerate(card.earn):
            if (
                rule.active
                and rule.active.from_ <= day <= rule.active.to
                and rule.active.requires_activation
                and not instance.settings.get(f"activated_{index}")
            ):
                add(
                    "rotation_inactive",
                    card.id + str(index),
                    "Rotating category needs activation",
                    f"{card.name}: confirm activation with issuer, then update wallet settings.",
                    None,
                    {"card": card.id, "rule": index},
                )
        anniversary = instance.opened_on.replace(year=day.year, day=min(instance.opened_on.day, 28))
        if anniversary < day:
            anniversary = shift_month(anniversary, 12)
        if card.annual_fee and (anniversary - day).days <= 45:
            add(
                "annual_fee_due",
                card.id,
                "Annual fee anniversary approaches",
                f"{card.name}: estimated anniversary {anniversary.isoformat()}. Confirm billing date.",
                card.annual_fee,
                {"date": anniversary.isoformat()},
            )
    for balance in catalog.wallet.balances:
        if balance.amount >= catalog.preferences.idle_points_threshold and (day - balance.as_of).days >= 0:
            add(
                "idle_points",
                balance.currency,
                "Points balance worth reviewing",
                f"{balance.amount:,} {balance.currency} points recorded on {balance.as_of}; no redemption activity is tracked, so actual dormancy is unknown.",
                money(balance.amount * catalog.valuation(balance.currency).cash_out) / 100,
                {"balance": balance.model_dump(mode="json")},
            )
    purchases = [r for r in rows if r["amount"] > 0 and not r["is_fee"] and not r["is_payment"]]
    uncertain = [r for r in purchases if r["confidence"] < 0.7]
    total = sum(r["amount"] for r in purchases)
    add(
        "data_quality",
        "coverage",
        "Review uncertain merchants and unverified terms",
        f"{100 * sum(r['amount'] for r in uncertain) / max(1, total):.1f}% of spending has inference confidence below 0.7. Card terms are unverified; computed statements may omit balances.",
        None,
        {
            "low_confidence_cents": sum(r["amount"] for r in uncertain),
            "total_cents": total,
            "unmatched": list(dict.fromkeys(r["raw_description"] for r in uncertain))[:10],
        },
    )
    generation = uuid.uuid4().hex
    with db:
        for f in findings:
            db.execute(
                "INSERT INTO finding(fingerprint,kind,severity,dollar_impact,title,detail,evidence_json,generation) VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(fingerprint) DO UPDATE SET severity=excluded.severity,dollar_impact=excluded.dollar_impact,title=excluded.title,detail=excluded.detail,evidence_json=excluded.evidence_json,generation=excluded.generation",
                (
                    f["fingerprint"],
                    f["kind"],
                    f["severity"],
                    f["dollar_impact"],
                    f["title"],
                    f["detail"],
                    json.dumps(f["evidence"]),
                    generation,
                ),
            )
        db.execute("DELETE FROM finding WHERE generation!=? AND dismissed_at IS NULL", (generation,))
    return read_findings(db, generation)


def read_findings(db: sqlite3.Connection, generation: str | None = None) -> list[dict[str, Any]]:
    rows = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM finding WHERE dismissed_at IS NULL ORDER BY COALESCE(dollar_impact,0) DESC,title"
        )
    ]
    for row in rows:
        row["evidence"] = json.loads(row.pop("evidence_json"))
    return [r for r in rows if generation is None or r["generation"] == generation]


def dismiss(db: sqlite3.Connection, fingerprint: str) -> None:
    with db:
        cursor = db.execute(
            "UPDATE finding SET dismissed_at=CURRENT_TIMESTAMP WHERE fingerprint=?", (fingerprint,)
        )
        if cursor.rowcount == 0:
            raise ValueError("finding not found")
