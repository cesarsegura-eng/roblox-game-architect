"""Generate strict Blender scene recipes with the project's environment skills.

The model returns JSON data, never executable Blender Python. Blender's add-on
validates the same recipe contract before creating geometry.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from .budget import BudgetedLLMProvider, IterationBudget, SpendBudget
from .llm.provider import LLMProvider
from .llm.types import (
    CostQuote,
    GenerationRequest,
    GenerationResponse,
    TrustedInstruction,
    UntrustedContent,
)
from .skills import SkillLibrary
from .spatial import (
    PATH_SEGMENT_MAX_GAP,
    bounds_distance,
    largest_connected_component,
    object_bounds,
)

SCENE_RECIPE_VERSION = 3
SUPPORTED_RECIPE_VERSIONS = frozenset({1, 2, 3})
MAX_RECIPE_BYTES = 1_048_576
MAX_SCENE_OBJECTS = 512
MAX_SCENE_LIGHTS = 16
MAX_SCENE_CHARACTERS = 8
CHARACTER_OUTPUT_OBJECTS = 17
MAX_RENDERED_OBJECTS = (
    MAX_SCENE_OBJECTS + MAX_SCENE_LIGHTS + MAX_SCENE_CHARACTERS * CHARACTER_OUTPUT_OBJECTS
)
MAX_MESH_VERTICES = 2_000
MAX_MESH_FACES = 2_000
COLLECTIBLE_ROUTE_MAX_GAP = 16.0
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9 _-]{0,63}\Z", re.ASCII)
_PRIMITIVES = frozenset({"cube", "uv_sphere", "ico_sphere", "cylinder", "cone", "plane", "torus"})
_ROLES = frozenset(
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
_LIGHT_TYPES = frozenset({"SUN", "AREA", "POINT", "SPOT"})
_V1_ROLES = frozenset(
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
_V2_ROLES = _ROLES - {"hazard"}
_ROLE_PROXIMITIES = (
    ("path", "entry", 5.0),
    ("entry", "exterior", 8.0),
    ("roof", "exterior", 12.0),
    ("entry", "courtyard", 8.0),
    ("courtyard", "interior", 10.0),
    ("entry", "interior", 10.0),
    ("entry", "opening", 8.0),
    ("opening", "interior", 8.0),
    ("roof", "interior", 10.0),
    ("roof", "courtyard", 12.0),
)
DEFAULT_WORLD_SKILLS = ("world-environments", "blender-scene-authoring")
_CHARACTER_SKILL_TERMS = frozenset(
    {
        "anatomy",
        "anatomies",
        "animation",
        "animations",
        "animate",
        "animating",
        "animated",
        "avatar",
        "avatars",
        "character",
        "characters",
        "creature",
        "creatures",
        "humanoid",
        "humanoids",
        "gait",
        "locomotion",
        "npc",
        "rig",
        "rigging",
        "rigged",
        "rigs",
        "skeleton",
        "skeletons",
        "skeletal",
        "walk",
        "walking",
        "walkcycle",
        "run",
        "running",
        "sprint",
        "sprinting",
        "jump",
        "jumping",
        "caminar",
        "caminando",
        "caminata",
        "caminatas",
        "correr",
        "corriendo",
        "animar",
        "animaciones",
        "animado",
        "animada",
        "modelaje",
        "modelado",
        "modelar",
        "saltar",
        "salto",
        "saltando",
        "esqueleto",
        "hueso",
        "huesos",
        "articulación",
        "articulacion",
        "articulaciones",
        "marcha",
        "marchas",
        "posing",
        "pose",
        "poses",
        "anatomia",
        "anatomía",
        "anatomías",
        "anatómico",
        "anatomico",
        "anatómica",
        "anatomica",
        "animación",
        "animacion",
        "criatura",
        "criaturas",
        "personaje",
        "personajes",
        "habitante",
        "habitantes",
        "protagonista",
        "protagonistas",
        "movimiento",
        "movimientos",
    }
)
_SCENE_SCHEMA_PATH = Path(__file__).parent / "schemas" / "scene-recipe-v3.schema.json"


class WorldbuildingError(ValueError):
    """A world brief, skill, or generated scene recipe is invalid."""


class WorldRecipeGenerationError(WorldbuildingError):
    """The bounded generation loop could not produce a valid scene recipe."""


_Entry = TypeVar("_Entry")


def _parse_entries(
    items: list[Any], field: str, parse: Callable[[Any], _Entry]
) -> tuple[_Entry, ...]:
    entries = []
    for index, item in enumerate(items):
        try:
            entries.append(parse(item))
        except WorldbuildingError as exc:
            raise WorldbuildingError(f"{field}[{index}]: {exc}") from exc
    return tuple(entries)


@dataclass(frozen=True, slots=True)
class SceneMaterial:
    base_color: tuple[float, float, float, float]
    roughness: float


@dataclass(frozen=True, slots=True)
class SceneMesh:
    """Bounded low-poly mesh data expressed in object-local coordinates."""

    vertices: tuple[tuple[float, float, float], ...]
    faces: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class SceneObject:
    name: str
    primitive: str | None
    role: str
    location: tuple[float, float, float]
    rotation_deg: tuple[float, float, float]
    scale: tuple[float, float, float]
    bevel: float = 0.0
    smooth_shading: bool = False
    material: SceneMaterial | None = None
    mesh: SceneMesh | None = None


@dataclass(frozen=True, slots=True)
class SceneLight:
    name: str
    type: str
    location: tuple[float, float, float]
    rotation_deg: tuple[float, float, float]
    color: tuple[float, float, float]
    energy: float
    distance: float | None = None
    spot_size_deg: float | None = None
    angle_deg: float | None = None


@dataclass(frozen=True, slots=True)
class SceneCharacter:
    """Bounded generic humanoid blockout and motion preset for Blender."""

    name: str
    motion: str
    location: tuple[float, float, float]
    scale: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class SceneAtmosphere:
    color: tuple[float, float, float]
    decay: tuple[float, float, float]
    density: float
    glare: float
    haze: float
    offset: float


@dataclass(frozen=True, slots=True)
class SceneClouds:
    color: tuple[float, float, float]
    cover: float
    density: float
    enabled: bool


@dataclass(frozen=True, slots=True)
class SceneEnvironment:
    ambient_color: tuple[float, float, float]
    outdoor_ambient_color: tuple[float, float, float]
    brightness: float
    clock_time: float
    exposure_compensation: float
    global_shadows: bool
    shadow_softness: float
    atmosphere: SceneAtmosphere
    clouds: SceneClouds | None = None


@dataclass(frozen=True, slots=True)
class SceneRecipe:
    name: str
    objects: tuple[SceneObject, ...]
    lights: tuple[SceneLight, ...] = ()
    characters: tuple[SceneCharacter, ...] = ()
    schema_version: int = SCENE_RECIPE_VERSION
    environment: SceneEnvironment | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "objects", tuple(self.objects))
        object.__setattr__(self, "lights", tuple(self.lights))
        object.__setattr__(self, "characters", tuple(self.characters))
        _validate_recipe(self)

    @classmethod
    def from_json(cls, text: str) -> SceneRecipe:
        if not isinstance(text, str):
            raise WorldbuildingError("scene recipe must be JSON text")
        if len(text.encode("utf-8", errors="strict")) > MAX_RECIPE_BYTES:
            raise WorldbuildingError("scene recipe exceeds the input size limit")
        try:
            payload = json.loads(
                text,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_non_finite,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise WorldbuildingError("scene recipe is not strict JSON") from exc
        return cls.from_mapping(payload)

    @classmethod
    def from_mapping(cls, payload: object) -> SceneRecipe:
        required = {"schema_version", "name", "units", "up_axis", "objects"}
        if (
            not isinstance(payload, dict)
            or not required <= set(payload)
            or set(payload) - required - {"lights", "characters", "environment"}
        ):
            raise WorldbuildingError("scene recipe has unexpected or missing top-level fields")
        if (
            type(payload["schema_version"]) is not int
            or payload["schema_version"] not in SUPPORTED_RECIPE_VERSIONS
        ):
            raise WorldbuildingError("unsupported scene recipe version")
        if payload["units"] != "blender_units" or payload["up_axis"] != "Z":
            raise WorldbuildingError("scene recipe must use Blender units and Z-up coordinates")
        if not isinstance(payload["objects"], list) or len(payload["objects"]) > MAX_SCENE_OBJECTS:
            raise WorldbuildingError("objects must be an array")
        lights_payload = payload.get("lights", [])
        if not isinstance(lights_payload, list) or len(lights_payload) > MAX_SCENE_LIGHTS:
            raise WorldbuildingError("lights must be an array")
        characters_payload = payload.get("characters", [])
        if (payload["schema_version"] == 1 and "characters" in payload) or (
            not isinstance(characters_payload, list)
            or len(characters_payload) > MAX_SCENE_CHARACTERS
        ):
            raise WorldbuildingError("characters must be a version 2 array with at most 8 entries")

        objects = _parse_entries(
            payload["objects"],
            "objects",
            lambda item: _parse_object(item, version=payload["schema_version"]),
        )
        lights = _parse_entries(lights_payload, "lights", _parse_light)
        characters = _parse_entries(characters_payload, "characters", _parse_character)
        environment_payload = payload.get("environment")
        if payload["schema_version"] == 3:
            if "environment" not in payload:
                raise WorldbuildingError("version 3 recipes require an environment block")
            environment = _parse_environment(environment_payload)
        else:
            if environment_payload is not None:
                raise WorldbuildingError("environment settings require scene recipe version 3")
            environment = None
        return cls(
            name=payload["name"],
            objects=objects,
            lights=lights,
            characters=characters,
            schema_version=payload["schema_version"],
            environment=environment,
        )

    def to_mapping(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "name": self.name,
            "units": "blender_units",
            "up_axis": "Z",
            "objects": [_object_mapping(item) for item in self.objects],
        }
        if self.lights:
            result["lights"] = [_light_mapping(item) for item in self.lights]
        if self.characters:
            result["characters"] = [_character_mapping(item) for item in self.characters]
        if self.environment is not None:
            result["environment"] = _environment_mapping(self.environment)
        return result

    @property
    def rendered_object_count(self) -> int:
        return (
            len(self.objects) + len(self.lights) + len(self.characters) * CHARACTER_OUTPUT_OBJECTS
        )

    def to_json(self) -> str:
        return json.dumps(self.to_mapping(), ensure_ascii=False, indent=2, allow_nan=False) + "\n"


@dataclass(frozen=True, slots=True)
class WorldBuildResult:
    recipe: SceneRecipe
    iterations: int
    responses: tuple[GenerationResponse, ...]
    skill_names: tuple[str, ...]

    def write_recipe(self, path: str | Path) -> Path:
        """Write JSON for the Blender add-on, refusing to overwrite an existing file."""
        destination = Path(path)
        if destination.suffix.lower() != ".json":
            raise WorldbuildingError("scene recipe output must use a .json extension")
        try:
            with destination.open("x", encoding="utf-8", newline="\n") as output:
                output.write(self.recipe.to_json())
        except FileExistsError as exc:
            raise WorldbuildingError(
                "scene recipe output already exists; choose a new path"
            ) from exc
        return destination


_WORLD_DESIGN_INSTRUCTION = """You design original, playable environments and Blender blockouts.
Return exactly one JSON object matching the provided Scene Recipe v3 contract.
Return no Markdown, commentary, Python, code, scripts, file paths, or extra fields.
Use the listed primitives or create a bounded low-poly mesh with local vertices
and polygon faces (maximum 2000 vertices and 2000 faces per object). Prefer a
few purposeful silhouettes over microgeometry. Keep the scene coherent with the
requested biome, climate, terrain, human use, gameplay route, architecture,
interior/exterior relationship, scale, and atmosphere. Build a clear large-form
layout first, then a restrained set of midground and close details. Name objects
uniquely and use a small number of simple lights to support the desired mood.
Always include the v3 environment block. Choose global ambient and outdoor colors,
brightness, time of day, exposure, shadows, atmosphere color/decay/density/haze,
and optional cloud cover to reinforce the requested climate and mood without
obscuring the playable route. These values become Roblox Lighting, Atmosphere,
and optional Terrain Clouds settings in a script-free place artifact.
Mark walkable trails, roads, boardwalks, and traversal platforms with the `path`
role; use connected segments with consistent width so the intended route reads
clearly in the blockout.
For a Treasure Hunt game build, mark every pickup with the `collectible` role
and place them along the intended route; these objects become touch collectibles
scored by the built-in server-side gameplay template. For dangerous obstacles,
use the `hazard` role; built-in Obby and Treasure Hunt scripts treat these parts
as lethal touch hazards with standard Roblox respawns.
For a simple checkpoint Obby build, provide at least two ordered, connected route
segments with the `path` role. The selected fixed Obby template creates a
checkpoint/respawn pad over each segment, requires players to touch them in
order, tracks the current stage, and awards session-only wins at the final
checkpoint. It does not create moving platforms, persistent saves, or
custom model-authored Luau; describe those as unimplemented unless another fixed
template explicitly supports them.
For buildings, assign semantic roles to distinguish exterior massing, entries,
courtyards, interiors, roofs, openings, and furnishings; include separate
playable exterior and interior spatial cues when both are requested.
Use a `characters` entry only when a humanoid NPC blockout is requested; it
creates a generic rigid-weighted skeleton and a fixed WALK, RUN, JUMP, or IDLE
motion preset, not a production avatar. This is still a blockout: do not claim UVs, textures, or
production topology unless they are explicitly represented."""


class WorldDesignAgent:
    """Use selected project skills to generate a budgeted, validated Blender recipe."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        skills: SkillLibrary | None = None,
        iterations: IterationBudget | None = None,
        spend: SpendBudget | None = None,
    ) -> None:
        self._skills = skills or SkillLibrary()
        self._iterations = iterations or IterationBudget.from_env()
        self._spend = spend or SpendBudget.from_env()
        self._provider = BudgetedLLMProvider(provider, self._spend)
        try:
            schema = _SCENE_SCHEMA_PATH.read_text(encoding="utf-8")
            if len(schema.encode("utf-8")) > 64_000:
                raise OSError("schema exceeds its prompt-size limit")
        except OSError as exc:
            raise WorldbuildingError("Scene Recipe v3 schema is unavailable") from exc
        self._schema_text = schema

    def generate(
        self,
        brief: str,
        *,
        project_context: tuple[UntrustedContent, ...] = (),
        skill_names: tuple[str, ...] | None = None,
        max_output_tokens: int = 8192,
    ) -> WorldBuildResult:
        """Generate a recipe or raise after the configured iteration bound.

        User brief is the trusted request. Existing place descriptions, maps,
        notes, and other project material stay in the untrusted data channel.
        """
        if not isinstance(brief, str) or not brief.strip():
            raise WorldbuildingError("world brief must be non-empty text")
        context = tuple(project_context)
        if any(not isinstance(item, UntrustedContent) for item in context):
            raise TypeError("project_context must contain UntrustedContent values")
        selected_names = _select_skill_names(brief) if skill_names is None else tuple(skill_names)
        if not selected_names or len(set(selected_names)) != len(selected_names):
            raise WorldbuildingError("select one or more unique skill packs")
        selected_skills = tuple(self._skills.load(name) for name in selected_names)
        required_roles = _required_scene_roles(brief)
        skill_instructions = tuple(
            TrustedInstruction(f"Project skill pack: {skill.name}\n{skill.instructions}")
            for skill in selected_skills
        )

        previous_output: str | None = None
        feedback: str | None = None
        responses: list[GenerationResponse] = []
        while self._iterations.remaining:
            self._iterations.consume()
            instructions = [
                TrustedInstruction(_WORLD_DESIGN_INSTRUCTION),
                TrustedInstruction(f"Scene Recipe v3 JSON Schema:\n{self._schema_text}"),
                TrustedInstruction(f"World design brief:\n{brief}"),
                *skill_instructions,
            ]
            untrusted = list(context)
            if previous_output is not None:
                untrusted.append(UntrustedContent("previous_generated_recipe", previous_output))
            if feedback is not None:
                untrusted.append(UntrustedContent("recipe_validation_feedback", feedback))
            request = GenerationRequest(
                instructions=tuple(instructions),
                untrusted=tuple(untrusted),
                max_output_tokens=max_output_tokens,
            )
            response = self._provider.generate(request)
            if not isinstance(response, GenerationResponse) or not isinstance(response.text, str):
                raise TypeError("LLM provider returned an invalid generation response")
            responses.append(response)
            previous_output = response.text
            try:
                if response.finish_reason == "length":
                    raise WorldbuildingError("recipe output was truncated")
                recipe = SceneRecipe.from_json(response.text)
                _validate_requested_world_roles(recipe, required_roles)
                if recipe.schema_version != SCENE_RECIPE_VERSION:
                    raise WorldbuildingError(
                        f"newly generated recipes must use Scene Recipe v{SCENE_RECIPE_VERSION}"
                    )
            except WorldbuildingError as exc:
                feedback = str(exc)
                continue
            return WorldBuildResult(
                recipe=recipe,
                iterations=len(responses),
                responses=tuple(responses),
                skill_names=selected_names,
            )

        raise WorldRecipeGenerationError(
            f"no valid Blender scene recipe after {len(responses)} bounded attempts"
        )

    def quote_next_call(self, brief: str, *, max_output_tokens: int = 8192) -> CostQuote | None:
        """Return the provider's upper bound for the first call of this brief.

        Later repair attempts have additional untrusted context and are quoted
        independently by ``BudgetedLLMProvider`` before they can be sent.
        """
        if not isinstance(brief, str) or not brief.strip():
            raise WorldbuildingError("world brief must be non-empty text")
        selected_names = _select_skill_names(brief)
        skill_instructions = tuple(
            TrustedInstruction(f"Project skill pack: {skill.name}\n{skill.instructions}")
            for skill in (self._skills.load(name) for name in selected_names)
        )
        request = GenerationRequest(
            instructions=(
                TrustedInstruction(_WORLD_DESIGN_INSTRUCTION),
                TrustedInstruction(f"Scene Recipe v3 JSON Schema:\n{self._schema_text}"),
                TrustedInstruction(f"World design brief:\n{brief}"),
                *skill_instructions,
            ),
            max_output_tokens=max_output_tokens,
        )
        return self._provider.quote_max_cost(request)


