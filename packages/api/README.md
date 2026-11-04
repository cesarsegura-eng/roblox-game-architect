# packages/api — the service

HTTP endpoints, authentication, session state, persistence, and orchestration of
long-running agent runs.

**Status: the plugin channel is implemented; nothing else is.** What runs today is
the whole protocol loop of
[ADR-0011](../../docs/architecture/adr/0011-delivery-execution-and-recovery.md) over the
transport of [ADR-0007](../../docs/architecture/adr/0007-plugin-initiated-http-transport.md):
the handshake, long-polled delivery of one approved work item at a time, results with
their duplicate, conflict and late cases, snapshots, the per-credential lock and the
attestation that releases it. There is **no agent loop, no LLM call and no web surface**,
and no plugin has ever connected to it: it has been driven only by tests and by
`tools/fake_plugin.py`.

It is built on the **standard library**. That is deliberate: the web framework is still an
open decision (`ARCHITECTURE.md` section 6), so this adds no runtime dependency and
forecloses nothing. `apps/web` will need that decision; the plugin channel did not.

| Module | What it holds |
|---|---|
| `json_profile.py` | the strict JSON profile, the API's own copy — the reference one is test-only |
| `messages.py` | envelope and payload validation for the five request types, and the response envelopes |
| `store.py` | the `Store` seam, and a provisional file-backed implementation under `DATA_DIR` |
| `service.py` | the lifecycle: sessions, delivery, results, the lock. Transport-free |
| `http.py` | the transport, and nothing else |
| `cli.py` | the operator surface, until `apps/web` exists |

**Three decisions ADR-0011 leaves open had to be made one way for this to run at all.**
Each is marked `PROVISIONAL` where it is made, and making it here does not settle it: how
two results are compared, what the idempotency digest covers, and what is answered when a
`message_id` returns with different content.

## Running it

```
PLUGIN_AUTH_TOKEN=dev python -m api.cli serve
PLUGIN_AUTH_TOKEN=dev python -m api.cli queue tools/examples/create-platform.json
PLUGIN_AUTH_TOKEN=dev python -m api.cli approve a-0001
PLUGIN_AUTH_TOKEN=dev python tools/fake_plugin.py
```

`tools/fake_plugin.py` speaks the protocol but **applies nothing**: there is no place, no
pre-flight and no verification at apply time. It is a way to drive the API by hand.

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
