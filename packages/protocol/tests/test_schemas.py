"""Contract tests for packages/protocol: the schemas, the audit of their subset, the vectors.

What these tests establish, and what they do not:

* The Python side is verified: the schemas are valid Draft 2020-12, every one stays inside the
  closed subset a hand-written Luau validator could implement, and every vector in
  examples/v1/ gives the declared result under the reference stages.
* Luau conformance is SPECIFIED, NOT VERIFIED. No Luau validator or parser exists yet (ADR-0009).
  The vectors are the conformance suite it must pass when it does.
"""

import json
import re

import pytest
from jsonschema import Draft202012Validator
from protocol_schemas import (
    BASE,
    DIALECT,
    EXAMPLES_DIR,
    ROOT_ONLY,
    SCHEMA_DIR,
    audit_file,
    audit_graph,
    const_properties,
    errors_against,
    expand_generate,
    load_files,
    load_version,
    message_depth,
    message_types,
    operation_branches,
    pointer_get,
    pointer_of,
    select_envelope,
    select_payload_schema,
    untrusted_locations,
    validate_message,
    validate_text,
    vector_message,
    vector_text,
)
from protocol_strict_json import (
    MAX_INTEGER,
    MAX_JSON_DEPTH,
    MAX_MESSAGE_BYTES,
    REASONS,
    parse_strict,
)

FILES = load_files()
INDEX = json.loads((EXAMPLES_DIR / "index.json").read_text(encoding="utf-8"))

PROTOCOL_ERROR_CODES = [
    "invalid_message",
    "unknown_type",
    "unsupported_version",
    "unauthorized",
    "session_expired",
    "unknown_work",
    "result_conflict",
    "internal",
]
OPERATION_ERROR_CODES = [
    "target_not_found",
    "parent_not_found",
    "ambiguous_target",
    "class_mismatch",
    "name_conflict",
    "invalid_reparent",
    "property_unavailable",
    "operation_failed",
]
ALLOWLIST = {
    "Anchored",
    "CanCollide",
    "Transparency",
    "Size",
    "Position",
    "Orientation",
    "Color",
    "Material",
}
PART_CLASSES = ["Part", "WedgePart"]
SCRIPT_CLASSES = ["Script", "LocalScript", "ModuleScript"]
CREATABLE_CLASSES = [
    "Folder",
    "Model",
    "Part",
    "WedgePart",
    "Script",
    "ModuleScript",
    "LocalScript",
]


def node_at(rel, pointer):
    return pointer_get(FILES[rel], pointer)


# ------------------------------------------------------------------- the schema set


def test_version_file_describes_the_schema_set():
    version = load_version()
    assert (version["major"], version["minor"]) == (1, 0)
    assert version["types"] == [
        "session.hello",
        "work.poll",
        "project.state",
        "edit.result",
        "playtest.report",
    ]
    assert node_at("common.json", "/$defs/protocol_version/properties/major")["const"] == 1


@pytest.mark.parametrize("rel", sorted(FILES))
def test_schema_is_valid_draft_2020_12(rel):
    Draft202012Validator.check_schema(FILES[rel])


@pytest.mark.parametrize("rel", sorted(FILES))
def test_schema_stays_inside_the_permitted_subset(rel):
    assert audit_file(rel, FILES[rel]) == []


def test_schema_graph_is_sound():
    """Every $ref resolves inside the set, no cycles, no orphans, no dead definitions, every
    oneOf is discriminated by a const, and no property names a provider or a secret."""
    assert audit_graph(FILES, message_types()) == []


def test_every_dispatchable_message_has_a_schema():
    for message_type in message_types():
        for kind in ("request", "response"):
            assert f"messages/{message_type}.{kind}.json" in FILES
    assert {"envelope.request.json", "envelope.response.json", "envelope.error.json"} <= set(FILES)
    assert {"envelope.hello.request.json", "envelope.hello.response.json"} <= set(FILES)


def test_deepest_message_is_well_inside_the_parser_depth_limit():
    deepest = 0
    for message_type in message_types():
        for kind, status in (("request", "ok"), ("response", "ok"), ("response", "error")):
            deepest = max(deepest, message_depth(FILES, message_type, kind, status))
    assert deepest <= 8 < MAX_JSON_DEPTH


