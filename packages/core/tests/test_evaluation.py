import json
import os
import subprocess
import sys
from pathlib import Path

from core.evaluation import WORLD_EVALUATION_CASES, assess_world_result
from core.worldbuilding import SceneRecipe, WorldBuildResult, _select_skill_names


def _result(
    case_id: str,
    *,
    omit_role: str | None = None,
    omit_motion: bool = False,
    omit_silhouette: str | None = None,
):
    case = next(case for case in WORLD_EVALUATION_CASES if case.case_id == case_id)
    roles = []
    for role in case.required_roles:
        if role == omit_role:
            continue
        count = max(
            case.minimum_connected_path_segments if role == "path" else 1,
            dict(case.required_role_counts).get(role, 1),
        )
        roles.extend([role] * count)
    roles.extend("prop" for _ in range(max(0, case.minimum_objects - len(roles))))
    entry_index = roles.index("entry") if "entry" in roles else 0
    segment_count = sum(role == "path" for role in roles)
    path_centers = [-(segment_count - index - 0.5) * 8 for index in range(segment_count)]
    path_index = 0
    role_occurrences: dict[str, int] = {}
    objects = []
    for index, role in enumerate(roles):
        location = [index * 2, 0, 0]
        if case_id == "volcanic-cave-crossing":
            location = {
                "exterior": [0, 0, 0],
                "entry": [2, 0, 0],
                "opening": [4, 0, 0],
                "interior": [6, 0, 0],
                "landmark": [8, 0, 0],
            }.get(role, location)
        if role == "path":
            location = [entry_index * 2, path_centers[path_index], 0]
            path_index += 1
        elif role == "collectible" and case_id == "rainforest-collect-and-win":
            location = [0, path_centers[role_occurrences.get(role, 0) % segment_count], 0.5]
        elif role == "hazard" and case_id == "rainforest-collect-and-win":
            location = [0.5, path_centers[len(path_centers) // 2], 0.5]
        elif role == "landmark" and case_id == "rainforest-collect-and-win":
            location = [0, path_centers[-1] + 4, 0.5]
        role_occurrences[role] = role_occurrences.get(role, 0) + 1
        objects.append(
            {
                "name": f"Object {index}",
                "primitive": "cube",
                "role": role,
                "location": location,
                "rotation_deg": [0, 0, 0],
                "scale": [1, 4, 0.2] if role == "path" else [1, 1, 1],
            }
        )
    light_types = list(case.required_light_types)
    light_types.extend("SUN" for _ in range(max(0, case.minimum_lights - len(light_types))))
    lights = []
    for index, light_type in enumerate(light_types):
        location = [0, 0, 8]
        for required_type, role, _max_distance in case.required_lights_near_roles:
            if light_type == required_type:
                target = next((item for item in objects if item["role"] == role), None)
                if target is not None:
                    location = list(target["location"])
                    location[2] += 2
                break
        lights.append(
            {
                "name": f"Light {index}",
                "type": light_type,
                "location": location,
                "rotation_deg": [25, 0, 0],
                "color": [1, 1, 1],
                "energy": 1,
            }
        )
    characters = (
        []
        if omit_motion
        else [
            {
                "name": f"Character {index}",
                "motion": motion,
                **(
                    {"silhouette": case.required_character_silhouettes[index]}
                    if index < len(case.required_character_silhouettes)
                    and case.required_character_silhouettes[index] != omit_silhouette
                    else {}
                ),
                "location": [index * 4, 0, 0],
                "scale": [1, 1, 1],
            }
            for index, motion in enumerate(case.required_character_motions)
        ]
    )
    if not objects and not characters:
        objects.append(
            {
                "name": "Anchor",
                "primitive": "cube",
                "role": "prop",
                "location": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [1, 1, 1],
            }
        )
    recipe = SceneRecipe.from_mapping(
        {
            "schema_version": 3,
            "name": "Evaluation Result",
            "units": "blender_units",
            "up_axis": "Z",
            "objects": objects,
            "lights": lights,
            "characters": characters,
            "environment": {
                "ambient_color": [0.15, 0.18, 0.22],
                "outdoor_ambient_color": [0.4, 0.48, 0.56],
                "brightness": 2,
                "clock_time": 13,
                "exposure_compensation": 0,
                "global_shadows": True,
                "shadow_softness": 0.2,
                "atmosphere": {
                    "color": [0.75, 0.83, 0.92],
                    "decay": [0.35, 0.45, 0.58],
                    "density": 0.15,
                    "glare": 0,
                    "haze": 0.4,
                    "offset": 0.2,
                },
            },
        }
    )
    return case, WorldBuildResult(recipe, 1, (), case.required_skills)


def test_fixed_world_design_cases_cover_environment_architecture_and_motion():
    assert {case.case_id for case in WORLD_EVALUATION_CASES} == {
        "rainforest-checkpoint-obby",
        "rainforest-trail",
        "rainforest-collect-and-win",
        "desert-courtyard-home",
        "coastal-wetland",
        "alpine-inn",
        "mangrove-stilt-house",
        "volcanic-cave-crossing",
        "guard-walk-cycle",
    }
    assert all(
        assess_world_result(*_result(case.case_id)).passed for case in WORLD_EVALUATION_CASES
    )
    assert all(
        next(
            check
            for check in assess_world_result(*_result(case.case_id)).checks
            if check.name == "global_environment"
        ).passed
        for case in WORLD_EVALUATION_CASES
    )
    assert all(
        _select_skill_names(case.brief) == case.required_skills for case in WORLD_EVALUATION_CASES
    )


def test_offline_evaluation_cli_passes_all_cases_with_reviewed_fixtures(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    environment = os.environ.copy()
    environment["LLM_PROVIDER"] = "fake"
    environment["AGENT_MAX_USD_PER_SESSION"] = "0"
    monkeypatch.setenv("LLM_PROVIDER", "fake")
    result = subprocess.run(  # noqa: S603 - fixed trusted repository script and arguments
        [sys.executable, str(root / "tools/evaluate_worldbuilding.py")],
        cwd=root,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    report = json.loads(result.stdout)
    assert report["evaluation_mode"] == "reviewed_fixture_generation"
    assert report["passed"] == len(WORLD_EVALUATION_CASES)
    assert report["failed"] == 0
    assert report["spent_usd"] == "0"
    assert "does not assess visual quality" in report["scope"]


def test_evaluation_fails_when_requested_role_is_missing():
    case, result = _result("coastal-wetland", omit_role="path")

    assessed = assess_world_result(case, result)

    assert not assessed.passed
    role_check = next(check for check in assessed.checks if check.name == "required_roles")
    assert not role_check.passed
    assert "path" in role_check.detail


def test_lava_obby_evaluation_requires_hazard_role():
    case, result = _result("rainforest-checkpoint-obby", omit_role="hazard")

    assessed = assess_world_result(case, result)

    assert not assessed.passed
    role_check = next(check for check in assessed.checks if check.name == "required_roles")
    assert not role_check.passed
    assert "hazard" in role_check.detail


def test_collect_and_win_evaluation_requires_three_collectibles():
    case, result = _result("rainforest-collect-and-win")
    mapping = result.recipe.to_mapping()
    collectibles = [item for item in mapping["objects"] if item["role"] == "collectible"]
    mapping["objects"].remove(collectibles[-1])
    two_coin_result = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, two_coin_result)

    assert not assessed.passed
    count_check = next(check for check in assessed.checks if check.name == "minimum_role_counts")
    assert not count_check.passed
    assert "collectible (2; minimum 3)" in count_check.detail


def test_collect_and_win_evaluation_rejects_hazard_detached_from_route():
    case, result = _result("rainforest-collect-and-win")
    mapping = result.recipe.to_mapping()
    hazard = next(item for item in mapping["objects"] if item["role"] == "hazard")
    hazard["location"][0] += 100
    detached_hazard = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, detached_hazard)

    assert not assessed.passed
    proximity = next(
        check for check in assessed.checks if check.name == "required_role_proximities"
    )
    assert not proximity.passed
    assert "path/hazard" in proximity.detail


def test_collect_and_win_evaluation_rejects_individual_collectible_detached_from_route():
    case, result = _result("rainforest-collect-and-win")
    mapping = result.recipe.to_mapping()
    collectibles = [item for item in mapping["objects"] if item["role"] == "collectible"]
    collectibles[-1]["location"][0] += 100
    detached_collectible = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, detached_collectible)

    assert not assessed.passed
    pair_proximity = next(
        check for check in assessed.checks if check.name == "required_role_proximities"
    )
    assert pair_proximity.passed
    coverage = next(check for check in assessed.checks if check.name == "required_role_coverage")
    assert not coverage.passed
    assert "Object" in coverage.detail and "collectible" in coverage.detail


def test_collect_and_win_evaluation_requires_coins_on_distinct_route_segments():
    case, result = _result("rainforest-collect-and-win")
    mapping = result.recipe.to_mapping()
    paths = [item for item in mapping["objects"] if item["role"] == "path"]
    collectibles = [item for item in mapping["objects"] if item["role"] == "collectible"]
    for collectible in collectibles:
        collectible["location"] = [*paths[0]["location"]]
    clustered_collectibles = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, clustered_collectibles)

    assert not assessed.passed
    coverage = next(check for check in assessed.checks if check.name == "required_role_coverage")
    assert coverage.passed
    distribution = next(
        check for check in assessed.checks if check.name == "required_role_distribution"
    )
    assert not distribution.passed
    assert "1 distinct targets; minimum 3" in distribution.detail


