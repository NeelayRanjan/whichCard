# whichcard — specification

Read `AGENTS.md` for the operating rules before building anything from this file.

## Mission

Build `whichcard`, a local-first credit card optimizer, end to end, with no human
in the loop. The run ends when every item in the Completion checklist is true and
`make check` passes on a fresh clone.

The user holds several rewards credit cards and wants one tool that answers, at the
moment of purchase, which card to use and why; tracks the long-horizon things the
register moment hides (sign-up bonus deadlines, expiring credits, annual fee
break-even, utilization, dormancy, the 5/24 clock); learns the user's real spending
from imported statements and simulates which card, if any, would be worth adding;
computes cash-versus-points math for flights and hotels; and lets the user ask
questions about their own spending through an optional local LLM that is blunt
about what the data does and does not support.

All data stays on the user's machine. No cloud services, no bank logins, no API
keys. Existing apps in this space (CardPointers, MaxRewards, Kudos) charge
subscriptions and hold user data; this tool does neither.

## Product scope

In scope for v1:

- Statement import from CSV and OFX/QFX files exported by the user, with
  per-issuer adapters and a generic column-mapping fallback.
- Merchant normalization and category/MCC inference with a confidence score, plus
  a user override loop that feeds a learned patterns file.
- A rules engine that ranks the user's cards for a purchase given any subset of:
  merchant, category, amount, channel (in person, online, recurring), app context
  ("ubereats"), date, and location. Every result shows the math.
- Context endpoints designed to be called from iOS Shortcuts automations (app
  opened, arrived at location) and a written guide for setting those automations up.
- Trackers: sign-up bonus progress, recurring credits and their expiry, annual fee
  break-even, statement utilization, dormancy, hard-inquiry and 5/24 timeline.
- Gap analysis: simulate every card in the data layer against the user's actual
  12-month spend and rank candidates by net annual value, with the score-side costs
  shown next to the dollar-side gains.
- Redemption calculator for flights and hotels: cents per point, transfer paths
  from the user's currencies, forgone earning, verdict.
- Airport lounge lookup: given an airport code or coordinates, which lounges the
  user's cards unlock.
- Insights: a deterministic findings generator that quantifies misrouted spend,
  unused credits, fee verdicts, and data-quality gaps.
- Assistant: a chat endpoint backed by any OpenAI-compatible local server (Ollama,
  llama.cpp, LM Studio), with a mock provider for tests. It answers from computed
  facts, not raw rows, and is instructed to be direct about limits.
- A mobile-first installable PWA covering all of the above, plus a CLI for the
  engine and trackers.

Out of scope for v1 (do not build, do not stub beyond an interface):

- Bank aggregation (Plaid, SimpleFIN, screen scraping). Leave an `ImportSource`
  interface so one can be added later.
- Automated award flight search or any airline, hotel, or map API.
- Native iOS or Android apps, App Store packaging, push notifications.
- Multi-user accounts, authentication, cloud sync.
- Automatic activation of issuer offers (Amex Offers and the like). Offers are
  entered by hand.
- Precise credit score prediction. Utilization and inquiry guidance are heuristics
  and must be labeled as such in the UI.

## Architecture and stack

One repo, two packages: a Python backend that owns all logic and data, and a thin
TypeScript PWA that only renders what the API returns. Nothing in the frontend
computes rewards; if a number appears in the UI, the API produced it.

Backend:

- Python 3.11+, FastAPI, uvicorn, pydantic v2, PyYAML.
- SQLite in `var/whichcard.db`, accessed through SQLAlchemy 2 Core or plain
  `sqlite3`. Schema versioning via numbered SQL files in `backend/migrations/`
  applied by a small runner; migrations are idempotent.
- Tooling: `uv` or `pip` with a pinned `requirements.txt`, `pytest`, `ruff`,
  `mypy`. One `Makefile` at the root.
- A `typer` CLI (`whichcard ...`) that exposes the engine, importers, trackers,
  and insights without the UI.
- Card definitions, merchant patterns, lounges, transfer partners, and valuations
  are YAML files under `data/`, validated by pydantic models at load time. A bad
  YAML file fails loudly at startup with the file and line.

Frontend:

- Vite, React, TypeScript, `vite-plugin-pwa`. Plain CSS, no component library.
  Dark mode via `prefers-color-scheme`.
- Served by the backend from `frontend/dist` so there is one process to run. Dev
  mode proxies `/api` to the backend.
