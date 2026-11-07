from core.scene_to_studio import (
    MAX_PROXY_OPERATIONS,
    MAX_PROXY_PARTS,
    scene_recipe_to_studio_action,
)
from sandbox.action_policy import validate_action


def _object(name: str, role: str, x: int) -> dict:
    return {
        "name": name,
        "role": role,
        "primitive": "cube",
        "location": [x, 0, 0],
        "rotation_deg": [0, 0, 0],
        "scale": [1, 1, 1],
    }


def test_scene_proxy_cap_prioritizes_route_and_entry_and_stays_policy_valid():
    recipe = {
        "schema_version": 2,
        "name": "Over-budget blockout",
        "units": "blender_units",
        "up_axis": "Z",
        "objects": [
            *(_object(f"Decorative prop {index}", "prop", index * 2) for index in range(14)),
            _object("Main route", "path", 30),
            _object("Main entry", "entry", 32),
        ],
    }

    action = scene_recipe_to_studio_action(recipe, "e9d52f8d-3b2f-4d13-bb90-4f8e08f80c1c")
    validate_action(action)
    created_parts = [
        operation["name"]
        for operation in action["operations"]
        if operation["op"] == "create_instance" and operation["class_name"] == "Part"
    ]

    assert len(created_parts) == MAX_PROXY_PARTS
    assert any(name.startswith("path Main route") for name in created_parts)
    assert any(name.startswith("entry Main entry") for name in created_parts)
    assert sum(name.startswith("prop Decorative prop") for name in created_parts) == 12
    # Chosen parts return to source order after the cap selection is made.
    assert created_parts[-2].startswith("path Main route")
    assert created_parts[-1].startswith("entry Main entry")


def test_scene_proxy_preserves_blender_orientation_in_roblox_basis():
    recipe = {
        "schema_version": 2,
        "name": "Rotated blockout",
        "units": "blender_units",
        "up_axis": "Z",
        "objects": [
            {
                **_object("Rotated wall", "architecture", 5),
                "location": [5, 3, 7],
                "rotation_deg": [0, 0, 90],
                "scale": [4, 1, 0.5],
            }
        ],
    }

    action = scene_recipe_to_studio_action(recipe, "e9d52f8d-3b2f-4d13-bb90-4f8e08f80c1c")
    validate_action(action)
    properties = {
        operation["property"]: operation["value"]
        for operation in action["operations"]
        if operation["op"] == "set_property"
    }

    assert properties["Position"] == {"x": 5, "y": 7, "z": 3}
    assert properties["Size"] == {"x": 8, "y": 1, "z": 2}
    assert properties["Orientation"] == {"x": 0, "y": -90, "z": 0}


def test_rotated_proxy_selection_obeys_operation_budget():
    recipe = {
        "schema_version": 2,
        "name": "Rotated over-budget blockout",
        "units": "blender_units",
        "up_axis": "Z",
        "objects": [
            {
                **_object(f"Prop {index}", "prop", index * 2),
                "rotation_deg": [0, 0, 15],
            }
            for index in range(14)
        ]
        + [
            {
                **_object("Main route", "path", 30),
                "rotation_deg": [0, 0, 15],
            },
            {
                **_object("Main entry", "entry", 32),
                "rotation_deg": [0, 0, 15],
            },
        ],
    }

    action = scene_recipe_to_studio_action(recipe, "e9d52f8d-3b2f-4d13-bb90-4f8e08f80c1c")
    validate_action(action)
    parts = [
        operation["name"]
        for operation in action["operations"]
        if operation["op"] == "create_instance" and operation["class_name"] == "Part"
    ]

    assert len(parts) == 12
    assert any(name.startswith("path Main route") for name in parts)
    assert any(name.startswith("entry Main entry") for name in parts)
    assert len(action["operations"]) <= MAX_PROXY_OPERATIONS