def test_collect_and_win_distribution_finds_optimal_assignment_when_nearest_is_shared():
    case, result = _result("rainforest-collect-and-win")
    mapping = result.recipe.to_mapping()
    paths = [item for item in mapping["objects"] if item["role"] == "path"]
    collectibles = [item for item in mapping["objects"] if item["role"] == "collectible"]
    for index, path in enumerate(paths):
        path["location"] = [index * 2.0, 0, 0]
        path["scale"] = [2.0, 0.2, 0.2]
    for collectible, x in zip(collectibles, (0.4, -2.5, 4.0), strict=True):
        collectible["location"] = [x, 0, 0]
        collectible["scale"] = [0.1, 0.1, 0.1]
    overlapping_neighborhoods = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, overlapping_neighborhoods)

    distribution = next(
        check for check in assessed.checks if check.name == "required_role_distribution"
    )
    assert distribution.passed


def test_alpine_path_evaluation_requires_multiple_connected_segments():
    case, result = _result("alpine-inn")
    mapping = result.recipe.to_mapping()
    paths = [item for item in mapping["objects"] if item["role"] == "path"]
    paths[-1]["location"][0] += 100
    disconnected = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, disconnected)

    assert not assessed.passed
    route_check = next(
        check for check in assessed.checks if check.name == "connected_path_segments"
    )
    assert not route_check.passed
    assert "2 segments; minimum 3" in route_check.detail