- Geolocation and clipboard are the only browser APIs used. The service worker
  caches the shell and the last response of each read endpoint so the app opens
  offline.

Repo layout:

```
AGENTS.md  SPEC.md  PLAN.md  ASSUMPTIONS.md  RUNBOOK.md  REVIEW_CARDS.md  README.md  Makefile
backend/
  whichcard/
    data_layer/   # YAML loaders + pydantic models for cards, merchants, lounges, valuations
    importers/    # ImportSource interface, CSV/OFX adapters, issuer formats
    inference/    # merchant normalization, category/MCC inference, learned overrides
    engine/       # rules engine, caps, SUB override, explanations
    trackers/     # sub, credits, fee_breakeven, utilization, inquiries
    analysis/     # spend profile, gap simulation, redemption calculator
    insights/     # findings generator
    assistant/    # provider interface, mock + openai_compatible, tool definitions
    api/          # FastAPI routers
    cli.py
  migrations/
  tests/
  scripts/gen_fixtures.py
data/
  cards/*.yaml  merchants/patterns.yaml  merchants/learned.yaml  mcc/categories.yaml
  lounges/airports.yaml  lounges/programs.yaml  transfer_partners.yaml  valuations.yaml
  app_contexts.yaml  airports.csv
config/
  wallet.example.yaml  wallet.yaml  preferences.yaml  places.yaml  offers.yaml
frontend/
shortcuts/README.md
imports/   # user drops exports here (gitignored)
var/       # db and caches (gitignored)
```

Make targets: `setup` (install both packages), `check` (ruff, mypy, pytest,
frontend typecheck and build), `test`, `run` (migrate, build frontend if missing,
serve on 0.0.0.0:8787), `fixtures` (generate synthetic data and import it into a
scratch db), `smoke` (start the server against the fixture db, hit every endpoint,
exit nonzero on any failure).

## Data layer

The YAML data layer is the product. It must be readable and editable by a person,
validated on load, and versioned in git. Every file below has a pydantic model; add
fields if the engine needs them, but keep these.

Card definition, one file per card in `data/cards/`:

```yaml
id: chase-sapphire-preferred
issuer: Chase
name: Sapphire Preferred
network: visa
currency: chase-ur            # key into valuations.yaml and transfer_partners.yaml; or "cash"
annual_fee: 95
foreign_transaction_fee: 0.0  # fraction, 0.03 = 3%
confidence: medium            # low | medium | high
verified_on: null             # ISO date set by the user after checking issuer terms
notes: "Seeded from model memory; verify multipliers and credits against the issuer page."
earn:
  - match: {category: dining}
    rate: 3                    # points per dollar, or percent if currency is cash
  - match: {category: travel, portal: chase}
    rate: 5
  - match: {category: travel}
    rate: 2
  - match: {category: grocery, channel: online}
    rate: 3
  - match: {any: true}
    rate: 1
  - match: {category: gas}      # example of a rotating or capped rule
    rate: 5
    cap: {amount: 1500, period: quarter, basis: calendar}
    active: {from: 2026-10-01, to: 2026-12-31, requires_activation: true}
credits:
  - id: hotel-credit
    name: "$50 annual hotel credit via portal"
    amount: 50
    period: annual
    reset: anniversary          # anniversary | calendar
    match: {merchant_pattern: "CHASE TRAVEL", category: lodging}
perks:
  lounge_programs: []           # keys into data/lounges/programs.yaml
  no_foreign_fee: true
  other: ["primary rental car CDW", "trip delay insurance"]
signup_bonus:
  points: 60000
  min_spend: 4000
  window_days: 90
product_change_targets: [chase-freedom-unlimited, chase-freedom-flex]
```

Match keys (all optional, ANDed): `category`, `merchant_id`, `merchant_pattern`
(regex on normalized description), `channel` (in_person | online | recurring),
`portal`, `mcc` (list), `app_context`, `any`. Among the rules that match, the
highest rate whose cap is not exhausted wins, and an exhausted cap falls through to
the next matching rule; document the resolution order in `engine/README.md` and
test it.

`config/wallet.yaml` (user's instances; ship `wallet.example.yaml` with four cards
and copy it to `wallet.yaml` if absent):

