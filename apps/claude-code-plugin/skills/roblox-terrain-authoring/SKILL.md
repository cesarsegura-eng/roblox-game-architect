---
name: roblox-terrain-authoring
description: Create bounded Roblox voxel terrain from biome, route, heightfield, and material plans through the user's existing native Studio MCP.
---

# Roblox terrain authoring

Use this skill when a Roblox map needs hills, cliffs, valleys, rivers, beaches,
marsh, caves, or another voxel terrain form. Read
`references/terrain-recipes.md` before changing `Workspace.Terrain`.

This skill uses Roblox Studio's existing native MCP connection. It does not add
an MCP server, install the optional RGA Studio plugin, or require a program on
the user's computer beyond the Studio they already use.

## Workflow

1. Discover the connected Studio instances with `list_roblox_studios`. Confirm
   the requested place and inspect its edit/play state before selecting its
   `studio_id`. Use `search_game_tree` and `inspect_instance` to inspect Terrain
   and the intended work area. Never assume the active window or target place.
2. Use `http_get` to read the current Roblox Terrain and Engine API references
   when an API detail is uncertain. Use the native `skill` tool for relevant
   Studio guidance when available.
3. Plan a concrete, bounded terrain patch. State its world-space bounds, voxel
   resolution, approximate voxel count, materials, height transitions, water,
   and the playable route before writing anything. Snap bounds to the 4-stud
   terrain grid. Prefer existing empty space or a disposable copy. Do not clear
   or replace an existing region unless the user explicitly requested that
   change and reviewed its exact bounds.
4. Choose the least complex native API that can express the plan. Use bounded
   `Terrain:FillBlock`, `FillBall`, `FillCylinder`, or `FillWedge` operations
   for modular landforms. Use `WriteVoxels` only when a planned heightfield or
   material transition needs per-voxel data. For a repeatable small heightfield,
   start from the reviewed Luau template in `references/terrain-recipes.md` and
   change only its named configuration values. Read that reference for limits
   and construction checks.
5. Present the exact operation, target place, bounds, and voxel budget for
   review before applying terrain changes. Run the reviewed operation through
   the existing Studio MCP `execute_luau` tool using its documented edit data
   model. Do not route this work through an RGA Roblox MCP or local plugin.
6. Inspect the changed region with `inspect_instance` and `screen_capture`.
   Check the route from player height, terrain edges, waterline, materials,
   collision, spawn safety, and whether the next landmark remains visible.
   Use `character_navigation` and a disposable playtest when those tools and a
   safe test copy are available. Report exactly which checks ran.
7. Keep vegetation, buildings, trails, lighting, sound, and gameplay as
   coordinated passes. Terrain generation does not prove ecology, art quality,
   navigation, performance, or production readiness.

## Deliverable

Return the terrain plan, target `studio_id` and place name, changed bounds,
algorithm and materials, voxel count, and the actual inspection/playtest
results. If the connection lacks `execute_luau`, use only the capabilities it
does expose or provide a clear Terrain Editor handoff; do not create another
Roblox connection to fill the gap.
