from __future__ import annotations

import calendar
import os
import re
import sqlite3
from datetime import date as Date
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from pydantic import Field

from whichcard.data_layer import Catalog
from whichcard.data_layer.models import Card, Match, Model, WalletCard
from whichcard.inference import infer
from whichcard.storage import transactions


def today() -> Date:
    return (
        Date.fromisoformat(os.environ["WHICHCARD_TODAY"]) if "WHICHCARD_TODAY" in os.environ else Date.today()
    )


def money(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def shift_month(day: Date, months: int) -> Date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return Date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))


def period(day: Date, kind: str, basis: str = "calendar", opened: Date | None = None) -> tuple[Date, Date]:
    months = {"month": 1, "quarter": 3, "annual": 12}[kind]
    anchor = opened if basis == "anniversary" and opened else Date(day.year, 1, 1)
    elapsed = (day.year - anchor.year) * 12 + day.month - anchor.month
    start = shift_month(anchor, elapsed // months * months)
    if start > day:
        start = shift_month(start, -months)
    return start, shift_month(start, months)


class Context(Model):
    merchant_id: str | None = None
    merchant_query: str | None = None
    category: str | None = None
    amount_cents: int = Field(default=0, ge=0)
    channel: Literal["in_person", "online", "recurring"] | None = None
    app_context: str | None = None
    date: Date = Field(default_factory=today)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    is_foreign: bool = False
    portal: str | None = None
    mcc: int | None = None


def resolve(context: Context, catalog: Catalog) -> tuple[dict[str, Any], float]:
    data = context.model_dump()
    confidence = 1.0 if context.category and context.category != "other" else 0.0
    if context.merchant_query:
        if context.merchant_query.lower() in catalog.categories:
            data["category"] = context.category or context.merchant_query.lower()
            confidence = 1
        else:
            inferred = infer(context.merchant_query, catalog)
            for key in ["merchant_id", "category", "channel", "mcc"]:
                if data.get(key) is None:
                    data[key] = inferred[key]
            data["normalized_description"] = inferred["normalized_description"]
            confidence = inferred["confidence"] if not context.category else 1
    if context.app_context in catalog.apps:
        app = catalog.apps[str(context.app_context)]
        data["category"] = context.category or app.category
        data["channel"] = context.channel or app.channel
        confidence = max(confidence, 0.7)
    data["category"] = data.get("category") or "other"
    data["channel"] = data.get("channel") or "in_person"
    data["normalized_description"] = data.get("normalized_description") or (
        data.get("merchant_id") or ""
    ).upper().replace("-", " ")
    return data, confidence


def matches(match: Match, context: dict[str, Any], instance: WalletCard | None = None) -> bool:
    for key, value in match.model_dump(exclude_none=True).items():
        if key == "any":
            continue
        if key == "category" and value == "chosen":
            value = instance.settings.get("chosen_category") if instance else None
            if value is None:
                return False
        if key == "merchant_pattern":
            if not re.search(value, context.get("normalized_description", ""), re.I):
                return False
        elif key == "mcc":
            if context.get("mcc") not in value:
                return False
        elif context.get(key) != value:
            return False
    return True


def eligible(rows: list[dict[str, Any]], card: str, start: Date, end: Date) -> list[dict[str, Any]]:
    return [
        r
        for r in rows
        if r["wallet_card_id"] == card
        and start.isoformat() <= r["transaction_date"] < end.isoformat()
        and not r["is_fee"]
        and not r["is_payment"]
    ]


def bonus_status(instance: WalletCard, rows: list[dict[str, Any]], day: Date) -> dict[str, Any] | None:
    bonus = instance.signup_bonus
    if not bonus:
        return None
    end = min(day, bonus.deadline) + timedelta(days=1)
    spend = max(0, sum(r["amount"] for r in eligible(rows, instance.card, instance.opened_on, end)))
    target = money(bonus.min_spend * 100)
    remaining = max(0, target - spend)
    elapsed = max(1, (min(day, bonus.deadline) - instance.opened_on).days + 1)
    window = max(1, (bonus.deadline - instance.opened_on).days + 1)
    days_left = max(0, (bonus.deadline - day).days)
    projected = spend / elapsed * window
    status = (
        "done"
        if bonus.completed or not remaining
        else "missed"
        if day > bonus.deadline
        else "at_risk"
        if projected < target
        else "on_track"
    )
    return dict(
        card=instance.card,
        spend_cents=spend,
        target_cents=target,
        remaining_cents=remaining,
        days_left=days_left,
        required_daily_cents=money(remaining / max(1, days_left)),
        actual_daily_cents=money(spend / elapsed),
        projected_cents=money(projected),
        status=status,
        deadline=bonus.deadline.isoformat(),
        progress_pct=round(min(100, 100 * spend / target), 1),
    )


def card_rate(
    card: Card,
    instance: WalletCard,
    ctx: dict[str, Any],
    rows: list[dict[str, Any]],
    catalog: Catalog,
    valuation: str = "typical",
) -> dict[str, Any]:
    day = ctx["date"]
    amount = ctx.get("amount_cents", 0)
    warnings = (
        [f"Unverified {card.confidence}-confidence card terms; check issuer."]
        if card.verified_on is None
        else []
    )
    candidates = []
    for index, rule in enumerate(card.earn):
        if not matches(rule.match, ctx, instance):
            continue
        if rule.active and not rule.active.from_ <= day <= rule.active.to:
            continue
        if rule.active and rule.active.requires_activation:
            if not instance.settings.get(f"activated_{index}", False):
                warnings.append(
                    f"{rule.rate:g}x rule requires activation; excluded until confirmed in wallet settings."
                )
                continue
        available = amount or 1
        if rule.cap:
            start, _ = period(day, rule.cap.period, rule.cap.basis, instance.opened_on)
            group = [
                r.match for r in card.earn if r.cap and rule.cap.group and r.cap.group == rule.cap.group
            ] or [rule.match]
            spent = sum(
                r["amount"]
                for r in eligible(rows, card.id, start, day + timedelta(days=1))
                if any(matches(m, r, instance) for m in group)
            )
            available = max(0, money(rule.cap.amount * 100) - max(0, spent))
            if not available:
                warnings.append(f"{rule.rate:g}x cap exhausted; falling through to next matching rule.")
            elif amount and available < amount:
                warnings.append(
                    f"Only ${available / 100:.2f} remains under the {rule.rate:g}x cap; purchase is split."
                )
        candidates.append((rule.rate, available))
    # Allocate the purchase from the highest available rate to lower matching rules.
    remaining = amount or 1
    points_numerator = 0.0
    portions = []
    for rate, available in sorted(candidates, reverse=True):
        used = min(remaining, available)
        if used:
            points_numerator += used * rate
            portions.append(f"${used / 100:.2f} at {rate:g}x" if amount else f"{rate:g}x")
            remaining -= used
        if not remaining:
            break
    multiplier = points_numerator / (amount or 1)
    value = getattr(catalog.valuation(card.currency), valuation)
    fee = card.foreign_transaction_fee * 100 if ctx.get("is_foreign") else 0
    rate = multiplier * value - fee
    reasons = [
        f"{multiplier:g}x × {value:g} cents per point = {multiplier * value:g}%; " + ", ".join(portions)
    ]
    if fee:
        reasons.append(f"Subtract {fee:g}% foreign transaction fee = {rate:g}%.")
    return dict(
        effective_rate_pct=round(rate, 6),
        reward_rate_pct=round(multiplier * value, 6),
        multiplier=multiplier,
        est_value_cents=money(amount * rate / 100),
        reasons=reasons,
        warnings=warnings,
    )


def recommend(
    context: Context,
    catalog: Catalog,
    db: sqlite3.Connection,
    *,
    use_bonus: bool = True,
    use_offers: bool = True,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ctx, inference_confidence = resolve(context, catalog)
    rows = transactions(db, before=context.date.isoformat()) if rows is None else rows
    ranking = []
    for instance in catalog.wallet.cards:
        card = catalog.cards[instance.card]
        if instance.opened_on > context.date:
            continue
        result = card_rate(card, instance, ctx, rows, catalog)
        low = card_rate(card, instance, ctx, rows, catalog, "cash_out")["effective_rate_pct"]
        high = card_rate(card, instance, ctx, rows, catalog, "optimized")["effective_rate_pct"]
        offer_cents = 0
        if use_offers and context.amount_cents > 0:
            for offer in catalog.offers:
                if (
                    offer.wallet_card == card.id
                    and context.date <= offer.expires
                    and context.amount_cents >= money(offer.min_spend * 100)
                    and re.search(offer.merchant_pattern, ctx["normalized_description"], re.I)
                ):
                    value = (
                        money(context.amount_cents * offer.value / 100)
                        if offer.type == "percent"
                        else money(offer.value * 100)
                    )
                    offer_cents += value
                    result["reasons"].append(
                        f"Offer adds ${value / 100:.2f}; verify eligibility and remaining uses."
                    )
        offer_rate = offer_cents / context.amount_cents * 100 if context.amount_cents else 0
        result["effective_rate_pct"] = round(result["effective_rate_pct"] + offer_rate, 6)
        result["est_value_cents"] += offer_cents
        statement = db.execute(
            "SELECT statement_balance FROM statement WHERE wallet_card_id=? AND close_date<=? ORDER BY close_date DESC LIMIT 1",
            (card.id, context.date.isoformat()),
        ).fetchone()
        utilization = max(0, statement[0]) / (instance.credit_limit * 100) if statement else 0
        last = max(
            (
                r["transaction_date"]
                for r in rows
                if r["wallet_card_id"] == card.id
                and r["amount"] > 0
                and not r["is_fee"]
                and not r["is_payment"]
            ),
            default=instance.opened_on.isoformat(),
        )
        bonus = bonus_status(instance, rows, context.date) if use_bonus else None
        at_risk = bool(bonus and bonus["status"] == "at_risk")
        if at_risk and bonus is not None:
            result["reasons"].append(
                f"Sign-up bonus is behind pace: ${bonus['remaining_cents'] / 100:.2f} remains in {bonus['days_left']} days."
            )
        result.update(
            card_id=card.id,
            name=card.name,
            nickname=instance.nickname or card.name,
            range={"cash_out_pct": round(low + offer_rate, 6), "optimized_pct": round(high + offer_rate, 6)},
            confidence="low" if inference_confidence < 0.7 or card.confidence == "low" else card.confidence,
            inference_confidence=inference_confidence,
            offer_cents=offer_cents,
            utilization_pct=round(utilization * 100, 2),
            last_purchase=last,
            bonus_at_risk=at_risk,
        )
        ranking.append(result)
    ranking.sort(
        key=lambda r: (
            not r["bonus_at_risk"],
            -r["effective_rate_pct"],
            r["utilization_pct"],
            r["last_purchase"],
            r["card_id"],
        )
    )
    return {
        "ranked": ranking,
        "override": "signup_bonus" if ranking and ranking[0]["bonus_at_risk"] else None,
        "category": ctx["category"],
        "as_of": context.date.isoformat(),
        "confidence": "low" if inference_confidence < 0.7 else "medium",
        "warning": "Estimates from unverified card terms. Review ambiguous merchant categories.",
    }
