# Contributing

Thanks for considering a contribution. This project is at the scaffolding stage,
so the most valuable contributions right now are architecture review and the
first vertical slice, not breadth.

## Ground rules

1. **Open an issue before a large PR.** A design disagreement is cheaper to
   resolve in an issue than in 800 lines of diff.
2. **One concern per pull request.** Mixed refactor-plus-feature PRs are hard to
   review and harder to revert.
3. **The architecture decisions in `docs/architecture/adr/` are settled** unless
   you supersede one with a new ADR. Do not reopen them inline in a PR comment.

## Development setup

[uv](https://docs.astral.sh/uv/) manages the Python side. It resolves,
installs and locks in one tool, and it is what CI uses.

```bash
cp .env.example .env
```

```bash
uv sync --locked --extra dev
```

```bash
uv run python -m pytest
```

That last command runs `tests/test_scaffolding.py`, which checks the repository
itself (line endings, `.gitattributes`, and that `LLM_PROVIDER=fake` is in
effect). The test suite does not embed Roblox Studio; engine checks use a local
disposable place and the procedures in
[`docs/runbook-live-verification.md`](docs/runbook-live-verification.md).

If you would rather not use uv, `pip install -e ".[dev]"` in a virtual
environment works too — the dev dependencies stay declared as an extra, not a
PEP 735 group, for exactly that reason. You will be resolving within the version
ranges instead of against the lock, so CI is the arbiter.

### Dependency reproducibility

`uv.lock` is committed and is the source of truth for what gets installed.
Version ranges in `pyproject.toml` are bounded at the next breaking release, so
they also cannot drift on their own, but the lock is what makes an install
identical across machines.

CI installs with `uv sync --locked --extra dev`, and checks `uv lock --check`
**before** installing. Order matters: an install allowed to resolve freely
rewrites the lockfile, so a check that ran afterwards would inspect a file it
had just repaired and always pass.

When you change a dependency in `pyproject.toml`:

```bash
uv lock
```

Commit the updated `uv.lock` in the same pull request. If you forget, CI fails
at the "Lockfile matches pyproject.toml" step with
`The lockfile at uv.lock needs to be updated`.

Dependabot currently updates the ranges in `pyproject.toml` (the `pip`
ecosystem). Moving it to the `uv` ecosystem so it updates the lock directly is
a ready-to-enable block in `.github/dependabot.yml`.

### Luau tooling

The current Studio plugin and developer-only engine drivers use the toolchain
pinned in `aftman.toml` (Rokit reads this file):

```bash
rokit install
```

That installs `rojo`, `selene` and `stylua` at the versions pinned in
`aftman.toml` — rokit reads that filename, and the header there explains why it
has not been renamed. aftman itself is no longer used: its repository is
archived.

`selene` uses the checked-in Roblox standard library in `roblox.yml`, pinned by
`selene.toml` so local lint and CI don't fetch the API at run time. To update
that engine API baseline intentionally, run:

```bash
selene generate-roblox-std
```

Review the resulting `roblox.yml` diff before committing it.

## Before you change code

Check [`docs/read-before-changing.md`](docs/read-before-changing.md) for the
file you are about to edit. It records the implementation details that look
arbitrary and are not, what breaks if they change, and how each was
established. Simpler implementations are welcome; the entries name the
property that has to survive.

## Checks

Run these before pushing. CI runs the same ones.

```bash
uv run ruff check .
```

```bash
uv run ruff format --check .
```

```bash
uv run python -m pytest
```

CI lints the Studio plugin and Play Solo drivers and checks their formatting.
Run the same checks locally with the pinned tools:

```bash
selene apps/studio-plugin/src \
  tools/studio_rainforest_obby.luau \
  tools/studio_rainforest_obby_multiplayer.luau \
  tools/studio_treasure_hunt.luau \
  tools/studio_rule_game_speed_boost.luau \
  tools/studio_rule_game_round_reset.luau
```

```bash
stylua --check \
  apps/studio-plugin/src/Main.plugin.lua \
  apps/studio-plugin/src/Protocol/StrictJson.lua \
  apps/studio-plugin/src/Protocol/SchemaValidator.lua \
  tools/studio_rainforest_obby.luau \
  tools/studio_rainforest_obby_multiplayer.luau \
  tools/studio_treasure_hunt.luau \
  tools/studio_rule_game_speed_boost.luau \
  tools/studio_rule_game_round_reset.luau
```

## Code style

- **Python** — `ruff` for linting and formatting; type hints on anything public.
  Keep `packages/core` free of web framework imports: it must stay importable
  from a plain script. CI does not enforce that yet, but reviewers do.
- **Luau** — `stylua` for formatting, `selene` for linting, tabs for indentation.
- **Commits** — Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`,
  `refactor:`, `test:`). The history is read by humans deciding what broke.

## Tests

- Unit tests live next to the code they test, in `packages/<name>/tests/`.
- Integration and end-to-end tests live in `tests/`.
- Tests must pass with `LLM_PROVIDER=fake`. A test that needs a paid API key is
  not a test CI can rely on, and will be asked to use the fake provider instead.

## AI-generated contributions

Part of this project's output is model-written by design, and model-written
contributions are welcome here. Two conditions:

- **You have read and understood what you are submitting.** You are the author
  of record; "the model wrote it" is not an answer to a review question.
- **Say so in the PR description.** Not for judgement, for review attention:
  generated code tends to fail in different places than hand-written code.

## Scope boundaries

Pull requests that will be declined regardless of code quality:

- Anything that publishes to Roblox without an explicit human action.
- Anything that moves LLM API keys into the Studio plugin.
- Anything that removes the execution boundary or the budget limits.

These are safety invariants, not preferences. See [`docs/safety.md`](docs/safety.md).

## Code of conduct

Participation is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
