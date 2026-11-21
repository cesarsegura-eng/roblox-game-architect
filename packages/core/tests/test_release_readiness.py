from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from core.game_planning import GamePlanningError
from core.release_readiness import review_release_readiness


def _plan() -> dict[str, object]:
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
                "purpose": "Reach island objectives.",
                "implementation_stage": "blockout",
            },
            {
                "name": "Resources",
                "purpose": "Save persistent progress after each expedition.",
                "implementation_stage": "later",
            },
            {
                "name": "Harbor upgrades",
                "purpose": "Show long-term player progress.",
                "implementation_stage": "later",
            },
        ],
        "playable_slice": {
            "gameplay_mode": "blockout",
            "gameplay_rules": [],
            "included_systems": ["Exploration"],
            "deferred_systems": ["Resources", "Harbor upgrades"],
            "limitations": ["Persistent progression is not included in the first slice."],
        },
        "world_brief": (
            "Create a readable floating harbor hub with a central spawn, clear routes to "
            "three island landmarks, safe return paths, and a sheltered workshop interior."
        ),
        "milestones": ["Greybox the hub", "Validate routes", "Prototype one expedition"],
        "validation_goals": [
            "Players can find the first island route",
            "Players can return from an expedition",
            "The blockout reads at mobile scale",
        ],
    }


