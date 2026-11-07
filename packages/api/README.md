# packages/api — the service

HTTP endpoints, authentication, session state, persistence, and orchestration of
long-running agent runs.

**Status: the plugin channel, local operator UI, game-planning API, quoted static Luau preview, Blender recipe routes, remote Blender MCP client, generated Studio blockout queue, remote Roblox place-build client, and fixed-harness validation client are implemented.** What runs today is
the whole protocol loop of
[ADR-0011](../../docs/architecture/adr/0011-delivery-execution-and-recovery.md) over the
transport of [ADR-0007](../../docs/architecture/adr/0007-plugin-initiated-http-transport.md):
the handshake, long-polled delivery of one approved work item at a time, results with
their duplicate, conflict and late cases, snapshots, the per-credential lock and the
attestation that releases it. The Luau agent is connected only to the read-only
source-preview endpoint; generated Luau is not queued, delivered, or run. A Roblox Studio plugin performs the
handshake, sends a bounded place snapshot, polls for one approved action, presents
it for local review, applies the safe subset, and reports results. The queue delegates execution policy to `packages/sandbox` and
admits only scoped non-script creation and allowlisted properties. Script
changes, destructive operations and playtests are rejected. The protocol's work lifecycle has been driven by tests and
`tools/fake_plugin.py`.

When `OPERATOR_AUTH_TOKEN` is set, the server also serves a same-origin local
operator panel at `/`. It displays lifecycle and queue state, lets the operator
inspect full queued action JSON, exposes authenticated queue and approval
routes, can generate a Blender scene recipe, preview scoped Luau that passes the
narrow sandbox policy, and generate a compact
script-free Studio blockout into the unapproved queue when a real LLM provider
and spend budget are configured. The token is distinct from both plugin and
Blender tokens. Unset it to disable the panel's API routes. See
[`apps/web`](../../apps/web/README.md).

`POST /v1/operator/game-plan` generates a strict Game Plan v2 JSON handoff through
the configured provider and shared spend budget. The plan partitions systems
into its initial slice and deferred work, and recommends only a supported build
mode (`blockout`, `obby`, `treasure_hunt`, or `rule_game`). The UI can apply that mode
when handing the plan's map brief to world design. Legacy v1 plans migrate to a
script-free blockout slice. The first generation call can be quoted at
`/v1/operator/game-plan-quote`; successful and failed runs are
audited without storing the game brief or plan content. Planning writes no code
and changes no Studio place. Its audit records per-call provider, model, token
usage, and cost, plus matching run totals, without the prompts or generated plan.
The included `game-design-planning` skill separates
script-free blockout work from features that require later implementation.

`POST /v1/operator/code-preview-quote` and `POST /v1/operator/code-preview`
accept a bounded task description and declared `Workspace/.../**` scope. They
are enabled only when a real provider and exactly pinned Lute 1.0.0 are
available. Generation requires the matching single-use quote handle, which
expires after 15 minutes; every retry is individually constrained by the
shared session budget. The API returns source
only when the static scene-blockout policy passes, then audits counts without
storing source or task text. The result is read-only: it is not queued, sent to
Studio, or executed. This is not a general gameplay code generator.

`POST /v1/operator/studio-recipe-action` validates a Scene Recipe and derives
up to 14 axis-aligned, script-free Part proxies for Studio. It bounds the proxy
geometry, converts Blender Z-up coordinates to Roblox Y-up, and queues the
result unapproved. If the recipe exceeds the cap, path, entry, landmark, terrain,
and building roles are prioritized while preserving source order within each
role. The browser request ID makes a retry idempotent, so a lost
response cannot queue a second proxy action. The plugin still requires local
review and an Apply click.

Set `BLENDER_MCP_URL` and `BLENDER_MCP_BEARER_TOKEN` to connect to the dedicated
HTTPS Blender MCP server. Blender runs on that separate server; the Roblox Game
Architect user's computer does not need Blender or its extension installed.
The operator can review a validated scene recipe and explicitly apply it through the dedicated
`rga_apply_scene_recipe` tool. Scene Recipe v3 can build environment geometry,
generic WALK/RUN/JUMP/IDLE character blockouts, and bounded Roblox Lighting,
Atmosphere, and cloud settings; the API receives an authenticated GLB artifact
for operator download. Environment settings are applied to the separate `.rbxlx`
place-build artifact because GLB does not preserve Roblox Lighting or Terrain
configuration. Generic Python execution tools are rejected.
The full endpoint contract and server requirements are in
[`docs/integrations/blender-remote-mcp.md`](../../docs/integrations/blender-remote-mcp.md).

Set `ROBLOX_MCP_URL` and `ROBLOX_MCP_BEARER_TOKEN` to connect to the separately
deployed fixed-harness validation server. Its Open Cloud key, pinned disposable
place, and persistence evidence are deployment requirements; see
[`apps/roblox_mcp_server/README.md`](../../apps/roblox_mcp_server/README.md).
The operator UI exposes reviewed validation and `.rbxlx` build actions when this
endpoint is configured. A build returns a full-place artifact and SHA-256 for
download; the build action itself does not publish. A separately configured,
digest-bound publisher can update only the pinned disposable test place after
the operator opens that exact download in Studio, confirms inspection, and
approves a second action. Production place publishing remains disabled. The
connection check requires the fixed build and validation tools and reports the
test-place publisher separately.
The **Check remote MCPs** action performs a read-only `tools/list` contract
check against each configured service with a five-second request timeout; it
does not call the scene builder or submit a Roblox task.

