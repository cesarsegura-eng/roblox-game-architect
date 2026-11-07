"""Strict data-only validator for Scene Recipes v1 through v3 (no Blender dependency)."""

from __future__ import annotations

import json
import math
import re
from typing import Any

MAX_RECIPE_BYTES = 1_048_576
MAX_OBJECTS = 512
MAX_LIGHTS = 16
MAX_CHARACTERS = 8
MAX_MESH_VERTICES = 2_000
MAX_MESH_FACES = 2_000
NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9 _-]{0,63}\Z", re.ASCII)
PRIMITIVES = frozenset({"cube", "uv_sphere", "ico_sphere", "cylinder", "cone", "plane", "torus"})
ROLES = frozenset(
    {
        "terrain",
        "path",
        "architecture",
        "exterior",
        "interior",
        "entry",
        "courtyard",
        "roof",
        "opening",
        "furnishing",
        "vegetation",
        "rock",
        "water",
        "prop",
        "landmark",
        "character_blockout",
        "collectible",
        "hazard",
    }
)
V1_ROLES = frozenset(
    {
        "terrain",
        "architecture",
        "furnishing",
        "vegetation",
        "rock",
        "water",
        "prop",
        "landmark",
        "character_blockout",
    }
)
V2_ROLES = ROLES - {"hazard"}
LIGHT_TYPES = frozenset({"SUN", "AREA", "POINT", "SPOT"})


class RecipeError(ValueError):
    """Invalid or unsupported recipe data."""


