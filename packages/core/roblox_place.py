"""Build deterministic, script-free Roblox place files from Scene Recipes.

Rojo is the only serializer. This module emits a closed DataModel description
and never accepts caller supplied class names, instance properties, paths, or
Luau source. Curved/custom geometry is represented by oriented Part bounds;
Blender GLB remains the higher fidelity geometry route.
"""

from __future__ import annotations

import json
import math
import re
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .gameplay_templates import (
    GameplayTemplateError,
    gameplay_script,
    validate_gameplay_mode,
    validate_gameplay_rules,
)
from .scene_to_studio import _ROLE_COLOR, _ROLE_MATERIAL, _rotation_matrix
from .worldbuilding import SceneClouds, SceneEnvironment, SceneLight, SceneObject, SceneRecipe

ROJO_VERSION = "7.7.1"
MAX_PLACE_FILE_BYTES = 8_000_000
MAX_IMPORTED_MODEL_BYTES = 512_000
_NAME = re.compile(r"[^A-Za-z0-9 _-]+", re.ASCII)
_FORBIDDEN_CLASSES = frozenset({"Script", "LocalScript", "ModuleScript", "Actor"})


class RobloxPlaceBuildError(ValueError):
    """A bounded scene recipe could not be serialized into a Roblox place."""


@dataclass(frozen=True, slots=True)
class RobloxPlaceBuild:
    place_file: bytes
    object_count: int
    part_count: int
    light_count: int
    approximated_object_count: int
    omitted_character_count: int
    omitted_sun_light_count: int
    gameplay_mode: str = "blockout"
    imported_meshpart_count: int = 0