When `RGA_ROBLOX_ASSET_APPROVAL_SECRET` is configured alongside both remote MCP
services, the operator can approve a separate upload of the exact Blender GLB
to a pinned Roblox account or group. The API fetches the artifact from remote
Blender, signs a short-lived approval over its SHA-256 and metadata, and sends
the bytes directly to the remote Roblox MCP. No GLB is routed through the
browser. This creates a persistent Model asset subject to Roblox moderation; it
does not insert the model into a place or publish a game. The durable remote
ledger makes request retries idempotent.

Use **Check model moderation** to refresh a pending upload without uploading
the GLB again. The authenticated `POST /v1/operator/roblox-model-status` route
accepts only the original `request_id` and calls the remote status tool. An
approved receipt enables the existing model-import review; pending or rejected
receipts do not. If the selected artifact changes while a check is running,
the panel ignores that outdated response. Status checks require the Roblox
MCP connection, but do not require another upload approval or a Blender call.

`RGA_ROBLOX_PUBLISH_APPROVAL_SECRET` plus the pinned test universe/place IDs
enables the separate `POST /v1/operator/roblox-publish` action when the remote
MCP reports its fixed publishing tool. The API will publish only a build
artifact held in its current process cache, not bytes supplied by the browser.
Its short-lived HMAC approval binds the exact file digest and fixed destination;
the remote MCP uses a separate `universe-places:write` key and durable ledger.
The operator must attest that the downloaded file was inspected in Roblox
Studio. This action replaces the published version of the disposable test
place; it is not available for production place IDs.

It is built on the **standard library**. The local operator panel is static HTML,
CSS, and JavaScript served by the API's standard-library HTTP server; it adds no
third-party runtime dependency and does not import a web framework. This is the
accepted implementation for the local, single-user operator workflow.

| Module | What it holds |
|---|---|
| `json_profile.py` | the strict JSON profile, the API's own copy — the reference one is test-only |
| `messages.py` | envelope and payload validation for the five request types, and the response envelopes |
| `store.py` | the `Store` seam, SQLite FULL-synchronous lifecycle storage, and migration from legacy per-credential JSON files under `DATA_DIR` |
| `service.py` | the lifecycle: sessions, delivery, results, the lock. Transport-free |
| `http.py` | loopback protocol transport, operator panel, and authenticated generation/remote-apply endpoints |
| `blender_mcp.py` | restricted remote MCP Streamable HTTP client for scene recipe imports |
| `roblox_mcp.py` | fixed-harness remote MCP client for map validation, place builds, reviewed Model uploads, and digest-bound disposable-place publishing |
| `cli.py` | operator actions, API startup, and shared-budget provider wiring |

The operator-only `POST /v1/operator/world-quote` and
`POST /v1/operator/studio-quote` routes return the provider's maximum-cost
estimate for the first call using the same skill-guided prompt as the matching
generator, along with the current session cap and remaining budget. Every later
repair attempt is quoted independently by `BudgetedLLMProvider`; generation is
refused if a quote is unavailable or exceeds the remaining cap.
The authenticated operator status response also exposes the live session cap,
spent amount, in-flight reservations, and remaining budget; the web panel
refreshes it after each generation attempt.
Generation success and failure events carry an opaque run ID, operation type,
duration, and structural output counts. Successful model-backed runs can also
include bounded per-call provider, model, token usage, and cost metadata with
verified totals. They omit the user brief, model prompt and output, generated
recipe/action, and provider exception text.
The panel's HTML, CSS, and JavaScript are included as `apps` package resources,
so the operator UI does not depend on a source-checkout-relative asset path.

**Three decisions ADR-0011 leaves open had to be made one way for this to run at all.**
Each is marked `PROVISIONAL` where it is made, and making it here does not settle it: how
two results are compared, what the idempotency digest covers, and what is answered when a
`message_id` returns with different content.

## Running it

```
PLUGIN_AUTH_TOKEN=local-only-example-token-please-change python -m api.cli serve
PLUGIN_AUTH_TOKEN=local-only-example-token-please-change python -m api.cli queue tools/examples/create-platform.json
PLUGIN_AUTH_TOKEN=local-only-example-token-please-change python -m api.cli approve a-0001
PLUGIN_AUTH_TOKEN=local-only-example-token-please-change python tools/fake_plugin.py
```

For a bounded Blender scene recipe, run
`python -m api.world_cli "Describe the place" path/to/new-recipe.json` after
setting `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, `LLM_MODEL_ID`, and the
spend limit in the operator process environment. The command refuses an
existing output path and does not send the API key to Blender.

Use long random `PLUGIN_AUTH_TOKEN`, `BLENDER_AUTH_TOKEN` and
`BLENDER_MCP_BEARER_TOKEN` values in real configurations; they are distinct
credentials and each requires 32–512 printable ASCII characters. The API
exposes the authenticated `POST /v1/world/recipe` route on loopback; generation
shares the API server's spend budget. The optional local Blender extension can
call this route with `BLENDER_AUTH_TOKEN`, but the remote MCP build/download
workflow does not require that extension. The Anthropic key remains in the API
process.

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
