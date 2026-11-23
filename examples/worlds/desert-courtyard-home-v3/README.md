# Desert Courtyard Home v3

A hand-authored blockout recipe that gives an arid courtyard house distinct
exterior, entry, courtyard, interior, opening, roof, and furnishing roles. Its
two lights distinguish harsh outdoor sun from warm interior fill. Use it as a
fixture for the world-environment and Blender-scene-authoring skill packs.

The geometry is deliberately simple and is not a finished architectural asset.
The opening role identifies a doorway lintel; the recipe contract does not
create a complete door system or guarantee playability. Inspect the generated
scene in Blender and refine proportions, circulation, openings, and materials.

Validate from the project root:

```powershell
uv run python tools/validate_scene_recipe.py examples/worlds/desert-courtyard-home-v3/scene-recipe.json
```

To build a separate, unpublished script-free Roblox place for inspection in
Studio, use the pinned Rojo toolchain:

```powershell
uv run python tools/build_roblox_place.py `
  examples/worlds/desert-courtyard-home-v3/scene-recipe.json `
  dist/rga-review-desert-courtyard-house.rbxlx --gameplay-mode blockout
```

The version 3 recipe adds a warm afternoon Roblox Lighting profile, a low-haze
Atmosphere, and sparse clouds. The place builder writes these settings into the
artifact and keeps the recipe as a blockout; the generated file is not a tested
or production-ready house. For the agent workflow, use the user's existing
native Studio MCP and remote Blender MCP when they are available; this local
build command is an optional review path and does not require installing the
RGA Studio plugin.
