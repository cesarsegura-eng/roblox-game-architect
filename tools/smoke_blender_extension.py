"""Smoke-test the RGA add-on inside a real Blender process.

Run from the repository root:
  blender --background --factory-startup --python tools/smoke_blender_extension.py -- \
    --recipe examples/worlds/mistral-coast-lookout-v2/scene-recipe.json \
    --output dist/rga-smoke.glb
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
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
    sys.path.insert(0, str(repo))
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
            "silhouette": "heroic",
        },
        {
            "name": "Smoke Idle",
            "motion": "IDLE",
            "location": [24, 0, 0],
            "scale": [1, 1, 1],
            "silhouette": "slender",
        },
        {
            "name": "Smoke Round",
            "motion": "RUN",
            "location": [28, 0, 0],
            "scale": [1, 1, 1],
            "silhouette": "round",
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
    if len(rigs) != 3 or len(parts) != 48 or any(part.parent not in rigs for part in parts):
        raise RuntimeError("character blockout has no correctly parented skinned parts")
    bpy.context.view_layer.update()
    heroic_torso = next((obj for obj in parts if obj.name == "Smoke Walker Torso"), None)
    slender_torso = next((obj for obj in parts if obj.name == "Smoke Idle Torso"), None)
    round_torso = next((obj for obj in parts if obj.name == "Smoke Round Torso"), None)
    if (
        heroic_torso is None
        or slender_torso is None
        or round_torso is None
        or not heroic_torso.dimensions.x > round_torso.dimensions.x > slender_torso.dimensions.x
        or rigs[0].get("rga_silhouette") != "heroic"
        or rigs[1].get("rga_silhouette") != "slender"
        or rigs[2].get("rga_silhouette") != "round"
    ):
        raise RuntimeError("character silhouette presets did not produce the expected proportions")
    if any(rig.animation_data is None or rig.animation_data.action is None for rig in rigs):
        raise RuntimeError("character blockout has no animation action")

    # Exercise the exact image-validation path used before Roblox asset upload.
    test_image = bpy.data.images.new("RGA JPEG Preflight Smoke", width=16, height=8)
    test_image.pixels.foreach_set([0.25, 0.5, 0.75, 1.0] * (16 * 8))
    test_image.file_format = "JPEG"
    test_material = bpy.data.materials.new("RGA JPEG Preflight Material")
    test_material.node_tree.nodes.clear()
    output_node = test_material.node_tree.nodes.new("ShaderNodeOutputMaterial")
    principled_node = test_material.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    texture_node = test_material.node_tree.nodes.new("ShaderNodeTexImage")
    texture_node.image = test_image
    test_material.node_tree.links.new(
        principled_node.outputs["BSDF"], output_node.inputs["Surface"]
    )
    test_material.node_tree.links.new(
        texture_node.outputs["Color"], principled_node.inputs["Base Color"]
    )
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    texture_smoke_mesh = bpy.context.object
    for old_collection in list(texture_smoke_mesh.users_collection):
        old_collection.objects.unlink(texture_smoke_mesh)
    collection.objects.link(texture_smoke_mesh)
    texture_smoke_mesh.name = "RGA JPEG Preflight Smoke"
    texture_smoke_mesh.data.materials.append(test_material)

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
        export_image_format="JPEG",
    )
    document = _glb_json(output)
    exported_animations = document.get("animations")
    expected_animation_names = {"RGA_Idle_Loop", "RGA_Run_Loop", "RGA_Walk_Loop"}
    if (
        not isinstance(exported_animations, list)
        or {
            animation.get("name")
            for animation in exported_animations
            if isinstance(animation, dict) and animation.get("channels")
        }
        != expected_animation_names
    ):
        raise RuntimeError("GLB export is missing one of the three character animation clips")
    images = document.get("images")
    if not isinstance(images, list) or not any(
        isinstance(image, dict) and image.get("mimeType") == "image/jpeg" for image in images
    ):
        raise RuntimeError("GLB smoke export is missing its embedded JPEG texture")
    validator_candidates = [
        repo / ".venv" / "Scripts" / "python.exe",
        repo / ".venv" / "bin" / "python",
        Path(shutil.which("python") or ""),
        Path(shutil.which("python3") or ""),
    ]
    validator_python = next((path for path in validator_candidates if path.is_file()), None)
    if validator_python is None:
        raise RuntimeError("the Blender smoke needs the project's Python validator environment")
    validator = subprocess.run(  # noqa: S603 -- argument list invokes a local fixed Python runtime
        [
            str(validator_python),
            "-c",
            "import sys; from pathlib import Path; "
            "from apps.roblox_mcp_server.assets import MAX_GLB_BYTES, _validate_glb; "
            "_validate_glb(Path(sys.argv[1]).read_bytes(), MAX_GLB_BYTES)",
            str(output),
        ],
        cwd=repo,
        capture_output=True,
        check=False,
        text=True,
    )
    if validator.returncode:
        raise RuntimeError(
            "Roblox asset preflight failed for Blender's GLB export: "
            f"{validator.stdout}{validator.stderr}"
        )
    bpy.data.images.remove(test_image)
    before_import = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(output))
    imported = [obj for obj in bpy.data.objects if obj not in before_import]
    imported_rigs = [obj for obj in imported if obj.type == "ARMATURE"]
    imported_meshes = [obj for obj in imported if obj.type == "MESH"]
    imported_texture_mesh = next(
        (obj for obj in imported_meshes if obj.name.startswith("RGA JPEG Preflight Smoke")),
        None,
    )
    decoded_texture_images = (
        [
            node.image
            for material in imported_texture_mesh.data.materials
            if material is not None and material.node_tree is not None
            for node in material.node_tree.nodes
            if node.type == "TEX_IMAGE" and node.image is not None
        ]
        if imported_texture_mesh is not None
        else []
    )
    imported_mesh_counts = [
        sum(mesh.parent is rig for mesh in imported_meshes) for rig in imported_rigs
    ]
    imported_animation_flags = [
        rig.animation_data is not None and rig.animation_data.action is not None
        for rig in imported_rigs
    ]
    decoded_texture_valid = any(
        tuple(image.size) == (16, 8)
        and len(image.pixels) == 16 * 8 * 4
        and all(0 <= value <= 1 for value in image.pixels[:4])
        for image in decoded_texture_images
    )
    if (
        not imported_rigs
        or len(imported_rigs) != 3
        or len(imported_meshes) < 10
        or any(count < 16 for count in imported_mesh_counts)
        or not any(imported_animation_flags)
        or not decoded_texture_valid
    ):
        raise RuntimeError(
            "GLB round-trip checks failed: "
            f"rigs={len(imported_rigs)} meshes={len(imported_meshes)} "
            f"child_meshes={imported_mesh_counts} imported_animation={imported_animation_flags} "
            f"decoded_texture={decoded_texture_valid}"
        )
    addon.unregister()
    print(
        f"RGA_BLENDER_SMOKE_OK recipe_objects={built} character_parts={len(parts)} "
        f"characters={len(rigs)} imported_meshes={len(imported_meshes)} "
        "silhouettes=heroic,round,slender jpeg_texture_preflight=passed "
        f"glb={output}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
