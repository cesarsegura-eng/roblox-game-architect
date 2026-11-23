# Remote Blender MCP integration

Blender runs in a dedicated server environment, separate from the Roblox Game
Architect user's computer. The server-side Blender worker validates a strict
Scene Recipe, builds the scene in a clean background process, and exports a GLB.
The requesting MCP client receives an artifact receipt. If
`BLENDER_MCP_PUBLIC_ORIGIN` is configured, the receipt also includes a signed
15-minute HTTPS download link for that one artifact. Claude Code can download
the model data into a folder already approved by Roblox Studio's native MCP and
upload it through the existing `open_cloud_invoke` flow after the user's
approval. This does not add another Roblox MCP connection or require Blender on
the user's computer. Roblox documents an Open Cloud upload limit of 20 MB per
asset file in its [Assets usage guide](https://create.roblox.com/docs/cloud/guides/usage-assets).
RGA caps its client and server paths at 19 MiB (19,922,944 bytes), including the
signed Blender-to-Roblox transfer; larger GLBs need a reduced or rebuilt recipe
for that path. The optional operator API can also retrieve a reviewed artifact
for download.

Deploy the reference service using the [remote server guide](../../apps/blender_mcp_server/README.md).
Configure the API process with `BLENDER_MCP_URL` and
`BLENDER_MCP_BEARER_TOKEN`. Remote endpoints must use HTTPS and a 32–512
character bearer secret.

The client prefers stateless MCP Streamable HTTP protocol version `2026-07-28`
and supports handshake-based `2025-11-25` servers. It discovers tools,
validates the fixed `rga_apply_scene_recipe` contract, and refuses generic tools
such as `execute_blender_code`. The official Blender Lab server exposes
arbitrary Python execution without guards, so it does not satisfy this
project's remote tool contract by itself ([Blender MCP security note](https://www.blender.org/lab/mcp-server/)).

The reference service accepts only a recipe object and an idempotency UUID. It
validates the recipe against the same contract as the local extension, then
starts a trusted Blender background process with bounded time, memory, and
output. It exposes an authenticated, ID-addressed GLB download for configured
service clients and a signed, time-limited link for the reviewed agent handoff.
Do not record artifact request paths or query strings in reverse-proxy access
logs. The service does not accept source code, arbitrary `bpy` commands,
caller-supplied file paths, or generic execution payloads. Generated scenes are
built in a fresh Blender process, so existing user scenes are not touched.

Scene Recipe v2 and v3 also support bounded humanoid blockouts with a fixed skeleton,
rigid skin weights, and a `WALK`, `RUN`, `JUMP`, or `IDLE` animation preset. The request supplies
only a character name, motion enum, placement, and scale. These assets support
proportion and motion iteration; the generic rig is not an R15 avatar or
production-ready anatomy.

Scene Recipe positions and scales use Roblox studs. The Blender worker keeps an
unscaled unit system so one recipe unit stays one stud; when importing the GLB,
keep Studio Importer's **Scale Unit** set to **Studs**. This matches the
[Creator Hub Blender guidance](https://create.roblox.com/docs/art/blender) and
[Importer settings](https://create.roblox.com/docs/studio/importer). Roblox's
standard GLB path uses the full `.gltf` payload exported by the worker; the
worker exports geometry, skin, and animation data but omits glTF light nodes
(`KHR_lights_punctual`), which the Roblox asset preflight does not accept. Use
the script-free `.rbxlx` artifact for recipe lighting. The Studio proxy uses
the same stud dimensions and preserves object rotation, while reducing each
mesh to an oriented Part bounding box.

The signed artifact URL is tied to the artifact UUID and an expiry no more than
15 minutes in the future. It does not carry the Blender MCP bearer credential.
Treat the URL itself as a temporary secret, keep its query out of logs, and
verify the downloaded file's size and SHA-256 before the native Studio MCP
upload. See Roblox's [Open Cloud with Studio MCP
guide](https://create.roblox.com/docs/studio/mcp-open-cloud) and [asset usage
guide](https://create.roblox.com/docs/cloud/guides/usage-assets) for the current
approved-folder, permissions, and upload-size rules.

The Blender receipt includes the lowercase SHA-256 digest of the completed GLB.
The operator API carries that value into its audit record and response; the web
operator hashes the downloaded bytes and refuses to offer a file whose digest
does not match the receipt. Agent skills must make the same comparison before
using any other artifact handoff. The API operator download route also checks
the bytes against the recent receipt before forwarding the GLB.

The API validates the recipe before sending it and records successful remote
builds in the local operator audit log. The operator reviews the full recipe
and confirms before the remote call. If the server does not confirm the result,
the request UUID allows a safe retry without creating a second artifact.

The client sends per-request metadata and required routing headers for the
modern revision; legacy fallback occurs only when a modern request receives an
unrecognized 400/404 response. Recognized modern protocol errors fail closed.
See the [current transport specification](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/streamable-http.mdx)
and [version compatibility rules](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/versioning.mdx).

This remote MCP service is the standard Blender integration for Roblox Game
Architect. It follows the separate-server pattern used by tools such as REA:
the MCP host owns and runs Blender, while the API connects over authenticated
HTTPS. The user's PC needs neither Blender nor the Blender extension installed.
The extension described in `apps/blender-addon/README.md` remains optional for
people who choose local authoring or manual recipe import.
