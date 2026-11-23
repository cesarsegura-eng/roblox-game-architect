"""Tests for the reference semantic checks (ADR-0008) and for the vectors' semantic validity.

The checks are an executable specification that lives only here. `packages/sandbox` is the
single authority on scope and ordering and will implement them itself.
"""

import copy
import json

import pytest
from protocol_schemas import EXAMPLES_DIR, vector_text
from protocol_semantics import (
    ACTION_VIOLATIONS,
    RESULT_VIOLATIONS,
    STATE_VIOLATIONS,
    absence_is_evidence,
    check_edit_action,
    check_edit_result,
    check_project_state,
    covers,
)
from protocol_strict_json import parse_strict

INDEX = json.loads((EXAMPLES_DIR / "index.json").read_text(encoding="utf-8"))


def ref(path, cls="Part"):
    return {"path": path.split("/"), "expect_class": cls}


def create(i, parent, parent_cls, name, cls):
    return {
        "op": "create_instance",
        "op_id": f"o{i}",
        "parent": ref(parent, parent_cls),
        "name": name,
        "class_name": cls,
    }


def setp(i, path, cls="Part"):
    return {
        "op": "set_property",
        "op_id": f"o{i}",
        "target": ref(path, cls),
        "property": "Anchored",
        "value": True,
    }


def delete(i, path, cls="Part"):
    return {"op": "delete_instance", "op_id": f"o{i}", "target": ref(path, cls)}


def move(i, path, new_parent, cls="Part", parent_cls="Folder"):
    return {
        "op": "reparent",
        "op_id": f"o{i}",
        "target": ref(path, cls),
        "new_parent": ref(new_parent, parent_cls),
    }


def action(ops, *scope):
    entries = [{"path": p.split("/"), "extent": e} for p, e in scope] or [
        {"path": ["W"], "extent": "subtree"}
    ]
    return {"action_id": "a1", "declared_scope": entries, "operations": ops}


def codes(act):
    return sorted(v.code for v in check_edit_action(act))


# --------------------------------------------------------------- scope coverage


@pytest.mark.parametrize(
    ("scope", "path", "extent", "expected"),
    [
        ([("W/M", "subtree")], "W/M", "self", True),
        ([("W/M", "subtree")], "W/M/B/C", "subtree", True),
        ([("W/M", "subtree")], "W/N", "self", False),
        ([("W/M", "subtree")], "W", "self", False),
        ([("W/M", "self")], "W/M", "self", True),
        ([("W/M", "self")], "W/M", "subtree", False),
        ([("W/M", "self")], "W/M/B", "self", False),
        ([("W/M", "self"), ("W/N", "subtree")], "W/N/B", "subtree", True),
        ([], "W/M", "self", False),
    ],
)
def test_coverage(scope, path, extent, expected):
    entries = [{"path": p.split("/"), "extent": e} for p, e in scope]
    assert covers(entries, tuple(path.split("/")), extent) is expected


# ------------------------------------------------------------ action: valid cases


def test_the_documented_example_action_is_clean():
    with open(EXAMPLES_DIR / "valid/work.poll.response.edit-action.json", encoding="utf-8") as f:
        work = json.load(f)["message"]["payload"]["work"]
    assert check_edit_action(work) == []


@pytest.mark.parametrize(
    "act",
    [
        action([create(1, "W/M", "Folder", "A", "Part")], ("W/M/A", "self")),
        action([setp(1, "W/M/B")], ("W/M/B", "self")),
        action([delete(1, "W/M/B")], ("W/M", "subtree")),
        action([move(1, "W/M/B", "W/N")], ("W/M", "subtree"), ("W/N", "subtree")),
        action(
            [
                create(1, "W/M", "Folder", "F", "Folder"),
                create(2, "W/M/F", "Folder", "P", "Part"),
                setp(3, "W/M/F/P"),
            ]
        ),
        action([move(1, "W/M/B", "W/N"), setp(2, "W/N/B")], ("W", "subtree")),
    ],
    ids=[
        "create-under-self-scope",
        "self-scope-property",
        "delete",
        "move",
        "chain",
        "use-new-path",
    ],
)
def test_clean_actions(act):
    assert check_edit_action(act) == []


# ---------------------------------------------------------- action: each violation

