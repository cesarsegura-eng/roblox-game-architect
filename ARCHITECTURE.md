# Architecture

This document describes the intended shape of Roblox Game Architect and the
invariants that shape it. **None of it is implemented yet** — it is the
agreement we are building against, written down before the first line of engine
code so that the expensive decisions are made deliberately.

Individual decisions and their rationale are in
[`docs/architecture/adr/`](docs/architecture/adr/). This document is the map;
the ADRs are the reasoning.

## 1. The problem shape

The system must design, build, test and improve Roblox games with a high degree
of autonomy, through two very different surfaces: a web application and a Roblox
Studio plugin. That gives us three hard constraints from the start:

1. **Two languages, one contract.** The plugin is Luau; the engine is Python.
   Every message crossing that line is an integration risk.
2. **The agent writes and runs code.** That is the product, and it is also the
   single largest security surface. It needs an explicit boundary, not an
   afterthought.
3. **The engine is the hardest part to test.** LLM calls are non-deterministic
   and cost money. If testing the engine requires a server and a paid API key,
   it will not be tested.

Everything below follows from those three.

## 2. Component layout

```
                    ┌──────────────────┐
                    │     apps/web     │  browser UI: describe, review, approve
                    └────────┬─────────┘
                             │ HTTP
                    ┌────────▼─────────┐
                    │  packages/api    │  HTTP, auth, sessions, orchestration
                    └────────┬─────────┘
                             │ imports
            ┌────────────────▼─────────────────┐
            │         packages/core            │  planner, builder, tester,
            │  no web framework imports ever   │  reviewer, codegen, domain
            └───┬──────────────────────────┬───┘
                │ imports                  │ imports
    ┌───────────▼──────────┐   ┌───────────▼──────────┐
    │  packages/sandbox    │   │  packages/protocol   │
    │  execution boundary  │   │  the shared contract │
    └──────────────────────┘   └───────────┬──────────┘
                                           │ generates / validates
                             ┌─────────────▼─────────────┐
                             │  apps/studio-plugin       │  thin Luau client
                             │  applies, playtests,      │
                             │  reports                  │
                             └───────────────────────────┘
```

### `packages/core` — the engine

The planning, generation, validation and review loop. Agents as separate,
testable units: a **planner** that turns a request into tasks, a **builder**
that produces Luau, a **tester** that decides what to verify, and a
**reviewer** that reads results and decides the next iteration.

Its defining constraint: **no web framework dependency**. The engine must be
importable from a plain script and from CI. That single rule is what makes the
hardest component in the system testable and reproducible, and what lets a
contributor run a generation without deploying anything
([ADR-0001](docs/architecture/adr/0001-monorepo-layout.md)).

### `packages/api` — the service

HTTP endpoints, authentication, session state, persistence, and orchestration of
long-running agent runs. It owns all credentials. It is the only component that
talks to an LLM provider over the network
([ADR-0005](docs/architecture/adr/0005-credentials-and-thin-plugin.md)).

### `packages/protocol` — the contract

Versioned JSON Schema definitions for every message that crosses the
Python/Luau boundary: edit actions, test reports, project state, approval
requests. This is a package rather than a folder because a contract between two
languages needs an owner and a version
([ADR-0006](docs/architecture/adr/0006-protocol-single-source-of-truth.md)).

### `packages/sandbox` — the boundary

Static validation of generated Luau against an allowlist of permitted APIs, and
controlled execution in a disposable place. It is a package of its own so that
the security boundary has a name in the file tree: a boundary nobody can point
at is a boundary nobody reviews
([ADR-0002](docs/architecture/adr/0002-execution-boundary-and-autonomy.md)).

**This package is the single authority on validation.** No other component
validates generated code, not even partially: `packages/core` calls into it and
treats its verdict as final. A boundary with two owners has none — if `core`
also pre-validated, someone would eventually treat the real gate as optional.