```yaml
cards:
  - card: chase-sapphire-preferred
    nickname: CSP
    last4: null
    opened_on: 2026-10-05
    credit_limit: 8000
    statement_day: 12
    signup_bonus: {min_spend: 4000, deadline: 2027-01-03, completed: false}
    authorized_user: false
  - card: bofa-customized-cash
    opened_on: 2024-06-01
    credit_limit: 3000
    statement_day: 20
    settings: {chosen_category: online_shopping}   # for cards with a user-selected category
inquiries:                                            # hard pulls not tied to a card above
  - {date: 2026-03-14, note: "auto loan"}
balances:                                             # points balances, entered by hand
  - {currency: chase-ur, amount: 12000, as_of: 2026-10-14}
```

`config/preferences.yaml`: point valuations override (cents per point, per
currency, three values: `cash_out`, `typical`, `optimized`), `goal` (cash | travel
| balanced), `home_airports`, `utilization_targets` (per-card 30, total 10),
`assistant` (`provider: none | openai_compatible`, `base_url`, `model`), `server`
(`bind`, `port`).

`data/valuations.yaml`: default cents-per-point for each currency with the same
three values and a `source_note`. `data/transfer_partners.yaml`: for each currency,
list of `{partner, ratio, typical_days}`. `data/mcc/categories.yaml`: the canonical
category list (dining, grocery, gas, travel, lodging, airfare, transit, drugstore,
streaming, online_shopping, utilities, home_improvement, wholesale_club,
entertainment, medical, education, insurance, rent, other) each with its MCC ranges
and the issuer-specific category names that map onto it (Chase, Amex, Capital One,
Citi, BofA, Discover, Apple export categories). `data/merchants/patterns.yaml`:
ordered regex patterns to `{merchant_id, display_name, category, mcc, confidence}`;
ship at least 250 patterns covering common national chains, delivery apps,
airlines, hotel brands, payment processors (`SQ *`, `TST*`, `PAYPAL *`, `PY *`),
and known ambiguous cases (Costco gas, Walmart Supercenter, Target, Amazon).
`data/merchants/learned.yaml`: written by the app from user overrides, same shape,
loaded after `patterns.yaml`. `data/app_contexts.yaml`: app name to `{category,
channel, alternatives}` where alternatives lists competing apps and the perks that
favor them (for example `ubereats` to alternative `doordash` when a wallet card
carries a DoorDash credit). `data/lounges/programs.yaml`: program key to name,
guest rules, notes. `data/lounges/airports.yaml`: IATA to list of `{name, terminal,
programs: [...]}`. `data/airports.csv`: if network is available at build time,
vendor the public-domain OurAirports `airports.csv` filtered to large and medium
airports; otherwise embed the 100 busiest US airports from memory and flag the file
in `REVIEW_CARDS.md`. `config/offers.yaml`: hand-entered card-linked offers
`{wallet_card, merchant_pattern, type: percent | fixed, value, min_spend,
expires}`. `config/places.yaml`: pinned places `{name, lat, lon, merchant_id,
radius_m}` the user adds from the UI.

## Database model

SQLite holds only user-generated state. Card definitions and reference data stay in
YAML and are loaded at startup; the database references them by string id.

| Table | Fields | Notes |
| --- | --- | --- |
| `import_batch` | id, source_file, adapter, imported_at, row_count, wallet_card_id | One row per file import; re-importing the same file is a no-op |
| `transaction` | id, wallet_card_id, import_batch_id, transaction_date, posted_date, amount, currency, raw_description, normalized_description, merchant_id, category, mcc, channel, confidence, is_refund, is_fee, is_payment, is_foreign, dedupe_hash | `dedupe_hash` = sha256 of card + date + amount + raw description; unique |
| `transaction_override` | transaction_id, field, value, set_at | User corrections; applied on read and mirrored into `learned.yaml` when the correction generalizes to a pattern |
| `merchant_alias` | normalized_description, merchant_id, category, mcc, source (pattern, learned, user), confidence | Cache of inference results so re-imports are stable |
| `statement` | wallet_card_id, close_date, statement_balance, source (computed, manual) | Computed from transactions between statement days unless the user enters the real figure |
| `credit_usage` | wallet_card_id, credit_id, period_start, period_end, amount_used, source (auto, manual), transaction_id | Auto rows come from credit match rules; manual rows from the UI |
| `recommendation_log` | id, requested_at, context_json, result_json, chosen_card_id, feedback | Optional feedback loop; feeds nothing in v1 beyond display |
| `finding` | id, kind, severity, dollar_impact, title, detail, evidence_json, created_at, dismissed_at | Regenerated on demand; dismissals persist by a stable `fingerprint` field |
| `assistant_message` | id, session_id, role, content, tool_calls_json, created_at | Chat history, local only |
| `schema_version` | version, applied_at | Migration runner |