VIOLATION_CASES = [
    (
        "create outside scope",
        action([create(1, "X/Y", "Folder", "A", "Part")]),
        ["scope_violation"],
    ),
    ("property outside scope", action([setp(1, "X/Y")]), ["scope_violation"]),
    (
        "self entry does not cover create beneath it",
        action([create(1, "W/M", "Folder", "A", "Part")], ("W/M", "self")),
        ["scope_violation"],
    ),
    ("delete needs subtree", action([delete(1, "W/M")], ("W/M", "self")), ["scope_violation"]),
    (
        "move destination outside scope",
        action([move(1, "W/M/B", "X")], ("W/M", "subtree")),
        ["scope_violation"],
    ),
    (
        "move source outside scope",
        action([move(1, "X/B", "W/N")], ("W/N", "subtree")),
        ["scope_violation"],
    ),
    (
        "forward reference",
        action([setp(1, "W/M/New"), create(2, "W/M", "Folder", "New", "Part")]),
        ["forward_reference"],
    ),
    (
        "forward reference to a descendant",
        action([setp(1, "W/M/New/Kid"), create(2, "W/M", "Folder", "New", "Folder")]),
        ["forward_reference"],
    ),
    ("address after delete", action([delete(1, "W/M/B"), setp(2, "W/M/B")]), ["stale_target"]),
    (
        "address beneath a deleted path",
        action([delete(1, "W/M"), setp(2, "W/M/B/C")]),
        ["stale_target"],
    ),
    (
        "create beneath a deleted path",
        action([delete(1, "W/M", "Folder"), create(2, "W/M", "Folder", "A", "Part")]),
        ["stale_target", "stale_target"],
    ),
    (
        "recreate a deleted path",
        action([delete(1, "W/M/B"), create(2, "W/M", "Folder", "B", "Part")]),
        ["stale_target"],
    ),
    ("address after move", action([move(1, "W/M/B", "W/N"), setp(2, "W/M/B")]), ["stale_target"]),
    (
        "duplicate create",
        action([create(1, "W/M", "Folder", "A", "Part"), create(2, "W/M", "Folder", "A", "Part")]),
        ["duplicate_target"],
    ),
    (
        "move onto a created path",
        action([create(1, "W/N", "Folder", "B", "Part"), move(2, "W/M/B", "W/N")]),
        ["duplicate_target"],
    ),
    ("move into itself", action([move(1, "W/M", "W/M", "Folder")]), ["invalid_reparent"]),
    ("move into a descendant", action([move(1, "W/M", "W/M/K/L", "Folder")]), ["invalid_reparent"]),
    ("move to the same parent", action([move(1, "W/M/B", "W/M")]), ["invalid_reparent"]),
    (
        "move a service",
        action([move(1, "W", "X")], ("W", "subtree"), ("X", "subtree")),
        ["invalid_reparent"],
    ),
    (
        "two moves forming a cycle",
        action([move(1, "W/A", "W/B", "Folder"), move(2, "W/B", "W/B/A", "Folder")]),
        ["invalid_reparent"],
    ),
    (
        "created class contradicted",
        action([create(1, "W/M", "Folder", "F", "Folder"), setp(2, "W/M/F", "Part")]),
        ["created_class_mismatch"],
    ),
    (
        "parent class contradicted",
        action(
            [create(1, "W/M", "Folder", "F", "Folder"), create(2, "W/M/F", "Model", "P", "Part")]
        ),
        ["created_class_mismatch"],
    ),
    (
        "duplicate op_id",
        action([setp(1, "W/M/B"), {**setp(2, "W/M/C"), "op_id": "o1"}]),
        ["duplicate_op_id"],
    ),
]


@pytest.mark.parametrize(
    ("label", "act", "expected"), VIOLATION_CASES, ids=[c[0] for c in VIOLATION_CASES]
)
def test_each_rule_is_enforced(label, act, expected):
    assert codes(act) == expected


def test_every_violation_code_is_exercised_and_the_list_is_closed():
    seen = {code for _, act, _ in VIOLATION_CASES for code in codes(act)}
    assert seen == set(ACTION_VIOLATIONS)


def test_a_move_makes_the_new_path_usable_and_the_old_one_stale():
    clean = action([move(1, "W/M/B", "W/N"), setp(2, "W/N/B")])
    assert codes(clean) == []
    stale = action([move(1, "W/M/B", "W/N"), setp(2, "W/M/B")])
    assert codes(stale) == ["stale_target"]


