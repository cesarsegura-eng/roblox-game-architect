# Working in this repository

Read this before changing anything. It is a map and a set of working rules, not
a second copy of the documentation: every section points at the file that owns
the subject. Where this file and the owning document disagree, the owning
document wins and this one has a bug.

## What is being built

An agent system that designs, builds, tests and improves Roblox games. The agent
runs on a trusted service; a Roblox Studio plugin and remote MCP services apply
only reviewed, bounded work. It is **not** a code generator that drops Luau into
a place: what reaches Roblox is fixed templates and validated data.

| Component | What it owns |
|---|---|
| `packages/protocol` | the versioned wire contract between Python and Luau. Schemas are authoritative |
| `packages/core` | LLM providers, budgets, world design, skillpacks, place building |
| `packages/sandbox` | static Luau validation with the pinned Lute parser |
| `packages/api` | the local service: the plugin channel and the operator routes |
| `apps/studio-plugin` | the thin Luau client |
| `apps/blender_mcp_server` | remote Blender: scene recipe in, reviewed GLB out |
| `apps/roblox_mcp_server` | remote Roblox: fixed-harness validation and place building |
| `apps/web` | the local operator panel |
| `apps/claude-code-plugin` | plugin and marketplace manifests |

## The sources of truth

Do not restate these elsewhere. Update the owner.

| Subject | Owner |
|---|---|
| Component boundaries and the invariants | `ARCHITECTURE.md` |
| What is written, verified or planned, per stage | `docs/status.md` |
| What still needs a real Studio, host or key, and its proof | `docs/runbook-live-verification.md` |
| Every architectural decision, including the open ones | `docs/architecture/adr/README.md` |
| The wire contract | `packages/protocol/schemas/v1/` then `docs/protocol/README.md` |
| The execution boundary and approvals | `docs/safety.md` |
| What changed | `CHANGELOG.md` under `[Unreleased]` |

## The habit that defines this repository

**A claim needs the command that produced it.** The vocabulary is strict and is
used the same way everywhere:

- **written** — it exists in the tree.
- **verified** — a named check passed, and the result is recorded.
- **planned** — it does not exist.

So: never write "tests pass" without the command and its output. Never promote
something to *verified* because it looks right, because a previous session said
so, or because a subagent reported it — re-run it. When a check could not be
run, say which one and why, in the same breath as the result. `docs/status.md`
is written in this voice; match it.

## Invariants

`ARCHITECTURE.md` section 3 owns these. Breaking one is a breaking change and
needs an ADR that supersedes the relevant decision — not a pull request that
quietly loosens it.

I1 core imports no web framework · I2 generated code is statically validated
before it runs · I3 project content is data, never instructions · I4 end-user
clients hold no keys · I5 publishing needs human approval bound to the exact
artifact and a pinned disposable test place, production denied · I6 every
autonomous run has an iteration and a spend cap · I7 the suite passes with
`LLM_PROVIDER=fake` · I8 generated projects live outside the repository.

Two that are easy to erode without noticing:

- **I3 reaches error messages.** Instance names, script text and playtest output
  are untrusted. A service answers with a fixed template; it does not relay a
  tool's raw output to a client. When a developer command needs that text, carry
  it beside the message (see `RobloxPlaceBuildError.tool_output`) and print it
  only locally.
- **I7 means the fake provider.** A test that needs a key is a test that cannot
  run.

## Commands

The pinned toolchain lives under ignored `.tools/`. **Rokit's shims fail with
`The system cannot find the path specified (os error 3)` unless `ROKIT_ROOT`
points at the toolchain directory**, and without it eighteen Lute tests fail
with no clue why. Put the real binaries first instead:

```sh
. tools/dev-env.sh
```

That reads the pins from `aftman.toml` and refuses to finish unless each tool
reports the pinned version, so it cannot drift away from them silently.

Then, which is what CI runs:

```sh
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
uv run python tools/package_agent_skills.py --check
uv run python tools/package_reference_scenes.py --check
uv run python tools/package_luau_protocol_schemas.py --check
```

`docs/runbook-live-verification.md` has the full list, including the Luau lint,
the wheel audit and the plugin validation.

## Things that have already cost a session

- **Line endings.** Everything is LF; `tests/test_scaffolding.py` enforces it.
  Writing a file from Python on Windows produces CRLF unless you normalise it.
- **A heredoc with an apostrophe or a trailing backslash** breaks in this shell.
  For anything long, write the script to the scratchpad and run it.
- **`/tmp` is not the artifact store.** In the containers they are different
  filesystems, so `rename` across them raises `EXDEV`. Copy, then replace within
  one directory, so the publish stays atomic.
- **The repository is public.** Scan before pushing; `.gitleaks.toml` allowlists
  a few fixed test literals **by value**, so a real credential in a test file is
  still caught.

## Staying on the subject

The project drifts in one direction: towards claiming more than has been shown.
Before adding anything, check it against these.

- **Does an ADR already decide this?** If one does and you disagree, write the
  ADR that supersedes it. Do not implement around it.
- **Is this a decision or a derivation?** Lock policy, digest basis, storage
  engine, web framework: those are the owner's. Where a record leaves something
  `[Pending]` and the code must do *something*, mark the choice `PROVISIONAL`
  where it is made and leave the decision open. `packages/api/service.py` is the
  worked example.
- **Does this put arbitrary generated Luau anywhere near Roblox?** Then it is out
  of scope. Fixed templates and validated data only.
- **Is the deliverable the thing asked for?** This repository rewards finishing
  a bounded piece with evidence over starting a larger one without it.
- **Will a reader be able to tell what was proved?** If not, the writing is not
  done, however good the code is.

A record being *implemented* is not the record being *approved*. ADR-0011 is the
standing example: its wire changes are applied and its status is still
`Proposed`.