def test_obby_evaluation_requires_consecutive_segments_to_connect_in_recipe_order():
    case, result = _result("rainforest-checkpoint-obby")
    mapping = result.recipe.to_mapping()
    paths = [item for item in mapping["objects"] if item["role"] == "path"]
    paths[1]["location"], paths[2]["location"] = paths[2]["location"], paths[1]["location"]
    reordered_route = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, reordered_route)

    assert not assessed.passed
    connected = next(check for check in assessed.checks if check.name == "connected_path_segments")
    assert connected.passed
    ordered = next(check for check in assessed.checks if check.name == "ordered_route_sequence")
    assert not ordered.passed
    assert "Object" in ordered.detail


def test_navigable_map_evaluation_rejects_a_path_without_an_elongated_footprint():
    case, result = _result("coastal-wetland")
    mapping = result.recipe.to_mapping()
    path = next(item for item in mapping["objects"] if item["role"] == "path")
    path["scale"] = [1.8, 1, 0.2]
    too_wide = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, too_wide)

    assert not assessed.passed
    path_check = next(check for check in assessed.checks if check.name == "playable_path_shape")
    assert not path_check.passed
    assert "2:1" in path_check.detail


def test_desert_home_evaluation_requires_distinct_interior_exterior_house_roles():
    case, result = _result("desert-courtyard-home", omit_role="interior")

    assessed = assess_world_result(case, result)

    assert not assessed.passed
    role_check = next(check for check in assessed.checks if check.name == "required_roles")
    assert not role_check.passed
    assert "interior" in role_check.detail


