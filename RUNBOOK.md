# Run whichcard

whichcard runs on your computer. Python owns all rewards math; the browser displays
results. The bundled card terms, point values, transfer paths and lounge data are
**unverified estimates**. Start with the ten-minute review below.

## Install and first run

Prerequisites: Python 3.11 or newer, Node.js 20.19+ (Node 22+ recommended), npm, Git
and Make. Package installation needs internet access; normal use does not.

```sh
git clone https://github.com/NeelayRanjan/creditoptimization.git
cd creditoptimization
make setup
make check
make run
```

Open `http://localhost:8787`. If `python3` is an older system interpreter, use
`make setup PYTHON=python3.12` (or the absolute path to a Python 3.11+ executable).
Activate the CLI with `source .venv/bin/activate`, or use `.venv/bin/whichcard`.
`make run` applies migrations at startup and builds the frontend if it is missing.
After changing frontend source, run `cd frontend && npm run build` and restart.
For development, use `npm run dev` in `frontend/` alongside the backend; Vite
proxies `/api` to port 8787. Production is one uvicorn process.

`config/preferences.yaml` sets the server bind and port; saved UI preferences
create `config/preferences.local.yaml`, which takes precedence. The default bind
is `0.0.0.0:8787`. This app has no authentication: use a trusted private network,
never expose it with public port forwarding. Optional assistant calls are restricted
to HTTP loopback addresses on the server machine. No telemetry or cloud API is used.

## Try the synthetic example

```sh
make fixtures
WHICHCARD_DB=var/fixtures.db WHICHCARD_TODAY=2026-10-14 make run
```

The deterministic fixture set has 540 transactions spanning November 2025 through
October 2026. The fixed clock makes bonus pacing and credit expiry reproducible.
One future October transaction demonstrates the catch-up date. A supplementary
Freedom Flex export exercises rotation and cap tests without adding a fifth card
to the example wallet. Fixture data is synthetic, not your actual finances.

For CLI use against this example:

```sh
export WHICHCARD_DB=var/fixtures.db
export WHICHCARD_TODAY=2026-10-14
whichcard recommend costco --amount 180 --json
whichcard trackers
whichcard insights
whichcard gap
whichcard redeem --cash 420 --points 28000 --program united --fees 11.20
whichcard airport SFO
whichcard review
whichcard ask 'How much did I spend on dining?'
```

Unset both variables before using your own data. Normal storage is
`var/whichcard.db`. `make smoke` uses a separate temporary copy of reference and
configuration files and a synthetic database; it does not modify your wallet.

## Fill in your wallet

On first load, `config/wallet.example.yaml` is copied to `config/wallet.yaml` if
absent. Edit that file, or use **Settings → Wallet configuration**. The editor
accepts JSON; the file is saved as YAML. Keep only products you hold. List available
product IDs with `whichcard cards list`.

For each card, set `card`, optional `nickname`, `opened_on` (YYYY-MM-DD),
`credit_limit` (dollars), and `statement_day` (1–31). Last four digits are optional;
full card numbers are not accepted. This version supports one instance per card
product. For charge cards, enter a planning limit only if appropriate and treat
utilization as an estimate, not issuer reporting.

Open bonuses use `signup_bonus: {min_spend: 4000, deadline: 2026-11-30,
completed: false}`. Set `completed: true` once fulfilled. Optional balances and
inquiries are entered in the same file. Authorized-user cards are counted in the
5/24 heuristic and do not automatically create assumed hard inquiries.

Selected-category products need `settings: {chosen_category: online_shopping}`
(or another canonical category). An activation-required earn rule is excluded
until its zero-based rule index is confirmed, for example
`settings: {activated_3: true}` for the seeded Freedom Flex gas rule. Update the
rule dates and categories against issuer terms first. See
`backend/whichcard/engine/README.md` for cap and tie resolution.

In **Wallet**, enter actual closing statement balances. Automatically computed
balances only sum a statement cycle; they cannot reconstruct a carried balance.
Manual balances override estimates. Credit usage is inferred from matching
transactions; **Mark fully used** records a manual period total without double
counting automatically matched spending.

## Ten-minute card-data review

1. Run `whichcard cards review`, then open `REVIEW_CARDS.md`. Your wallet cards sort
   first. All 38 seeded cards have low confidence and no verification date.
2. Compare your products with their issuer terms. Check fees, category exclusions,
   caps, enrollment/activation, selected categories, portal-only rates, credits,
   and bonus eligibility. Seeded credits are a conservative subset and some
   products are historical or no longer available to new applicants.
