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
- `packages/protocol` version 1.0: JSON Schema (Draft 2020-12) for the handshake,
  `work.poll`, `project.state`, `edit.action`/`edit.result`, `playtest.request`/
  `playtest.report` and the two error taxonomies; 20 schema files and
  `schemas/v1/version.json`.
- `packages/protocol/examples/v1/`: 240 conformance vectors (50 valid, 148 invalid,
  42 for the strict JSON profile) and `index.json`.
- `packages/protocol/tests/`: schema, subset-audit, strict-JSON and semantic tests
  (reference checks for scope and ordering, test-only).
- ADR-0008 (`edit.action` as a flat list of primitive operations, the property
  allowlist in the schema, script creation) and ADR-0009 (a closed schema subset and
  a strict JSON profile for validation on both sides).
- ADR-0010 to ADR-0013 (proposed): script execution reach and action semantics;
  delivery, execution, idempotency and recovery; untrusted text and Unicode
  rendering; conformance suites. ADR-0008 and ADR-0009 record that they are amended
  by them. ADR-0010, ADR-0012 and ADR-0013 remain documentation only; the changes
  ADR-0011 makes to the wire are applied (see *Changed*), while its state machines,
  lock and records have no schema and are not implemented.
- `docs/protocol/README.md` rewritten as the specification of version 1.0.
- `jsonschema` (4.26.0) in the `dev` extra, with its five transitive dependencies,
  to validate the protocol schemas in tests.
- `packages/core`: the `LLMProvider` contract, trusted/untrusted prompt framing,
  deterministic fake provider, `IterationBudget`, and `SpendBudget` /
  `BudgetedLLMProvider`, with unit tests. These are foundations only; there is no
  agent loop or paid provider adapter.
- ADR-0014: owner-selected official Lute parser for Luau source analysis, pinned
  to stable 1.0.0; a syntax-only bridge and integration smoke test are present.
  The security policy analyzer and memory limit are not implemented.
- `packages/protocol`: the protocol error code `result_conflict`, answered when a
  result differs from the one already recorded for a work item, and two conformance
  vectors for it and for the mixed form of `indeterminate`
  (`edit.result.response.error-result-conflict.json`,
  `edit.result.request.indeterminate-partial-knowledge.json`). 52 valid vectors.
- `packages/api`: the plugin channel, on the **standard library** — no runtime
  dependency and no web framework chosen. It runs the loop of ADR-0011 over the
  transport of ADR-0007: the handshake with version negotiation, long-polled delivery
  of one approved work item at a time with the state `delivered` persisted before the
  response leaves, results with their duplicate, conflict and late cases, the bounded
  replay cache, snapshots, the per-credential lock on each of T1 to T4, and the human
  attestation that releases it. `store.py` keeps the state durable under `DATA_DIR`
  behind a `Store` seam, so the persistence engine stays an open decision; the data
  directory is named after a digest of the credential and never holds the token.
  There is no agent loop, no LLM call and no web surface, and no Studio plugin has
  ever connected to it.
- `packages/api/json_profile.py` and `messages.py`: the API's own strict-JSON parser
  and message validator, because the reference checks under `packages/protocol/tests/`
  are test-only and `jsonschema` is a test dependency. `packages/api/tests/
  test_conformance.py` holds them to the protocol's own vectors — all 42 parse vectors
  and every request-kind vector in the suite, `generate` recipes expanded.
- `packages/api/cli.py`: the operator surface until `apps/web` exists — `serve`,
  `queue`, `approve`, `status` and `attest`, the last printing the warning it records.
- `tools/fake_plugin.py` and `tools/examples/`: a stand-in that speaks the protocol and
  **applies nothing**, so the loop can be driven by hand without Roblox.
- `tests/test_api_e2e.py`: the loop over real HTTP, plus the checks that lifecycle state
  survives a new process and that `DATA_DIR` never holds the credential.

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
- `docs/safety.md` records that protocol v1 cannot activate a script: generated
  scripts are created disabled and a human enables them.
- **Breaking (pre-1.0 protocol):** the protocol error code `unknown_action` is
  renamed `unknown_work`, and is now answered for any work item — an action or a
  playtest — whose state does not accept a result (ADR-0011, RD5). Renaming a member
  of a closed enum is admissible only because the tag `protocol-v1.0` does not exist
  yet; after it, this would be a major bump.
- `indeterminate` now means **at least one** operation is `unknown`, with the applied
  operations before it and the skipped ones after, instead of requiring every
  operation to be `unknown` (ADR-0011 section 9). The reference check and its tests
  follow: the order an action is reported in ranks `failed` and `unknown` together,
  between `applied` and `skipped`, and the per-outcome status sets keep the two from
  sharing a result. The schema is unchanged.
- `docs/protocol/README.md` section *Idempotency and recovery* rewritten to ADR-0011:
  three records instead of one status, one active work item, redelivery only inside
  the delivering session, a per-credential lock released only by a human attestation,
  and the statement that the API cannot tell which process sent a message. The
  superseded ledger table and "`indeterminate` is final" are gone.
- `packages/api`, `ARCHITECTURE.md` and `README.md` no longer describe the API as not
  implemented: the plugin channel is, and the roadmap says stage 4 is in progress with
  what is missing named. Approving work is refused while the lock is engaged, and after
  an attestation until a fresh snapshot arrives, which is RD3 read as a precondition.
- `ARCHITECTURE.md` section 6: the persistence engine is still undecided but now
  carries ADR-0011's two durability requirements — `delivered` persisted before the
  work item is sent, and an accepted result with its idempotency record committed
  before `ok` is emitted.
- `ARCHITECTURE.md` section 6: the shape of `edit.action` and the Luau-side
  validation are settled (ADR-0008, ADR-0009); Luau conformance remains unverified.
- Documentation no longer states that generated scripts cannot run in a v1 playtest.
  `docs/protocol/README.md`, `docs/safety.md`, `ARCHITECTURE.md` and
  `packages/protocol/README.md` now say that no protocol operation enables a script
  and that this does not guarantee agent-authored code cannot execute (ADR-0010).

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

No end-to-end engine exists yet. The core LLM and budget foundations are
implemented and tested as libraries, but there is no agent loop, real provider
adapter, API, sandbox, Studio plugin or web application to run.