def test_desert_home_evaluation_allows_an_interior_room_inside_exterior_massing():
    case, result = _result("desert-courtyard-home")
    mapping = result.recipe.to_mapping()
    exterior = next(item for item in mapping["objects"] if item["role"] == "exterior")
    interior = next(item for item in mapping["objects"] if item["role"] == "interior")
    interior["location"] = exterior["location"]
    interior_light = next(light for light in mapping["lights"] if light["type"] == "AREA")
    interior_light["location"] = [*interior["location"][:2], interior["location"][2] + 2]
    overlapping_spaces = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, overlapping_spaces)

    assert assessed.passed, assessed.checks


def test_desert_home_evaluation_rejects_a_spatially_detached_interior():
    case, result = _result("desert-courtyard-home")
    mapping = result.recipe.to_mapping()
    for item in mapping["objects"]:
        if item["role"] == "interior":
            item["location"][0] += 100
    detached_room = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, detached_room)

    assert not assessed.passed
    proximity = next(
        check for check in assessed.checks if check.name == "required_role_proximities"
    )
    assert not proximity.passed
    assert "courtyard/interior" in proximity.detail


def test_desert_home_evaluation_uses_object_volume_for_space_proximity():
    case, result = _result("desert-courtyard-home")
    mapping = result.recipe.to_mapping()
    courtyard = next(item for item in mapping["objects"] if item["role"] == "courtyard")
    courtyard["location"][0] = 10
    broad_courtyard = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, broad_courtyard)

    assert assessed.passed, assessed.checks


def test_desert_courtyard_example_passes_its_structural_evaluation():
    root = Path(__file__).resolve().parents[3]
    mapping = json.loads(
        (root / "examples/worlds/desert-courtyard-home-v3/scene-recipe.json").read_text(
            encoding="utf-8"
        )
    )
    case = next(case for case in WORLD_EVALUATION_CASES if case.case_id == "desert-courtyard-home")
    result = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        iterations=1,
        responses=(),
        skill_names=case.required_skills,
    )

    assessed = assess_world_result(case, result)

    assert assessed.passed, assessed.checks


def test_desert_home_evaluation_requires_separate_exterior_and_interior_lighting():
    case, result = _result("desert-courtyard-home")
    mapping = result.recipe.to_mapping()
    mapping["lights"] = [light for light in mapping["lights"] if light["type"] != "AREA"]
    unlit_interior = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, unlit_interior)

    assert not assessed.passed
    type_check = next(check for check in assessed.checks if check.name == "required_light_types")
    assert not type_check.passed
    assert "AREA" in type_check.detail


def test_desert_home_requires_area_light_near_the_interior():
    case, result = _result("desert-courtyard-home")
    mapping = result.recipe.to_mapping()
    area_light = next(light for light in mapping["lights"] if light["type"] == "AREA")
    area_light["location"] = [100, 100, 100]
    unlit_interior = WorldBuildResult(
        SceneRecipe.from_mapping(mapping),
        result.iterations,
        result.responses,
        result.skill_names,
    )

    assessed = assess_world_result(case, unlit_interior)

    assert not assessed.passed
    coverage_check = next(
        check for check in assessed.checks if check.name == "required_lights_near_roles"
    )
    assert not coverage_check.passed
    assert "interior" in coverage_check.detail


def test_evaluation_fails_when_requested_character_motion_is_missing():
    case, result = _result("guard-walk-cycle", omit_motion=True)

    assessed = assess_world_result(case, result)

    assert not assessed.passed
    motion_check = next(check for check in assessed.checks if check.name == "character_motions")
    assert not motion_check.passed
    assert "WALK" in motion_check.detail


def test_evaluation_requires_requested_character_silhouette_presets():
    case, result = _result("guard-walk-cycle", omit_silhouette="slender")

    assessed = assess_world_result(case, result)

    assert not assessed.passed
    silhouette_check = next(
        check for check in assessed.checks if check.name == "character_silhouettes"
    )
    assert not silhouette_check.passed
    assert "slender" in silhouette_check.detail