Amounts are integers in cents. Dates are ISO strings. Every table has
`created_at`. Add indexes on `transaction(wallet_card_id, transaction_date)` and
`transaction(dedupe_hash)`.

## Feature specifications

Each feature lists what it does and the acceptance criteria that its tests must
prove.

### Import

`ImportSource` is an interface with one method:
`read(path) -> Iterable[RawTransaction]`. Implement adapters for Chase, American
Express, Capital One, Citi, Bank of America, Discover, Wells Fargo, and Apple Card
CSV exports, plus OFX/QFX, plus a generic CSV adapter that detects the date,
amount, and description columns by header name and sample values and asks nothing.
Adapter detection is automatic from headers; the CLI and UI allow forcing one. Sign
conventions differ by issuer (some export charges as negative); normalize so
purchases are positive and refunds negative. Payments and interest are flagged, not
deleted.

Acceptance: each adapter round-trips its fixture file with zero unmatched rows;
importing the same file twice adds zero rows; a CSV with unknown headers still
imports via the generic adapter or fails with a message naming the missing column.

### Merchant inference

Pipeline per transaction: normalize the description (uppercase, strip store
numbers, city and state suffixes, processor prefixes, trailing reference codes);
check `merchant_alias`; match `learned.yaml` then `patterns.yaml` in order; if the
issuer export included a category column, map it through `categories.yaml` as a
second signal; combine into `(merchant_id, category, mcc, confidence)` where
confidence is 0.95 for an exact pattern hit, 0.7 for an issuer-category-only hit,
0.4 for a keyword guess, 0 for unknown. Channel is inferred from patterns (`AMZN`,
`.COM`, `*` processor prefixes imply online; recurring is detected when the same
normalized description and amount recur monthly).

User overrides: `POST /api/transactions/{id}/override` sets merchant, category, or
channel. When an override applies to a normalized description seen more than once,
write a pattern to `learned.yaml` so future imports agree.

Acceptance: at least 90% of fixture transactions get confidence >= 0.7; the
ambiguous fixtures (Costco gas, Walmart, Target, Amazon) are reported with
confidence <= 0.5 and appear in the review queue; an override on a repeated
merchant changes future inference without re-importing.

### Rules engine and recommendation

`recommend(context) -> Recommendation` where context carries any of:
`merchant_id`, `merchant_query` (free text, resolved through the same inference),
`category`, `amount_cents`, `channel`, `app_context`, `date`, `lat/lon`,
`is_foreign`, `portal`. Output: a ranked list of the wallet's cards, each with
`effective_rate_pct` (multiplier times typical cents-per-point, or cash percent),
`est_value_cents` for the given amount, `reasons[]` (plain sentences with the
arithmetic, like "3x dining x 1.6c = 4.8%"), `warnings[]`, `confidence`, and a
top-level `override` field when a non-rate rule changed the ranking.

Ranking rules, in order: an active offer in `offers.yaml` matching the merchant
adds its value; an open sign-up bonus with remaining spend whose projected pace
(spend to date / days elapsed x window) falls short of the target moves that card
to the top with `override: signup_bonus`; a rate whose cap is exhausted for the
current period falls back to the card's base rate and says so; foreign purchases
subtract the card's foreign fee; `requires_activation` rules add a warning rather
than assuming activation; ties break toward the card with the lower utilization
this cycle, then toward the card that has been dormant longest. Unknown category
yields the best flat-rate card with `confidence: low`.

Valuation: use `preferences.yaml` overrides, else `valuations.yaml`, and always
compute at the `typical` value with `cash_out` and `optimized` shown as a range.

Acceptance: the golden table in `tests/golden_recommendations.yaml` (at least 40
cases spanning every rule above) passes exactly; effective rate never exceeds the
card's highest multiplier times the optimized valuation; a cap hit mid-quarter in
the fixtures flips the recommendation on the right date.

### Context endpoints

