from __future__ import annotations

import csv
import math
import sqlite3
from collections import defaultdict
from datetime import date
from functools import lru_cache
from typing import Any

from pydantic import Field

from whichcard.data_layer import Catalog
from whichcard.data_layer.models import Model, WalletCard
from whichcard.engine import Context, card_rate, money, recommend, shift_month, today
from whichcard.storage import transactions
from whichcard.trackers import account_timeline


def spend_profile(
    catalog: Catalog, db: sqlite3.Connection, day: date | None = None, months: int = 12
) -> dict[str, Any]:
    day = day or today()
    start = shift_month(day, -months)
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in transactions(db, before=day.isoformat()):
        if row["is_fee"] or row["is_payment"] or row["transaction_date"] <= start.isoformat():
            continue
        key = (row["transaction_date"][:7], row["category"], row["channel"])
        group = groups.setdefault(
            key, dict(month=key[0], category=key[1], channel=key[2], spend_cents=0, weighted_cents=0)
        )
        group["spend_cents"] += row["amount"]
        group["weighted_cents"] += money(row["amount"] * row["confidence"])
    totals: dict[str, int] = defaultdict(int)
    for g in groups.values():
        g["weighted_cents"] = max(0, g["weighted_cents"])
        totals[g["category"]] += g["spend_cents"]
    return dict(
        as_of=day.isoformat(),
        months=months,
        total_cents=sum(totals.values()),
        by_category=dict(totals),
        segments=sorted(groups.values(), key=lambda x: (x["month"], x["category"], x["channel"])),
        note="Spend is in billed-currency cents; verify foreign rows. Simulations weight categories by inference confidence and do not extrapolate missing months.",
    )


def portfolio_earning(
    cards: list[WalletCard], profile: dict[str, Any], catalog: Catalog, valuation: str
) -> int:
    earned = 0
    history: list[dict[str, Any]] = []
    for segment in profile["segments"]:
        if segment["weighted_cents"] <= 0:
            continue
        ctx = dict(
            segment,
            amount_cents=segment["weighted_cents"],
            date=date.fromisoformat(segment["month"] + "-15"),
            normalized_description="",
            is_foreign=False,
        )
        rates = [
            (
                card_rate(catalog.cards[c.card], c, ctx, history, catalog, valuation)["effective_rate_pct"],
                c.card,
            )
            for c in cards
        ]
        if not rates:
            continue
        rate, card = max(rates)
        earned += money(segment["weighted_cents"] * rate / 100)
        history.append(
            dict(
                wallet_card_id=card,
                transaction_date=ctx["date"].isoformat(),
                amount=segment["weighted_cents"],
                category=segment["category"],
                channel=segment["channel"],
                is_fee=False,
                is_payment=False,
            )
        )
    return earned


def credit_potential(card_id: str, profile: dict[str, Any], catalog: Catalog) -> int:
    card = catalog.cards[card_id]
    value = 0
    for credit in card.credits:
        category = credit.match.category
        if not category and credit.match.merchant_pattern and "UBER" in credit.match.merchant_pattern:
            category = "dining"
        spend = profile["by_category"].get(category or "other", 0) / 100
        monthly = spend / 12
        periods = {"month": 12, "quarter": 4, "annual": 1}[credit.period]
        probability = min(1, max(0, monthly / credit.amount)) if credit.amount else 0
        value += money(credit.amount * periods * probability * 100)
    return value


