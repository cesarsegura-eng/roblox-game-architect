"""Fail-closed Gate 1 policy for the current script-free edit subset.

The API queue accepts declarative creation and allowlisted property changes only.
Luau source, destructive operations, reparenting, and playtests remain blocked until
their policy and execution boundaries are implemented.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

MAX_ID = 64
MAX_SEGMENTS = 16
MAX_SEGMENT_LENGTH = 100
MAX_OPERATIONS = 100
MAX_SCOPE_ENTRIES = 32
SAFE_CLASSES = frozenset({"Folder", "Model", "Part", "WedgePart"})
SAFE_MATERIALS = frozenset(
    {
        "Plastic",
        "SmoothPlastic",
        "Wood",
        "WoodPlanks",
        "Metal",
        "Concrete",
        "Brick",
        "Glass",
        "Neon",
        "Grass",
        "Sand",
        "Fabric",
    }
)


class ActionPolicyError(ValueError):
    """An action is malformed or outside the currently safe declarative subset."""


def validate_action(action: object) -> None:
    """Raise when an action fails the closed schema subset, scope, or ordering rules."""
    if not isinstance(action, Mapping) or set(action) != {
        "type",
        "action_id",
        "declared_scope",
        "operations",
    }:
        raise ActionPolicyError("edit.action has unexpected or missing fields")
    if action["type"] != "edit.action":
        raise ActionPolicyError("work item is not an edit.action")
    _text(action["action_id"], MAX_ID, "action_id")
    scope = action["declared_scope"]
    if not isinstance(scope, list) or not 1 <= len(scope) <= MAX_SCOPE_ENTRIES:
        raise ActionPolicyError("declared_scope must contain between 1 and 32 entries")
    for entry in scope:
        if not isinstance(entry, Mapping) or set(entry) != {"path", "extent"}:
            raise ActionPolicyError("scope entry has unexpected or missing fields")
        scope_path = _path(entry["path"], "scope path")
        if scope_path[0] != "Workspace":
            raise ActionPolicyError("the current edit policy is limited to Workspace")
        if not isinstance(entry["extent"], str) or entry["extent"] not in {"self", "subtree"}:
            raise ActionPolicyError("scope extent must be self or subtree")

    operations = action["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise ActionPolicyError("operations must contain between 1 and 100 entries")
    _validate_operation_shapes(operations)
    violations = _check_scope_and_order(scope, operations)
    if violations:
        rendered = ", ".join(f"{code} at operation {index + 1}" for code, index in violations)
        raise ActionPolicyError(f"edit.action violates scope or ordering policy: {rendered}")


def validate_work_item(item: object) -> None:
    """Gate every work type; unsupported execution classes fail closed."""
    if not isinstance(item, Mapping):
        raise ActionPolicyError("work item must be an object")
    kind = item.get("type")
    if kind == "edit.action":
        validate_action(item)
    elif kind == "playtest.request":
        raise ActionPolicyError("playtests are blocked until disposable execution is available")
    else:
        raise ActionPolicyError("unsupported work item type")


def _validate_operation_shapes(operations: list[object]) -> None:
    ids: set[str] = set()
    for index, operation in enumerate(operations):
        label = f"operation {index + 1}"
        if not isinstance(operation, Mapping):
            raise ActionPolicyError(f"{label} must be an object")
        op = operation.get("op")
        if op == "create_instance":
            if set(operation) != {"op", "op_id", "parent", "name", "class_name"}:
                raise ActionPolicyError(f"{label} has unexpected or missing fields")
            _reference(operation["parent"], f"{label} parent")
            if operation["parent"]["expect_class"] not in {"Workspace", "Folder", "Model"}:
                raise ActionPolicyError(f"{label} parent must be Workspace, Folder, or Model")
            _text(operation["name"], MAX_SEGMENT_LENGTH, f"{label} name")
            class_name = operation["class_name"]
            if not isinstance(class_name, str) or class_name not in SAFE_CLASSES:
                raise ActionPolicyError(f"{label} class is blocked by the script-free policy")
        elif op == "set_property":
            if set(operation) != {"op", "op_id", "target", "property", "value"}:
                raise ActionPolicyError(f"{label} has unexpected or missing fields")
            target = _reference(operation["target"], f"{label} target")
            if target["expect_class"] not in {"Part", "WedgePart"}:
                raise ActionPolicyError(f"{label} target class is not an editable part")
            _validate_property(operation["property"], operation["value"], label)
        else:
            raise ActionPolicyError(
                f"{label} operation {op!r} is blocked; only create_instance and "
                "set_property are enabled"
            )
        op_id = _text(operation.get("op_id"), MAX_ID, f"{label} op_id")
        if op_id in ids:
            raise ActionPolicyError(f"duplicate op_id: {op_id}")
        ids.add(op_id)


def _validate_property(property_name: object, value: object, label: str) -> None:
    if not isinstance(property_name, str):
        raise ActionPolicyError(f"{label} property must be a string")
    if property_name in {"Anchored", "CanCollide"}:
        if type(value) is not bool:
            raise ActionPolicyError(f"{label} {property_name} must be boolean")
    elif property_name == "Transparency":
        _number(value, 0, 1, f"{label} Transparency")
    elif property_name in {"Size", "Position"}:
        axes = _object(value, {"x", "y", "z"}, f"{label} {property_name}")
        if set(axes) != {"x", "y", "z"}:
            raise ActionPolicyError(f"{label} {property_name} must contain x, y, and z")
        if property_name == "Size":
            for axis, component in axes.items():
                _number(component, 0.05, 2048, f"{label} Size.{axis}")
        else:
            for axis, component in axes.items():
                _number(component, -100_000, 100_000, f"{label} Position.{axis}")
    elif property_name == "Orientation":
        axes = _object(value, {"x", "y", "z"}, f"{label} Orientation")
        if set(axes) != {"x", "y", "z"}:
            raise ActionPolicyError(f"{label} Orientation must contain x, y, and z")
        for axis, component in axes.items():
            _number(component, -360, 360, f"{label} Orientation.{axis}")
    elif property_name == "Color":
        color = _object(value, {"r", "g", "b"}, f"{label} Color")
        if set(color) != {"r", "g", "b"}:
            raise ActionPolicyError(f"{label} Color must contain r, g, and b")
        for channel, component in color.items():
            _number(component, 0, 1, f"{label} Color.{channel}")
    elif property_name == "Material":
        material = _object(value, {"enum", "item"}, f"{label} Material")
        if set(material) != {"enum", "item"} or material["enum"] != "Material":
            raise ActionPolicyError(f"{label} Material value is malformed")
        if not isinstance(material["item"], str) or material["item"] not in SAFE_MATERIALS:
            raise ActionPolicyError(f"{label} Material item is not allowed")
    else:
        raise ActionPolicyError(f"{label} property is not allowlisted")


def _check_scope_and_order(scope: list[object], operations: list[object]) -> list[tuple[str, int]]:
    known_class: dict[tuple[str, ...], str] = {}
    stale: list[tuple[str, ...]] = []
    addressed: list[tuple[str, ...]] = []
    violations: list[tuple[str, int]] = []
    seen_ids: set[str] = set()

    def address(reference: Mapping[str, object], index: int) -> tuple[str, ...]:
        path = tuple(reference["path"])  # already type-checked
        if any(_is_prefix(old, path) for old in stale):
            violations.append(("stale_target", index))
        known = known_class.get(path)
        if known is not None and known != reference["expect_class"]:
            violations.append(("created_class_mismatch", index))
        return path

    def touch(path: tuple[str, ...], extent: str, index: int) -> None:
        if not _covered(scope, path, extent):
            violations.append(("scope_violation", index))

    def bring_into_being(
        path: tuple[str, ...], class_name: str, before: list[tuple[str, ...]], index: int
    ) -> None:
        if path in known_class:
            violations.append(("duplicate_target", index))
        if any(_is_prefix(old, path) for old in stale):
            violations.append(("stale_target", index))
        live = [node for node in before if not any(_is_prefix(old, node) for old in stale)]
        if any(_is_prefix(path, named) for named in live):
            violations.append(("forward_reference", index))
        known_class[path] = class_name

    for index, operation in enumerate(operations):
        op_id = operation["op_id"]
        if op_id in seen_ids:
            violations.append(("duplicate_op_id", index))
        seen_ids.add(op_id)
        before = list(addressed)
        if operation["op"] == "create_instance":
            parent = address(operation["parent"], index)
            addressed.append(parent)
            created = (*parent, operation["name"])
            touch(created, "self", index)
            bring_into_being(created, operation["class_name"], before, index)
        else:
            target = address(operation["target"], index)
            addressed.append(target)
            touch(target, "self", index)
    return violations


def _covered(scope: list[object], path: tuple[str, ...], extent: str) -> bool:
    for entry in scope:
        scope_path = tuple(entry["path"])
        if not _is_prefix(scope_path, path):
            continue
        if entry["extent"] == "subtree" or (scope_path == path and extent == "self"):
            return True
    return False


def _is_prefix(prefix: tuple[str, ...], path: tuple[str, ...]) -> bool:
    return path[: len(prefix)] == prefix


def _reference(value: object, label: str) -> Mapping[str, object]:
    reference = _object(value, {"path", "expect_class"}, label)
    if set(reference) != {"path", "expect_class"}:
        raise ActionPolicyError(f"{label} has unexpected or missing fields")
    path = _path(reference["path"], f"{label} path")
    if path[0] != "Workspace":
        raise ActionPolicyError(f"{label} must be inside Workspace")
    _text(reference["expect_class"], 64, f"{label} expect_class")
    return reference


def _path(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_SEGMENTS:
        raise ActionPolicyError(f"{label} must contain 1 to 16 segments")
    return [_text(segment, MAX_SEGMENT_LENGTH, f"{label} segment") for segment in value]


def _object(value: object, allowed: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not set(value) <= allowed:
        raise ActionPolicyError(f"{label} has unexpected or missing fields")
    return value


def _text(value: object, maximum: int, label: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise ActionPolicyError(f"{label} must contain 1 to {maximum} characters")
    return value


def _number(
    value: object,
    low: float,
    high: float,
    label: str,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ActionPolicyError(f"{label} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ActionPolicyError(f"{label} is outside the supported range") from exc
    if not math.isfinite(number) or number < low or number > high:
        raise ActionPolicyError(f"{label} is outside the supported range")
    return number
