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
Agents can set `include_preview: true` to receive an additional 512x512 PNG
isometric inspection image in the MCP response. The preview uses fixed
service-side camera and lighting, comes from the same validated recipe as the
GLB, and is not persisted with the artifact. Set `preview_mode: "cutaway"`
with `include_preview: true` to temporarily hide recipe objects whose role is
`roof` in the preview. The roof is restored before the GLB is exported, so the
downloaded model remains complete. Cutaway previews help inspect courtyards and
interiors while keeping the exported architecture intact.

## Deploy with Docker Compose

Run these commands on the server that will host the Blender worker:

```sh
cd apps/blender_mcp_server/deploy
cp server.env.example server.env
```

Set `BLENDER_MCP_BEARER_TOKEN` in `server.env` to a unique random secret of at
least 32 characters. Set `BLENDER_MCP_PUBLIC_ORIGIN` to the public HTTPS origin
(for example, `https://blender.example.com`) to return a 15-minute download
link with each artifact receipt. Leave it empty when no browser or agent-side
download flow is deployed. Then build and start the service:

```sh
docker compose up --build -d
```

The service binds to `127.0.0.1:8788`. Put a TLS reverse proxy in front of it
and expose only `/mcp` and `/artifacts/<uuid>.glb`. The container health check
uses the internal `/healthz` endpoint; keep that endpoint private. Preserve the
`Authorization`, `MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name` request
headers, plus `Content-Type` and `Accept`. Do not expose the container port
directly to the public internet. Restrict bearer-authenticated MCP calls to
trusted clients. The artifact links are separate short-lived capabilities for
one UUID-addressed GLB; do not log their request paths or query strings at the
reverse proxy. They never reveal the MCP bearer token and expire after 15
minutes.

The Compose volume stores artifacts and the idempotency ledger across restarts.
Artifact downloads are denied after seven days; expired files are physically
pruned at startup or before a later build. The service caps artifact storage at
2 GiB, 4,096 files, and 64 MiB per GLB. Each Blender process has a three-minute
timeout and a 4 GiB address-space limit; the service accepts at most eight
concurrent HTTP requests and serializes scene builds. Compose runs the container
read-only, drops Linux capabilities, disables privilege escalation, limits the
process count, and provides a bounded non-executable temporary filesystem for
builds.
On startup and before builds, the service removes UUID-named GLBs left without
ledger rows by an interrupted write. It keeps ledger entries when unlinking
fails and rejects a build if cleanup cannot enforce the storage cap.

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

For direct agent-authored Blender iterations, set `include_preview: true` in
the MCP tool call and inspect the returned image before revising or handing off
the final GLB. This checks Blender composition only; it does not replace Roblox
Studio import, collision, material, or gameplay review.

To verify the interior cutaway path during local development, run
`python tools/smoke_blender_cutaway_mcp.py <Blender executable>`. The smoke
starts a temporary MCP server on `127.0.0.1`, generates a fresh ephemeral
bearer token, requests the Desert Courtyard Home preview through the MCP client,
downloads the GLB, and confirms the roof remains in the exported scene. Its
preview must also differ from the isometric roof view. Its artifact store is
temporary. This developer check uses an installed local Blender binary;
end-user agents use the separately hosted Blender MCP instead.

Every artifact receipt includes its lowercase SHA-256. The API preserves that
digest in the audit record and response, and the operator verifies the
downloaded bytes before offering the GLB file.

For the user's existing native Roblox Studio MCP workflow, set the public
origin so the Blender tool receipt includes a temporary artifact link. The
agent can download that exact GLB into a folder the user has already approved
for Studio MCP uploads, then use Studio's existing `open_cloud_invoke` asset
upload capability after the user's explicit approval. This transfers a model
file only; it does not install Blender or another Roblox connection. Roblox's
current Open Cloud asset upload limit is 20 MB per asset, so larger GLBs need a
reduced or rebuilt recipe before that path can be used. Do not log or share the
temporary link; it grants access to that one artifact until it expires.

Scene Recipe v2 and v3 can include up to eight generic humanoid character entries with
`WALK`, `RUN`, `JUMP`, or `IDLE` motion, scale, and placement. The worker creates their fixed
trusted rig and rigidly weighted blockout meshes, then exports skin and
animation data with the same GLB. These are modeling and motion blockouts, not
production anatomy or Roblox R15 avatar rigs.

V3 Roblox environment settings remain part of the validated recipe, but GLB does
not carry Roblox `Lighting`, `Atmosphere`, or `Terrain.Clouds` configuration.
The Roblox place-build service applies them to its script-free `.rbxlx` artifact
from the same recipe. The worker also omits Blender light nodes from the GLB so
it does not emit `KHR_lights_punctual`, which the Roblox asset preflight rejects;
use the place artifact when recipe lighting needs to arrive in Studio.

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

The `blender-mcp-container` CI job builds the image and first runs
`tools/smoke_blender_extension.py` inside Blender. That smoke exports a JPEG-
textured GLB, imports it back into Blender, and applies the exact Roblox asset
preflight to check texture, rig, skin, and animation structure. It verifies the
imported 16x8 image has decoded pixels after the source image is removed from
the Blender scene. The job then
executes `tools/smoke_blender_cutaway_mcp.py` in the same pinned Blender image.
That smoke starts a loopback-only MCP server, requests cutaway and isometric
previews through the production client, checks that the images differ, then
downloads and validates the GLB while confirming the hidden roof is restored.
The job next starts the MCP service with a temporary credential and runs
`tools/smoke_remote_blender_mcp.py` against its live endpoint. The MCP smoke
adds WALK and IDLE characters to a curated environment fixture, downloads the
GLB through the production client, and checks meshes, skins, animations, the
receipt SHA-256, and Roblox asset preflight. Local execution requires Docker;
Blender is supplied by the image, so the user's Roblox Game Architect machine
does not need a Blender installation.

## Run without Docker

For development, install the project package and set `BLENDER_EXECUTABLE`,
`BLENDER_MCP_BEARER_TOKEN`, and `BLENDER_MCP_OUTPUT_DIR`, then run:

```sh
python apps/blender_mcp_server/server.py
```

When the local server uses plain HTTP on loopback, leave
`BLENDER_MCP_PUBLIC_ORIGIN` unset. The MCP client can still download the
artifact by ID with its bearer token, but the receipt will not contain a
public download link. Signed links are emitted only when this value is an
HTTPS origin without a path and the agent's MCP URL uses the same host. For the
native Studio upload handoff, configure the public HTTPS origin on the remote
service behind its TLS reverse proxy; do not set it to a local `http://` URL.

Use a reverse proxy with TLS for any non-loopback deployment. The built-in
server intentionally speaks plain HTTP so TLS can be handled by the trusted
proxy. Do not run it with an untrusted recipe source or expose it without
authentication.
