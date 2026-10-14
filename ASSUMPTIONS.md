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