def scene_recipe_to_rojo_project(
    payload: object,
    *,
    gameplay_mode: str = "blockout",
    include_imported_model: bool = False,
    gameplay_rules: object = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    """Convert a validated scene recipe to a closed Rojo DataModel project."""
    recipe = payload if isinstance(payload, SceneRecipe) else SceneRecipe.from_mapping(payload)
    try:
        mode = validate_gameplay_mode(gameplay_mode, recipe, gameplay_rules)
    except GameplayTemplateError as exc:
        raise RobloxPlaceBuildError(str(exc)) from exc
    role_nodes: dict[str, dict[str, Any]] = {}
    part_count = 0
    approximated_count = 0
    for index, spec in enumerate(recipe.objects, start=1):
        node, approximated = _object_node(spec, index)
        role_node = role_nodes.setdefault(
            spec.role,
            {"$className": "Folder", "$ignoreUnknownInstances": True},
        )
        role_node[f"{index:03d} {_safe_name(spec.name)}"] = node
        part_count += 1
        approximated_count += int(approximated)

    lights_node: dict[str, Any] = {"$className": "Folder", "$ignoreUnknownInstances": True}
    serialized_lights = 0
    omitted_suns = 0
    for index, light in enumerate(recipe.lights, start=1):
        node = _light_node(light, index)
        if node is None:
            omitted_suns += 1
            continue
        lights_node[f"{index:03d} {_safe_name(light.name)}"] = node
        serialized_lights += 1

    map_children: dict[str, Any] = {
        "$className": "Model",
        "$ignoreUnknownInstances": True,
        **{
            f"{role.title()}": node
            for role, node in sorted(role_nodes.items())
            if not include_imported_model
        },
    }
    if mode == "treasure_hunt":
        start_path = next(item for item in recipe.objects if item.role == "path")
        map_children["RGA Spawn"] = _spawn_location_node(start_path)
    elif mode == "obby":
        paths = [item for item in recipe.objects if item.role == "path"]
        map_children["RGA Checkpoints"] = {
            "$className": "Folder",
            **{
                f"{index:03d} Checkpoint": _spawn_location_node(path)
                for index, path in enumerate(paths, start=1)
            },
        }
    elif mode == "rule_game":
        start_path = next(item for item in recipe.objects if item.role == "path")
        map_children["RGA Spawn"] = {
            "$className": "Folder",
            "Player Spawn": _spawn_location_node(start_path),
        }
        validated_rules = validate_gameplay_rules(gameplay_rules, recipe)
        map_children["RGA Gameplay Rules"] = {
            "$className": "StringValue",
            "$properties": {
                "Value": json.dumps(validated_rules, ensure_ascii=True, separators=(",", ":"))
            },
        }
    if serialized_lights:
        map_children["Lighting"] = lights_node
    if include_imported_model:
        # The reviewed Blender model replaces all recipe Part proxies. Global
        # Roblox lighting/environment still comes from the validated recipe.
        part_count = 0
        approximated_count = 0
    generated_root: dict[str, Any] = {
        "$className": "Folder",
        "$ignoreUnknownInstances": True,
        f"{_safe_name(recipe.name)}": map_children,
    }
    if include_imported_model:
        generated_root["Imported Blender Model"] = {
            "$className": "Folder",
            "RGA Imported Model": {"$path": "assets/imported-model.rbxm"},
        }
    workspace: dict[str, Any] = {
        "$className": "Workspace",
        "$ignoreUnknownInstances": True,
        "Roblox Game Architect": generated_root,
    }
    lighting_node = None
    if recipe.environment is not None:
        lighting_node = _environment_node(recipe.environment)
        if recipe.environment.clouds is not None:
            workspace["Terrain"] = {
                "$className": "Terrain",
                "Clouds": _clouds_node(recipe.environment.clouds),
            }
    services: dict[str, Any] = {"Workspace": workspace}
    if lighting_node is not None:
        services["Lighting"] = lighting_node
    script_template = gameplay_script(mode)
    if script_template is not None:
        script_name, _ = script_template
        script_path = {
            "obby": "obby_course.server.luau",
            "treasure_hunt": "treasure_hunt.server.luau",
            "rule_game": "rule_game.server.luau",
        }[mode]
        services["ServerScriptService"] = {
            "$className": "ServerScriptService",
            script_name: {
                "$path": f"server/{script_path}",
            },
        }
    project = {
        "name": f"RGA {_safe_name(recipe.name)}",
        "tree": {"$className": "DataModel", **services},
    }
    return project, {
        "object_count": len(recipe.objects),
        "part_count": part_count,
        "light_count": serialized_lights,
        "approximated_object_count": approximated_count,
        "omitted_character_count": len(recipe.characters),
        "omitted_sun_light_count": omitted_suns,
    }


def validate_gameplay_rules_artifact(
    document: ET.Element,
    gameplay_mode: str,
    gameplay_rules: object,
    recipe: SceneRecipe,
) -> None:
    """Verify the compiled rule payload exactly matches the validated request."""
    parents = {child: parent for parent in document.iter() for child in parent}

    def instance_name(node: ET.Element) -> str | None:
        properties = node.find("Properties")
        return next((entry.text for entry in properties or [] if entry.get("name") == "Name"), None)

    configs = []
    for node in document.iter("Item"):
        if node.get("class") != "StringValue":
            continue
        if instance_name(node) == "RGA Gameplay Rules":
            configs.append(node)
    if gameplay_mode != "rule_game":
        if configs:
            raise RobloxPlaceBuildError("compiled place contains unexpected gameplay rules")
        return
    if len(configs) != 1:
        raise RobloxPlaceBuildError("compiled rule game must contain exactly one rules value")
    map_node = parents.get(configs[0])
    rga_folder = parents.get(map_node) if map_node is not None else None
    workspace = parents.get(rga_folder) if rga_folder is not None else None
    if (
        map_node is None
        or map_node.get("class") != "Model"
        or instance_name(map_node) != recipe.name
        or rga_folder is None
        or rga_folder.get("class") != "Folder"
        or instance_name(rga_folder) != "Roblox Game Architect"
        or workspace is None
        or workspace.get("class") != "Workspace"
    ):
        raise RobloxPlaceBuildError("compiled gameplay rules are outside their scene model")
    spawn_folder = next(
        (
            item
            for item in map_node.findall("Item")
            if item.get("class") == "Folder" and instance_name(item) == "RGA Spawn"
        ),
        None,
    )
    if spawn_folder is None or not any(
        item.get("class") == "SpawnLocation" for item in spawn_folder.findall("Item")
    ):
        raise RobloxPlaceBuildError("compiled rule game has no player spawn location")
    properties = configs[0].find("Properties")
    encoded = next(
        (
            entry.text
            for entry in properties or []
            if entry.get("name") == "Value" and entry.tag in {"string", "ProtectedString"}
        ),
        None,
    )
    try:
        actual = json.loads(encoded) if isinstance(encoded, str) else None
        expected = validate_gameplay_rules(gameplay_rules, recipe)
    except (ValueError, TypeError, json.JSONDecodeError, GameplayTemplateError) as exc:
        raise RobloxPlaceBuildError("compiled gameplay rules are invalid") from exc
    if actual != expected:
        raise RobloxPlaceBuildError("compiled gameplay rules differ from the validated request")
    for role in {str(rule["trigger_role"]) for rule in expected}:
        role_folder = next(
            (
                item
                for item in map_node.findall("Item")
                if item.get("class") == "Folder" and instance_name(item) == role.title()
            ),
            None,
        )
        if role_folder is None or not any(
            item.get("class") in {"Part", "MeshPart", "UnionOperation"}
            for item in role_folder.findall("Item")
        ):
            raise RobloxPlaceBuildError(f"compiled gameplay rule has no touchable {role!r} objects")


def scene_recipe_collision_payload(recipe: SceneRecipe) -> dict[str, Any]:
    """Compile the same object geometry for the fixed engine navigation harness."""
    objects = []
    for index, spec in enumerate(recipe.objects, start=1):
        node, _ = _object_node(spec, index)
        props = node["$properties"]
        objects.append(
            {
                "name": spec.name,
                "role": spec.role,
                "cframe": props["CFrame"],
                "size": props["Size"],
                "shape": props["Shape"],
                "can_collide": props["CanCollide"],
            }
        )
    return {
        "geometry_version": 1,
        "schema_version": recipe.schema_version,
        "name": recipe.name,
        "objects": objects,
    }


def _object_node(spec: SceneObject, index: int) -> tuple[dict[str, Any], bool]:
    position, size, rotation = _object_transform(spec)
    shape = "Block"
    approximated = spec.mesh is not None or spec.primitive in {"cone", "torus", "plane"}
    if spec.primitive in {"uv_sphere", "ico_sphere"}:
        shape = "Ball"
    elif spec.primitive == "cylinder":
        shape = "Cylinder"
        # Roblox cylinders use local X as their axis; the recipe's cylinder
        # uses Blender Z, which is Roblox Y after the basis conversion.
        rotation = _multiply_rotation(rotation, _rotation_z(math.pi / 2))
        size = (size[1], size[2], size[0])
    color = spec.material.base_color[:3] if spec.material is not None else _ROLE_COLOR[spec.role]
    material = _ROLE_MATERIAL[spec.role]
    properties: dict[str, Any] = {
        "Anchored": True,
        "CanCollide": spec.role not in {"water", "collectible"},
        "CFrame": [*position, *_flatten(rotation)],
        "Color": list(color),
        "Material": material,
        "Shape": shape,
        "Size": list(size),
        "Transparency": 0.25 if spec.role == "water" else 0.0,
    }
    if spec.role == "opening":
        properties["CanCollide"] = False
        properties["Transparency"] = 0.55
    elif spec.role == "collectible":
        properties["CanTouch"] = True
    elif spec.role == "hazard":
        properties["CanTouch"] = True
    return {"$className": "Part", "$properties": properties}, approximated


def _spawn_location_node(path: SceneObject) -> dict[str, Any]:
    """Place a trusted, neutral start pad above the first path segment."""
    position, size, rotation = _object_transform(path)
    spawn_position = (position[0], position[1] + size[1] / 2 + 2.5, position[2])
    return {
        "$className": "SpawnLocation",
        "$properties": {
            "AllowTeamChangeOnTouch": False,
            "Anchored": True,
            "CFrame": [*spawn_position, *_flatten(rotation)],
            "Duration": 0,
            "Enabled": True,
            "Neutral": True,
            "Size": [6, 1, 6],
        },
    }


def _environment_node(environment: SceneEnvironment) -> dict[str, Any]:
    properties = {
        "Ambient": list(environment.ambient_color),
        "OutdoorAmbient": list(environment.outdoor_ambient_color),
        "Brightness": environment.brightness,
        "ClockTime": environment.clock_time,
        "ExposureCompensation": environment.exposure_compensation,
        "GlobalShadows": environment.global_shadows,
        "ShadowSoftness": environment.shadow_softness,
    }
    atmosphere = environment.atmosphere
    return {
        "$className": "Lighting",
        "$properties": properties,
        "Atmosphere": {
            "$className": "Atmosphere",
            "$properties": {
                "Color": list(atmosphere.color),
                "Decay": list(atmosphere.decay),
                "Density": atmosphere.density,
                "Glare": atmosphere.glare,
                "Haze": atmosphere.haze,
                "Offset": atmosphere.offset,
            },
        },
    }


def _clouds_node(clouds: SceneClouds) -> dict[str, Any]:
    return {
        "$className": "Clouds",
        "$properties": {
            "Color": list(clouds.color),
            "Cover": clouds.cover,
            "Density": clouds.density,
            "Enabled": clouds.enabled,
        },
    }


def _object_transform(
    spec: SceneObject,
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[tuple[float, ...], ...]]:
    basis = ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
    blender_rotation = _rotation_matrix(spec.rotation_deg)
    rotation = _multiply_rotation(_multiply_rotation(basis, blender_rotation), basis)

    if spec.mesh is not None:
        vertices = spec.mesh.vertices
        mins = tuple(min(point[axis] for point in vertices) for axis in range(3))
        maxs = tuple(max(point[axis] for point in vertices) for axis in range(3))
        local_center = tuple((mins[axis] + maxs[axis]) / 2 for axis in range(3))
        dims = tuple(max(0.05, (maxs[axis] - mins[axis]) * spec.scale[axis]) for axis in range(3))
    else:
        extents = {
            "cube": (2.0, 2.0, 2.0),
            "uv_sphere": (2.0, 2.0, 2.0),
            "ico_sphere": (2.0, 2.0, 2.0),
            "cylinder": (2.0, 2.0, 2.0),
            "cone": (2.0, 2.0, 2.0),
            "plane": (2.0, 2.0, 0.1),
            "torus": (2.5, 2.5, 0.5),
        }[spec.primitive]
        local_center = (0.0, 0.0, 0.0)
        dims = tuple(max(0.05, extents[axis] * spec.scale[axis]) for axis in range(3))

    rotated_center = tuple(
        sum(
            blender_rotation[row][column] * local_center[column] * spec.scale[column]
            for column in range(3)
        )
        for row in range(3)
    )
    blender_position = tuple(spec.location[axis] + rotated_center[axis] for axis in range(3))
    position = (blender_position[0], blender_position[2], blender_position[1])
    size = (dims[0], dims[2], dims[1])
    return position, size, rotation


def _light_node(light: SceneLight, index: int) -> dict[str, Any] | None:
    if light.type == "SUN":
        return None
    position = (light.location[0], light.location[2], light.location[1])
    rotation = _multiply_rotation(
        _multiply_rotation(
            ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
            _rotation_matrix(light.rotation_deg),
        ),
        ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    )
    if light.type == "AREA":
        light_class = "SurfaceLight"
        light_properties = {"Face": "Top", "Angle": 180.0}
    elif light.type == "SPOT":
        light_class = "SpotLight"
        light_properties = {"Face": "Front", "Angle": light.spot_size_deg or 45.0}
    else:
        light_class = "PointLight"
        light_properties = {}
    light_properties.update(
        {
            "Brightness": min(10_000.0, max(0.0, light.energy / 10.0)),
            "Color": list(light.color),
            "Range": min(60.0, max(1.0, light.distance or 16.0)),
        }
    )
    return {
        "$className": "Part",
        "$properties": {
            "Anchored": True,
            "CanCollide": False,
            "CFrame": [*position, *_flatten(rotation)],
            "Size": [0.1, 0.1, 0.1],
            "Transparency": 1.0,
        },
        "Light": {"$className": light_class, "$properties": light_properties},
    }


def _safe_name(value: str) -> str:
    result = _NAME.sub("_", value).strip(" _-")
    return result[:64] or "Scene"


def _rotation_z(angle: float) -> tuple[tuple[float, float, float], ...]:
    cosine, sine = math.cos(angle), math.sin(angle)
    return ((cosine, -sine, 0.0), (sine, cosine, 0.0), (0.0, 0.0, 1.0))


def _multiply_rotation(
    left: tuple[tuple[float, ...], ...], right: tuple[tuple[float, ...], ...]
) -> tuple[tuple[float, float, float], ...]:
    return tuple(
        tuple(sum(left[row][k] * right[k][column] for k in range(3)) for column in range(3))
        for row in range(3)
    )


def _flatten(matrix: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
    return tuple(_clean(value) for row in matrix for value in row)


def _clean(value: float) -> float:
    if abs(value) < 1e-10:
        return 0.0
    return round(value, 10)


class RojoPlaceBuilder:
    """Build `.rbxlx` place files using a pinned Rojo executable."""

    def __init__(self, rojo_bin: str | Path = "rojo", *, timeout_seconds: float = 30) -> None:
        if not 1 <= timeout_seconds <= 120:
            raise ValueError("Rojo build timeout must be between 1 and 120 seconds")
        self.rojo_bin = str(rojo_bin)
        self.timeout_seconds = timeout_seconds
        try:
            version = subprocess.run(  # noqa: S603 - configured pinned binary, fixed arguments.
                [self.rojo_bin, "--version"],
                capture_output=True,
                check=False,
                timeout=min(timeout_seconds, 10),
                text=True,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RobloxPlaceBuildError("pinned Rojo executable is unavailable") from exc
        if version.returncode != 0 or ROJO_VERSION not in (version.stdout + version.stderr):
            raise RobloxPlaceBuildError(f"Rojo {ROJO_VERSION} is required to build place files")

    def build(
        self,
        payload: object,
        *,
        gameplay_mode: str = "blockout",
        imported_model: bytes | None = None,
        imported_meshpart_count: int = 0,
        gameplay_rules: object = None,
    ) -> RobloxPlaceBuild:
        if imported_model is not None and gameplay_mode != "blockout":
            raise RobloxPlaceBuildError(
                "imported Blender models currently require the script-free blockout mode"
            )
        if imported_model is None:
            if imported_meshpart_count != 0:
                raise RobloxPlaceBuildError("imported MeshPart count has no model data")
        else:
            _validate_imported_model_header(imported_model, imported_meshpart_count)
        project, summary = scene_recipe_to_rojo_project(
            payload,
            gameplay_mode=gameplay_mode,
            include_imported_model=imported_model is not None,
            gameplay_rules=gameplay_rules,
        )
        with tempfile.TemporaryDirectory(prefix="rga-rojo-") as directory:
            root = Path(directory)
            project_path = root / "default.project.json"
            output_path = root / "scene.rbxlx"
            project_path.write_text(
                json.dumps(project, ensure_ascii=True, separators=(",", ":")),
                encoding="utf-8",
            )
            script_template = gameplay_script(gameplay_mode)
            if script_template is not None:
                script_name = (
                    "obby_course.server.luau"
                    if gameplay_mode == "obby"
                    else "treasure_hunt.server.luau"
                    if gameplay_mode == "treasure_hunt"
                    else "rule_game.server.luau"
                )
                script_path = root / "server" / script_name
                script_path.parent.mkdir()
                script_path.write_text(script_template[1], encoding="utf-8", newline="\n")
            if imported_model is not None:
                model_path = root / "assets" / "imported-model.rbxm"
                model_path.parent.mkdir()
                model_path.write_bytes(imported_model)
            try:
                result = subprocess.run(  # noqa: S603 - fixed argv; recipe values are not commands.
                    [self.rojo_bin, "build", str(project_path), "--output", str(output_path)],
                    capture_output=True,
                    check=False,
                    timeout=self.timeout_seconds,
                    text=True,
                    cwd=root,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RobloxPlaceBuildError("Rojo place build failed or timed out") from exc
            if result.returncode != 0 or not output_path.is_file():
                raise RobloxPlaceBuildError("Rojo could not build the generated place project")
            place_file = output_path.read_bytes()
        if not place_file.startswith(b"<roblox") or len(place_file) > MAX_PLACE_FILE_BYTES:
            raise RobloxPlaceBuildError("Rojo produced an invalid or oversized place file")
        if b"<!DOCTYPE" in place_file.upper() or b"<!ENTITY" in place_file.upper():
            raise RobloxPlaceBuildError("Rojo produced XML with a forbidden document declaration")
        try:
            document = ET.fromstring(place_file)  # noqa: S314 - DTD and entities are rejected above.
        except ET.ParseError as exc:
            raise RobloxPlaceBuildError("Rojo produced invalid XML") from exc
        classes = [node.get("class") for node in document.iter("Item")]
        forbidden = _FORBIDDEN_CLASSES - ({"Script"} if script_template is not None else set())
        if any(class_name in forbidden for class_name in classes):
            raise RobloxPlaceBuildError("generated place unexpectedly contains executable code")
        if script_template is not None:
            expected_name, expected_source = script_template
            scripts = [node for node in document.iter("Item") if node.get("class") == "Script"]
            parents = {child: parent for parent in document.iter() for child in parent}
            if (
                len(scripts) != 1
                or parents.get(scripts[0], {}).get("class") != "ServerScriptService"
            ):
                raise RobloxPlaceBuildError(
                    "generated gameplay script is outside its fixed service"
                )
            properties = scripts[0].find("Properties")
            if properties is None:
                raise RobloxPlaceBuildError("generated gameplay script has no source properties")
            name = next((prop.text for prop in properties if prop.get("name") == "Name"), None)
            source = next(
                (
                    prop.text or ""
                    for prop in properties
                    if prop.tag in {"ProtectedString", "string"} and prop.get("name") == "Source"
                ),
                None,
            )
            if name != expected_name or source != expected_source:
                raise RobloxPlaceBuildError(
                    "generated gameplay source failed fixed-template review"
                )
        validate_gameplay_rules_artifact(
            document,
            gameplay_mode,
            gameplay_rules,
            payload if isinstance(payload, SceneRecipe) else SceneRecipe.from_mapping(payload),
        )
        if imported_model is not None:
            _validate_imported_model_tree(document, imported_meshpart_count)
        return RobloxPlaceBuild(
            place_file=place_file,
            gameplay_mode=gameplay_mode,
            imported_meshpart_count=imported_meshpart_count,
            **summary,
        )


def _validate_imported_model_header(model: object, meshpart_count: int) -> None:
    if not isinstance(model, bytes) or not 32 <= len(model) <= MAX_IMPORTED_MODEL_BYTES:
        raise RobloxPlaceBuildError("imported Roblox model is empty or exceeds its byte limit")
    if model[:14] != b"<roblox!\x89\xff\r\n\x1a\n" or model[14:16] != b"\x00\x00":
        raise RobloxPlaceBuildError("imported model is not a Roblox binary model")
    classes, instances = struct.unpack_from("<ii", model, 16)
    if (
        not 1 <= classes <= 16
        or not 1 <= instances <= 512
        or type(meshpart_count) is not int
        or not 1 <= meshpart_count <= min(128, instances)
    ):
        raise RobloxPlaceBuildError("imported model header or MeshPart count is invalid")


def _validate_imported_model_tree(document: ET.Element, expected_meshparts: int) -> None:
    items = list(document.iter("Item"))
    parents = {child: parent for parent in document.iter() for child in parent}
    roots = []
    for item in items:
        properties = item.find("Properties")
        name = next((prop.text for prop in properties or [] if prop.get("name") == "Name"), None)
        parent = parents.get(item)
        parent_properties = parent.find("Properties") if parent is not None else None
        parent_name = next(
            (prop.text for prop in parent_properties or [] if prop.get("name") == "Name"),
            None,
        )
        if name == "RGA Imported Model" and parent_name == "Imported Blender Model":
            roots.append(item)
    if len(roots) != 1:
        if expected_meshparts == 0 and not roots:
            return
        raise RobloxPlaceBuildError("generated place lost its imported model root")
    allowed = {"Model", "Folder", "MeshPart", "SurfaceAppearance"}
    imported_items = list(roots[0].iter("Item"))
    if not imported_items or any(item.get("class") not in allowed for item in imported_items):
        raise RobloxPlaceBuildError("imported model contains unsupported Roblox instances")
    meshparts = [item for item in imported_items if item.get("class") == "MeshPart"]
    if len(meshparts) != expected_meshparts:
        raise RobloxPlaceBuildError("generated place MeshPart count does not match inspection")
    for item in imported_items:
        if item.get("class") == "SurfaceAppearance":
            if parents.get(item, {}).get("class") != "MeshPart":
                raise RobloxPlaceBuildError("SurfaceAppearance is outside an imported MeshPart")
    for item in meshparts:
        properties = item.find("Properties")
        _validate_imported_mesh_geometry(properties)
        mesh_id = next(
            (
                prop.findtext("uri") or prop.findtext("url")
                for prop in properties or []
                if prop.get("name") in {"MeshId", "MeshContent"}
                and prop.tag in {"Content", "ContentId"}
            ),
            None,
        )
        if not isinstance(mesh_id, str) or not re.fullmatch(
            r"rbxassetid://[1-9][0-9]{0,19}", mesh_id, re.ASCII
        ):
            raise RobloxPlaceBuildError("imported MeshPart has an unsupported mesh reference")


def _validate_imported_mesh_geometry(properties: ET.Element | None) -> None:
    """Verify the static geometry contract after the engine/Rojo handoff."""
    props = list(properties) if properties is not None else []
    names = [prop.get("name") for prop in props]
    if len(names) != len(set(names)):
        raise RobloxPlaceBuildError("imported MeshPart has duplicate properties")
    anchored = next((prop for prop in props if prop.get("name") == "Anchored"), None)
    if anchored is None or anchored.tag != "bool" or anchored.text != "true":
        raise RobloxPlaceBuildError("imported MeshPart must be anchored")

    def components(names: set[str], tag: str, fields: tuple[str, ...]) -> list[float]:
        candidates = [prop for prop in props if prop.get("name") in names]
        if len(candidates) != 1 or candidates[0].tag != tag:
            raise RobloxPlaceBuildError("imported MeshPart has missing or invalid geometry")
        node = candidates[0]
        if len(node) != len(fields) or {child.tag for child in node} != set(fields):
            raise RobloxPlaceBuildError("imported MeshPart has invalid geometry components")
        try:
            values = [float(node.findtext(field, "")) for field in fields]
        except ValueError as exc:
            raise RobloxPlaceBuildError("imported MeshPart has nonnumeric geometry") from exc
        if not all(math.isfinite(value) for value in values):
            raise RobloxPlaceBuildError("imported MeshPart has nonfinite geometry")
        return values

    size = components({"size", "Size"}, "Vector3", ("X", "Y", "Z"))
    if any(value <= 0 for value in size):
        raise RobloxPlaceBuildError("imported MeshPart dimensions must be positive")
    components(
        {"CFrame"},
        "CoordinateFrame",
        ("X", "Y", "Z", "R00", "R01", "R02", "R10", "R11", "R12", "R20", "R21", "R22"),
    )
