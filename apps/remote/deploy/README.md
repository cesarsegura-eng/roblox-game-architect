# Remote MCP deployment

This stack runs the Blender and Roblox MCP services on a separate host. Only
Caddy publishes ports 80/443; the MCP containers have no host ports and are
reachable only on the Compose network. The user's computer needs only an agent
that can connect to the two HTTPS MCP endpoints and load the portable RGA skills.
Blender runs inside the Blender server image. Roblox Studio is not required for
the fixed data-only build and map-validation tools; Studio remains useful for
human review and live acceptance testing.

## Host requirements

- A Linux server with Docker Engine and the Docker Compose plugin.
- Public DNS A/AAAA records for both MCP names pointing to this server.
- Inbound TCP 80/443, plus UDP 443 if HTTP/3 is desired.
- Enough memory for the Blender container. Its worker is capped separately; the
  Compose limit reserves up to 6 GiB for the Blender service.
- A Roblox Open Cloud key is optional and is needed only for configured cloud
  validation, asset creation, or test-place publication. Keep it server-side.

## Configure and start

From this directory, make private copies of the environment examples:

```sh
cp .env.example .env
cp blender.env.example blender.env
cp roblox.env.example roblox.env
chmod 600 .env blender.env roblox.env
```

Set the real DNS names in `.env`. Generate separate, high-entropy bearer tokens
for `BLENDER_MCP_BEARER_TOKEN` and `RGA_ROBLOX_MCP_TOKEN`; do not reuse a token
between services. For the first build, leave the Roblox cloud, target, upload,
transfer and publication settings blank. With its bearer token and the bundled
Rojo executable, the Roblox service exposes `rga_build_place`. To enable
`rga_validate_map`, configure the complete
[disposable-place validation settings](../../roblox_mcp_server/README.md#optional-cloud-validation).

### Optional Blender-to-Roblox model pipeline

To let the Roblox MCP fetch a generated GLB directly from the Blender MCP, set
these values in `roblox.env` on the server:

```text
BLENDER_MCP_URL=https://<BLENDER_DOMAIN>/mcp
BLENDER_MCP_BEARER_TOKEN=<copy the Blender service token>
RGA_ROBLOX_BLENDER_TRANSFER_CONFIRMED=I_ACCEPT_ROBLOX_MODEL_TRANSFER
```

Enable the disposable-place validator before configuring the model pipeline.
Transfer also requires a dedicated
asset-create Open Cloud key, a fixed creator ID/type, a unique
`RGA_ROBLOX_ASSET_APPROVAL_SECRET`, and
`RGA_ROBLOX_ASSET_CREATION_CONFIRMED=I_ACCEPT_ROBLOX_ASSET_CREATION`. Keep the
key and secret in `roblox.env`; never place them in the agent's MCP client.
Each asset write still requires the agent to show the recipe and digest and
obtain the user's per-call approval. After Roblox moderation approves the asset,
the agent can use `rga_build_place` to make a script-free place artifact that
contains it. This pipeline does not publish that place, and custom gameplay
source is still unsupported.

Build and start the stack:

```sh
docker compose up --build -d
docker compose ps
```

Caddy obtains and renews TLS certificates. It forwards only `/mcp` and
`/artifacts/*` for Blender, and `/mcp` and GET `/downloads/*` for Roblox. The Blender health endpoint
and every other route stay private. Caddy preserves MCP and authorization
headers; request bodies are capped at 1 MiB for Blender calls and 28 MiB for
Roblox MCP calls. The service handlers apply their own stricter tool-specific
limits. Pin and review the image versions before exposing this stack to agent
clients.

## Connect an existing agent

For browser delivery, set `RGA_ROBLOX_DOWNLOAD_ORIGIN=https://<ROBLOX_DOMAIN>`
in `roblox.env` on the service host. The authenticated agent can then call
`rga_build_place_download` with the same recipe and rules as `rga_build_place`.
Give the returned private link to the requesting user. Anyone holding it can
download that one file for 15 minutes without the service credential. Each
server process holds at most 64 MiB or 256 files. Restarting it clears links.
Use a single Roblox backend for this route and omit download paths from proxy logs.

Configure the agent's MCP client with these Streamable HTTP URLs and the matching
bearer credentials:

```text
https://<BLENDER_DOMAIN>/mcp
https://<ROBLOX_DOMAIN>/mcp
```

Build the portable skill archive from the repository root with
`python tools/package_agent_skills.py --archive dist/rga-agent-skills.zip`, then
install/import it in the agent's own skill system. Do not install Blender,
Roblox Studio, or the RGA API on the player's computer for the direct MCP
workflow. The optional local API/operator panel is a separate deployment choice.

Verify both endpoint tool lists through the actual agent MCP client before
calling them live. Start with read-only health/contract checks, then build a
non-published artifact and inspect it. Cloud writes and test-place publication
remain disabled until the isolated Roblox target and rollback evidence are
recorded in [ADR-0015](../../../docs/architecture/adr/0015-disposable-world-validation.md)
and [ADR-0018](../../../docs/architecture/adr/0018-remote-roblox-map-authoring.md).

The deployment pins Caddy 2.11.8, which includes the request size limiter. See the
[official Caddy directive documentation](https://caddyserver.com/docs/caddyfile/directives/request_body).
