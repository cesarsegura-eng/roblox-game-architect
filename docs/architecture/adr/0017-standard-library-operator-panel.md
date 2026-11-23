# ADR-0017: Standard-library local operator panel

- **Status:** Accepted
- **Date:** 2026-11-05

## Context

The local operator workflow needs a browser interface for game plans, world
recipes, Studio blockout review, budget quotes, remote MCP status, and audit
history. The project is a local, single-user tool and the UI is served by the
same API process. A separate frontend framework would add a runtime toolchain,
dependencies, and build artifacts without providing a deployment capability the
current product needs.

## Decision

Serve the operator panel as static HTML, CSS, and JavaScript from the existing
Python standard-library HTTP server. Keep the operator API on loopback by
default and require the operator credential for state-changing or sensitive
routes. The client uses the same-origin API and has no independent backend.

## Consequences

- The project has no web-framework or Node runtime dependency for local use.
- The UI remains intentionally suited to a single local operator, not a hosted
  multi-user product.
- UI changes are tested through the API route tests and browser-side JavaScript
  syntax checks; there is no frontend compilation step.
- A future hosted workspace would require a new deployment and authentication
  decision rather than extending this local panel implicitly.

## Alternatives considered

- **A separate React/Vue application:** adds a frontend build and deployment
  pipeline that does not benefit the local operator workflow.
- **No UI:** leaves recipe generation, review, quotes, and cross-service audit
  discovery dependent on CLI commands and manual log inspection.
