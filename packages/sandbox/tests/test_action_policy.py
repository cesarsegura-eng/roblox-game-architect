from __future__ import annotations

import copy

import pytest

from sandbox.action_policy import ActionPolicyError, validate_action, validate_work_item


def reference(*path: str, class_name: str = "Workspace") -> dict:
    return {"path": list(path), "expect_class": class_name}


def create_part() -> dict:
    return {
        "op": "create_instance",
        "op_id": "op-create",
        "parent": reference("Workspace"),
        "name": "Platform",
        "class_name": "Part",
    }


def valid_action() -> dict:
    return {
        "type": "edit.action",
        "action_id": "action-1",
        "declared_scope": [{"path": ["Workspace"], "extent": "subtree"}],
        "operations": [
            create_part(),
            {
                "op": "set_property",
                "op_id": "op-anchor",
                "target": reference("Workspace", "Platform", class_name="Part"),
                "property": "Anchored",
                "value": True,
            },
            {
                "op": "set_property",
                "op_id": "op-size",
                "target": reference("Workspace", "Platform", class_name="Part"),
                "property": "Size",
                "value": {"x": 0.05, "y": 1, "z": 8},
            },
            {
                "op": "set_property",
                "op_id": "op-orientation",
                "target": reference("Workspace", "Platform", class_name="Part"),
                "property": "Orientation",
                "value": {"x": 0, "y": -90, "z": 0},
            },
        ],
    }


def test_allows_scoped_part_creation_and_allowlisted_properties() -> None:
    validate_action(valid_action())


def test_rejects_actions_outside_declared_workspace_subtree() -> None:
    item = valid_action()
    item["declared_scope"] = [{"path": ["Workspace"], "extent": "self"}]
    with pytest.raises(ActionPolicyError, match="scope_violation"):
        validate_action(item)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda item: item["operations"][0].update(class_name="Script"), "script-free policy"),
        (
            lambda item: item["operations"][0].update(op="set_script_source"),
            "blocked",
        ),
        (
            lambda item: item["operations"][1].update(property="Enabled", value=True),
            "not allowlisted",
        ),
        (
            lambda item: item["operations"][1].update(value="true"),
            "must be boolean",
        ),
        (
            lambda item: item["operations"][3].update(value={"x": 0, "y": 361, "z": 0}),
            "Orientation.y",
        ),
        (
            lambda item: item["declared_scope"].__setitem__(
                0, {"path": ["ServerStorage"], "extent": "self"}
            ),
            "limited to Workspace",
        ),
    ],
)
def test_rejects_unsafe_or_malformed_actions(mutation, message: str) -> None:
    item = valid_action()
    mutation(item)
    with pytest.raises(ActionPolicyError, match=message):
        validate_action(item)


def test_rejects_forward_references_and_class_confusion() -> None:
    item = valid_action()
    item["operations"] = [copy.deepcopy(item["operations"][1]), create_part()]
    with pytest.raises(ActionPolicyError, match="forward_reference"):
        validate_action(item)

    item = valid_action()
    item["operations"][1]["target"]["expect_class"] = "Model"
    with pytest.raises(ActionPolicyError, match="class is not an editable part"):
        validate_action(item)


def test_blocks_playtests_until_disposable_execution_exists() -> None:
    with pytest.raises(ActionPolicyError, match="disposable execution"):
        validate_work_item({"type": "playtest.request", "playtest_id": "playtest-1"})
