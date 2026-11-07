# Roblox Game Architect

An open source AI system that designs, builds, tests and improves Roblox games
through separately hosted MCP services. Blender and the build tooling are
server-side capabilities; the user needs only Roblox Studio, where the game is
made, and no other program.

> **Status: pre-alpha. It does not yet build a game end to end.**
>
> What exists today:
>
> - the Python/Luau protocol (v1) and an API that serves the Studio plugin channel;
> - game-planning, world-design and Studio-blockout agents, with a fake and an
>   optional Anthropic provider, and spend and iteration guards;
> - a static Luau gate for scoped, script-free scene blockouts, built on the
>   pinned official Lute 1.0.0 parser;
> - separately hosted Blender and Roblox MCP services that turn reviewed recipes
>   into GLB and place files, plus a local operator panel and a Studio plugin
>   that applies reviewed, script-free actions.
>
> What does not exist yet: execution of model-written gameplay Luau (it stays
> blocked), evidence from an isolated runtime, and a verified live end-to-end
> playtest. The remote services have been tested locally, not against live
> infrastructure.
>
> The end user needs **Roblox Studio**, where the game is made, and no other
> program. See [the status page](docs/status.md), [the roadmap](#roadmap) and the
> [runbook that turns written into verified](docs/runbook-live-verification.md).

## What it is meant to do

The primary product is a set of dedicated skills and remote MCP tools for the
user's existing agent. That agent plans the game and calls separately hosted
Blender and Roblox services to build scene assets, place artifacts, and fixed-
harness map checks. No authoring software or RGA MCP host is required on the
user's computer. The local web operator panel, Studio plugin, and Blender
extension are optional development, compatibility, and inspection paths.

The core also contains early planning, world generation, and constrained Luau
validation components. General model-authored gameplay execution and a full
end-to-end playtest loop are not implemented. Place builds can select
repository-owned templates or bounded data-only touch rules interpreted by one
fixed server script; arbitrary generated code remains unsupported.

The repository also provides six portable agent skills in [`skills/`](skills/):
one end-to-end Roblox Game Architect skill and dedicated skills for game design,
biome/world design, Blender scene authoring, Roblox map blockouts, and character
modeling/animation. They give an existing agent domain knowledge and route it to
the separately hosted MCP tools. See the
[Codex agent and remote MCP setup](docs/integrations/roblox-game-architect-codex.md).
The skills also package for other skill-compatible agents; see the
[agent-neutral skill distribution guide](docs/integrations/agent-skills.md).
Installing those skill instructions does not install Blender or an MCP server
on the user's computer. The user does need Roblox Studio, because that is where
the game is made and played; nothing else should be required.

## The user's path

The intended path needs one program on the user's computer, Roblox Studio:

1. Install Roblox Studio (the user already has it if they make Roblox games).
2. Give your agent the project's skills and connect it to the hosted MCP
   services; no local server is involved.
3. Ask the agent for a game. It plans, builds through the remote tools, and
   returns a reviewable place file (`.rbxlx`) with its SHA-256 digest.
4. Open that file in Roblox Studio to inspect, edit and play it.

Steps 2 and 3 are written and tested against local stand-ins, not against live
hosted services; see [the status page](docs/status.md). The Studio plugin and
the local operator panel are optional compatibility paths, not part of this path.

## What it is explicitly not

- It does **not** publish to production. An optional publisher can update only
  a configured disposable test place after the user inspects and explicitly
  approves the exact artifact; production targets are denied.
- Model-authored Luau is not executed. Fixed repository-owned template scripts
  may be included only through their explicitly selected, validated modes.
  General gameplay code still needs a static policy and isolated runtime gate;
  see [`docs/safety.md`](docs/safety.md).
- It does **not** hold your Roblox credentials. The plugin uses the API only in
  the optional local Studio compatibility workflow. In the remote agent
  workflow, service credentials stay on the separately hosted MCP/API services;
  end users do not need a local API process.

## Architecture at a glance

```text
existing agent + portable skills
            │ authenticated Streamable HTTP
            ├── remote Blender MCP ── Blender worker ── GLB artifacts
            └── remote Roblox MCP ─── build / validate ── place artifacts
                         │
                         └── hosted RGA API (optional orchestration/review)

optional contributor tools: local operator UI, Studio plugin, Blender extension
```

`packages/core` has no web dependencies, so the engine can be driven from a
script or from CI without a server. `packages/protocol` is the single source of
truth for every message crossing the Python/Luau boundary.

Read [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full picture and
[`docs/architecture/adr/`](docs/architecture/adr/) for why each decision was made.

To host both MCP services on a separate Linux server behind one HTTPS reverse
proxy, follow the [remote Compose deployment guide](apps/remote/deploy/README.md).
That server-side setup is infrastructure for the agent connection; it does not
add a Blender, Roblox Studio, or RGA service installation to the user's PC.

## Development and service requirements

These are requirements for contributors and the separately hosted services, not
for the end user. The end user needs Roblox Studio and nothing else: the product
must not ask them to install Blender, a converter, a local server or any other
program. Python and uv are all the standard test suite needs; the
other rows apply only to the service or optional development workflow.

| Tool | Version | Needed for | Needed now? |
|---|---|---|---|
| Python | 3.11+ | tooling and the test suite | **yes** |
| uv | 0.9+ | dependency management ([CONTRIBUTING](CONTRIBUTING.md)) | **yes** |
| rokit | 1+ | installs the pinned Lute 1.0.0 and the Luau toolchain | **contributors only**: the real-Lute integration test, or building the plugin as a model or a local `.rbxlx`. Not for end users: the plugin installs as one file |
| Blender | 5.2.3 on the MCP host | builds reviewed scene recipes and exports GLB through the remote Blender service | **no local install**; server deployment only. Local extension authoring is optional |
| Roblox Studio | current | **end user**: where the game is made and played; opens the generated place file; hosts the optional RGA plugin | **yes, for the end user** (the only program they install); not needed to run the test suite |
| Node.js | 20+ | optional future web build tooling | no, the local operator panel is served by Python |

## Contributor setup (not required for end users)

The repository includes a runnable operator API and separately deployable
Blender and Roblox MCP services. In the intended user workflow, the user's
computer needs no 3D or game-authoring application: the API connects to the
remote services, which hold and run those tools. The Studio plugin and Blender
extension are optional compatibility and development tools. Roblox Studio may
be used to inspect an artifact, but it is not the remote execution backend. The
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
for the remote Blender and Roblox MCP services and the optional local Studio
plugin. The Roblox Studio MCP server itself uses local `stdio`; it is not the
project's remote MCP route. No remote service credentials or Roblox test place
are configured in this checkout.

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
| 2 | `packages/protocol` — versioned schema | written; Python tests pass; Luau conformance not verified |
| 3 | `packages/core` — LLM foundation, agents, run guards | in progress |
| 4 | First vertical slice: generate → validate → run → report | in progress; generated source stays blocked; no live runtime evidence |
| 5 | 3D authoring and Studio clients | in progress; remote services tested locally only |
| 6 | Web application (local operator panel) | in progress |
| 7 | Agent evaluation suite with fixed cases | in progress; offline cases only |
| 8 | Existing-agent delivery: domain skills + remote MCP tools | in progress; no live hosted connection verified |

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
