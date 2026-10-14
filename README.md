# whichcard

A local-first credit card optimizer: which card to use for a purchase and why,
plus the long-horizon tracking that the register moment hides (sign-up bonus
deadlines, expiring credits, annual fee break-even, utilization, 5/24), gap
analysis against real spend, cash-versus-points math, and an optional local LLM you
can ask about your own spending. All data stays on your machine.

This repo currently holds the specification only. The code is built by an agent
from the prompts below.

## Files

- `SPEC.md` — the specification: scope, architecture, data formats, feature
  acceptance criteria, milestones, tests, completion checklist.
- `AGENTS.md` — operating rules for the agent (read automatically by Codex and
  Claude Code).
- `PROMPT.md` — the prompt to paste to start the build, and the one to paste if a
  fresh session has to resume it.

## Building it

1. Clone this repo and open it in Codex (or Claude Code) with the most autonomous
   approval mode available and network access for package installs. Nothing in the
   spec needs an API key, an account, or a paid service.
2. Paste the Start prompt from `PROMPT.md`.
3. When the usage cap hits, press reset and let it continue. If the same session
   resumes, do nothing. If you land in a new session, paste the Resume prompt.
   `PLAN.md` and the per-milestone commits are what make that work.

The milestones are ordered so a run that dies early still leaves something usable:
data layer, import, inference, engine, and CLI come first; the PWA is last.

## After the build

About 20 minutes of manual work:

1. Edit `config/wallet.yaml` with the cards you hold, open dates, limits, and any
   open sign-up bonus.
2. Export CSVs from each issuer's website and drop them in `imports/`.
3. `make run`, then open the PWA on your phone over your LAN (Tailscale works well
   for this).
4. Set up the Shortcuts automations by following `shortcuts/README.md`. This is the
   one part an agent cannot do for you; it takes about five minutes.
5. Read `REVIEW_CARDS.md` and fix any card facts that are wrong. Seeded card data
   comes from the model's memory and is marked unverified on purpose.
6. Optional: install Ollama, pull a model, and point `config/preferences.yaml` at
   it to turn on the assistant.

`RUNBOOK.md` covers all of this in detail once the build has produced it.
