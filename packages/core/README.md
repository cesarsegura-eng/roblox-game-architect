# packages/core — the engine

The planning, generation, validation and review loop. This is the part of the
system that actually designs, builds, tests and improves a game.

**Status: partially implemented.** Two pieces exist: the LLM foundation (the
`llm/` package: provider interface, request/response types, trusted/untrusted
framing, a deterministic fake provider, and a registry that picks the provider
from `LLM_PROVIDER`, defaulting to `fake`) and the run guards (`budget.py`, below: iteration and spend), all with unit
tests. The guards are not used by any loop yet. There are no real vendor
adapters (so nothing quotes real costs), and the planning, generation,
validation and review loop is not built.
Stage 3 on the [roadmap](../../README.md#roadmap).

## The one rule

**This package must not import a web framework.** Invariant I1. The engine has
to stay importable from a plain script and from CI, with no server running —
that is what makes the hardest component in the system testable and what lets a
contributor reproduce a generation. Reviewers enforce it; see
[ADR-0001](../../docs/architecture/adr/0001-monorepo-layout.md).

It may import `packages/protocol` and `packages/sandbox`. It must never import
`packages/api`.

## Layout

Present today:

```
llm/        the LLMProvider interface, the fake, and the provider registry
budget.py   IterationBudget (AGENT_MAX_ITERATIONS) and SpendBudget /
            BudgetedLLMProvider (AGENT_MAX_USD_PER_SESSION)
tests/      unit tests for llm/ and budget.py
```

Planned, **not yet present**:

```
agents/     planner, builder, tester, reviewer — separate, testable units
domain/     domain models (GameSpec, Task, RunState, ...)
codegen/    Luau generation (validation belongs to packages/sandbox)
```

Thin vendor adapters for `llm/` are also planned.

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
- `AGENT_MAX_ITERATIONS` and `AGENT_MAX_USD_PER_SESSION` are to be enforced
  here, not in the UI, so no front end can bypass them (invariant I6). Both
  guard mechanisms exist, but the agent loop does not integrate either yet:
  - **Implemented — iteration guard.** `IterationBudget` (`budget.py`) takes a
    positive `int` limit (bools and non-ints are rejected). `consume()` allows
    exactly `limit` calls and raises `IterationLimitExceededError` before
    exceeding it; `consumed`, `remaining` and `limit` are observable.
    `IterationBudget.from_env()` reads `AGENT_MAX_ITERATIONS`, defaulting to 10
    only when the variable is absent. A present but empty, blank or invalid
    value raises `InvalidIterationLimitError` (fail closed). Nothing in the
    loop calls it yet, because the loop does not exist.
  - **Mechanism implemented, not yet in use — spend cap.** `SpendBudget` and
    `BudgetedLLMProvider` (`budget.py`) implement the
    `AGENT_MAX_USD_PER_SESSION` cap (`SpendBudget.from_env()`, default 1.00 USD
    only when the variable is absent; invalid values raise). A paid call is
    admitted only if the provider returns a maximum-cost quote that fits in
    `limit - spent - reserved`; the check and the hold happen under one lock.
    Settlement is exact `Decimal` arithmetic that fails closed, is atomic (if
    it cannot be computed the reservation stays held, never released uncounted)
    and can happen only once per reservation. A failed call is charged its full
    quote. **The agent loop does not use it yet** (the loop does not exist), and
    **there are no real adapters that quote**, so no real paid call is capped
    today. The guarantee is only as strong as the adapter's promise: the cap
    holds if each adapter's quote is a true upper bound on what the vendor will
    charge and its reported `usage.cost_usd` is the real cost. A provider that
    under-quotes or under-reports can overspend; an overcharge is recorded and
    raises `ProviderQuoteViolation`, which blocks further calls only after the
    fact.
- Project content the agent reads is untrusted data and enters the model through
  a separate, labelled channel — never as instructions (invariant I3,
  [`docs/safety.md`](../../docs/safety.md)).
