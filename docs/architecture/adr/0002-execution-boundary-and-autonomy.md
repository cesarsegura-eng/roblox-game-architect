# ADR-0002: Execution boundary and autonomy model

- **Status:** Accepted
- **Date:** 2026-11-01

## Context

The product writes Luau and runs it in the user's Studio session. Luau in Studio
reaches `HttpService`, `DataStoreService`, `MarketplaceService`, the plugin API
and the user's Roblox account. A hallucinated script — not even a malicious one
— can destroy a place or exfiltrate data.

Two further forces:

- The agent reads project content (script text, instance names, descriptions).
  Any of it may contain text aimed at the agent. With high autonomy this is a
  privilege-escalation path.
- An autonomous "improve" loop against a paid API is an unbounded spend.

This decision has to be made now rather than later. Retrofitting a security
boundary onto code that already assumes it can execute freely is a rewrite, and
in security it is rarely done well the second time.

## Decision

**Three gates, in this order, before generated code affects anything the user
cares about:**

1. **Static validation** in `packages/sandbox`, not skippable. An API allowlist
   under version control, structural checks (no `loadstring` or dynamic code
   construction), and a blast-radius check that the touched instances are a
   subset of what the task declared. Failure returns to the builder as feedback
   and never prompts the user for an override.
2. **Human approval** before anything is applied to a real place.
3. **Disposable execution** — first run always in a throwaway test place.

**Default autonomy is "propose and wait", not "act and report."** Planning,
generating, validating and running in a disposable place are autonomous.
Modifying the user's working place, deleting content and changing settings
require approval. Publishing is never done by the agent.

**Project content is data, never instructions.** Enforced structurally — a
separate, delimited, untrusted-labelled channel — not by asking the model
nicely in a system prompt.

**Every run is bounded** by `AGENT_MAX_ITERATIONS` and
`AGENT_MAX_USD_PER_SESSION`, enforced in `packages/core` so no front end can
bypass them.

Every autonomous action goes to a human-readable run log.

The full matrix is in [`docs/safety.md`](../../safety.md).

## Consequences

**Easier:**

- The blast radius of a bad generation is bounded by design rather than by luck.
- A fresh clone cannot bill the user by accident (the default provider is
  `fake`) and cannot publish anything.
- The boundary is a named package, so a reviewer can find and audit it.

**Harder:**

- Approval gates make the product feel less magical. A user who wants to walk
  away and come back to a finished game will be disappointed by the default.
- The API allowlist is maintenance: every legitimately needed API is a reviewed
  diff, and the agent will hit walls that look like bugs to users.
- The blast-radius check requires tasks to declare their scope up front, which
  constrains how the planner can be written.
- Structural separation of untrusted content costs prompt tokens and
  implementation complexity on every call.

**Given up:** fully unattended operation as the default. Users can loosen the
middle of the matrix per session; they cannot loosen publishing or validation.

## Alternatives considered

- **Act and report, with undo.** Rejected: undo in Studio is not reliable
  enough to be a safety control, and some actions (publishing, DataStore writes,
  HTTP calls) are not reversible at all.
- **Validation as a warning rather than a gate.** Rejected: a warning that can
  be clicked through is not a control, and the user is not well placed to judge
  generated Luau.
- **Prompt-level instruction instead of structural separation for injection.**
  Rejected as a sole control: it reduces the rate but does not bound the risk,
  and it fails silently.
- **Rely on Roblox's own sandboxing.** Rejected: it protects Roblox and other
  users, not this user's own place and data, which is exactly what is at risk.
