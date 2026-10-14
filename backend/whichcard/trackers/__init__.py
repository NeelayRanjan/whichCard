from __future__ import annotations

import calendar
import sqlite3
from datetime import date, timedelta
from typing import Any

from whichcard.data_layer import Catalog
from whichcard.data_layer.models import Credit, WalletCard
from whichcard.engine import bonus_status, card_rate, eligible, matches, money, period, shift_month, today
from whichcard.storage import transactions


def credit_status(
    instance: WalletCard, credit: Credit, rows: list[dict[str, Any]], db: sqlite3.Connection, day: date
) -> dict[str, Any]:
    start, end = period(day, credit.period, credit.reset, instance.opened_on)
    matched = [
        r
        for r in eligible(
            rows, instance.card, max(start, instance.opened_on), min(end, day + timedelta(days=1))
        )
        if matches(credit.match, r, instance)
    ]
    auto = max(0, sum(r["amount"] for r in matched))
    manual = db.execute(
        'SELECT COALESCE(SUM(amount_used),0) FROM credit_usage WHERE wallet_card_id=? AND credit_id=? AND period_start=? AND source="manual"',
        (instance.card, credit.id, start.isoformat()),
    ).fetchone()[0]
    used = min(money(credit.amount * 100), max(auto, manual))
    with db:
        db.execute(
            'DELETE FROM credit_usage WHERE wallet_card_id=? AND credit_id=? AND period_start=? AND source="auto"',
            (instance.card, credit.id, start.isoformat()),
        )
        for r in matched:
            db.execute(
                "INSERT INTO credit_usage(wallet_card_id,credit_id,period_start,period_end,amount_used,source,transaction_id) VALUES(?,?,?,?,?,?,?)",
                (instance.card, credit.id, start.isoformat(), end.isoformat(), r["amount"], "auto", r["id"]),
            )
    return dict(
        card=instance.card,
        credit_id=credit.id,
        name=credit.name,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        used_cents=used,
        remaining_cents=money(credit.amount * 100) - used,
        days_until_reset=(end - day).days,
        source="manual" if manual > auto else "auto",
    )


def mark_credit(
    db: sqlite3.Connection, catalog: Catalog, card: str, credit_id: str, amount_cents: int, day: date
) -> None:
    instance = next((c for c in catalog.wallet.cards if c.card == card), None)
    credit = (
        next((c for c in catalog.cards[card].credits if c.id == credit_id), None)
        if card in catalog.cards
        else None
    )
    if not instance or not credit or amount_cents < 0 or amount_cents > money(credit.amount * 100):
        raise ValueError("unknown wallet credit or amount outside credit allowance")
    start, end = period(day, credit.period, credit.reset, instance.opened_on)
    with db:
        db.execute(
            'DELETE FROM credit_usage WHERE wallet_card_id=? AND credit_id=? AND period_start=? AND source="manual"',
            (card, credit_id, start.isoformat()),
        )
        db.execute(
            "INSERT INTO credit_usage(wallet_card_id,credit_id,period_start,period_end,amount_used,source) VALUES(?,?,?,?,?,?)",
            (card, credit_id, start.isoformat(), end.isoformat(), amount_cents, "manual"),
        )


def fee_break_even(
    instance: WalletCard, catalog: Catalog, db: sqlite3.Connection, rows: list[dict[str, Any]], day: date
) -> dict[str, Any]:
    card = catalog.cards[instance.card]
    start = shift_month(day, -12) + timedelta(days=1)
    uplift = 0
    for row in eligible(rows, instance.card, start, day + timedelta(days=1)):
        ctx = dict(row, date=date.fromisoformat(row["transaction_date"]), amount_cents=abs(row["amount"]))
        prior = [r for r in rows if (r["transaction_date"], r["id"]) < (row["transaction_date"], row["id"])]
        actual = card_rate(card, instance, ctx, prior, catalog)["effective_rate_pct"]
        alternatives = [
            card_rate(catalog.cards[c.card], c, ctx, prior, catalog)["effective_rate_pct"]
            for c in catalog.wallet.cards
            if c.card != card.id and c.opened_on <= ctx["date"]
        ]
        uplift += money(row["amount"] * (actual - max(alternatives, default=0)) / 100)
    credit_total = 0
    for credit in card.credits:
        seen = set()
        cursor = start
        while cursor <= day:
            beginning, end = period(cursor, credit.period, credit.reset, instance.opened_on)
            if beginning not in seen:
                # Restrict matching to the trailing-year measurement window.
                selected = [r for r in rows if start.isoformat() <= r["transaction_date"] <= day.isoformat()]
                credit_total += credit_status(
                    instance, credit, selected, db, min(end - timedelta(days=1), day)
                )["used_cents"]
                seen.add(beginning)
            cursor = end
    perks = money(catalog.preferences.perk_values.get(card.id, 0) * 100)
    fee = money(card.annual_fee * 100)
    net = uplift + credit_total + perks - fee
    verdict = "keep" if net >= 0 else "downgrade" if card.product_change_targets else "cancel"
    return dict(
        card=card.id,
        annual_fee_cents=fee,
        earning_uplift_cents=uplift,
        credits_used_cents=credit_total,
        perk_value_cents=perks,
        net_cents=net,
        verdict=verdict,
        product_change_targets=card.product_change_targets,
        arithmetic=f"${uplift / 100:.2f} earning uplift + ${credit_total / 100:.2f} credits + ${perks / 100:.2f} perks − ${fee / 100:.2f} fee = ${net / 100:.2f}",
        note="Historical marginal value against other wallet cards; not a prediction. Check unverified terms.",
    )


