import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from core.gameplay_templates import (
    GameplayTemplateError,
    obby_course_source,
    rule_game_source,
    treasure_hunt_source,
    validate_gameplay_mode,
)
from core.roblox_place import (
    RobloxPlaceBuildError,
    _validate_imported_model_tree,
    scene_recipe_collision_payload,
    scene_recipe_to_rojo_project,
)
from core.worldbuilding import SceneRecipe


def _recipe():
    return {
        "schema_version": 3,
        "name": "Mangrove Shore",
        "units": "blender_units",
        "up_axis": "Z",
        "objects": [
            {
                "name": "Stilt House",
                "role": "architecture",
                "primitive": "cube",
                "location": [2, 3, 4],
                "rotation_deg": [0, 0, 90],
                "scale": [2, 1, 0.5],
            },
            {
                "name": "Mangrove Crown",
                "role": "vegetation",
                "primitive": "uv_sphere",
                "location": [0, 0, 2],
                "rotation_deg": [0, 0, 0],
                "scale": [1, 1, 1],
            },
        ],
        "lights": [
            {
                "name": "Warm Interior",
                "type": "POINT",
                "location": [1, 2, 3],
                "rotation_deg": [0, 0, 0],
                "energy": 50,
                "color": [1, 0.7, 0.4],
                "distance": 12,
            }
        ],
        "characters": [],
        "environment": {
            "ambient_color": [0.12, 0.16, 0.2],
            "outdoor_ambient_color": [0.36, 0.44, 0.52],
            "brightness": 2.4,
            "clock_time": 16,
            "exposure_compensation": 0.1,
            "global_shadows": True,
            "shadow_softness": 0.25,
            "atmosphere": {
                "color": [0.72, 0.81, 0.91],
                "decay": [0.3, 0.41, 0.55],
                "density": 0.18,
                "glare": 0.2,
                "haze": 0.7,
                "offset": 0.15,
            },
            "clouds": {
                "color": [0.82, 0.87, 0.92],
                "cover": 0.45,
                "density": 0.4,
                "enabled": True,
            },
        },
    }


def test_rainforest_treasure_hunt_example_compiles_with_spawn_and_nonblocking_pickups():
    root = Path(__file__).resolve().parents[3]
    example = json.loads(
        (root / "examples/worlds/rainforest-treasure-hunt/scene-recipe.json").read_text(
            encoding="utf-8"
        )
    )
    project, _ = scene_recipe_to_rojo_project(example, gameplay_mode="treasure_hunt")

    map_node = project["tree"]["Workspace"]["Roblox Game Architect"]["Rainforest Treasure Hunt"]
    collectibles = map_node["Collectible"]
    assert map_node["RGA Spawn"]["$className"] == "SpawnLocation"
    pickup_nodes = [item for name, item in collectibles.items() if not name.startswith("$")]
    assert len(pickup_nodes) == 3
    assert all(not item["$properties"]["CanCollide"] for item in pickup_nodes)
    assert all(item["$properties"]["CanTouch"] is True for item in pickup_nodes)
    assert "RGA Treasure Hunt" in project["tree"]["ServerScriptService"]


def test_scene_recipe_compiles_to_closed_rojo_tree_with_y_up_transforms():
    project, summary = scene_recipe_to_rojo_project(_recipe())
    map_node = project["tree"]["Workspace"]["Roblox Game Architect"]["Mangrove Shore"]
    house = map_node["Architecture"]["001 Stilt House"]
    foliage = map_node["Vegetation"]["002 Mangrove Crown"]

    assert house["$className"] == "Part"
    assert house["$properties"]["CFrame"][:3] == [2.0, 4.0, 3.0]
    assert house["$properties"]["Size"] == [4.0, 1.0, 2.0]
    assert foliage["$properties"]["Shape"] == "Ball"
    assert map_node["Lighting"]["001 Warm Interior"]["Light"]["$className"] == "PointLight"
    lighting = project["tree"]["Lighting"]
    assert lighting["$properties"]["ClockTime"] == 16
    assert lighting["$properties"]["GlobalShadows"] is True
    assert lighting["Atmosphere"]["$properties"]["Density"] == 0.18
    assert project["tree"]["Workspace"]["Terrain"]["Clouds"]["$properties"]["Cover"] == 0.45
    assert summary == {
        "object_count": 2,
        "part_count": 2,
        "light_count": 1,
        "approximated_object_count": 0,
        "omitted_character_count": 0,
        "omitted_sun_light_count": 0,
    }


