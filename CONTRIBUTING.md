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
uv run pytest
```

That last command runs `tests/test_scaffolding.py`, which checks the repository
itself (line endings, `.gitattributes`, and that `LLM_PROVIDER=fake` is in
effect). There is no engine to run yet.

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

Optional until `apps/studio-plugin` has source:

```bash
rokit install
```

That installs `rojo`, `selene` and `stylua` at the versions pinned in
`aftman.toml` — rokit reads that filename, and the header there explains why it
has not been renamed. aftman itself is no longer used: its repository is
archived.

`selene` needs the Roblox standard library, which is generated rather than
bundled:

```bash
selene update-roblox-std
```

## Checks

Run these before pushing. CI runs the same ones.

```bash
uv run ruff check .
```

```bash
uv run ruff format --check .
```

```bash
uv run pytest
```

The Luau checks only do something once `apps/studio-plugin/src` has files; CI
skips them until then.

```bash
selene apps/studio-plugin/src
```

```bash
stylua --check apps/studio-plugin/src
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
