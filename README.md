# Roblox Game Architect

An open source AI system that designs, builds, tests and improves Roblox games.

> **Status: pre-alpha — foundations only.**
> There is no working end-to-end engine yet. The repository has protocol schemas
> and tests, plus early `packages/core` foundations: the `LLMProvider` interface,
> trusted/untrusted request framing, a deterministic `fake` provider, and
> standalone iteration/spend guards. No agent loop uses them; there are no real
> provider adapters and no end-to-end generation, build or playtest.
> `packages/sandbox` contains only a syntax-only bridge using the owner-selected
> official Lute 1.0.0 parser: there is no CST policy analyzer, API allowlist,
> memory bound, complete Gate 1, approval gate, execution isolation or
> disposable-place mechanism. The API, Studio plugin and web application are still
> planned. See [the roadmap](#roadmap).

## What it is meant to do

Roblox Game Architect is a modular, autonomy-capable agent with two surfaces:

- **A web application** — where you describe the game you want, watch the agent
  work, review what it proposes and approve what it changes.
- **A Roblox Studio plugin** — a thin client that applies approved changes
  inside Studio, runs playtests and reports results back.

Between the two sits a provider-agnostic core engine that plans, generates Luau,
validates it, runs it in a disposable place, reads the results and iterates.

## What it is explicitly not

- It does **not** publish games for you. Publishing is always a manual action
  taken by a human.
- It will **not** run generated code without a boundary. Everything the agent
  writes is to pass static validation and run under the limits described in
  [`docs/safety.md`](docs/safety.md) — mostly a design that is not yet built.
- It does **not** hold your Roblox credentials. The plugin authenticates against
  your own local API service.

## Architecture at a glance

```
apps/web  ──┐                        ┌── packages/core     planning, codegen, review
            ├── packages/api  ───────┤── packages/sandbox   execution boundary
apps/studio-plugin ──┘               └── packages/protocol  the shared contract
```

`packages/core` has no web dependencies, so the engine can be driven from a
script or from CI without a server. `packages/protocol` is the single source of
truth for every message crossing the Python/Luau boundary.

Read [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full picture and
[`docs/architecture/adr/`](docs/architecture/adr/) for why each decision was made.

## Requirements

Python and uv are all the standard test suite needs. The other rows are what the
planned surfaces will need, listed so you know what is coming; rokit is optional
today, to install the pinned Lute 1.0.0 runtime for the real-parser integration
test described under *Getting started*.

| Tool | Version | Needed for | Needed now? |
|---|---|---|---|
| Python | 3.11+ | tooling and the test suite | **yes** |
| uv | 0.9+ | dependency management ([CONTRIBUTING](CONTRIBUTING.md)) | **yes** |
| rokit | 1+ | installs the pinned Lute 1.0.0 and the Luau toolchain | **optional** now (real-Lute integration test); needed when `apps/studio-plugin` is built |
| Roblox Studio | current | running the plugin | when `apps/studio-plugin` exists |
| Node.js | 20+ | `apps/web` | when `apps/web` exists |

## Getting started

What works today is the repository toolchain, the protocol schemas and tests,
and the tested core foundations. There is no engine to run.

```bash
git clone https://github.com/cesarsegura-eng/roblox-game-architect.git
```

`.env.example` documents future runtime configuration and the budget limits. No
application loads `.env` automatically yet; the current test suite needs no
`.env` file.

```bash
uv sync --locked --extra dev && uv run pytest
```

The suite covers repository hygiene, protocol schemas and examples, the fake LLM
provider and framing, the standalone iteration/spend guard mechanisms, and the
fail-closed handling of the sandbox's syntax-only Lute bridge (against a mocked
process). It does **not** cover Roblox Studio or generation of games: no game is
generated, built or playtested.

The standard suite works **without Lute**: the one test that runs the real parser
is skipped when `lute` is not on `PATH`. To run it, install the pinned runtime
with rokit and select the integration test:

```bash
rokit install
uv run pytest -m integration packages/sandbox/tests/test_lute_integration.py
```

`LLM_PROVIDER=fake` is the default, and the engine **will** be built so that it
runs deterministically and at zero cost in that mode (invariant I7). The fake
provider exists; no real provider adapter does yet, so setting a real key in
`.env` does nothing for now.

Per-package setup instructions live in each package's own README. They say
honestly what exists and what does not.

## Roadmap

Three states, used strictly. **Written** means it exists in the repository and
has been checked locally. **Verified** means CI has proved it. **Planned** means
it does not exist. Nothing here claims working software yet.

| Stage | Scope | State |
|---|---|---|
| 0 | Architecture decisions, safety model | written (documents only) |
| 1 | Repository hygiene, CI, governance | written; checks pass locally, CI itself has **never run** |
| 2 | `packages/protocol` — first versioned schema | written; Python tests pass locally; CI not run on it; **Luau conformance not verified** |
| 3 | `packages/core` — LLM foundation and run guards | in progress; provider/fake, trusted/untrusted framing and iteration/spend mechanisms are implemented; no real adapter or agent loop |
| 4 | First vertical slice: generate → validate → run → report | in progress; the `packages/api` plugin channel runs the whole protocol loop end to end, driven by tests and a stand-in plugin. No agent loop, no LLM call, and no Studio plugin has connected to it |
| 5 | Studio plugin as a thin client | planned |
| 6 | Web application | planned |
| 7 | Agent evaluation suite with fixed cases | planned |

Stage 1 moves to "verified" after the first green CI run on `main`, and not
before. The approval gate, sandbox policy analysis and execution, and Studio
behavior in [`docs/safety.md`](docs/safety.md) remain design (the sandbox has
only its syntax-only Lute bridge); the core framing and run guards are
foundations that the future loop must integrate.

## Contributing

Contributions are welcome. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md); it
covers the development setup, the code style and what a reviewable PR looks like
in a project where part of the code is written by a model.

Security issues go through [`SECURITY.md`](SECURITY.md), not public issues.

## License

[MIT](LICENSE).