def test_untrusted_fields_are_exactly_the_documented_ones():
    """Project and playtest text carries x-untrusted. It is a marker for consumers, not a
    control: it does not remove the risk of prompt injection (docs/protocol/README.md)."""
    assert untrusted_locations(FILES) == {
        ("common.json", "/$defs/segment"),
        ("messages/playtest.report.request.json", "/$defs/output_line/properties/text"),
    }


def test_no_schema_uses_x_since_yet():
    """1.0 is the baseline: x-since exists, is audited, and nothing is annotated with it."""
    assert not any('"x-since"' in json.dumps(schema) for schema in FILES.values())


# --------------------------------------------------------- limits are explicit and locked

LIMITS = [
    ("common.json", "/$defs/id", {"minLength": 1, "maxLength": 64}),
    ("common.json", "/$defs/segment", {"minLength": 1, "maxLength": 100}),
    ("common.json", "/$defs/path", {"minItems": 1, "maxItems": 16}),
    ("common.json", "/$defs/class_name", {"maxLength": 64}),
    ("common.json", "/$defs/service_name", {"maxLength": 100}),
    ("common.json", "/$defs/timestamp_ms", {"minimum": 0, "maximum": 2**53 - 1}),
    ("common.json", "/$defs/unit_interval", {"minimum": 0, "maximum": 1}),
    ("common.json", "/$defs/vector3_size/properties/x", {"minimum": 0.05, "maximum": 2048}),
    ("common.json", "/$defs/vector3_size/properties/y", {"minimum": 0.05, "maximum": 2048}),
    ("common.json", "/$defs/vector3_size/properties/z", {"minimum": 0.05, "maximum": 2048}),
    (
        "common.json",
        "/$defs/vector3_position/properties/x",
        {"minimum": -100000, "maximum": 100000},
    ),
    (
        "common.json",
        "/$defs/vector3_position/properties/y",
        {"minimum": -100000, "maximum": 100000},
    ),
    (
        "common.json",
        "/$defs/vector3_position/properties/z",
        {"minimum": -100000, "maximum": 100000},
    ),
    ("common.json", "/$defs/color3/properties/r", {"minimum": 0, "maximum": 1}),
    ("common.json", "/$defs/color3/properties/g", {"minimum": 0, "maximum": 1}),
    ("common.json", "/$defs/color3/properties/b", {"minimum": 0, "maximum": 1}),
    ("error.protocol.json", "/properties/message", {"minLength": 1, "maxLength": 256}),
    ("error.protocol.json", "/properties/details/properties/supported", {"maxItems": 8}),
    (
        "error.protocol.json",
        "/properties/details/properties/retry_after_ms",
        {"minimum": 0, "maximum": 3600000},
    ),
    ("error.operation.json", "/properties/message", {"minLength": 1, "maxLength": 256}),
    (
        "messages/session.hello.request.json",
        "/properties/supported",
        {"minItems": 1, "maxItems": 8},
    ),
    (
        "messages/session.hello.request.json",
        "/properties/client/properties/name",
        {"maxLength": 64},
    ),
    (
        "messages/session.hello.request.json",
        "/properties/client/properties/version",
        {"maxLength": 32},
    ),
    ("messages/edit.action.json", "/properties/operations", {"minItems": 1, "maxItems": 100}),
    ("messages/edit.action.json", "/properties/declared_scope", {"minItems": 1, "maxItems": 32}),
    (
        "messages/edit.action.json",
        "/$defs/set_script_source/properties/source",
        {"maxLength": 100000},
    ),
    (
        "messages/playtest.request.json",
        "/properties/duration_limit_s",
        {"minimum": 1, "maximum": 600},
    ),
    ("messages/playtest.request.json", "/properties/collect", {"maxItems": 2}),
    ("messages/project.state.request.json", "/properties/entries", {"maxItems": 2000}),
    ("messages/project.state.request.json", "/properties/roots", {"maxItems": 16}),
    (
        "messages/project.state.request.json",
        "/properties/complete_depth",
        {"minimum": 0, "maximum": 16},
    ),
    (
        "messages/edit.result.request.json",
        "/properties/operations",
        {"minItems": 1, "maxItems": 100},
    ),
    ("messages/playtest.report.request.json", "/properties/output", {"maxItems": 1000}),
    (
        "messages/playtest.report.request.json",
        "/$defs/output_line/properties/text",
        {"maxLength": 1000},
    ),
]