Designed to be called from iOS Shortcuts with a single GET and shown as a
notification. `GET /api/now?app=ubereats`, `GET /api/now?category=dining`,
`GET /api/now?merchant=costco`, `GET /api/now?lat=..&lon=..`. Response includes a
`notification_text` field under 120 characters: "Use CSP (3x dining, 4.8%). Alt:
DoorDash on Amex has $10 credit left this month." Location resolves against
`places.yaml` within each place's radius, then against `airports.csv` within 3 km
to return lounge access instead. `POST /api/places` pins the current location to a
merchant from the UI.

Acceptance: every `/api/now` variant returns in under 100 ms against the fixture
db; `notification_text` never exceeds 120 characters; an airport coordinate returns
the lounge payload.

### Trackers

Sign-up bonus: per wallet card with an open bonus, compute spend to date since
`opened_on` (purchases minus refunds, excluding fees and payments), remaining, days
left, required daily pace versus actual pace, status (on_track, at_risk, missed,
done). Credits: for each credit on each wallet card, compute the current period
from `reset` and `opened_on` or the calendar, auto-match transactions by the
credit's match rule, expose used, remaining, and days until reset; the UI allows
marking a credit used by hand. Fee break-even: for each card with an annual fee,
over the trailing 12 months compute credits actually used plus earning uplift (what
this card earned on its transactions minus what the next-best wallet card would
have earned on the same transactions) plus the user-assigned value of perks from
`preferences.yaml`, minus the fee; verdict keep, downgrade (naming
`product_change_targets`), or cancel, with the full arithmetic. Utilization: per
card and total, from the latest `statement` rows; alerts when any card exceeds the
per-card target or the total exceeds the total target; recommend which card to pay
down before its statement date. Dormancy: any wallet card with no purchase in 180
days gets a finding suggesting a small recurring charge. Inquiries and 5/24: from
`opened_on` dates plus `inquiries`, count accounts opened in the trailing 24
months, list the date each one ages out, show the next date the user would be under
5/24, and list inquiries by bureau-agnostic date with a 12-month and 24-month
count.

Acceptance: the fixture wallet's bonus crosses from at_risk to on_track on a known
date; the Uber-style monthly credit in the fixtures shows as expiring unused in the
month with no matching charge; the fee break-even for the fixture premium card
produces the expected verdict; utilization alerts fire on the fixture statement
that exceeds 30%.

### Gap analysis

Build a 12-month spend profile by category, weighted by inference confidence, with
online versus in-person split. For every card in `data/cards/` not in the wallet,
simulate annual value: for each category, spend x (best rate among wallet plus
candidate) minus spend x (best rate among wallet alone), valued at `typical`; add
credits the candidate offers in categories where the user already spends, scaled by
a usage probability (1.0 if monthly spend in that category exceeds the credit, else
spend / credit); subtract the annual fee; show the sign-up bonus value separately
as one-time. Report the score-side costs alongside: one hard inquiry, the drop in
average account age given the current wallet, and the resulting 5/24 count. Also
run "swap" variants: candidate added and the weakest wallet card dropped. Output
the top five with full math and a sensitivity line showing the value at `cash_out`
and `optimized`.

Acceptance: a candidate identical to a wallet card simulates to exactly zero
uplift; raising a category's spend in the fixtures changes the ranking in the
expected direction; the output explicitly says when no candidate beats zero.

### Redemption calculator

Inputs: cash price, award price in points for one or more programs, taxes and fees
on the award, optional portal cash price and the card that would pay it. Compute
cents per point for each option, compare to the program's `typical` valuation, list
transfer paths from the user's currencies with ratios and typical transfer times,
subtract forgone earning (points you would have earned paying cash with the best
wallet card, which an award does not earn except on taxes), and give a verdict: pay
cash with card X, pay through portal with card Y, or redeem N points from program
Z. Hotels use the same calculator with nightly inputs. Expose as
`POST /api/redeem/evaluate` and `whichcard redeem`.

Acceptance: a 2.0c redemption on a currency valued at 1.5c is recommended; the same
redemption at 0.9c is rejected in favor of cash with the earning gap quantified; a
transfer path that needs a 1:0.5 ratio reports the adjusted cents per point.

### Lounges

`GET /api/airport/{iata}` and the coordinate form of `/api/now` return the lounges
at that airport the user's cards unlock, via which program, with guest rules, and a
note when a lounge exists but the user has no access. Seed `airports.yaml` for at
least the 40 busiest US airports plus LHR, NRT, HND, ICN, CDG, FRA, AMS, YYZ, YVR,
MEX, flagged `confidence: low`.

