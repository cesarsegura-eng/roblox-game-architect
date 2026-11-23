---
name: blender-scene-authoring
description: Create modular game-environment and prop blockouts in Blender from validated scene recipes, then export assets for Roblox Studio.
---

# Blender scene authoring

Use this skill when a task needs Blender geometry, a map blockout, modular
architecture, props, materials, scene organization, or a Roblox-ready model
export. Combine it with `world-environments` for any playable location and with
`character-modeling-animation` for characters.

The project exchanges declarative JSON scene recipes with its remote Blender
MCP service. Read `references/scene-recipe-v3.schema.json` as the authoritative
contract and `references/scene-recipes.md` for examples and limits. Version 2
supports allowlisted primitives and bounded polygon meshes made from explicit
vertices and faces, plus simple materials. Version 1 recipes remain importable.
Do not put Python, drivers, expressions, or arbitrary scripts in a recipe.

## Workflow

1. Choose whether the request needs a playable blockout, modular kit, hero prop,
   or final-ready mesh. Be clear about the level of finish.
2. Treat recipe locations and scale as Roblox studs. Use Blender's unscaled
   unit system (`None`) and keep the service-side Roblox importer or build
   harness on the matching scale. If a service operator chooses to inspect a
   GLB in Studio, set the Importer **Scale Unit** to **Studs**. Establish
   silhouette, primary forms, camera distance, and object budget before adding
   detail. Prefer reusable parts and named collections.
3. Give scene objects meaningful names and semantic roles. Keep the generated
   collection separate from user-authored content; never clear a user's scene.
4. Use simple materials with deliberate palette and roughness. If a scene needs
   complex UVs, sculpting, image textures, or node graphs,
   flag the need for a subsequent artist workflow rather than faking it with
   hundreds of primitives.
5. Inspect silhouette, scale, pivots, normals, and material assignment. Test the
   selected export in Blender before handing it off.
6. If direct Studio MCP tools are available, inspect their schemas for native
   `generate_mesh`, `generate_material`, and `generate_procedural_model` support.
   These can create meshes, materials, or assembled primitive models directly
   in the open Studio place; wait for `wait_job_finished` when that workflow
   returns a job. For an existing catalog item, use native `search_asset` to
   find Creator Store or Creator Inventory candidates; inspect the result and
   its descendants for fit and embedded scripts before `insert_asset`. Follow
   each tool's permission, approval, and asset-persistence rules. Respect
   catalog licensing, then inspect the result in Studio. Prefer native Studio
   generation or approved catalog assets when the result should be authored
   directly in the open place.
   Prefer the remote Blender MCP when the task needs recipe-controlled geometry,
   reusable modular assets, scene organization, or a skinned and animated GLB.
   These paths complement each other and neither makes an uninspected result
   production-ready.
7. Use the remote Blender MCP to create the `.glb` artifact. When the receipt
   includes `artifact_download_url`, treat it as a secret, short-lived
   capability for that artifact and download it directly into a user-approved
   Studio MCP upload folder. Compare the downloaded file's SHA-256 with
   `artifact_sha256` from the Blender receipt; reject a mismatch before showing
   the recipe or asking for per-call approval. Use the user's existing native
   Studio MCP `open_cloud_invoke` upload flow if available; Roblox documents a
   20 MB per-file limit in its [Assets usage guide](https://create.roblox.com/docs/cloud/guides/usage-assets).
   RGA's separate server-side model upload route uses a lower 19 MiB cap. When
   using `open_cloud_invoke`, first confirm the open place belongs to a
   published, dedicated test experience: unpublished local places cannot grant
   per-game Open Cloud upload permissions. If no isolated published test
   experience exists, keep the GLB local and leave asset upload pending; do not
   use a production experience as a substitute. If the native MCP exposes
   `skill`, load Roblox's `rbx-permissions` and
   `rbx-import-asset` skills before uploading. Let Studio's current guidance
   handle permission scopes, approved folders, moderation, and import
   adjustments; retain RGA's artifact digest and provenance checks around that
   workflow. Do not add a second
   Roblox MCP connection. A specialized RGA Roblox asset handoff may be used
   only when it is already exposed by the agent's configured tools. If no
   signed URL or other supported handoff is available, return the artifact ID
   and say that it has not been ingested into Roblox. The user's computer does
   not need Blender or an RGA runtime. Never upload, publish, or overwrite
   assets without approval.

For visual review, request `include_preview: true`. Use the optional
`preview_mode: "cutaway"` for rooms, courtyards, and other roofed architecture;
the service hides recipe objects with the `roof` role only while rendering the
preview, then restores them before exporting the complete GLB. Use the default
`isometric` mode for a whole-scene silhouette check.

## Roblox constraints

Use Blender's Z-up scene convention and keep scale explicit. Follow Roblox's
current mesh budgets, watertightness, thickness, UV, texture, rig, and export
requirements for the particular asset type. Requirements differ between ordinary
environment meshes, avatar bodies, and accessories; consult the relevant official
Creator Hub page before creating those specialized assets.

Author reusable modules and unique hero assets separately. For repeated
environment pieces, preserve a reusable asset identity so the Studio workflow
can duplicate instances instead of importing equivalent copies as unique assets.
For ordinary environment meshes, keep each mesh below Roblox's general 20,000-
triangle ceiling; avatar bodies and accessories have separate specifications.
Prefer much lower budgets for repeated props and low-end devices. Use embedded
PNG or JPEG textures no larger than Roblox's 4096×4096 import maximum; choose
lower resolutions when the object size and detail allow it. Keep geometry
watertight and give surfaces thickness. The current RGA GLB upload checks each
glTF primitive against the per-imported-MeshPart triangle ceiling. It also
validates embedded accessor ranges and alignment, vertex strides, index ranges,
finite positions, paired skinning attributes, Roblox's four-influence-per-
vertex cap, and animation channels and key data. For textures it checks
embedded PNG chunk checksums, PNG/JPEG structure and dimensions, and fully
decodes bounded image pixels with Pillow 13.0.0 in the remote asset service.
This path is optional and its dependency stays on the service; native Studio
MCP imports use their own validation. These checks do not certify watertightness,
surface topology, visual or animation quality, successful moderation, or Studio
rendering; verify those against Roblox's current import rules. Profile the
assembled place to catch mesh density, shadows, physics, texture memory, and
transparency costs; a triangle estimate alone is not a performance result.

Use `references/research-sources.md` for the official Blender, glTF, Roblox
import, mesh, texture, rigging, and performance references. For changing
platform requirements, consult current Creator Hub documentation with the host
agent's available search or documentation tools before export.