def _parse_object(payload: object, *, version: int) -> SceneObject:
    required = {"name", "primitive", "role", "location", "rotation_deg", "scale"}
    optional = {"primitive", "bevel", "smooth_shading", "material", "mesh"}
    if version >= 2:
        required -= {"primitive"}
        required |= {"name", "role", "location", "rotation_deg", "scale"}
    if (
        not isinstance(payload, dict)
        or not required <= set(payload)
        or set(payload) - required - optional
    ):
        raise WorldbuildingError("scene object has unexpected or missing fields")
    name = payload["name"]
    primitive = payload.get("primitive")
    role = payload["role"]
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise WorldbuildingError("scene object name is invalid")
    mesh_payload = payload.get("mesh")
    if version == 1 and "mesh" in payload:
        raise WorldbuildingError("custom meshes require scene recipe version 2")
    if version >= 2 and ((primitive is None) == (mesh_payload is None)):
        raise WorldbuildingError("version 2+ objects need exactly one primitive or mesh")
    if primitive is not None and (not isinstance(primitive, str) or primitive not in _PRIMITIVES):
        raise WorldbuildingError("scene object primitive is unsupported")
    supported_roles = _V1_ROLES if version == 1 else _V2_ROLES if version == 2 else _ROLES
    if not isinstance(role, str) or role not in supported_roles:
        raise WorldbuildingError("scene object role is unsupported")
    mesh = _parse_mesh(mesh_payload) if mesh_payload is not None else None
    if version == 1 and primitive is None:
        raise WorldbuildingError("version 1 objects require a primitive")
    if version >= 2 and ("primitive" in payload) == ("mesh" in payload):
        raise WorldbuildingError("version 2+ objects need exactly one geometry field")
    location = _vector(payload["location"], "location", -10_000, 10_000)
    rotation = _vector(payload["rotation_deg"], "rotation_deg", -36_000, 36_000)
    scale = _vector(payload["scale"], "scale", 0.001, 1_000, minimum_exclusive=True)
    bevel = _number(payload.get("bevel", 0), "bevel", 0, 1)
    smooth = payload.get("smooth_shading", False)
    if not isinstance(smooth, bool):
        raise WorldbuildingError("smooth_shading must be boolean")

    material_payload = payload.get("material")
    material = None
    if "material" in payload:
        if not isinstance(material_payload, dict) or set(material_payload) != {
            "base_color",
            "roughness",
        }:
            raise WorldbuildingError("material has unexpected or missing fields")
        material = SceneMaterial(
            base_color=_vector(material_payload["base_color"], "base_color", 0, 1, size=4),
            roughness=_number(material_payload["roughness"], "roughness", 0, 1),
        )
    return SceneObject(
        name=name,
        primitive=primitive,
        role=role,
        location=location,
        rotation_deg=rotation,
        scale=scale,
        bevel=bevel,
        smooth_shading=smooth,
        material=material,
        mesh=mesh,
    )


