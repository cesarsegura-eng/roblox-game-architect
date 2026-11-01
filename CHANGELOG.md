# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Repository scaffolding: `packages/` (core, api, protocol, sandbox) and `apps/`
  (web, studio-plugin), each with a README stating its boundaries.
- `ARCHITECTURE.md` describing the component layout and the invariants.
- Architecture decision records ADR-0001 to ADR-0007.
- `docs/safety.md` — the execution boundary, approval model and spend limits.
- `docs/protocol/README.md` — rules for the backend/plugin contract.
- Governance: `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, issue and
  pull request templates.
- CI: lint, tests and secret scanning on push and pull request; Dependabot.
- `.editorconfig`, `.env.example`, Python tooling config in `pyproject.toml`,
  Luau tooling config (`selene.toml`, `stylua.toml`, `aftman.toml`).

- `.gitattributes`, normalising line endings to LF and marking Roblox place and
  model files as binary.
- `uv.lock` — 10 packages pinned (ruff 0.17.3, pytest 9.2.0, pytest-env 1.8.4
  and their transitive dependencies).
- `tests/test_scaffolding.py` — checks the repository itself: LF line endings,
  `.gitattributes`, no Roblox binaries, `uv.lock` present, and that
  `LLM_PROVIDER=fake` is in effect (invariant I7). It replaces a CI guard that
  let the test step pass while collecting nothing.
- ADR-0007: plugin-initiated HTTP with long-polling, amending ADR-0006.

### Changed

- `.gitignore` extended to cover Roblox binaries (`*.rbxl`, `*.rbxm`), Rojo and
  Wally artifacts, generated project data, test caches and OS files.
- `LICENSE` copyright holder filled in.
- Python dependencies are managed with uv and bounded at the next breaking
  release; `pyproject.toml` uses the PEP 639 license form.
- Toolchain installed with rokit instead of aftman (whose repository is
  archived), at versions verified against upstream releases: rojo 7.7.1,
  selene 0.32.0, StyLua 2.6.0.
- GitHub Actions updated to current majors (`checkout@v7`, `codeql-action@v4`)
  and gitleaks pinned to a commit SHA.
- `packages/sandbox` documented as the single authority on static validation;
  `packages/core` no longer described as pre-validating.
- Safety controls that are not implemented are now labelled *(planned)* at each
  heading, not only in a status line at the top of the document.
- `README.md` no longer describes the engine or the test suite as existing, and
  the roadmap distinguishes written, verified and planned.

### Fixed

- Removed a duplicate, mistyped git remote (`orgin`).
- `.gitignore` had CRLF line endings, contradicting `.editorconfig`.
- `ruff` configuration ignored `ANN101` and `ANN102`, removed in ruff 0.8.0;
  selecting a removed rule is an error, so `ruff check` would have failed.
- `selene`'s Roblox standard library is generated, not bundled: CI now generates
  it in an explicit step.
- Documentation described a WebSocket transport option that Luau does not
  provide.
- CI installed dependencies with free resolution and checked the lockfile
  *after* installing, which made the check meaningless: the install rewrote the
  lock first. The order is now check-then-install, the install uses `--locked`,
  and a missing lockfile fails the build instead of being skipped.
- `tests/test_scaffolding.py` walked the filesystem and so inspected gitignored
  build artefacts; it now takes its file list from git.

### Notes

No engine code exists yet. Nothing in this release is runnable.
