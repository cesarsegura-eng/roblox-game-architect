"""Reference implementation of the protocol's strict JSON profile. Test-only.

The profile is specified in docs/protocol/README.md and ADR-0009. It exists because the
standard parsers disagree about inputs that matter here: Python's json module accepts NaN,
Infinity and 1e999, keeps the last of two duplicate keys, and accepts lone surrogate escapes;
Luau's HttpService:JSONDecode is undocumented on all of these and silently drops null.

A message that does not parse under this profile never reaches schema validation. Every
implementation (this one, the future API parser, and the Studio plugin's strict Luau parser)
must give the same accept/reject answer on the vectors in examples/v1/. The Studio plugin's
parser and schema validator pass the shared suites under Lute; installed Studio runtime
conformance remains NOT verified.
"""

import json
import math
import re

MAX_MESSAGE_BYTES = 1_048_576
MAX_JSON_DEPTH = 12
MAX_INTEGER = 2**53

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


class ProfileError(ValueError):
    """The input is not a message under the strict JSON profile."""

    def __init__(self, reason, detail=""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def _reject_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ProfileError("duplicate_key", key)
        seen[key] = value
    return seen


def _reject_constant(name):
    raise ProfileError("non_finite", name)


def _parse_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise ProfileError("non_finite", text)
    return value


def _parse_int(text):
    try:
        value = int(text)
    except ValueError as exc:  # Python refuses absurdly long digit strings
        raise ProfileError("integer_out_of_range", text[:20]) from exc
    if abs(value) > MAX_INTEGER:
        raise ProfileError("integer_out_of_range", text)
    return value


def _check_tree(value):
    """Walk the parsed value: top level, null, surrogates and nesting depth."""
    if not isinstance(value, dict):
        raise ProfileError("not_object")
    stack = [(value, 1)]
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


def parse_strict(data):
    """Parse a message. Accepts str or bytes; raises ProfileError with a closed reason."""
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
    if text.startswith("﻿"):
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
