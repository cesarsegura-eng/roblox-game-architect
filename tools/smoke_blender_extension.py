"""Smoke-test the RGA add-on inside a real Blender process.

Run from the repository root:
  blender --background --factory-startup --python tools/smoke_blender_extension.py -- \
    --recipe examples/worlds/mistral-coast-lookout-v2/scene-recipe.json \
    --output dist/rga-smoke.glb
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import bpy


def _arguments() -> argparse.Namespace:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(args)


def _glb_json(path: Path) -> dict:
    with path.open("rb") as stream:
        magic, version, total_length = struct.unpack("<4sII", stream.read(12))
        json_length, chunk_type = struct.unpack("<I4s", stream.read(8))
        payload = json.loads(stream.read(json_length))
    if magic != b"glTF" or version != 2 or total_length != path.stat().st_size:
        raise RuntimeError("export is not a valid GLB v2 container")
    if chunk_type != b"JSON":
        raise RuntimeError("GLB does not start with its JSON chunk")
    if not payload.get("skins") or not payload.get("animations") or not payload.get("meshes"):
        raise RuntimeError("GLB is missing mesh, skin, or animation data")
    return payload


def main() -> None:
    args = _arguments()
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "apps" / "blender-addon"))
    import rga_scene_builder as addon

    output = args.output.resolve()
    if output.suffix.lower() != ".glb" or output.exists():
        raise RuntimeError("choose a new, non-existing .glb output path")
    addon.register()
    source = json.loads(args.recipe.read_text(encoding="utf-8"))
    source["characters"] = [
        {
            "name": "Smoke Walker",
            "motion": "WALK",
            "location": [20, 0, 0],
            "scale": [1, 1, 1],
        },
        {
            "name": "Smoke Idle",
            "motion": "IDLE",
            "location": [24, 0, 0],
            "scale": [1, 1, 1],
        },
    ]
    recipe = addon.parse_recipe(json.dumps(source, allow_nan=False))
    built = addon._build_recipe(bpy.context, recipe)
    expected = (
        len(recipe["objects"])
        + len(recipe.get("lights", []))
        + 17 * len(recipe.get("characters", []))
    )
    if built != expected:
        raise RuntimeError(f"recipe import built {built} objects; expected {expected}")

    collection = bpy.data.collections[f"RGA - {recipe['name']}"]
    rigs = [obj for obj in collection.objects if obj.type == "ARMATURE"]
    parts = [obj for obj in collection.objects if obj.get("rga_role") == "character_blockout"]
    if len(rigs) != 2 or len(parts) != 32 or any(part.parent not in rigs for part in parts):
        raise RuntimeError("character blockout has no correctly parented skinned parts")
    if any(rig.animation_data is None or rig.animation_data.action is None for rig in rigs):
        raise RuntimeError("character blockout has no animation action")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in collection.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = rigs[0]
    bpy.ops.export_scene.gltf(
        filepath=str(output),
        export_format="GLB",
        use_selection=True,
        export_animations=True,
        export_skins=True,
    )
    _glb_json(output)
    before_import = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(output))
    imported = [obj for obj in bpy.data.objects if obj not in before_import]
    imported_rigs = [obj for obj in imported if obj.type == "ARMATURE"]
    imported_meshes = [obj for obj in imported if obj.type == "MESH"]
    if (
        not imported_rigs
        or len(imported_meshes) < 10
        or not any(mesh.parent in imported_rigs for mesh in imported_meshes)
        or not any(rig.animation_data and rig.animation_data.action for rig in imported_rigs)
    ):
        raise RuntimeError("GLB round-trip lost its rig, skinning, or animation")
    addon.unregister()
    print(
        f"RGA_BLENDER_SMOKE_OK recipe_objects={built} character_parts={len(parts)} "
        f"characters={len(rigs)} imported_meshes={len(imported_meshes)} glb={output}"
    )


if __name__ == "__main__":
    main()
