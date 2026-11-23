"""Test-only helpers: load the v1 schema set, validate messages, audit the schema subset.

Nothing here ships. The audit encodes the rules that make a hand-written Luau validator
feasible (ADR-0009): a closed subset of JSON Schema, every object closed, every string,
array and number bounded, no recursion, no null.
"""

import copy
import json
import posixpath
import re
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from protocol_strict_json import ProfileError, parse_strict
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

PACKAGE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_DIR = PACKAGE_DIR / "schemas" / "v1"
EXAMPLES_DIR = PACKAGE_DIR / "examples" / "v1"
BASE = "https://schemas.invalid/roblox-game-architect/protocol/v1/"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
MAX_SAFE_INTEGER = 9007199254740991

ALLOWED_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$ref",
        "$defs",
        "title",
        "description",
        "type",
        "enum",
        "const",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "oneOf",
    }
)
ANNOTATIONS = frozenset({"x-untrusted", "x-since"})
ROOT_ONLY = frozenset({"$schema", "$id", "$defs"})
COMMON_KEYS = frozenset({"type", "description", "title"}) | ROOT_ONLY
TYPE_KEYWORDS = {
    "object": frozenset({"properties", "required", "additionalProperties"}),
    "array": frozenset({"items", "minItems", "maxItems"}),
    "string": frozenset({"minLength", "maxLength", "enum", "const"}),
    "integer": frozenset({"minimum", "maximum", "const"}),
    "number": frozenset({"minimum", "maximum"}),
    "boolean": frozenset(),
}
FORBIDDEN_PROPERTY_NAMES = frozenset(
    {
        "prompt",
        "system_prompt",
        "completion",
        "api_key",
        "apikey",
        "secret",
        "password",
        "token",
        "authorization",
        "credentials",
        "provider",
        "model",
        "llm",
    }
)


# ----------------------------------------------------------------------- loading


@lru_cache(maxsize=1)
def load_files():
    files = {}
    for path in sorted(SCHEMA_DIR.rglob("*.json")):
        rel = path.relative_to(SCHEMA_DIR).as_posix()
        if rel != "version.json":
            files[rel] = json.loads(path.read_text(encoding="utf-8"))
    return files


