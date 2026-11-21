"""Blender extension for declarative Roblox Game Architect scene recipes."""

from __future__ import annotations

import json
import math
import os
from http.client import HTTPConnection, HTTPException
from pathlib import Path

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty
from bpy.types import AddonPreferences, Operator, Panel
from bpy_extras.io_utils import ExportHelper, ImportHelper

from .character_tools import create_stylized_humanoid
from .recipe_contract import RecipeError, parse_recipe

bl_info = {
    "name": "Roblox Game Architect Scene Builder",
    "author": "Roblox Game Architect contributors",
    "version": (0, 4, 0),
    "blender": (4, 2, 0),
    "category": "3D View",
}

_COLLECTION_PREFIX = "RGA - "
_MATERIAL_PREFIX = "RGA_Mat_"
_MAX_RECIPE_BYTES = 1_048_576


class RGA_AddonPreferences(AddonPreferences):
    bl_idname = __package__

    service_token: StringProperty(
        name="Blender service token",
        description="Local API token; this is not the Anthropic API key",
        subtype="PASSWORD",
    )
    server_port: IntProperty(
        name="Local API port",
        default=8787,
        min=1024,
        max=65535,
    )

    def draw(self, context: bpy.types.Context) -> None:
        del context
        layout = self.layout
        layout.label(text="The provider key stays in the local API process.")
        layout.prop(self, "service_token")
        layout.prop(self, "server_port")


def _addon_preferences(context: bpy.types.Context) -> RGA_AddonPreferences | None:
    addon = context.preferences.addons.get(__package__)
    return addon.preferences if addon is not None else None


def _make_mesh_object(spec: dict, collection: bpy.types.Collection) -> bpy.types.Object:
    location = spec["location"]
    rotation = tuple(math.radians(value) for value in spec["rotation_deg"])
    if "mesh" in spec:
        mesh_spec = spec["mesh"]
        mesh_data = bpy.data.meshes.new(f"{spec['name']} Mesh")
        mesh_data.from_pydata(mesh_spec["vertices"], [], mesh_spec["faces"])
        mesh_data.update(calc_edges=True)
        obj = bpy.data.objects.new(spec["name"], mesh_data)
        collection.objects.link(obj)
    else:
        add = {
            "cube": bpy.ops.mesh.primitive_cube_add,
            "uv_sphere": bpy.ops.mesh.primitive_uv_sphere_add,
            "ico_sphere": bpy.ops.mesh.primitive_ico_sphere_add,
            "cylinder": bpy.ops.mesh.primitive_cylinder_add,
            "cone": bpy.ops.mesh.primitive_cone_add,
            "plane": bpy.ops.mesh.primitive_plane_add,
            "torus": bpy.ops.mesh.primitive_torus_add,
        }[spec["primitive"]]
        add(location=location, rotation=rotation)
        obj = bpy.context.object
        if obj is None:
            raise RuntimeError("Blender did not create a mesh object")
    obj.name = spec["name"]
    obj.scale = spec["scale"]
    obj.location = location
    obj.rotation_euler = rotation
    obj["rga_role"] = spec["role"]
    obj["rga_generated"] = True
    for previous_collection in tuple(obj.users_collection):
        previous_collection.objects.unlink(obj)
    collection.objects.link(obj)

    if spec.get("smooth_shading", False):
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
    bevel = float(spec.get("bevel", 0.0))
    if bevel > 0:
        modifier = obj.modifiers.new(name="RGA Soft Edges", type="BEVEL")
        modifier.width = bevel
        modifier.segments = 2
        modifier.limit_method = "ANGLE"
    material_spec = spec.get("material")
    if material_spec is not None:
        obj.data.materials.append(_get_material(material_spec))
    return obj


def _get_material(spec: dict) -> bpy.types.Material:
    color = tuple(float(value) for value in spec["base_color"])
    roughness = float(spec["roughness"])
    key = "_".join(f"{value:.4f}" for value in (*color, roughness))
    name = f"{_MATERIAL_PREFIX}{key}"
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name=name)
        material.diffuse_color = color
        material.use_nodes = True
        principled = material.node_tree.nodes.get("Principled BSDF")
        if principled is not None:
            principled.inputs["Base Color"].default_value = color
            principled.inputs["Roughness"].default_value = roughness
    return material


