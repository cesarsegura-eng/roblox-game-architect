"""Reference checks for the rules JSON Schema cannot express. Test-only.

This is an executable specification of ADR-0008, not an implementation. `packages/sandbox`
is the single authority on scope and ordering (ARCHITECTURE.md section 2) and will implement
these rules itself against shared vectors; nothing here is importable by production code.

Every check is decidable from the message alone, without the state of the place: that is the
point of the flat operation list.
"""

from dataclasses import dataclass

# The closed list of violation codes. Kept here so the tests can assert on it.
ACTION_VIOLATIONS = (
    "duplicate_op_id",
    "scope_violation",
    "forward_reference",
    "stale_target",
    "duplicate_target",
    "invalid_reparent",
    "created_class_mismatch",
)
RESULT_VIOLATIONS = ("duplicate_op_id", "outcome_mismatch", "error_mismatch", "result_mismatch")
STATE_VIOLATIONS = (
    "reason_mismatch",
    "root_mismatch",
    "duplicate_entry",
    "complete_depth_mismatch",
)


@dataclass(frozen=True)
class Violation:
    code: str
    index: int
    detail: str = ""


def is_prefix(prefix, path):
    return path[: len(prefix)] == prefix


def covers(declared_scope, path, extent):
    """Is the effect (path, extent) inside the declared scope?

    A subtree entry covers its path and everything under it. A self entry covers exactly its
    own path, and only effects of extent self.
    """
    for entry in declared_scope:
        entry_path = tuple(entry["path"])
        if not is_prefix(entry_path, path):
            continue
        if entry["extent"] == "subtree":
            return True
        if entry_path == path and extent == "self":
            return True
    return False


class _Walk:
    """State of the single in-order pass over an action's operations."""

    def __init__(self, declared_scope):
        self.scope = declared_scope
        self.known_class = {}  # paths brought into being by this action -> class
        self.stale = []  # old paths of deleted or moved subtrees
        self.addressed = []  # every path an earlier operation named
        self.violations = []

    def violation(self, code, index, detail=""):
        self.violations.append(Violation(code, index, detail))

    def address(self, ref, index):
        """An operation names an existing (or earlier-created) instance."""
        path = tuple(ref["path"])
        if any(is_prefix(old, path) for old in self.stale):
            self.violation("stale_target", index, "/".join(path))
        known = self.known_class.get(path)
        if known is not None and known != ref["expect_class"]:
            self.violation("created_class_mismatch", index, "/".join(path))
        return path

    def touch(self, path, extent, index):
        if not covers(self.scope, path, extent):
            self.violation("scope_violation", index, f"{'/'.join(path)} ({extent})")

    def bring_into_being(self, path, class_name, before, index):
        """A create or the destination of a move: the path must be new and never named before."""
        if path in self.known_class:
            self.violation("duplicate_target", index, "/".join(path))
        if any(is_prefix(old, path) for old in self.stale):
            self.violation("stale_target", index, "/".join(path))
        # A path named earlier while it was still live and has since been deleted or moved is
        # the stale case above, not a forward reference.
        live_names = [n for n in before if not any(is_prefix(old, n) for old in self.stale)]
        if any(is_prefix(path, named) for named in live_names):
            self.violation("forward_reference", index, "/".join(path))
        self.known_class[path] = class_name


