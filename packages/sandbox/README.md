# packages/sandbox — the execution boundary

Static validation of generated Luau, and controlled execution in a disposable
place. This is the security boundary of the whole system.

**Status: partial static gate; execution remains blocked.** The declarative
action policy admits scoped creation of non-script instances and allowlisted
properties. `LuauSourcePolicyValidator` also accepts a narrow scene-blockout
subset: up to 100 Parts, WedgeParts, Folders, or Models; reviewed property
types (including Part `Orientation` bounded to -360 through 360 degrees); and
parent paths covered by the task's `Workspace/.../**` scope. Every Part and
WedgePart must be explicitly anchored before the candidate passes. Its
version-controlled allowlist is [`luau_policy.json`](luau_policy.json). It
rejects scripts, deletion, arbitrary calls, loops, dynamic indexing, unsupported
syntax, and out-of-scope writes. Neither validator executes generated source.
`LuteSyntaxParser` parses source syntax with the owner-selected official Lute parser, pinned to exactly 1.0.0
([`ADR-0014`](../../docs/architecture/adr/0014-luau-source-analysis-with-lute.md)).
The parser returns a bounded summary plus normalized CST program; the source
policy checks that structure and the summary. It is still only the currently
supported blockout subset, not a complete Luau API policy. Generated Luau
cannot run. The separate fixed-recipe Roblox map harness is not a general Luau
execution boundary and remains gated on live isolation proof. The child process has output and time limits;
its memory is bounded on Linux and Windows, and parsing fails closed on other
platforms where the implementation cannot enforce a memory limit. The full design and
remaining gaps are in [`docs/safety.md`](../../docs/safety.md).

## Running the tests

The standard suite needs only Python and uv, and works without Lute:

```bash
uv sync --locked --extra dev && uv run python -m pytest
```

It exercises the policy against normalized AST fixtures. Real-parser integration
tests exercise both the bridge and source policy, and are skipped when `lute` is
not on `PATH`. To run them, install the pinned runtime with rokit:

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

## Gate 1 — static validation *(partial; source blockout subset implemented)*

Will run before any execution. Not skippable, not overridable by the user. The
Lute bridge, bounded normalized CST, scoped scene-blockout source policy, and
declarative operation policy are implemented. The source policy is intentionally
restricted and does not yet cover general gameplay Luau. See
[`ADR-0014`](../../docs/architecture/adr/0014-luau-source-analysis-with-lute.md).

- **Current allowlist:** [`luau_policy.json`](luau_policy.json) permits only the
  blockout constructors, material enum values, and typed Part properties. All
  service access, publishing, filesystem access, and external `require` are
  rejected because their global names and calls are outside the subset.
- **Current structural checks:** no loops, dynamic calls or indexes, source
  mutation, script classes, or unsupported CST nodes. Numeric values and object
  counts are bounded.
- **Current blast-radius check:** each created object path must fit under one of
  the declared `Workspace/.../**` scopes; duplicate paths and reparenting fail.
- **Still needed for a general gameplay gate:** existing-instance references,
  service-level APIs, and broader data/control-flow analysis.

A failure returns to the builder as feedback. It never prompts the user for an
override — the user is not well placed to judge generated Luau, and a warning
that can be clicked through is not a control.

## Gate 3 — disposable execution *(fixed map harness implemented; runtime gate pending)*

The remote Roblox MCP adapter accepts only bounded scene-recipe JSON as binary
input to a repository-controlled Luau harness. That harness creates temporary
blockout parts, checks route connectivity with PathfindingService, removes its
temporary objects, and returns a bounded result. The API, authenticated MCP
service, and operator route exist. They remain disabled until an isolated test
universe, pinned place version, narrowly scoped Open Cloud key, and actual
non-persistence evidence are provisioned and verified. This validates map
structure and a coarse navigation signal; it does not execute generated Luau or
prove final playability. See
[`ADR-0015`](../../docs/architecture/adr/0015-disposable-world-validation.md).

(Gate 2, human approval, lives in `packages/api`.)

## Known gaps

Carried here from `docs/safety.md` so they are visible at the boundary itself:

- The policy file covers only the scene-blockout subset, not general gameplay
  services, methods, or existing-instance mutation. The bridge bounds input
  length, wall time and output; process memory is bounded on Linux and Windows,
  while other platforms fail closed.
- The declarative edit policy remains script-free; Luau validation is a separate
  restricted static source policy and does not permit execution.
- The fixed remote map harness is implemented, but no isolated test place,
  scoped key, persistence evidence, or live result is configured. It is not a
  general Luau execution sandbox. The remaining gates are in
  [`ADR-0015`](../../docs/architecture/adr/0015-disposable-world-validation.md).
