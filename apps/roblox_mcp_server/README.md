# Remote Roblox validation MCP

Use `rga_review_game_plan` with a structured game plan to get the required
map roles and build settings. Supply the scene recipe as well to check role
coverage, route constraints and gameplay rules before spending time on a build.
Pass that same reviewed `plan` with the exact `recipe` to `rga_build_place` or
`rga_build_place_download`; the build host rechecks that the selected mode and
rules match the plan and that the recipe satisfies its required roles.
For example, an unreachable win threshold reports both the requested score and
the points available per round. The tool runs on the MCP host with Open Cloud
disabled. A successful review covers the proposed data. Engine playtests
establish whether a player can traverse the map and trigger its mechanics.

Authenticated agents can discover and read curated JSON references through
`resources/list` and `resources/read`. Available `rga://examples/` resources
cover a rainforest scene and playable plan, a desert courtyard home, coastal
architecture, an alpine inn, a mangrove stilt house, gameplay rules, and a
character movement set. Apply the versioned `rga://schemas/` resources when
editing these examples. References show supported input shapes; they are not
proof of gameplay, rig compatibility, or production readiness.

This service runs on a separate server. A bearer token and the bundled Rojo
executable enable `rga_build_place`. The service exposes `rga_validate_map`
when the disposable Open Cloud target is fully configured. With asset-creation
settings it exposes the reviewed Model upload tool; with the fixed Blender
source configured as well, it adds a two-step, server-to-server GLB handoff.
The validator accepts a validated
Scene Recipe and executes the repository-owned `harness.luau` against a pinned
Roblox Open Cloud place version. The builder uses pinned Rojo 7.7.1 to create a
complete `.rbxlx` artifact from the same bounded recipe. The default mode is
script-free. An explicitly selected Treasure Hunt mode requires `collectible`
objects and a `path`; the Obby Course mode requires at least two connected
`path` segments, listed in start-to-finish order with each consecutive pair
connected, and creates checkpoint pads in that sequence. Treasure Hunt tracks
collections per player, resets that player's score after each full set, and
supports repeat rounds with a brief touch debounce. Each mode uses one exact
project-owned server script. Obby stage and win stats are session-only. `rule_game`
accepts a bounded `gameplay_rules` array for touch-triggered score, healing,
temporary speed boosts, nonlethal hazard damage, elimination, and threshold-based wins; the same fixed interpreter handles
every approved rule and rechecks its role, exact fields, and numeric ranges in
the Roblox server runtime. No mode
accepts model-provided Luau.
Recipe JSON is uploaded as Open Cloud binary input; the recipe is never inserted
into executable Luau source. The server does not expose Studio's general MCP
tools or arbitrary scripts. Optional test-place publishing is separately
configured, limited to one disposable target, and requires digest-bound user
approval. A generated place is a separate complete place file, not a merge
into an existing experience.

## Optional cloud validation

Before enabling cloud tools, create a dedicated Roblox test universe and a
disposable place that contain no production scripts, secrets, data stores, or
external integrations. Record the place version to pin. Configure the production
universe and place ID lists as a second guard against accidental target reuse.
Create a server-only Open Cloud key scoped only to Luau Execution task creation
and task/log reads for that test universe.

The environment confirmation is an operator assertion; it is not proof that a
place is isolated or that Open Cloud never persists a task's DataModel changes.
Cloud validation also requires `RGA_ROBLOX_PERSISTENCE_VERIFIED=` set to the exact value
`I_VERIFIED_PINNED_PLACE_NONPERSISTENCE` and a non-empty
`RGA_ROBLOX_PERSISTENCE_EVIDENCE` reference. Set those only after a runtime
exercise against the disposable place has verified the target, pinned version,
task behavior, and absence of production or place-version changes. Keep that
evidence with the deployment record. The checked-in sample leaves IDs,
credentials, and all confirmations empty.

The MCP host rejects requests carrying an unapproved browser `Origin` with
HTTP 403. Leave `RGA_ROBLOX_MCP_ALLOWED_ORIGINS` empty for direct agent clients
that do not send `Origin`; if a trusted browser client is used, set its exact
HTTPS origin in this server-only allowlist. Keep health routes private behind
the trusted proxy.

## Deploy

On the separate server, copy `deploy/server.env.example` to `deploy/server.env`
and generate a unique 32–512 character `RGA_ROBLOX_MCP_TOKEN`. For place builds
alone, leave the cloud target, confirmation, transfer and key fields blank.
When enabling cloud tools, configure the complete disposable target and keep
`ROBLOX_OPEN_CLOUD_API_KEY` only on this server.
Then run:

```sh
cd apps/roblox_mcp_server/deploy
docker compose up --build -d
```

## Optional reviewed Model asset upload

The service can expose `rga_upload_reviewed_model` when asset-creation
configuration is complete. It accepts only bounded GLB 2.0 bytes, a fixed
creator configured on this host, and a five-minute HMAC approval bound to the
artifact digest, metadata, request ID, and approval ID. The Open Cloud key and
approval secret stay on trusted servers. SQLite records the request before the
external write; an ambiguous result is never resubmitted automatically. A
successful operation returns the asset ID and moderation state. Upload creates
a persistent Roblox asset; it does not publish or modify a place. Before any
external request, the host checks each GLTF primitive's accessor counts against
Roblox's 20,000-triangle per-imported-MeshPart ceiling, verifies referenced
accessor ranges and alignment fit the embedded buffer, rejects invalid vertex
strides, validates every standard and custom vertex-attribute reference,
component type, normalization flag, count, and finite value, rejects normalized
float positions and indices outside the position array, and checks non-finite
positions. It caps
vertex accessors at 60,000 elements per mesh and animation accessors at 100,000
elements, including sparse accessors, and caps total accessor elements visited
across the file at 1,000,000 to bound repeated scans of reused accessors. Sparse
substitutions are applied before checking positions, indices, skin data, or
animation values. It rejects
non-finite or unbounded node transforms, invalid mesh/camera/child references,
cyclic or multiply-parented node hierarchies, and TRS animations targeting
matrix nodes. GLTF extension declarations must be well-formed, and extensions
are rejected because compressed or extended geometry/material data is not
decoded by this preflight. GLTF metadata collections are bounded to 16,384
entries each, embedded images to 256, and aggregate texture dimensions to 64
million pixels. For skinned meshes it validates paired joint/weight attributes,
joint references, finite MAT4 inverse-bind matrices whose count covers the skin
joints, affine matrix rows, and Roblox's four-influence limit per vertex. Morph
target accessors, per-mesh target counts, mesh/node weights, and morph-weight
animation dimensions are checked against the base primitive and bounded data.
Animation clips are checked for valid channels, increasing finite key times,
matching output dimensions, and finite output values. Embedded PNG/JPEG textures
are checked for recognized headers and Roblox's 4096-pixel dimension cap. PNG chunk
checksums are verified; JPEG frame, scan, and end-marker structure is checked
before Pillow 13.0.0 fully decodes every unique embedded image source; the
decoder runs sequentially with decompression-bomb warnings treated as errors.
The service container is bounded to 512 MiB and one CPU. Material-to-texture-to-image references
are checked against the embedded GLB tables. This preflight does not prove
watertight geometry, UV quality, texture visual quality, successful moderation,
animation quality, or Studio rendering. Install the optional `roblox-assets`
extra on the remote service; end users do not need Pillow installed locally.
The structural checks follow the [glTF 2.0 skin and morph-target rules](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html)
and Roblox's [mesh and importer requirements](https://create.roblox.com/docs/studio/importer).