def simulate_card(
    card_id: str,
    catalog: Catalog,
    db: sqlite3.Connection,
    day: date | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    day = day or today()
    if card_id not in catalog.cards:
        raise ValueError("unknown card")
    if card_id in {c.card for c in catalog.wallet.cards}:
        return dict(
            card_id=card_id,
            net_annual_cents=0,
            earning_uplift_cents=0,
            already_owned=True,
            sensitivity={"cash_out_cents": 0, "optimized_cents": 0},
        )
    profile = profile or spend_profile(catalog, db, day)
    card = catalog.cards[card_id]
    best_category = (
        max(profile["by_category"], key=profile["by_category"].get) if profile["by_category"] else "other"
    )
    candidate = WalletCard(
        card=card_id,
        opened_on=day,
        credit_limit=1000,
        statement_day=1,
        settings={"chosen_category": best_category},
    )
    fee = money(card.annual_fee * 100)
    credits = credit_potential(card_id, profile, catalog)
    values = {}
    uplifts = {}
    for valuation in ["typical", "cash_out", "optimized"]:
        baseline = portfolio_earning(catalog.wallet.cards, profile, catalog, valuation)
        uplift = portfolio_earning(catalog.wallet.cards + [candidate], profile, catalog, valuation) - baseline
        uplifts[valuation] = uplift
        values[valuation] = uplift + credits - fee
    swaps: list[dict[str, Any]] = []
    base = portfolio_earning(catalog.wallet.cards, profile, catalog, "typical")
    for dropped in catalog.wallet.cards:
        alternatives = [c for c in catalog.wallet.cards if c.card != dropped.card] + [candidate]
        removed_fee = money(catalog.cards[dropped.card].annual_fee * 100)
        lost_credits = credit_potential(dropped.card, profile, catalog)
        swap_earn = portfolio_earning(alternatives, profile, catalog, "typical") - base
        swaps.append(
            dict(
                dropped_card=dropped.card,
                net_annual_cents=swap_earn + credits - fee + removed_fee - lost_credits,
                earning_uplift_cents=swap_earn,
                fee_saved_cents=removed_fee,
                lost_credit_cents=lost_credits,
            )
        )
    ages = [max(0, (day - c.opened_on).days) / 365.25 for c in catalog.wallet.cards]
    average = sum(ages) / len(ages) if ages else 0
    bonus = (
        money(card.signup_bonus.points * catalog.valuation(card.currency).typical) if card.signup_bonus else 0
    )
    return dict(
        card_id=card_id,
        name=card.name,
        net_annual_cents=values["typical"],
        earning_uplift_cents=uplifts["typical"],
        credit_value_cents=credits,
        annual_fee_cents=fee,
        signup_bonus_cents=bonus,
        arithmetic=f"${uplifts['typical'] / 100:.2f} incremental earning + ${credits / 100:.2f} estimated credits − ${fee / 100:.2f} annual fee",
        sensitivity=dict(cash_out_cents=values["cash_out"], optimized_cents=values["optimized"]),
        costs=dict(
            hard_inquiries=1,
            average_age_drop_years=round(average - (sum(ages) / (len(ages) + 1)), 2),
            resulting_5_24=account_timeline(catalog, day)["count_5_24"] + 1,
        ),
        swap=max(swaps, key=lambda s: s["net_annual_cents"]) if swaps else None,
        note="Heuristic, not credit-score advice. Bonus is one-time and excluded from annual net; selected categories modeled from highest spend. Merchant/portal-specific perks are conservative without matching evidence.",
    )


def gap_analysis(catalog: Catalog, db: sqlite3.Connection, day: date | None = None) -> dict[str, Any]:
    day = day or today()
    profile = spend_profile(catalog, db, day)
    results = [
        simulate_card(id_, catalog, db, day, profile)
        for id_ in catalog.cards
        if id_ not in {c.card for c in catalog.wallet.cards}
    ]
    results.sort(key=lambda r: r["net_annual_cents"], reverse=True)
    positive = any(r["net_annual_cents"] > 0 for r in results)
    return dict(
        profile=profile,
        candidates=results[:5],
        no_positive_candidate=not positive,
        message="Candidates with positive modeled annual value."
        if positive
        else "No candidate beats zero annual value on the available spending data.",
    )


class Award(Model):
    program: str
    points: int = Field(gt=0)
    fees_cents: int = Field(default=0, ge=0)


class Redemption(Model):
    cash_price_cents: int = Field(gt=0)
    awards: list[Award] = Field(min_length=1)
    category: str = "airfare"
    portal_price_cents: int | None = Field(default=None, gt=0)
    portal_card: str | None = None
    portal: str | None = None
    nights: int = Field(default=1, ge=1, le=365)


def redemption(request: Redemption, catalog: Catalog, db: sqlite3.Connection) -> dict[str, Any]:
    cash = request.cash_price_cents * request.nights
    cash_rank = recommend(
        Context(category=request.category, amount_cents=cash), catalog, db, use_bonus=False, use_offers=False
    )["ranked"]
    if not cash_rank:
        raise ValueError("add a wallet card before evaluating cash earning")
    best = cash_rank[0]
    cash_net = cash - best["est_value_cents"]
    choices = [
        dict(
            kind="cash",
            net_cost_cents=cash_net,
            card_id=best["card_id"],
            verdict=f"Pay cash with {best['nickname']}",
        )
    ]
    if request.portal_price_cents:
        ranking = recommend(
            Context(
                category="travel",
                amount_cents=request.portal_price_cents * request.nights,
                portal=request.portal,
            ),
            catalog,
            db,
            use_bonus=False,
            use_offers=False,
        )["ranked"]
        portal = next(
            (r for r in ranking if not request.portal_card or r["card_id"] == request.portal_card), None
        )
        if not portal:
            raise ValueError("portal card is not in wallet")
        choices.append(
            dict(
                kind="portal",
                net_cost_cents=request.portal_price_cents * request.nights - portal["est_value_cents"],
                card_id=portal["card_id"],
                verdict=f"Pay through portal with {portal['nickname']}",
            )
        )
    currencies = {catalog.cards[c.card].currency for c in catalog.wallet.cards} | {
        b.currency for b in catalog.wallet.balances
    }
    options = []
    for award in request.awards:
        points = award.points * request.nights
        fees = award.fees_cents * request.nights
        tax_earn = money(fees * best["effective_rate_pct"] / 100)
        forgone = max(0, best["est_value_cents"] - tax_earn)
        net_cpp = (cash - fees - forgone) / points
        paths = []
        for currency in currencies:
            for partner in catalog.transfers.get(currency, []):
                if partner.partner == award.program:
                    source_points = math.ceil(points / partner.ratio)
                    value = catalog.valuation(currency).typical
                    cost = money(source_points * value) + fees - tax_earn
                    paths.append(
                        dict(
                            currency=currency,
                            ratio=partner.ratio,
                            source_points=source_points,
                            typical_days=partner.typical_days,
                            adjusted_cpp=round(net_cpp * partner.ratio, 4),
                            net_cost_cents=cost,
                        )
                    )
                    choices.append(
                        dict(
                            kind="award",
                            net_cost_cents=cost,
                            verdict=f"Redeem {source_points:,} {currency} points via {award.program}",
                            program=award.program,
                        )
                    )
        valuation = catalog.valuations.get(award.program)
        if valuation:
            value = catalog.valuation(award.program).typical
            choices.append(
                dict(
                    kind="award",
                    net_cost_cents=money(points * value) + fees - tax_earn,
                    verdict=f"Redeem {points:,} points from {award.program}",
                    program=award.program,
                )
            )
        elif not paths:
            raise ValueError(f"no valuation or transfer path for {award.program}")
        options.append(
            dict(
                program=award.program,
                points=points,
                fees_cents=fees,
                cpp=round((cash - fees) / points, 4),
                net_cpp=round(net_cpp, 4),
                typical_cpp=catalog.valuation(award.program).typical if valuation else None,
                forgone_earning_cents=forgone,
                transfer_paths=paths,
            )
        )
    winner = min(choices, key=lambda x: x["net_cost_cents"])
    return dict(
        cash_price_cents=cash,
        cash_card=best["card_id"],
        cash_earning_cents=best["est_value_cents"],
        options=options,
        verdict=winner["verdict"],
        recommended=winner["kind"],
        choices=choices,
        note="Opportunity-cost comparison; verify award availability, transfer eligibility and sufficient points. No award search is performed.",
    )


def airport(iata: str, catalog: Catalog) -> dict[str, Any]:
    iata = iata.upper()
    result = []
    for lounge in catalog.lounges.get(iata, []):
        access = []
        for c in catalog.wallet.cards:
            for program in lounge.programs:
                if program in catalog.cards[c.card].perks.lounge_programs:
                    access.append(
                        dict(
                            card_id=c.card, program=program, guest_rules=catalog.programs[program].guest_rules
                        )
                    )
        result.append(
            dict(
                name=lounge.name,
                terminal=lounge.terminal,
                access=access,
                confidence=lounge.confidence,
                note=lounge.notes if access else "No access indicated by your wallet. " + lounge.notes,
            )
        )
    return dict(
        iata=iata,
        lounges=result,
        notification_text=(
            f"{iata}: {sum(bool(r['access']) for r in result)} possible lounge options. Verify access and hours."
        )[:119],
        note="Unverified lounge directory." if result else "No local lounge data for this airport.",
    )


@lru_cache(maxsize=4)
def coordinates(root: str) -> list[dict[str, str]]:
    from pathlib import Path

    with (Path(root) / "data/airports.csv").open() as f:
        return list(csv.DictReader(f))


def distance(lat: float, lon: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon) / 2) ** 2
    )
    return 6371000 * 2 * math.asin(min(1, math.sqrt(a)))


def now(context: Context, catalog: Catalog, db: sqlite3.Connection) -> dict[str, Any]:
    if context.lat is not None and context.lon is not None:
        lat, lon = context.lat, context.lon
        for place in catalog.places:
            if distance(lat, lon, place.lat, place.lon) <= place.radius_m:
                context = context.model_copy(
                    update={
                        "merchant_id": place.merchant_id,
                        "merchant_query": place.merchant_id.replace("-", " "),
                    }
                )
                break
        else:
            for a in coordinates(str(catalog.root)):
                if (
                    abs(float(a["lat"]) - lat) < 0.04
                    and distance(lat, lon, float(a["lat"]), float(a["lon"])) <= 3000
                ):
                    return airport(a["iata"], catalog)
    result = recommend(context, catalog, db)
    top = result["ranked"][0] if result["ranked"] else None
    result["notification_text"] = (
        f"Use {top['nickname']} ({top['effective_rate_pct']:g}% estimated)."
        if top
        else "Add a card to your wallet."
    )[:119]
    result["alternatives"] = []
    if context.app_context in catalog.apps:
        result["alternatives"] = [a.model_dump() for a in catalog.apps[str(context.app_context)].alternatives]
    return result
