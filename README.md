# whichcard

A local-first credit card optimizer with statement imports, explained purchase
recommendations, trackers, spend simulations, travel calculations, and an optional
local assistant. No cloud account, bank login, API key, or runtime internet required.

**Start with [RUNBOOK.md](RUNBOOK.md)** for installation, the synthetic demo,
wallet setup, imports, mobile access and data verification. Card terms are seeded,
unverified estimates—review [REVIEW_CARDS.md](REVIEW_CARDS.md) before relying on them.

```sh
make setup
make check
make run
```

Requires Python 3.11+ and Node 20.19+. Open `http://localhost:8787`.
See [shortcuts/README.md](shortcuts/README.md) for iOS automations and
[PLAN.md](PLAN.md) for milestone completion.