def account_timeline(catalog: Catalog, day: date) -> dict[str, Any]:
    active = sorted(
        [
            dict(
                card=c.card,
                opened_on=c.opened_on.isoformat(),
                ages_out=shift_month(c.opened_on, 24).isoformat(),
                authorized_user=c.authorized_user,
            )
            for c in catalog.wallet.cards
            if c.opened_on <= day < shift_month(c.opened_on, 24)
        ],
        key=lambda x: str(x["ages_out"]),
    )
    next_under = day.isoformat() if len(active) < 5 else active[len(active) - 5]["ages_out"]
    inquiries = [
        dict(date=i.date.isoformat(), note=i.note, ages_out=shift_month(i.date, 24).isoformat())
        for i in catalog.wallet.inquiries
        if i.date <= day
    ]
    inquiries += [
        dict(
            date=c.opened_on.isoformat(),
            note=f"Assumed opening inquiry: {c.card}",
            ages_out=shift_month(c.opened_on, 24).isoformat(),
        )
        for c in catalog.wallet.cards
        if c.opened_on <= day and not c.authorized_user
    ]
    return dict(
        count_5_24=len(active),
        accounts=active,
        next_under_5_24=next_under,
        inquiries=inquiries,
        inquiries_12m=sum(shift_month(day, -12).isoformat() < i["date"] for i in inquiries),
        inquiries_24m=sum(shift_month(day, -24).isoformat() < i["date"] for i in inquiries),
        note="Heuristic: includes authorized-user accounts in 5/24; issuers may treat them differently. Opening inquiries are assumed, not bureau records.",
    )


def utilization(
    catalog: Catalog, db: sqlite3.Connection, rows: list[dict[str, Any]], day: date
) -> dict[str, Any]:
    results = []
    for c in catalog.wallet.cards:

        def close_on(month: date) -> date:
            return month.replace(day=min(c.statement_day, calendar.monthrange(month.year, month.month)[1]))

        close = close_on(day)
        if close > day:
            close = close_on(shift_month(day.replace(day=1), -1))
        previous = close_on(shift_month(close.replace(day=1), -1))
        statement = db.execute(
            "SELECT * FROM statement WHERE wallet_card_id=? AND close_date<=? ORDER BY close_date DESC LIMIT 1",
            (c.card, day.isoformat()),
        ).fetchone()
        if (
            statement is not None
            and statement["source"] == "manual"
            and statement["close_date"] >= close.isoformat()
        ):
            balance = max(0, statement["statement_balance"])
            source = "manual"
        else:
            balance = max(
                0,
                sum(
                    r["amount"]
                    for r in rows
                    if r["wallet_card_id"] == c.card
                    and previous.isoformat() < r["transaction_date"] <= close.isoformat()
                ),
            )
            with db:
                db.execute(
                    "INSERT INTO statement(wallet_card_id,close_date,statement_balance,source) VALUES(?,?,?,?) "
                    "ON CONFLICT(wallet_card_id,close_date) DO UPDATE SET statement_balance=excluded.statement_balance "
                    'WHERE statement.source="computed"',
                    (c.card, close.isoformat(), balance, "computed"),
                )
            source = "computed"
        limit = money(c.credit_limit * 100)
        pct = 100 * balance / limit
        results.append(
            dict(
                card=c.card,
                balance_cents=balance,
                limit_cents=limit,
                utilization_pct=round(pct, 2),
                source=source,
                alert=pct > catalog.preferences.utilization_targets.per_card,
                pay_down_cents=max(
                    0, balance - money(limit * catalog.preferences.utilization_targets.per_card / 100)
                ),
                next_statement=close_on(shift_month(close.replace(day=1), 1)).isoformat(),
            )
        )
    total_balance = sum(r["balance_cents"] for r in results)
    total_limit = sum(r["limit_cents"] for r in results)
    total = 100 * total_balance / total_limit if total_limit else 0
    return dict(
        cards=results,
        total_pct=round(total, 2),
        total_alert=total > catalog.preferences.utilization_targets.total,
        total_pay_down_cents=max(
            0, total_balance - money(total_limit * catalog.preferences.utilization_targets.total / 100)
        ),
        targets=catalog.preferences.utilization_targets.model_dump(),
        note="Heuristic, not a credit-score prediction. Computed balances omit carried balances; enter actual statements.",
    )


def trackers(catalog: Catalog, db: sqlite3.Connection, day: date | None = None) -> dict[str, Any]:
    day = day or today()
    rows = transactions(db, before=day.isoformat())
    bonuses = []
    credits = []
    fees = []
    dormancy = []
    for c in catalog.wallet.cards:
        bonus = bonus_status(c, rows, day)
        if bonus:
            bonuses.append(bonus)
        for credit in catalog.cards[c.card].credits:
            credits.append(credit_status(c, credit, rows, db, day))
        if catalog.cards[c.card].annual_fee:
            fees.append(fee_break_even(c, catalog, db, rows, day))
        last = max(
            (
                r["transaction_date"]
                for r in rows
                if r["wallet_card_id"] == c.card
                and r["amount"] > 0
                and not r["is_fee"]
                and not r["is_payment"]
            ),
            default=c.opened_on.isoformat(),
        )
        days = (day - date.fromisoformat(last)).days
        dormancy.append(dict(card=c.card, last_purchase=last, days=days, dormant=days >= 180))
    return dict(
        as_of=day.isoformat(),
        bonuses=bonuses,
        credits=credits,
        fees=fees,
        dormancy=dormancy,
        utilization=utilization(catalog, db, rows, day),
        timeline=account_timeline(catalog, day),
    )
