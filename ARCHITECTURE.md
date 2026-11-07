# Architecture

This document describes the intended shape of Roblox Game Architect and the
invariants that shape it. **The product is an agent capability pack backed by
separately hosted tools:** a user equips an existing agent with domain skills,
then connects that agent to authenticated remote MCP services. The end user's
computer needs Roblox Studio, since that is where the game is made, and nothing
else: no Blender, no RGA server, no converters. The RGA plugin and Blender
extension are optional, and opening a generated place file in Studio needs
neither. Local app integrations are optional contributor,
compatibility, and inspection paths. The repository has protocol schemas,
game-planning and world-design agents, budgeted provider interfaces, and
dedicated guidance for biomes, playable maps, interior/exterior architecture,
character modeling, and movement. Fixed remote MCP tools can turn validated
recipes into Blender GLBs and Roblox place files, validate maps with a
repository-owned harness, and offer separately approved asset upload or
test-place publishing. Model-authored Luau execution remains blocked. The
sandbox validates only a restricted script-free scene-construction subset;
production gameplay still needs a broader reviewed policy and isolated runtime
evidence. The optional local web panel, Studio plugin, and Blender extension
support contributors and compatibility checks without becoming user-computer
requirements.

Individual decisions and their rationale are in
[`docs/architecture/adr/`](docs/architecture/adr/). This document is the map;
the ADRs are the reasoning.

## 1. The problem shape

The system must equip an existing agent to design, build, and validate Roblox
games using domain knowledge and remote MCP tools, without requiring the end
user to install target applications. This gives us three hard constraints:

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
existing agent + skills ── authenticated MCP ── separately hosted services
       │                                       ├── Blender worker → GLB assets
       │                                       └── Roblox builder/validator → place artifacts
       └── optional hosted RGA API for orchestration, review, and lifecycle

packages/core + packages/sandbox + packages/protocol provide shared agent
knowledge, validated formats, budgets, and safety policies.