### Insights

`generate_findings()` produces `finding` rows, each with a stable fingerprint, a
severity, and a dollar impact where one exists. Kinds: misrouted spend
(transactions where a different wallet card would have earned more, aggregated per
merchant with annualized cost), unused or expiring credits, fee verdicts, sign-up
bonus risk, utilization alerts, dormancy, rotating category not yet activated,
annual fee due within 45 days, points balances idle above a threshold while
cash-equivalent redemptions exist, and data-quality gaps (share of spend at
confidence below 0.7, top unmatched descriptions). Findings are sorted by dollar
impact and shown in the UI with a dismiss action.

Acceptance: the fixtures produce at least one finding of every kind; dollar impacts
reconcile with the underlying transactions in a test.

### Assistant

`AssistantProvider` interface with two implementations: `MockProvider`
(deterministic canned responses keyed by prompt content, used in tests) and
`OpenAICompatibleProvider` (POST to `{base_url}/v1/chat/completions`, no auth
header unless configured, works with Ollama, llama.cpp server, and LM Studio). The
assistant never receives raw transaction rows by default. It gets tools:
`spend_summary(months, by)`, `findings(limit)`, `card_rules(card_id)`,
`recommend(context)`, `simulate_card(card_id)`, `transactions(filter, limit=25)`,
`trackers()`. If the model advertises tool support, use it; otherwise fall back to
a retrieval mode that injects a compact spend summary and the top findings into the
system prompt and answers from that. Keep every tool result under 1,500 tokens so a
7B model with a 4k context works.

The system prompt must instruct the model to: answer with numbers from tool results
and say which finding or summary each number came from; say "the data does not show
that" when a tool returns nothing relevant; name the inference confidence when it
is below 0.7; point out limits of the app itself (unmatched merchants, missing
statements, unverified card data) when they affect the answer; never praise the
user's choices; and keep answers under 200 words unless asked for detail. Ship six
suggested questions in the UI, including "Which card am I misusing most?" and "Is
my annual fee card earning its keep?"

Acceptance: with `MockProvider`, a question about dining spend triggers
`spend_summary` and the reply cites the number; with `provider: none`, the Ask
screen shows the findings feed and the suggested questions explain that an LLM
endpoint is not configured; an integration test against a live local endpoint
exists and is skipped when none is reachable.

### PWA

