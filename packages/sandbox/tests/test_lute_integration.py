"""Smoke-test the exact Lute runtime when it is installed in the environment."""

import shutil
import subprocess
from pathlib import Path

import pytest

from core.agent_loop import BuildTask
from core.gameplay_templates import obby_course_source, rule_game_source, treasure_hunt_source
from sandbox.parser import LuteSyntaxParser, SyntaxCheckResult
from sandbox.source_policy import LuauSourcePolicyValidator

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("lute") is None, reason="Lute is not installed"),
]


def test_pinned_lute_parses_valid_and_invalid_source() -> None:
    parser = LuteSyntaxParser()

    assert parser.parse("local value = 1") == SyntaxCheckResult(syntax_valid=True)
    assert parser.parse("local =") == SyntaxCheckResult(syntax_valid=False)


def test_studio_plugin_source_parses_with_the_pinned_luau_parser() -> None:
    repository = Path(__file__).resolve().parents[3]
    source = (repository / "apps/studio-plugin/src/Main.plugin.lua").read_text(encoding="utf-8")

    assert LuteSyntaxParser().parse(source) == SyntaxCheckResult(syntax_valid=True)


def test_treasure_hunt_template_parses_with_the_pinned_luau_parser() -> None:
    assert LuteSyntaxParser().parse(treasure_hunt_source()) == SyntaxCheckResult(syntax_valid=True)


def test_studio_round_driver_parses_with_the_pinned_luau_parser() -> None:
    repository = Path(__file__).resolve().parents[3]
    source = (repository / "tools/studio_rainforest_round.luau").read_text(encoding="utf-8")
    assert LuteSyntaxParser().parse(source) == SyntaxCheckResult(syntax_valid=True)


def test_cloud_navigation_harness_parses_with_the_pinned_luau_parser() -> None:
    repository = Path(__file__).resolve().parents[3]
    source = (repository / "apps/roblox_mcp_server/harness.luau").read_text(encoding="utf-8")
    assert LuteSyntaxParser().parse(source) == SyntaxCheckResult(syntax_valid=True)


def test_cloud_navigation_checks_every_authored_leg(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[3]
    harness = (repository / "apps/roblox_mcp_server/harness.luau").read_text(encoding="utf-8")
    fixture = Path(__file__).with_name("navigation_simulation.luau").read_text(encoding="utf-8")
    script = tmp_path / "navigation.luau"
    script.write_text(fixture.replace("-- INSERT CLOUD HARNESS", harness), encoding="utf-8")
    subprocess.run(  # noqa: S603 - repository-owned harness and simulation only.
        [shutil.which("lute"), "run", str(script)], check=True, timeout=10
    )


def test_obby_course_template_parses_with_the_pinned_luau_parser() -> None:
    assert LuteSyntaxParser().parse(obby_course_source()) == SyntaxCheckResult(syntax_valid=True)


def test_rule_game_template_parses_with_the_pinned_luau_parser() -> None:
    assert LuteSyntaxParser().parse(rule_game_source()) == SyntaxCheckResult(syntax_valid=True)


def test_rule_game_validates_before_connecting_and_scores_per_round(tmp_path: Path) -> None:
    fixture = Path(__file__).with_name("rule_game_simulation.luau").read_text(encoding="utf-8")
    source = fixture.replace("-- INSERT TRUSTED TEMPLATE", rule_game_source())
    script = tmp_path / "simulate.luau"
    script.write_text(source, encoding="utf-8")
    subprocess.run(  # noqa: S603 - project-owned Luau source and fixture only.
        [shutil.which("lute"), "run", str(script)], check=True, timeout=10
    )


def test_pinned_lute_extracts_structured_cst_facts() -> None:
    parser = LuteSyntaxParser()

    result = parser.analyze(
        'local Players = game:GetService("Players")\n'
        'local root = game.Workspace["Folder"]\n'
        "while true do task.wait() end"
    )

    assert result.syntax_valid
    assert {"game", "task"} <= set(result.summary.globals)
    assert "game:GetService" in result.summary.access_chains
    assert "game:GetService" in result.summary.calls
    assert result.summary.bracket_index_count == 1
    assert "while" in result.summary.loop_kinds
    assert result.program["kind"] == "block"
    assert result.program["statements"][0]["kind"] == "local"
    assert result.program["statements"][2] == {"kind": "unsupported", "tag": "while"}


def test_pinned_lute_program_preserves_local_binding_identity() -> None:
    result = LuteSyntaxParser().analyze("local value = 1\nvalue = value + 2")

    declaration, assignment = result.program["statements"]
    binding_id = declaration["variables"][0]["id"]
    assert assignment["targets"][0]["binding"] == binding_id
    assert assignment["values"][0]["left"]["binding"] == binding_id


def test_pinned_lute_parses_long_strings_but_blockout_policy_rejects_them() -> None:
    source = "local modelClass = [[Part]]"
    analysis = LuteSyntaxParser().analyze(source)
    result = LuauSourcePolicyValidator().validate(
        source, BuildTask("Create a model blockout", ("Workspace/Model/**",))
    )

    assert analysis.syntax_valid
    assert not result.passed
    assert result.feedback == ("Only simple, bounded string literals are allowed.",)


def test_pinned_lute_policy_accepts_scoped_blockout_and_rejects_unsafe_code() -> None:
    validator = LuauSourcePolicyValidator()
    task = BuildTask("Create a road blockout", ("Workspace/Town/**",))
    safe = """
local town = Instance.new("Model")
town.Name = "Town"
town.Parent = workspace
local road = Instance.new("Part")
road.Name = "Road"
road.Size = Vector3.new(32, 1, 4)
road.Color = Color3.fromRGB(128, 90, 40)
road.Material = Enum.Material.Wood
road.Anchored = true
road.Parent = town
"""
    unsafe = safe.replace(
        "road.Parent = town",
        "road.Parent = town\nworkspace:GetChildren()",
    )

    assert validator.validate(safe, task).passed
    rejected = validator.validate(unsafe, task)
    assert not rejected.passed
    assert rejected.feedback == ("Only local declarations and property assignments are allowed.",)