3. Edit their files in `data/cards/`. Only you should assign a verification date
   after checking. Restart the server after reference-file changes.
4. Review `data/valuations.yaml` and `data/transfer_partners.yaml`; use Settings
   valuation overrides for your own cash-out, typical and optimized values. These
   are scenarios, not promises of availability or redemption value.
5. Verify lounge membership, enrollment, guest charges, terminal, opening hours
   and admission limits before travel. The 50-airport directory is unverified.
   Airports without a supported membership mapping show no access. Coordinates
   come from the public-domain OurAirports dataset; see `data/AIRPORTS_SOURCE.md`.

Generate the review table again when definitions change. Mark the blank Verified
column yourself. New files fail validation at startup with a file and line;
misspelled fields are rejected rather than silently ignored.

## Export statements and import them

Use your issuer's transaction/activity download, not a PDF statement. UI labels
vary; select a full date range, **CSV** where available, and avoid overlapping
account identities. Keep exported files in the gitignored `imports/` folder.

| Issuer | Export route and expected columns | Adapter |
|---|---|---|
| Chase | Card → Account activity → Download; Transaction Date, Post Date, Description, Category, Type, Amount, Memo | `chase` |
| American Express | Statements & Activity → Download transactions → CSV; Date, Description, Amount, Extended Details, Category | `amex` |
| Capital One | Account → Transactions → Download; Transaction Date, Posted Date, Card No., Description, Category, Debit, Credit | `capitalone` |
| Citi | Account activity → Download/export; Status, Date, Description, Debit, Credit | `citi` |
| Bank of America | Account activity → Download → spreadsheet/CSV; Posted Date, Reference Number, Payee, Address, Amount | `bofa` |
| Discover | Activity & Statements → Download; Trans. Date, Post Date, Description, Amount, Category | `discover` |
| Wells Fargo | Account activity → Download → CSV; Date, Amount, Star, Check Number, Description | `wellsfargo` |
| Apple Card | Wallet → Apple Card → Card Balance → monthly statement → Export Transactions → CSV; Transaction Date, Clearing Date, Description, Merchant, Category, Type, Amount (USD), Purchased By | `apple` |

Headerless five-column Wells Fargo downloads are detected automatically. If an issuer has changed its format, use a CSV with Date, Description,
Amount (purchases positive, refunds negative), optional Category and Currency,
then force `generic`. The generic adapter also infers unfamiliar headings from
sample values, or reports the missing column. It cannot safely guess an issuer's
sign convention from arbitrary unlabeled rows.

```sh
whichcard import imports/chase.csv --card CSP
whichcard import imports/other.csv --card amex-gold --adapter generic
whichcard import imports/export.qfx --card amex-gold
```

Or use **Transactions → Import an export**, choose the wallet card, and upload
CSV, OFX or QFX (up to 10 MB). Detection is automatic, with a forced-adapter
selector. OFX/QFX banking debit signs are normalized; both XML and common SGML
transaction blocks are supported. Malformed rows or unsupported encodings
fail with an explanation instead of partially committing rows. UTF-8/BOM CSV is
supported. A repeated file adds zero rows; overlapping exports deduplicate by
card, transaction date, cents and raw description. Distinct purchases with all
four values identical are indistinguishable and deduplicate—review exports if
that occurs. Payments and fees are retained but excluded from eligible rewards.

Foreign rows are flagged. The app does not fetch exchange rates: use the issuer's
billed USD amount for comparable totals. A non-USD amount left in an export is
not converted and must not be interpreted as a precise USD value.

## Review and correct inference

Open **Transactions → Low confidence only**, or run `whichcard review`. Change
category or channel in place, or edit merchant ID and leave the field to save.
Corrections apply without re-importing. A category/merchant correction for a
repeated normalized description creates a learned pattern for future imports.
Learned patterns take precedence over shipped patterns. Channel corrections are
transaction-specific so in-person and online variants are not conflated.

Costco Gas, Walmart, Target and Amazon intentionally remain low-confidence until
reviewed; a store name alone does not prove how a purchase codes. Recurring
subscriptions require a consistent monthly description/amount pattern. The
spend profile reports raw spend; candidate simulations weight spend by inference
confidence and never extrapolate missing months.

## Use the screens

- **Now:** merchant/category, amount, app context or location; every ranked card
  shows its arithmetic, warnings, valuation range and confidence. At-risk bonuses
  can take priority over the highest immediate rate.
- **Wallet:** bonus pacing, current credits, statement utilization and marginal
  annual-fee value against your other cards. Perk values can be entered in
  `preferences.local.yaml` as annual dollar amounts under `perk_values`.