def _parse_mesh(payload: object) -> SceneMesh:
    if not isinstance(payload, dict) or set(payload) != {"vertices", "faces"}:
        raise WorldbuildingError("mesh must contain only vertices and faces")
    raw_vertices = payload["vertices"]
    raw_faces = payload["faces"]
    if not isinstance(raw_vertices, list) or not 3 <= len(raw_vertices) <= MAX_MESH_VERTICES:
        raise WorldbuildingError("mesh vertices must contain between 3 and 2000 points")
    if not isinstance(raw_faces, list) or not 1 <= len(raw_faces) <= MAX_MESH_FACES:
        raise WorldbuildingError("mesh faces must contain between 1 and 2000 polygons")
    vertices = tuple(_vector(v, "mesh vertex", -1000, 1000) for v in raw_vertices)
    faces: list[tuple[int, ...]] = []
    for face in raw_faces:
        if not isinstance(face, list) or not 3 <= len(face) <= 32:
            raise WorldbuildingError("each mesh face must reference 3 to 32 vertices")
        if any(isinstance(i, bool) or not isinstance(i, int) for i in face):
            raise WorldbuildingError("mesh face indices must be integers")
        if len(set(face)) != len(face) or any(i < 0 or i >= len(vertices) for i in face):
            raise WorldbuildingError("mesh face indices must be unique and in range")
        faces.append(tuple(face))
    return SceneMesh(vertices=vertices, faces=tuple(faces))


