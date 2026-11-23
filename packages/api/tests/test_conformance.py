"""The API's own parser and validator, held to the protocol's vectors.

`packages/protocol/examples/v1/` is the conformance suite for *every* implementation
(docs/protocol/README.md, *Conformance*). The reference checks under
`packages/protocol/tests/` are test-only, so the API has its own parser and validator;
these tests are what keep the two from drifting.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from api.json_profile import ProfileError, parse_strict
from api.messages import REQUEST_TYPES, MessageError, validate_request

EXAMPLES = Path(__file__).resolve().parents[2] / "protocol" / "examples" / "v1"
INDEX = json.loads((EXAMPLES / "index.json").read_text(encoding="utf-8"))


def _vectors(group: str) -> list[tuple[str, dict]]:
    return [(rel, json.loads((EXAMPLES / rel).read_text(encoding="utf-8"))) for rel in INDEX[group]]


def _expand(vector: dict) -> dict:
    """Apply a vector's `generate` recipe, as examples/v1/README.md specifies."""
    message = copy.deepcopy(vector["message"])
    for step in vector.get("generate", []):
        *parents, last = step["at"][1:].split("/")
        node = message
        for token in parents:
            node = node[int(token)] if isinstance(node, list) else node[token]
        key = int(last) if isinstance(node, list) else last
        if "repeat" in step:
            node[key] = [copy.deepcopy(step["repeat"]) for _ in range(step["count"])]
        else:
            node[key] = step["fill"] * step["length"]
    return message


PARSE = _vectors("parse")
VALID = _vectors("valid")
INVALID = _vectors("invalid")


def _is_plugin_request(vector: dict) -> bool:
    message = vector.get("message")
    return (
        isinstance(message, dict)
        and message.get("kind") == "request"
        and message.get("type") in REQUEST_TYPES
    )


# ------------------------------------------------------------------ the strict profile


@pytest.mark.parametrize(("rel", "vector"), PARSE, ids=[rel for rel, _ in PARSE])
def test_parse_vectors(rel, vector):
    expect = vector["expect"]
    raw = vector.get("message_raw")
    if raw is None:
        raw = json.dumps(_expand(vector), ensure_ascii=False, separators=(",", ":"))
    if expect["valid"]:
        parse_strict(raw)
        return
    with pytest.raises(ProfileError) as caught:
        parse_strict(raw)
    assert caught.value.reason == expect["reason"], rel


def test_every_parse_vector_is_exercised():
    assert len(PARSE) == 42


# ------------------------------------------------------------------ message validation


@pytest.mark.parametrize(
    ("rel", "vector"),
    [(rel, v) for rel, v in VALID if _is_plugin_request(v)],
    ids=[rel for rel, v in VALID if _is_plugin_request(v)],
)
def test_valid_requests_are_accepted(rel, vector):
    request = validate_request(parse_strict(json.dumps(_expand(vector))))
    assert request.type == vector["message"]["type"], rel


@pytest.mark.parametrize(
    ("rel", "vector"),
    [(rel, v) for rel, v in INVALID if _is_plugin_request(v)],
    ids=[rel for rel, v in INVALID if _is_plugin_request(v)],
)
def test_invalid_requests_are_refused(rel, vector):
    with pytest.raises((MessageError, ProfileError)):
        validate_request(parse_strict(json.dumps(_expand(vector))))


def test_the_suite_actually_covers_requests():
    """Guard against the filter above silently matching nothing."""
    assert sum(1 for _, v in VALID if _is_plugin_request(v)) >= 15
    assert sum(1 for _, v in INVALID if _is_plugin_request(v)) >= 40
