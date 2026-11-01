# packages/api — the service

HTTP endpoints, authentication, session state, persistence, and orchestration of
long-running agent runs.

**Status: not implemented.** The web framework is a deliberately open decision
(see [`ARCHITECTURE.md` §6](../../ARCHITECTURE.md)).

## Responsibilities

- Serve `apps/web` and the `apps/studio-plugin` channel.
- Own **all** credentials. This is the only component that talks to an LLM
  provider over the network
  ([ADR-0005](../../docs/architecture/adr/0005-credentials-and-thin-plugin.md)).
- Authenticate the plugin with a scoped token (`PLUGIN_AUTH_TOKEN`) whose
  privileges cover only: report place state, apply approved edits, run
  playtests.
- Host the approval gate — the point where a human confirms before anything
  touches a real place
  ([ADR-0002](../../docs/architecture/adr/0002-execution-boundary-and-autonomy.md)).
- Validate every inbound protocol message and reject malformed ones rather than
  coercing them ([ADR-0006](../../docs/architecture/adr/0006-protocol-single-source-of-truth.md)).

## Boundaries

- It imports `packages/core`; `core` never imports it.
- It holds no agent reasoning. Prompts, planning and review logic belong in
  `core`, so they can be tested without a server.
- Secrets are redacted from logs and from any error text that reaches a client.
