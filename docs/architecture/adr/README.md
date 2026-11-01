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