def test_cloud_collision_geometry_preserves_rotation_axes_shapes_and_openings():
    payload = _recipe()
    payload["objects"][1]["role"] = "opening"
    compiled = scene_recipe_collision_payload(SceneRecipe.from_mapping(payload))
    house, opening = compiled["objects"]
    assert house["cframe"][:3] == [2, 4, 3]
    assert house["cframe"][3:] == pytest.approx([0, 0, -1, 0, 1, 0, 1, 0, 0])
    assert house["size"] == [4, 1, 2]
    assert house["shape"] == "Block"
    assert house["can_collide"] is True
    assert opening["shape"] == "Ball"
    assert opening["can_collide"] is False


def test_reviewed_imported_model_replaces_recipe_proxies_and_keeps_environment():
    project, summary = scene_recipe_to_rojo_project(_recipe(), include_imported_model=True)
    workspace = project["tree"]["Workspace"]["Roblox Game Architect"]
    assert workspace["Imported Blender Model"]["RGA Imported Model"] == {
        "$path": "assets/imported-model.rbxm"
    }
    map_node = workspace["Mangrove Shore"]
    assert set(map_node) == {"$className", "$ignoreUnknownInstances", "Lighting"}
    assert project["tree"]["Lighting"]["Atmosphere"]["$properties"]["Density"] == 0.18
    assert summary["object_count"] == len(_recipe()["objects"])
    assert summary["part_count"] == 0
    assert summary["approximated_object_count"] == 0


def test_imported_model_tree_requires_whitelisted_meshes_and_references():
    root = ET.Element("roblox")
    imported_parent = ET.SubElement(root, "Item", {"class": "Folder"})
    parent_properties = ET.SubElement(imported_parent, "Properties")
    ET.SubElement(parent_properties, "string", {"name": "Name"}).text = "Imported Blender Model"
    imported_root = ET.SubElement(imported_parent, "Item", {"class": "Model"})
    properties = ET.SubElement(imported_root, "Properties")
    ET.SubElement(properties, "string", {"name": "Name"}).text = "RGA Imported Model"
    mesh = ET.SubElement(imported_root, "Item", {"class": "MeshPart"})
    mesh_properties = ET.SubElement(mesh, "Properties")
    ET.SubElement(mesh_properties, "bool", {"name": "Anchored"}).text = "true"
    size = ET.SubElement(mesh_properties, "Vector3", {"name": "size"})
    for axis in ("X", "Y", "Z"):
        ET.SubElement(size, axis).text = "1"
    frame = ET.SubElement(mesh_properties, "CoordinateFrame", {"name": "CFrame"})
    for axis in ("X", "Y", "Z", "R00", "R01", "R02", "R10", "R11", "R12", "R20", "R21", "R22"):
        ET.SubElement(frame, axis).text = "1" if axis in {"R00", "R11", "R22"} else "0"
    ET.SubElement(mesh_properties, "Content", {"name": "MeshContent"}).append(ET.Element("uri"))
    mesh_properties[-1][0].text = "rbxassetid://123456789"
    _validate_imported_model_tree(root, 1)
    for target, invalid, message in (
        (mesh_properties.find("bool"), "false", "must be anchored"),
        (size.find("X"), "0", "must be positive"),
        (size.find("X"), "nan", "nonfinite"),
        (frame.find("X"), "inf", "nonfinite"),
        (frame.find("R00"), "invalid", "nonnumeric"),
    ):
        original = target.text
        target.text = invalid
        with pytest.raises(RobloxPlaceBuildError, match=message):
            _validate_imported_model_tree(root, 1)
        target.text = original
    mesh.set("class", "Script")
    with pytest.raises(RobloxPlaceBuildError, match="unsupported Roblox instances"):
        _validate_imported_model_tree(root, 1)


