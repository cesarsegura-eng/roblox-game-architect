# packages/core — the engine

The planning, generation, validation and review loop. This is the part of the
system that actually designs, builds, tests and improves a game.

**Status: partially implemented.** Existing pieces include the LLM foundation (the
`llm/` package: provider interface, request/response types, trusted/untrusted
framing, a deterministic fake provider, and a registry that picks the provider
from `LLM_PROVIDER`, defaulting to `fake`), the iteration and spend guards in
`budget.py`, `agent_loop.py`, and the worldbuilding and game-planning tools. The
planner produces strict descriptive Game Plan v2 JSON with a player loop, staged
systems, a bounded playable-slice mode, validated data-only gameplay rules, a
map handoff, milestones, and validation goals; it migrates legacy v1 plans to a
script-free blockout slice. The plan's rule DSL can configure the existing fixed
server interpreter; it does not produce Luau. The Luau loop generates source and passes it
to an injected static policy validator, feeds validation failures back as
untrusted data, and retries under both budgets. The sandbox provides a
restricted source validator for scoped scene blockouts; the Luau loop does not apply or execute
code, and general gameplay source remains outside the policy.
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
llm/        the LLMProvider interface, fake and Anthropic adapters, registry
budget.py   IterationBudget (AGENT_MAX_ITERATIONS) and SpendBudget /
            BudgetedLLMProvider (AGENT_MAX_USD_PER_SESSION)
agent_loop.py   bounded Luau generate/validate/retry loop
game_planning.py budgeted, schema-validated descriptive game planning
worldbuilding.py skill-guided Scene Recipe v3 generation for Blender and Roblox
studio_building.py bounded declarative Roblox map blockouts; injected sandbox policy validation
scene_to_studio.py deterministic, bounded Blender-recipe to Roblox Part proxies
skills.py   loader for version-controlled project skill packs
asset_approval.py short-lived, exact-digest HMAC approval shared by API and MCP
skillpacks/ game design planning, biomes and playable spaces, Blender authoring,
            Roblox Studio blockouts, character modeling and animation
