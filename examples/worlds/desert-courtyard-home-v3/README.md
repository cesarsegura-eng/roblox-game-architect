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

The version 3 recipe adds a warm afternoon Roblox Lighting profile, a low-haze Atmosphere, and sparse clouds. The script-free Roblox place builder writes these settings to the generated place file.