def test_release_readiness_report_is_evidence_oriented_and_fails_closed() -> None:
    report = review_release_readiness(_plan())
    schema_path = (
        Path(__file__).resolve().parents[1] / "schemas" / "release-readiness-v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.validate(report)

    assert report["schema_version"] == 1
    assert report["readiness"] == "not_ready"
    assert report["verified_gate_count"] == 0
    gates = {gate["id"]: gate for gate in report["gates"]}
    assert report["pending_gate_count"] == len(gates) == 9
    assert gates["persistence_and_recovery"]["applicability"] == "likely_in_scope"
    assert gates["persistence_and_recovery"]["status"] == "pending"
    assert gates["human_release_approval"]["owner_role"] == "authorized_human_reviewer"
    assert "No evidence was supplied" in report["notice"]
    asset_evidence = gates["content_rights_and_safety"]["evidence_required"]
    assert any("Structural validation receipts" in item for item in asset_evidence)
    assert any("Roblox import and render review" in item for item in asset_evidence)

    falsely_verified = json.loads(json.dumps(report))
    falsely_verified["gates"][0]["status"] = "verified"
    assert not validator.is_valid(falsely_verified)


def test_release_readiness_keeps_unknown_feature_scope_for_owner_review() -> None:
    plan = _plan()
    plan["systems"] = [
        {"name": "Exploration", "purpose": "Find islands.", "implementation_stage": "blockout"},
        {"name": "Scenery", "purpose": "Show the harbor.", "implementation_stage": "later"},
        {"name": "Landmarks", "purpose": "Orient visitors.", "implementation_stage": "later"},
    ]
    plan["playable_slice"] = {
        "gameplay_mode": "blockout",
        "gameplay_rules": [],
        "included_systems": ["Exploration"],
        "deferred_systems": ["Scenery", "Landmarks"],
        "limitations": ["No persistence or commerce is included."],
    }
    report = review_release_readiness(plan)
    gates = {gate["id"]: gate for gate in report["gates"]}

    assert gates["persistence_and_recovery"]["applicability"] == "owner_scope_decision_required"
    assert gates["commerce_and_policy"]["applicability"] == "owner_scope_decision_required"
    assert gates["multiplayer_and_network"]["applicability"] == "likely_in_scope"


def test_datastore_service_does_not_get_mistaken_for_monetization() -> None:
    plan = _plan()
    plan["systems"][1]["purpose"] = "Persist versioned player profiles with DataStoreService."
    report = review_release_readiness(plan)
    gates = {gate["id"]: gate for gate in report["gates"]}

    assert gates["persistence_and_recovery"]["applicability"] == "likely_in_scope"
    assert gates["commerce_and_policy"]["applicability"] == "owner_scope_decision_required"

    plan["systems"][1]["purpose"] += " Also sell optional developer products."
    report = review_release_readiness(plan)
    gates = {gate["id"]: gate for gate in report["gates"]}
    assert gates["persistence_and_recovery"]["applicability"] == "likely_in_scope"
    assert gates["commerce_and_policy"]["applicability"] == "likely_in_scope"


def test_session_only_progression_does_not_imply_persistence_or_commerce() -> None:
    plan = _plan()
    plan["systems"][1]["purpose"] = (
        "Design comprehensive progression; it does not save player data."
    )
    plan["playable_slice"]["limitations"] = ["Progression resets when this session ends."]
    report = review_release_readiness(plan)
    gates = {gate["id"]: gate for gate in report["gates"]}

    assert gates["persistence_and_recovery"]["applicability"] == "owner_scope_decision_required"
    assert gates["commerce_and_policy"]["applicability"] == "owner_scope_decision_required"


@pytest.mark.parametrize(
    "purpose",
    [
        "Progression resets every session; the game does not save player data.",
        "El progreso dura solo durante la sesión y no se guarda.",
    ],
)
def test_session_only_progression_requires_owner_scope_decision(purpose: str) -> None:
    plan = _plan()
    plan["systems"][1]["purpose"] = purpose
    plan["playable_slice"]["limitations"] = ["State lasts only in the current session."]

    report = review_release_readiness(plan)
    gates = {gate["id"]: gate for gate in report["gates"]}

    assert gates["persistence_and_recovery"]["applicability"] == "owner_scope_decision_required"


def test_explicit_persistence_requirement_survives_a_session_only_slice_note() -> None:
    plan = _plan()
    plan["playable_slice"]["limitations"] = [
        "Persistent progression is deferred from this first slice."
    ]
    report = review_release_readiness(plan)
    gates = {gate["id"]: gate for gate in report["gates"]}

    assert gates["persistence_and_recovery"]["applicability"] == "likely_in_scope"


def test_release_readiness_detects_pvp_without_other_multiplayer_cues() -> None:
    plan = _plan()
    plan["genre"] = "Combat arena"
    plan["pitch"] = "A solo training challenge against NPC opponents."
    plan["target_players"] = "One player per session."
    plan["core_loop"] = ["Enter the arena", "Defeat a training dummy", "Claim a score"]
    plan["systems"] = [
        {
            "name": "Training combat",
            "purpose": "Fight NPC targets.",
            "implementation_stage": "blockout",
        },
        {
            "name": "Score display",
            "purpose": "Show the current training score.",
            "implementation_stage": "later",
        },
        {
            "name": "Arena scenery",
            "purpose": "Provide a readable training space.",
            "implementation_stage": "later",
        },
    ]
    plan["playable_slice"] = {
        "gameplay_mode": "blockout",
        "gameplay_rules": [],
        "included_systems": ["Training combat"],
        "deferred_systems": ["Score display", "Arena scenery"],
        "limitations": ["The first slice only uses placeholder scoring."],
    }

    plan["pitch"] = "A PvP combat arena with a single duel mode."
    report = review_release_readiness(plan)
    gates = {gate["id"]: gate for gate in report["gates"]}
    assert gates["multiplayer_and_network"]["applicability"] == "likely_in_scope"

    plan["pitch"] = "A player-versus-player combat arena with a single duel mode."
    report = review_release_readiness(plan)
    gates = {gate["id"]: gate for gate in report["gates"]}
    assert gates["multiplayer_and_network"]["applicability"] == "likely_in_scope"

    plan["pitch"] = "A 1v1 combat arena with a single duel mode."
    report = review_release_readiness(plan)
    gates = {gate["id"]: gate for gate in report["gates"]}
    assert gates["multiplayer_and_network"]["applicability"] == "likely_in_scope"


def test_release_readiness_rejects_unvalidated_plan_fields() -> None:
    plan = _plan()
    plan["unsafe_source"] = "print('run me')"
    with pytest.raises(GamePlanningError, match="unexpected or missing fields"):
        review_release_readiness(plan)
