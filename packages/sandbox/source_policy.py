"""Conservative static policy for generated Luau scene blockouts.

This gate accepts a deliberately small, data-like Luau subset. Passing it is
not permission to execute source: Gate 3 must still run it in a disposable place.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Protocol

from .parser import LuteSyntaxParser, SourceAnalysis

MAX_COORDINATE = 100_000.0
MAX_PART_SIZE = 2048.0
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_SCOPE_SEGMENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9 _-]{0,99}\Z")
MAX_SCOPE_SEGMENTS = 16
_NUMBER = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_STRING = re.compile(r"(?:'([A-Za-z0-9 _-]{1,100})'|\"([A-Za-z0-9 _-]{1,100})\")\Z")


def _load_policy() -> dict[str, Any]:
    """Load the reviewed, packaged allowlist and fail closed on schema drift."""
    try:
        policy = json.loads(files("sandbox").joinpath("luau_policy.json").read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("the packaged Luau allowlist is unavailable or malformed") from exc
    if (
        not isinstance(policy, dict)
        or set(policy)
        != {"version", "max_objects", "globals", "classes", "materials", "properties"}
        or policy["version"] != 1
        or isinstance(policy["version"], bool)
        or type(policy["max_objects"]) is not int
        or not 1 <= policy["max_objects"] <= 1000
        or any(
            not isinstance(policy[key], list)
            or any(not isinstance(item, str) or not item for item in policy[key])
            or len(policy[key]) != len(set(policy[key]))
            for key in ("globals", "classes", "materials")
        )
        or not isinstance(policy["properties"], dict)
        or set(policy["properties"]) - set(policy["classes"])
        or any(
            not isinstance(properties, dict)
            or any(
                not isinstance(name, str)
                or not isinstance(kind, str)
                or kind not in {"boolean", "number", "vector3", "cframe", "color3", "material"}
                for name, kind in properties.items()
            )
            for properties in policy["properties"].values()
        )
    ):
        raise RuntimeError("the packaged Luau allowlist has an invalid schema")
    return policy


_POLICY = _load_policy()
MAX_OBJECTS = _POLICY["max_objects"]
SAFE_CLASSES = frozenset(_POLICY["classes"])
SAFE_MATERIALS = frozenset(_POLICY["materials"])
_GLOBAL_NAMES = frozenset(_POLICY["globals"])


class SourcePolicyError(ValueError):
    """Generated source is outside the currently supported static subset."""


class _AnalysisParser(Protocol):
    def analyze(self, source: str) -> SourceAnalysis: ...


class _BuildTask(Protocol):
    scope: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceValidationResult:
    """Structural equivalent of core's validator result, without a core dependency."""

    passed: bool
    feedback: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Value:
    kind: str
    value: Any = None


@dataclass(slots=True)
class _Object:
    class_name: str
    name: str
    path: tuple[str, ...] | None = None
    anchored: bool = False


