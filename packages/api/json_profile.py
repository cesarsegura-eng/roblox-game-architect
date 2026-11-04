"""The strict JSON profile, for production use (ADR-0009, docs/protocol/README.md).

`packages/protocol/tests/protocol_strict_json.py` is the reference implementation and is
test-only: nothing there is importable from here. This is the second implementation the
record calls for, and the vectors in `packages/protocol/examples/v1/parse/` are what hold
the two to the same accept/reject answer.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

MAX_MESSAGE_BYTES = 1_048_576
MAX_JSON_DEPTH = 12
MAX_INTEGER = 2**53

# The closed list of reasons a message can fail the profile.
REASONS = (
    "invalid_utf8",
    "size_exceeded",
    "invalid_json",
    "not_object",
    "duplicate_key",
    "null_value",
    "non_finite",
    "integer_out_of_range",
    "lone_surrogate",
    "depth_exceeded",
)

_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
_BOM = "﻿"


class ProfileError(ValueError):
    """The input is not a message under the strict JSON profile."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ProfileError("duplicate_key", key)
        seen[key] = value
    return seen


def _reject_constant(name: str) -> float:
    raise ProfileError("non_finite", name)


def _parse_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ProfileError("non_finite", text)
    return value


def _parse_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:  # Python refuses absurdly long digit strings
        raise ProfileError("integer_out_of_range", text[:20]) from exc
    if abs(value) > MAX_INTEGER:
        raise ProfileError("integer_out_of_range", text)
    return value


def _check_tree(value: object) -> None:
    """Walk the parsed value: top level, null, lone surrogates and nesting depth."""
    if not isinstance(value, dict):
        raise ProfileError("not_object")
    stack: list[tuple[object, int]] = [(value, 1)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, dict):
            if depth > MAX_JSON_DEPTH:
                raise ProfileError("depth_exceeded")
            for key, child in node.items():
                if _LONE_SURROGATE.search(key):
                    raise ProfileError("lone_surrogate")
                stack.append((child, depth + 1))
        elif isinstance(node, list):
            if depth > MAX_JSON_DEPTH:
                raise ProfileError("depth_exceeded")
            stack.extend((child, depth + 1) for child in node)
        elif node is None:
            raise ProfileError("null_value")
        elif isinstance(node, str) and _LONE_SURROGATE.search(node):
            raise ProfileError("lone_surrogate")


def parse_strict(data: str | bytes) -> dict[str, Any]:
    """Parse one message. Raises `ProfileError` with a reason from `REASONS`."""
    if isinstance(data, str):
        try:
            raw = data.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ProfileError("invalid_utf8") from exc
    else:
        raw = bytes(data)
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProfileError("size_exceeded", str(len(raw)))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProfileError("invalid_utf8") from exc
    if text.startswith(_BOM):
        raise ProfileError("invalid_json", "byte order mark")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
            parse_float=_parse_float,
            parse_int=_parse_int,
        )
    except ProfileError:
        raise
    except RecursionError as exc:
        raise ProfileError("depth_exceeded") from exc
    except ValueError as exc:
        raise ProfileError("invalid_json", str(exc)) from exc
    _check_tree(value)
    return value


def serialise(message: dict[str, Any]) -> bytes:
    """Encode a message the profile would accept. Compact, UTF-8, no BOM."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
