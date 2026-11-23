"""Envelope and payload validation for what the plugin sends, and the responses to it.

The schemas in `packages/protocol/schemas/v1/` are authoritative (ADR-0006). The checks
here are the second implementation of them: the reference checks under
`packages/protocol/tests/` are test-only and `jsonschema` is a test dependency, so
production cannot reach either. The vectors in `packages/protocol/examples/v1/` are what
hold this to the schemas.

The API never sends a request and never receives a response, so only the five request
types are validated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_ID = 64
MAX_PATH_SEGMENTS = 16
MAX_SEGMENT = 100
MAX_OPERATIONS = 100
MAX_SNAPSHOT_ENTRIES = 2000
MAX_SNAPSHOT_ROOTS = 16
MAX_OUTPUT_LINES = 1000
MAX_OUTPUT_TEXT = 1000
MAX_ERROR_MESSAGE = 256
MAX_CLIENT_NAME = 64
MAX_CLIENT_VERSION = 32
MAX_SUPPORTED = 8
MAX_TIMESTAMP_MS = 3_600_000

REQUEST_TYPES = ("session.hello", "work.poll", "project.state", "edit.result", "playtest.report")

PROTOCOL_ERROR_CODES = (
    "invalid_message",
    "unknown_type",
    "unsupported_version",
    "unauthorized",
    "session_expired",
    "unknown_work",
    "result_conflict",
    "internal",
)

OUTCOMES = ("applied", "rejected", "partial", "indeterminate")
OP_STATUSES = ("applied", "failed", "skipped", "unknown")
PLAYTEST_OUTCOMES = ("completed", "timed_out", "aborted", "failed_to_start")
SNAPSHOT_REASONS = ("session_start", "after_action")
LOG_LEVELS = ("info", "warn", "error")

MATERIALS = (
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
)

# The order an action is reported in: everything applied, then the operation that ended
# it, then the ones never attempted (ADR-0011 section 9).
_STATUS_RANK = {"applied": 0, "failed": 1, "unknown": 1, "skipped": 2}


class MessageError(Exception):
    """A message the API refuses. `code` is one of `PROTOCOL_ERROR_CODES`."""

    def __init__(self, code: str, detail: str = "", *, retryable: bool = False) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.retryable = retryable


@dataclass(frozen=True)
class Request:
    """One validated plugin request."""

    type: str
    message_id: str
    session_id: str | None
    payload: dict[str, Any]
    minor: int


def _reject(where: str) -> MessageError:
    return MessageError("invalid_message", where)


def _text(value: object, where: str, maximum: int, minimum: int = 1) -> str:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise _reject(where)
    return value


def _flag(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise _reject(where)
    return value


def _whole(value: object, where: str, maximum: int, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _reject(where)
    if not minimum <= value <= maximum:
        raise _reject(where)
    return value


def _object(value: object, allowed: set[str], required: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _reject(where)
    keys = set(value)
    if not keys <= allowed:
        raise _reject(f"{where} has {sorted(keys - allowed)}")
    if not required <= keys:
        raise _reject(f"{where} lacks {sorted(required - keys)}")
    return value


def _array(value: object, where: str, maximum: int, minimum: int = 0) -> list[Any]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise _reject(where)
    return value


def _one_of(value: object, allowed: tuple[str, ...], where: str) -> str:
    if value not in allowed:
        raise _reject(where)
    return str(value)


def _path(value: object, where: str) -> list[str]:
    segments = _array(value, where, MAX_PATH_SEGMENTS, 1)
    return [_text(segment, f"{where} segment", MAX_SEGMENT) for segment in segments]


def _number(value: object, where: str, low: float, high: float) -> float:
    """A JSON number in bounds. `1.0` and `1` are the same number (the strict profile)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _reject(where)
    if not low <= value <= high:
        raise _reject(where)
    return float(value)


def _vector(value: object, where: str, low: float, high: float) -> None:
    axes = _object(value, {"x", "y", "z"}, {"x", "y", "z"}, where)
    for axis in ("x", "y", "z"):
        _number(axes[axis], f"{where}/{axis}", low, high)


def _entry_properties(value: object, where: str) -> None:
    """The allowlist is the one `set_property` uses, with the same value shapes.

    `messages/edit.action.json` states it; this is the API's copy of that statement,
    and the vectors are what keep the two the same.
    """
    body = _object(
        value,
        {
            "Anchored",
            "CanCollide",
            "Transparency",
            "Size",
            "Position",
            "Orientation",
            "Color",
            "Material",
        },
        set(),
        where,
    )
    for name in ("Anchored", "CanCollide"):
        if name in body:
            _flag(body[name], f"{where}/{name}")
    if "Transparency" in body:
        _number(body["Transparency"], f"{where}/Transparency", 0, 1)
    if "Size" in body:
        _vector(body["Size"], f"{where}/Size", 0.05, 2048)
    if "Position" in body:
        _vector(body["Position"], f"{where}/Position", -100000, 100000)
    if "Orientation" in body:
        _vector(body["Orientation"], f"{where}/Orientation", -360, 360)
    if "Color" in body:
        channels = _object(body["Color"], {"r", "g", "b"}, {"r", "g", "b"}, f"{where}/Color")
        for channel in ("r", "g", "b"):
            _number(channels[channel], f"{where}/Color/{channel}", 0, 1)
    if "Material" in body:
        material = _object(
            body["Material"], {"enum", "item"}, {"enum", "item"}, f"{where}/Material"
        )
        if material["enum"] != "Material":
            raise _reject(f"{where}/Material/enum")
        _one_of(material["item"], MATERIALS, f"{where}/Material/item")