@lru_cache(maxsize=1)
def load_version():
    return json.loads((SCHEMA_DIR / "version.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def registry():
    resources = [
        (schema["$id"], Resource.from_contents(schema, default_specification=DRAFT202012))
        for schema in load_files().values()
    ]
    return Registry().with_resources(resources)


@cache
def validator_for(uri):
    return Draft202012Validator({"$ref": uri}, registry=registry())


def schema_uri(rel, fragment=""):
    return BASE + rel + ("#" + fragment if fragment else "")


def escape_token(token):
    return str(token).replace("~", "~0").replace("/", "~1")


def pointer_of(parts):
    return "".join("/" + escape_token(part) for part in parts)


def pointer_get(document, pointer):
    node = document
    if pointer == "":
        return node
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


# -------------------------------------------------------------- message validation


@dataclass(frozen=True)
class Outcome:
    valid: bool
    stage: str | None = None
    path: str | None = None
    keyword: str | None = None
    error_count: int = 0
    reason: str | None = None


def message_types():
    return tuple(load_version()["types"])


def select_envelope(message):
    """Stage 1 dispatch. Returns (schema file, None) or (None, pointer of the culprit)."""
    kind = message.get("kind")
    if kind not in ("request", "response"):
        return None, "/kind"
    if kind == "response" and "type" not in message:
        return "envelope.error.json", None
    message_type = message.get("type")
    if not isinstance(message_type, str) or message_type not in message_types():
        return None, "/type"
    if message_type == "session.hello":
        return f"envelope.hello.{kind}.json", None
    return f"envelope.{kind}.json", None


def select_payload_schema(message):
    """Stage 2 dispatch, valid only after the envelope validated."""
    if message["kind"] == "request":
        return f"messages/{message['type']}.request.json"
    if message["status"] == "ok":
        return f"messages/{message['type']}.response.json"
    return "error.protocol.json"


def _outcome(stage, errors, prefix):
    errors = sorted(errors, key=lambda e: ([str(p) for p in e.absolute_path], e.validator))
    first = errors[0]
    return Outcome(
        False,
        stage,
        prefix + pointer_of(first.absolute_path),
        first.validator,
        len(errors),
    )


def validate_message(message):
    envelope, culprit = select_envelope(message)
    if envelope is None:
        return Outcome(False, "dispatch", culprit, None, 1)
    errors = list(validator_for(schema_uri(envelope)).iter_errors(message))
    if errors:
        return _outcome("envelope", errors, "")
    payload_schema = select_payload_schema(message)
    errors = list(validator_for(schema_uri(payload_schema)).iter_errors(message["payload"]))
    if errors:
        return _outcome("payload", errors, "/payload")
    return Outcome(True)


def validate_text(data):
    try:
        message = parse_strict(data)
    except ProfileError as exc:
        return Outcome(False, "parse", None, None, 1, exc.reason)
    return validate_message(message)


def errors_against(rel, fragment, instance):
    """Validate an instance against one subschema, to explain a oneOf failure."""
    return list(validator_for(schema_uri(rel, fragment)).iter_errors(instance))


# ------------------------------------------------------------------------ vectors


def expand_generate(message, generate):
    """Apply a vector's `generate` recipe: repeat an item into an array, or fill a string."""
    message = copy.deepcopy(message)
    for step in generate:
        *parent_tokens, last = step["at"][1:].split("/")
        parent = pointer_get(message, "".join("/" + t for t in parent_tokens))
        key = int(last) if isinstance(parent, list) else last
        if "repeat" in step:
            parent[key] = [copy.deepcopy(step["repeat"]) for _ in range(step["count"])]
        else:
            parent[key] = step["fill"] * step["length"]
    return message


def vector_message(vector):
    """The message a vector describes, as a Python value (not for message_raw vectors)."""
    return expand_generate(vector["message"], vector.get("generate", []))


def vector_text(vector):
    if "message_raw" in vector:
        return vector["message_raw"]
    return json.dumps(vector_message(vector), ensure_ascii=False, separators=(",", ":"))


def load_vector(rel):
    return json.loads((EXAMPLES_DIR / rel).read_text(encoding="utf-8"))


# ------------------------------------------------------------------- schema audit


class AuditError(Exception):
    pass


@dataclass(frozen=True)
class Ctx:
    is_root: bool = True
    in_oneof: bool = False
    optional_property: bool = False


def parse_since(text):
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)", text) if isinstance(text, str) else None
    return (int(match.group(1)), int(match.group(2))) if match else None


def iter_nodes(node, pointer="", ctx=None, *, skip_defs=False):
    """Yield (pointer, node, ctx) for every literal subschema of a schema file."""
    ctx = ctx or Ctx()
    yield pointer, node, ctx
    if not isinstance(node, dict):
        return
    if not skip_defs and isinstance(node.get("$defs"), dict):
        for name, child in node["$defs"].items():
            yield from iter_nodes(child, f"{pointer}/$defs/{escape_token(name)}", Ctx(False))
    properties = node.get("properties")
    if isinstance(properties, dict):
        required = node.get("required", [])
        for name, child in properties.items():
            child_ctx = Ctx(False, False, name not in required)
            yield from iter_nodes(
                child, f"{pointer}/properties/{escape_token(name)}", child_ctx, skip_defs=skip_defs
            )
    if isinstance(node.get("items"), dict):
        yield from iter_nodes(node["items"], f"{pointer}/items", Ctx(False), skip_defs=skip_defs)
    if isinstance(node.get("oneOf"), list):
        for index, child in enumerate(node["oneOf"]):
            yield from iter_nodes(
                child, f"{pointer}/oneOf/{index}", Ctx(False, True), skip_defs=skip_defs
            )


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _audit_annotations(rel, node, ctx, current, bad):
    if "x-untrusted" in node and (node["x-untrusted"] is not True or node.get("type") != "string"):
        bad("x-untrusted must be true and sit on a string schema")
    if "x-since" not in node:
        return
    since = parse_since(node["x-since"])
    if since is None:
        bad("x-since must be a 'MAJOR.MINOR' string")
        return
    if since > (current["major"], current["minor"]):
        bad("x-since is newer than version.json")
    in_message_root = ctx.is_root and rel.startswith("messages/")
    if not (ctx.in_oneof or ctx.optional_property or in_message_root):
        bad("x-since may only sit on a oneOf branch, an optional property or a message schema")


def _audit_typed(node, typ, bad):
    if typ == "object":
        properties = node.get("properties")
        if not isinstance(properties, dict):
            bad("object without a properties map")
            return
        if node.get("additionalProperties") is not False:
            bad("object is not closed (additionalProperties must be false)")
        required = node.get("required", [])
        if not isinstance(required, list) or not all(isinstance(r, str) for r in required):
            bad("required must be a list of strings")
        elif not set(required) <= set(properties):
            bad("required names a property that is not declared")
    elif typ == "array":
        if not isinstance(node.get("items"), dict):
            bad("array without an items schema")
        max_items = node.get("maxItems")
        if not isinstance(max_items, int) or isinstance(max_items, bool) or max_items < 0:
            bad("array without maxItems")
        elif node.get("minItems", 0) > max_items:
            bad("minItems exceeds maxItems")
    elif typ == "string":
        if "enum" in node:
            values = node["enum"]
            if not (
                isinstance(values, list)
                and values
                and all(isinstance(v, str) for v in values)
                and len(set(values)) == len(values)
            ):
                bad("enum must be a non-empty list of unique strings")
        elif "const" in node:
            if not isinstance(node["const"], str):
                bad("const must be a string")
        else:
            max_length = node.get("maxLength")
            if not isinstance(max_length, int) or isinstance(max_length, bool) or max_length < 0:
                bad("string without maxLength")
            elif node.get("minLength", 0) > max_length:
                bad("minLength exceeds maxLength")
    elif typ in ("integer", "number"):
        if "const" in node:
            const = node["const"]
            if not isinstance(const, int) or isinstance(const, bool):
                bad("integer const must be an integer")
            return
        low, high = node.get("minimum"), node.get("maximum")
        if not (_is_number(low) and _is_number(high)):
            bad(f"{typ} without minimum and maximum")
        elif low > high:
            bad("minimum exceeds maximum")
        elif typ == "integer" and (
            not isinstance(low, int)
            or not isinstance(high, int)
            or abs(low) > MAX_SAFE_INTEGER
            or abs(high) > MAX_SAFE_INTEGER
        ):
            bad("integer bounds must be integers within +/- 2^53-1")


def _audit_node(rel, pointer, node, ctx, current, out):
    def bad(message):
        out.append(f"{rel}#{pointer}: {message}")

    if not isinstance(node, dict):
        bad("schema is not an object")
        return
    for key in node:
        if key in ALLOWED_KEYWORDS:
            if key in ROOT_ONLY and not ctx.is_root:
                bad(f"'{key}' is only allowed at the file root")
        elif key in ANNOTATIONS:
            continue
        elif key.startswith("x-"):
            bad(f"annotation '{key}' is not one of {sorted(ANNOTATIONS)}")
        else:
            bad(f"keyword '{key}' is outside the permitted subset")
    if ctx.is_root:
        if node.get("$schema") != DIALECT:
            bad("$schema must be Draft 2020-12")
        if node.get("$id") != BASE + rel:
            bad("$id must be the base URI plus the file path")
    if "$ref" in node:
        if set(node) != {"$ref"}:
            bad("a $ref schema may not have sibling keywords")
        return
    _audit_annotations(rel, node, ctx, current, bad)
    if "oneOf" in node:
        extra = set(node) - {"oneOf", "description", "title"} - ROOT_ONLY - ANNOTATIONS
        if extra:
            bad(f"oneOf may not be combined with {sorted(extra)}")
        branches = node["oneOf"]
        if not isinstance(branches, list) or len(branches) < 2:
            bad("oneOf needs at least two branches")
        return
    typ = node.get("type")
    if typ is None:
        is_slot = rel.startswith("envelope.") and pointer.endswith("/properties/payload")
        only_container = ctx.is_root and set(node) <= COMMON_KEYS | ANNOTATIONS
        if not (is_slot and set(node) == {"description"}) and not only_container:
            bad("schema has no type")
        return
    if not isinstance(typ, str) or typ not in TYPE_KEYWORDS:
        bad(f"type must be one of {sorted(TYPE_KEYWORDS)} (no null, no unions)")
        return
    stray = set(node) - COMMON_KEYS - ANNOTATIONS - TYPE_KEYWORDS[typ]
    if stray:
        bad(f"keywords {sorted(stray)} do not apply to type {typ}")
    _audit_typed(node, typ, bad)
    if typ == "object" and isinstance(node.get("properties"), dict):
        for name in node.get("required", []):
            child = node["properties"].get(name)
            since = parse_since(child.get("x-since")) if isinstance(child, dict) else None
            if since is not None and since > (1, 0):
                bad(f"required property '{name}' cannot be introduced after 1.0")


def audit_file(rel, schema, current=None):
    """Node-level audit of one schema file. Returns a list of problems."""
    current = current or load_version()
    out = []
    for pointer, node, ctx in iter_nodes(schema):
        _audit_node(rel, pointer, node, ctx, current, out)
    return out


# ----------------------------------------------------------------- graph audit


def resolve(files, rel, ref):
    if "://" in ref or ref.startswith("/"):
        raise AuditError(f"external reference {ref!r}")
    file_part, _, fragment = ref.partition("#")
    target = (
        rel
        if not file_part
        else posixpath.normpath(posixpath.join(posixpath.dirname(rel), file_part))
    )
    if target not in files:
        raise AuditError(f"{ref!r} points at a file that is not in the schema set")
    node = files[target]
    if fragment:
        if not fragment.startswith("/"):
            raise AuditError(f"{ref!r} has a fragment that is not a JSON pointer")
        try:
            for token in fragment[1:].split("/"):
                token = token.replace("~1", "/").replace("~0", "~")
                node = node[int(token)] if isinstance(node, list) else node[token]
        except (KeyError, IndexError, ValueError) as exc:
            raise AuditError(f"{ref!r} does not resolve") from exc
    return target, fragment, node


def _ref_sites(files):
    for rel, schema in files.items():
        for pointer, node, _ in iter_nodes(schema):
            if isinstance(node, dict) and "$ref" in node:
                yield rel, pointer, node["$ref"]


def _follow(files, rel, node):
    """Follow a chain of $ref until a concrete schema. Returns (file, node)."""
    seen = 0
    while isinstance(node, dict) and "$ref" in node:
        rel, _, node = resolve(files, rel, node["$ref"])
        seen += 1
        if seen > 20:
            raise AuditError("reference chain too long")
    return rel, node


def const_properties(files, rel, node):
    rel, node = _follow(files, rel, node)
    properties = node.get("properties", {}) if isinstance(node, dict) else {}
    return {
        name: child["const"]
        for name, child in properties.items()
        if isinstance(child, dict) and "const" in child
    }


def _depth(files, rel, node, stack):
    """Maximum container nesting of the instances a schema describes."""
    rel, node, stack = _follow_tracking(files, rel, node, stack)
    if "oneOf" in node:
        return max(_depth(files, rel, branch, stack) for branch in node["oneOf"])
    typ = node.get("type")
    if typ == "object":
        children = [_depth(files, rel, c, stack) for c in node.get("properties", {}).values()]
        return 1 + max(children, default=0)
    if typ == "array":
        return 1 + _depth(files, rel, node["items"], stack)
    return 0


def _follow_tracking(files, rel, node, stack):
    while isinstance(node, dict) and "$ref" in node:
        target_rel, fragment, target = resolve(files, rel, node["$ref"])
        key = (target_rel, fragment)
        if key in stack:
            raise AuditError(f"reference cycle through {target_rel}#{fragment}")
        stack = stack | {key}
        rel, node = target_rel, target
    return rel, node, stack


def message_depth(files, message_type, kind, status="ok"):
    """Nesting depth of a whole message: envelope plus payload."""
    if kind == "request":
        payload = f"messages/{message_type}.request.json"
    elif status == "ok":
        payload = f"messages/{message_type}.response.json"
    else:
        payload = "error.protocol.json"
    return 1 + _depth(files, payload, files[payload], frozenset())


def dispatch_roots(files, types):
    roots = {rel for rel in files if rel.startswith("envelope.")} | {"error.protocol.json"}
    for message_type in types:
        roots.add(f"messages/{message_type}.request.json")
        roots.add(f"messages/{message_type}.response.json")
    return roots


def audit_graph(files, types):
    out = []
    targets = {}
    for rel, pointer, ref in _ref_sites(files):
        try:
            target_rel, fragment, node = resolve(files, rel, ref)
        except AuditError as exc:
            out.append(f"{rel}#{pointer}: {exc}")
            continue
        if fragment and not re.fullmatch(r"/\$defs/[A-Za-z0-9_]+", fragment):
            out.append(f"{rel}#{pointer}: fragment must be /$defs/<name>, got {fragment!r}")
        if not isinstance(node, dict):
            out.append(f"{rel}#{pointer}: target is not a schema")
        targets[(rel, pointer)] = (target_rel, fragment)

    # Reference cycles: computing a depth walks every reference and fails on a cycle.
    for rel, schema in files.items():
        if "type" in schema or "oneOf" in schema:
            try:
                _depth(files, rel, schema, frozenset())
            except AuditError as exc:
                out.append(f"{rel}: {exc}")

    # Reachability and dead definitions.
    roots = dispatch_roots(files, types)
    missing = sorted(roots - set(files))
    out.extend(f"dispatch file missing: {rel}" for rel in missing)
    edges = {rel: set() for rel in files}
    for (rel, _), (target_rel, _) in targets.items():
        edges[rel].add(target_rel)
    reached, frontier = set(), [r for r in roots if r in files]
    while frontier:
        current = frontier.pop()
        if current not in reached:
            reached.add(current)
            frontier.extend(edges[current])
    out.extend(f"unreachable schema file: {rel}" for rel in sorted(set(files) - reached))
    referenced = {(t, f.rsplit("/", 1)[-1]) for t, f in targets.values() if f}
    for rel, schema in files.items():
        for name in schema.get("$defs", {}):
            if (rel, name) not in referenced:
                out.append(f"{rel}: definition '{name}' is never referenced")

    # oneOf branches must be told apart by a differing const.
    for rel, schema in files.items():
        for pointer, node, _ in iter_nodes(schema):
            if not (isinstance(node, dict) and isinstance(node.get("oneOf"), list)):
                continue
            try:
                consts = [const_properties(files, rel, b) for b in node["oneOf"]]
            except AuditError as exc:
                out.append(f"{rel}#{pointer}: {exc}")
                continue
            for i in range(len(consts)):
                for j in range(i + 1, len(consts)):
                    shared = set(consts[i]) & set(consts[j])
                    if not any(consts[i][p] != consts[j][p] for p in shared):
                        out.append(
                            f"{rel}#{pointer}: oneOf branches {i} and {j} are not distinguished "
                            "by a differing const property"
                        )

    # No property may name a provider, a prompt or a secret.
    for rel, schema in files.items():
        for pointer, node, _ in iter_nodes(schema):
            if isinstance(node, dict) and isinstance(node.get("properties"), dict):
                for name in node["properties"]:
                    if name.lower() in FORBIDDEN_PROPERTY_NAMES:
                        out.append(f"{rel}#{pointer}: forbidden property name '{name}'")
    return out


def untrusted_locations(files):
    return {
        (rel, pointer)
        for rel, schema in files.items()
        for pointer, node, _ in iter_nodes(schema)
        if isinstance(node, dict) and node.get("x-untrusted") is True
    }


def operation_branches(files):
    """The set_property allowlist as the schema states it: name -> (classes, value schema)."""
    defs = files["messages/edit.action.json"]["$defs"]
    allowlist = {}
    for name, branch in defs.items():
        if not name.startswith("set_property_"):
            continue
        properties = branch["properties"]
        _, classes = _follow(
            files,
            "messages/edit.action.json",
            properties["target"]["properties"]["expect_class"],
        )
        allowlist[properties["property"]["const"]] = {
            "classes": classes["enum"],
            "value": properties["value"],
        }
    return allowlist
