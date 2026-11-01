# ADR-0006: The protocol is a versioned package, not a convention

- **Status:** Accepted
- **Date:** 2026-11-01
- **Amended by:** [ADR-0007](0007-plugin-initiated-http-transport.md) — rule 5's
  parenthetical example names WebSocket, which Luau does not provide. The rule
  itself (schemas make no transport assumptions) stands unchanged; the body
  below is left as written, because an accepted ADR is a record, not a document
  to edit.

## Context

The engine is Python; the plugin is Luau. Every interaction between them is a
message whose shape must be agreed by both. Without a single owner, that shape
gets defined twice — once as Python types, once as Luau tables — and the two
definitions drift.

The drift is made worse by release cadence. The API updates when the user pulls
the repository. The plugin updates when the user reinstalls it into Studio,
which happens rarely. So an old plugin talking to a new API is the normal case,
not an edge case.

In practice, cross-language contract bugs are the most expensive class of bug in
a system like this: the failure appears far from the cause, and reproducing it
needs both runtimes.

## Decision

`packages/protocol` is a package of its own and is the single source of truth
for the contract. Versioned JSON Schema definitions under `schemas/v1/`.

Rules:

1. Schemas are authoritative. Python types and Luau tables are derived from or
   validated against them, never the reverse.
2. Every message carries a protocol version; version negotiation happens
   explicitly on connect.
3. Within a major version, changes are additive only. Removing or renaming a
   field, or narrowing a type, is a major bump.
4. Both sides validate — the API validates what the plugin sends and vice versa.
   A malformed message is rejected and logged, never coerced.
5. Schemas make no transport assumptions. Long-poll vs WebSocket stays open.
6. A protocol change is its own reviewable pull request; it does not ride along
   inside a feature PR.

Message families and open questions are listed in
[`docs/protocol/README.md`](../../protocol/README.md).

## Consequences

**Easier:**

- The two sides can be developed and released independently without silent
  incompatibility.
- Integration failures surface as validation errors at the boundary, with a
  clear culprit, instead of as strange behaviour three steps later.
- Schemas double as the boundary's documentation for contributors who only work
  on one side.

**Harder:**

- Schema-first is more ceremony than writing the types inline. Early on, when
  the contract changes daily, this will feel like friction — and it partly is.
- Validation on both sides costs code and runtime.
- Luau has no mature JSON Schema validator, so the plugin-side validation will
  likely need either generated validators or a hand-written subset. That work is
  not designed yet and is a known risk to this decision.

**Given up:** the speed of changing a message shape in one place and fixing the
other side when it breaks.

## Alternatives considered

- **Convention and documentation only.** Rejected: it is what produces the
  drift this ADR exists to prevent.
- **Generate the contract from the Python types.** Tempting and cheaper, but it
  makes Python the authority, so the Luau side is permanently downstream and the
  plugin's needs do not get a vote in the contract's design.
- **An IDL with code generation (Protobuf, Cap'n Proto).** Rejected for now:
  stronger guarantees, but Luau tooling support is poor and it adds a build step
  to the plugin. JSON Schema over JSON is what Studio's HTTP layer handles
  natively.