For a pending upload, call `rga_check_model_upload` with its original
`request_id`. The host uses Get Asset with the server key's asset read
permission, checks the Model ID, creator and first revision, and records the
moderation decision. Repeated checks after approval or rejection return the
recorded receipt. See the [Roblox Assets API](https://create.roblox.com/docs/cloud/reference/features/assets).

For opt-in deployment, create a separate Open Cloud key with asset-create
permission for the pinned user or group, and set these server-only values:

- `RGA_ROBLOX_ASSET_CREATOR_TYPE` to `userId` or `groupId`
- `RGA_ROBLOX_ASSET_CREATOR_ID` to that creator's numeric ID
- `ROBLOX_OPEN_CLOUD_ASSET_API_KEY` to the asset-scoped key
- `RGA_ROBLOX_ASSET_CREATION_CONFIRMED=I_ACCEPT_ROBLOX_ASSET_CREATION`
- `RGA_ROBLOX_ASSET_APPROVAL_SECRET` to a unique 32-512 character secret held
  on this server (also configure it in the API only if the optional operator
  panel upload route will be used)

For direct use from an agent connected to the hosted MCP services, also set
these server-only values in this Roblox service's `server.env`:

- `BLENDER_MCP_URL` to the fixed Blender MCP HTTPS URL ending in `/mcp`
- `BLENDER_MCP_BEARER_TOKEN` to the Blender service's distinct bearer token
- `RGA_ROBLOX_BLENDER_TRANSFER_CONFIRMED=I_ACCEPT_ROBLOX_MODEL_TRANSFER`
- `RGA_ROBLOX_MODEL_TRANSFER_LEDGER=/var/lib/rga/model_transfers.sqlite3`

The Roblox service fetches only `/artifacts/<uuid>.glb` from that pinned host.
It exposes `rga_prepare_blender_model_upload` as a read-only step; the result
contains the artifact digest, request ID, expiry, and a digest-bound confirmation
phrase. After presenting the source recipe and exact digest to the user, the
agent may call `rga_upload_prepared_blender_model` only after the user explicitly
approves creating that Roblox asset. This second step fetches the same fixed
artifact again and refuses if its bytes changed, the approval expired, or the
digest/phrase does not match. The agent never receives or resends the GLB bytes.
The upload call must remain in `prompt` mode in the connected MCP client; the
digest-bound phrase is a second workflow check, not a substitute for client
approval. Do not expose the persistent upload tool through clients that cannot
require a per-call user approval. An uncertain Open Cloud write is never retried
automatically.

The local operator API can still orchestrate the same server-to-server transfer
with its own review control; it is not required for the direct MCP flow. Asset
creation remains a persistent Roblox write and is separate from place building.
After Roblox reports moderation as approved, pass the returned `asset_id` to
`rga_build_place` to import that model into a separate script-free `.rbxlx`.
The fixed Open Cloud harness accepts only `Model`, `Folder`, `MeshPart`, and
`SurfaceAppearance`, clears attributes and tags, enforces limits of 512
instances, 128 MeshParts, and 512,000 serialized bytes, then returns an
engine-serialized model. Rojo adds it to the generated place, and the API
rechecks the imported subtree, MeshPart references, receipt counts, and place
digest. Imported geometry replaces recipe Part proxies while recipe Roblox
lighting and environment remain. The path is available only in script-free
blockout mode; Treasure Hunt and Obby Course remain unavailable with imported
models. The remote
engine execution and actual mesh appearance have not yet been verified against
the configured isolated place, so treat this as an implementation prototype
until the live acceptance checks in
[`ADR-0019`](../../docs/architecture/adr/0019-remote-model-asset-pipeline.md)
pass. Configure the TLS proxy to accept request bodies up to 28 MB for this
optional tool.

## Publish a reviewed build to the disposable test place

The service can optionally expose `rga_publish_reviewed_place`. This operation
is fixed to `RGA_ROBLOX_TEST_UNIVERSE_ID` and `RGA_ROBLOX_TEST_PLACE_ID`; it has
no caller-selected target. It requires a separate Open Cloud key with only
`universe-places:write`, non-empty production universe/place deny lists, the
explicit `RGA_ROBLOX_PLACE_PUBLISH_CONFIRMED=I_ACCEPT_DISPOSABLE_TEST_PLACE_PUBLISHING`
setting, and an approval secret shared with the operator API. The approval
signature binds a five-minute window to the build digest, request ID, approval
ID, and both target IDs. SQLite records the request before the write; uncertain
outcomes are never automatically resubmitted.

The operator panel reveals this action only when the remote server reports the
fixed tool. It holds the generated artifact server-side for 15 minutes. The
operator must open and inspect the exact downloaded `.rbxlx` in Roblox Studio,
check the review box, and confirm the action. Publishing replaces the place's
published version and can affect players who can access that test experience.
It is not a production publisher. Place files containing `SurfaceAppearance`,
`EditableImage`, `EditableMesh`, `PartOperation`, or `BaseWrap` are rejected
because Roblox documents that Place Publishing does not update those instance
types. The fixed Treasure Hunt, Obby Course, and data-driven rule scripts are
accepted only when their source matches the respective repository-owned
template exactly.

Configure `ROBLOX_OPEN_CLOUD_PUBLISH_API_KEY`,
`RGA_ROBLOX_PLACE_PUBLISH_CONFIRMED`, and
`RGA_ROBLOX_PUBLISH_APPROVAL_SECRET` in the remote service's `server.env`; set
the same `RGA_ROBLOX_TEST_UNIVERSE_ID`, `RGA_ROBLOX_TEST_PLACE_ID`, and
`RGA_ROBLOX_PUBLISH_APPROVAL_SECRET` in the API environment. Keep this feature
disabled until the test target is confirmed disposable, the exact artifact has
been opened in Studio, and restoration of its prior version has been rehearsed.

An existing agent connected directly to this MCP host can use the same pinned
test target without installing Studio. When publication is configured, the
server also exposes `rga_prepare_test_place_publication` and
`rga_publish_prepared_test_place`. A successful `rga_build_place` keeps the
exact publishable artifact and build summary on the remote service for up to 24
hours. The agent first calls the read-only prepare tool with the build request
ID and SHA-256; it returns the exact digest, summary, fixed universe/place IDs,
and a five-minute confirmation phrase. The agent must show those details to the
user and obtain explicit approval before making the second, persistent tool
call with the phrase. The server retrieves the stored bytes and signs the
approval itself; the agent never supplies the place bytes or an approval
signature to the publish tool. The MCP client's per-call approval prompt must
stay enabled. The write remains limited to the configured disposable test
place, and uncertain writes are never resubmitted. This flow does not require a
local API, Blender, Roblox Studio, or an RGA extension on the user's computer.

Direct MCP publication is not a production publishing path. Keep the feature
disabled until the test target is verified disposable, the exact artifact has
been inspected, and restoration of its prior version has been rehearsed.

The service binds to `127.0.0.1:8790`. Put a trusted TLS reverse proxy in front
of it and expose only `/mcp`. Restrict network access to the RGA API host and
registered agent MCP clients where their egress ranges are stable; otherwise
rely on the unique bearer credential, TLS, the bundled proxy's request-header and
body timeouts, and request-size limits. The stock proxy has no per-client rate limit,
so add one at your edge if the endpoint is reachable by untrusted networks. Do not expose port 8790 directly. SQLite keeps request IDs, temporary
build artifacts, approvals, and receipts across restarts. An interrupted or
ambiguous Open Cloud request is marked uncertain and will not be submitted
again for the same request ID.

Configure the API process with `ROBLOX_MCP_URL=https://host.example/mcp` and
`ROBLOX_MCP_BEARER_TOKEN` matching the remote service token. The operator panel
shows remote build and validation actions when this connection is configured.
Build returns a `.rbxlx` file and SHA-256 digest for the operator to inspect or
import; it does not publish or modify a Roblox place.

## What the result means

The host compiles recipe objects through the same geometry conversion used by
the Rojo builder, then sends bounded data to the fixed harness. Position,
rotation, mesh bounding-box offsets, primitive shape, size, and collision flags
therefore agree with the built recipe Parts. The harness creates temporary
anchored parts, checks route navigation with `PathfindingService`, removes its temporary
folder, and returns counts plus the task and place-version IDs. It reports
`structure_only` when fewer than two path features exist, or
`navigation_pass` / `navigation_failed` when a route query runs. It does not
prove final mesh quality, collision behavior for imported GLB assets, gameplay
template behavior, or production playability. The map harness does not run
gameplay templates. The MCP client only accepts the exact selected Treasure
Hunt, Obby Course, or data-driven rule script under `ServerScriptService`, with
no other executable classes.

Navigation queries each consecutive pair of path features in recipe order and
passes only if every query succeeds with waypoints. An upstream timeout is an
error, never a partial navigation pass. The waypoint count is the sum across
successful legs, capped at 512. This does not establish that every gameplay
trigger is reachable.
Spawn pads and gameplay-created instances are not part of this recipe-geometry
check. A navigation pass is consequently narrower than a full level playtest.

Both the cloud adapter and API client check the evidence before accepting a
receipt: path counts must match the submitted recipe, a pass must have enough
waypoints for every route leg, and the declared status must agree with the
connectivity result. With fewer than two path features, only a zero-waypoint,
disconnected `structure_only` result is valid. A failed multi-leg check may
retain waypoints from earlier successful legs, but it remains a failure.
On a failed route, the receipt includes `navigation_failed_leg` with its
zero-based `leg_index` and exact `from` and `to` path names. The operator panel
shows those names and the one-based segment number, giving the agent specific
adjacent path sections to revise. Successful and structure-only receipts carry
a null diagnostic.

Validation request digests include the navigation contract version and pinned
universe, place, and place-version IDs. Changing any target ID requires a new
request UUID; changing only the API key preserves retry behavior. No API key
is included in this digest context or the validation ledger. Requests
cached by the old endpoint-only implementation are rejected on reuse; submit a
new UUID to obtain a fresh result under the updated geometry and route checks.

Local validation covers the MCP contract and fake Open Cloud transport. CI also
starts the built container with a test-only fake validator and exercises its
authenticated initialize, tool-list, and recipe receipt flow; that smoke does
not contact Roblox or count as live place verification. Live Roblox runtime
verification still requires the separately provisioned test place and a scoped
Open Cloud key. A second isolated container smoke uses the pinned Pillow extra
to decode valid PNG/JPEG GLBs and reject a structurally valid but undecodable
JPEG before any Open Cloud request.