class LuauSourcePolicyValidator:
    """Validate only bounded, scoped scene construction; never execute source."""

    def __init__(self, parser: _AnalysisParser | None = None) -> None:
        self._parser = parser or LuteSyntaxParser()

    def validate(self, source: str, task: _BuildTask) -> SourceValidationResult:
        try:
            self._validate(source, task)
        except SourcePolicyError as exc:
            return SourceValidationResult(False, (str(exc),))
        return SourceValidationResult(True)

    def _validate(self, source: str, task: _BuildTask) -> None:
        analysis: SourceAnalysis = self._parser.analyze(source)
        if not analysis.syntax_valid:
            raise SourcePolicyError("Luau syntax is invalid; return a complete source file.")
        if analysis.summary.loop_kinds:
            raise SourcePolicyError("Loops are not allowed in the current scene-building subset.")
        if analysis.summary.bracket_index_count:
            raise SourcePolicyError("Dynamic indexing is not allowed.")
        if analysis.summary.unresolved_call_count:
            raise SourcePolicyError("Calls must use an explicitly allowed constructor.")
        denied = sorted(set(analysis.summary.globals) - _GLOBAL_NAMES)
        if denied:
            raise SourcePolicyError(f"Global access is not allowed: {', '.join(denied)}.")

        scopes = _parse_scopes(task.scope)
        bindings: dict[str, _Value] = {}
        created_paths: set[tuple[str, ...]] = set()
        object_count = 0
        statements = analysis.program.get("statements")
        if not isinstance(statements, list):
            raise SourcePolicyError("The parser returned an invalid program structure.")

        for statement in statements:
            kind = statement.get("kind")
            if kind in {"local", "const"}:
                variables, expressions = statement["variables"], statement["values"]
                if len(variables) != len(expressions) or not variables:
                    raise SourcePolicyError("Local declarations must have one value per variable.")
                for variable, expression in zip(variables, expressions, strict=True):
                    identity, name = variable["id"], variable["name"]
                    if identity in bindings or not _IDENTIFIER.fullmatch(name):
                        raise SourcePolicyError(
                            "Local binding is duplicated or has an invalid name."
                        )
                    value = self._evaluate(expression, bindings)
                    bindings[identity] = value
                    if value.kind == "object":
                        object_count += 1
                        if object_count > MAX_OBJECTS:
                            raise SourcePolicyError(
                                f"A build may create at most {MAX_OBJECTS} objects."
                            )
            elif kind == "assign":
                targets, expressions = statement["targets"], statement["values"]
                if len(targets) != len(expressions) or not targets:
                    raise SourcePolicyError("Assignments must have matching targets and values.")
                for target, expression in zip(targets, expressions, strict=True):
                    self._assign(
                        target,
                        self._evaluate(expression, bindings),
                        bindings,
                        scopes,
                        created_paths,
                    )
            elif kind == "unsupported":
                raise SourcePolicyError(
                    f"Luau statement '{statement.get('tag', 'unknown')}' is not allowed."
                )
            else:
                raise SourcePolicyError(
                    "Only local declarations and property assignments are allowed."
                )

        if object_count == 0:
            raise SourcePolicyError("The source must create at least one allowlisted scene object.")
        if any(value.kind == "object" and value.value.path is None for value in bindings.values()):
            raise SourcePolicyError(
                "Every created object must be parented inside the declared scope."
            )
        if any(
            value.kind == "object"
            and value.value.class_name in {"Part", "WedgePart"}
            and not value.value.anchored
            for value in bindings.values()
        ):
            raise SourcePolicyError("Every blockout Part and WedgePart must be Anchored=true.")

    def _evaluate(self, expression: dict[str, Any], bindings: dict[str, _Value]) -> _Value:
        kind = expression["kind"]
        if kind == "unsupported":
            raise SourcePolicyError(f"Luau expression '{expression['tag']}' is not allowed.")
        if kind == "string":
            match = _STRING.fullmatch(expression["raw"])
            if not match:
                raise SourcePolicyError("Only simple, bounded string literals are allowed.")
            return _Value("string", match.group(1) or match.group(2))
        if kind == "number":
            raw = expression["raw"].replace("_", "")
            if not _NUMBER.fullmatch(raw):
                raise SourcePolicyError("Numeric literals must be finite decimal numbers.")
            number = float(raw)
            if not math.isfinite(number) or abs(number) > MAX_COORDINATE:
                raise SourcePolicyError("Numeric literals must be finite and within scene bounds.")
            return _Value("number", number)
        if kind == "boolean":
            return _Value("boolean", expression["value"])
        if kind == "local":
            value = bindings.get(expression["binding"])
            if value is None:
                raise SourcePolicyError(
                    "Local binding is not available at this point in the source."
                )
            return value
        if kind == "global":
            if expression["name"] == "workspace":
                return _Value("workspace")
            raise SourcePolicyError("Globals are allowed only as approved constructor namespaces.")
        if kind == "indexname":
            chain = _chain(expression)
            if (
                chain.startswith("Enum.Material.")
                and chain.removeprefix("Enum.Material.") in SAFE_MATERIALS
            ):
                return _Value("material", chain.removeprefix("Enum.Material."))
            raise SourcePolicyError("Only allowlisted Enum.Material values may be read.")
        if kind == "call":
            return self._constructor(expression, bindings)
        if kind == "group":
            return self._evaluate(expression["expression"], bindings)
        if kind == "unary":
            operand = self._evaluate(expression["operand"], bindings)
            operator = expression["operator"]
            if operand.kind != "number" or operator not in {"+", "-"}:
                raise SourcePolicyError("Only unary plus and minus on numbers are allowed.")
            return _Value("number", operand.value if operator == "+" else -operand.value)
        if kind in {"binary", "index", "nil"}:
            raise SourcePolicyError(f"Luau expression '{kind}' is not allowed.")
        raise SourcePolicyError("The parser returned an unknown expression kind.")

    def _constructor(self, expression: dict[str, Any], bindings: dict[str, _Value]) -> _Value:
        function = expression["func"]
        chain = _chain(function)
        arguments = [self._evaluate(argument, bindings) for argument in expression["arguments"]]
        if chain == "Instance.new":
            if len(arguments) != 1 or arguments[0].kind != "string":
                raise SourcePolicyError("Instance.new accepts one literal class name.")
            class_name = arguments[0].value
            if class_name not in SAFE_CLASSES:
                raise SourcePolicyError(f"Instance class '{class_name}' is not allowed.")
            return _Value("object", _Object(class_name, class_name))
        if chain == "Vector3.new":
            vector = _components(arguments, 3, "Vector3")
            if any(abs(number) > MAX_COORDINATE for number in vector):
                raise SourcePolicyError("Vector3 values exceed scene bounds.")
            return _Value("vector3", vector)
        if chain == "Color3.new":
            color = _components(arguments, 3, "Color3")
            if any(not 0 <= number <= 1 for number in color):
                raise SourcePolicyError("Color3.new channels must be between 0 and 1.")
            return _Value("color3", color)
        if chain == "Color3.fromRGB":
            color = _components(arguments, 3, "Color3.fromRGB")
            if any(not number.is_integer() or not 0 <= number <= 255 for number in color):
                raise SourcePolicyError("Color3.fromRGB channels must be integers from 0 to 255.")
            return _Value("color3", tuple(number / 255 for number in color))
        if chain == "CFrame.new":
            values = _components(arguments, (3, 6), "CFrame")
            if len(values) == 6:
                raise SourcePolicyError("CFrame.new rotation overload is not enabled yet.")
            if any(abs(number) > MAX_COORDINATE for number in values):
                raise SourcePolicyError("CFrame values exceed scene bounds.")
            return _Value("cframe", values)
        raise SourcePolicyError(f"Constructor or call '{chain or 'dynamic'}' is not allowed.")

    def _assign(
        self,
        target: dict[str, Any],
        value: _Value,
        bindings: dict[str, _Value],
        scopes: tuple[tuple[tuple[str, ...], bool], ...],
        created_paths: set[tuple[str, ...]],
    ) -> None:
        if target.get("kind") != "indexname" or target.get("accessor") != ".":
            raise SourcePolicyError(
                "Only allowlisted properties on created objects can be assigned."
            )
        base = target["base"]
        if base.get("kind") != "local":
            raise SourcePolicyError(
                "Assignments cannot target Workspace or global objects directly."
            )
        reference = bindings.get(base["binding"])
        if reference is None or reference.kind != "object":
            raise SourcePolicyError("Property targets must be locally created instances.")
        instance: _Object = reference.value
        prop = target["name"]
        if prop == "Name":
            if value.kind != "string":
                raise SourcePolicyError("Name must be a simple string literal.")
            instance.name = value.value
            if instance.path is not None:
                raise SourcePolicyError("Names cannot change after parenting an instance.")
        elif prop == "Parent":
            if instance.path is not None:
                raise SourcePolicyError("An instance can be parented only once.")
            if value.kind == "workspace":
                parent_path = ("Workspace",)
            elif value.kind == "object" and value.value.class_name in {"Folder", "Model"}:
                parent_path = value.value.path
                if parent_path is None:
                    raise SourcePolicyError("Parent containers must be in scope before use.")
            else:
                raise SourcePolicyError("Parent must be Workspace or an in-scope Folder/Model.")
            created_path = (*parent_path, instance.name)
            if created_path in created_paths:
                raise SourcePolicyError(
                    f"Created path {'/'.join(created_path)} duplicates another scene object."
                )
            if not _in_scope(created_path, scopes):
                raise SourcePolicyError(
                    f"Created path {'/'.join(created_path)} is outside the declared scope."
                )
            instance.path = created_path
            created_paths.add(created_path)
        else:
            expected = _property_kind(instance.class_name, prop)
            if expected is None or value.kind != expected:
                raise SourcePolicyError(
                    f"Property '{prop}' is not allowed for {instance.class_name} "
                    "or has the wrong value type."
                )
            if prop == "Transparency" and not 0 <= value.value <= 1:
                raise SourcePolicyError("Transparency must be between 0 and 1.")
            if prop == "Orientation" and any(abs(number) > 360 for number in value.value):
                raise SourcePolicyError(
                    "Orientation components must be between -360 and 360 degrees."
                )
            if prop == "Anchored":
                instance.anchored = value.value
            if prop == "Size" and any(
                not 0.05 <= number <= MAX_PART_SIZE for number in value.value
            ):
                raise SourcePolicyError("Part size components must be between 0.05 and 2048.")