def parse_recipe(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or len(text.encode("utf-8", errors="strict")) > MAX_RECIPE_BYTES:
        raise RecipeError("recipe is not text or exceeds the size limit")
    try:
        data = json.loads(
            text,
            object_pairs_hook=_unique_keys,
            parse_constant=lambda value: _invalid_constant(value),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise RecipeError("recipe is not strict JSON") from exc
    _validate_recipe(data)
    return data


def _validate_recipe(data: object) -> None:
    required = {"schema_version", "name", "units", "up_axis", "objects"}
    optional = {"lights", "characters", "environment"}
    if not isinstance(data, dict) or not required <= set(data) or set(data) - required - optional:
        raise RecipeError("recipe has unexpected or missing top-level fields")
    if type(data["schema_version"]) is not int or data["schema_version"] not in {1, 2, 3}:
        raise RecipeError("unsupported scene recipe version")
    if data["schema_version"] == 3:
        _validate_environment(data.get("environment"))
    elif "environment" in data:
        raise RecipeError("environment settings require scene recipe version 3")
    if data["units"] != "blender_units" or data["up_axis"] != "Z":
        raise RecipeError("recipe must use Blender units and Z-up coordinates")
    _require_name(data["name"], "scene name")
    objects = data["objects"]
    lights = data.get("lights", [])
    characters = data.get("characters", [])
    if (
        not isinstance(objects, list)
        or len(objects) > MAX_OBJECTS
        or (not objects and not characters)
    ):
        raise RecipeError("scene must contain between 1 and 512 objects")
    if not isinstance(lights, list) or len(lights) > MAX_LIGHTS:
        raise RecipeError("scene supports at most 16 lights")
    if (
        not isinstance(characters, list)
        or len(characters) > MAX_CHARACTERS
        or (data["schema_version"] == 1 and characters)
    ):
        raise RecipeError("characters require a version 2+ recipe with at most 8 entries")

    names: set[str] = set()
    for item in objects:
        _validate_object(item, data["schema_version"])
        if item["name"] in names:
            raise RecipeError("object and light names must be unique")
        names.add(item["name"])
    for light in lights:
        _validate_light(light)
        if light["name"] in names:
            raise RecipeError("object and light names must be unique")
        names.add(light["name"])
    for character in characters:
        _validate_character(character)
        if character["name"] in names:
            raise RecipeError("scene object, light, and character names must be unique")
        names.add(character["name"])


def _validate_character(character: object) -> None:
    if not isinstance(character, dict) or set(character) != {"name", "motion", "location", "scale"}:
        raise RecipeError("character has unexpected or missing fields")
    _require_name(character["name"], "character name")
    if not isinstance(character["motion"], str) or character["motion"] not in {
        "WALK",
        "RUN",
        "JUMP",
        "IDLE",
    }:
        raise RecipeError("character motion must be WALK, RUN, JUMP, or IDLE")
    _vector(character["location"], "character location", -10_000, 10_000)
    _vector(character["scale"], "character scale", 0.25, 4)


def _validate_environment(environment: object) -> None:
    required = {
        "ambient_color",
        "outdoor_ambient_color",
        "brightness",
        "clock_time",
        "exposure_compensation",
        "global_shadows",
        "shadow_softness",
        "atmosphere",
    }
    if (
        not isinstance(environment, dict)
        or not required <= set(environment)
        or set(environment) - required - {"clouds"}
    ):
        raise RecipeError("environment has unexpected or missing fields")
    _vector(environment["ambient_color"], "ambient_color", 0, 1)
    _vector(environment["outdoor_ambient_color"], "outdoor_ambient_color", 0, 1)
    _number(environment["brightness"], "brightness", 0, 10)
    _number(environment["clock_time"], "clock_time", 0, 24)
    _number(environment["exposure_compensation"], "exposure_compensation", -5, 5)
    if type(environment["global_shadows"]) is not bool:
        raise RecipeError("global_shadows must be boolean")
    _number(environment["shadow_softness"], "shadow_softness", 0, 1)
    atmosphere = environment["atmosphere"]
    if not isinstance(atmosphere, dict) or set(atmosphere) != {
        "color",
        "decay",
        "density",
        "glare",
        "haze",
        "offset",
    }:
        raise RecipeError("atmosphere has unexpected or missing fields")
    _vector(atmosphere["color"], "atmosphere color", 0, 1)
    _vector(atmosphere["decay"], "atmosphere decay", 0, 1)
    _number(atmosphere["density"], "atmosphere density", 0, 1)
    _number(atmosphere["glare"], "atmosphere glare", 0, 10)
    _number(atmosphere["haze"], "atmosphere haze", 0, 10)
    _number(atmosphere["offset"], "atmosphere offset", 0, 1)
    if "clouds" in environment:
        clouds = environment["clouds"]
        if not isinstance(clouds, dict) or set(clouds) != {"color", "cover", "density", "enabled"}:
            raise RecipeError("clouds have unexpected or missing fields")
        _vector(clouds["color"], "cloud color", 0, 1)
        _number(clouds["cover"], "cloud cover", 0, 1)
        _number(clouds["density"], "cloud density", 0, 1)
        if type(clouds["enabled"]) is not bool:
            raise RecipeError("clouds enabled must be boolean")


def _validate_object(item: object, version: int) -> None:
    required = {"name", "role", "location", "rotation_deg", "scale"}
    if version == 1:
        required.add("primitive")
    optional = {"primitive", "mesh", "bevel", "smooth_shading", "material"}
    if not isinstance(item, dict) or not required <= set(item) or set(item) - required - optional:
        raise RecipeError("object has unexpected or missing fields")
    _require_name(item["name"], "object name")
    allowed_roles = V1_ROLES if version == 1 else V2_ROLES if version == 2 else ROLES
    if not isinstance(item["role"], str) or item["role"] not in allowed_roles:
        raise RecipeError("object role is unsupported")
    primitive_present = "primitive" in item
    mesh_present = "mesh" in item
    if version == 1 and mesh_present:
        raise RecipeError("custom meshes require scene recipe version 2")
    if version >= 2 and primitive_present == mesh_present:
        raise RecipeError("version 2+ objects need exactly one geometry field")
    if primitive_present and (
        not isinstance(item["primitive"], str) or item["primitive"] not in PRIMITIVES
    ):
        raise RecipeError("object primitive is unsupported")
    if mesh_present:
        _validate_mesh(item["mesh"])
    _vector(item["location"], "location", -10_000, 10_000)
    _vector(item["rotation_deg"], "rotation_deg", -36_000, 36_000)
    _vector(item["scale"], "scale", 0.001, 1000, exclusive=True)
    if "bevel" in item:
        _number(item["bevel"], "bevel", 0, 1)
    if "smooth_shading" in item and type(item["smooth_shading"]) is not bool:
        raise RecipeError("smooth_shading must be boolean")
    if "material" in item:
        material = item["material"]
        if not isinstance(material, dict) or set(material) != {"base_color", "roughness"}:
            raise RecipeError("material has unexpected or missing fields")
        _vector(material["base_color"], "base_color", 0, 1, size=4)
        _number(material["roughness"], "roughness", 0, 1)


def _validate_mesh(mesh: object) -> None:
    if not isinstance(mesh, dict) or set(mesh) != {"vertices", "faces"}:
        raise RecipeError("mesh must contain only vertices and faces")
    vertices = mesh["vertices"]
    faces = mesh["faces"]
    if not isinstance(vertices, list) or not 3 <= len(vertices) <= MAX_MESH_VERTICES:
        raise RecipeError("mesh vertices must contain between 3 and 2000 points")
    if not isinstance(faces, list) or not 1 <= len(faces) <= MAX_MESH_FACES:
        raise RecipeError("mesh faces must contain between 1 and 2000 polygons")
    for vertex in vertices:
        _vector(vertex, "mesh vertex", -1000, 1000)
    for face in faces:
        if not isinstance(face, list) or not 3 <= len(face) <= 32:
            raise RecipeError("each mesh face must reference 3 to 32 vertices")
        if any(type(index) is not int for index in face):
            raise RecipeError("mesh face indices must be integers")
        if len(set(face)) != len(face) or any(
            index < 0 or index >= len(vertices) for index in face
        ):
            raise RecipeError("mesh face indices must be unique and in range")


def _validate_light(light: object) -> None:
    required = {"name", "type", "location", "rotation_deg", "color", "energy"}
    optional = {"distance", "spot_size_deg", "angle_deg"}
    if (
        not isinstance(light, dict)
        or not required <= set(light)
        or set(light) - required - optional
    ):
        raise RecipeError("light has unexpected or missing fields")
    _require_name(light["name"], "light name")
    if not isinstance(light["type"], str) or light["type"] not in LIGHT_TYPES:
        raise RecipeError("light type is unsupported")
    _vector(light["location"], "light location", -10_000, 10_000)
    _vector(light["rotation_deg"], "light rotation", -36_000, 36_000)
    _vector(light["color"], "light color", 0, 1, size=3)
    _number(light["energy"], "light energy", 0, 100_000)
    if "distance" in light:
        _number(light["distance"], "light distance", 0.001, 10_000, exclusive=True)
    if "spot_size_deg" in light:
        _number(light["spot_size_deg"], "spot size", 1, 180)
    if "angle_deg" in light:
        _number(light["angle_deg"], "sun angle", 0.01, 45, exclusive=True)


def _require_name(value: object, label: str) -> None:
    if not isinstance(value, str) or NAME_PATTERN.fullmatch(value) is None:
        raise RecipeError(f"{label} is invalid")


def _vector(
    value: object,
    label: str,
    low: float,
    high: float,
    *,
    size: int = 3,
    exclusive: bool = False,
) -> None:
    if not isinstance(value, list) or len(value) != size:
        raise RecipeError(f"{label} must contain exactly {size} numbers")
    for component in value:
        _number(component, label, low, high, exclusive)


def _number(value: object, label: str, low: float, high: float, exclusive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecipeError(f"{label} must contain finite numbers")
    number = float(value)
    if not math.isfinite(number) or (number <= low if exclusive else number < low) or number > high:
        raise RecipeError(f"{label} is outside the supported range")
    return number


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RecipeError("recipe contains duplicate JSON keys")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise RecipeError(f"invalid JSON number: {value}")
