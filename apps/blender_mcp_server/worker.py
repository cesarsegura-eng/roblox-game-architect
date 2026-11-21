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
    parser.add_argument("--preview-output", type=Path)
    parser.add_argument("--preview-mode", choices=("isometric", "cutaway"), default="isometric")
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

    if options.preview_output is not None:
        _render_preview(options.preview_output, mode=options.preview_mode)

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
        # Roblox's asset preflight intentionally rejects KHR_lights_punctual.
        # Recipe lighting is applied to the separate Roblox place artifact.
        export_lights=False,
        export_animations=True,
        export_skins=True,
    )
    options.result.write_text(
        json.dumps({"created_objects": created}, separators=(",", ":")), encoding="utf-8"
    )


def _render_preview(output: Path, *, mode: str = "isometric") -> None:
    """Render a fixed inspection image; cutaway hides only roof-role objects temporarily."""
    from mathutils import Vector

    if mode not in {"isometric", "cutaway"}:
        raise ValueError("unsupported preview mode")
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not mesh_objects:
        raise RuntimeError("preview requires at least one mesh")
    world_points = [
        obj.matrix_world @ Vector(corner) for obj in mesh_objects for corner in obj.bound_box
    ]
    minimum = Vector(tuple(min(point[axis] for point in world_points) for axis in range(3)))
    maximum = Vector(tuple(max(point[axis] for point in world_points) for axis in range(3)))
    center = (minimum + maximum) * 0.5
    dimensions = maximum - minimum
    longest = max(dimensions.x, dimensions.y, dimensions.z, 1.0)

    scene = bpy.context.scene
    camera_data = bpy.data.cameras.new("RGA Preview Camera")
    camera = bpy.data.objects.new("RGA Preview Camera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = center + Vector((1.4, -1.8, 1.25)).normalized() * longest * 2.8
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = longest * 1.35
    camera_data.clip_end = max(1000.0, longest * 8.0)
    scene.camera = camera

    for name, direction, energy_scale in (
        ("RGA Preview Key", Vector((1.0, -1.2, 1.8)), 5.0),
        ("RGA Preview Fill", Vector((-1.4, -0.2, 0.8)), 2.0),
        ("RGA Preview Rim", Vector((0.2, 1.4, 1.2)), 3.0),
    ):
        light_data = bpy.data.lights.new(name=name, type="AREA")
        light_data.energy = longest * longest * energy_scale
        light_data.shape = "DISK"
        light_data.size = longest * 1.2
        light = bpy.data.objects.new(name, light_data)
        scene.collection.objects.link(light)
        light.location = center + direction.normalized() * longest * 2.0
        light.rotation_euler = (center - light.location).to_track_quat("-Z", "Y").to_euler()

    world = bpy.data.worlds.new("RGA Preview World")
    background = world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.055, 0.07, 0.095, 1.0)
        background.inputs["Strength"].default_value = 0.5
    scene.world = world
    engines = scene.render.bl_rna.properties["engine"].enum_items
    scene.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.filepath = "rga_preview"
    scene.render.resolution_percentage = 100
    roofs = [obj for obj in mesh_objects if obj.get("rga_role") == "roof"]
    previous = [(obj, obj.hide_render) for obj in roofs]
    try:
        if mode == "cutaway":
            for obj in roofs:
                obj.hide_render = True
        bpy.ops.render.render(write_still=False)
        bpy.data.images["Render Result"].save_render(filepath=str(output), scene=scene)
    finally:
        for obj, hide_render in previous:
            obj.hide_render = hide_render


if __name__ == "__main__":
    main()
