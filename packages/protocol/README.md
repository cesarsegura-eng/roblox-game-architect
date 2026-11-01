# packages/protocol — the contract

Versioned JSON Schema definitions for every message crossing the Python/Luau
boundary. The single source of truth for the backend ↔ plugin contract.

**Status: not implemented.** This is stage 2 on the
[roadmap](../../README.md#roadmap) — the first thing to build, because
everything else is written against it.

The rules this package follows, the message families it will cover, and the open
questions are in [`docs/protocol/README.md`](../../docs/protocol/README.md).
The reasoning is in
[ADR-0006](../../docs/architecture/adr/0006-protocol-single-source-of-truth.md).

## In short

- Schemas are authoritative; Python types and Luau tables are derived from or
  validated against them, never the reverse.
- Every message carries a protocol version, negotiated explicitly on connect.
  An old plugin talking to a new API is the normal case, not an edge case.
- Additive changes only within a major version.
- Both sides validate.
- No transport assumptions.
- A schema change is its own pull request.

## Layout

```
schemas/
└── v1/      not created yet
```

## Known risk

Luau has no mature JSON Schema validator. The plugin-side validation will need
either generated validators or a hand-written subset, and that work is not
designed yet. It is the weakest point of this decision and is recorded as such
in ADR-0006.