def _select_skill_names(brief: str) -> tuple[str, ...]:
    words = set(re.findall(r"[^\W_]+", brief.casefold(), flags=re.UNICODE))
    if words & _CHARACTER_SKILL_TERMS:
        return (*DEFAULT_WORLD_SKILLS, "character-modeling-animation")
    return DEFAULT_WORLD_SKILLS


def _required_scene_roles(brief: str) -> set[str]:
    """Map requested routes and building features to required semantic roles."""
    roles: set[str] = set()
    terms_by_role = {
        "path": (
            r"routes?",
            r"trails?",
            r"paths?",
            r"roads?",
            r"boardwalks?",
            r"footpaths?",
            r"senderos?",
            r"caminos?",
            r"pasarelas?",
            r"rutas?",
        ),
        "entry": (
            r"entr(?:y|ies|ance|ances)",
            r"doors?",
            r"doorways?",
            r"thresholds?",
            r"entradas?",
            r"accesos?",
        ),
        "courtyard": (r"courtyards?", r"patios?"),
        "interior": (
            r"interiors?",
            r"indoors?",
            r"inside",
            r"rooms?",
            r"habitaci[oó]n(?:es)?",
            r"cuartos?",
        ),
        "exterior": (r"exteriors?", r"outdoors?", r"outside", r"fachadas?"),
        "roof": (r"roofs?", r"rooftops?", r"tejados?", r"techos?", r"cubiertas?"),
        "furnishing": (r"furnishings?", r"furniture", r"muebles?"),
        "collectible": (
            r"collectibles?",
            r"pickups?",
            r"treasure(?:s)?",
            r"coins?",
            r"recogibles?",
            r"recolectables?",
            r"tesoros?",
            r"monedas?",
        ),
        "hazard": (
            r"hazards?",
            r"traps?",
            r"lava",
            r"lethal(?:\s+obstacles?)?",
            r"peligros?",
            r"trampas?",
        ),
    }
    for role, terms in terms_by_role.items():
        if _brief_contains(brief, *terms):
            roles.add(role)
    if "collectible" in roles:
        roles.add("path")
    is_building = _brief_contains(
        brief, r"houses?", r"homes?", r"buildings?", r"casas?", r"viviendas?"
    )
    interior_only_scope = _brief_contains(
        brief,
        r"interior\s+only",
        r"only\s+(?:the\s+)?interior",
        r"inside\s+only",
        r"solo\s+(?:el\s+)?interior",
        r"interior\s+solamente",
    )
    if is_building and not interior_only_scope:
        roles.update({"exterior", "entry", "roof"})
    return roles


