"""Fixed, structural evaluations for skill-guided world design generation.

These checks measure recipe validity and requested structural coverage. They do
not claim to judge visual quality, playability in Studio, or asset production
readiness; those require human review and runtime inspection.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .spatial import (
    PATH_SEGMENT_MAX_GAP,
    bounds_distance,
    largest_connected_component,
    object_bounds,
)
from .worldbuilding import SceneObject, WorldBuildResult


@dataclass(frozen=True, slots=True)
class WorldEvaluationCase:
    case_id: str
    brief: str
    required_skills: tuple[str, ...]
    required_roles: tuple[str, ...]
    minimum_objects: int
    minimum_lights: int
    required_role_counts: tuple[tuple[str, int], ...] = ()
    required_character_motions: tuple[str, ...] = ()
    required_light_types: tuple[str, ...] = ()
    required_lights_near_roles: tuple[tuple[str, str, float], ...] = ()
    required_role_proximities: tuple[tuple[str, str, float], ...] = ()
    minimum_path_aspect_ratio: float | None = None
    minimum_connected_path_segments: int = 1
    path_segment_max_gap: float = PATH_SEGMENT_MAX_GAP


@dataclass(frozen=True, slots=True)
class EvaluationCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class WorldEvaluationResult:
    case_id: str
    passed: bool
    checks: tuple[EvaluationCheck, ...]
    recipe: dict


WORLD_EVALUATION_CASES = (
    WorldEvaluationCase(
        case_id="rainforest-checkpoint-obby",
        brief=(
            "Design a low-poly rainforest Obby checkpoint course with a scenic start, "
            "three ordered connected traversal segments, a rising canopy bridge, and a "
            "summit landmark. Add one clearly marked lethal touch hazard on the course. "
            "Keep the route wide, clear, and readable."
        ),
        required_skills=("world-environments", "blender-scene-authoring"),
        required_roles=("terrain", "path", "vegetation", "landmark", "hazard"),
        minimum_objects=15,
        minimum_lights=1,
        required_light_types=("SUN",),
        minimum_path_aspect_ratio=2.0,
        minimum_connected_path_segments=3,
        path_segment_max_gap=1.0,
    ),
    WorldEvaluationCase(
        case_id="rainforest-trail",
        brief=(
            "Build a playable temperate rainforest trail with a clear route, a landmark "
            "lookout, varied terrain, and layered vegetation."
        ),
        required_skills=("world-environments", "blender-scene-authoring"),
        required_roles=("terrain", "path", "vegetation", "landmark"),
        minimum_objects=8,
        minimum_lights=1,
        required_light_types=("SUN",),
        minimum_path_aspect_ratio=2.0,
    ),
    WorldEvaluationCase(
        case_id="rainforest-collect-and-win",
        brief=(
            "Build a rainforest collect-and-win game with at least three canopy coins "
            "distributed along a connected path, one lethal hazard beside the route, and "
            "a summit landmark at the finish. Make the route clear and continuous."
        ),
        required_skills=("world-environments", "blender-scene-authoring"),
        required_roles=("terrain", "path", "vegetation", "collectible", "hazard", "landmark"),
        minimum_objects=19,
        minimum_lights=1,
        required_role_counts=(("path", 3), ("collectible", 3), ("hazard", 1), ("landmark", 1)),
        required_light_types=("SUN",),
        required_role_proximities=(
            ("path", "collectible", 2.0),
            ("path", "hazard", 4.0),
            ("path", "landmark", 6.0),
        ),
        minimum_path_aspect_ratio=2.0,
        minimum_connected_path_segments=3,
        path_segment_max_gap=1.0,
    ),
    WorldEvaluationCase(
        case_id="desert-courtyard-home",
        brief=(
            "Create a desert courtyard home blockout with an entry, shaded public "
            "courtyard, readable interior room, a legible doorway opening, furnishings, "
            "and climate-aware roof."
        ),
        required_skills=("world-environments", "blender-scene-authoring"),
        required_roles=(
            "exterior",
            "entry",
            "courtyard",
            "interior",
            "opening",
            "roof",
            "furnishing",
        ),
        minimum_objects=10,
        minimum_lights=2,
        required_light_types=("SUN", "AREA"),
        required_lights_near_roles=(("AREA", "interior", 6.0),),
        required_role_proximities=(
            ("entry", "courtyard", 8.0),
            ("courtyard", "interior", 10.0),
            ("entry", "opening", 8.0),
            ("opening", "interior", 8.0),
            ("roof", "courtyard", 12.0),
        ),
    ),
    WorldEvaluationCase(
        case_id="coastal-wetland",
        brief=(
            "Design a navigable coastal wetland map with tide pools, a raised footpath, "
            "shore rocks, reeds, and one memorable route landmark."
        ),
        required_skills=("world-environments", "blender-scene-authoring"),
        required_roles=("terrain", "path", "water", "rock", "vegetation", "landmark"),
        minimum_objects=8,
        minimum_lights=1,
        required_light_types=("SUN",),
        minimum_path_aspect_ratio=2.0,
    ),
    WorldEvaluationCase(
        case_id="alpine-inn",
        brief=(
            "Build a snowy alpine approach to a timber inn with a readable trail made from at "
            "least three connected segments, a sheltered entry, a distinct warm interior, roof "
            "overhangs, conifers, and a mountain landmark."
        ),
        required_skills=("world-environments", "blender-scene-authoring"),
        required_roles=(
            "terrain",
            "path",
            "exterior",
            "entry",
            "interior",
            "opening",
            "roof",
            "furnishing",
            "vegetation",
            "rock",
            "landmark",
        ),
        minimum_objects=13,
        minimum_lights=2,
        required_light_types=("SUN", "AREA"),
        required_lights_near_roles=(("AREA", "interior", 6.0),),
        required_role_proximities=(
            ("path", "entry", 5.0),
            ("entry", "interior", 5.0),
            ("opening", "interior", 4.0),
            ("roof", "interior", 6.0),
        ),
        minimum_path_aspect_ratio=2.0,
        minimum_connected_path_segments=3,
    ),
    WorldEvaluationCase(
        case_id="mangrove-stilt-house",
        brief=(
            "Design a tropical mangrove shoreline with tidal water, a raised boardwalk, a stilt "
            "house whose entry connects to a separate furnished interior, mangrove vegetation, "
            "and an unmistakable canopy landmark."
        ),
        required_skills=("world-environments", "blender-scene-authoring"),
        required_roles=(
            "terrain",
            "water",
            "path",
            "exterior",
            "entry",
            "interior",
            "opening",
            "roof",
            "furnishing",
            "vegetation",
            "landmark",
        ),
        minimum_objects=13,
        minimum_lights=2,
        required_light_types=("SUN", "POINT"),
        required_lights_near_roles=(("POINT", "interior", 6.0),),
        required_role_proximities=(
            ("path", "entry", 5.0),
            ("entry", "opening", 4.0),
            ("opening", "interior", 5.0),
            ("roof", "interior", 7.0),
        ),
        minimum_path_aspect_ratio=2.0,
    ),
    WorldEvaluationCase(
        case_id="guard-walk-cycle",
        brief=(
            "Crea un guardia NPC con anatomía estilizada y un esqueleto genérico para un "
            "puesto costero. Genera blockouts separados para los ciclos de caminar y correr, "
            "y para una acción de salto con anticipación, fase aérea y aterrizaje."
        ),
        required_skills=(
            "world-environments",
            "blender-scene-authoring",
            "character-modeling-animation",
        ),
        required_roles=(),
        minimum_objects=0,
        minimum_lights=0,
        required_character_motions=("WALK", "RUN", "JUMP"),
    ),
)


def assess_world_result(
    case: WorldEvaluationCase, result: WorldBuildResult
) -> WorldEvaluationResult:
    """Assess a parsed generation against a fixed, reviewable structural rubric."""
    recipe = result.recipe
    role_names = {item.role for item in recipe.objects}
    role_counts = {
        role: sum(item.role == role for item in recipe.objects)
        for role, _minimum in case.required_role_counts
    }
    present_motions = {item.motion for item in recipe.characters}
    present_light_types = {item.type for item in recipe.lights}
    environment = recipe.environment
    missing_light_coverage = []
    missing_role_counts = [
        f"{role} ({role_counts[role]}; minimum {minimum})"
        for role, minimum in case.required_role_counts
        if role_counts[role] < minimum
    ]
    for light_type, role, max_distance in case.required_lights_near_roles:
        targets = [item for item in recipe.objects if item.role == role]
        nearby = any(
            light.type == light_type
            and any(
                math.dist(light.location, target.location) <= max_distance for target in targets
            )
            for light in recipe.lights
        )
        if not nearby:
            missing_light_coverage.append(f"{light_type} near {role} (within {max_distance:g})")
    role_bounds = {
        role: [(object_bounds(item), item) for item in recipe.objects if item.role == role]
        for first_role, second_role, _ in case.required_role_proximities
        for role in (first_role, second_role)
    }
    distant_role_pairs = []
    for first_role, second_role, max_distance in case.required_role_proximities:
        first_items = role_bounds[first_role]
        second_items = role_bounds[second_role]
        closest = min(
            (
                bounds_distance(first_bounds, second_bounds)
                for first_bounds, _first in first_items
                for second_bounds, _second in second_items
            ),
            default=math.inf,
        )
        if closest > max_distance:
            distant_role_pairs.append(
                f"{first_role}/{second_role} ({closest:.1f}; max {max_distance:g})"
            )
    elongated_path = any(
        item.role == "path"
        and _horizontal_aspect_ratio(item) >= (case.minimum_path_aspect_ratio or 0)
        for item in recipe.objects
    )
    path_objects = [item for item in recipe.objects if item.role == "path"]
    largest_path_component = largest_connected_component(
        [object_bounds(item) for item in path_objects], case.path_segment_max_gap
    )
    connected_path = (
        case.minimum_path_aspect_ratio is None
        or largest_path_component >= case.minimum_connected_path_segments
    )
    checks = (
        EvaluationCheck(
            "required_skills",
            set(case.required_skills) <= set(result.skill_names),
            "required skill packs were selected"
            if set(case.required_skills) <= set(result.skill_names)
            else "one or more required skill packs were not selected",
        ),
        EvaluationCheck(
            "required_roles",
            set(case.required_roles) <= role_names,
            "all requested scene roles are present"
            if set(case.required_roles) <= role_names
            else "missing roles: " + ", ".join(sorted(set(case.required_roles) - role_names)),
        ),
        EvaluationCheck(
            "minimum_role_counts",
            not missing_role_counts,
            "all role-specific minimum counts are met"
            if not missing_role_counts
            else "below minimum: " + ", ".join(missing_role_counts),
        ),
        EvaluationCheck(
            "minimum_objects",
            len(recipe.objects) >= case.minimum_objects,
            f"{len(recipe.objects)} scene objects; minimum {case.minimum_objects}",
        ),
        EvaluationCheck(
            "minimum_lights",
            len(recipe.lights) >= case.minimum_lights,
            f"{len(recipe.lights)} lights; minimum {case.minimum_lights}",
        ),
        EvaluationCheck(
            "global_environment",
            environment is not None,
            "global lighting and atmospheric settings are present"
            if environment is not None
            else "missing version 3 global environment settings",
        ),
        EvaluationCheck(
            "required_light_types",
            set(case.required_light_types) <= present_light_types,
            "all requested light types are present"
            if set(case.required_light_types) <= present_light_types
            else "missing light types: "
            + ", ".join(sorted(set(case.required_light_types) - present_light_types)),
        ),
        EvaluationCheck(
            "required_lights_near_roles",
            not missing_light_coverage,
            "required lighting reaches its scene roles"
            if not missing_light_coverage
            else "missing: " + ", ".join(missing_light_coverage),
        ),
        EvaluationCheck(
            "required_role_proximities",
            not distant_role_pairs,
            "required spaces are arranged near their transitions"
            if not distant_role_pairs
            else "spatially disconnected: " + ", ".join(distant_role_pairs),
        ),
        EvaluationCheck(
            "playable_path_shape",
            case.minimum_path_aspect_ratio is None or elongated_path,
            "a route feature has a readable elongated footprint"
            if elongated_path
            else (
                "no route aspect-ratio requirement for this case"
                if case.minimum_path_aspect_ratio is None
                else (
                    f"no path object reaches a {case.minimum_path_aspect_ratio:g}:1 "
                    "horizontal aspect ratio"
                )
            ),
        ),
        EvaluationCheck(
            "connected_path_segments",
            connected_path,
            (
                f"largest connected route has {largest_path_component} segments; "
                f"minimum {case.minimum_connected_path_segments}"
                if case.minimum_path_aspect_ratio is not None
                else "no connected route segment count required for this case"
            ),
        ),
        EvaluationCheck(
            "character_motions",
            set(case.required_character_motions) <= present_motions,
            "all requested motion presets are present"
            if set(case.required_character_motions) <= present_motions
            else "missing motions: "
            + ", ".join(sorted(set(case.required_character_motions) - present_motions)),
        ),
    )
    return WorldEvaluationResult(
        case_id=case.case_id,
        passed=all(check.passed for check in checks),
        checks=checks,
        recipe=recipe.to_mapping(),
    )


def _horizontal_aspect_ratio(item: SceneObject) -> float:
    """Return the path's longest-to-shortest horizontal dimensions."""
    if item.mesh is not None:
        local_dimensions = tuple(
            max(vertex[axis] for vertex in item.mesh.vertices)
            - min(vertex[axis] for vertex in item.mesh.vertices)
            for axis in range(3)
        )
        horizontal = [local_dimensions[axis] * item.scale[axis] for axis in (0, 1)]
    else:
        horizontal = [item.scale[0], item.scale[1]]
    shorter = min(horizontal)
    return max(horizontal) / shorter if shorter > 0 else 0.0
