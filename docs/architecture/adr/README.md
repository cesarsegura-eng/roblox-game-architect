# Architecture Decision Records

Short documents recording a decision, its context, and what it costs.

## Why we keep these

In an open source project with non-obvious decisions, every new contributor
otherwise reopens debates that were already settled — and the reasoning is
nowhere to be found, because it lived in a conversation. An ADR is cheap to
write and stops that.

## Rules

- One decision per record. Numbered, never renumbered.
- A record is **immutable** once accepted. To change a decision, write a new ADR
  that supersedes the old one and mark the old one `Superseded by ADR-NNNN`.
  Where only part of a record turns out wrong, the new ADR *amends* it: add an
  `Amended by:` line to the old record's header and leave its body alone. The
  body is the reasoning as it stood, including the mistake.
- Status is one of `Proposed`, `Accepted`, `Superseded`, `Deprecated`.
- Dates are the date of acceptance, in `YYYY-MM-DD`.
- Write the consequences honestly, including the ones you dislike. An ADR with
  no downsides listed is marketing, not a record.

## Template

```markdown
# ADR-NNNN: Title

- **Status:** Proposed
- **Date:** YYYY-MM-DD

## Context
What forces are at play? What makes this decision necessary?

## Decision
What we are doing, stated plainly.

## Consequences
What becomes easier. What becomes harder. What we are giving up.

## Alternatives considered
What else was on the table, and why it lost.
```

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-monorepo-layout.md) | Monorepo layout with a web-free core | Accepted |
| [0002](0002-execution-boundary-and-autonomy.md) | Execution boundary and autonomy model | Accepted |
| [0003](0003-llm-provider-abstraction.md) | Provider-agnostic LLM interface with a fake | Accepted |
| [0004](0004-generated-project-storage.md) | Generated projects live outside the repository | Accepted |
| [0005](0005-credentials-and-thin-plugin.md) | Credentials stay server-side; the plugin is thin | Accepted |
| [0006](0006-protocol-single-source-of-truth.md) | The protocol is a versioned package | Accepted (amended by 0007) |
| [0007](0007-plugin-initiated-http-transport.md) | Plugin-initiated HTTP with long-polling | Accepted |
| [0008](0008-edit-action-flat-operations.md) | `edit.action` is a flat list of primitive operations | Accepted (amended by 0010, proposed) |
| [0009](0009-luau-validation-subset-and-strict-json.md) | Both sides validate: a closed schema subset and a strict JSON profile | Accepted (amended by 0012 and 0013, proposed) |
| [0010](0010-script-execution-reach-and-action-semantics.md) | Script execution reach and action semantics | Proposed |
| [0011](0011-delivery-execution-and-recovery.md) | Delivery, execution, idempotency and recovery | Proposed |
| [0012](0012-untrusted-text-and-unicode-rendering.md) | Untrusted text: lossless on the wire, exact in storage, escaped for display | Proposed |
| [0013](0013-conformance-suites.md) | Conformance suites as the shared contract | Proposed |
| [0014](0014-luau-source-analysis-with-lute.md) | Official Lute parser for Luau source analysis | Proposed |
| [0015](0015-disposable-world-validation.md) | Disposable Roblox place validation boundary | Proposed |
| [0016](0016-sqlite-lifecycle-store.md) | SQLite lifecycle storage for the local API | Accepted |
| [0017](0017-standard-library-operator-panel.md) | Standard-library local operator panel | Accepted |
| [0018](0018-remote-roblox-map-authoring.md) | Remote Roblox map authoring boundary | Accepted |
| [0019](0019-remote-model-asset-pipeline.md) | Remote Blender model assets into Roblox places | Accepted |