@pytest.mark.parametrize(("rel", "pointer", "expected"), LIMITS, ids=lambda v: str(v)[:60])
def test_documented_limit_matches_the_schema(rel, pointer, expected):
    node = node_at(rel, pointer)
    assert {key: node.get(key) for key in expected} == expected


def test_parser_limits_are_the_documented_ones():
    assert MAX_MESSAGE_BYTES == 1_048_576
    assert MAX_JSON_DEPTH == 12
    assert MAX_INTEGER == 2**53


# ------------------------------------------------------------------ error taxonomy


def test_error_code_lists_are_closed_and_separate():
    protocol = node_at("error.protocol.json", "/properties/code")["enum"]
    operation = node_at("error.operation.json", "/properties/code")["enum"]
    assert protocol == PROTOCOL_ERROR_CODES
    assert operation == OPERATION_ERROR_CODES
    assert not set(protocol) & set(operation)
    assert "session_expired" in protocol
    assert {"name_conflict", "class_mismatch"} <= set(operation)


def test_error_details_are_closed_and_free_of_free_form_data():
    protocol_details = node_at("error.protocol.json", "/properties/details")
    operation_details = node_at("error.operation.json", "/properties/details")
    assert set(protocol_details["properties"]) == {"supported", "retry_after_ms"}
    assert set(operation_details["properties"]) == {"path"}
    assert protocol_details["additionalProperties"] is False
    assert operation_details["additionalProperties"] is False


# ----------------------------------------------------- allowlist and script behaviour


def test_property_allowlist_is_exactly_the_documented_set():
    allowlist = operation_branches(FILES)
    assert set(allowlist) == ALLOWLIST
    assert all(entry["classes"] == PART_CLASSES for entry in allowlist.values())


def test_property_allowlist_is_the_single_source_for_snapshots_too():
    """project.state reports the same properties, with the same value shapes, as set_property."""
    snapshot = node_at("messages/project.state.request.json", "/$defs/entry_properties")
    assert set(snapshot["properties"]) == ALLOWLIST
    allowlist = operation_branches(FILES)
    for name, schema in snapshot["properties"].items():
        assert schema == allowlist[name]["value"], name


def test_nothing_that_changes_names_parents_or_activates_scripts_is_expressible():
    text = json.dumps(FILES)
    for forbidden in ("Enabled", "Disabled", "RunContext", "enable_script", "rename_instance"):
        assert forbidden not in text, forbidden
    assert "Name" not in operation_branches(FILES)
    assert "Parent" not in operation_branches(FILES)


def test_class_enums_are_the_documented_ones():
    common = FILES["common.json"]["$defs"]
    assert common["creatable_class"]["enum"] == CREATABLE_CLASSES
    assert common["script_class"]["enum"] == SCRIPT_CLASSES
    assert common["part_class"]["enum"] == PART_CLASSES


def test_script_creation_and_source_are_separate_operations():
    defs = FILES["messages/edit.action.json"]["$defs"]
    assert "source" not in defs["create_instance"]["properties"]
    assert "enabled" not in defs["create_instance"]["properties"]
    assert defs["create_instance"]["properties"]["class_name"]["$ref"].endswith("/creatable_class")
    target = defs["set_script_source"]["properties"]["target"]["properties"]["expect_class"]
    assert target["$ref"].endswith("/script_class")


def test_hello_framing_is_frozen_at_one_point_zero():
    hello = node_at("common.json", "/$defs/hello_protocol_version")["properties"]
    assert hello["major"]["const"] == 1
    assert hello["minor"]["const"] == 0
    request = FILES["envelope.hello.request.json"]["properties"]["protocol_version"]
    assert request["$ref"].endswith("/hello_protocol_version")
    for branch in FILES["envelope.hello.response.json"]["oneOf"]:
        assert branch["properties"]["protocol_version"]["$ref"].endswith("/hello_protocol_version")


# ------------------------------------------------------------ the audit catches things


def synthetic(body, rel="messages/synthetic.json", **extra):
    return rel, {"$schema": DIALECT, "$id": BASE + rel, **body, **extra}


