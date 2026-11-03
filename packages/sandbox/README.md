# packages/sandbox — the execution boundary

Static validation of generated Luau, and controlled execution in a disposable
place. This is the security boundary of the whole system.

**Status: partial foundation.** `LuteSyntaxParser` parses source syntax with
the owner-selected official Lute parser, pinned to exactly 1.0.0
([`ADR-0014`](../../docs/architecture/adr/0014-luau-source-analysis-with-lute.md)).
This is all that exists here: there is no CST policy analyzer, API allowlist,
memory bound, complete Gate 1, execution isolation or disposable-place mechanism,
so it cannot authorize generated code to run. The full design and remaining gaps
are in [`docs/safety.md`](../../docs/safety.md).

## Running the tests

The standard suite needs only Python and uv, and works without Lute:

```bash
uv sync --locked --extra dev && uv run pytest
```

It exercises the bridge's fail-closed handling against a mocked Lute process. The
one test that runs the real parser is skipped when `lute` is not on `PATH`. To run
it, install the pinned runtime with rokit, then select the integration test:

```bash
rokit install
uv run pytest -m integration packages/sandbox/tests/test_lute_integration.py
```

## Why this is a package and not a module

A boundary nobody can point at is a boundary nobody reviews. Giving it a name in
the file tree makes it a thing a contributor can find, audit and reason about
([ADR-0002](../../docs/architecture/adr/0002-execution-boundary-and-autonomy.md)).

## This package is the only validator

No other component decides whether generated code may run. `packages/core`
produces code and asks here for a verdict; it implements no checks of its own.
A boundary with two owners has none.

## Gate 1 — static validation *(not implemented; syntax bridge exists)*

Will run before any execution. Not skippable, not overridable by the user. The
syntax bridge uses the official Lute parser at exact version 1.0.0; the API
allowlist and structural policy checks are not implemented. See
[`ADR-0014`](../../docs/architecture/adr/0014-luau-source-analysis-with-lute.md).

- **API allowlist**, kept as a version-controlled file so changing it is a
  reviewable diff. Denied by default: `HttpService`, `DataStoreService`,
  `MarketplaceService`, anything that publishes, anything that writes to the
  filesystem, and `require` of external assets.
- **Structural checks**: no dynamic code construction (`loadstring` and
  equivalents), no unbounded loops without a yield, no obfuscated identifiers.
- **Blast-radius check**: the instances the script will touch must be a subset
  of what the task declared.

A failure returns to the builder as feedback. It never prompts the user for an
override — the user is not well placed to judge generated Luau, and a warning
that can be clicked through is not a control.

## Gate 3 — disposable execution *(planned, not implemented)*

First execution of anything is to happen in a throwaway test place, never the
user's working place. Playtest output is collected and handed back to the reviewer
agent as data.

(Gate 2, human approval, lives in `packages/api`.)

## Known gaps

Carried here from `docs/safety.md` so they are visible at the boundary itself:

- The API allowlist does not exist yet.
- The syntax bridge is implemented, but no CST analyzer or API allowlist exists.
  It bounds input length and wall time, but not process memory; it is not a
  security gate.
- "Disposable test place" has no mechanism — how the plugin creates and tears
  one down is undesigned.