def _make_light(spec: dict, collection: bpy.types.Collection) -> bpy.types.Object:
    data = bpy.data.lights.new(name=spec["name"], type=spec["type"])
    data.energy = spec["energy"]
    data.color = spec["color"]
    if spec["type"] in {"POINT", "SPOT"} and "distance" in spec:
        data.cutoff_distance = spec["distance"]
    if spec["type"] == "SPOT" and "spot_size_deg" in spec:
        data.spot_size = math.radians(spec["spot_size_deg"])
    if spec["type"] == "SUN" and "angle_deg" in spec:
        data.angle = math.radians(spec["angle_deg"])
    obj = bpy.data.objects.new(spec["name"], data)
    collection.objects.link(obj)
    obj.location = spec["location"]
    obj.rotation_euler = tuple(math.radians(value) for value in spec["rotation_deg"])
    obj["rga_generated"] = True
    obj["rga_role"] = "lighting"
    return obj


def _build_recipe(context: bpy.types.Context, recipe: dict) -> int:
    collection = bpy.data.collections.new(f"{_COLLECTION_PREFIX}{recipe['name']}")
    context.scene.collection.children.link(collection)
    created: list[bpy.types.Object] = []
    try:
        for spec in recipe["objects"]:
            created.append(_make_mesh_object(spec, collection))
        for spec in recipe.get("lights", []):
            created.append(_make_light(spec, collection))
        for spec in recipe.get("characters", []):
            armature, parts = create_stylized_humanoid(
                context,
                collection,
                spec["motion"],
                name=spec["name"],
                location=tuple(spec["location"]),
                scale=tuple(spec["scale"]),
                silhouette=spec.get("silhouette", "balanced"),
            )
            created.extend((armature, *parts))
        for obj in tuple(context.selected_objects):
            obj.select_set(False)
        for obj in created:
            obj.select_set(True)
        if created:
            context.view_layer.objects.active = created[-1]
        return len(created)
    except Exception:
        for obj in tuple(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for obj in created:
            if obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        if collection.name in bpy.data.collections:
            bpy.data.collections.remove(collection, do_unlink=True)
        raise


class RGA_OT_import_recipe(Operator, ImportHelper):
    bl_idname = "rga.import_scene_recipe"
    bl_label = "Import Scene Recipe"
    bl_description = "Build a validated, data-only recipe in a separate Blender collection"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            path = Path(self.filepath)
            if path.stat().st_size > 1_048_576:
                raise RecipeError("recipe exceeds the 1 MiB limit")
            recipe = parse_recipe(path.read_text(encoding="utf-8"))
            count = _build_recipe(context, recipe)
        except (OSError, UnicodeError, RecipeError, RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, f"Scene recipe was not imported: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Imported {count} objects into a new RGA collection")
        return {"FINISHED"}


class RGA_OT_generate_recipe(Operator):
    bl_idname = "rga.generate_scene_recipe"
    bl_label = "Generate World in Blender"
    bl_description = "Ask the loopback API for a validated scene recipe and import it"

    brief: StringProperty(
        name="World brief",
        description="Describe biome, gameplay route, architecture, interiors, and atmosphere",
        maxlen=10_000,
    )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        del event
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context: bpy.types.Context) -> None:
        del context
        self.layout.prop(self, "brief", text="")

    def execute(self, context: bpy.types.Context) -> set[str]:
        prefs = _addon_preferences(context)
        if prefs is None or not prefs.service_token.strip():
            self.report({"ERROR"}, "Set the Blender service token in extension preferences first")
            return {"CANCELLED"}
        if not self.brief.strip():
            self.report({"ERROR"}, "Enter a world brief")
            return {"CANCELLED"}
        payload = json.dumps({"brief": self.brief}, ensure_ascii=False).encode("utf-8")
        try:
            with HTTPConnection("127.0.0.1", prefs.server_port, timeout=180) as connection:
                connection.request(
                    "POST",
                    "/v1/world/recipe",
                    body=payload,
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "Authorization": f"Bearer {prefs.service_token.strip()}",
                    },
                )
                response = connection.getresponse()
                if response.status != 200:
                    self.report(
                        {"ERROR"}, f"Local generation service returned HTTP {response.status}"
                    )
                    return {"CANCELLED"}
                raw = response.read(_MAX_RECIPE_BYTES + 1)
            if len(raw) > _MAX_RECIPE_BYTES:
                raise RecipeError("generated recipe exceeds the 1 MiB limit")
            recipe = parse_recipe(raw.decode("utf-8"))
            count = _build_recipe(context, recipe)
        except (HTTPException, OSError, UnicodeError, RecipeError, RuntimeError, ValueError) as exc:
            self.report({"ERROR"}, f"Could not generate/import the world: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Generated and imported {count} objects into a new RGA collection")
        return {"FINISHED"}


