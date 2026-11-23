"""Tests for the fail-closed Luau scene-construction subset."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from core.agent_loop import AgentLoop, BuildTask
from core.budget import IterationBudget, SpendBudget
from core.llm.types import CostQuote, GenerationRequest, GenerationResponse, Usage
from sandbox.parser import CstSummary, SourceAnalysis
from sandbox.source_policy import LuauSourcePolicyValidator


@dataclass
class _Parser:
    result: SourceAnalysis

    def analyze(self, source: str) -> SourceAnalysis:
        del source
        return self.result


def _global(name: str) -> dict[str, str]:
    return {"kind": "global", "name": name}


def _local(identity: str, name: str) -> dict[str, str]:
    return {"kind": "local", "binding": identity, "name": name}


def _string(value: str) -> dict[str, str]:
    return {"kind": "string", "raw": f'"{value}"'}


def _number(value: int | float) -> dict[str, str]:
    return {"kind": "number", "raw": str(value)}


def _negative(value: int | float) -> dict[str, Any]:
    return {"kind": "unary", "operator": "-", "operand": _number(value)}


def _index(base: dict[str, Any], name: str) -> dict[str, Any]:
    return {"kind": "indexname", "base": base, "accessor": ".", "name": name}


def _call(name: str, *arguments: dict[str, Any]) -> dict[str, Any]:
    namespace, method = name.rsplit(".", 1)
    function: dict[str, Any] = _global(namespace.split(".")[0])
    for segment in namespace.split(".")[1:]:
        function = _index(function, segment)
    return {"kind": "call", "func": _index(function, method), "arguments": list(arguments)}


def _local_statement(identity: str, name: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "local",
        "variables": [{"id": identity, "name": name}],
        "values": [value],
    }


def _assign(identity: str, name: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "assign",
        "targets": [_index(_local(identity, "instance"), name)],
        "values": [value],
    }


def _result(
    statements: list[dict[str, Any]],
    globals_: tuple[str, ...] = (),
    loops: tuple[str, ...] = (),
) -> SourceAnalysis:
    return SourceAnalysis(
        syntax_valid=True,
        summary=CstSummary(globals_, (), (), 0, 0, loops),
        program={"kind": "block", "statements": statements},
    )


def _valid_program() -> SourceAnalysis:
    model_id, part_id = "1:7:1:12", "4:7:4:12"
    return _result(
        [
            _local_statement(model_id, "model", _call("Instance.new", _string("Model"))),
            _assign(model_id, "Name", _string("Town")),
            _assign(model_id, "Parent", _global("workspace")),
            _local_statement(part_id, "part", _call("Instance.new", _string("Part"))),
            _assign(part_id, "Name", _string("Road")),
            _assign(
                part_id,
                "Size",
                _call("Vector3.new", _number(32), _number(1), _number(4)),
            ),
            _assign(
                part_id,
                "Position",
                _call("Vector3.new", _negative(32), _number(1), _number(4)),
            ),
            _assign(
                part_id,
                "Color",
                _call("Color3.fromRGB", _number(128), _number(90), _number(40)),
            ),
            _assign(part_id, "Anchored", {"kind": "boolean", "value": True}),
            _assign(part_id, "Material", _index(_index(_global("Enum"), "Material"), "Wood")),
            _assign(part_id, "Parent", _local(model_id, "model")),
        ],
        ("Color3", "Enum", "Instance", "Vector3", "workspace"),
    )


def _validate(program: SourceAnalysis, scope: tuple[str, ...] = ("Workspace/**",)):
    return LuauSourcePolicyValidator(_Parser(program)).validate(
        "source is intentionally supplied by the fake parser", BuildTask("build a town", scope)
    )


def test_accepts_scoped_part_and_model_construction() -> None:
    result = _validate(_valid_program(), ("Workspace/Town/**",))

    assert result.passed
    assert result.feedback == ()


def test_accepts_bounded_part_orientation() -> None:
    model_id, part_id = "1:7:1:12", "4:7:4:12"
    program = _result(
        [
            _local_statement(model_id, "model", _call("Instance.new", _string("Model"))),
            _assign(model_id, "Name", _string("Town")),
            _assign(model_id, "Parent", _global("workspace")),
            _local_statement(part_id, "part", _call("Instance.new", _string("Part"))),
            _assign(part_id, "Name", _string("Roof")),
            _assign(
                part_id,
                "Orientation",
                _call("Vector3.new", _number(0), _number(35), _negative(15)),
            ),
            _assign(part_id, "Anchored", {"kind": "boolean", "value": True}),
            _assign(part_id, "Parent", _local(model_id, "model")),
        ],
        ("Instance", "Vector3", "workspace"),
    )

    assert _validate(program, ("Workspace/Town/**",)).passed


def test_rejects_unbounded_part_orientation() -> None:
    model_id, part_id = "1:7:1:12", "4:7:4:12"
    program = _result(
        [
            _local_statement(model_id, "model", _call("Instance.new", _string("Model"))),
            _assign(model_id, "Name", _string("Town")),
            _assign(model_id, "Parent", _global("workspace")),
            _local_statement(part_id, "part", _call("Instance.new", _string("Part"))),
            _assign(part_id, "Name", _string("Roof")),
            _assign(
                part_id,
                "Orientation",
                _call("Vector3.new", _number(0), _number(361), _number(0)),
            ),
            _assign(part_id, "Parent", _local(model_id, "model")),
        ],
        ("Instance", "Vector3", "workspace"),
    )

    result = _validate(program, ("Workspace/Town/**",))
    assert not result.passed
    assert "Orientation components" in result.feedback[0]


def test_build_task_requires_bounded_declared_scope() -> None:
    with pytest.raises(ValueError, match="scope must contain 1 to 32"):
        BuildTask("Build a town", ())
    with pytest.raises(ValueError, match="scope must contain 1 to 32"):
        BuildTask("Build a town", tuple(f"Workspace/{index}" for index in range(33)))
    with pytest.raises(ValueError, match="at most"):
        BuildTask("Build a town", ("Workspace/" + "x" * 1700,))


def test_rejects_creation_outside_declared_scope() -> None:
    result = _validate(_valid_program(), ("Workspace/Other/**",))

    assert not result.passed
    assert "outside the declared scope" in result.feedback[0]


@pytest.mark.parametrize(
    ("program", "expected"),
    [
        (
            _result(
                [{"kind": "unsupported", "tag": "while"}],
                ("workspace",),
                ("while",),
            ),
            "Loops are not allowed",
        ),
        (
            _result([_local_statement("1:1:1:2", "code", _global("os"))], ("os",)),
            "Global access is not allowed",
        ),
        (
            _result(
                [_local_statement("1:1:1:2", "part", _call("Instance.new", _string("Script")))],
                ("Instance",),
            ),
            "Instance class 'Script' is not allowed",
        ),
        (
            _result(
                [
                    _local_statement("1:1:1:2", "part", _call("Instance.new", _string("Part"))),
                    _assign("1:1:1:2", "Source", _string("unsafe source")),
                ],
                ("Instance",),
            ),
            "Property 'Source' is not allowed",
        ),
    ],
)
def test_rejects_unsupported_globals_classes_and_properties(
    program: SourceAnalysis, expected: str
) -> None:
    result = _validate(program)

    assert not result.passed
    assert expected in result.feedback[0]


def test_rejects_unparented_objects_even_when_other_statements_are_safe() -> None:
    result = _validate(
        _result(
            [_local_statement("1:1:1:2", "part", _call("Instance.new", _string("Part")))],
            ("Instance",),
        )
    )

    assert not result.passed
    assert "must be parented inside the declared scope" in result.feedback[0]


def test_rejects_unanchored_blockout_parts() -> None:
    model_id, part_id = "1:7:1:12", "4:7:4:12"
    program = _result(
        [
            _local_statement(model_id, "model", _call("Instance.new", _string("Model"))),
            _assign(model_id, "Name", _string("Town")),
            _assign(model_id, "Parent", _global("workspace")),
            _local_statement(part_id, "part", _call("Instance.new", _string("Part"))),
            _assign(part_id, "Name", _string("Road")),
            _assign(part_id, "Parent", _local(model_id, "model")),
        ],
        ("Instance", "workspace"),
    )

    result = _validate(program, ("Workspace/Town/**",))
    assert not result.passed
    assert "must be Anchored=true" in result.feedback[0]


def test_rejects_invalid_syntax_and_malformed_scope() -> None:
    invalid = SourceAnalysis(
        False, CstSummary((), (), (), 0, 0, ()), {"kind": "block", "statements": []}
    )
    assert "syntax is invalid" in _validate(invalid).feedback[0]
    assert "Declared scopes" in _validate(_valid_program(), ("ServerStorage/**",)).feedback[0]


class _QueueProvider:
    name = "test"

    def __init__(self, source: str) -> None:
        self.source = source
        self.requests: list[GenerationRequest] = []

    def quote_max_cost(self, request: GenerationRequest) -> CostQuote:
        del request
        return CostQuote(Decimal(0))

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        return GenerationResponse(
            text=self.source,
            provider=self.name,
            model="test-model",
            usage=Usage(1, 1, Decimal(0)),
        )


def test_agent_loop_accepts_the_sandbox_policy_result_contract() -> None:
    task = BuildTask("Build a town", ("Workspace/Town/**",))
    agent = AgentLoop(
        _QueueProvider("safe scene source"),
        LuauSourcePolicyValidator(_Parser(_valid_program())),
        iterations=IterationBudget(1),
        spend=SpendBudget(Decimal(0)),
    )

    result = agent.run(task)

    assert result.succeeded
    assert result.source == "safe scene source"
    assert result.validation is not None and result.validation.passed


def test_agent_loop_never_returns_a_rejected_source_as_successful() -> None:
    task = BuildTask("Build a town", ("Workspace/Town/**",))
    rejected_program = _result(
        [_local_statement("1:1:1:2", "escape", _global("game"))],
        ("game",),
    )
    agent = AgentLoop(
        _QueueProvider("unsafe source"),
        LuauSourcePolicyValidator(_Parser(rejected_program)),
        iterations=IterationBudget(1),
        spend=SpendBudget(Decimal(0)),
    )

    result = agent.run(task)

    assert not result.succeeded
    assert result.source is None
    assert result.validation is not None and not result.validation.passed


def test_agent_loop_quotes_the_same_first_request_before_generation() -> None:
    class RecordingProvider(_QueueProvider):
        def __init__(self, source: str) -> None:
            super().__init__(source)
            self.requests: list[GenerationRequest] = []

        def quote_max_cost(self, request: GenerationRequest) -> CostQuote:
            self.requests.append(request)
            return CostQuote(Decimal("0.01"))

        def generate(self, request: GenerationRequest) -> GenerationResponse:
            self.requests.append(request)
            return super().generate(request)

    task = BuildTask("Build a town", ("Workspace/Town/**",))
    provider = RecordingProvider("safe scene source")
    agent = AgentLoop(
        provider,
        LuauSourcePolicyValidator(_Parser(_valid_program())),
        iterations=IterationBudget(1),
        spend=SpendBudget(Decimal("0.02")),
    )

    quote = agent.quote_next_call(task)
    result = agent.run(task)

    assert quote == CostQuote(Decimal("0.01"))
    assert result.succeeded
    assert provider.requests[0] == provider.requests[1] == provider.requests[2]
    assert any(
        "Skill pack roblox-studio-map-blockouts" in instruction.text
        for instruction in provider.requests[0].instructions
    )
    assert all(
        "Build a town" not in instruction.text for instruction in provider.requests[0].instructions
    )
    assert {item.source: item.text for item in provider.requests[0].untrusted}[
        "user_task"
    ] == "Build a town"


def test_agent_loop_adds_blender_and_character_skills_for_relevant_tasks() -> None:
    task = BuildTask(
        "Create a Blender mesh prop and animate an NPC character movement",
        ("Workspace/Town/**",),
    )
    provider = _QueueProvider("safe scene source")
    agent = AgentLoop(
        provider,
        LuauSourcePolicyValidator(_Parser(_valid_program())),
        iterations=IterationBudget(1),
        spend=SpendBudget(Decimal(0)),
    )

    result = agent.run(task)

    assert result.succeeded
    trusted_instructions = "\n".join(item.text for item in provider.requests[0].instructions)
    assert "Skill pack blender-scene-authoring" in trusted_instructions
    assert "Skill pack character-modeling-animation" in trusted_instructions
    assert "Skill pack world-environments" in trusted_instructions