def _brief_contains(brief: str, *terms: str) -> bool:
    pattern = r"(?<!\w)(?:" + "|".join(terms) + r")(?!\w)"
    return re.search(pattern, brief, re.IGNORECASE) is not None


def _validate_requested_world_roles(recipe: SceneRecipe, required_roles: set[str]) -> None:
    present_roles = {item.role for item in recipe.objects}
    missing_roles = required_roles - present_roles
    if missing_roles:
        raise WorldbuildingError(
            "recipe is missing requested semantic role(s): " + ", ".join(sorted(missing_roles))
        )
    paths = [item for item in recipe.objects if item.role == "path"]
    if len(paths) > 1:
        connected = largest_connected_component(
            [object_bounds(item) for item in paths], PATH_SEGMENT_MAX_GAP
        )
        if connected != len(paths):
            raise WorldbuildingError(
                f"recipe path segments are disconnected; connect all route pieces within "
                f"{PATH_SEGMENT_MAX_GAP:g} Blender units (largest connected group: {connected} "
                f"of {len(paths)})"
            )
    if "collectible" in required_roles and "path" in required_roles:
        collectible_paths = [item for item in recipe.objects if item.role == "collectible"]
        for collectible in collectible_paths:
            nearest = min(
                bounds_distance(object_bounds(collectible), object_bounds(path)) for path in paths
            )
            if nearest > COLLECTIBLE_ROUTE_MAX_GAP:
                raise WorldbuildingError(
                    f"collectible {collectible.name!r} is off the route by {nearest:.1f} Blender "
                    f"units; put every collectible within {COLLECTIBLE_ROUTE_MAX_GAP:g} units "
                    "of a path segment"
                )
    role_bounds = {
        role: [object_bounds(item) for item in recipe.objects if item.role == role]
        for pair in _ROLE_PROXIMITIES
        for role in pair[:2]
    }
    for first_role, second_role, max_gap in _ROLE_PROXIMITIES:
        if first_role not in required_roles or second_role not in required_roles:
            continue
        nearest = min(
            (
                bounds_distance(first, second)
                for first in role_bounds[first_role]
                for second in role_bounds[second_role]
            ),
            default=math.inf,
        )
        if nearest > max_gap:
            raise WorldbuildingError(
                f"recipe {first_role}/{second_role} roles are disconnected: nearest bounds "
                f"gap {nearest:.1f} Blender units; maximum {max_gap:g}"
            )


