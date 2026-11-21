"""Review a proposed game and its map using the same contracts as the builders."""

from __future__ import annotations

from typing import Any

from core.game_planning import GamePlan
from core.gameplay_templates import validate_gameplay_mode
from core.worldbuilding import SceneRecipe, _required_scene_roles, _validate_requested_world_roles

TOOL_NAME = "rga_review_game_plan"


def tool_definition() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Check a Game Plan and optionally its Scene Recipe before building. Returns "
            "build settings for the planned playable slice and checks its role, route and "
            "gameplay requirements. This static review does not run Roblox or create an artifact."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"plan": {"type": "object"}, "recipe": {"type": "object"}},
            "required": ["plan"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    }


def review(arguments: dict[str, Any]) -> dict[str, Any]:
    plan = GamePlan.from_mapping(arguments["plan"])
    mode = plan.playable_slice.gameplay_mode
    rules = [rule.to_mapping() for rule in plan.playable_slice.gameplay_rules]
    roles = _required_scene_roles(plan.world_brief)
    if mode != "blockout":
        roles.add("path")
    if mode == "treasure_hunt":
        roles.add("collectible")
    roles.update(rule["trigger_role"] for rule in rules)
    settings: dict[str, Any] = {"gameplay_mode": mode}
    if rules:
        settings["gameplay_rules"] = rules
    if "recipe" in arguments:
        recipe = SceneRecipe.from_mapping(arguments["recipe"])
        validate_gameplay_mode(mode, recipe, rules or None)
        _validate_requested_world_roles(recipe, roles)
    return {
        "review": "plan_and_recipe" if "recipe" in arguments else "plan_only",
        "build_settings": settings,
        "required_scene_roles": sorted(roles),
    }


def validate_build_request(
    plan: object,
    recipe: object,
    gameplay_mode: object,
    gameplay_rules: object,
) -> None:
    """Bind one built artifact request to the reviewed plan and scene recipe."""
    checked = review({"plan": plan, "recipe": recipe})
    expected = checked["build_settings"]
    supplied: dict[str, Any] = {"gameplay_mode": gameplay_mode}
    if gameplay_rules is not None:
        supplied["gameplay_rules"] = gameplay_rules
    if supplied != expected:
        raise ValueError("build settings do not match the reviewed Game Plan playable slice")
