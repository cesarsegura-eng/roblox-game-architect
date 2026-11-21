# Roblox Game Architect

An open source AI system that designs, builds, tests and improves Roblox games
by equipping the user's existing agent with domain skills and remote Blender
authoring tools. Roblox Studio work uses the native MCP connection the user
already has configured; a separate RGA Roblox artifact service is optional.

> **Status: pre-alpha. It does not yet build a game end to end.**
>
> What exists today:
>
> - the Python/Luau protocol (v1) and an API that serves the Studio plugin channel;
> - game-planning, world-design and Studio-blockout agents, with a fake and an
>   optional Anthropic provider, and spend and iteration guards;
> - a static Luau gate for scoped, script-free scene blockouts, built on the
>   pinned official Lute 1.0.0 parser;
> - a separately hosted Blender MCP service that turns reviewed recipes into
>   GLB assets, plus an optional RGA Roblox artifact service for deployments
>   that already expose it; neither replaces the user's native Studio MCP.
>
> What does not exist yet: general model-written gameplay execution in RGA's
> own service path (it stays blocked), verification against a separately
> published Open Cloud test universe, and a verified live end-to-end playtest.
> Local unpublished `.rbxlx` files can be tested in Studio without that cloud
> universe; a local one-player Studio Play Solo check has
> verified the fixed rainforest rules script and the Obby checkpoint, finish,
> hazard, respawn, and four-leg PathfindingService route; these do not establish
> manual walking/control playability, live-service behavior, or production
> readiness. Remote services have been tested locally, not against live
> infrastructure.
>
> The user needs an existing compatible agent to use RGA skills, remote Blender
> MCP, and the existing Roblox Studio MCP. No RGA-specific software is required
> on the user's computer. See [the status page](docs/status.md), [the roadmap](#roadmap) and the
> [runbook that turns written into verified](docs/runbook-live-verification.md).

## What it is meant to do

The primary product is dedicated skills plus remote Blender authoring tools for
the user's existing agent. Direct Roblox creation and editing use the Roblox
Studio session and native MCP the user already has configured; the Claude Code
plugin does not add a second Roblox MCP connection. A separate RGA Roblox
service can build recipe artifacts and run fixed checks for compatible agent
deployments that already expose it. The workflow adds no local Blender install,
RGA MCP host, or RGA Studio plugin on the user's computer. The local web
operator panel and Blender extension are optional development paths.

The core also contains early planning, world generation, and constrained Luau
validation components. General model-authored gameplay execution and a full
end-to-end playtest loop are not implemented. Place builds can select
repository-owned templates or bounded data-only touch rules interpreted by one
fixed server script; arbitrary generated code remains unsupported.

The repository also provides nine portable agent skills in [`skills/`](skills/):
one end-to-end Roblox Game Architect skill and dedicated skills for game design,
server gameplay engineering, UI/UX, biome/world design, native Roblox Terrain,
Blender scene authoring, Roblox map blockouts, and character modeling/animation.
They give an existing agent domain knowledge and route it to the user's already
available tools. See the
[Codex agent and remote MCP setup](docs/integrations/roblox-game-architect-codex.md).
The skills also package for other skill-compatible agents; see the
[agent-neutral skill distribution guide](docs/integrations/agent-skills.md).
For Claude Code, the [integration guide](docs/integrations/claude-code.md)
adds remote Blender authoring and uses the existing native Studio connection
for Roblox work; it does not add another Roblox MCP endpoint. Installing those
skill instructions does not install Blender or an MCP server on the user's
computer. Studio is used directly through the user's existing native tools.

## The user's path

The intended Claude Code path uses the agent's existing tools plus remote
Blender authoring:

1. Give the agent the project skills and configure the RGA Blender MCP; leave
   the native Roblox Studio MCP unchanged.
2. Ask for a game. The agent plans, creates 3D assets remotely, and uses the
   native Studio tools for supported work in the open place.
3. The separate RGA Roblox artifact service is optional and is not configured
   by the Claude plugin.

No Blender, RGA plugin, RGA application, or local RGA service is required on
the user's computer. Direct Studio work depends on the user's existing Studio
setup and the tools it exposes.

The combined remote Blender and native Studio workflow has not yet been
verified end to end against hosted services; see [the status page](docs/status.md).
The optional RGA Studio plugin and local operator panel are compatibility
paths, not part of this path.

## What it is explicitly not

