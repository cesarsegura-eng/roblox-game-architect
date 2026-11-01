# tests/ — integration and end-to-end

**Unit tests do not live here.** They live next to the code they test, in
`packages/<name>/tests/`. Tests placed beside the code get maintained, because
you see them while editing it; distant tests get abandoned
([ADR-0001](../docs/architecture/adr/0001-monorepo-layout.md)).

This directory is for tests that cross a boundary.

```
test_scaffolding.py   checks on the repository itself (see below)
integration/          contract tests across the Python/Luau boundary
e2e/                  the full loop: request -> plan -> generate -> validate -> run -> review
```

**Status:** `integration/` and `e2e/` are empty — nothing to integrate yet.
`test_scaffolding.py` is the one suite that runs today.

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
- Protocol tests belong in `integration/` and should validate real messages
  against the schemas in `packages/protocol`, in both directions — the point is
  to catch drift, so testing only the Python side defeats it.
- Luau unit tests use TestEZ and live in `apps/studio-plugin/tests/`, not here.

## The evaluation suite

Separate from these tests and not yet built: a set of fixed cases, with
`examples/` as input, that measures whether a change to a prompt or an agent
improves or regresses behaviour. Stage 7 on the
[roadmap](../README.md#roadmap). Without it, engine changes cannot be reviewed
on evidence.
