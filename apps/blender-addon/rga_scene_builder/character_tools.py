"""Local, deterministic humanoid blockout and motion tools for Blender."""

from __future__ import annotations

import math

import bpy

_RADIUS = 0.22
CHARACTER_OBJECT_COUNT = 17  # one armature and sixteen rigidly weighted body meshes
_SILHOUETTE_RADIIS = {
    "balanced": {},
    "heroic": {
        "Head": (0.94, 0.96, 0.98),
        "Pelvis": (1.08, 1.04, 1.0),
        "Torso": (1.18, 1.08, 1.02),
        "Upper Arm": (1.12, 1.10, 1.04),
        "Forearm": (1.10, 1.08, 1.02),
        "Thigh": (1.12, 1.08, 1.0),
        "Shin": (1.08, 1.06, 1.0),
    },
    "slender": {
        "Pelvis": (0.90, 0.94, 1.0),
        "Torso": (0.84, 0.90, 1.0),
        "Upper Arm": (0.88, 0.90, 1.0),
        "Forearm": (0.86, 0.90, 1.0),
        "Thigh": (0.90, 0.92, 1.0),
        "Shin": (0.90, 0.92, 1.0),
        "Foot": (0.94, 0.96, 1.0),
    },
    "round": {
        "Head": (1.16, 1.12, 1.08),
        "Pelvis": (1.12, 1.10, 1.0),
        "Torso": (1.10, 1.10, 0.98),
        "Upper Arm": (1.06, 1.06, 1.0),
        "Forearm": (1.06, 1.06, 1.0),
        "Thigh": (1.08, 1.06, 1.0),
        "Shin": (1.04, 1.04, 1.0),
    },
}
_BONE_SPECS = (
    ("Root", (0, 0, 0), (0, 0, 2.65), None),
    ("Hips", (0, 0, 2.65), (0, 0, 3.05), "Root"),
    ("Spine", (0, 0, 3.05), (0, 0, 3.65), "Hips"),
    ("Chest", (0, 0, 3.65), (0, 0, 4.12), "Spine"),
    ("Neck", (0, 0, 4.12), (0, 0, 4.52), "Chest"),
    ("Head", (0, 0, 4.52), (0, 0, 5.25), "Neck"),
    ("UpperArm.L", (0.48, 0, 3.98), (0.94, 0, 3.88), "Chest"),
    ("LowerArm.L", (0.94, 0, 3.88), (1.38, 0, 3.78), "UpperArm.L"),
    ("Hand.L", (1.38, 0, 3.78), (1.62, 0, 3.75), "LowerArm.L"),
    ("UpperArm.R", (-0.48, 0, 3.98), (-0.94, 0, 3.88), "Chest"),
    ("LowerArm.R", (-0.94, 0, 3.88), (-1.38, 0, 3.78), "UpperArm.R"),
    ("Hand.R", (-1.38, 0, 3.78), (-1.62, 0, 3.75), "LowerArm.R"),
    ("UpperLeg.L", (0.18, 0, 2.72), (0.18, 0, 1.55), "Hips"),
    ("LowerLeg.L", (0.18, 0, 1.55), (0.18, 0, 0.42), "UpperLeg.L"),
    ("Foot.L", (0.18, 0, 0.42), (0.18, -0.45, 0.20), "LowerLeg.L"),
    ("UpperLeg.R", (-0.18, 0, 2.72), (-0.18, 0, 1.55), "Hips"),
    ("LowerLeg.R", (-0.18, 0, 1.55), (-0.18, 0, 0.42), "UpperLeg.R"),
    ("Foot.R", (-0.18, 0, 0.42), (-0.18, -0.45, 0.20), "LowerLeg.R"),
)


def _ellipsoid_mesh(name: str, radii: tuple[float, float, float]) -> bpy.types.Mesh:
    segments = 12
    rings = 8
    rx, ry, rz = radii
    vertices = [(0.0, 0.0, rz)]
    for ring in range(1, rings):
        latitude = math.pi * ring / rings
        for segment in range(segments):
            longitude = 2 * math.pi * segment / segments
            vertices.append(
                (
                    rx * math.sin(latitude) * math.cos(longitude),
                    ry * math.sin(latitude) * math.sin(longitude),
                    rz * math.cos(latitude),
                )
            )
    bottom_index = len(vertices)
    vertices.append((0.0, 0.0, -rz))
    faces = []
    for segment in range(segments):
        next_segment = (segment + 1) % segments
        faces.append((0, 1 + segment, 1 + next_segment))
    for ring in range(rings - 2):
        upper = 1 + ring * segments
        lower = upper + segments
        for segment in range(segments):
            next_segment = (segment + 1) % segments
            faces.append(
                (
                    upper + segment,
                    lower + segment,
                    lower + next_segment,
                    upper + next_segment,
                )
            )
    last_ring = 1 + (rings - 2) * segments
    for segment in range(segments):
        next_segment = (segment + 1) % segments
        faces.append((bottom_index, last_ring + next_segment, last_ring + segment))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    return mesh