- It does **not** publish to production. An optional publisher can update only
  a configured disposable test place after the user inspects and explicitly
  approves the exact artifact; production targets are denied.
- RGA's remote builder does not execute model-authored Luau. Fixed
  repository-owned template scripts may be included only through their
  explicitly selected, validated modes. The user's native Studio MCP may
  support direct script edits and execution in the open place, outside RGA's
  sandbox; verify the target and use its test safeguards. General gameplay code
  in RGA still needs a static policy and isolated runtime gate; see
  [`docs/safety.md`](docs/safety.md).
- It does **not** hold your Roblox credentials. The optional RGA Studio plugin
  uses the API only in the local Studio compatibility workflow. The Claude Code
  plugin adds RGA skills and the remote Blender MCP only; Claude's existing
  native Studio connection remains independently configured. End users do not
  need a local API process.

## Architecture at a glance

```text
existing agent + portable skills
            │ authenticated Streamable HTTP
            ├── remote Blender MCP ── Blender worker ── signed GLB handoff
            │                                               │ model data only
            └── existing native Roblox Studio MCP ──────────┴─ user's open place

optional separate service: RGA Roblox MCP ── recipe artifacts / fixed checks

optional contributor tools: local operator UI, Studio plugin, Blender extension
```

`packages/core` has no web dependencies, so the engine can be driven from a
script or from CI without a server. `packages/protocol` is the single source of
truth for every message crossing the Python/Luau boundary.