class RGA_OT_export_glb(Operator, ExportHelper):
    bl_idname = "rga.export_selected_glb"
    bl_label = "Export Selection as GLB"
    bl_description = "Export selected objects for review and manual import in Roblox Studio"
    filename_ext = ".glb"
    filter_glob: StringProperty(default="*.glb", options={"HIDDEN"})

    def execute(self, context: bpy.types.Context) -> set[str]:
        filepath = os.path.abspath(self.filepath)
        if Path(filepath).suffix.lower() != ".glb":
            self.report({"ERROR"}, "Choose a .glb filename")
            return {"CANCELLED"}
        if os.path.exists(filepath):
            self.report({"ERROR"}, "Choose a new filename; this export will not overwrite files")
            return {"CANCELLED"}
        if not context.selected_objects:
            self.report({"ERROR"}, "Select the model or generated collection to export")
            return {"CANCELLED"}
        try:
            bpy.ops.export_scene.gltf(
                filepath=filepath,
                export_format="GLB",
                use_selection=True,
                export_yup=True,
                export_animations=True,
                export_skins=True,
                export_lights=False,
            )
        except (RuntimeError, TypeError) as exc:
            self.report({"ERROR"}, f"GLB export failed: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, "Exported GLB; review it in Roblox Studio's Importer")
        return {"FINISHED"}


class RGA_OT_create_humanoid(Operator):
    bl_idname = "rga.create_stylized_humanoid"
    bl_label = "Create Humanoid Rig Blockout"
    bl_description = "Create a low-poly character, generic skeleton, and looped motion preset"

    motion: EnumProperty(
        name="Motion",
        description="Initial motion action to create",
        items=(
            ("WALK", "Walk Cycle", "Alternating arm and leg swing"),
            ("RUN", "Run Cycle", "Faster stride with stronger lean and arm swing"),
            ("JUMP", "Jump Cycle", "Takeoff, airborne pose, and grounded landing"),
            ("IDLE", "Idle Loop", "Subtle breathing and pose movement"),
        ),
        default="WALK",
    )
    silhouette: EnumProperty(
        name="Silhouette",
        description="Choose bounded body proportions for this stylized blockout",
        items=(
            ("balanced", "Balanced", "Default generic proportions"),
            ("heroic", "Heroic", "Broader torso and limbs"),
            ("slender", "Slender", "Narrower torso and limbs"),
            ("round", "Round", "Rounder torso and larger head"),
        ),
        default="balanced",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT"

    def execute(self, context: bpy.types.Context) -> set[str]:
        collection = bpy.data.collections.new(f"{_COLLECTION_PREFIX}Character")
        context.scene.collection.children.link(collection)
        try:
            create_stylized_humanoid(context, collection, self.motion, silhouette=self.silhouette)
        except Exception as exc:
            for obj in tuple(collection.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            if collection.name in bpy.data.collections:
                bpy.data.collections.remove(collection, do_unlink=True)
            self.report({"ERROR"}, f"Character blockout failed: {exc}")
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            "Created a generic humanoid rig blockout; review and adapt before Roblox use",
        )
        return {"FINISHED"}


class RGA_PT_scene_builder(Panel):
    bl_label = "Roblox Game Architect"
    bl_idname = "RGA_PT_scene_builder"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RGA"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.label(text="Scene recipes are validated JSON data")
        layout.label(text="Generation connects to the local API only")
        layout.operator(RGA_OT_generate_recipe.bl_idname, icon="WORLD")
        layout.operator(RGA_OT_import_recipe.bl_idname, icon="IMPORT")
        layout.separator()
        layout.label(text="Character modeling and motion")
        walk = layout.operator(RGA_OT_create_humanoid.bl_idname, text="Create Walk Rig Blockout")
        walk.motion = "WALK"
        run = layout.operator(RGA_OT_create_humanoid.bl_idname, text="Create Run Rig Blockout")
        run.motion = "RUN"
        jump = layout.operator(RGA_OT_create_humanoid.bl_idname, text="Create Jump Rig Blockout")
        jump.motion = "JUMP"
        idle = layout.operator(RGA_OT_create_humanoid.bl_idname, text="Create Idle Rig Blockout")
        idle.motion = "IDLE"
        layout.label(text="Generic NPC rig; not R15 avatar-ready", icon="INFO")
        layout.separator()
        layout.label(text="Export selection for manual Studio review")
        layout.operator(RGA_OT_export_glb.bl_idname, icon="EXPORT")


_CLASSES = (
    RGA_AddonPreferences,
    RGA_OT_import_recipe,
    RGA_OT_generate_recipe,
    RGA_OT_create_humanoid,
    RGA_OT_export_glb,
    RGA_PT_scene_builder,
)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