Optional local development paths: apps/web, apps/studio-plugin,
apps/blender-addon. These are not end-user product prerequisites.
```

### `packages/core` — the engine

The planning, generation, validation and review loop. Agents as separate,
testable units: a **planner** that turns a request into tasks, a **builder**
that produces Luau, a **tester** that decides what to verify, and a
**reviewer** that reads results and decides the next iteration.

The current slices include a budget-enforced builder loop and a `WorldDesignAgent`
that loads the built-in world, Blender, and character skill packs to produce a
strict scene-recipe JSON document. The Luau builder has a read-only preview and
a static validator for a narrow scene-construction subset; it does not execute
or apply generated source. Fixed remote MCP build modes can include only
repository-owned gameplay scripts. The optional Studio plugin applies reviewed,
script-free Workspace edits with undo recording.

Its defining constraint: **no web framework dependency**. The engine must be
importable from a plain script and from CI. That single rule is what makes the
hardest component in the system testable and reproducible, and what lets a
contributor run a generation without deploying anything
([ADR-0001](docs/architecture/adr/0001-monorepo-layout.md)).

### `packages/api` — optional orchestration service and MCP client

The plugin channel is implemented on the standard library: the handshake, long-polled
delivery of one approved work item at a time, results, the per-credential lock of
[ADR-0011](docs/architecture/adr/0011-delivery-execution-and-recovery.md) and the
attestation that releases it, with the lifecycle state durable under `DATA_DIR`.
The scoped Luau builder loop is connected to an authenticated, read-only API
preview: it quotes the request, generates source, and returns it only after the
static blockout policy accepts it. It does not apply or execute that source in
Studio. The optional local operator panel covers game-plan and world-recipe
generation, constrained Studio blockout generation, remote MCP checks, artifact
review, and API activity history. Existing agents can call the separately
hosted Blender and Roblox MCP services directly; the RGA API is optional
orchestration, not a user-computer dependency.

HTTP endpoints, authentication, session state, persistence, and orchestration of
long-running agent runs. In a hosted deployment it owns service credentials. It
is the only component that talks to an LLM provider over the network
([ADR-0005](docs/architecture/adr/0005-credentials-and-thin-plugin.md)).

### `packages/protocol` — the contract

Versioned JSON Schema definitions for every message that crosses the
Python/Luau boundary: the handshake, edit actions and their results, project
state and playtest reports. (Messages from the API to the web application —
approval requests and the run log — are not part of v1.) This is a package rather
than a folder because a contract between two languages needs an owner and a
version ([ADR-0006](docs/architecture/adr/0006-protocol-single-source-of-truth.md)).
Version 1.0 is written; see [`docs/protocol/README.md`](docs/protocol/README.md).

### `packages/sandbox` — the boundary

Static validation of generated Luau against an allowlist of permitted APIs, and
controlled execution in a disposable place. It also owns the declarative edit
policy consumed by the API queue. It is a package of its own so that
the security boundary has a name in the file tree: a boundary nobody can point
at is a boundary nobody reviews
([ADR-0002](docs/architecture/adr/0002-execution-boundary-and-autonomy.md)).

**Current status: a script-free declarative subset plus syntax bridge.** The
queue admits scoped non-script creation and allowlisted part properties only;
it rejects source edits, deletion, reparenting and playtests. The package also
contains `LuteSyntaxParser`,
which reports syntax and bounded CST facts, using the official Lute parser pinned
to exactly 1.0.0 ([ADR-0014](docs/architecture/adr/0014-luau-source-analysis-with-lute.md)).
It fails closed and bounds source size, wall time, output and memory where the OS
supports that limit; it refuses to run where the memory limit is unavailable.
The CST policy analyzer and versioned Luau allowlist cover a restricted,
script-free scene-blockout subset; a successful parse alone authorises nothing.
General generated-Luau execution remains blocked. A fixed remote map-validation
harness exists, but no disposable Roblox environment or live isolation evidence
is configured.

**This package is the single authority on validation.** No other component
validates generated code, not even partially: `packages/core` calls into it and
treats its verdict as final. A boundary with two owners has none — if `core`
also pre-validated, someone would eventually treat the real gate as optional.

### `apps/studio-plugin` — optional local compatibility client

Applies approved changes, runs playtests, reports results. It holds no
decision logic, no prompts and no credentials. It is the most privileged
component in the system — a Studio plugin can do nearly anything in the user's
session — and therefore the one that must be able to do the least thinking.

### `apps/blender-addon` — optional local 3D authoring tool

The extension imports Scene Recipe v2 JSON (and existing v1 files) into a
separate Blender collection using allowlisted primitives and bounded
low-poly meshes, materials, and lights. It also creates a generic humanoid rig
blockout with walk, run, jump, and idle action presets. The GLB exporter includes skinning and
active animation data for human review and import in Studio. It executes no
model-generated Python and does not upload or publish assets. Recipe delivery
can use either a local file or the authenticated loopback API endpoint. The
generated skeleton is not an R15 avatar rig.

### `apps/web` — optional operator and review surface

Where an operator can review locally orchestrated work. The agent-first product
flow uses the user's existing agent and its MCP client directly; the panel is
not required.

## 3. Invariants

These are not preferences. A change that breaks one of them is a breaking
change and needs an ADR that supersedes the relevant decision.

These remain architecture goals and are not generally enforced by the product.
I6 has budget mechanisms integrated into the core builder loop; I7 has a
deterministic fake provider and a repository check that verifies it is selected
in tests (`tests/test_scaffolding.py`). Read the table as the contract the
implementation must satisfy, not as a description of end-to-end behaviour.

| # | Invariant | Why |
|---|---|---|
| I1 | `packages/core` imports no web framework | keeps the engine runnable from a script and from CI |
| I2 | Generated code is statically validated before it runs | the agent's output is untrusted input to the system |
| I3 | Project content the agent reads is data, never instructions | prompt injection through script text and instance names is a real escalation path |
| I4 | End-user clients hold no provider or Open Cloud keys | secrets stay on the trusted service that uses them |
| I5 | Publishing requires explicit human approval bound to the exact artifact and a server-pinned disposable test place; production publishing is denied | platform policy and blast radius |
| I6 | Every autonomous run has an iteration cap and a spend cap | an unbounded improve loop bills in real money |
| I7 | The test suite passes with `LLM_PROVIDER=fake` | otherwise the project is untestable by contributors |
| I8 | Generated projects live outside the repository | generated artefacts in the source tree destroy the ability to audit what a human wrote |

## 4. Intended agent-first data flow

```
user asks their existing agent for a Roblox game
  → portable skills guide planning, biomes, architecture, maps, characters
  → agent calls remote Blender MCP to build reviewed scene/character assets
  → agent calls remote Roblox MCP to build a place artifact or validate a map
  → agent presents outputs and validation evidence for human review
  → optional gated asset creation / disposable-place validation after approval