Read [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full picture and
[`docs/architecture/adr/`](docs/architecture/adr/) for why each decision was made.

For the intended Claude workflow, configure the hosted Blender MCP and keep the
user's native Roblox Studio MCP unchanged. If a compatible agent deployment
already exposes the optional RGA Roblox artifact service, it can be hosted
alongside Blender using the [remote Compose deployment guide](apps/remote/deploy/README.md).
That server-side setup does not install Blender, Roblox Studio, or an RGA
service on the user's PC.

## Development and service requirements

These are requirements for contributors and the separately hosted services, not
for the end user. The end user uses an agent they already run; Studio is needed
only to inspect, edit, or play an artifact locally. The product must not ask
them to install Blender, a converter, a local server or RGA-specific software.
Python and uv are all the standard test suite needs; the
other rows apply only to the service or optional development workflow.

| Tool | Version | Needed for | Needed now? |
|---|---|---|---|
| Python | 3.11+ | tooling and the test suite | **yes** |
| uv | 0.9+ | dependency management ([CONTRIBUTING](CONTRIBUTING.md)) | **yes** |
| rokit | 1+ | installs the pinned Lute 1.0.0 and the Luau toolchain | **contributors only**: the real-Lute integration test, or building the plugin as a model or a local `.rbxlx`. Not for end users: the plugin installs as one file |
| Blender | 5.2.3 on the MCP host | builds reviewed scene recipes and exports GLB through the remote Blender service | **no local install**; server deployment only. Local extension authoring is optional |
| Roblox Studio | current | the user's existing native MCP target for direct place work; can also open generated place files | no RGA plugin or RGA-specific Studio install is required |
| Node.js | 20+ | optional future web build tooling | no, the local operator panel is served by Python |

## Contributor setup (not required for end users)

The repository includes a runnable operator API and separately deployable
Blender and Roblox MCP services. In the intended user workflow, the user's
computer needs no RGA-specific authoring application: Blender runs remotely,
and the agent reuses the user's existing native Studio MCP for direct place
work. The Studio plugin and Blender extension are optional compatibility and
development tools. The native Studio connection is distinct from remote RGA
artifact generation and validation. The
complete game-building engine is not ready: static Luau validation currently
covers only a restricted, script-free scene-construction subset. The bounded
Luau agent loop is available as a quoted, read-only source preview when pinned
Lute 1.0.0 and a real provider are configured. Broader gameplay code, approval
to apply source, isolated execution, and playtesting remain gated.
The operator can also build a complete Roblox `.rbxlx` file on the remote Rojo
MCP host without installing Studio. The default is a script-free map blockout;
Treasure Hunt and Obby Course modes add their fixed scripts after role and route
validation. The `rule_game` mode accepts a validated data-only rule array and
adds one fixed interpreter script. This does not publish or
merge into an existing place, and the remote map harness does not playtest that
script. See
[remote application integration boundaries](docs/integrations/remote-application-architecture.md)
for the remote Blender and Roblox MCP services and the optional RGA Studio
plugin. Claude Code's native Roblox Studio MCP connection is managed separately
from RGA's remotely hosted MCP routes; this project neither creates nor replaces
that connection. No hosted remote-service credentials or published Open Cloud
test place are configured in this checkout. The runbook includes a command to
generate a separate unpublished Studio test file without adding a Roblox MCP
endpoint.

```bash
git clone https://github.com/cesarsegura-eng/roblox-game-architect.git
```

`.env.example` documents future runtime configuration and the budget limits. No
application loads `.env` automatically yet; the current test suite needs no
`.env` file.

```bash
uv sync --locked --extra dev && uv run python -m pytest
```

The suite covers repository hygiene, protocol schemas and examples, fake LLM
flows, policy validation, API and operator routes, and Blender MCP protocol and
artifact handling. Its remote Blender server tests use a fake renderer; the
suite does not call a live LLM, run Blender, or exercise Roblox Studio. Those
runtime checks require their separately configured services.

The standard suite works **without Lute**: the real-parser integration tests are
skipped when `lute` is not on `PATH`. To run them, install the pinned runtime
with rokit and select the integration test:

```bash
rokit install
uv run pytest -m integration packages/sandbox/tests/test_lute_integration.py
```

`LLM_PROVIDER=fake` is the default, and the engine runs deterministically and
at zero cost in that mode (invariant I7). An optional Anthropic adapter can
generate Blender recipes with a preflight spend quote. To enable it, set
`LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, `LLM_MODEL_ID=claude-sonnet-5-5`,
and `AGENT_MAX_USD_PER_SESSION` in the environment used to run the command, then
run `uv run python -m api.world_cli "A misty alpine village with an inn interior" examples/worlds/alpine-inn.json`.
The `.env.example` file is a reference and is not automatically loaded. Recipes
can be sent through the reviewed remote MCP integration described in
[`docs/integrations/blender-remote-mcp.md`](docs/integrations/blender-remote-mcp.md).
The optional local extension can also import a saved recipe, but it is not part
of the remote MCP setup.

Per-package setup instructions live in each package's own README. They say
honestly what exists and what does not.

## Roadmap

Three states, used strictly. **Written** means the implementation or design
exists in the repository. **Verified** means the stated check has passed.
**Planned** means it does not exist. A written remote adapter is not described
as live until its external service and runtime evidence are available.

| Stage | Scope | State |
|---|---|---|
| 0 | Architecture decisions, safety model | written |
| 1 | Repository hygiene, CI, governance | written; this tree has not run in hosted CI |
| 2 | `packages/protocol` — versioned schema | Python and Luau parser/schema vectors pass locally; hosted CI and installed Studio runtime remain unverified |
| 3 | `packages/core` — LLM foundation, agents, run guards | in progress |
| 4 | First vertical slice: generate → validate → run → report | in progress; fixed rainforest gameplay passed a one-player Studio engine-driver check; walking-route, isolated-place, and live end-to-end verification remain |
| 5 | 3D authoring and Studio clients | in progress; a signed Blender artifact handoff supports the existing native Studio Open Cloud upload path; hosted MCP services and live Roblox asset/rendering checks remain |
| 6 | Web application (local operator panel) | in progress |
| 7 | Agent evaluation suite with fixed cases | in progress; offline cases only |
| 8 | Existing-agent delivery: domain skills + remote MCP tools | in progress; portable skills, a Claude Code plugin/marketplace package, and remote Blender authoring with a signed artifact handoff exist; live hosted MCP endpoints are not configured or verified |

The per-stage detail, with every verified and unverified claim, is in
[`docs/status.md`](docs/status.md).

Stage 1 moves to "verified" after the first green CI run on `main`, and not
before. The broader Luau source policy and isolated
execution in [`docs/safety.md`](docs/safety.md) remain incomplete (the sandbox
enforces only a narrow scene-building subset). Trusted/untrusted framing and
iteration/spend guards are implemented. The Luau `AgentLoop` is connected to a
read-only API preview and remains disconnected from Studio execution.

## Contributing

Contributions are welcome. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md); it
covers the development setup, the code style and what a reviewable PR looks like
in a project where part of the code is written by a model.

Security issues go through [`SECURITY.md`](SECURITY.md), not public issues.

## License

[MIT](LICENSE).