def check_edit_action(action):
    """Scope and ordering rules R1-R4 of ADR-0008. Returns a list of Violation."""
    walk = _Walk(action["declared_scope"])
    seen_ids = set()
    for index, operation in enumerate(action["operations"]):
        if operation["op_id"] in seen_ids:
            walk.violation("duplicate_op_id", index, operation["op_id"])
        seen_ids.add(operation["op_id"])
        before = list(walk.addressed)
        kind = operation["op"]
        if kind == "create_instance":
            parent = walk.address(operation["parent"], index)
            walk.addressed.append(parent)
            new_path = (*parent, operation["name"])
            walk.touch(new_path, "self", index)
            walk.bring_into_being(new_path, operation["class_name"], before, index)
        elif kind in ("set_property", "set_script_source"):
            target = walk.address(operation["target"], index)
            walk.addressed.append(target)
            walk.touch(target, "self", index)
        elif kind == "delete_instance":
            target = walk.address(operation["target"], index)
            walk.addressed.append(target)
            walk.touch(target, "subtree", index)
            walk.stale.append(target)
        elif kind == "reparent":
            target = walk.address(operation["target"], index)
            new_parent = walk.address(operation["new_parent"], index)
            walk.addressed.extend([target, new_parent])
            if len(target) < 2 or is_prefix(target, new_parent) or new_parent == target[:-1]:
                walk.violation("invalid_reparent", index, "/".join(target))
                continue
            destination = (*new_parent, target[-1])
            walk.touch(target, "subtree", index)
            walk.touch(destination, "subtree", index)
            walk.bring_into_being(destination, operation["target"]["expect_class"], before, index)
            walk.stale.append(target)
    return walk.violations


# The order an action is reported in: everything applied, then the one operation that
# ended it (failed, or unknown when its effect could not be determined), then the ones
# never attempted. ADR-0011 section 9: failed and unknown never share a result, which
# the per-outcome status sets below enforce, so they share a rank here.
_STATUS_RANK = {"applied": 0, "failed": 1, "unknown": 1, "skipped": 2}


def check_edit_result(result, action=None):
    """Consistency of an edit.result, and optionally of its match with the action."""
    violations = []
    operations = result["operations"]
    statuses = [op["status"] for op in operations]
    ids = [op["op_id"] for op in operations]
    if len(set(ids)) != len(ids):
        violations.append(Violation("duplicate_op_id", 0))
    for index, op in enumerate(operations):
        if (op["status"] == "failed") != ("error" in op):
            violations.append(Violation("error_mismatch", index, op["op_id"]))
    outcome = result["outcome"]
    applied, failed = statuses.count("applied"), statuses.count("failed")
    unknown = statuses.count("unknown")
    expected_ok = {
        "applied": applied == len(statuses),
        "rejected": failed >= 1 and applied == 0 and set(statuses) <= {"failed", "skipped"},
        "partial": applied >= 1
        and failed >= 1
        and set(statuses) <= {"applied", "failed", "skipped"},
        "indeterminate": unknown >= 1 and set(statuses) <= {"applied", "unknown", "skipped"},
    }[outcome]
    ordered = statuses == sorted(statuses, key=_STATUS_RANK.__getitem__)
    if not expected_ok or (outcome in ("rejected", "partial") and failed != 1) or not ordered:
        violations.append(Violation("outcome_mismatch", 0, outcome))
    if action is not None and (
        result["action_id"] != action["action_id"]
        or ids != [op["op_id"] for op in action["operations"]]
    ):
        violations.append(Violation("result_mismatch", 0))
    return violations


def check_project_state(snapshot):
    """Cross-field rules of a project.state payload."""
    violations = []
    has_action = "after_action_id" in snapshot
    if has_action != (snapshot["reason"] == "after_action"):
        violations.append(Violation("reason_mismatch", 0, snapshot["reason"]))
    roots = set(snapshot["roots"])
    seen = set()
    max_depth = 0
    for index, entry in enumerate(snapshot["entries"]):
        path = tuple(entry["path"])
        if path[0] not in roots:
            violations.append(Violation("root_mismatch", index, path[0]))
        if path in seen:
            violations.append(Violation("duplicate_entry", index, "/".join(path)))
        seen.add(path)
        max_depth = max(max_depth, len(path))
    if not snapshot["truncated"] and snapshot["complete_depth"] < max_depth:
        violations.append(Violation("complete_depth_mismatch", 0))
    return violations


def absence_is_evidence(snapshot, path):
    """May the absence of `path` from this snapshot be read as 'it did not exist'?

    Only where the snapshot demonstrably covers the path: a root it captured, and either a
    snapshot that was not truncated or a depth at or below complete_depth. Anything else is
    unknown, and unknown is never evidence of absence.
    """
    path = tuple(path)
    if path[0] not in snapshot["roots"]:
        return False
    return (not snapshot["truncated"]) or len(path) <= snapshot["complete_depth"]
