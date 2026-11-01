# ADR-0003: Provider-agnostic LLM interface with a fake implementation

- **Status:** Accepted
- **Date:** 2026-11-01

## Context

The engine's core dependency is a language model. Calling a vendor SDK directly
from the agent code creates two problems, one strategic and one immediate:

- **Lock-in.** Swapping providers, or supporting more than one, becomes a
  refactor across the whole engine.
- **Untestability.** Every test needs network access and a paid key, and returns
  a different answer each run. A contributor cannot run the suite. CI cannot
  either, unless the project funds it.

The second problem is the urgent one. The engine is the hardest part of this
system to get right, and a component that cannot be tested cheaply does not get
tested.

## Decision

`packages/core/llm` defines the project's own `LLMProvider` interface. Agents
depend on that interface only; no agent imports a vendor SDK.

Three kinds of implementation:

- **`fake`** — deterministic, offline, zero cost. Returns canned or
  rule-derived responses. **This is the default**, set in `.env.example` via
  `LLM_PROVIDER=fake`.
- **Real adapters** — one thin module per provider, containing the SDK call and
  nothing else: no prompt construction, no decision logic.
- **A recording adapter** (later) — replays captured real responses, for tests
  that need realistic output without paying for it.

The provider is selected by configuration, never by an import in agent code.
The test suite must pass with `fake` (invariant I7).

The default model for real runs is the latest and most capable Claude model
available; the adapter pins an explicit model id rather than an alias, so a
provider-side change cannot silently alter behaviour.

## Consequences

**Easier:**

- Tests are fast, free, offline and deterministic. A fresh clone runs the suite
  with no key.
- An evaluation suite with fixed cases becomes possible, which is the only way
  to review an engine change on evidence instead of vibes.
- Supporting a second provider is a new adapter, not a refactor.

**Harder:**

- The interface is an abstraction over APIs that genuinely differ (tool calling,
  streaming, caching, system prompt handling). It will leak, and keeping it
  honest is ongoing work.
- The `fake` provider is code that must be maintained and that can drift from
  real provider behaviour — a green suite against `fake` is not proof the system
  works live.
- Pinning model ids means deliberate upgrades instead of free improvements.

**Given up:** direct access to provider-specific features from agent code.
Anything vendor-specific has to be expressed in the interface first, which is
slower on purpose.

## Alternatives considered

- **Call the vendor SDK directly.** Rejected: makes the engine untestable
  without money and network, which is disqualifying for an open source project
  that wants contributions.
- **Use a third-party abstraction library.** Rejected for now: it is a large
  dependency whose abstraction choices we would inherit, in exchange for
  replacing an interface we can write in an afternoon. Revisit if we need many
  providers.
- **Mock the SDK in tests instead of abstracting.** Rejected: mocks couple tests
  to the vendor's call shape, so a provider change breaks every test rather than
  one adapter.
