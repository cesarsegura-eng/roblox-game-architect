import json
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from core.budget import IterationBudget, SpendBudget
from core.game_planning import GamePlan, GamePlanningAgent, GamePlanningError
from core.llm.fake import FakeProvider
from core.llm.framing import render_trusted


def _plan_mapping() -> dict:
    return {
        "schema_version": 2,
        "title": "Sky Harbor",
        "genre": "Cooperative exploration",
        "pitch": "Players restore a floating harbor by exploring nearby islands.",
        "target_players": "Small cooperative groups; short sessions.",
        "core_loop": ["Choose a route", "Recover a resource", "Upgrade the harbor"],
        "systems": [
            {
                "name": "Exploration",
                "purpose": "Guide players between the harbor and island objectives.",
                "implementation_stage": "blockout",
            },
            {
                "name": "Resource collection",
                "purpose": "Give each expedition a clear return objective.",
                "implementation_stage": "later",
            },
            {
                "name": "Harbor upgrades",
                "purpose": "Show persistent progress between sessions.",
                "implementation_stage": "later",
            },
        ],
        "playable_slice": {
            "gameplay_mode": "blockout",
            "gameplay_rules": [],
            "included_systems": ["Exploration"],
            "deferred_systems": ["Resource collection", "Harbor upgrades"],
            "limitations": ["No custom gameplay code or persistent progression is included."],
        },
        "world_brief": (
            "Create a readable floating harbor hub with a central spawn, clear routes to "
            "three small island landmarks, safe return paths, and a sheltered interior workshop."
        ),
        "milestones": ["Greybox the hub", "Validate routes", "Prototype one expedition"],
        "validation_goals": [
            "Players can find the first island route",
            "The expedition has a clear return path",
            "The blockout stays readable at mobile scale",
        ],
    }


def test_game_plan_round_trips_and_rejects_extra_fields():
    plan = GamePlan.from_mapping(_plan_mapping())
    assert GamePlan.from_json(plan.to_json()) == plan
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "game-plan-v2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(plan.to_mapping())
    malformed = {**_plan_mapping(), "luau": "print('unsafe')"}
    with pytest.raises(GamePlanningError, match="unexpected or missing fields"):
        GamePlan.from_mapping(malformed)


def test_game_plan_v1_migrates_to_a_truthful_v2_blockout_slice():
    legacy = _plan_mapping()
    legacy["schema_version"] = 1
    legacy.pop("playable_slice")

    plan = GamePlan.from_mapping(legacy)

    assert plan.to_mapping()["schema_version"] == 2
    assert plan.playable_slice.gameplay_mode == "blockout"
    assert plan.playable_slice.included_systems == ("Exploration",)
    assert plan.playable_slice.deferred_systems == ("Resource collection", "Harbor upgrades")


def test_game_plan_accepts_data_driven_rule_game_mode():
    mapping = _plan_mapping()
    mapping["playable_slice"]["gameplay_mode"] = "rule_game"
    mapping["playable_slice"]["gameplay_rules"] = [
        {"trigger_role": "collectible", "action": "award_points", "amount": 2},
        {"trigger_role": "hazard", "action": "damage", "amount": 15},
        {"trigger_role": "landmark", "action": "award_win", "minimum_points": 6},
    ]

    plan = GamePlan.from_mapping(mapping)

    assert plan.playable_slice.gameplay_mode == "rule_game"
    assert plan.playable_slice.gameplay_rules[0].to_mapping() == {
        "trigger_role": "collectible",
        "action": "award_points",
        "amount": 2,
    }
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "game-plan-v2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(plan.to_mapping())


