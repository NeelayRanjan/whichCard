# Build plan
Current task: M3 — inference and correction loop.

## M0 Scaffold
- [x] Repository layout, pinned Python/Node dependencies, Make targets, ignores and assumptions.
- [x] Health API, CLI entry point, Vite shell; lint, types, tests and build; commit.
## M1 Data layer
- [x] Strict YAML models/loaders for all reference and config files with file/line errors.
- [x] At least 36 unverified cards, categories, valuations, transfers, app contexts, lounge programs and 50 airports, vendored airport coordinates.
- [x] Four-card example wallet, preferences, places, offers; cards list/review CLI and REVIEW_CARDS.md.
- [x] Positive/negative schema tests; make check; commit.
## M2 Storage and import
- [x] Versioned idempotent migrations, all state tables and indexes, integer cents and ISO dates.
- [x] ImportSource, eight issuer CSV adapters, generic inference, OFX/QFX, signs/flags and dedupe; import CLI.
- [x] Deterministic 12-month JSON/CSV/OFX fixtures and manifest covering all required edge cases; scratch fixture DB.
- [x] Adapter, dedupe and storage tests; make fixtures and make check; commit.
## M3 Inference
- [ ] Normalizer, 250+ patterns, issuer categories, confidence, aliases, channel/recurring detection.
- [ ] Overrides persisted on read, learned patterns, low-confidence queue and review CLI.
- [ ] Coverage/ambiguity/override tests; make check; commit.
## M4 Engine
- [ ] Context/ranking, AND matches, partial/exhausted caps, activation warnings, offers, SUB override, foreign fees and ties.
- [ ] Valuation ranges, arithmetic/reasons/confidence, engine README; API and recommend CLI.
- [ ] 40+ golden cases and property tests; make check; commit.
## M5 Trackers
- [ ] Bonus pace/status, credit periods/auto/manual usage, trailing-year fee arithmetic and product changes.
- [ ] Statements/utilization/paydown, dormancy, inquiries, 5/24 age-out timeline; API and CLI.
- [ ] Fixture acceptance and property tests; make check; commit.
## M6 Analysis
- [ ] Confidence-weighted spend profile; candidate/swap simulation, credits, fees, bonus, score heuristics and sensitivity.
- [ ] Cash/award/portal/hotel redemption math and transfer ratios; CLI/API.
- [ ] Lounge access, pinned places and coordinate resolution; now endpoint, alternatives and short notification.
- [ ] Analysis acceptance, zero-uplift properties and latency tests; make check; commit.
## M7 Insights and assistant
- [ ] All finding kinds, reconciled impacts, stable fingerprints/dismissals; insights CLI/API.
- [ ] Provider interface, mock/local OpenAI provider, bounded tools/retrieval, grounded prompt and local history.
- [ ] Ask CLI/API, disabled fallback, six suggestions, mock tests and optional live test.
- [ ] All-kind fixture tests; make check; commit.
## M8 PWA
- [ ] Seven mobile screens: Now, Wallet, Transactions, Plan, Travel, Ask, Settings; API-only financial computations.
- [ ] Imports, inline overrides, manual credits, preferences, places/offers, dismissals and error/loading states.
- [ ] Install manifest, icons, offline shell/read cache, dark mode, backend static serving.
- [ ] Vitest client/formatting tests, all-endpoint smoke and mobile browser verification; make check; commit.
## M9 Ship
- [ ] Four exact Shortcuts recipes, RUNBOOK setup/import/review/LAN/LLM guidance, short README.
- [ ] Final assumptions/data review; completion CLI/API checks and runtime network audit.
- [ ] Fresh clone: setup/check/fixtures/smoke; fix failures and repeat before final commit.
- [ ] All completion requirements verified, clean git, final milestone commit and v0.1.0 tag.