def test_effects_are_decidable_without_the_state_of_the_place():
    """The check takes only the action: no snapshot, no place. That is the design goal."""
    act = action([create(1, "W/M", "Folder", "A", "Part"), setp(2, "W/M/A")])
    assert check_edit_action(copy.deepcopy(act)) == check_edit_action(act) == []


# ---------------------------------------------------------------------- results


def result(outcome, *ops):
    return {"action_id": "a1", "outcome": outcome, "operations": list(ops)}


def op(i, status, with_error=None):
    out = {"op_id": f"o{i}", "status": status}
    if with_error or status == "failed":
        out["error"] = {"code": "operation_failed", "message": "x"}
    return out


def broken_error(i, status):
    out = {"op_id": f"o{i}", "status": status}
    if status != "failed":
        out["error"] = {"code": "operation_failed", "message": "x"}
    return out


RESULT_CASES = [
    ("applied", result("applied", op(1, "applied"), op(2, "applied")), []),
    ("rejected", result("rejected", op(1, "failed"), op(2, "skipped")), []),
    ("partial", result("partial", op(1, "applied"), op(2, "failed"), op(3, "skipped")), []),
    ("indeterminate", result("indeterminate", op(1, "unknown"), op(2, "unknown")), []),
    (
        "applied with a failure",
        result("applied", op(1, "applied"), op(2, "failed")),
        ["outcome_mismatch"],
    ),
    (
        "rejected with an applied op",
        result("rejected", op(1, "applied"), op(2, "failed")),
        ["outcome_mismatch"],
    ),
    ("rejected without a failure", result("rejected", op(1, "skipped")), ["outcome_mismatch"]),
    (
        "partial without an applied op",
        result("partial", op(1, "failed"), op(2, "skipped")),
        ["outcome_mismatch"],
    ),
    (
        "partial with two failures",
        result("partial", op(1, "applied"), op(2, "failed"), op(3, "failed")),
        ["outcome_mismatch"],
    ),
    (
        "partial out of order",
        result("partial", op(1, "failed"), op(2, "applied")),
        ["outcome_mismatch"],
    ),
    (
        "indeterminate with an applied op",
        result("indeterminate", op(1, "applied"), op(2, "unknown")),
        [],
    ),
    (
        "indeterminate with a skipped op after the unknown",
        result("indeterminate", op(1, "applied"), op(2, "unknown"), op(3, "skipped")),
        [],
    ),
    (
        "indeterminate with two unknowns",
        result("indeterminate", op(1, "unknown"), op(2, "unknown"), op(3, "skipped")),
        [],
    ),
    (
        "indeterminate without an unknown",
        result("indeterminate", op(1, "applied"), op(2, "skipped")),
        ["outcome_mismatch"],
    ),
    (
        "indeterminate out of order",
        result("indeterminate", op(1, "unknown"), op(2, "applied")),
        ["outcome_mismatch"],
    ),
    (
        "indeterminate with a failure",
        result("indeterminate", op(1, "applied"), op(2, "failed"), op(3, "unknown")),
        ["outcome_mismatch"],
    ),
    (
        "failed without an error",
        result("rejected", {"op_id": "o1", "status": "failed"}, op(2, "skipped")),
        ["error_mismatch"],
    ),
    (
        "error on a skipped op",
        result("rejected", op(1, "failed"), broken_error(2, "skipped")),
        ["error_mismatch"],
    ),
    (
        "duplicate op ids",
        result("applied", op(1, "applied"), {"op_id": "o1", "status": "applied"}),
        ["duplicate_op_id"],
    ),
]


@pytest.mark.parametrize(
    ("label", "res", "expected"), RESULT_CASES, ids=[c[0] for c in RESULT_CASES]
)
def test_result_consistency(label, res, expected):
    assert sorted({v.code for v in check_edit_result(res)}) == expected


def test_a_result_must_match_its_action():
    act = action([setp(1, "W/M/B"), setp(2, "W/M/C")])
    good = result("applied", op(1, "applied"), op(2, "applied"))
    assert check_edit_result(good, act) == []
    assert [v.code for v in check_edit_result({**good, "action_id": "other"}, act)] == [
        "result_mismatch"
    ]
    short = result("applied", op(1, "applied"))
    assert [v.code for v in check_edit_result(short, act)] == ["result_mismatch"]