def _validate_recipe(recipe: SceneRecipe) -> None:
    if (
        isinstance(recipe.schema_version, bool)
        or recipe.schema_version not in SUPPORTED_RECIPE_VERSIONS
    ):
        raise WorldbuildingError("unsupported scene recipe version")
    if not isinstance(recipe.name, str) or not _NAME.fullmatch(recipe.name):
        raise WorldbuildingError("scene name is invalid")
    if len(recipe.objects) > MAX_SCENE_OBJECTS:
        raise WorldbuildingError("scene supports at most 512 scene objects")
    if len(recipe.lights) > MAX_SCENE_LIGHTS:
        raise WorldbuildingError("scene supports at most 16 lights")
    if len(recipe.characters) > MAX_SCENE_CHARACTERS:
        raise WorldbuildingError("scene supports at most 8 character blockouts")
    if not recipe.objects and not recipe.characters:
        raise WorldbuildingError("scene needs at least one object or character")
    if recipe.schema_version == 1 and recipe.characters:
        raise WorldbuildingError("character blockouts require scene recipe version 2")
    if not all(isinstance(item, SceneObject) for item in recipe.objects):
        raise WorldbuildingError("scene objects must be SceneObject values")
    if not all(isinstance(item, SceneLight) for item in recipe.lights):
        raise WorldbuildingError("scene lights must be SceneLight values")
    if not all(isinstance(item, SceneCharacter) for item in recipe.characters):
        raise WorldbuildingError("scene characters must be SceneCharacter values")
    if recipe.schema_version == 3:
        if not isinstance(recipe.environment, SceneEnvironment):
            raise WorldbuildingError("version 3 recipes require a SceneEnvironment")
        _parse_environment(_environment_mapping(recipe.environment))
    elif recipe.environment is not None:
        raise WorldbuildingError("environment settings require scene recipe version 3")
    for item in recipe.characters:
        _parse_character(_character_mapping(item))
    for item in recipe.objects:
        if recipe.schema_version == 1 and (
            item.primitive not in _PRIMITIVES or item.mesh is not None
        ):
            raise WorldbuildingError("version 1 objects must use a supported primitive")
        if recipe.schema_version >= 2 and ((item.primitive is None) == (item.mesh is None)):
            raise WorldbuildingError("version 2+ objects need exactly one primitive or mesh")
    names = (
        [item.name for item in recipe.objects]
        + [item.name for item in recipe.lights]
        + [item.name for item in recipe.characters]
    )
    if len(names) != len(set(names)):
        raise WorldbuildingError("scene object, light, and character names must be unique")