- **Plan:** utilization targets, 5/24/inquiry heuristics, and five candidate cards
  with annual value, one-time bonus, sensitivity and swap scenarios. These are
  heuristics, never predicted credit-score changes.
- **Travel:** per-unit flight/hotel cash, points and fees; set nights for hotels.
  See forgone earning and transfer-adjusted value. Optional portal UI input models
  Chase; the API supports a named portal and wallet card. Airport lookup works
  without maps or live airline/lounges APIs.
- **Ask:** computed findings when no model is configured, or optional local chat.
  Dismissed findings stay dismissed when their fingerprint recurs.
- **Settings:** goal, valuations, utilization targets, wallet, local model,
  pinned places and manually entered offers. Goal is a recorded preference;
  typical valuation drives rankings in all modes, as specified.

## Reach it from a phone and install

Keep the computer and server running. On the same trusted Wi-Fi, open
`http://<computer-LAN-IP>:8787`. A private Tailscale address can also reach the
server; installing/configuring Tailscale is optional and outside this app.

Plain LAN HTTP can display the app and serve Shortcuts, but browsers require a
**secure context** for geolocation and service-worker installation. For a fully
installable phone PWA, use an HTTPS reverse proxy on your private network (a
locally trusted certificate or private Tailscale Serve). Do not enable a public
funnel. `localhost` is trusted for desktop testing; a phone's localhost refers to
the phone, not this computer. The app itself remains local and makes no cloud
requests. Certificate/network setup is managed outside whichcard.

On iPhone Safari, use Share → Add to Home Screen. On Chrome, use Install app when
offered. Visit each screen once while connected so its read data is cached.
The offline app can show the shell and previously cached reads. New imports,
corrections, chat and new calculations require the local server. Caches contain
private financial data on that browser: use a trusted device, and clear site data
when retiring it. Offline information may be stale.

See `shortcuts/README.md` for the four automation recipes.

## Enable a local LLM (optional)

Start an OpenAI-compatible server on **the same computer** using an already
installed Ollama, llama.cpp server or LM Studio and a locally downloaded model.
Model downloads are a setup operation; inference stays local. Example endpoint
values are `http://127.0.0.1:11434` (Ollama), `http://127.0.0.1:8080`
(llama.cpp), or `http://127.0.0.1:1234` (LM Studio). Model names must match what
your server has loaded.

Set **Settings → Provider → Local OpenAI-compatible server**, base URL and model.
Enable tool calls only if the model/server supports them; explicit unsupported-tool
responses fall back to retrieval. Otherwise compact summaries and findings are
injected directly. `/v1` on the base URL is accepted. No API key is needed or sent.
Remote URLs, embedded credentials, HTTPS remote endpoints and redirects are
rejected. Raw transaction rows are not supplied by default. The optional
`transactions` tool returns a bounded selected view, not raw descriptions.

The model is instructed to cite computed sources, acknowledge low confidence,
state limits and keep replies short. It may still make mistakes; compare its
answer with the cited summary/finding. With provider `none`, the rest of the app
is fully functional. Provider `mock` is for deterministic testing.

Optional integration test:

```sh
WHICHCARD_LIVE_LLM=http://127.0.0.1:11434 WHICHCARD_LIVE_MODEL=llama3.2 \
  .venv/bin/pytest backend/tests/test_insights_assistant.py -k live
```

No configured/reachable endpoint means a skipped test, not a failed build.

## Operations, checks and backup

`make check` runs Ruff, mypy, pytest and coverage, TypeScript, Vitest and a
production build. Coverage must reach 80% independently for engine, trackers,
analysis and inference. `make fixtures` regenerates synthetic exports and imports
them idempotently. `make smoke` boots an isolated real server and exercises every
UI endpoint, including writes, without touching your private configuration.

Back up `var/whichcard.db`, `config/wallet.yaml`, all `config/*.local.yaml`, and
`data/merchants/learned.local.yaml` with the server stopped. Those paths and
`imports/` are gitignored. Reference YAML is versioned; private mutations are
separate local files. Database migrations are numbered SQL files and run once,
transactionally. No full card-number field exists.

If a recommendation surprises you: review category and channel, card activation,
cap consumption, bonus priority, valuation and warnings. If a server fails to
start: inspect its file/line validation message, interpreter version or occupied
port. If the browser shows an old shell after a rebuild: reload once online or
clear that site's service-worker/cache data. If a download format changed: use
the generic adapter with explicit normalized columns.
