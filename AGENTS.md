# Operating rules

These rules govern the whole build of `whichcard`. `SPEC.md` is the specification;
this file is how you work. Read both in full before your first action, and re-read
both after any restart or loss of context.

1. Never ask the user a question. When the spec is silent or ambiguous, decide,
   implement, and record the decision with a one-line rationale in `ASSUMPTIONS.md`.
   When something in the spec is impossible as written, implement the closest
   feasible version and record it under a "Deviations" heading in the same file.
   Never stop early for any reason other than the Completion checklist in `SPEC.md`
   being fully satisfied.
2. No runtime network, no secrets. The finished app must run with the network
   unplugged. The only network use at runtime is an optional call to a local LLM
   server on the user's own machine. Build-time package installs are fine. If a
   download fails during the build, vendor or embed what you need and note it.
3. Work milestone by milestone, in order. Do not start milestone N+1 until
   `make check` passes at milestone N. Commit at the end of each milestone with
   the message `M<n>: <summary>`. Commit more often if useful.
4. Keep `PLAN.md` current: one checkbox per task under each milestone, ticked as
   you go, with a "Current task" line at the top. On any restart or loss of
   context, read `AGENTS.md`, `SPEC.md`, `PLAN.md`, `ASSUMPTIONS.md`, and
   `git log --oneline` before doing anything else.
5. Every feature ships with tests. The synthetic fixtures described under Testing
   in `SPEC.md` are the ground truth. A feature without tests is not done.
6. Seeded financial data is never presented as verified. Every card definition
   carries `confidence` and `verified_on` fields; everything you seed from memory
   gets `confidence: low` or `medium` and `verified_on: null`, and is listed in
   `REVIEW_CARDS.md` for the user to check.
7. Prefer boring, widely used libraries, pinned versions, and as few dependencies
   as the job allows. The engine must be correct; the UI may be plain.
8. Never store full card numbers. `last4` is optional. User data lives under
   `var/` and `imports/`, both gitignored. Fixtures are synthetic and committed;
   real data is never committed.
9. Quality bar at every milestone: `ruff` and `mypy` clean, `pytest` green,
   frontend typecheck and build green.
10. Documentation is for running the thing, not describing it. `README.md` stays a
    short pointer to `RUNBOOK.md` once `RUNBOOK.md` exists.
11. If a milestone is taking far longer than its neighbors, cut scope within that
    milestone (plainer UI, fewer seeded cards, simpler heuristics), note the cut in
    `ASSUMPTIONS.md`, and move on. A finished, narrower v1 beats an unfinished
    broad one.