```

This agent-first flow is the intended product and does not require local
authoring applications. Generated Luau execution, broad gameplay playtests, and
production publication are not yet complete. Persistent asset creation and
test-place publication remain separately gated; production publishing is off.
The optional local plugin/API path is described in its own protocol and is not
the primary product flow.

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

- Multi-user and hosted deployment of the optional orchestration API. The
  current API implementation targets a local, single-user service. For that
  deployment, lifecycle records use SQLite
  full-synchronous transactions, as decided in
  [ADR-0016](docs/architecture/adr/0016-sqlite-lifecycle-store.md). The service
  commits `delivered` before sending work and accepted results before
  acknowledging them, as required by
  [ADR-0011](docs/architecture/adr/0011-delivery-execution-and-recovery.md).

The transport used to be on this list as "long-poll vs WebSocket". It is not an
open question: Luau has no WebSocket client and a plugin cannot accept inbound
connections, so the channel is plugin-initiated HTTP with long-polling for
results. See [ADR-0007](docs/architecture/adr/0007-plugin-initiated-http-transport.md).

Two decisions that were on the critical path are settled by stage 2:

- **The shape of `edit.action`** is a flat list of primitive operations, with the
  property allowlist in the schema itself
  ([ADR-0008](docs/architecture/adr/0008-edit-action-flat-operations.md)).
- **How the Luau side validates messages** is a closed subset of JSON Schema and
  one strict JSON profile, with a hand-written Luau parser
  ([ADR-0009](docs/architecture/adr/0009-luau-validation-subset-and-strict-json.md)).
  The Studio plugin's parser and validator are implemented; protocol examples
  and schema behavior are covered by the Python conformance suite. A live Studio
  runtime check is still needed for the Luau implementation.

Still open on the protocol side, and named so they are not mistaken for
oversights: how generated code can run without touching the user's working place
(no protocol operation enables a script, which is not a guarantee that generated
code cannot run; see
[ADR-0010](docs/architecture/adr/0010-script-execution-reach-and-action-semantics.md)),
and whether snapshots can be requested by scope.

Further records track work that crosses package boundaries. ADR-0011's wire
changes, API state machine, durable lock, and recovery records are implemented;
the Studio runtime path still needs testing. ADR-0014's syntax bridge, bounded
CST fact extraction, and scoped blockout source policy exist; general gameplay
policy and live runtime evidence remain open. Other records describe remaining
decisions and verification:
[ADR-0010](docs/architecture/adr/0010-script-execution-reach-and-action-semantics.md)
(script execution reach and action semantics),
[ADR-0011](docs/architecture/adr/0011-delivery-execution-and-recovery.md)
(delivery, execution and recovery),
[ADR-0012](docs/architecture/adr/0012-untrusted-text-and-unicode-rendering.md)
(untrusted text),
[ADR-0013](docs/architecture/adr/0013-conformance-suites.md) (conformance suites)
and
[ADR-0014](docs/architecture/adr/0014-luau-source-analysis-with-lute.md) (the
official Lute parser for Luau source analysis; syntax and bounded CST fact
extraction are implemented, while general gameplay policy and its API allowlist
remain open. Process memory is bounded on Linux and Windows; unsupported
platforms fail closed.)