@pytest.mark.parametrize(
    "rules",
    [
        [],
        [{"trigger_role": "collectible", "action": "award_points", "amount": True}],
        [{"trigger_role": "landmark", "action": "award_win", "minimum_points": 0}],
        [{"trigger_role": "collectible", "action": "run_code", "source": "print(1)"}],
        [{"trigger_role": "collectible", "action": ["award_points"]}],
        [{"trigger_role": "prop", "action": "damage", "amount": 15}],
        [{"trigger_role": "landmark", "action": "award_win", "minimum_points": 5}],
        [
            {"trigger_role": "hazard", "action": "damage", "amount": 15},
            {"trigger_role": "hazard", "action": "eliminate"},
        ],
        [
            {"trigger_role": "hazard", "action": "eliminate"},
            {"trigger_role": "hazard", "action": "eliminate"},
        ],
    ],
)
def test_game_plan_rejects_missing_or_unsafe_data_rules(rules):
    mapping = _plan_mapping()
    mapping["playable_slice"]["gameplay_mode"] = "rule_game"
    mapping["playable_slice"]["gameplay_rules"] = rules

    with pytest.raises(
        GamePlanningError, match=r"rule|amount|unsupported|duplicate|minimum_points|requires"
    ):
        GamePlan.from_mapping(mapping)
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "game-plan-v2.schema.json"
    assert not Draft202012Validator(json.loads(schema_path.read_text())).is_valid(mapping)


def test_game_plan_allows_only_empty_rules_outside_rule_game():
    mapping = _plan_mapping()
    mapping["playable_slice"]["gameplay_rules"] = [
        {"trigger_role": "hazard", "action": "eliminate"}
    ]

    with pytest.raises(GamePlanningError, match="only in rule_game"):
        GamePlan.from_mapping(mapping)


@pytest.mark.parametrize(
    "invalid_slice",
    [
        {
            "gameplay_mode": "custom_code",
            "gameplay_rules": [],
            "included_systems": ["Exploration"],
            "deferred_systems": ["Resource collection", "Harbor upgrades"],
            "limitations": ["No custom code."],
        },
        {
            "gameplay_mode": "obby",
            "gameplay_rules": [],
            "included_systems": ["Exploration"],
            "deferred_systems": ["Resource collection"],
            "limitations": ["No custom code."],
        },
        {
            "gameplay_mode": "treasure_hunt",
            "gameplay_rules": [],
            "included_systems": ["Resource collection", "Exploration"],
            "deferred_systems": ["Harbor upgrades"],
            "limitations": ["No custom code."],
        },
    ],
)
def test_game_plan_rejects_unsupported_or_inconsistent_playable_slice(invalid_slice: dict):
    mapping = {**_plan_mapping(), "playable_slice": invalid_slice}

    with pytest.raises(GamePlanningError, match="playable_slice"):
        GamePlan.from_mapping(mapping)


def test_game_plan_rejects_duplicate_keys_and_duplicate_system_names():
    source = json.dumps(_plan_mapping())
    duplicate_key = source[:-1] + ',"title":"Injected"}'
    with pytest.raises(GamePlanningError, match="duplicate JSON keys"):
        GamePlan.from_json(duplicate_key)

    mapping = _plan_mapping()
    mapping["systems"][1]["name"] = mapping["systems"][0]["name"]
    with pytest.raises(GamePlanningError, match="names must be unique"):
        GamePlan.from_mapping(mapping)


def test_planner_quotes_and_returns_a_validated_plan_with_skills():
    provider = FakeProvider({"Design a cooperative exploration game": json.dumps(_plan_mapping())})
    spend = SpendBudget(Decimal("0.25"))
    agent = GamePlanningAgent(
        provider,
        iterations=IterationBudget(1),
        spend=spend,
    )
    brief = "Design a cooperative exploration game about restoring a floating harbor."
    quote = agent.quote_next_call(brief)
    result = agent.generate(brief)

    assert quote is not None and quote.max_usd == Decimal(0)
    assert result.plan.title == "Sky Harbor"
    assert result.skill_names == (
        "game-design-planning",
        "world-environments",
        "roblox-studio-map-blockouts",
    )
    trusted = render_trusted(provider.calls[0])
    assert "Do not output Luau, Python, commands" in trusted
    assert "Game Plan v2 JSON Schema" in trusted
    assert "gameplay_mode" in result.plan.playable_slice.to_mapping()
    assert "game-design-planning" in trusted
    assert spend.spent == 0
    assert spend.reserved == 0