def validate_request(message: dict[str, Any]) -> Request:
    """Validate one parsed request. Raises `MessageError` with the code to answer with."""
    if message.get("kind") != "request":
        raise _reject("/kind")
    message_type = message.get("type")
    if message_type not in REQUEST_TYPES:
        raise MessageError("unknown_type", "/type")
    is_hello = message_type == "session.hello"
    allowed = {"protocol_version", "kind", "type", "message_id", "sent_at", "payload"}
    required = {"protocol_version", "kind", "type", "message_id", "payload"}
    if not is_hello:
        allowed.add("session_id")
        required.add("session_id")
    _object(message, allowed, required, "/")
    version = _object(
        message["protocol_version"], {"major", "minor"}, {"major", "minor"}, "/protocol_version"
    )
    major = _whole(version["major"], "/protocol_version/major", 255, 1)
    minor = _whole(version["minor"], "/protocol_version/minor", 255)
    if major != 1 or (is_hello and minor != 0):
        raise MessageError("unsupported_version", "/protocol_version")
    message_id = _text(message["message_id"], "/message_id", MAX_ID)
    session_id = None if is_hello else _text(message["session_id"], "/session_id", MAX_ID)
    if "sent_at" in message:
        _whole(message["sent_at"], "/sent_at", 2**53)
    payload = _VALIDATORS[message_type](message["payload"])
    return Request(
        type=message_type,
        message_id=message_id,
        session_id=session_id,
        payload=payload,
        minor=minor,
    )


def _hello(payload: object) -> dict[str, Any]:
    body = _object(payload, {"client", "supported"}, {"client", "supported"}, "/payload")
    client = _object(body["client"], {"name", "version"}, {"name", "version"}, "/payload/client")
    _text(client["name"], "/payload/client/name", MAX_CLIENT_NAME)
    _text(client["version"], "/payload/client/version", MAX_CLIENT_VERSION)
    supported = _array(body["supported"], "/payload/supported", MAX_SUPPORTED, 1)
    for index, entry in enumerate(supported):
        where = f"/payload/supported/{index}"
        pair = _object(entry, {"major", "max_minor"}, {"major", "max_minor"}, where)
        _whole(pair["major"], f"{where}/major", 255, 1)
        _whole(pair["max_minor"], f"{where}/max_minor", 255)
    return body


def _poll(payload: object) -> dict[str, Any]:
    return _object(payload, set(), set(), "/payload")


def _snapshot(payload: object) -> dict[str, Any]:
    body = _object(
        payload,
        {
            "snapshot_id",
            "reason",
            "after_action_id",
            "roots",
            "complete_depth",
            "truncated",
            "entries",
        },
        {"snapshot_id", "reason", "roots", "complete_depth", "truncated", "entries"},
        "/payload",
    )
    _text(body["snapshot_id"], "/payload/snapshot_id", MAX_ID)
    reason = _one_of(body["reason"], SNAPSHOT_REASONS, "/payload/reason")
    if ("after_action_id" in body) != (reason == "after_action"):
        raise _reject("/payload/after_action_id")
    if "after_action_id" in body:
        _text(body["after_action_id"], "/payload/after_action_id", MAX_ID)
    for root in _array(body["roots"], "/payload/roots", MAX_SNAPSHOT_ROOTS):
        _text(root, "/payload/roots", MAX_SEGMENT)
    _whole(body["complete_depth"], "/payload/complete_depth", MAX_PATH_SEGMENTS)
    _flag(body["truncated"], "/payload/truncated")
    entries = _array(body["entries"], "/payload/entries", MAX_SNAPSHOT_ENTRIES)
    for index, entry in enumerate(entries):
        where = f"/payload/entries/{index}"
        node = _object(entry, {"path", "class_name", "properties"}, {"path", "class_name"}, where)
        _path(node["path"], f"{where}/path")
        _text(node["class_name"], f"{where}/class_name", MAX_ID)
        if "properties" in node:
            _entry_properties(node["properties"], f"{where}/properties")
    return body


