"""Trusted Blender background worker; recipe contents are data, never code."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    options = parser.parse_args(args)

    sys.path.insert(0, str(options.project_root / "apps" / "blender-addon"))
    import rga_scene_builder as addon
    from rga_scene_builder.character_tools import CHARACTER_OBJECT_COUNT

    # Load the project extension in every isolated Blender worker so server-side
    # builds exercise the same registered extension code as a Blender 5.2 user.
    addon.register()
    recipe = addon.parse_recipe(options.recipe.read_text(encoding="utf-8"))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # Scene Recipe coordinates are Roblox studs. Make the conversion contract
    # explicit instead of relying on Blender's startup defaults.
    units = bpy.context.scene.unit_settings
    units.system = "NONE"
    units.scale_length = 1.0
    units.system_rotation = "DEGREES"
    created = addon._build_recipe(bpy.context, recipe)
    expected = (
        len(recipe["objects"])
        + len(recipe.get("lights", []))
        + CHARACTER_OBJECT_COUNT * len(recipe.get("characters", []))
    )
    if created != expected:
        raise RuntimeError("Blender created an unexpected object count")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = next(
        (obj for obj in bpy.context.scene.objects if obj.type == "MESH"), None
    )
    bpy.ops.export_scene.gltf(
        filepath=str(options.output),
        export_format="GLB",
        use_selection=True,
        export_lights=True,
        export_animations=True,
        export_skins=True,
    )
    options.result.write_text(
        json.dumps({"created_objects": created}, separators=(",", ":")), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
