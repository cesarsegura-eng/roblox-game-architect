# Scene recipe v2

The current authoring schema is `packages/core/schemas/scene-recipe-v3.schema.json`.
The core parser and Blender's dependency-free validator mirror it. Both still
accept the older v1 and v2 geometry formats.

Recipes are JSON data: a version, scene name, units, bounded objects, lights,
and optional character blockouts.
Each object has a name, semantic role, transform, and exactly one geometry form:

- `primitive`: one allowlisted built-in shape.
- `mesh`: 3–2000 local-space vertices and 1–2000 polygon faces. Vertex
  coordinates are limited to ±1000 Blender units; each face references 3–32
  unique in-range integer indices.

Recipe v2 and v3 roles describe scene use, not geometry class. For house and settlement
blockouts, use `exterior`, `entry`, `courtyard`, `interior`, `roof`, `opening`,
and `furnishing` on distinct forms when the brief asks for those spaces. A role
does not create a doorway or a room by itself: geometry and placement must make
the threshold and circulation legible.

Optional bevel, smooth shading, and a simple RGBA/roughness material are also
supported. Mesh recipes can describe custom low-poly silhouettes such as
faceted rocks, roof gables, cliffs, and stylized props. Optional `characters`
entries define a generic humanoid blockout by name, location, scale, and either
a `WALK`, `RUN`, `JUMP`, or `IDLE` action. Each entry creates a fixed skeleton and 16 rigidly
weighted body meshes. This is not production anatomy, deformation-ready skinning,
or a Roblox R15 rig. Recipes still cannot describe arbitrary bone data,
expressions, or custom motion curves.

Recipe v3 adds a strict, bounded Roblox environment block: ambient and outdoor
color, brightness, time of day, exposure, shadows, Atmosphere color/decay and
scattering parameters, and optional dynamic cloud cover. The script-free Roblox
place builder writes these to the Lighting service and Terrain; GLB geometry
exports do not carry those Roblox-specific environment settings, so review and
use the `.rbxlx` artifact when the requested mood depends on them.

The recipe is not an arbitrary Blender command language. It cannot create
scripts, Python drivers, filesystem paths, network requests, modifiers with
executable parameters, or publish actions. Geometry is built into a dedicated
generated collection. The remote Blender MCP returns a `.glb` artifact; use the
configured, separately approved Roblox asset handoff when available. Optional
Studio inspection is an operator review path, not a requirement on the end
user's computer.

When producing a recipe:

- use a small coherent modular set before scattering details;
- use custom meshes where silhouette matters, and primitives for simple pieces;
- keep faces planar and indices valid; avoid degenerate or self-intersecting
  geometry;
- keep names unique and short, use semantic roles, and keep coordinates in range;
- reserve Blender's Z axis for up and document export-axis conversion;
- keep object and triangle budgets appropriate to Roblox runtime limits;
- state clearly when topology, UVs, rigging, or animation need an artist pass.
