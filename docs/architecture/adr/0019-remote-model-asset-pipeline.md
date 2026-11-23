# ADR-0019: Remote model asset pipeline

- **Status:** Accepted
- **Date:** 2026-11-05
- **Deciders:** project owner

## Context

The remote Blender MCP creates a reviewable GLB, and the remote Roblox MCP
creates a script-free place from Scene Recipe data. The place builder currently
reduces custom recipe meshes to Part bounds. The GLB is a separate download and
is not included in the generated place, so the current workflow does not carry
Blender geometry all the way into Roblox.

Roblox's Open Cloud Assets API supports creating Model assets from GLB, up to
20 MB per upload. The API returns an asynchronous operation, and uploaded
models are packages containing one or more MeshParts. Asset upload is a
persistent external write and uploaded content can undergo moderation. These
properties require a separate reviewed operation; they must not be hidden
inside map generation. See the [Assets usage guide](https://create.roblox.com/docs/cloud/guides/usage-assets)
and [Assets API reference](https://create.roblox.com/docs/cloud/reference/features/assets).

## Decision

1. Keep Blender execution remote. The API can hand an authenticated,
   size-bounded GLB artifact to a separate Roblox MCP service, and the Roblox
   MCP host can fetch a UUID-addressed GLB from a fixed, authenticated Blender
   MCP host for direct agent workflows. The user's computer does not need
   Blender, an extension, or an asset conversion tool.
2. Add model upload as a distinct, fixed MCP operation. It must accept only a
   validated GLB artifact, a canonical request ID, bounded metadata, and an
   explicit operator approval bound to the artifact SHA-256. Direct MCP upload
   uses a separate prepare/commit flow with a short-lived digest-bound phrase
   and a client-enforced per-call approval prompt. It must not accept arbitrary
   URLs, file paths, asset types, creator IDs, or Open Cloud routes.
3. Keep the Roblox asset credential on the Roblox MCP host. Pin the creator
   account or group in server configuration and scope the key to asset creation
   for that creator. Never grant or reuse a place-publishing credential for
   this operation.
4. Make upload retries idempotent. Persist the request ID and artifact digest
   before the external write. If the outcome is ambiguous, mark it uncertain
   and do not submit the same request again automatically. Poll only a validated
   Open Cloud operation path on the documented Roblox host.
5. Do not treat asset creation as place publishing. Return the resulting asset
   ID, moderation/operation status, artifact digest, and an audit receipt for
   review. Existing assets are never updated by this path.
6. Before model geometry can be included in a generated place, validate a
   separate import step through the Roblox engine on the pinned disposable
   place. Roblox documents `AssetService:LoadAssetAsync()` and identifies
   `SerializationService:DeserializeInstancesAsync()` as available in Open
   Cloud Luau Execution. Use the engine to load the creator-owned Model, walk
   and bound its instance tree, and reject scripts and unsupported classes.
   Serialize only the accepted tree with Roblox's `SerializationService`, then
   test adding that engine-authored `.rbxm` as a `$path` model in the pinned
   Rojo place project. Rojo documents both binary models and filesystem model
   inclusion. Do not assume an uploaded package can be represented by a
   writable `PackageLink`; that instance is documented as non-creatable.
   Binary handoff size, Rojo parse fidelity, content references, and rendered
   output still require isolated runtime proof before enabling this import path.
7. Keep place publishing disabled. Any later publisher is a separate design
   and requires an exact-file digest review, target allowlists, a disposable
   staging import, and verified rollback.

## Consequences

- This closes the architecture gap between remote 3D authoring and Roblox
  assets without asking the end user to install Blender or Studio.
- Creating assets writes to the user's Roblox account/group and can invoke
  Roblox moderation. It therefore needs its own explicit consent and receipt.
- The official upload API is documented as beta and limits a single model
  upload to 20 MB. The server should enforce a lower configurable ceiling and
  reject larger files before decoding or forwarding them.
- The system now has a signed API upload path and a two-step direct MCP upload
  that fetches from a fixed Blender host, plus a bounded Open Cloud
  client. A separate opt-in import prototype loads approved RGA-created Model
  assets in a fixed cloud harness, filters and serializes static MeshParts, and
  feeds the engine-authored model into the Rojo build. Live engine execution,
  real asset receipt, binary handoff, rendered appearance, and final Studio
  workflow remain unproven.

## Acceptance evidence

The final Rojo XML is checked independently of the cloud harness: every
imported MeshPart must be anchored and have explicit positive, finite size
components and finite CFrame components. Duplicate or missing geometry
properties are rejected. This catches a broken serialization handoff; it does
not establish correct alignment, collision shape, texture loading, or visual
appearance. A local synthetic MeshPart passed the binary-model to Rojo-place
handoff on 2026-11-07; its placeholder asset URI was not loaded by Roblox.

- [x] Authenticated, bounded fake-transport tests cover accepted GLB, wrong
  digest, size limit, creator pinning, moderation-pending state, duplicate
  request, digest mismatch, and uncertain external outcome.
- [x] A direct Roblox MCP fake-source/fake-Open-Cloud flow fetches a fixed
  Blender artifact, presents a separate digest-bound confirmation, creates an
  approved test receipt, and leaves asset bytes off the agent-facing request.
- [ ] The deployed Roblox MCP smoke uses a fake Open Cloud transport and does
  not create Roblox assets.
- [ ] A separately approved isolated test-account upload returns a real Model
  asset and reaches an allowed moderation state.
- [ ] A repository-owned cloud task loads that creator-owned Model, enforces
  the class/count/property allowlist, and returns only a bounded Roblox-engine
  serialization without saving or changing the pinned place.
- [ ] Rojo 7.7.1 consumes that serialized model from a generated project path;
  the resulting place contains the expected MeshParts, retains approved mesh
  and texture references, and contains no asset-provided executable instances.
- [ ] Retrieved package contents are validated, merged into a built place, and
  opened in Roblox Studio with the expected MeshParts and no executable
  instances.
- [ ] The generated place's geometry, collisions, and visual appearance are
  reviewed in an isolated test experience before the feature is called
  production-ready.

## Import research update (2026-11-05)

The initial research gap is narrower than the original decision described:
Roblox's current Creator Hub documents `AssetService:LoadAssetAsync()` for
loading a Model and documents `SerializationService` for deserializing RBXM
content in Open Cloud Luau Execution. The `MeshPart` reference documents
`MeshId` and texture content properties. This supports an engine-mediated
inspection prototype, avoiding a custom parser for Roblox's binary model
format. Rojo's v7 project format accepts filesystem model paths, including an
example `.rbxm` under Workspace, and its sync reference lists binary models as
supported input. The sync reference also lists `MeshPart.MeshId` among
real-time sync limitations, so generated-place output must be verified
separately. These contracts do not yet prove the cloud task can return a
bounded serialized model or that Rojo preserves its geometry and content
references. That requires an isolated execution and rendering experiment. See the
[Open Cloud Luau Execution reference](https://create.roblox.com/docs/cloud/reference/features/luau-execution),
[AssetService reference](https://create.roblox.com/docs/reference/engine/classes/AssetService),
[SerializationService reference](https://create.roblox.com/docs/reference/engine/classes/SerializationService),
[MeshPart reference](https://create.roblox.com/docs/reference/engine/classes/MeshPart),
and Rojo's [v7 project format](https://rojo.space/docs/v7/project-format/)
and [v7 sync details](https://rojo.space/docs/v7/sync-details/).

## Import prototype status

The repository now implements the proposed path. The Roblox MCP will accept an
asset ID only when its durable upload ledger contains an approved RGA upload
receipt. A repository-owned fixed Luau harness loads that asset without
parenting it into the DataModel, rejects unsupported classes, clears attributes
and tags, bounds counts and serialized bytes, and returns engine-authored RBXM
as a bounded Base64 result. Rojo receives that fixed file path; the place
builder verifies its binary header, then checks the built XML subtree contains
only the approved static classes, expected MeshPart count, and numeric Roblox
mesh references. The operator web flow offers import only after the asset
receipt reports `approved`, and only for script-free blockout mode. Offline
tests and a live Roblox Cloud task plus rendered output are still required;
this implementation is not yet production-verified.