### `apps/studio-plugin` — the thin client

Applies approved changes, runs playtests, reports results. It holds no
decision logic, no prompts and no credentials. It is the most privileged
component in the system — a Studio plugin can do nearly anything in the user's
session — and therefore the one that must be able to do the least thinking.

### `apps/web` — the user surface

Where the user describes the game, watches the run, and approves or rejects what
the agent proposes.

## 3. Invariants

These are not preferences. A change that breaks one of them is a breaking
change and needs an ADR that supersedes the relevant decision.

**None of them is enforced by code yet** — I7 is the only one with any
automated check behind it today (`tests/test_scaffolding.py` asserts the fake
provider is in effect). Read the table as the contract the implementation must
satisfy, not as a description of current behaviour.

| # | Invariant | Why |
|---|---|---|
| I1 | `packages/core` imports no web framework | keeps the engine runnable from a script and from CI |
| I2 | Generated code is statically validated before it runs | the agent's output is untrusted input to the system |
| I3 | Project content the agent reads is data, never instructions | prompt injection through script text and instance names is a real escalation path |
| I4 | The Studio plugin holds no API keys and no prompts | a plugin is not a safe place for a secret |
| I5 | Publishing to Roblox is always a human action | platform policy and blast radius |
| I6 | Every autonomous run has an iteration cap and a spend cap | an unbounded improve loop bills in real money |
| I7 | The test suite passes with `LLM_PROVIDER=fake` | otherwise the project is untestable by contributors |
| I8 | Generated projects live outside the repository | generated artefacts in the source tree destroy the ability to audit what a human wrote |

## 4. Data flow of one iteration

```
user request
  → planner            produces tasks            (core)
  → builder            produces Luau             (core)
  → validator          allowlist + static checks (sandbox)   ── fails → back to builder
  → approval gate      human confirms            (api → web)  ── rejects → stop
  → plugin applies     edits in Studio           (studio-plugin)
  → playtest           runs, collects output     (studio-plugin → sandbox)
  → reviewer           reads results, decides    (core)
  → iterate or stop    bounded by I6
```

The approval gate's position is a decision, not an accident: it sits after
validation and before anything touches the user's place. Its default strictness
is set in [ADR-0002](docs/architecture/adr/0002-execution-boundary-and-autonomy.md).

## 5. Testing strategy

- **Unit tests** next to their code, in `packages/<name>/tests/`. Tests placed
  beside the code get maintained, because they are visible while editing it.
- **Integration and end-to-end tests** in `tests/`, covering the protocol
  boundary and the full iteration loop.
- **An evaluation suite** with fixed cases, so that a change to a prompt or an
  agent can be shown to improve or regress behaviour. Without this, nobody —
  maintainer or contributor — can review an engine change on evidence.

All of it runs against the `fake` provider by default (I7, and
[ADR-0003](docs/architecture/adr/0003-llm-provider-abstraction.md)).

## 6. What is deliberately not decided yet

Named here so they are not mistaken for oversights:

- The web framework for `apps/web`.
- The persistence engine behind `DATA_DIR`.
- Multi-user and hosted deployment. The current design assumes a local,
  single-user service.

The transport used to be on this list as "long-poll vs WebSocket". It is not an
open question: Luau has no WebSocket client and a plugin cannot accept inbound
connections, so the channel is plugin-initiated HTTP with long-polling for
results. See [ADR-0007](docs/architecture/adr/0007-plugin-initiated-http-transport.md).

Two decisions that look open but are on the critical path, and should be settled
in stage 2 rather than drifting:

- **The shape of `edit.action`** (flat operation list vs instance tree). It
  determines how precisely the blast-radius check can be expressed, so it is a
  safety decision, not an ergonomic one.
- **How the Luau side validates messages**, given that Luau has no mature JSON
  Schema validator. Without an answer, ADR-0006's "both sides validate" is not
  real.
