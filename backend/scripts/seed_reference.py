"""Reproducible unverified reference seeds; do not overwrite user edits casually."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def save(name, value):
    (ROOT / name).write_text(yaml.safe_dump(value, sort_keys=False))


def main():
    # id | issuer | name | fee | currency | base | category:rate,...
    rows = """chase-sapphire-preferred|Chase|Sapphire Preferred|95|chase-ur|1|dining:3,travel:2,streaming:3
chase-sapphire-reserve|Chase|Sapphire Reserve|795|chase-ur|1|dining:3,airfare:4,lodging:4
chase-freedom-unlimited|Chase|Freedom Unlimited|0|chase-ur|1.5|dining:3,drugstore:3
chase-freedom-flex|Chase|Freedom Flex|0|chase-ur|1|dining:3,drugstore:3
chase-amazon|Chase|Prime Visa|0|cash|1|dining:2,gas:2
amex-gold|Amex|Gold|325|amex-mr|1|dining:4,grocery:4,airfare:3
amex-platinum|Amex|Platinum|895|amex-mr|1|airfare:5
amex-blue-cash-preferred|Amex|Blue Cash Preferred|95|cash|1|grocery:6,streaming:6,gas:3,transit:3
amex-blue-cash-everyday|Amex|Blue Cash Everyday|0|cash|1|grocery:3,gas:3,online_shopping:3
amex-green|Amex|Green|150|amex-mr|1|travel:3,dining:3,transit:3
capitalone-venture|Capital One|Venture|95|capitalone-miles|2|
capitalone-venture-x|Capital One|Venture X|395|capitalone-miles|2|
capitalone-savor|Capital One|Savor|0|cash|1|dining:3,grocery:3,entertainment:3,streaming:3
capitalone-savorone|Capital One|SavorOne (legacy)|0|cash|1|dining:3,grocery:3,entertainment:3,streaming:3
capitalone-quicksilver|Capital One|Quicksilver|0|cash|1.5|
citi-double-cash|Citi|Double Cash|0|citi-ty|2|
citi-custom-cash|Citi|Custom Cash|0|citi-ty|1|chosen:5
citi-strata-premier|Citi|Strata Premier|95|citi-ty|1|dining:3,grocery:3,gas:3,airfare:3,lodging:3
citi-costco|Citi|Costco Anywhere|0|cash|1|gas:4,dining:3,travel:3,wholesale_club:2
bofa-customized-cash|BofA|Customized Cash|0|cash|1|chosen:3,grocery:2,wholesale_club:2
bofa-unlimited-cash|BofA|Unlimited Cash|0|cash|1.5|
bofa-premium-rewards|BofA|Premium Rewards|95|bofa-points|1.5|dining:2,travel:2
bofa-travel-rewards|BofA|Travel Rewards|0|bofa-points|1.5|
wells-active-cash|Wells Fargo|Active Cash|0|cash|2|
wells-autograph|Wells Fargo|Autograph|0|wells-points|1|dining:3,travel:3,gas:3,transit:3,streaming:3
bilt|Bilt|Bilt Mastercard (legacy)|0|bilt|1|rent:1,dining:3,travel:2
discover-it|Discover|Discover it|0|cash|1|
discover-it-student|Discover|Discover it Student|0|cash|1|
usbank-cash-plus|US Bank|Cash+|0|cash|1|chosen:5
usbank-altitude-go|US Bank|Altitude Go|0|cash|1|dining:4,grocery:2,gas:2,streaming:2
apple-card|Apple|Apple Card|0|cash|1|
united-explorer|Chase|United Explorer|150|united|1|dining:2,lodging:2
delta-gold|Amex|Delta Gold|150|delta|1|dining:2,grocery:2
aadvantage-platinum|Citi|AAdvantage Platinum Select|99|american|1|dining:2,gas:2
southwest-plus|Chase|Southwest Plus|99|southwest|1|
marriott-boundless|Chase|Marriott Boundless|95|marriott|2|grocery:3,dining:3,gas:3
hilton-honors|Amex|Hilton Honors|0|hilton|3|grocery:5,dining:5,gas:5
world-of-hyatt|Chase|World of Hyatt|95|hyatt|1|dining:2,airfare:2,transit:2"""
    for row in rows.splitlines():
        id_, issuer, name, fee, currency, base, categories = row.split("|")
        rules = [
            {"match": {"category": c.split(":")[0]}, "rate": float(c.split(":")[1])}
            for c in categories.split(",")
            if c
        ]
        rules.append({"match": {"any": True}, "rate": float(base)})
        credits = []
        lounges = []
        if id_ == "chase-sapphire-preferred":
            rules += [
                {"match": {"category": "grocery", "channel": "online"}, "rate": 3},
                {"match": {"category": "travel", "portal": "chase"}, "rate": 5},
            ]
            credits = [
                {
                    "id": "hotel",
                    "name": "Portal hotel credit",
                    "amount": 50,
                    "period": "annual",
                    "reset": "anniversary",
                    "match": {"merchant_pattern": "CHASE TRAVEL", "category": "lodging"},
                }
            ]
        if id_ == "amex-gold":
            credits = [
                {
                    "id": "uber",
                    "name": "Monthly Uber credit (eligibility unverified)",
                    "amount": 10,
                    "period": "month",
                    "reset": "calendar",
                    "match": {"merchant_pattern": "UBER"},
                }
            ]
        if id_ in {"amex-platinum", "capitalone-venture-x", "chase-sapphire-reserve"}:
            lounges = ["priority-pass"]
        if id_ == "amex-platinum":
            lounges += ["centurion"]
        if id_ == "chase-amazon":
            rules += [{"match": {"merchant_id": "amazon"}, "rate": 5}]
        if id_ in {"chase-freedom-flex", "discover-it", "discover-it-student"}:
            rules += [
                {
                    "match": {"category": "gas"},
                    "rate": 5,
                    "cap": {"amount": 1500, "period": "quarter", "basis": "calendar"},
                    "active": {"from": "2026-10-01", "to": "2026-12-31", "requires_activation": True},
                }
            ]
        if id_ == "bofa-customized-cash":
            for rule in rules[:-1]:
                rule["cap"] = {"amount": 2500, "period": "quarter", "basis": "calendar", "group": "combined"}
        if id_ in {"amex-blue-cash-preferred", "amex-blue-cash-everyday"}:
            for rule in rules:
                if (
                    rule["match"].get("category") in {"grocery", "gas", "online_shopping"}
                    and rule["rate"] > 3
                    or (id_ == "amex-blue-cash-everyday" and rule["rate"] == 3)
                ):
                    rule["cap"] = {"amount": 6000, "period": "annual", "basis": "calendar"}
        if id_ in {"citi-custom-cash", "usbank-cash-plus"}:
            rules[0]["cap"] = {
                "amount": 500 if id_ == "citi-custom-cash" else 2000,
                "period": "month" if id_ == "citi-custom-cash" else "quarter",
                "basis": "calendar",
            }
        for brand, merchant, rate in [
            ("united", "united", 2),
            ("delta", "delta", 2),
            ("aadvantage", "american-airlines", 2),
            ("southwest", "southwest", 2),
            ("marriott", "marriott", 6),
            ("hilton", "hilton", 7),
            ("world-of-hyatt", "hyatt", 4),
        ]:
            if id_.startswith(brand):
                rules += [{"match": {"merchant_id": merchant}, "rate": rate}]
        ftf = (
            0
            if int(fee) > 0
            or issuer in {"Capital One", "Discover"}
            or id_ in {"apple-card", "bilt", "citi-costco"}
            else 0.03
        )
        card = {
            "id": id_,
            "issuer": issuer,
            "name": name,
            "network": "amex"
            if issuer == "Amex"
            else "discover"
            if issuer == "Discover"
            else "mastercard"
            if issuer in {"Citi", "Apple", "Bilt"}
            else "visa",
            "currency": currency,
            "annual_fee": int(fee),
            "foreign_transaction_fee": ftf,
            "confidence": "low",
            "verified_on": None,
            "notes": "Seeded from memory. Check annual_fee, earn rates/caps/exclusions, activation dates, credits, bonus eligibility, foreign fees, network and lounge rules. Historical products may be unavailable. Credits are a conservative subset; selected categories require wallet settings.",
            "earn": rules,
            "credits": credits,
            "perks": {"lounge_programs": lounges, "no_foreign_fee": ftf == 0, "other": []},
            "signup_bonus": {"points": 60000, "min_spend": 4000, "window_days": 90}
            if id_ == "chase-sapphire-preferred"
            else None,
            "product_change_targets": ["chase-freedom-unlimited"] if id_.startswith("chase-sapphire") else [],
        }
        save(f"data/cards/{id_}.yaml", card)
    values = {
        "cash": (1, 1, 1),
        "chase-ur": (1, 1.5, 2),
        "amex-mr": (0.6, 1.5, 2),
        "capitalone-miles": (0.5, 1.5, 2),
        "citi-ty": (1, 1, 1.8),
        "bofa-points": (1, 1, 1),
        "wells-points": (1, 1, 1.5),
        "bilt": (0.55, 1.5, 2),
        "united": (1, 1.5, 2),
        "delta": (0.8, 1.2, 1.5),
        "american": (1, 1.5, 2),
        "southwest": (1, 1.3, 1.5),
        "marriott": (0.5, 0.7, 1),
        "hilton": (0.3, 0.5, 0.7),
        "hyatt": (1, 1.7, 2.5),
    }
    save(
        "data/valuations.yaml",
        {
            k: dict(
                zip(["cash_out", "typical", "optimized"], v),
                source_note="Unverified estimates, not guaranteed redemption or cash-out availability; verify eligibility.",
            )
            for k, v in values.items()
        },
    )
    save(
        "data/transfer_partners.yaml",
        {
            k: [{"partner": p, "ratio": 1, "typical_days": 1} for p in ps]
            for k, ps in {
                "chase-ur": ["united", "hyatt", "southwest"],
                "amex-mr": ["delta", "marriott"],
                "capitalone-miles": ["air-canada"],
                "citi-ty": ["avianca"],
                "bilt": ["hyatt", "united"],
            }.items()
        },
    )
    names = "dining grocery gas travel lodging airfare transit drugstore streaming online_shopping utilities home_improvement wholesale_club entertainment medical education insurance rent other".split()
    aliases = {
        "dining": ["Food & Drink", "Restaurants", "Restaurant"],
        "grocery": ["Groceries", "Supermarkets"],
        "gas": ["Gas", "Gasoline", "Automotive"],
        "travel": ["Travel"],
        "online_shopping": ["Shopping", "Merchandise"],
        "utilities": ["Bills & Utilities"],
        "lodging": ["Hotels"],
        "airfare": ["Airlines"],
    }
    mcc = {
        "dining": [[5812, 5814]],
        "grocery": [[5411, 5411]],
        "gas": [[5541, 5542]],
        "lodging": [[3501, 3999], [7011, 7011]],
        "airfare": [[3000, 3299], [4511, 4511]],
        "wholesale_club": [[5300, 5300]],
    }
    save(
        "data/mcc/categories.yaml",
        {
            n: {
                "mcc_ranges": mcc.get(n, []),
                "issuer_names": {
                    i: [n.replace("_", " ").title()] + aliases.get(n, [])
                    for i in [
                        "Chase",
                        "Amex",
                        "Capital One",
                        "Citi",
                        "BofA",
                        "Discover",
                        "Wells Fargo",
                        "Apple",
                        "generic",
                    ]
                },
            }
            for n in names
        },
    )
    save("data/merchants/patterns.yaml", [])
    save("data/merchants/learned.yaml", [])
    save(
        "data/app_contexts.yaml",
        {
            "ubereats": {
                "category": "dining",
                "channel": "online",
                "alternatives": [
                    {"app": "doordash", "perk": "Check any eligible monthly delivery credit before ordering."}
                ],
            },
            "doordash": {"category": "dining", "channel": "online"},
            "amazon": {"category": "online_shopping", "channel": "online"},
            "wallet": {"category": "other", "channel": "in_person"},
        },
    )
    save(
        "data/lounges/programs.yaml",
        {
            p: {
                "name": n,
                "guest_rules": "Verify guest fee, enrollment and visit limits with issuer.",
                "notes": "Unverified seed; admission and capacity restrictions apply.",
            }
            for p, n in [
                ("priority-pass", "Priority Pass"),
                ("centurion", "Centurion"),
                ("united-club", "United Club"),
                ("delta-skyclub", "Delta Sky Club"),
            ]
        },
    )
    airports = "ATL DFW DEN ORD LAX JFK LAS MCO MIA CLT SEA PHX EWR SFO IAH BOS FLL MSP LGA DTW PHL SLC BWI DCA SAN IAD TPA BNA AUS MDW HNL DAL PDX STL RDU HOU SJC MSY OAK SMF LHR NRT HND ICN CDG FRA AMS YYZ YVR MEX".split()
    centurion = set("ATL DFW DEN LAX JFK LAS MIA CLT SEA PHX SFO IAH PHL DCA LHR HKG".split())
    save(
        "data/lounges/airports.yaml",
        {
            a: [
                {
                    "name": "Centurion Lounge"
                    if a in centurion
                    else "Airport lounge — verify current program directory",
                    "terminal": "Verify terminal before travel",
                    "programs": ["centurion"] if a in centurion else ["priority-pass"],
                    "confidence": "low",
                    "notes": "Seeded from memory; lounge existence, exact name and access are unverified.",
                }
            ]
            for a in airports
        },
    )
    save(
        "config/wallet.example.yaml",
        {
            "cards": [
                {
                    "card": "chase-sapphire-preferred",
                    "nickname": "CSP",
                    "opened_on": "2026-09-01",
                    "credit_limit": 8000,
                    "statement_day": 12,
                    "signup_bonus": {"min_spend": 4000, "deadline": "2026-11-30", "completed": False},
                },
                {
                    "card": "bofa-customized-cash",
                    "nickname": "Custom Cash",
                    "opened_on": "2024-06-01",
                    "credit_limit": 3000,
                    "statement_day": 20,
                    "settings": {"chosen_category": "online_shopping"},
                },
                {
                    "card": "amex-gold",
                    "nickname": "Gold",
                    "opened_on": "2023-11-10",
                    "credit_limit": 10000,
                    "statement_day": 15,
                },
                {
                    "card": "amex-platinum",
                    "nickname": "Platinum",
                    "opened_on": "2020-11-01",
                    "credit_limit": 15000,
                    "statement_day": 25,
                },
            ],
            "inquiries": [{"date": "2026-03-14", "note": "Synthetic auto loan"}],
            "balances": [{"currency": "chase-ur", "amount": 12000, "as_of": "2026-10-14"}],
        },
    )
    save(
        "config/preferences.yaml",
        {
            "goal": "balanced",
            "valuations": {},
            "home_airports": ["SFO"],
            "utilization_targets": {"per_card": 30, "total": 10},
            "assistant": {"provider": "none", "base_url": "http://127.0.0.1:11434", "model": "llama3.2"},
            "server": {"bind": "0.0.0.0", "port": 8787},
            "perk_values": {},
        },
    )
    save("config/places.yaml", [])
    save("config/offers.yaml", [])


if __name__ == "__main__":
    main()