def closed(properties, required=()):
    node = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        node["required"] = list(required)
    return node


STRING = {"type": "string", "maxLength": 5}
BAD_SCHEMAS = [
    ("pattern", closed({"a": {**STRING, "pattern": "^a"}}), "outside the permitted subset"),
    ("format", closed({"a": {**STRING, "format": "uuid"}}), "outside the permitted subset"),
    ("allOf", {"allOf": [closed({})]}, "outside the permitted subset"),
    ("anyOf", {"anyOf": [closed({}), closed({})]}, "outside the permitted subset"),
    ("not", {"not": closed({})}, "outside the permitted subset"),
    ("if", {"if": closed({}), "then": closed({})}, "outside the permitted subset"),
    (
        "uniqueItems",
        closed({"a": {"type": "array", "maxItems": 2, "items": STRING, "uniqueItems": True}}),
        "outside the permitted subset",
    ),
    (
        "multipleOf",
        closed({"a": {"type": "integer", "minimum": 0, "maximum": 9, "multipleOf": 3}}),
        "outside the permitted subset",
    ),
    ("patternProperties", closed({}) | {"patternProperties": {}}, "outside the permitted subset"),
    ("anchor", closed({}) | {"$anchor": "a"}, "outside the permitted subset"),
    ("dynamicRef", closed({"a": {"$dynamicRef": "#x"}}), "outside the permitted subset"),
    ("null type", closed({"a": {"type": "null"}}), "no null"),
    ("type union", closed({"a": {"type": ["string", "null"]}}), "no null"),
    ("open object", {"type": "object", "properties": {}}, "not closed"),
    ("additionalProperties true", {**closed({}), "additionalProperties": True}, "not closed"),
    ("unbounded string", closed({"a": {"type": "string"}}), "without maxLength"),
    ("unbounded array", closed({"a": {"type": "array", "items": STRING}}), "without maxItems"),
    (
        "array without items",
        closed({"a": {"type": "array", "maxItems": 3}}),
        "without an items schema",
    ),
    ("number without bounds", closed({"a": {"type": "number"}}), "without minimum and maximum"),
    (
        "integer without upper bound",
        closed({"a": {"type": "integer", "minimum": 0}}),
        "without minimum and maximum",
    ),
    (
        "integer beyond 2^53",
        closed({"a": {"type": "integer", "minimum": 0, "maximum": 2**60}}),
        "within +/- 2^53",
    ),
    (
        "min above max",
        closed({"a": {"type": "integer", "minimum": 5, "maximum": 1}}),
        "minimum exceeds maximum",
    ),
    ("required not declared", closed({"a": STRING}, ["b"]), "not declared"),
    ("unknown annotation", closed({"a": {**STRING, "x-foo": True}}), "is not one of"),
    (
        "x-untrusted false",
        closed({"a": {**STRING, "x-untrusted": False}}),
        "x-untrusted must be true",
    ),
    (
        "x-untrusted on integer",
        closed({"a": {"type": "integer", "minimum": 0, "maximum": 1, "x-untrusted": True}}),
        "x-untrusted must be true",
    ),
    ("x-since malformed", closed({"a": {**STRING, "x-since": "1"}}), "MAJOR.MINOR"),
    (
        "x-since from the future",
        closed({"a": {**STRING, "x-since": "1.1"}}, []),
        "newer than version.json",
    ),
    (
        "x-since on a required property",
        closed({"a": {**STRING, "x-since": "1.0"}}, ["a"]),
        "may only sit on",
    ),
    (
        "ref with siblings",
        closed({"a": {"$ref": "#/$defs/x", "description": "d"}}),
        "sibling keywords",
    ),
    ("nested $defs", closed({"a": {**STRING, "$defs": {}}}), "only allowed at the file root"),
    ("typeless schema", closed({"a": {"description": "anything goes"}}), "no type"),
    ("oneOf with one branch", {"oneOf": [closed({})]}, "at least two branches"),
    (
        "oneOf beside type",
        {"type": "object", "oneOf": [closed({}), closed({})]},
        "oneOf may not be combined",
    ),
    ("float const", closed({"a": {"type": "integer", "const": 1.5}}), "integer const"),
    (
        "object const",
        closed({"a": {"type": "string", "const": {"x": 1}}}),
        "const must be a string",
    ),
    (
        "integer enum",
        closed({"a": {"type": "string", "enum": [1, 2]}}),
        "non-empty list of unique strings",
    ),
    ("duplicate enum", closed({"a": {"type": "string", "enum": ["a", "a"]}}), "unique strings"),
    (
        "string min above max",
        closed({"a": {"type": "string", "minLength": 9, "maxLength": 3}}),
        "minLength exceeds",
    ),
    (
        "keyword on the wrong type",
        closed({"a": {"type": "boolean", "maxLength": 3}}),
        "do not apply to type",
    ),
    (
        "wrong dialect",
        closed({}) | {"$schema": "http://json-schema.org/draft-07/schema#"},
        "Draft 2020-12",
    ),
    ("wrong $id", closed({}) | {"$id": "https://example.com/x.json"}, "$id must be"),
]