def _material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF") if material.node_tree else None
    if shader is not None:
        shader.inputs["Base Color"].default_value = color
        shader.inputs["Roughness"].default_value = 0.78
    return material


def _silhouette_radii(
    part_name: str, radii: tuple[float, float, float], silhouette: str
) -> tuple[float, float, float]:
    scales = _SILHOUETTE_RADIIS[silhouette]
    part_scale = next(
        (
            value
            for prefix, value in scales.items()
            if part_name == prefix or part_name.startswith(f"{prefix} ")
        ),
        (1.0, 1.0, 1.0),
    )
    return tuple(radius * factor for radius, factor in zip(radii, part_scale, strict=True))


def _create_character_part(
    name: str,
    bone_name: str,
    location: tuple[float, float, float],
    radii: tuple[float, float, float],
    color: tuple[float, float, float, float],
    armature: bpy.types.Object,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    mesh = _ellipsoid_mesh(f"{name} Mesh", radii)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.location = location
    obj.parent = armature
    obj.data.materials.append(_material(f"RGA_Character_{bone_name}", color))
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    group = obj.vertex_groups.new(name=bone_name)
    group.add(list(range(len(mesh.vertices))), 1.0, "REPLACE")
    modifier = obj.modifiers.new("RGA Character Skin", "ARMATURE")
    modifier.object = armature
    obj["rga_generated"] = True
    obj["rga_role"] = "character_blockout"
    obj["rga_rig"] = "generic_stylized_humanoid"
    return obj


def _create_motion(armature: bpy.types.Object, motion: str) -> bpy.types.Action:
    action_name = f"RGA_{motion.title()}_Loop"
    action = bpy.data.actions.new(action_name)
    armature.animation_data_create()
    armature.animation_data.action = action
    pose = armature.pose.bones
    if motion == "WALK":
        samples = (
            (1, 0.55, -0.55, 0.55, 0.0, 0.0, 0.0),
            (7, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            (13, -0.55, 0.55, -0.55, 0.0, 0.0, 0.0),
            (19, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            (25, 0.55, -0.55, 0.55, 0.0, 0.0, 0.0),
        )
    elif motion == "RUN":
        samples = (
            (1, 0.82, -0.78, 0.78, 0.0, 0.0, 0.0),
            (4, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            (7, -0.82, 0.78, -0.78, 0.0, 0.0, 0.0),
            (10, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            (13, 0.82, -0.78, 0.78, 0.0, 0.0, 0.0),
            (16, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            (19, -0.82, 0.78, -0.78, 0.0, 0.0, 0.0),
            (22, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            (25, 0.82, -0.78, 0.78, 0.0, 0.0, 0.0),
        )
    elif motion == "JUMP":
        samples = (
            (1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            (4, -0.1, 0.15, 0.15, 0.0, 0.1, 0.1),
            (7, 0.15, -0.45, -0.45, 0.25, 0.35, 0.45),
            (13, 0.1, 0.0, 0.0, 1.0, 0.4, 0.65),
            (18, -0.1, 0.45, 0.45, 0.65, 0.35, 0.4),
            (22, -0.2, 0.2, 0.2, 0.0, 0.1, 0.15),
            (25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        )
    else:
        samples = (
            (1, 0.03, 0.0, 0.0, 0.0, 0.0, 0.0),
            (13, -0.03, 0.0, 0.0, 0.0, 0.0, 0.0),
            (25, 0.03, 0.0, 0.0, 0.0, 0.0, 0.0),
        )

    for frame, torso_sway, left_leg, right_leg, root_lift, knee_fold, arm_raise in samples:
        for bone in pose:
            bone.rotation_mode = "XYZ"
            bone.rotation_euler = (0.0, 0.0, 0.0)
        pose["Root"].location = (0.0, 0.0, root_lift)
        pose["Chest"].rotation_euler[1] = torso_sway
        if motion in {"WALK", "RUN"}:
            pose["UpperLeg.L"].rotation_euler[0] = left_leg
            pose["UpperLeg.R"].rotation_euler[0] = right_leg
            pose["LowerLeg.L"].rotation_euler[0] = max(0.0, -left_leg) * 0.65
            pose["LowerLeg.R"].rotation_euler[0] = max(0.0, -right_leg) * 0.65
            arm_swing = 0.7 if motion == "WALK" else 0.9
            pose["UpperArm.L"].rotation_euler[0] = -left_leg * arm_swing
            pose["UpperArm.R"].rotation_euler[0] = -right_leg * arm_swing
        elif motion == "IDLE":
            pose["Head"].rotation_euler[1] = -torso_sway * 0.4
            pose["UpperArm.L"].rotation_euler[0] = 0.06
            pose["UpperArm.R"].rotation_euler[0] = 0.06
        else:
            pose["UpperLeg.L"].rotation_euler[0] = -knee_fold
            pose["UpperLeg.R"].rotation_euler[0] = -knee_fold
            pose["LowerLeg.L"].rotation_euler[0] = knee_fold * 0.8
            pose["LowerLeg.R"].rotation_euler[0] = knee_fold * 0.8
            pose["UpperArm.L"].rotation_euler[2] = arm_raise
            pose["UpperArm.R"].rotation_euler[2] = -arm_raise
        for bone in pose:
            bone.keyframe_insert(data_path="rotation_euler", frame=frame, group=bone.name)
        if motion == "JUMP":
            pose["Root"].keyframe_insert(data_path="location", frame=frame, group="Root")

    if hasattr(action, "fcurves"):
        for curve in action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"
    return action


def create_stylized_humanoid(
    context: bpy.types.Context,
    collection: bpy.types.Collection,
    motion: str,
    *,
    name: str = "Character",
    location: tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
    silhouette: str = "balanced",
) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    """Create a proportioned humanoid blockout, generic rig, and loop action."""
    if motion not in {"WALK", "RUN", "JUMP", "IDLE"}:
        raise ValueError("unsupported character motion preset")
    if silhouette not in _SILHOUETTE_RADIIS:
        raise ValueError("unsupported character silhouette preset")
    armature_data = bpy.data.armatures.new(f"{name} Skeleton")
    armature = bpy.data.objects.new(f"{name} Rig", armature_data)
    collection.objects.link(armature)
    armature.location = location
    armature.scale = scale
    for selected in tuple(context.selected_objects):
        selected.select_set(False)
    armature.select_set(True)
    context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature_data.edit_bones
    for bone_name, head, tail, parent_name in _BONE_SPECS:
        bone = edit_bones.new(bone_name)
        bone.head = head
        bone.tail = tail
        if parent_name is not None:
            bone.parent = edit_bones[parent_name]
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.show_in_front = True
    armature.display_type = "WIRE"
    armature["rga_generated"] = True
    armature["rga_role"] = "character_rig_blockout"
    armature["rga_compatibility"] = "Generic rig; not a Roblox R15 avatar rig"
    armature["rga_silhouette"] = silhouette

    parts = [
        ("Pelvis", "Hips", (0, 0, 2.80), (0.38, 0.25, 0.29), (0.22, 0.33, 0.48, 1)),
        ("Torso", "Chest", (0, 0, 3.70), (0.50, 0.29, 0.66), (0.18, 0.45, 0.58, 1)),
        ("Neck", "Neck", (0, 0, 4.36), (0.15, 0.15, 0.21), (0.76, 0.56, 0.40, 1)),
        ("Head", "Head", (0, 0, 4.87), (0.30, 0.28, 0.38), (0.82, 0.64, 0.48, 1)),
    ]
    for side, sign in (("L", 1), ("R", -1)):
        parts.extend(
            [
                (
                    f"Upper Arm {side}",
                    f"UpperArm.{side}",
                    (sign * 0.79, 0, 3.91),
                    (0.19, 0.19, 0.40),
                    (0.18, 0.45, 0.58, 1),
                ),
                (
                    f"Forearm {side}",
                    f"LowerArm.{side}",
                    (sign * 1.19, 0, 3.81),
                    (0.15, 0.16, 0.35),
                    (0.18, 0.45, 0.58, 1),
                ),
                (
                    f"Hand {side}",
                    f"Hand.{side}",
                    (sign * 1.49, -0.01, 3.76),
                    (0.14, 0.12, 0.17),
                    (0.82, 0.64, 0.48, 1),
                ),
                (
                    f"Thigh {side}",
                    f"UpperLeg.{side}",
                    (sign * 0.18, 0, 2.17),
                    (0.23, 0.22, 0.55),
                    (0.22, 0.33, 0.48, 1),
                ),
                (
                    f"Shin {side}",
                    f"LowerLeg.{side}",
                    (sign * 0.18, 0, 1.00),
                    (0.17, 0.18, 0.49),
                    (0.22, 0.33, 0.48, 1),
                ),
                (
                    f"Foot {side}",
                    f"Foot.{side}",
                    (sign * 0.18, -0.22, 0.25),
                    (0.17, 0.37, 0.15),
                    (0.18, 0.20, 0.23, 1),
                ),
            ]
        )
    objects = []
    for part_name, bone, part_location, radii, color in parts:
        objects.append(
            _create_character_part(
                part_name,
                bone,
                part_location,
                _silhouette_radii(part_name, radii, silhouette),
                color,
                armature,
                collection,
            )
        )
    for obj in objects:
        obj.name = f"{name} {obj.name}"
    _create_motion(armature, motion)
    context.scene.frame_start = 1
    context.scene.frame_end = 25
    context.scene.render.fps = 24
    context.scene.frame_set(1)
    for obj in (*objects, armature):
        obj.select_set(True)
    context.view_layer.objects.active = armature
    return armature, objects