def test_scene_recipe_never_accepts_callers_class_names_or_script_nodes():
    recipe = _recipe()
    recipe["objects"][0]["$className"] = "Script"
    try:
        scene_recipe_to_rojo_project(recipe)
    except ValueError:
        pass
    else:
        raise AssertionError("unrecognized recipe fields must be rejected")


def test_treasure_hunt_mode_adds_only_fixed_server_template():
    recipe = _recipe()
    recipe["objects"].append(
        {
            "name": "Coast Trail",
            "role": "path",
            "primitive": "cube",
            "location": [2, 3, 3],
            "rotation_deg": [0, 0, 0],
            "scale": [4, 1, 0.2],
        }
    )
    recipe["objects"].append(
        {
            "name": "Golden Coin",
            "role": "collectible",
            "primitive": "cylinder",
            "location": [4, 2, 1],
            "rotation_deg": [0, 0, 0],
            "scale": [0.5, 0.5, 0.2],
        }
    )
    project, _ = scene_recipe_to_rojo_project(recipe, gameplay_mode="treasure_hunt")
    server_scripts = project["tree"]["ServerScriptService"]
    map_node = project["tree"]["Workspace"]["Roblox Game Architect"]["Mangrove Shore"]
    assert server_scripts["RGA Treasure Hunt"] == {
        "$path": "server/treasure_hunt.server.luau",
    }
    assert map_node["RGA Spawn"]["$className"] == "SpawnLocation"
    assert map_node["RGA Spawn"]["$properties"]["Anchored"] is True
    assert map_node["RGA Spawn"]["$properties"]["Neutral"] is True
    assert map_node["RGA Spawn"]["$properties"]["CFrame"][:3] == [2.0, 5.7, 3.0]
    collectible = map_node["Collectible"]["004 Golden Coin"]
    assert collectible["$properties"]["CanCollide"] is False
    assert collectible["$properties"]["CanTouch"] is True
    source = treasure_hunt_source()
    assert "DataStoreService" not in source
    assert "HttpService" not in source
    assert "loadstring" not in source
    assert "Victories" in source and "GetPlayerFromCharacter" in source
    assert source.index("Players.PlayerAdded:Connect(addPlayer)") < source.index(
        "Players:GetPlayers()"
    )
    assert "if playerCollections[player] ~= nil then" in source


def test_treasure_hunt_requires_collectible_scene_objects_and_closed_mode():
    recipe = SceneRecipe.from_mapping(_recipe())
    with pytest.raises(GameplayTemplateError, match="requires 1 to 100"):
        validate_gameplay_mode("treasure_hunt", recipe)
    with pytest.raises(
        GameplayTemplateError,
        match="must be blockout, obby, treasure_hunt, or rule_game",
    ):
        validate_gameplay_mode("arbitrary", recipe)
    with pytest.raises(RobloxPlaceBuildError, match="requires 1 to 100"):
        scene_recipe_to_rojo_project(recipe, gameplay_mode="treasure_hunt")