schemas/    JSON contracts for game plans and Blender scene recipes
tests/      core unit tests, skill and recipe contract tests, and fixed evaluations
```

Planned, **not yet present**:

```
agents/     multi-agent planning, build, test, and review orchestration
domain/     domain models (GameSpec, Task, RunState, ...)
codegen/    Luau generation (validation belongs to packages/sandbox)
```

`agent_loop.py` is the first orchestration slice: it accepts a user task and
untrusted project context, invokes the builder, then requires an injected
`StaticValidator`. It returns source only after that validator passes. The
syntax parser alone is not such a validator; only the separate sandbox
source-policy implementation can return a source-policy verdict.

For the current scene-blockout subset, inject
`sandbox.source_policy.LuauSourcePolicyValidator` into `AgentLoop` and declare
the allowed root, for example `Workspace/Town/**`. A passing `BuildRunResult`
contains validated source for review; it does not authorize Studio application
or execution. The local API exposes this as `/v1/operator/code-preview` only
when the pinned Lute 1.0.0 parser is available, and quotes the same initial
generation request before use. Failed candidates are never returned as source.

`WorldDesignAgent` uses the selected built-in skill packs and strict Scene
Recipe v3 JSON contract to produce a bounded Blender blockout with simple
materials, lighting, primitives, low-poly meshes, optional generic humanoid
rigs with WALK, RUN, JUMP, or IDLE motion presets, and bounded global Roblox
Lighting, Atmosphere, and optional cloud settings. The recipe is data only; the
Blender extension or remote Blender MCP service builds geometry and exports GLB
artifacts, while the script-free Roblox place builder applies global environment
settings to a downloadable `.rbxlx`. See
[`apps/blender-addon`](../../apps/blender-addon/README.md).
Character modeling and movement guidance is added when the brief names a
character, creature, rig, anatomy, or movement task; English and Spanish
singular and plural forms are recognized so requests such as “personajes” or
“animaciones” load the dedicated character skillpack.

When a brief explicitly asks for a route, trail, path, road, or boardwalk, the
generation loop also requires at least one object with the `path` role. A missing
role is returned as bounded validation feedback and consumes the existing retry
and spend budgets. When a recipe uses multiple `path` objects, their rotated
axis-aligned bounds must form one connected group with no more than one Blender
unit between segments; disconnected pieces trigger the same bounded repair loop.
This is a blockout-level proximity check, not mesh-intersection analysis or proof
that the route is traversable in Roblox Studio.

House and building briefs also map requested features to semantic roles. A basic
building request expects exterior massing, an entry, and a roof; explicit
interior-only wording keeps those defaults out. Interior and exterior roles may
share a footprint or overlap as a room can sit inside an enclosing shell; each
requested role must be represented by its own tagged scene objects. These checks
validate recipe structure, not room clearance, collisions, or in-engine navigation.
When a brief requests connected building transitions, the generation loop also
checks entry, courtyard, interior, opening, roof, and exterior proximity, then
returns disconnected layouts as bounded repair feedback. These are AABB checks,
not mesh-intersection analysis.

`StudioBlockoutAgent` generates a constrained `edit.action` with a new Workspace
root, up to fourteen anchored Parts, and allowlisted size, position, color, material,
and collision properties. It checks that explicitly requested routes and building
features are represented in Part names, and that a named route has a flat elongated
footprint. Those are structural checks, not navigation or collision simulations.
It receives the sandbox action validator by injection;
the API queues its result unapproved. The operator then reviews and approves it,
and the Studio plugin presents its own final Apply/Reject choice. Current Studio
geometry is axis-aligned primitive blockout only; Blender remains the route for
meshes, rigging, and richer scene authoring.

`scene_to_studio.py` can also derive up to fourteen axis-aligned Part proxies
from an already reviewed, validated Scene Recipe. It maps Blender's Z-up
coordinates to Roblox's Y-up coordinates, names the object role, and converts
each eligible mesh or primitive to a bounded box. It skips out-of-bounds scene
objects and omits lights and character rigs. The API queues this deterministic
action using the browser's stable request ID; it is still unapproved until the
operator reviews it, and the Studio plugin still requires local Apply.

`roblox_place.py` compiles a complete `.rbxlx` place from the same validated
Scene Recipe through the pinned Rojo CLI. The default `blockout` mode is
script-free. An explicitly selected `treasure_hunt` mode requires `collectible`
objects and a `path`, adds a neutral Roblox `SpawnLocation` above the first
path segment, and adds the repository-owned fixed server script. The `obby`
mode requires at least two connected `path` segments; it adds sequential
checkpoint/respawn pads, stage and session-win stats, and its own fixed server
script. Both modes support optional, role-tagged lethal touch hazards using
server-owned logic. `rule_game` adds a generic, bounded touch-rule format for
awarding points, healing, nonlethal hazard damage, wins at landmarks, or lethal
hazard effects interpreted by one exact
repository-owned Script. Its rules are validated data; no mode accepts
model-authored Luau. Obby progression is session only and these modes do not
save data. Collectible proxies are
noncollidable and explicitly keep touch
detection enabled for the fixed server handler. Primitive Parts preserve
the Blender Z-up to Roblox Y-up transform; custom meshes and unsupported
primitives are represented by oriented bounds. Roblox lights map to point,
spot, or surface lights; sun lights and character rigs are explicitly reported
as omitted. The remote Roblox MCP exposes this as a downloadable artifact and
does not publish it. A place file is a complete DataModel, so it cannot be
merged into an existing place through this route.

## Fixed world-design evaluations

`tools/evaluate_worldbuilding.py` runs eight reviewed cases for rainforest
trail, checkpoint Obby, collect-and-win routes, alpine inn, desert courtyard
home, coastal wetland, mangrove stilt house, and a character walk/run/jump set.
The collect-and-win case reuses the gameplay recipe and checks minimum counts
for coins, hazards, and landmarks plus their proximity to a connected route. It uses
the configured LLM provider and the normal iteration and spend guards. With
`LLM_PROVIDER=fake`, reviewed recipe fixtures exercise generation parsing and
the structural rubric deterministically; this mode does not evaluate model
quality. Run one
case with `python tools/evaluate_worldbuilding.py --case coastal-wetland` or all
cases without `--case`. Set provider and budget configuration in the process
environment first; this utility does not load `.env` files. The JSON report
includes each recipe and checks required
skills, scene roles, object/light minimums, required light types, and required
light proximity: the courtyard home needs daylight plus an area light within six
Blender units of its interior role. It checks that the entry, courtyard,
interior, opening, and roof roles remain near their connected spaces; these are
axis-aligned object-volume gap checks, not exact rotated-mesh clearance or
walkable-mesh tests. It
also checks requested motion presets.
The rainforest and wetland routes need at least one path object with a 2:1
horizontal aspect ratio so a feature named `path` alone cannot pass. The alpine
route also requires three path objects whose axis-aligned bounds form one
connected group, with at most one Blender unit between segments.
This is a structural smoke rubric only: it does not claim visual quality, gameplay
readability, cultural accuracy, Roblox runtime compatibility, or production
asset quality. Inspect recipes and imported scenes separately.

The Studio blockout agent is budgeted, bounded, and covered by the same injected
sandbox policy used by API queueing. Its loop does not generate Luau or invoke
Roblox APIs directly.

Additional vendor adapters for `llm/` are planned.

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
  guard mechanisms are integrated into the builder and world design loops:
  - **Implemented — iteration guard.** `IterationBudget` (`budget.py`) takes a
    positive `int` limit (bools and non-ints are rejected). `consume()` allows
    exactly `limit` calls and raises `IterationLimitExceededError` before
    exceeding it; `consumed`, `remaining` and `limit` are observable.
    `IterationBudget.from_env()` reads `AGENT_MAX_ITERATIONS`, defaulting to 10
    only when the variable is absent. A present but empty, blank or invalid
    value raises `InvalidIterationLimitError` (fail closed). `AgentLoop`
    consumes one iteration before every model call and stops at the limit.
  - **Implemented — spend cap.** `SpendBudget` and
    `BudgetedLLMProvider` (`budget.py`) implement the
    `AGENT_MAX_USD_PER_SESSION` cap (`SpendBudget.from_env()`, default 1.00 USD
    only when the variable is absent; invalid values raise). A paid call is
    admitted only if the provider returns a maximum-cost quote that fits in
    `limit - spent - reserved`; the check and the hold happen under one lock.
    Settlement is exact `Decimal` arithmetic that fails closed, is atomic (if
    it cannot be computed the reservation stays held, never released uncounted)
    and can happen only once per reservation. A failed call is charged its full
    quote. `AgentLoop` and `WorldDesignAgent` wrap the provider with this guard.
    Anthropic is the first real adapter; unsupported models fail closed. The guarantee is only as strong as the adapter's promise: the cap
    holds if each adapter's quote is a true upper bound on what the vendor will
    charge and its reported `usage.cost_usd` is the real cost. A provider that
    under-quotes or under-reports can overspend; an overcharge is recorded and
    raises `ProviderQuoteViolation`, which blocks further calls only after the
    fact.
- Project content the agent reads is untrusted data and enters the model through
  a separate, labelled channel — never as instructions (invariant I3,
  [`docs/safety.md`](../../docs/safety.md)).
