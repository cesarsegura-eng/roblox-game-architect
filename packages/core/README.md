# packages/core — the engine

The planning, generation, validation and review loop. This is the part of the
system that actually designs, builds, tests and improves a game.

**Status: not implemented.** There is nothing to run here yet. Stage 3 on the
[roadmap](../../README.md#roadmap).

## The one rule

**This package must not import a web framework.** Invariant I1. The engine has
to stay importable from a plain script and from CI, with no server running —
that is what makes the hardest component in the system testable and what lets a
contributor reproduce a generation. Reviewers enforce it; see
[ADR-0001](../../docs/architecture/adr/0001-monorepo-layout.md).

It may import `packages/protocol` and `packages/sandbox`. It must never import
`packages/api`.

## Intended layout

```
agents/     planner, builder, tester, reviewer — separate, testable units
llm/        the LLMProvider interface, the fake, and thin vendor adapters
domain/     domain models (GameSpec, Task, RunState, ...)
codegen/    Luau generation (validation belongs to packages/sandbox)
tests/      unit tests for all of the above
```

## Validation is not this package's job

`packages/sandbox` is the single authority on whether generated Luau may run.
`codegen/` produces code and calls into `sandbox` for a verdict; it does not
implement checks of its own, not even quick ones for faster feedback. Two
validators means the real gate eventually gets treated as optional
([ADR-0002](../../docs/architecture/adr/0002-execution-boundary-and-autonomy.md),
`ARCHITECTURE.md` §2).

## Design notes that already apply

- Agents depend on the `LLMProvider` interface only. No agent imports a vendor
  SDK ([ADR-0003](../../docs/architecture/adr/0003-llm-provider-abstraction.md)).
- `LLM_PROVIDER=fake` is the default and the mode tests run in. The suite must
  pass offline with no API key (invariant I7).
- `AGENT_MAX_ITERATIONS` and `AGENT_MAX_USD_PER_SESSION` are enforced here, not
  in the UI, so no front end can bypass them (invariant I6).
- Project content the agent reads is untrusted data and enters the model through
  a separate, labelled channel — never as instructions (invariant I3,
  [`docs/safety.md`](../../docs/safety.md)).