@pytest.mark.parametrize(
    ("label", "body", "expected"), BAD_SCHEMAS, ids=[b[0] for b in BAD_SCHEMAS]
)
def test_audit_rejects_constructs_outside_the_subset(label, body, expected):
    rel, schema = synthetic(body)
    problems = audit_file(rel, schema)
    assert any(expected in problem for problem in problems), (label, problems)


def test_audit_accepts_a_well_formed_schema():
    body = closed(
        {
            "a": {**STRING, "x-untrusted": True},
            "b": {"type": "integer", "minimum": 0, "maximum": 9},
            "c": {"type": "array", "maxItems": 2, "items": STRING},
            "d": {"type": "string", "enum": ["x", "y"]},
            "e": {"type": "boolean"},
        },
        ["a"],
    )
    rel, schema = synthetic(body)
    assert audit_file(rel, schema) == []


def test_audit_accepts_x_since_in_its_three_permitted_places():
    future = {"major": 1, "minor": 1}
    optional = closed({"new": {**STRING, "x-since": "1.1"}, "old": STRING}, ["old"])
    rel, schema = synthetic(optional)
    assert audit_file(rel, schema, future) == []
    branches = {
        "oneOf": [
            closed({"k": {"type": "string", "const": "a"}}),
            {**closed({"k": {"type": "string", "const": "b"}}), "x-since": "1.1"},
        ]
    }
    rel, schema = synthetic(branches)
    assert audit_file(rel, schema, future) == []
    rel, schema = synthetic(closed({}), **{"x-since": "1.1"})
    assert audit_file(rel, schema, future) == []


def test_audit_rejects_x_since_on_a_required_property_even_when_allowed_elsewhere():
    future = {"major": 1, "minor": 1}
    rel, schema = synthetic(closed({"new": {**STRING, "x-since": "1.1"}}, ["new"]))
    problems = audit_file(rel, schema, future)
    assert any("cannot be introduced after 1.0" in p for p in problems), problems


def _graph(files):
    return audit_graph(files, ["a.thing"])


def _minimal_set(**extra):
    leaf = {"$schema": DIALECT, "$id": BASE + "x.json", **closed({})}
    files = {
        "envelope.request.json": dict(leaf),
        "error.protocol.json": dict(leaf),
        "messages/a.thing.request.json": dict(leaf),
        "messages/a.thing.response.json": dict(leaf),
    }
    files.update(extra)
    return files


