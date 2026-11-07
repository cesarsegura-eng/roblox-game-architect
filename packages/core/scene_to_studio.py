"""Create a bounded, script-free Studio proxy action from a Blender recipe."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .worldbuilding import SceneObject, SceneRecipe

MAX_PROXY_PARTS = 14
MAX_PROXY_POSITION = 300.0
MAX_PROXY_SIZE = 100.0
MAX_PROXY_OPERATIONS = 100
_ROTATION_EPSILON = 1e-7


@dataclass(frozen=True, slots=True)
class Proxy:
    position: tuple[float, float, float]
    size: tuple[float, float, float]
    orientation: tuple[float, float, float]
    world_size: tuple[float, float, float]


_ROLE_MATERIAL = {
    "terrain": "Grass",
    "path": "Concrete",
    "architecture": "Brick",
    "exterior": "Brick",
    "interior": "WoodPlanks",
    "entry": "Wood",
    "courtyard": "Concrete",
    "roof": "WoodPlanks",
    "opening": "Glass",
    "furnishing": "Wood",
    "vegetation": "Grass",
    "rock": "Concrete",
    "water": "Glass",
    "prop": "Plastic",
    "landmark": "Concrete",
    "character_blockout": "Plastic",
    "collectible": "Neon",
    "hazard": "Neon",
}
_ROLE_COLOR = {
    "terrain": (0.30, 0.46, 0.25),
    "path": (0.48, 0.45, 0.39),
    "architecture": (0.61, 0.43, 0.32),
    "exterior": (0.61, 0.43, 0.32),
    "interior": (0.68, 0.53, 0.37),
    "entry": (0.42, 0.27, 0.18),
    "courtyard": (0.55, 0.52, 0.43),
    "roof": (0.36, 0.22, 0.18),
    "opening": (0.35, 0.65, 0.78),
    "furnishing": (0.58, 0.39, 0.24),
    "vegetation": (0.22, 0.48, 0.24),
    "rock": (0.42, 0.43, 0.42),
    "water": (0.12, 0.47, 0.72),
    "prop": (0.72, 0.56, 0.28),
    "landmark": (0.75, 0.55, 0.18),
    "character_blockout": (0.72, 0.48, 0.38),
    "collectible": (0.98, 0.78, 0.20),
    "hazard": (0.92, 0.12, 0.08),
}
_ROLE_PROXY_PRIORITY = {
    "path": 0,
    "entry": 1,
    "landmark": 2,
    "terrain": 3,
    "exterior": 4,
    "interior": 5,
    "courtyard": 6,
    "opening": 7,
    "architecture": 8,
    "roof": 9,
    "furnishing": 10,
    "vegetation": 11,
    "water": 12,
    "rock": 13,
    "prop": 14,
    "character_blockout": 15,
    "collectible": 2,
    "hazard": 2,
}


class SceneToStudioError(ValueError):
    """A validated Blender recipe cannot produce a bounded Studio proxy action."""


def scene_recipe_to_studio_action(payload: object, request_id: str) -> dict[str, Any]:
    """Convert eligible recipe objects to reviewed Roblox Parts without running code.

    Blender is Z-up and Roblox is Y-up. Meshes and curved primitives are reduced
    to oriented local bounding boxes; this is a layout proxy, not a GLB import.
    Objects outside the fixed Studio bounds are skipped. If more than fourteen
    fit, navigation and architectural features are selected first, with source
    order preserved within each role priority. The result is queued as an
    ordinary, unapproved edit.action and is still subject to Studio's Apply
    confirmation.
    """
    recipe = payload if isinstance(payload, SceneRecipe) else SceneRecipe.from_mapping(payload)
    try:
        canonical_request_id = str(UUID(request_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise SceneToStudioError("request_id must be a UUID") from exc
    if canonical_request_id != request_id.lower():
        raise SceneToStudioError("request_id must use canonical UUID syntax")
    request_hex = UUID(canonical_request_id).hex
    action_id = "scene-" + request_hex
    root = "RGA Scene " + request_hex
    root_path = ["Workspace", root]
    scope = [{"path": root_path, "extent": "subtree"}]
    operations: list[dict[str, Any]] = [
        {
            "op": "create_instance",
            "op_id": "root-create",
            "parent": {"path": ["Workspace"], "expect_class": "Workspace"},
            "name": root,
            "class_name": "Model",
        }
    ]
    candidates: list[tuple[int, int, SceneObject, Proxy]] = []
    for source_index, spec in enumerate(recipe.objects):
        proxy = _proxy(spec)
        if proxy is None:
            continue
        if any(abs(value) > MAX_PROXY_POSITION for value in proxy.position):
            continue
        if any(value < 0.5 or value > MAX_PROXY_SIZE for value in proxy.world_size):
            continue
        candidates.append((_ROLE_PROXY_PRIORITY.get(spec.role, 99), source_index, spec, proxy))
    selected = []
    operation_count = len(operations)
    for candidate in sorted(candidates, key=lambda item: (item[0], item[1])):
        if len(selected) >= MAX_PROXY_PARTS:
            break
        orientation = candidate[3].orientation
        has_rotation = any(abs(value) > _ROTATION_EPSILON for value in orientation)
        candidate_operations = 7 + int(has_rotation)
        if operation_count + candidate_operations > MAX_PROXY_OPERATIONS:
            continue
        selected.append(candidate)
        operation_count += candidate_operations
    selected.sort(key=lambda item: item[1])
    used_names: set[str] = set()
    included = 0
    for _, _, spec, proxy in selected:
        included += 1
        name = _part_name(f"{spec.role} {spec.name}", included, used_names)
        part_path = [*root_path, name]
        operations.append(
            {
                "op": "create_instance",
                "op_id": f"part-{included:02d}-create",
                "parent": {"path": root_path, "expect_class": "Model"},
                "name": name,
                "class_name": "Part",
            }
        )
        color = (
            spec.material.base_color[:3] if spec.material is not None else _ROLE_COLOR[spec.role]
        )
        properties = [
            ("Size", _axes(proxy.size)),
            ("Position", _axes(proxy.position)),
        ]
        if any(abs(value) > _ROTATION_EPSILON for value in proxy.orientation):
            properties.append(("Orientation", _axes(proxy.orientation)))
        properties.extend(
            [
                ("Color", {axis: color[index] for index, axis in enumerate(("r", "g", "b"))}),
                ("Material", {"enum": "Material", "item": _ROLE_MATERIAL[spec.role]}),
                ("Anchored", True),
                ("CanCollide", spec.role != "water"),
            ]
        )
        for prop_index, (prop, value) in enumerate(properties, start=1):
            operations.append(
                {
                    "op": "set_property",
                    "op_id": f"part-{included:02d}-set-{prop_index}",
                    "target": {"path": part_path, "expect_class": "Part"},
                    "property": prop,
                    "value": value,
                }
            )
    if included == 0:
        raise SceneToStudioError(
            "recipe has no objects that fit the bounded Studio proxy dimensions"
        )
    return {
        "type": "edit.action",
        "action_id": action_id,
        "declared_scope": scope,
        "operations": operations,
    }


def _proxy(spec: SceneObject) -> Proxy | None:
    """Return an oriented bounding proxy in Roblox XYZ order."""
    if spec.mesh is not None:
        points = spec.mesh.vertices
        mins = tuple(min(point[index] for point in points) for index in range(3))
        maxs = tuple(max(point[index] for point in points) for index in range(3))
        local_center = tuple((mins[index] + maxs[index]) / 2 for index in range(3))
        half_extent = tuple(
            (maxs[index] - mins[index]) * spec.scale[index] / 2 for index in range(3)
        )
    else:
        base = {
            "cube": (1.0, 1.0, 1.0),
            "uv_sphere": (1.0, 1.0, 1.0),
            "ico_sphere": (1.0, 1.0, 1.0),
            "cylinder": (1.0, 1.0, 1.0),
            "cone": (1.0, 1.0, 1.0),
            "plane": (1.0, 1.0, 0.125),
            "torus": (1.25, 1.25, 0.25),
        }.get(spec.primitive)
        if base is None:
            return None
        local_center = (0.0, 0.0, 0.0)
        half_extent = tuple(base[index] * spec.scale[index] for index in range(3))

    matrix = _rotation_matrix(spec.rotation_deg)
    rotated_center = tuple(
        sum(matrix[row][col] * local_center[col] * spec.scale[col] for col in range(3))
        for row in range(3)
    )
    blender_center = tuple(spec.location[index] + rotated_center[index] for index in range(3))
    # Blender (X, Y, Z-up) -> Roblox (X, Y-up, Z), preserving the recipe's
    # transform in the same basis used by the Studio proxy position.
    local_half = (half_extent[0], half_extent[2], half_extent[1])
    local_size = tuple(max(0.5, 2 * extent) for extent in local_half)
    roblox_rotation = _roblox_rotation_matrix(matrix)
    rotated_half = tuple(
        sum(abs(roblox_rotation[row][col]) * local_size[col] / 2 for col in range(3))
        for row in range(3)
    )
    return Proxy(
        position=(blender_center[0], blender_center[2], blender_center[1]),
        size=local_size,
        orientation=_orientation_yxz(roblox_rotation),
        world_size=tuple(2 * extent for extent in rotated_half),
    )


def _roblox_rotation_matrix(
    blender_rotation: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], ...]:
    """Change the rotation matrix basis from Blender XYZ-up to Roblox Y-up."""
    basis = ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
    return tuple(
        tuple(
            sum(
                basis[row][left] * blender_rotation[left][right] * basis[col][right]
                for left in range(3)
                for right in range(3)
            )
            for col in range(3)
        )
        for row in range(3)
    )


def _orientation_yxz(
    matrix: tuple[tuple[float, ...], ...],
) -> tuple[float, float, float]:
    """Decompose Roblox's Y-X-Z Orientation rotation order in degrees."""
    sine_x = max(-1.0, min(1.0, -matrix[1][2]))
    x = math.asin(sine_x)
    cosine_x = math.cos(x)
    if abs(cosine_x) > _ROTATION_EPSILON:
        y = math.atan2(matrix[0][2], matrix[2][2])
        z = math.atan2(matrix[1][0], matrix[1][1])
    else:
        y = math.atan2(-matrix[0][1], matrix[0][0])
        z = 0.0
    return tuple(_clean_angle(math.degrees(value)) for value in (x, y, z))


def _clean_angle(value: float) -> float:
    return 0.0 if abs(value) <= _ROTATION_EPSILON else value


def _rotation_matrix(degrees: tuple[float, float, float]) -> tuple[tuple[float, ...], ...]:
    x, y, z = (math.radians(value) for value in degrees)
    cx, sx = math.cos(x), math.sin(x)
    cy, sy = math.cos(y), math.sin(y)
    cz, sz = math.cos(z), math.sin(z)
    return (
        (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
        (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
        (-sy, cy * sx, cy * cx),
    )


def _axes(values: tuple[float, float, float]) -> dict[str, float]:
    return {axis: values[index] for index, axis in enumerate(("x", "y", "z"))}


def _part_name(source: str, index: int, used: set[str]) -> str:
    stem = re.sub(r"[^A-Za-z0-9 _-]", "_", source).strip(" _-") or "ScenePart"
    if not stem[0].isalpha():
        stem = f"Part {stem}"
    suffix = f" {index:02d}"
    name = stem[: 64 - len(suffix)] + suffix
    while name.casefold() in used:
        index += MAX_PROXY_PARTS
        suffix = f" {index:02d}"
        name = stem[: 64 - len(suffix)] + suffix
    used.add(name.casefold())
    return name
