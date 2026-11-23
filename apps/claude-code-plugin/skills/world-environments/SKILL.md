---
name: world-environments
description: Plan playable game worlds from biome, climate, landform, ecology, culture, architecture, and environmental storytelling.
---

# World environments

Use this skill when planning a biome, map, settlement, building, interior, exterior,
or the atmosphere of a game location. Produce a coherent place the player can
navigate, read, and remember; do not make a collection of unrelated scenery.

Read `references/biomes-and-levels.md` for the compact biome matrix and
`references/playable-spaces.md` for layout, interiors, and ambience patterns.
When a brief names a cloud forest, seasonal tropical forest, chaparral,
volcanic terrain, floodplain, estuary, reef, or cave, use the matching entry in
the specialized-settings section and attach a regional source before choosing
species, architecture, or seasonal details.
For direct Roblox lighting, clouds, particles, and sound, also read
`references/environment-effects.md`. Use these as reasoning guides, not as
fixed recipes.

## Research before making regional claims

If a brief names a real place, culture, species, climate, or historical period,
use the host agent's available web-search and page-fetch tools before deciding
its ecology or architectural details. Prefer local government and university
field guides, ecoregion or land-cover datasets, conservation agencies, and
peer-reviewed research. Check the source's region, date, season, and scale; a
global biome overview does not establish local species, building forms, or
weather. Follow citations to the underlying study when an overview makes a
specific claim. Record the source URLs and the design decisions each supports
in the plan or its research notes. Keep the design original: references inform
ecological and spatial relationships, not copied game maps, asset packs, or
recognizable copyrighted layouts.

If the host agent has no web-search access, keep the location fictional or use
only broad, well-supported biome relationships from the packaged references.
State which regional details still need research; do not invent citations or
present unsupported cultural, ecological, or architectural details as fact.

## Design workflow

1. Establish the player's activity, movement abilities, camera, scale, and the
   intended emotional rhythm. Make the playable route legible before detailing it.
2. Define the environment as a connected system: climate and season, elevation,
   geology and soil, water movement, vegetation layers, animal traces, human use,
   and time/weather. Explain how each choice affects the others.
3. Block out the route with readable silhouettes, focal landmarks, safe and risky
   spaces, meaningful choices, and clear transitions. Check sightlines from the
   player's camera height and movement speed. In Scene Recipe v3, mark walkable
   trails, roads, boardwalks, and traversal platforms with role `path`; use
   connected segments with a consistent width to make the intended route legible.
4. Build settlements from function and climate. Give exterior massing a coherent
   material palette and roof/drainage logic. Give interiors an understandable
   entrance, circulation path, public/private zones, light source, and usable
   interaction space. Keep doorways and furniture scaled to the target avatar.
   Model a doorway as actual empty clearance: split a wall into left/right
   sections and a header, or leave that aperture open in a mesh. The `opening`
   role can mark or frame the threshold; never fill the walk-through volume with
   a solid marker.
   When both inside and outside are requested, block out both as distinct spaces
   connected by an entry/threshold; do not label one undivided shell as both.
5. Tell local history through use and change: wear, repairs, abandoned objects,
   moved furniture, weathering, paths, and resource placement. Make clues
   consistent with the place's people and timeline; avoid random prop clutter.
6. Set atmosphere with a hierarchy of large forms, midground structure, and
   close detail. Use lighting, color, fog, particles, and sound to guide
   attention and signal weather, danger, shelter, or transition without
   obscuring play. Use `environment-effects.md` for direct Roblox authoring.
7. Review navigation and accessibility: contrast, landmark visibility, alternate
   routes, collision, jump distances, and performance on the intended device.
8. Define a sound and lighting pass separately from geometry: distinguish key
   gameplay cues from ambient layers, preview day/weather transitions, and keep
   effects from hiding silhouette or route information. Use the Roblox
   environmental-art curriculum and 3D-art documentation as implementation
   references when producing a Studio-ready map.
9. For a Treasure Hunt build, give each pickup the Scene Recipe role
   `collectible`, make it visually distinct from scenery, and distribute the
   pickups along the route. The built-in gameplay template scores touch
   pickups. Mark lethal touch obstacles with the `hazard` role; the Obby and
   Treasure Hunt templates connect them to server-side Humanoid death and the
   normal Roblox respawn. Neither template adds moving platforms, saved
   progression, or custom scripts.
10. For an Obby Course build, create at least two ordered, connected traversal
    segments with the `path` role, listed in the exact start-to-finish order
    used for checkpoints. Keep every consecutive segment connected; the build
    rejects a route sequence that jumps to a distant segment even when all path
    pieces form one connected group in another order. The fixed `obby` template
    adds sequential checkpoint/respawn pads, stage stats, and session-only wins.
    It supports optional `hazard` role objects; moving platforms, saved
    progression, and custom scripts remain unsupported.
11. Match the deliverable to the tool boundary. Current RGA scene recipes can
   express bounded geometry, simple materials, transforms, and basic lights;
   they do not generate Roblox Terrain voxels. When the brief needs native
   sculpted or procedural Terrain, use the dedicated
   `roblox-terrain-authoring` skill with the user's existing native Studio MCP
   when its documented tools support the work. Foliage systems, audio zones,
   particles, post-processing, and gameplay scripting still need separate
   authoring capabilities; list each as a concrete handoff task instead of
   implying it was generated. Blender and RGA services run remotely. Studio is
   not a prerequisite for generating remote artifacts.
12. For direct Studio ambience, preserve the user's existing native Studio MCP.
   Inspect the connected place and current effect objects, then use its
   documented `execute_luau`, inspection, and screen-capture tools only after
   confirming the target and reviewed scope. Do not create another Roblox MCP
   endpoint to author effects.

For house recipes, use the semantic roles `exterior`, `entry`, `courtyard`,
`interior`, `roof`, `opening`, and `furnishing` where applicable. Give each role
a distinct object or mesh and name it so a reviewer can find the entry, interior
room, roof, and courtyard in the generated collection.

## Output

When a Blender scene recipe is requested, use only the supported schema and
primitives. Treat it as a blockout or stylized modular kit; mark details that need
artist refinement. Avoid copying a recognizable game map or a living culture's
architecture as decoration. Identify real-world references and transform them
into an original, respectful design.