GRAPH_CASES = [
    (
        "orphan file",
        _minimal_set(
            **{
                "messages/orphan.json": {
                    "$schema": DIALECT,
                    "$id": BASE + "messages/orphan.json",
                    **closed({}),
                }
            }
        ),
        "unreachable schema file: messages/orphan.json",
    ),
    (
        "missing target",
        _minimal_set(**{"envelope.error.json": {**closed({"a": {"$ref": "nowhere.json"}})}}),
        "not in the schema set",
    ),
    (
        "external reference",
        _minimal_set(
            **{"envelope.error.json": {**closed({"a": {"$ref": "https://example.com/x.json"}})}}
        ),
        "external reference",
    ),
    (
        "dead definition",
        _minimal_set(**{"envelope.error.json": {**closed({}), "$defs": {"unused": closed({})}}}),
        "definition 'unused' is never referenced",
    ),
    (
        "reference cycle",
        _minimal_set(
            **{
                "envelope.error.json": {
                    **closed({"a": {"$ref": "#/$defs/n"}}),
                    "$defs": {"n": closed({"b": {"$ref": "#/$defs/n"}})},
                }
            }
        ),
        "reference cycle",
    ),
    (
        "indistinguishable oneOf",
        _minimal_set(
            **{
                "envelope.error.json": {
                    "oneOf": [
                        closed({"k": {"type": "string", "const": "a"}}),
                        closed({"k": {"type": "string", "const": "a"}}),
                    ]
                }
            }
        ),
        "not distinguished",
    ),
    (
        "forbidden property name",
        _minimal_set(
            **{"envelope.error.json": closed({"api_key": {"type": "string", "maxLength": 3}})}
        ),
        "forbidden property name 'api_key'",
    ),
    (
        "fragment that is not a definition",
        _minimal_set(
            **{"envelope.error.json": closed({"a": {"$ref": "#/properties/b"}, "b": STRING})}
        ),
        "fragment must be /$defs/<name>",
    ),
    (
        "missing dispatch file",
        {k: v for k, v in _minimal_set().items() if k != "error.protocol.json"},
        "dispatch file missing",
    ),
]


@pytest.mark.parametrize(
    ("label", "files", "expected"), GRAPH_CASES, ids=[c[0] for c in GRAPH_CASES]
)
def test_graph_audit_catches_structural_problems(label, files, expected):
    problems = _graph(files)
    assert any(expected in problem for problem in problems), (label, problems)


def test_graph_audit_accepts_a_minimal_set():
    assert _graph(_minimal_set()) == []


# ---------------------------------------------------------------------- dispatch


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ({"kind": "request", "type": "session.hello"}, ("envelope.hello.request.json", None)),
        ({"kind": "response", "type": "session.hello"}, ("envelope.hello.response.json", None)),
        ({"kind": "request", "type": "work.poll"}, ("envelope.request.json", None)),
        ({"kind": "response", "type": "work.poll"}, ("envelope.response.json", None)),
        ({"kind": "response"}, ("envelope.error.json", None)),
        ({"kind": "request"}, (None, "/type")),
        ({"kind": "request", "type": "edit.action"}, (None, "/type")),
        ({"kind": "request", "type": 5}, (None, "/type")),
        ({"kind": "notify", "type": "work.poll"}, (None, "/kind")),
        ({"type": "work.poll"}, (None, "/kind")),
    ],
)
def test_dispatch_selects_the_envelope(message, expected):
    assert select_envelope(message) == expected


def test_dispatch_selects_the_payload_schema():
    assert (
        select_payload_schema({"kind": "request", "type": "edit.result"})
        == "messages/edit.result.request.json"
    )
    assert (
        select_payload_schema({"kind": "response", "type": "edit.result", "status": "ok"})
        == "messages/edit.result.response.json"
    )
    assert (
        select_payload_schema({"kind": "response", "type": "edit.result", "status": "error"})
        == "error.protocol.json"
    )
    assert select_payload_schema({"kind": "response", "status": "error"}) == "error.protocol.json"


# ----------------------------------------------------------------------- vectors


def _listing(group):
    return sorted(f"{group}/{p.name}" for p in (EXAMPLES_DIR / group).glob("*.json"))


@pytest.mark.parametrize("group", ["valid", "invalid", "parse"])
def test_index_lists_exactly_the_vectors_on_disk(group):
    assert INDEX[group] == _listing(group)
    assert set(INDEX) == {"valid", "invalid", "parse"}


def _load(rel):
    return json.loads((EXAMPLES_DIR / rel).read_text(encoding="utf-8"))


ALL_VECTORS = {rel: _load(rel) for group in INDEX for rel in INDEX[group]}


@pytest.mark.parametrize("rel", sorted(ALL_VECTORS))
def test_vector_files_follow_the_documented_format(rel):
    vector = ALL_VECTORS[rel]
    assert set(vector) <= {"description", "message", "message_raw", "generate", "expect"}
    assert {"description", "expect"} <= set(vector)
    assert ("message" in vector) != ("message_raw" in vector)
    assert not ("message_raw" in vector and "generate" in vector)
    assert vector["description"].strip()
    raw = (EXAMPLES_DIR / rel).read_bytes()
    assert raw.isascii(), "vectors are ASCII so any runtime can read them"
    assert raw.endswith(b"\n")
    for step in vector.get("generate", []):
        assert step["at"].startswith("/")
        assert ("repeat" in step and "count" in step) != ("fill" in step and "length" in step)


