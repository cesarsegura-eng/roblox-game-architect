# apps/web — the web application

Where the user describes the game they want, watches the agent work, reviews
what it proposes and approves what it changes.

**Status: not implemented, and the framework is not chosen.** Stage 6 on the
[roadmap](../../README.md#roadmap). The choice is listed as deliberately open in
[`ARCHITECTURE.md` §6](../../ARCHITECTURE.md) — it is not an oversight, and it is
not urgent: nothing else in the system depends on it.

## Intended responsibilities

- Capture the user's request and show the agent's plan.
- Stream the run: what the planner decided, what the builder produced, what
  validation said, what the playtest reported.
- **Host the approval UI.** This is the surface where a human decides whether
  something touches their real place
  ([ADR-0002](../../docs/architecture/adr/0002-execution-boundary-and-autonomy.md)).
- Show estimated cost before a run and spend during it (invariant I6).
- Render the run log — the audit trail described in
  [`docs/safety.md`](../../docs/safety.md).

## Boundaries

- It talks only to `packages/api` over HTTP. It never talks to an LLM provider
  and never holds a provider key.
- It enforces nothing. Approval gates, spend caps and validation all live
  server-side, so a different front end cannot bypass them. The UI presents
  those controls; it is not where they live.
