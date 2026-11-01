# ADR-0001: Monorepo layout with a web-free core

- **Status:** Accepted
- **Date:** 2026-11-01

## Context

The system has four surfaces that must ship together and stay consistent: an AI
engine, an HTTP service, a web application and a Roblox Studio plugin. An early
flat layout (`backend/`, `frontend/`, `studio-plugin/`, `tests/`) put the engine
and the web service in the same directory.

That merge is the problem. The engine and the service have different natures:
the service is request-scoped, framework-bound and I/O-heavy; the engine is a
long-running, stateful reasoning loop. If they share a package, the engine ends
up importing the web framework, and then it can only be exercised through the
server. The hardest component to test becomes the one that needs the most
scaffolding to test.

## Decision

A monorepo split into `packages/` (importable libraries) and `apps/`
(deployable surfaces):

```
packages/core       engine — planner, builder, tester, reviewer, codegen
packages/api        HTTP service, auth, sessions, orchestration
packages/protocol   the Python/Luau contract
packages/sandbox    validation and execution boundary
apps/web            browser UI
apps/studio-plugin  Luau thin client
tests/              integration and end-to-end
```

**`packages/core` must not import a web framework.** This is invariant I1 in
`ARCHITECTURE.md`. Dependency direction is one-way: `api` → `core` → `sandbox`
and `protocol`. Nothing imports `api`.

Unit tests live inside each package, in `packages/<name>/tests/`. The root
`tests/` directory is for integration and end-to-end only.

## Consequences

**Easier:**

- The engine can be driven from a plain script and from CI, with no server. Any
  contributor can reproduce a generation.
- The security boundary (`sandbox`) and the cross-language contract
  (`protocol`) each have a name in the file tree, so each gets reviewed.
- `apps/` vs `packages/` makes it obvious what may be imported from where.

**Harder:**

- More directories than the work currently justifies. The repository looks
  bigger than it is, and that is a real cost for a newcomer.
- Two toolchains (Python, Node) plus Luau tooling in one repository means more
  CI configuration and more lock files.
- Unit tests split across packages means no single `pytest tests/` entry point
  covering everything; contributors have to be told where tests live, which
  `CONTRIBUTING.md` now does.

**Given up:** the simplicity of a single flat `backend/`.

## Alternatives considered

- **Keep the flat layout.** Rejected: it makes the web-free core impossible to
  enforce, which is the decision carrying the most value here.
- **Separate repositories per surface.** Rejected at this stage: the
  plugin/engine contract changes constantly early on, and cross-repository
  changes to a contract are far more expensive than a monorepo diff. Worth
  revisiting if the plugin stabilises.
- **Colocate unit tests in the root `tests/`.** Rejected: distant tests get
  abandoned, and the plugin's Luau tests (TestEZ) cannot live in a Python suite
  anyway.