Screens: Now (search box for merchant or category, chips for app contexts, a "use
my location" button, amount field, result card with reasons and the range), Wallet
(cards with bonus progress bars, credits with remaining and days-to-reset,
utilization, fee verdict), Transactions (import by file upload, list with filters,
review queue of low-confidence rows with inline override), Plan (utilization
targets, 5/24 timeline, inquiry counts, gap analysis results), Travel (redemption
calculator, airport lookup), Ask (chat with suggested questions, or the findings
feed when no provider is set), Settings (valuations, goal, assistant endpoint,
pinned places, offers). Mobile first at 390 px wide, installable, works offline for
the last cached data. No analytics, no external requests.

Acceptance: `npm run typecheck` and `npm run build` pass; a vitest suite covers the
formatting helpers and the API client; the smoke target confirms every screen's
data endpoints respond.

### CLI

`whichcard import <file> [--card CSP] [--adapter chase]`,
`whichcard recommend <query> [--amount 42.10] [--app ubereats] [--online]`,
`whichcard trackers`, `whichcard insights`, `whichcard gap`,
`whichcard redeem --cash 420 --points 28000 --program united --fees 11.20`,
`whichcard airport SFO`, `whichcard review` (interactive-free: prints the
low-confidence queue), `whichcard ask "..."`. Output is human-readable by default
and JSON with `--json`. `whichcard cards list` and `whichcard cards review` (which
writes `REVIEW_CARDS.md`) complete the set.

### Shortcuts package

`shortcuts/README.md` gives numbered steps with the exact field values for four
automations in the iOS Shortcuts app: when Uber Eats opens, when Wallet opens, when
arriving at a pinned place, and a daily 8 am summary. Each is Automation, trigger,
Get Contents of URL (`http://<host>:8787/api/now?...`), Get Dictionary Value
`notification_text`, Show Notification. Include a short note on reaching the server
from the phone over LAN or Tailscale and on turning off "Ask Before Running".
Signed `.shortcut` files cannot be generated here, so the README is the
deliverable.

## Milestones

Do them in this order. A milestone is done when its tests pass, `make check` is
green, the commit is made, and its boxes in `PLAN.md` are ticked. The order puts
the engine and CLI before the UI so an interrupted run still leaves a usable tool.

| Milestone | Build | Done when |
| --- | --- | --- |
| M0 Scaffold | Repo layout, `Makefile`, pinned deps, `PLAN.md` with every task from this spec, `ASSUMPTIONS.md`, `.gitignore`, empty FastAPI app with `/api/health`, empty Vite app | `make check` passes on an empty app; first commit |
| M1 Data layer | Pydantic models and loaders for every YAML file; `data/mcc/categories.yaml`; `valuations.yaml`; `transfer_partners.yaml`; `app_contexts.yaml`; `lounges/`; `airports.csv`; seeded card files per the Seed data section; `REVIEW_CARDS.md` | Loader tests pass; a deliberately broken YAML fixture fails with file and line; `whichcard cards list` prints every seeded card with its confidence |
| M2 Storage and import | Migrations and runner; `ImportSource`; all adapters; dedupe; `scripts/gen_fixtures.py`; fixture CSVs in every issuer format; `whichcard import` | Round-trip tests per adapter; `make fixtures` builds a scratch db with 12 months of data for the example wallet |
| M3 Inference | Normalizer; patterns (at least 250); issuer category mapping; confidence; channel and recurring detection; overrides and `learned.yaml`; review queue; `whichcard review` | Inference acceptance criteria pass on the fixtures |
| M4 Engine | Rules engine, caps, offers, sign-up bonus override, valuations, explanations; `recommend` API and CLI; golden table | Golden tests pass; `whichcard recommend costco --amount 180` prints a ranked list with reasons |
| M5 Trackers | Sign-up bonus, credits, fee break-even, utilization, dormancy, inquiries and 5/24; `/api/trackers`; `whichcard trackers` | Tracker acceptance criteria pass |
| M6 Analysis | Spend profile, gap simulation with swap variants, redemption calculator, airport and lounge lookup; `/api/now` with location; `whichcard gap`, `redeem`, `airport` | Analysis acceptance criteria pass; `/api/now` latency test passes |
| M7 Insights and assistant | Findings generator with fingerprints and dismissals; provider interface, mock and OpenAI-compatible providers, tools, retrieval fallback; `/api/ask`; `whichcard ask` | Every finding kind appears on the fixtures; mock-provider tests pass; live test skips cleanly |
| M8 PWA | All seven screens, service worker, install manifest, dark mode, API client; backend serves `frontend/dist` | Typecheck, build, vitest green; `make smoke` passes |
| M9 Ship | `shortcuts/README.md`; `RUNBOOK.md`; final pass of `REVIEW_CARDS.md` and `ASSUMPTIONS.md`; fresh-clone test in a temp directory (`git clone`, `make setup`, `make check`, `make fixtures`, `make smoke`) | Completion checklist fully true; final commit tagged `v0.1.0` |

## Testing requirements

The synthetic fixtures are the only ground truth available to an unattended run, so
build them carefully and early (M2), then test everything against them.

`scripts/gen_fixtures.py` is deterministic (fixed seed) and produces 12 months of
transactions for the four-card example wallet, written both as a combined JSON file
and as one CSV per card in that card's issuer format, plus one OFX file. The data
must include, with dates recorded in `tests/fixture_manifest.yaml` so tests can
assert on them:

- A category cap that is reached mid-quarter on a known date.
- A rotating category that is active in one quarter and not the next.
- A sign-up bonus window where spend starts behind pace and catches up on a known
  date.
- A monthly credit that is used in nine months and missed in three.
- An annual-fee card whose break-even is clearly negative, and one whose
  break-even is clearly positive.
- Refunds, a partial refund, a disputed reversal, a foreign purchase with a
  currency column, interest and fee lines, a payment line, and a duplicate row
  across two exports.
- Recurring subscriptions, online and in-person variants of the same merchant, and
  the ambiguous merchants (Costco gas, Walmart, Target, Amazon, a `SQ *` coffee
  shop).
- One statement whose balance exceeds 30% of the card's limit.
- A card with no purchases in the last seven months.

Test layers:

- Unit tests for every module, including the YAML loaders with a negative case per
  schema.
- `tests/golden_recommendations.yaml`: at least 40 `(context, expected top card,
  expected effective rate, expected override)` rows, covering every ranking rule,
  cap state, foreign fee, offer, app context, unknown category, and a tie.
- Property tests (Hypothesis): effective rate is bounded by max multiplier times
  optimized valuation; adding a transaction never lowers a sign-up bonus's spend to
  date; simulating a wallet card as a candidate yields zero uplift; dedupe is
  idempotent under re-import.
- API tests via FastAPI's `TestClient` for every endpoint, including error shapes.
- Frontend: vitest for formatting helpers and the API client against recorded
  responses; typecheck and production build.
- `make smoke`: boots the server on a scratch db, imports the fixtures, calls every
  endpoint the PWA uses, checks status codes and a few known values, and exits
  nonzero on any failure.
- `make check` runs ruff, mypy, pytest with coverage (fail under 80% for
  `engine/`, `trackers/`, `analysis/`, `inference/`), then the frontend checks.

Before the final commit, repeat the fresh-clone test from M9 and fix anything it
surfaces.

## Seed data requirements

Seed at least 36 US consumer cards from memory, covering Chase (Sapphire Preferred,
Sapphire Reserve, Freedom Unlimited, Freedom Flex, Amazon), American Express (Gold,
Platinum, Blue Cash Preferred, Blue Cash Everyday, Green), Capital One (Venture,
Venture X, Savor, SavorOne, Quicksilver), Citi (Double Cash, Custom Cash, Strata
Premier, Costco Anywhere), Bank of America (Customized Cash, Unlimited Cash,
Premium Rewards, Travel Rewards), Wells Fargo (Active Cash, Autograph), Bilt,
Discover (it, it Student), U.S. Bank (Cash+, Altitude Go), Apple Card, and the
major airline and hotel co-brands from United, Delta, American, Southwest,
Marriott, Hilton, and Hyatt. Student and no-fee versions matter more than
ultra-premium ones for this user.

Every seeded card gets `confidence: low` unless you are highly certain of its
current earn structure, in which case `medium`. Never write `high` or a
`verified_on` date yourself. Where you are unsure of a cap, credit amount, or
activation rule, encode your best guess and add a `notes` line saying exactly which
field to check. The same applies to `valuations.yaml`, `transfer_partners.yaml`,
and the lounge files.

`REVIEW_CARDS.md` is generated by `whichcard cards review` and committed: one table
with card, confidence, the fields flagged in `notes`, and a blank "verified" column
for the user to fill, sorted with the example-wallet cards first. The RUNBOOK tells
the user to spend ten minutes on this file before trusting any recommendation.

## Completion checklist

The run ends only when every line is true. Check them yourself; do not report done
on the strength of the milestone commits alone.

- [x] `SPEC.md`, `AGENTS.md`, `PLAN.md` (all boxes ticked), `ASSUMPTIONS.md`,
      `RUNBOOK.md`, `REVIEW_CARDS.md`, `shortcuts/README.md` exist and are current.
- [x] `make check` passes on a fresh clone in a temp directory with no cached
      dependencies beyond the package registries.
- [x] `make fixtures` then `make smoke` pass on that fresh clone.
- [x] `whichcard recommend costco --amount 180 --json` returns a ranked list with
      reasons, a range, and a confidence, against the fixture db.
- [x] `whichcard trackers`, `whichcard insights`, `whichcard gap`,
      `whichcard redeem`, and `whichcard airport SFO` each produce output against
      the fixture db without error.
- [x] `GET /api/now?app=ubereats` returns a `notification_text` under 120
      characters.
- [x] The PWA builds, is served by the backend, installs on a phone-width
      viewport, and every screen renders data from the fixture db.
- [x] With `assistant.provider: none`, the Ask screen degrades to the findings
      feed; with the mock provider, the assistant test suite passes; the
      live-endpoint test is skipped, not failed, when no server is reachable.
- [x] No file under `data/cards/` carries `confidence: high` or a non-null
      `verified_on`.
- [x] `git status` is clean, the final commit is tagged `v0.1.0`, and `var/`,
      `imports/`, and `config/wallet.yaml` are gitignored (with
      `wallet.example.yaml` committed).
- [x] `RUNBOOK.md` covers: install, first run, filling `wallet.yaml`, exporting
      CSVs from each supported issuer, importing, reviewing low-confidence rows,
      setting up Shortcuts, reaching the server from a phone, enabling a local LLM,
      and the ten-minute `REVIEW_CARDS.md` pass.