def _edit_result(payload: object) -> dict[str, Any]:
    body = _object(
        payload,
        {"action_id", "outcome", "replayed", "operations"},
        {"action_id", "outcome", "operations"},
        "/payload",
    )
    _text(body["action_id"], "/payload/action_id", MAX_ID)
    outcome = _one_of(body["outcome"], OUTCOMES, "/payload/outcome")
    if "replayed" in body:
        _flag(body["replayed"], "/payload/replayed")
    operations = _array(body["operations"], "/payload/operations", MAX_OPERATIONS, 1)
    statuses: list[str] = []
    seen: set[str] = set()
    for index, operation in enumerate(operations):
        where = f"/payload/operations/{index}"
        node = _object(operation, {"op_id", "status", "path", "error"}, {"op_id", "status"}, where)
        op_id = _text(node["op_id"], f"{where}/op_id", MAX_ID)
        if op_id in seen:
            raise _reject(f"{where}/op_id is a duplicate")
        seen.add(op_id)
        status = _one_of(node["status"], OP_STATUSES, f"{where}/status")
        if "path" in node:
            _path(node["path"], f"{where}/path")
        if (status == "failed") != ("error" in node):
            raise _reject(f"{where}/error")
        if "error" in node:
            error = _object(
                node["error"], {"code", "message", "details"}, {"code", "message"}, f"{where}/error"
            )
            _text(error["message"], f"{where}/error/message", MAX_ERROR_MESSAGE)
            if not isinstance(error["code"], str) or error["code"] in PROTOCOL_ERROR_CODES:
                raise _reject(f"{where}/error/code")
        statuses.append(status)
    _check_outcome(outcome, statuses)
    return body


def _check_outcome(outcome: str, statuses: list[str]) -> None:
    """The outcome must agree with the statuses (ADR-0011 section 9)."""
    applied = statuses.count("applied")
    failed = statuses.count("failed")
    unknown = statuses.count("unknown")
    agrees = {
        "applied": applied == len(statuses),
        "rejected": failed == 1 and applied == 0 and set(statuses) <= {"failed", "skipped"},
        "partial": applied >= 1
        and failed == 1
        and set(statuses) <= {"applied", "failed", "skipped"},
        "indeterminate": unknown >= 1 and set(statuses) <= {"applied", "unknown", "skipped"},
    }[outcome]
    if not agrees or statuses != sorted(statuses, key=_STATUS_RANK.__getitem__):
        raise _reject("/payload/outcome")


def _playtest_report(payload: object) -> dict[str, Any]:
    body = _object(
        payload,
        {"playtest_id", "outcome", "duration_ms", "output", "output_truncated"},
        {"playtest_id", "outcome", "duration_ms"},
        "/payload",
    )
    _text(body["playtest_id"], "/payload/playtest_id", MAX_ID)
    _one_of(body["outcome"], PLAYTEST_OUTCOMES, "/payload/outcome")
    _whole(body["duration_ms"], "/payload/duration_ms", MAX_TIMESTAMP_MS)
    if "output_truncated" in body:
        _flag(body["output_truncated"], "/payload/output_truncated")
    if "output" in body:
        lines = _array(body["output"], "/payload/output", MAX_OUTPUT_LINES)
        for index, line in enumerate(lines):
            where = f"/payload/output/{index}"
            node = _object(line, {"t_ms", "level", "text"}, {"t_ms", "level", "text"}, where)
            _whole(node["t_ms"], f"{where}/t_ms", MAX_TIMESTAMP_MS)
            _one_of(node["level"], LOG_LEVELS, f"{where}/level")
            _text(node["text"], f"{where}/text", MAX_OUTPUT_TEXT)
    return body


_VALIDATORS = {
    "session.hello": _hello,
    "work.poll": _poll,
    "project.state": _snapshot,
    "edit.result": _edit_result,
    "playtest.report": _playtest_report,
}


def ok_response(
    message_type: str,
    message_id: str,
    correlation_id: str,
    session_id: str,
    payload: dict[str, Any],
    *,
    minor: int = 0,
) -> dict[str, Any]:
    """A `status: ok` response envelope."""
    return {
        "protocol_version": {"major": 1, "minor": minor},
        "kind": "response",
        "type": message_type,
        "message_id": message_id,
        "correlation_id": correlation_id,
        "session_id": session_id,
        "status": "ok",
        "payload": payload,
    }


def error_response(
    message_type: str | None,
    message_id: str,
    correlation_id: str | None,
    session_id: str | None,
    code: str,
    text: str,
    *,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
    minor: int = 0,
) -> dict[str, Any]:
    """An error response. `type` and `session_id` are left out when there is none to give."""
    payload: dict[str, Any] = {
        "code": code,
        "message": text[:MAX_ERROR_MESSAGE],
        "retryable": retryable,
    }
    if details:
        payload["details"] = details
    envelope: dict[str, Any] = {
        "protocol_version": {"major": 1, "minor": minor},
        "kind": "response",
        "message_id": message_id,
        "status": "error",
        "payload": payload,
    }
    if message_type is not None:
        envelope["type"] = message_type
    if correlation_id is not None:
        envelope["correlation_id"] = correlation_id
    if session_id is not None:
        envelope["session_id"] = session_id
    return envelope
