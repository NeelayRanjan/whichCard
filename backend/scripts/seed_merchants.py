"""Ordered offline merchant hints; ambiguous general retailers stay in review."""

import re
from pathlib import Path

import yaml

GROUPS = {
    "dining": "Chipotle|Starbucks|McDonalds|Burger King|Wendys|Taco Bell|KFC|Popeyes|Chick Fil A|Panera|Subway|Jersey Mikes|Jimmy Johns|Firehouse Subs|Five Guys|Shake Shack|In N Out|Whataburger|Culvers|Sonic|Dairy Queen|Arbys|Jack In The Box|Del Taco|El Pollo Loco|Panda Express|PF Changs|Olive Garden|Red Lobster|Longhorn|Outback|Texas Roadhouse|Applebees|Chilis|Cheesecake Factory|Buffalo Wild Wings|Wingstop|Dominos|Pizza Hut|Papa Johns|Little Caesars|MOD Pizza|Blaze Pizza|California Pizza Kitchen|Sweetgreen|Cava|Noodles|Qdoba|Moes Southwest|Bojangles|Zaxbys|Raising Canes|Tim Hortons|Dunkin|Peets|Blue Bottle|Philz|Dutch Bros|Caribou Coffee|Coffee Bean|Jamba|Smoothie King|Tropical Smoothie|Cold Stone|Baskin Robbins|Ben Jerrys|Krispy Kreme|Einstein Bros|IHOP|Dennys|Waffle House|Cracker Barrel|Bob Evans|First Watch|Shake Smart|Pret A Manger|Au Bon Pain|Potbelly|Jason Deli|McAlisters|Schlotzskys|Rubios|Torchys|Salt Straw|Nothing Bundt|Insomnia Cookies|Crumbl|DoorDash|Uber Eats|Grubhub|Postmates|Seamless|Toast Takeout|Resy|OpenTable",
    "grocery": "Safeway|Kroger|Albertsons|Vons|Pavilions|Ralphs|Fred Meyer|QFC|King Soopers|Frys Food|Smiths Food|Harris Teeter|Food Lion|Giant Eagle|Giant Food|Stop Shop|ShopRite|Wegmans|Publix|HEB|Central Market|Whole Foods|Trader Joes|Sprouts|Aldi|Lidl|WinCo|Winn Dixie|Meijer|Hy Vee|Hannaford|Market Basket|Shaws|Acme Markets|Jewel Osco|Stater Bros|Save Mart|Lucky Supermarkets|Food4Less|Grocery Outlet|Smart Final|Natural Grocers|Fresh Market|Fresh Thyme|Bristol Farms|Gelsons|New Seasons|PCC Community|Mitsuwa|H Mart|99 Ranch|Patel Brothers|Apolonia|Instacart|FreshDirect|Amazon Fresh",
    "gas": "Shell|Chevron|Texaco|Exxon|Mobil|BP|Arco|76|Phillips 66|Conoco|Sunoco|Valero|Citgo|Marathon|Speedway|Circle K|QuikTrip|Kwik Trip|Wawa|Sheetz|Caseys|RaceTrac|Raceway|Murphy USA|Pilot|Flying J|Loves Travel|Sinclair|Gulf|Kum Go|Maverik",
    "airfare": "United Airlines|Delta Air|American Airlines|Southwest|Alaska Airlines|JetBlue|Spirit Airlines|Frontier Airlines|Hawaiian Airlines|Allegiant|Air Canada|WestJet|British Airways|Virgin Atlantic|Air France|KLM|Lufthansa|Swiss Air|Iberia|TAP Portugal|Turkish Airlines|Emirates|Qatar Airways|Etihad|Singapore Airlines|Cathay Pacific|ANA All Nippon|Japan Airlines|Korean Air|Asiana|Qantas|Air New Zealand|Aeromexico|LATAM|Avianca|Copa Airlines",
    "lodging": "Marriott|Hilton|Hyatt|Sheraton|Westin|Ritz Carlton|St Regis|W Hotels|Courtyard|Fairfield Inn|Residence Inn|SpringHill|TownePlace|Aloft|Moxy|Autograph Collection|Hampton Inn|DoubleTree|Embassy Suites|Homewood Suites|Home2 Suites|Tru By Hilton|Conrad|Waldorf Astoria|Hilton Garden|Holiday Inn|InterContinental|Crowne Plaza|Kimpton|Staybridge|Candlewood|Hotel Indigo|Wyndham|La Quinta|Days Inn|Super 8|Ramada|Best Western|Choice Hotels|Comfort Inn|Quality Inn|Sleep Inn|Econo Lodge|Motel 6|Red Roof|Four Seasons|Mandarin Oriental|Fairmont|Sofitel|Novotel|Ibis|Accor|Airbnb|VRBO|Booking.com|Expedia|Hotels.com|Chase Travel",
    "drugstore": "CVS|Walgreens|Rite Aid|Duane Reade|Bartell Drugs",
    "streaming": "Netflix|Hulu|Disney Plus|Disneyplus|HBO Max|Max.com|Spotify|Apple Music|Apple TV|YouTube Premium|YouTube TV|Peacock|Paramount Plus|Pandora|SiriusXM|Audible|Crunchyroll|Fubo|Sling TV",
    "online_shopping": "Etsy|eBay|Wayfair|Chewy|Zappos|Newegg|ASOS|Temu|Shein",
    "home_improvement": "Home Depot|Lowes|Ace Hardware|Menards|Harbor Freight|True Value",
    "transit": "Uber Trip|Lyft|BART|MTA|WMATA|Amtrak|Caltrain|Metrolink|Clipper|Ventra|MBTA|SEPTA|NJ Transit",
    "entertainment": "AMC Theatres|Regal Cinemas|Cinemark|Fandango|Ticketmaster|StubHub|Live Nation|Eventbrite|Six Flags|Disneyland|Universal Studios|SeaWorld|Topgolf",
    "utilities": "Comcast|Xfinity|ATT|Verizon|T Mobile|Spectrum|Cox Communications|PG E|Duke Energy|Con Edison",
    "other": "PayPal|Square|Toast|Stripe|Affirm|Klarna|Afterpay",
}


def main():
    patterns = []
    for regex, id_, name, category in [
        (r"COSTCO.*GAS", "costco-gas", "Costco Gas", "gas"),
        ("COSTCO", "costco", "Costco", "wholesale_club"),
        ("WALMART", "walmart", "Walmart", "other"),
        ("TARGET", "target", "Target", "other"),
        ("AMAZON|AMZN", "amazon", "Amazon", "online_shopping"),
    ]:
        patterns.append(
            dict(
                pattern=regex, merchant_id=id_, display_name=name, category=category, mcc=None, confidence=0.4
            )
        )
    for category, names in GROUPS.items():
        for name in names.split("|"):
            id_ = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            if name == "United Airlines":
                id_ = "united"
            if name == "Delta Air":
                id_ = "delta"
            if name == "Uber Eats":
                id_ = "ubereats"
            patterns.append(
                dict(
                    pattern=r"\b" + re.escape(name.upper()) + r"\b",
                    merchant_id=id_,
                    display_name=name,
                    category=category,
                    mcc={"dining": 5812, "grocery": 5411, "gas": 5541}.get(category),
                    confidence=0.95 if category != "other" else 0.4,
                )
            )
    path = Path(__file__).resolve().parents[2] / "data/merchants/patterns.yaml"
    path.write_text(yaml.safe_dump(patterns, sort_keys=False))
    print(len(patterns), "merchant patterns")


if __name__ == "__main__":
    main()