@pytest.mark.parametrize("rel", INDEX["valid"])
def test_valid_vector_validates(rel):
    vector = ALL_VECTORS[rel]
    assert vector["expect"] == {"valid": True}
    outcome = validate_text(vector_text(vector))
    assert outcome.valid, (rel, outcome)


def _verify_inner(vector, text):
    inner = vector["expect"]["inner"]
    message = parse_strict(text)
    if "unknown_discriminator" in inner:
        spec = inner["unknown_discriminator"]
        rel, _, fragment = spec["oneOf"].partition("#")
        node = pointer_get(FILES[rel], fragment)
        assert "oneOf" in node, "unknown_discriminator must point at a oneOf"
        branches = [const_properties(FILES, rel, branch) for branch in node["oneOf"]]
        for key in spec["values"]:
            assert any(key in consts for consts in branches), f"{key} is not a discriminator here"
        for consts in branches:
            assert not all(consts.get(k) == v for k, v in spec["values"].items()), consts
        return
    rel, _, fragment = inner["schema"].partition("#")
    instance = pointer_get(message, inner["instance"])
    consts = const_properties(FILES, rel, pointer_get(FILES[rel], fragment))
    for key, value in consts.items():
        assert instance.get(key) == value, f"the instance does not claim branch {inner['schema']}"
    errors = errors_against(rel, fragment, instance)
    assert len(errors) == 1, [e.message for e in errors]
    assert pointer_of(errors[0].absolute_path) == inner["path"]
    assert errors[0].validator == inner["keyword"]


@pytest.mark.parametrize("rel", INDEX["invalid"])
def test_invalid_vector_fails_for_the_declared_reason(rel):
    vector = ALL_VECTORS[rel]
    expect = vector["expect"]
    text = vector_text(vector)
    outcome = validate_text(text)
    assert not outcome.valid, rel
    assert (outcome.stage, outcome.path) == (expect["stage"], expect["path"]), outcome
    assert outcome.keyword == expect.get("keyword"), outcome
    if outcome.stage in ("envelope", "payload"):
        assert outcome.error_count == 1, f"{rel} has more than one defect"
    if expect.get("keyword") == "oneOf":
        assert "inner" in expect, f"{rel} fails a oneOf and must say which branch it meant"
        _verify_inner(vector, text)
    else:
        assert "inner" not in expect


@pytest.mark.parametrize("rel", INDEX["parse"])
def test_parse_vector_gives_the_declared_result(rel):
    vector = ALL_VECTORS[rel]
    expect = vector["expect"]
    text = vector_text(vector)
    assert expect["stage"] == "parse"
    if expect["valid"]:
        assert isinstance(parse_strict(text), dict)
        return
    assert expect["reason"] in REASONS
    outcome = validate_text(text)
    assert (outcome.valid, outcome.stage, outcome.reason) == (False, "parse", expect["reason"])


def _message_of(vector):
    try:
        return parse_strict(vector_text(vector))
    except ValueError:
        return None


def test_every_reason_the_profile_can_give_has_a_vector():
    used = {
        v["expect"]["reason"]
        for r, v in ALL_VECTORS.items()
        if r.startswith("parse/") and not v["expect"]["valid"]
    }
    # invalid_utf8 cannot be written in a JSON vector; test_strict_json covers it with bytes.
    assert used == set(REASONS) - {"invalid_utf8"}


def test_every_message_type_and_kind_has_valid_and_invalid_vectors():
    valid_seen, invalid_seen = set(), set()
    for rel, vector in ALL_VECTORS.items():
        message = _message_of(vector) if rel.startswith("valid/") else vector.get("message")
        if not isinstance(message, dict) or "type" not in message:
            continue
        key = (message["type"], message.get("kind"))
        (valid_seen if rel.startswith("valid/") else invalid_seen).add(key)
    expected = {(t, k) for t in message_types() for k in ("request", "response")}
    assert expected <= valid_seen, expected - valid_seen
    assert expected <= invalid_seen, expected - invalid_seen


