# tests/ — repository and cross-component tests

**Unit tests do not live here.** They live next to the code they test, in
`packages/<name>/tests/`. Tests placed beside the code get maintained, because
you see them while editing it; distant tests get abandoned
([ADR-0001](../docs/architecture/adr/0001-monorepo-layout.md)).

This directory contains tests that cross a boundary or verify the repository as
a distributable product. It does not contain the whole end-to-end game loop.

```
test_scaffolding.py       repository hygiene and test configuration
test_api_e2e.py           API transport, approval, delivery and result lifecycle
test_build_roblox_place.py fixed-mode place artifact CLI
test_agent_skills.py       portable skill synchronization and packaging
```

Protocol schema and reference-vector tests live beside the protocol package in
`packages/protocol/tests/`. Package-specific integration tests live beside the
components they exercise. These suites do not yet prove a complete game loop
through an existing agent, hosted MCP services, Roblox Studio play, and review.

## `test_scaffolding.py`

It tests the repository, not a game: LF line endings, that `.gitattributes`
enforces them, that no Roblox binary is in the repository, that `uv.lock`
exists (CI installs with `--locked` and cannot work without it), and that
`LLM_PROVIDER=fake` reaches the tests (invariant I7, which also proves
`pytest-env` and the `pyproject.toml` config are live).

The file list comes from `git ls-files --cached --others --exclude-standard`,
not from a directory walk. The invariants are about what enters the repository,
and a walk also picks up `.venv/` and `*.egg-info/` — gitignored build
artefacts whose line endings are not ours to control. The first version of this
file walked the tree and failed on exactly that.

It exists for a specific reason. The CI test step used to carry a guard that
let it pass when nothing was collected, so a green tick meant nothing. With a
suite that always collects, exit code 5 is a real failure again. Two of its
checks also pin mistakes that were actually made here: a CRLF file committed
from a Windows checkout, and a lint config that could not run.

## Rules

- Everything here must pass with `LLM_PROVIDER=fake` (invariant I7). A test that
  needs a paid API key is not a test CI can rely on.
- Protocol tests belong in `packages/protocol/tests/` and should validate real
  messages against the schemas in `packages/protocol`, in both directions — the
  point is to catch drift, so testing only the Python side defeats it.
- Luau unit tests use TestEZ and live in `apps/studio-plugin/tests/`, not here.

## The evaluation suite

The offline fixed-case evaluator exists as
[`tools/evaluate_worldbuilding.py`](../tools/evaluate_worldbuilding.py). It
measures bounded scene-generation structure against reviewed examples at zero
provider spend. It does not grade visual quality, Studio playability, live
provider behavior, or production readiness. Stage 7 on the
[roadmap](../README.md#roadmap) remains in progress until those gaps are covered.

The rainforest Obby also has two complementary play checks. The pinned-Lute
simulation at
[`tools/check_rainforest_obby.py`](../tools/check_rainforest_obby.py) exercises
the trusted template with mocked services; the developer-only
[`tools/studio_rainforest_obby.luau`](../tools/studio_rainforest_obby.luau)
driver checks real touch, respawn, and `PathfindingService` route behavior in a
fresh one-player Studio Play Solo session. Run it from the **Server** command
bar only, and stop the session without saving. Its mechanic checks teleport the
player, so they do not prove manual walking/control playability; neither check
proves multiplayer engine behavior, persistence, or live-server readiness.

[`tools/studio_rainforest_obby_multiplayer.luau`](../tools/studio_rainforest_obby_multiplayer.luau)
is the companion two-client Studio driver. Run it from the **Server** command
bar in a fresh local Server & Clients session configured for exactly two
clients. It checks per-player checkpoint isolation, separate finish awards,
duplicate finish handling, hazard elimination, respawn locations, and retained
stats. It teleports characters to trigger parts, so it does not test normal
controls. This driver is linted in CI but has not yet passed in the Studio
engine; multiplayer engine behavior remains unverified.
