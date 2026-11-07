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
Use them as reasoning guides, not as fixed recipes.

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
   When both inside and outside are requested, block out both as distinct spaces
   connected by an entry/threshold; do not label one undivided shell as both.
5. Tell local history through use and change: wear, repairs, abandoned objects,
   moved furniture, weathering, paths, and resource placement. Make clues
   consistent with the place's people and timeline; avoid random prop clutter.
6. Set atmosphere with a hierarchy of large forms, midground structure, and
   close detail. Use lighting, color, fog, particles, and sound to guide attention
   and signal weather, danger, shelter, or transition without obscuring play.
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
    segments with the `path` role. The fixed `obby` template adds sequential
    checkpoint/respawn pads, stage stats, and session-only wins. It supports
    optional `hazard` role objects; moving platforms, saved progression, and
    custom scripts remain unsupported.
11. Match the deliverable to the tool boundary. Current scene recipes can express
   bounded geometry, simple materials, transforms, and basic lights; detailed
   terrain sculpting, foliage systems, audio zones, particles, post-processing,
   and gameplay scripting need later authoring tools or server capabilities.
   List those as concrete handoff tasks rather than implying they are already
   present. The user has Roblox Studio, where the game is made; do not ask
   them to install any other program.

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
