# Roblox Game Architect

An open source AI system that designs, builds, tests and improves Roblox games.

> **Status: pre-alpha — scaffolding only.**
> There is no working engine yet. This repository currently holds the project
> structure, the architecture decisions and the contribution rules. Nothing in
> `packages/` or `apps/` is implemented. See [the roadmap](#roadmap).

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
  [`docs/safety.md`](docs/safety.md) — a design that is written down and not yet
  built.
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

Only the first row is needed today — the rest are what the planned surfaces
will need, listed so you know what is coming.

| Tool | Version | Needed for | Needed now? |
|---|---|---|---|
| Python | 3.11+ | tooling and the test suite | **yes** |
| uv | 0.9+ | dependency management ([CONTRIBUTING](CONTRIBUTING.md)) | **yes** |
| rokit | 1+ | installs the Luau toolchain | when `apps/studio-plugin` exists |
| Roblox Studio | current | running the plugin | when `apps/studio-plugin` exists |
| Node.js | 20+ | `apps/web` | when `apps/web` exists |

## Getting started

What works today is the repository's own toolchain. There is no engine to run.

```bash
git clone https://github.com/cesarsegura-eng/roblox-game-architect.git
```

```bash
cd roblox-game-architect && cp .env.example .env
```

```bash
uv sync --locked --extra dev && uv run pytest
```

That runs the scaffolding checks in `tests/test_scaffolding.py` — line endings,
`.gitattributes`, and that `LLM_PROVIDER=fake` is in effect. They verify the
repository, not a game.

`LLM_PROVIDER=fake` is the default, and the engine **will** be built so that it
runs deterministically and at zero cost in that mode (invariant I7). Neither the
engine nor a provider adapter exists yet, so setting a real key in `.env` does
nothing for now.

Per-package setup instructions live in each package's own README. They will tell
you honestly that there is nothing to run yet.

## Roadmap

Three states, used strictly. **Written** means it exists in the repository and
has been checked locally. **Verified** means CI has proved it. **Planned** means
it does not exist. Nothing here claims working software yet.

| Stage | Scope | State |
|---|---|---|
| 0 | Architecture decisions, safety model | written (documents only) |
| 1 | Repository hygiene, CI, governance | written; checks pass locally, CI itself has **never run** |
| 2 | `packages/protocol` — first versioned schema | next |
| 3 | `packages/core` — LLM interface + `fake` provider | planned |
| 4 | First vertical slice: generate → validate → run → report | planned |
| 5 | Studio plugin as a thin client | planned |
| 6 | Web application | planned |
| 7 | Agent evaluation suite with fixed cases | planned |

Stage 1 moves to "verified" after the first green CI run on `main`, and not
before. Everything described in [`docs/safety.md`](docs/safety.md) is stage 4 or
later: the safety model is designed, not enforced.

## Contributing

Contributions are welcome. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md); it
covers the development setup, the code style and what a reviewable PR looks like
in a project where part of the code is written by a model.

Security issues go through [`SECURITY.md`](SECURITY.md), not public issues.

## License

[MIT](LICENSE).