def _property_kind(class_name: str, prop: str) -> str | None:
    return _POLICY["properties"].get(class_name, {}).get(prop)


def _components(
    arguments: list[_Value], sizes: int | tuple[int, ...], label: str
) -> tuple[float, ...]:
    allowed = (sizes,) if isinstance(sizes, int) else sizes
    if len(arguments) not in allowed or any(value.kind != "number" for value in arguments):
        raise SourcePolicyError(f"{label} constructor requires literal numeric components.")
    return tuple(value.value for value in arguments)


def _chain(expression: dict[str, Any]) -> str:
    if expression.get("kind") == "global":
        return expression["name"]
    if expression.get("kind") == "indexname" and expression.get("accessor") == ".":
        prefix = _chain(expression["base"])
        if prefix:
            return f"{prefix}.{expression['name']}"
    return ""


def _parse_scopes(
    scopes: tuple[str, ...],
) -> tuple[tuple[tuple[str, ...], bool], ...]:
    parsed = []
    for scope in scopes:
        subtree = scope.endswith("/**")
        path_text = scope[:-3] if subtree else scope
        parts = tuple(path_text.split("/"))
        if (
            not parts
            or len(parts) > MAX_SCOPE_SEGMENTS
            or parts[0] != "Workspace"
            or any(not _SCOPE_SEGMENT.fullmatch(part) for part in parts)
        ):
            raise SourcePolicyError(
                "Declared scopes must be Workspace paths with an optional /** suffix."
            )
        parsed.append((parts, subtree))
    return tuple(parsed)


def _in_scope(path: tuple[str, ...], scopes: tuple[tuple[tuple[str, ...], bool], ...]) -> bool:
    return any(
        path[: len(scope_path)] == scope_path and (subtree or path == scope_path)
        for scope_path, subtree in scopes
    )
