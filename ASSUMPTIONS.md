# Decisions
- Dates in synthetic acceptance tests use 2026-10-14 as their fixed clock; live use defaults to the machine's local date.
- Build uses Python 3.11+ and npm; PYTHON may select an installed interpreter because the system Python here is 3.9.
- The repository is the local-only deliverable, with no deployment or runtime cloud services.

- One instance of each card product is supported in a wallet; duplicate ids fail validation to prevent state collisions.
- Mutable preferences, places, offers and learned overrides use gitignored `.local.yaml` files, protecting private edits from commits while preserving reference defaults.
- The example Gold/Platinum limits are synthetic planning limits, not representations of charge-card reporting rules.
- Selected-category cards require explicit settings; Custom Cash uses a configured expected top category in v1 instead of predicting it.
- Seeded lounge entries with unknown names are marked as unverified directory checks, never confirmed access; verify membership and admission before travel.
- Activation-required rates are excluded until explicit wallet activation, while showing a warning; this avoids assuming an unearned rate.
- Offers are manually maintained and assumed eligible/unused; the reward-rate bound excludes offer value, since the spec's unconditional effective-rate bound conflicts with additive offers.
- Bonus spend is monotone only for added purchases; refunds correctly reduce it, resolving the spec's overly broad monotonicity property.
- Caps split a purchase at the remaining allowance. No currency conversion is inferred; foreign-currency rows are flagged and require review of the billed USD amount.
- Gap simulations route confidence-weighted monthly category/channel segments through the engine and respect caps; missing months are not extrapolated. Selected-category candidates use the largest observed category, disclosed in output.
- Known lounge names are unverified seeds. Airports without a supported verified program mapping show no access, rather than inventing a membership benefit.
- Redemption opportunity cost uses typical point values and the cash-versus-tax earning difference; hotel prices/points/fees are per night when nights exceeds one.
- All-kind findings acceptance adds the supplementary Freedom Flex rotation fixture to the four-card wallet; the shipped example itself has no rotating card.
- Idle points findings mean a recorded balance above threshold; actual redemption dormancy cannot be established without redemption history, and output says so.
- Assistant tools use conservative character-bounded payloads, a four-round budget, and a local-only HTTP allowlist. Tool support is an explicit preference because OpenAI-compatible servers lack a uniform capability advertisement.
- Phone browsers require an HTTPS secure context for installation, geolocation and service workers. LAN HTTP supports basic browsing and Shortcuts; private HTTPS setup is documented because the app cannot provision a trusted certificate on a user's phone unattended.
- CSV parsing supports UTF-8/BOM and detects headerless five-column Wells Fargo exports; unknown sign conventions use explicitly normalized generic CSV.
- The daily Shortcuts recipe uses `/api/now?summary=true`, a compact bonus/credit summary added to the context endpoint.

# Deviations
- Learned corrections are written to gitignored `learned.local.yaml` instead of committing user-derived patterns into `learned.yaml`; defaults remain versioned and load first.
- Unconditional rate-bound and SUB-monotonicity requirements are inconsistent with offers/refunds; tests bound reward-only rates and purchase-only monotonicity while separately testing offers and refunds.
- Native installation on an actual phone cannot be performed here. Chrome at phone width passes the platform installability checks; private HTTPS provisioning remains a documented user setup step.
- v1 limits mutable wallet instances to one per product, uses explicit expected-category settings for Custom Cash, and seeds a conservative subset of complex credits; these limits are disclosed before reliance.

# Validation record
- 38 seeded cards; 363 merchant patterns; 50 lounge-airport entries and vendored large/medium airport coordinates.
- 47 golden recommendation cases plus Hypothesis properties, fixture acceptance, API and frontend tests.
- Chrome at 390 px: all seven screens render fixture data without horizontal overflow; desktop layout visually inspected.
- Normal isolated Chrome profile: installability error list empty; offline reload renders shell and cached recommendation; no external browser requests or JavaScript errors.
- First-load service-worker caching and refreshed computed statement balances have regression tests.