def test_every_result_code_is_exercised():
    seen = {v.code for _, res, _ in RESULT_CASES for v in check_edit_result(res)}
    seen |= {
        v.code
        for v in check_edit_result(result("applied", op(1, "applied")), action([setp(2, "W/M/B")]))
    }
    assert seen == set(RESULT_VIOLATIONS)


# -------------------------------------------------------------------- snapshots


def snapshot(**overrides):
    base = {
        "snapshot_id": "s1",
        "reason": "session_start",
        "roots": ["Workspace"],
        "complete_depth": 3,
        "truncated": False,
        "entries": [
            {"path": ["Workspace"], "class_name": "Workspace"},
            {"path": ["Workspace", "Map"], "class_name": "Folder"},
        ],
    }
    base.update(overrides)
    return base


STATE_CASES = [
    ("clean", snapshot(), []),
    ("after_action with an id", snapshot(reason="after_action", after_action_id="a1"), []),
    ("after_action without an id", snapshot(reason="after_action"), ["reason_mismatch"]),
    ("session_start with an id", snapshot(after_action_id="a1"), ["reason_mismatch"]),
    (
        "entry outside the roots",
        snapshot(entries=[{"path": ["Lighting"], "class_name": "Lighting"}]),
        ["root_mismatch"],
    ),
    (
        "duplicate entry",
        snapshot(entries=[{"path": ["Workspace"], "class_name": "Workspace"}] * 2),
        ["duplicate_entry"],
    ),
    (
        "complete but shallower than its entries",
        snapshot(complete_depth=1),
        ["complete_depth_mismatch"],
    ),
    ("truncated may be shallow", snapshot(truncated=True, complete_depth=1), []),
]


@pytest.mark.parametrize(
    ("label", "snap", "expected"), STATE_CASES, ids=[c[0] for c in STATE_CASES]
)
def test_snapshot_consistency(label, snap, expected):
    assert sorted(v.code for v in check_project_state(snap)) == expected


def test_every_snapshot_code_is_exercised():
    assert {v.code for _, s, _ in STATE_CASES for v in check_project_state(s)} == set(
        STATE_VIOLATIONS
    )


@pytest.mark.parametrize(
    ("snap", "path", "expected"),
    [
        (snapshot(), ["Workspace", "Map", "Gone"], True),
        (snapshot(), ["Lighting", "X"], False),
        (snapshot(truncated=True, complete_depth=2), ["Workspace", "Map"], True),
        (snapshot(truncated=True, complete_depth=2), ["Workspace", "Map", "Deep"], False),
        (snapshot(truncated=True, complete_depth=0), ["Workspace"], False),
        (snapshot(truncated=True, complete_depth=16), ["Workspace", "A"], True),
    ],
    ids=[
        "complete",
        "uncaptured-root",
        "truncated-covered",
        "truncated-too-deep",
        "nothing-covered",
        "deep-coverage",
    ],
)
def test_absence_is_evidence_only_where_covered(snap, path, expected):
    assert absence_is_evidence(snap, path) is expected


# ------------------------------------------------------ the valid vectors, semantically


def _semantic_subjects():
    for rel in INDEX["valid"]:
        with open(EXAMPLES_DIR / rel, encoding="utf-8") as f:
            vector = json.load(f)
        if "generate" in vector:
            continue  # boundary vectors repeat one item and are not meant to be coherent
        yield rel, parse_strict(vector_text(vector))


SUBJECTS = list(_semantic_subjects())


@pytest.mark.parametrize(("rel", "message"), SUBJECTS, ids=[s[0] for s in SUBJECTS])
def test_valid_vectors_are_semantically_coherent(rel, message):
    payload = message["payload"]
    if message["kind"] == "response" and message.get("type") == "work.poll":
        work = payload.get("work", {})
        if work.get("type") == "edit.action":
            assert check_edit_action(work) == []
    elif message["kind"] == "request" and message.get("type") == "edit.result":
        assert check_edit_result(payload) == []
    elif message["kind"] == "request" and message.get("type") == "project.state":
        assert check_project_state(payload) == []
