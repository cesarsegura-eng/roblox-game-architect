"""Evidence-oriented release gates for a validated Game Plan.

This module creates a review checklist only. It has no Roblox credentials,
cannot inspect a place, and never marks a release gate as passed.
"""

from __future__ import annotations

import re
from typing import Any

from .game_planning import GamePlan

_PERSISTENCE = re.compile(
    r"\b(save|saved|saving|persist|persistent|guardar|guardado|persistencia)\b",
    re.I,
)
_PROGRESSION = re.compile(r"\b(progression|progreso)\b", re.I)
_SESSION_ONLY = re.compile(
    r"\b(session[- ]only|only (?:for|during) (?:a )?session|"
    r"not saved|does not save|doesn't save|not persistent|does not persist|"
    r"doesn't persist|not persisted|no saves?|no saving|no persistence|"
    r"solo (?:durante la )?sesi[oó]n|no se guarda|sin guardado|sin persistencia)\b",
    re.I,
)
_DATA_STORE = re.compile(r"\bdata[\s_-]*stores?(?:service)?\b", re.I)
_COMMERCE = re.compile(
    r"\b(monetiz\w*|purchas\w*|game pass(?:es)?|developer products?|shops?|"
    r"(?:in[- ]game|item|cosmetic|robux) stores?|receipts?|"
    r"compra(?:s|r|do|ndo|n)?|tiendas?|pagos?|pagar|pagado|pagando)\b",
    re.I,
)
_MULTIPLAYER = re.compile(
    r"\b(pvp|player[- ]+(?:versus|vs\.?)[- ]*player|[1-9]v[1-9]|battle[- ]+royale|"
    r"multiplayer|multi-player|co-op|cooperative|competitive|trading|party|matchmaking|"
    r"social|multijugador|cooperativo|competitivo|intercambio)\b",
    re.I,
)


def review_release_readiness(plan_payload: object) -> dict[str, Any]:
    """Create pending, plan-specific production gates without asserting evidence."""
    plan = GamePlan.from_mapping(plan_payload)
    searchable = "\n".join(
        (
            plan.genre,
            plan.pitch,
            plan.target_players,
            *plan.core_loop,
            *(f"{system.name} {system.purpose}" for system in plan.systems),
            plan.world_brief,
            *plan.milestones,
            *plan.validation_goals,
        )
    )
    commerce_searchable = _DATA_STORE.sub(" ", searchable)
    session_only = bool(_SESSION_ONLY.search(searchable))
    affirmative_searchable = _SESSION_ONLY.sub(" ", searchable)
    explicit_persistence = bool(
        _PERSISTENCE.search(affirmative_searchable) or _DATA_STORE.search(affirmative_searchable)
    )
    progression_without_scope = bool(
        _PROGRESSION.search(affirmative_searchable) and not session_only
    )
    gates = [
        _gate(
            "release_scope",
            "Release scope and player targets",
            "design_owner",
            "required",
            "Set the intended audience, supported devices/input, regions, languages, "
            "concurrency, and release channel.",
            ["Approved target matrix", "Reviewed first-session and accessibility criteria"],
        ),
        _gate(
            "server_authority_and_abuse",
            "Server authority and abuse cases",
            "gameplay_engineer",
            "required",
            "Review every state-changing interaction and verify server-side validation, "
            "rate limits, replay handling, and malformed-input behavior.",
            [
                "Reviewed server/client boundary",
                "Automated abuse-case results for exposed interactions",
            ],
        ),
        _gate(
            "persistence_and_recovery",
            "Persistence, migration, and recovery",
            "backend_engineer",
            "likely_in_scope"
            if explicit_persistence or progression_without_scope
            else "owner_scope_decision_required",
            "If the game saves state, test versioned data, corrupt/default data, migration, "
            "duplicate writes, outage recovery, and rollback in a separate experience.",
            [
                "Owner decision on whether data persists",
                "If applicable: migration, failure-injection, and rollback results",
            ],
        ),
        _gate(
            "commerce_and_policy",
            "Commerce, receipts, and eligibility",
            "commerce_owner",
            "likely_in_scope"
            if _COMMERCE.search(commerce_searchable)
            else "owner_scope_decision_required",
            "If purchases or monetization exist, verify server-side receipt idempotency, retries, "
            "eligibility, unavailable paths, and current Creator Hub rules.",
            [
                "Owner decision on whether commerce exists",
                "If applicable: receipt retry/duplicate tests and policy review",
            ],
        ),
        _gate(
            "multiplayer_and_network",
            "Multiplayer and network conditions",
            "gameplay_qa",
            "likely_in_scope"
            if _MULTIPLAYER.search(searchable)
            else "owner_scope_decision_required",
            "Test player count, late joins, reconnects, disconnects, empty/full servers, "
            "and representative latency when the experience uses multiplayer or networked state.",
            [
                "Owner decision on player/network scope",
                "If applicable: recorded multi-client and network test results",
            ],
        ),
        _gate(
            "device_playability_and_performance",
            "Playability, accessibility, and performance",
            "qa_and_performance_owner",
            "required",
            "Play complete sessions on target devices, controls, and network conditions; profile "
            "assembled place against declared frame-time, memory, and join-time budgets.",
            [
                "Device/input test matrix",
                "Representative Studio playtest results",
                "Performance budgets and profile",
            ],
        ),
        _gate(
            "content_rights_and_safety",
            "Content, asset rights, and platform review",
            "human_content_owner",
            "required",
            "Review asset ownership/licenses, audience suitability, content maturity, privacy, "
            "moderation, and current platform requirements.",
            [
                "Human-reviewed asset inventory, rights, provenance, and suitability",
                "Structural validation receipts for generated meshes, textures, rigs, "
                "and animations",
                "Roblox import and render review for representative generated assets",
                "Recorded content moderation and platform-policy review",
            ],
        ),
        _gate(
            "operations_and_rollback",
            "Monitoring, incident response, and rollback",
            "operations_owner",
            "required",
            "Define launch monitoring, error/progression/purchase signals, data minimization, "
            "incident ownership, rollback, and a post-release review window.",
            [
                "Monitoring and retention plan",
                "Named incident owner",
                "Successful rollback rehearsal",
            ],
        ),
        _gate(
            "human_release_approval",
            "Final release approval",
            "authorized_human_reviewer",
            "required",
            "An authorized person reviews the release candidate and all applicable evidence "
            "before public release.",
            [
                "Release-candidate identifier",
                "Human approval record",
                "Unresolved-gate disposition",
            ],
        ),
    ]
    return {
        "schema_version": 1,
        "plan_title": plan.title,
        "readiness": "not_ready",
        "verified_gate_count": 0,
        "pending_gate_count": len(gates),
        "notice": (
            "This is a planning checklist, not a Roblox runtime or policy certification. "
            "No evidence was supplied to this review; an owner must resolve each scope decision, "
            "verify reproducible evidence, and obtain human release approval."
        ),
        "gates": gates,
    }


def _gate(
    gate_id: str,
    title: str,
    owner: str,
    applicability: str,
    verification_method: str,
    evidence_required: list[str],
) -> dict[str, Any]:
    return {
        "id": gate_id,
        "title": title,
        "owner_role": owner,
        "applicability": applicability,
        "status": "pending",
        "verification_method": verification_method,
        "evidence_required": evidence_required,
        "evidence": [],
    }
