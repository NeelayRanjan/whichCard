# Decisions
- Dates in synthetic acceptance tests use 2026-10-14 as their fixed clock; live use defaults to the machine's local date.
- Build uses Python 3.11+ and npm; PYTHON may select an installed interpreter because the system Python here is 3.9.
- The repository is the local-only deliverable, with no deployment or runtime cloud services.

# Deviations
None yet.
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
