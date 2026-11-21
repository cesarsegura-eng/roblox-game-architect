# Remote MCP deployment

This stack can run the Blender and Roblox MCP services on a separate host. Only
Caddy publishes ports 80/443; the MCP containers have no host ports and are
reachable only on the Compose network. The user's computer needs the existing
agent and its tools. Direct Roblox edits use the user's existing Roblox Studio
session and native MCP; Blender runs in the remote server image, so no local
Blender install or RGA server is required. Claude Code connects to remote
Blender authoring and leaves its native Studio MCP configuration untouched.
This deployment's Roblox MCP is an optional artifact builder for compatible
agent setups that already expose it.

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

Caddy obtains and renews TLS certificates. It forwards POST `/mcp` and GET
`/artifacts/*` for Blender, and POST `/mcp` and GET `/downloads/*` for Roblox. The Blender health endpoint
and every other route stay private. Caddy preserves MCP and authorization
headers; request bodies are capped at 2 MB for Blender calls and 28 MB for
Roblox MCP calls. The service handlers apply their own stricter tool-specific
limits. Pin and review the image versions before exposing this stack to agent
clients.

## Abuse controls

The bundled `Caddyfile` limits request size per route and bounds how long a client
may take to send its headers (10 s) and body (120 s), and each service also drops a
client that stalls for 30 s. Each service admits only a few simultaneous requests
(Blender 8, Roblox 2), so a flood of valid connections can still queue legitimate
ones. The stock Caddy image has no per-client rate limit; if the endpoints are
reachable by untrusted networks, add one at your edge (a firewall, a managed proxy
or a Caddy build with a rate-limit module). Authentication happens before any body
is read, and every endpoint requires its own bearer token.

## Connect an existing agent

For browser delivery, set `RGA_ROBLOX_DOWNLOAD_ORIGIN=https://<ROBLOX_DOMAIN>`
in `roblox.env` on the service host. The authenticated agent can then call
`rga_build_place_download` with the same recipe and rules as `rga_build_place`.
Give the returned private link to the requesting user. Anyone holding it can
download that one file for 15 minutes without the service credential. Each
server process holds at most 64 MiB or 256 files. Restarting it clears links.
Use a single Roblox backend for this route and omit download paths from proxy logs.

The Blender service returns a separate 15-minute signed URL for each generated
GLB. The unified Compose deployment sets `BLENDER_MCP_PUBLIC_ORIGIN` from
`BLENDER_DOMAIN`; standalone Blender deployments should set it to their public
HTTPS origin. Do not record `/artifacts/*` request paths or query strings in
reverse-proxy access logs. Claude downloads only the model data into a folder
already approved by the user's native Studio MCP, then uses that existing
connection's Open Cloud upload tool after the user's approval. The current
Open Cloud model upload limit is 20 MB; the optional RGA Roblox MCP is not
required for this path.
Compare the receipt's `artifact_sha256` with the downloaded bytes before any
Studio MCP upload.

An agent environment using both RGA hosted services can configure its MCP
client with these Streamable HTTP URLs and matching bearer credentials:

```text
https://<BLENDER_DOMAIN>/mcp
https://<ROBLOX_DOMAIN>/mcp
```

For Claude Code, follow the [Claude integration guide](../../../docs/integrations/claude-code.md).
It configures only remote Blender authoring and leaves Claude's native Roblox
Studio MCP untouched. The separate RGA Roblox MCP is not added to Claude.

Build the portable skill archive from the repository root with
`python tools/package_agent_skills.py --archive dist/rga-agent-skills.zip`, then
install/import it in the agent's own skill system. Do not install Blender,
Roblox Studio, or the RGA API on the player's computer for the direct MCP
workflow. The optional local API/operator panel is a separate deployment choice.

Use `docker compose ps` on the host to confirm both containers are healthy; the
`/healthz` endpoints are intentionally private and are not reachable through
Caddy. Then verify both MCP tool lists through the actual agent MCP client,
starting with read-only contract checks before building and inspecting a
non-published artifact. Cloud writes and test-place publication remain disabled
until the isolated Roblox target and rollback evidence are recorded in
[ADR-0015](../../../docs/architecture/adr/0015-disposable-world-validation.md)
and [ADR-0018](../../../docs/architecture/adr/0018-remote-roblox-map-authoring.md).

The deployment pins Caddy 2.11.8, which includes the request size limiter. See the
[official Caddy directive documentation](https://caddyserver.com/docs/caddyfile/directives/request_body).
