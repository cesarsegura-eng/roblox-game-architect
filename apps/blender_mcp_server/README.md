# Remote Blender MCP service

This service runs Blender on a separate server, exposes one restricted MCP tool,
and stores generated GLB artifacts for authenticated download. The Roblox Game
Architect user's computer does not need Blender installed. The server deployment
does need Blender 5.2.3; the included Docker image downloads Blender from the
official Blender release host and verifies its published SHA-256 checksum.
Each isolated Blender worker imports and registers the RGA extension before it
builds the validated recipe, so remote MCP generation exercises the same
extension code as the optional interactive workflow.

The endpoint accepts the standard MCP `2025-11-25` initialize handshake used
by existing MCP clients, as well as the project's stateless `2026-07-28`
request envelope. It is a JSON-only Streamable HTTP endpoint: it does not open
an SSE stream or retain MCP sessions. Clients should connect to the HTTPS
`/mcp` URL through a trusted TLS reverse proxy and use the fixed
`rga_apply_scene_recipe` tool.

## Deploy with Docker Compose

Run these commands on the server that will host the Blender worker:

```sh
cd apps/blender_mcp_server/deploy
cp server.env.example server.env
```

Set `BLENDER_MCP_BEARER_TOKEN` in `server.env` to a unique random secret of at
least 32 characters. Then build and start the service:

```sh
docker compose up --build -d
```

The service binds to `127.0.0.1:8788`. Put a TLS reverse proxy in front of it
and expose only `/mcp` and `/artifacts/<uuid>.glb`. The container health check
uses the internal `/healthz` endpoint; keep that endpoint private. Preserve the
`Authorization`, `MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name` request
headers, plus `Content-Type` and `Accept`. Do not expose the container port
directly to the public internet. Restrict proxy access to the Roblox Game
Architect API host.

The Compose volume stores artifacts and the idempotency ledger across restarts.
Artifacts expire after seven days, and the service caps artifact storage at 2
GiB and each GLB at 64 MiB. Each Blender process has a three-minute timeout and
a 4 GiB address-space limit; the service accepts at most eight concurrent HTTP
requests and serializes scene builds. Compose runs the container read-only,
drops Linux capabilities, disables privilege escalation, limits the process
count, and provides a bounded non-executable temporary filesystem for builds.

## Connect the API

Configure the Roblox Game Architect API process with:

```text
BLENDER_MCP_URL=https://blender.example.com/mcp
BLENDER_MCP_BEARER_TOKEN=<same secret as on the Blender server>
```

The API sends a validated, data-only Scene Recipe through the fixed
`rga_apply_scene_recipe` tool. It receives a receipt, then fetches the GLB by
artifact ID from the same server. The operator downloads the resulting GLB and
imports it into Roblox Studio. No generated Python, arbitrary `bpy` commands,
or filesystem paths are sent through MCP.

Scene Recipe v2 and v3 can include up to eight generic humanoid character entries with
`WALK`, `RUN`, `JUMP`, or `IDLE` motion, scale, and placement. The worker creates their fixed
trusted rig and rigidly weighted blockout meshes, then exports skin and
animation data with the same GLB. These are modeling and motion blockouts, not
production anatomy or Roblox R15 avatar rigs.

V3 Roblox environment settings remain part of the validated recipe, but GLB does
not carry Roblox `Lighting`, `Atmosphere`, or `Terrain.Clouds` configuration.
The Roblox place-build service applies them to its script-free `.rbxlx` artifact
from the same recipe; use that artifact when the requested mood needs to arrive
in Studio.

Design guidance lives in the Roblox Game Architect agent's dedicated
`blender-scene-authoring`, `world-environments`, and
`character-modeling-animation` skillpacks. Those skillpacks guide recipe
generation for biomes, atmosphere, architecture, interiors, exteriors, and
character movement. This server is the remote execution tool for approved
recipes; it does not require Blender or the extension on the user's computer.

The API must be able to reach the service over HTTPS. Use a trusted certificate
and keep the bearer token in server-side secret storage. `BLENDER_MCP_ALLOWED_ORIGINS`
may be set to a comma-separated allowlist if browser-origin traffic is expected;
the API's server-to-server requests do not send an Origin header.

## Automated runtime check

The `blender-mcp-container` CI job builds the image, starts it with a temporary
credential, and runs `tools/smoke_remote_blender_mcp.py` against the live MCP
endpoint. The smoke scene adds WALK and IDLE characters to a curated environment
fixture, downloads the resulting GLB through the production client, and checks
for meshes, skins, and animations. Local execution requires Docker and Blender
is supplied by the image; the user's Roblox Game Architect machine does not need
a Blender installation.

## Run without Docker

For development, install the project package and set `BLENDER_EXECUTABLE`,
`BLENDER_MCP_BEARER_TOKEN`, and `BLENDER_MCP_OUTPUT_DIR`, then run:

```sh
python apps/blender_mcp_server/server.py
```

Use a reverse proxy with TLS for any non-loopback deployment. The built-in
server intentionally speaks plain HTTP so TLS can be handled by the trusted
proxy. Do not run it with an untrusted recipe source or expose it without
authentication.