def _object_mapping(item: SceneObject) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": item.name,
        "role": item.role,
        "location": list(item.location),
        "rotation_deg": list(item.rotation_deg),
        "scale": list(item.scale),
    }
    if item.primitive is not None:
        result["primitive"] = item.primitive
    if item.mesh is not None:
        result["mesh"] = {
            "vertices": [list(vertex) for vertex in item.mesh.vertices],
            "faces": [list(face) for face in item.mesh.faces],
        }
    if item.bevel:
        result["bevel"] = item.bevel
    if item.smooth_shading:
        result["smooth_shading"] = item.smooth_shading
    if item.material is not None:
        result["material"] = {
            "base_color": list(item.material.base_color),
            "roughness": item.material.roughness,
        }
    return result


def _parse_light(payload: object) -> SceneLight:
    required = {"name", "type", "location", "rotation_deg", "color", "energy"}
    optional = {"distance", "spot_size_deg", "angle_deg"}
    if (
        not isinstance(payload, dict)
        or not required <= set(payload)
        or set(payload) - required - optional
    ):
        raise WorldbuildingError("scene light has unexpected or missing fields")
    name = payload["name"]
    light_type = payload["type"]
    if (
        not isinstance(name, str)
        or not _NAME.fullmatch(name)
        or not isinstance(light_type, str)
        or light_type not in _LIGHT_TYPES
    ):
        raise WorldbuildingError("scene light name or type is invalid")
    return SceneLight(
        name=name,
        type=light_type,
        location=_vector(payload["location"], "light location", -10_000, 10_000),
        rotation_deg=_vector(payload["rotation_deg"], "light rotation", -36_000, 36_000),
        color=_vector(payload["color"], "light color", 0, 1),
        energy=_number(payload["energy"], "light energy", 0, 100_000),
        distance=(
            _number(payload["distance"], "light distance", 0.001, 10_000, True)
            if "distance" in payload
            else None
        ),
        spot_size_deg=(
            _number(payload["spot_size_deg"], "spot size", 1, 180)
            if "spot_size_deg" in payload
            else None
        ),
        angle_deg=(
            _number(payload["angle_deg"], "sun angle", 0.01, 45, True)
            if "angle_deg" in payload
            else None
        ),
    )


def _parse_character(payload: object) -> SceneCharacter:
    if not isinstance(payload, dict) or set(payload) != {"name", "motion", "location", "scale"}:
        raise WorldbuildingError("scene character has unexpected or missing fields")
    name = payload["name"]
    motion = payload["motion"]
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise WorldbuildingError("scene character name is invalid")
    if not isinstance(motion, str) or motion not in {"WALK", "RUN", "JUMP", "IDLE"}:
        raise WorldbuildingError("scene character motion must be WALK, RUN, JUMP, or IDLE")
    return SceneCharacter(
        name=name,
        motion=motion,
        location=_vector(payload["location"], "character location", -10_000, 10_000),
        scale=_vector(payload["scale"], "character scale", 0.25, 4),
    )


def _character_mapping(character: SceneCharacter) -> dict[str, Any]:
    return {
        "name": character.name,
        "motion": character.motion,
        "location": list(character.location),
        "scale": list(character.scale),
    }