def test_every_operation_and_every_allowlisted_property_has_valid_and_invalid_vectors():
    branches = {
        name for name in FILES["messages/edit.action.json"]["$defs"] if name not in ("operation",)
    }
    valid_ops, invalid_branches = set(), set()
    for rel, vector in ALL_VECTORS.items():
        if rel.startswith("valid/"):
            message = _message_of(vector)
            work = (message or {}).get("payload", {}).get("work", {})
            for op in work.get("operations", []):
                valid_ops.add(
                    f"set_property_{op['property']}" if op["op"] == "set_property" else op["op"]
                )
        elif rel.startswith("invalid/"):
            inner = vector["expect"].get("inner", {})
            if "schema" in inner and inner["schema"].startswith(
                "messages/edit.action.json#/$defs/"
            ):
                invalid_branches.add(inner["schema"].rsplit("/", 1)[1])
    assert branches <= valid_ops, branches - valid_ops
    assert branches <= invalid_branches, branches - invalid_branches


def test_every_error_code_has_a_valid_vector():
    protocol, operation = set(), set()
    for rel, vector in ALL_VECTORS.items():
        if not rel.startswith("valid/"):
            continue
        message = _message_of(vector)
        payload = message.get("payload", {})
        if message.get("status") == "error":
            protocol.add(payload["code"])
        for op in payload.get("operations", []) if message.get("type") == "edit.result" else []:
            if "error" in op:
                operation.add(op["error"]["code"])
    assert protocol == set(PROTOCOL_ERROR_CODES)
    assert operation == set(OPERATION_ERROR_CODES)


def test_every_limit_has_a_vector_at_the_limit_and_one_over():
    names = set(ALL_VECTORS)
    for needle in (
        "boundary-100-operations",
        "operations-101",
        "boundary-source-100000",
        "script-source-100001",
        "boundary-path-16-segments",
        "path-17-segments",
        "boundary-2000-entries",
        "2001-entries",
        "boundary-1000-output-lines",
        "1001-output-lines",
        "boundary-segment-100-astral",
        "segment-101-astral",
        "scope-33-entries",
        "oversize-message",
        "depth-12",
        "depth-13",
        "integer-at-2-53",
        "integer-above-2-53",
    ):
        assert any(needle in name for name in names), needle


# --------------------------------------------------------- recipes and a few hand checks


def test_generate_repeat_and_fill_recipes():
    message = {"a": {"b": []}, "c": ""}
    out = expand_generate(
        message,
        [
            {"at": "/a/b", "repeat": {"x": 1}, "count": 3},
            {"at": "/c", "fill": "ab", "length": 2},
        ],
    )
    assert out == {"a": {"b": [{"x": 1}] * 3}, "c": "abab"}
    assert message == {"a": {"b": []}, "c": ""}, "the recipe must not mutate its input"


def test_vector_message_applies_generate():
    vector = _load("invalid/edit-action.operations-101.json")
    assert len(vector_message(vector)["payload"]["work"]["operations"]) == 101


def test_the_message_at_each_limit_is_inside_the_byte_cap():
    for rel in (
        "valid/work.poll.response.boundary-source-100000.json",
        "valid/project.state.request.boundary-2000-entries.json",
        "valid/playtest.report.request.boundary-1000-output-lines.json",
    ):
        assert len(vector_text(_load(rel)).encode()) < MAX_MESSAGE_BYTES, rel


def test_message_without_a_payload_slot_value_is_rejected_at_the_right_stage():
    message = json.loads(vector_text(_load("valid/work.poll.request.empty.json")))
    message["payload"] = []
    outcome = validate_message(message)
    assert (outcome.stage, outcome.path, outcome.keyword) == ("payload", "/payload", "type")


def test_schema_files_have_no_stray_files_beside_them():
    on_disk = {p.relative_to(SCHEMA_DIR).as_posix() for p in SCHEMA_DIR.rglob("*") if p.is_file()}
    assert on_disk == set(FILES) | {"version.json"}


def test_root_only_keywords_are_declared_consistently():
    assert ROOT_ONLY == {"$schema", "$id", "$defs"}
    assert all(re.fullmatch(r"https://schemas\.invalid/.+\.json", s["$id"]) for s in FILES.values())