def test_obby_build_adds_ordered_checkpoint_spawns_and_only_fixed_server_gameplay():
    recipe = _recipe()
    recipe["objects"].extend(
        [
            {
                "name": "Start Route",
                "role": "path",
                "primitive": "cube",
                "location": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [4, 2, 4],
            },
            {
                "name": "Final Route",
                "role": "path",
                "primitive": "cube",
                "location": [10, 4, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [8, 1, 4],
            },
        ]
    )
    recipe_value = SceneRecipe.from_mapping(recipe)
    validate_gameplay_mode("obby", recipe_value)
    project, _ = scene_recipe_to_rojo_project(recipe_value, gameplay_mode="obby")
    map_node = project["tree"]["Workspace"]["Roblox Game Architect"]["Mangrove Shore"]
    checkpoints = map_node["RGA Checkpoints"]
    assert checkpoints["001 Checkpoint"]["$className"] == "SpawnLocation"
    assert checkpoints["002 Checkpoint"]["$className"] == "SpawnLocation"
    assert checkpoints["001 Checkpoint"]["$properties"]["CFrame"][:3] == [0.0, 6.5, 0.0]
    assert project["tree"]["ServerScriptService"]["RGA Obby Course"] == {
        "$path": "server/obby_course.server.luau"
    }
    source = obby_course_source()
    assert "GetPlayerFromCharacter" in source
    assert "RespawnLocation" in source and "Stage" in source and "Wins" in source
    assert "DataStoreService" not in source
    assert "HttpService" not in source
    assert "loadstring" not in source
    assert source.index("Players.PlayerAdded:Connect(addPlayer)") < source.index(
        "Players:GetPlayers()"
    )
    assert "if playerStages[player] ~= nil then" in source
    assert 'map:FindFirstChild("Hazard")' in source
    assert "hazard.Touched:Connect(function(hit)" in source
    assert 'character:FindFirstChildOfClass("Humanoid")' in source
    assert "humanoid.Health = 0" in source


def test_obby_requires_two_connected_path_segments():
    recipe = _recipe()
    recipe["objects"].append(
        {
            "name": "Only Route",
            "role": "path",
            "primitive": "cube",
            "location": [0, 0, 0],
            "rotation_deg": [0, 0, 0],
            "scale": [8, 1, 4],
        }
    )
    with pytest.raises(GameplayTemplateError, match="at least two"):
        validate_gameplay_mode("obby", SceneRecipe.from_mapping(recipe))


def test_hazard_role_serializes_as_touchable_hazard_folder_for_fixed_gameplay():
    recipe = _recipe()
    recipe["objects"].extend(
        [
            {
                "name": "Start Route",
                "role": "path",
                "primitive": "cube",
                "location": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [8, 1, 4],
            },
            {
                "name": "Final Route",
                "role": "path",
                "primitive": "cube",
                "location": [10, 2, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [8, 1, 4],
            },
            {
                "name": "Lava Pit",
                "role": "hazard",
                "primitive": "cube",
                "location": [4, -2, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [4, 1, 4],
            },
        ]
    )
    project, _ = scene_recipe_to_rojo_project(recipe, gameplay_mode="obby")
    map_node = project["tree"]["Workspace"]["Roblox Game Architect"]["Mangrove Shore"]
    assert map_node["Hazard"]["005 Lava Pit"]["$properties"]["CanTouch"] is True
    assert 'map:FindFirstChild("Hazard")' in obby_course_source()


def test_rule_game_serializes_only_validated_data_and_trusted_interpreter():
    recipe = _recipe()
    recipe["objects"].extend(
        [
            {
                "name": "Start Path",
                "role": "path",
                "primitive": "cube",
                "location": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [8, 1, 4],
            },
            {
                "name": "Star Pickup",
                "role": "collectible",
                "primitive": "uv_sphere",
                "location": [1, 0, 2],
                "rotation_deg": [0, 0, 0],
                "scale": [0.5, 0.5, 0.5],
            },
            {
                "name": "Lava Vent",
                "role": "hazard",
                "primitive": "cube",
                "location": [2, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [2, 1, 0.2],
            },
            {
                "name": "Finish Lookout",
                "role": "landmark",
                "primitive": "cube",
                "location": [4, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [2, 1, 1],
            },
        ]
    )
    rules = [
        {"trigger_role": "collectible", "action": "award_points", "amount": 5},
        {"trigger_role": "collectible", "action": "heal", "amount": 10},
        {"trigger_role": "hazard", "action": "damage", "amount": 20},
        {"trigger_role": "landmark", "action": "award_win", "minimum_points": 5},
    ]
    project, _ = scene_recipe_to_rojo_project(
        recipe, gameplay_mode="rule_game", gameplay_rules=rules
    )
    map_node = project["tree"]["Workspace"]["Roblox Game Architect"]["Mangrove Shore"]
    rules_node = map_node["RGA Gameplay Rules"]
    assert json.loads(rules_node["$properties"]["Value"]) == rules
    assert map_node["RGA Spawn"]["Player Spawn"]["$className"] == "SpawnLocation"
    assert project["tree"]["ServerScriptService"]["RGA Data Rules"] == {
        "$path": "server/rule_game.server.luau"
    }
    source = rule_game_source()
    assert "HttpService:JSONDecode" in source
    assert 'action == "award_points"' in source
    assert 'action == "heal"' in source
    assert 'action == "damage"' in source
    assert "humanoid:TakeDamage(math.min(amount, math.max(0, humanoid.Health - 1)))" in source
    assert "Win threshold exceeds available points per round" in source
    assert 'action == "eliminate"' in source
    assert 'action == "award_win"' in source
    assert 'assert(allowedField, "Unexpected gameplay rule field")' in source
    assert 'assert(fieldCount == expectedFieldCount, "Invalid gameplay rule fields")' in source
    assert "leaderstats.Wins.Value += 1" in source
    assert "leaderstats.Points.Value = 0" in source
    assert "loadstring" not in source

    conflicting = [*rules, {"trigger_role": "hazard", "action": "eliminate"}]
    with pytest.raises(GameplayTemplateError, match="damage and eliminate"):
        validate_gameplay_mode("rule_game", SceneRecipe.from_mapping(recipe), conflicting)

    impossible = [*rules[:-1], {**rules[-1], "minimum_points": 6}]
    with pytest.raises(GameplayTemplateError, match="only 5 per round"):
        validate_gameplay_mode("rule_game", SceneRecipe.from_mapping(recipe), impossible)
    recipe["objects"].append({**recipe["objects"][-3], "name": "Second Star Pickup"})
    validate_gameplay_mode("rule_game", SceneRecipe.from_mapping(recipe), impossible)


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        ({"trigger_role": "collectible", "action": "execute", "source": "x"}, "action"),
        ({"trigger_role": "hazard", "action": "eliminate", "code": "x"}, "eliminate"),
        ({"trigger_role": "collectible", "action": "award_points", "amount": True}, "integer"),
        ({"trigger_role": "prop", "action": "damage", "amount": 10}, "hazard"),
        ({"trigger_role": "hazard", "action": "award_win", "minimum_points": 2}, "landmark"),
        ({"trigger_role": "landmark", "action": "award_win", "minimum_points": True}, "integer"),
    ],
)
def test_rule_game_rejects_unknown_actions_and_executable_fields(rule, message):
    recipe = _recipe()
    recipe["objects"].extend(
        [
            {
                "name": "Route",
                "role": "path",
                "primitive": "cube",
                "location": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [8, 1, 4],
            },
            {
                "name": "Pickup",
                "role": "collectible",
                "primitive": "cube",
                "location": [1, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [1, 1, 1],
            },
            {
                "name": "Lava",
                "role": "hazard",
                "primitive": "cube",
                "location": [2, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [1, 1, 1],
            },
            {
                "name": "Finish",
                "role": "landmark",
                "primitive": "cube",
                "location": [3, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [1, 1, 1],
            },
            {
                "name": "Touch Prop",
                "role": "prop",
                "primitive": "cube",
                "location": [4, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [1, 1, 1],
            },
        ]
    )
    rules = [rule]
    if rule.get("action") == "award_win":
        rules.append({"trigger_role": "collectible", "action": "award_points", "amount": 1})
    with pytest.raises(GameplayTemplateError, match=message):
        validate_gameplay_mode("rule_game", SceneRecipe.from_mapping(recipe), rules)


@pytest.mark.parametrize("word", ["hazard", "traps", "lava", "peligros", "trampas"])
def test_world_brief_hazards_require_hazard_scene_objects(word: str):
    from core.worldbuilding import _required_scene_roles

    assert "hazard" in _required_scene_roles(f"A Roblox world with {word} on the course")
