---
name: blender-scene-authoring
description: Create modular game-environment and prop blockouts in Blender from validated scene recipes, then export assets for Roblox Studio.
---

# Blender scene authoring

Use this skill when a task needs Blender geometry, a map blockout, modular
architecture, props, materials, scene organization, or a Roblox-ready model
export. Combine it with `world-environments` for any playable location and with
`character-modeling-animation` for characters.

The project exchanges declarative JSON scene recipes with its Blender extension.
Read `references/scene-recipes.md` for the exact schema and limits. Version 2
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
6. Use the remote Blender MCP to create the `.glb` artifact. When the configured
   Roblox MCP asset handoff is available, show its recipe and digest and wait
   for per-call approval before persistent asset creation. Build with the
   approved asset ID and report moderation or runtime status accurately. If
   remote handoff is unavailable, return the artifact and state that it has not
   been ingested into Roblox. Do not make local Blender or any program other than Roblox
   Studio a user prerequisite, or upload, publish, or overwrite assets without approval.

## Roblox constraints

Use Blender's Z-up scene convention and keep scale explicit. Follow Roblox's
current mesh budgets, watertightness, thickness, UV, texture, rig, and export
requirements for the particular asset type. Requirements differ between ordinary
environment meshes, avatar bodies, and accessories; consult the relevant official
Creator Hub page before creating those specialized assets.

Author reusable modules and unique hero assets separately. For repeated
environment pieces, preserve a reusable asset identity so the Studio workflow
can duplicate instances instead of importing equivalent copies as unique assets.
Profile the assembled place to catch mesh density, shadows, and transparency
costs; a triangle estimate alone is not a performance result.