def _parse_environment(payload: object) -> SceneEnvironment:
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
        not isinstance(payload, dict)
        or not required <= set(payload)
        or set(payload) - required - {"clouds"}
    ):
        raise WorldbuildingError("environment has unexpected or missing fields")
    if not isinstance(payload["global_shadows"], bool):
        raise WorldbuildingError("global_shadows must be boolean")
    atmosphere_payload = payload["atmosphere"]
    atmosphere_fields = {"color", "decay", "density", "glare", "haze", "offset"}
    if not isinstance(atmosphere_payload, dict) or set(atmosphere_payload) != atmosphere_fields:
        raise WorldbuildingError("atmosphere has unexpected or missing fields")
    atmosphere = SceneAtmosphere(
        color=_vector(atmosphere_payload["color"], "atmosphere color", 0, 1),
        decay=_vector(atmosphere_payload["decay"], "atmosphere decay", 0, 1),
        density=_number(atmosphere_payload["density"], "atmosphere density", 0, 1),
        glare=_number(atmosphere_payload["glare"], "atmosphere glare", 0, 10),
        haze=_number(atmosphere_payload["haze"], "atmosphere haze", 0, 10),
        offset=_number(atmosphere_payload["offset"], "atmosphere offset", 0, 1),
    )
    clouds = None
    if "clouds" in payload:
        clouds_payload = payload["clouds"]
        if not isinstance(clouds_payload, dict) or set(clouds_payload) != {
            "color",
            "cover",
            "density",
            "enabled",
        }:
            raise WorldbuildingError("clouds have unexpected or missing fields")
        if not isinstance(clouds_payload["enabled"], bool):
            raise WorldbuildingError("clouds enabled must be boolean")
        clouds = SceneClouds(
            color=_vector(clouds_payload["color"], "cloud color", 0, 1),
            cover=_number(clouds_payload["cover"], "cloud cover", 0, 1),
            density=_number(clouds_payload["density"], "cloud density", 0, 1),
            enabled=clouds_payload["enabled"],
        )
    return SceneEnvironment(
        ambient_color=_vector(payload["ambient_color"], "ambient color", 0, 1),
        outdoor_ambient_color=_vector(
            payload["outdoor_ambient_color"], "outdoor ambient color", 0, 1
        ),
        brightness=_number(payload["brightness"], "brightness", 0, 10),
        clock_time=_number(payload["clock_time"], "clock time", 0, 24),
        exposure_compensation=_number(
            payload["exposure_compensation"], "exposure compensation", -5, 5
        ),
        global_shadows=payload["global_shadows"],
        shadow_softness=_number(payload["shadow_softness"], "shadow softness", 0, 1),
        atmosphere=atmosphere,
        clouds=clouds,
    )


def _environment_mapping(item: SceneEnvironment) -> dict[str, Any]:
    atmosphere = item.atmosphere
    result: dict[str, Any] = {
        "ambient_color": list(item.ambient_color),
        "outdoor_ambient_color": list(item.outdoor_ambient_color),
        "brightness": item.brightness,
        "clock_time": item.clock_time,
        "exposure_compensation": item.exposure_compensation,
        "global_shadows": item.global_shadows,
        "shadow_softness": item.shadow_softness,
        "atmosphere": {
            "color": list(atmosphere.color),
            "decay": list(atmosphere.decay),
            "density": atmosphere.density,
            "glare": atmosphere.glare,
            "haze": atmosphere.haze,
            "offset": atmosphere.offset,
        },
    }
    if item.clouds is not None:
        result["clouds"] = {
            "color": list(item.clouds.color),
            "cover": item.clouds.cover,
            "density": item.clouds.density,
            "enabled": item.clouds.enabled,
        }
    return result


def _light_mapping(light: SceneLight) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": light.name,
        "type": light.type,
        "location": list(light.location),
        "rotation_deg": list(light.rotation_deg),
        "color": list(light.color),
        "energy": light.energy,
    }
    if light.distance is not None:
        result["distance"] = light.distance
    if light.spot_size_deg is not None:
        result["spot_size_deg"] = light.spot_size_deg
    if light.angle_deg is not None:
        result["angle_deg"] = light.angle_deg
    return result


def _vector(
    value: object,
    label: str,
    low: float,
    high: float,
    *,
    size: int = 3,
    minimum_exclusive: bool = False,
) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != size:
        raise WorldbuildingError(f"{label} must contain exactly {size} numbers")
    return tuple(_number(item, label, low, high, minimum_exclusive) for item in value)


def _number(value: object, label: str, low: float, high: float, exclusive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise WorldbuildingError(f"{label} must contain finite numbers")
    if not (low <= value <= high) or (exclusive and value == low):
        raise WorldbuildingError(f"{label} is outside the supported range")
    return float(value)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WorldbuildingError("scene recipe contains duplicate JSON keys")
        result[key] = value
    return result


def _reject_non_finite(value: str) -> None:
    raise WorldbuildingError(f"scene recipe contains invalid number {value}")
