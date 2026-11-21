"""The lifecycle of a unit of work: sessions, delivery, results and the lock.

This implements ADR-0011, which stays **Proposed** only because no plugin has been
exercised against Studio. Three choices the record once left open are decided there
("Decisions taken on 2026-11-07") and are marked where they are made:

1. how two results are compared, to tell a duplicate from a conflict (section 5);
2. what the digest of a retried request is computed over (section 6);
3. what the API answers when a `message_id` is repeated with different content — the
   record leaves `message_id_reuse` unadded, so `invalid_message` is used.

The governing rule is kept whatever those become: **a unit of work whose outcome is
uncertain is never run again automatically.**
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from sandbox.action_policy import ActionPolicyError, validate_work_item

from .json_profile import ProfileError, parse_strict
from .messages import (
    MessageError,
    Request,
    error_response,
    ok_response,
    validate_request,
)
from .store import Store

# Longer than the longest playtest (600 s, docs/protocol/README.md) plus a margin, so a
# report does not arrive late merely because the plugin was running a test.
# Decided in ADR-0011 (2026-11-07): the session inactivity limit.
DEFAULT_INACTIVITY_S = 900.0

WORK_KINDS = ("edit.action", "playtest.request")
GENERATION_OPERATIONS = frozenset(
    {"blender_scene_recipe", "studio_blockout", "game_plan", "luau_source_preview"}
)

# The highest minor of major 1 this API speaks. The negotiated minor is the lower of
# this and the plugin's (docs/protocol/README.md, Handshake).
API_MAX_MINOR = 0


@dataclass(frozen=True)
class Outcome:
    """What the service decided: the envelope to send, and whether to hold the poll open."""

    response: dict[str, Any]
    hold: bool = False


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8)}"


def _validate_model_trace(value: object) -> None:
    required = {
        "provider",
        "model",
        "iterations",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "attempts",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("generation model trace is malformed")
    attempts = value["attempts"]
    if (
        not isinstance(attempts, list)
        or not 1 <= len(attempts) <= 128
        or type(value["iterations"]) is not int
        or value["iterations"] != len(attempts)
    ):
        raise ValueError("generation model trace attempts are malformed")
    providers: set[str] = set()
    models: set[str] = set()
    input_tokens = 0
    output_tokens = 0
    cost = Decimal(0)
    for number, attempt in enumerate(attempts, start=1):
        keys = {"attempt", "provider", "model", "input_tokens", "output_tokens", "cost_usd"}
        if not isinstance(attempt, dict) or set(attempt) != keys:
            raise ValueError("generation model trace attempt is malformed")
        if (
            type(attempt["attempt"]) is not int
            or attempt["attempt"] != number
            or any(
                not isinstance(attempt[field], str)
                or not 1 <= len(attempt[field]) <= 80
                or any(ord(char) < 32 or ord(char) == 127 for char in attempt[field])
                for field in ("provider", "model")
            )
            or any(
                type(attempt[field]) is not int or not 0 <= attempt[field] <= 10_000_000
                for field in ("input_tokens", "output_tokens")
            )
            or not isinstance(attempt["cost_usd"], str)
            or not 1 <= len(attempt["cost_usd"]) <= 64
        ):
            raise ValueError("generation model trace attempt fields are invalid")
        try:
            attempt_cost = Decimal(attempt["cost_usd"])
        except (InvalidOperation, ValueError):
            raise ValueError("generation model trace attempt cost is invalid") from None
        if not attempt_cost.is_finite() or attempt_cost < 0 or attempt_cost > 1_000_000:
            raise ValueError("generation model trace attempt cost is invalid")
        providers.add(attempt["provider"])
        models.add(attempt["model"])
        input_tokens += attempt["input_tokens"]
        output_tokens += attempt["output_tokens"]
        cost += attempt_cost
    provider_label = ", ".join(sorted(providers))
    model_label = ", ".join(sorted(models))
    if (
        not isinstance(value["provider"], str)
        or not isinstance(value["model"], str)
        or len(value["provider"]) > 120
        or len(value["model"]) > 120
        or any(
            type(value[field]) is not int or value[field] < 0
            for field in ("input_tokens", "output_tokens")
        )
        or not isinstance(value["cost_usd"], str)
        or not 1 <= len(value["cost_usd"]) <= 64
        or value["provider"] != provider_label
        or value["model"] != model_label
        or value["input_tokens"] != input_tokens
        or value["output_tokens"] != output_tokens
        or value["cost_usd"] != str(cost)
    ):
        raise ValueError("generation model trace totals do not match its calls")


def _generation_event_details(
    *,
    run_id: str,
    operation: str,
    succeeded: bool,
    duration_ms: int,
    summary: dict[str, Any] | None = None,
    failure_stage: str = "generation",
) -> tuple[str, dict[str, Any]]:
    summary = {} if summary is None else summary
    if (
        operation not in GENERATION_OPERATIONS
        or type(succeeded) is not bool
        or type(duration_ms) is not int
        or not 0 <= duration_ms <= 3_600_000
        or not isinstance(summary, dict)
    ):
        raise ValueError("generation audit details are invalid")
    try:
        canonical_run_id = str(uuid.UUID(run_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("generation audit run_id must be a UUID") from exc
    if not succeeded:
        if summary or failure_stage not in {"generation", "validation", "queue"}:
            raise ValueError("failed generation audit details are invalid")
        detail: dict[str, Any] = {"failure_stage": failure_stage}
        kind = "model_generation_failed"
    elif operation == "blender_scene_recipe":
        required = {"object_count", "light_count", "character_count", "output_bytes"}
        if frozenset(summary) not in {
            frozenset(required),
            frozenset(required | {"model_trace"}),
        } or any(type(summary[key]) is not int or summary[key] < 0 for key in required):
            raise ValueError("scene recipe audit summary is invalid")
        if "model_trace" in summary:
            _validate_model_trace(summary["model_trace"])
        if summary["output_bytes"] > 1_048_576:
            raise ValueError("scene recipe audit output exceeds its limit")
        detail = dict(summary)
        kind = "model_generation_succeeded"
    elif operation == "luau_source_preview":
        required = {"iterations", "source_bytes"}
        allowed = {frozenset(required), frozenset(required | {"model_trace"})}
        if (
            frozenset(summary) not in allowed
            or type(summary["iterations"]) is not int
            or not 1 <= summary["iterations"] <= 128
            or type(summary["source_bytes"]) is not int
            or not 1 <= summary["source_bytes"] <= 100_000
        ):
            raise ValueError("Luau source preview audit summary is invalid")
        if "model_trace" in summary:
            _validate_model_trace(summary["model_trace"])
        detail = dict(summary)
        kind = "model_generation_succeeded"
    elif operation == "game_plan":
        base = {"system_count", "milestone_count", "output_bytes"}
        trace = {
            "provider",
            "model",
            "iterations",
            "input_tokens",
            "output_tokens",
            "cost_usd",
        }
        summary_keys = frozenset(summary)
        if summary_keys not in {
            frozenset(base),
            frozenset(base | trace),
            frozenset(base | trace | {"model_trace"}),
        } or any(type(summary[key]) is not int or summary[key] < 0 for key in base):
            raise ValueError("game plan audit summary is invalid")
        if (
            not 3 <= summary["system_count"] <= 10
            or not 3 <= summary["milestone_count"] <= 10
            or not 1 <= summary["output_bytes"] <= 65_536
        ):
            raise ValueError("game plan audit summary is outside its bounds")
        if trace <= set(summary):
            if any(
                not isinstance(summary[field], str)
                or not summary[field]
                or len(summary[field]) > 120
                or any(ord(char) < 32 for char in summary[field])
                for field in ("provider", "model")
            ):
                raise ValueError("game plan model trace labels are invalid")
            if (
                type(summary["iterations"]) is not int
                or not 1 <= summary["iterations"] <= 128
                or any(
                    type(summary[field]) is not int or not 0 <= summary[field] <= 10_000_000
                    for field in ("input_tokens", "output_tokens")
                )
                or not isinstance(summary["cost_usd"], str)
                or not 1 <= len(summary["cost_usd"]) <= 64
            ):
                raise ValueError("game plan model trace usage is invalid")
            try:
                cost = Decimal(summary["cost_usd"])
            except (InvalidOperation, ValueError):
                raise ValueError("game plan model trace cost is invalid") from None
            if not cost.is_finite() or cost < 0 or cost > 1_000_000:
                raise ValueError("game plan model trace cost is invalid")
        if "model_trace" in summary:
            _validate_model_trace(summary["model_trace"])
            model_trace = summary["model_trace"]
            if any(summary[field] != model_trace[field] for field in trace):
                raise ValueError("game plan aggregate trace differs from its calls")
        detail = dict(summary)
        kind = "model_generation_succeeded"
    else:
        required = {"action_id", "operation_count"}
        if (
            frozenset(summary) not in {frozenset(required), frozenset(required | {"model_trace"})}
            or not isinstance(summary["action_id"], str)
            or not 1 <= len(summary["action_id"]) <= 80
            or type(summary["operation_count"]) is not int
            or not 1 <= summary["operation_count"] <= 256
        ):
            raise ValueError("Studio blockout audit summary is invalid")
        if "model_trace" in summary:
            _validate_model_trace(summary["model_trace"])
        detail = dict(summary)
        kind = "model_generation_succeeded"
    return kind, {
        "run_id": canonical_run_id,
        "operation": operation,
        "duration_ms": duration_ms,
        **detail,
    }


def _blank_state() -> dict[str, Any]:
    return {
        "session": None,
        "work": {},
        "lock": {"engaged": False, "triggers": []},
        "snapshots": [],
        "current_snapshot": None,
        "recovered": True,
        "replay": {},
        "hello_replay": {},
        "events": [],
    }


class Service:
    """The protocol engine for one API process. Transport-free and testable directly."""

    def __init__(
        self,
        store: Store,
        *,
        clock: Callable[[], float] = time.monotonic,
        inactivity_s: float = DEFAULT_INACTIVITY_S,
        server_version: str = "0.0.0",
    ) -> None:
        self._store = store
        self._clock = clock
        self._inactivity_s = inactivity_s
        self._server_version = server_version

    # ------------------------------------------------------------------ state

    def _load(self, credential: str) -> dict[str, Any]:
        return self._store.load(credential) or _blank_state()

    def _commit(self, credential: str, state: dict[str, Any]) -> None:
        self._store.commit(credential, state)

    def _record(self, state: dict[str, Any], kind: str, **detail: object) -> None:
        """Append to the event history, which is the source of truth for audit."""
        state["events"].append(
            {"at": time.time(), "kind": kind, "session": _session_id(state), **detail}
        )

    # ------------------------------------------------------------------ operator surface

    def queue(
        self,
        credential: str,
        item: dict[str, Any],
        *,
        generation_run_id: str | None = None,
        generation_duration_ms: int | None = None,
        generation_model_trace: dict[str, Any] | None = None,
        workflow_id: str | None = None,
    ) -> str:
        """Add a work item as `queued`. It is delivered only after an approval."""
        if not isinstance(item, dict):
            raise ValueError("work item must be an object")
        kind = item.get("type")
        if kind not in WORK_KINDS:
            raise ValueError(f"a work item is one of {WORK_KINDS}, not {kind!r}")
        validate_work_item(item)
        work_id = item.get("action_id" if kind == "edit.action" else "playtest_id")
        if not isinstance(work_id, str) or not work_id:
            raise ValueError("a work item carries its own id")
        if (generation_run_id is None) != (generation_duration_ms is None):
            raise ValueError("generation trace needs both a run ID and duration")
        if generation_run_id is None and generation_model_trace is not None:
            raise ValueError("model call trace needs a generation run ID")
        if workflow_id is not None:
            try:
                workflow_id = str(uuid.UUID(workflow_id))
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError("workflow_id must be a UUID") from exc
        generation_detail = None
        if generation_run_id is not None:
            if kind != "edit.action":
                raise ValueError("only generated Studio edit actions can carry a model run trace")
            generation_detail = _generation_event_details(
                run_id=generation_run_id,
                operation="studio_blockout",
                succeeded=True,
                duration_ms=generation_duration_ms,
                summary={
                    "action_id": work_id,
                    "operation_count": len(item["operations"]),
                    **(
                        {"model_trace": generation_model_trace}
                        if generation_model_trace is not None
                        else {}
                    ),
                },
            )
        state = self._load(credential)
        if work_id in state["work"]:
            raise ValueError(f"{work_id} already exists")
        state["work"][work_id] = {
            "kind": kind,
            "item": item,
            "state": "queued",
            "knowledge": "none",
            "deliveries": 0,
            "delivered_in": None,
            "result": None,
            "stale_base": False,
        }
        self._record(
            state,
            "queued",
            work_id=work_id,
            **({"workflow_id": workflow_id} if workflow_id is not None else {}),
        )
        if generation_detail is not None:
            kind_name, details = generation_detail
            self._record(state, kind_name, **details)
        self._commit(credential, state)
        return work_id

    def approve(self, credential: str, work_id: str) -> None:
        """A human approval. Nothing is delivered without one (ADR-0002)."""
        state = self._load(credential)
        entry = state["work"].get(work_id)
        if entry is None:
            raise ValueError(f"no such work item: {work_id}")
        if entry["state"] != "queued":
            raise ValueError(f"{work_id} is {entry['state']}, not queued")
        try:
            validate_work_item(entry["item"])
        except ActionPolicyError as exc:
            raise ValueError(f"{work_id} is blocked by execution policy: {exc}") from exc
        if state["lock"]["engaged"]:
            # RD3 would return it to `queued` at once, and nothing is delivered while the
            # lock holds. An approval now would be planned against a state nobody has.
            raise ValueError("the lock is engaged: attest first, then plan against a snapshot")
        if not state["recovered"]:
            raise ValueError(
                "no fresh snapshot since the lock was released; planning cannot resume"
            )
        entry["state"] = "approved"
        entry["stale_base"] = False
        self._record(state, "approved", work_id=work_id)
        self._commit(credential, state)

    def attest(self, credential: str, actor: str, warning: str, review: str | None = None) -> None:
        """Release the lock on a human declaration that the executor has stopped.

        The declaration is not a technical guarantee: the API has no way to check that no
        Studio instance is still applying an item (ADR-0011 sections 1 and 7). A conflict
        also needs a recorded review of the two incompatible results.
        """
        state = self._load(credential)
        if not state["lock"]["engaged"]:
            raise ValueError("the lock is not engaged")
        if any(t["trigger"] == "T4" for t in state["lock"]["triggers"]) and not review:
            raise ValueError("a conflict needs a recorded review of both results")
        self._record(state, "attestation_recorded", actor=actor, warning=warning, review=review)
        state["lock"] = {"engaged": False, "triggers": []}
        state["recovered"] = False
        self._record(state, "lock_released", evidence="attestation")
        self._commit(credential, state)

    def has_deliverable(self, credential: str) -> bool:
        """Whether a poll would be answered with work now. Reads; never writes."""
        state = self._load(credential)
        if state["lock"]["engaged"]:
            return False
        session_id = _session_id(state)
        return any(
            entry["state"] == "approved"
            or (entry["state"] == "delivered" and entry["delivered_in"] == session_id)
            for entry in state["work"].values()
        )

    def status(self, credential: str) -> dict[str, Any]:
        """A read-only view, for an operator and for tests."""
        state = self._load(credential)
        return {
            "session": _session_id(state),
            "locked": state["lock"]["engaged"],
            "triggers": [t["trigger"] for t in state["lock"]["triggers"]],
            "recovered": state["recovered"],
            "current_snapshot": state["current_snapshot"],
            "work": {
                work_id: {
                    "kind": entry["kind"],
                    "state": entry["state"],
                    "knowledge": entry["knowledge"],
                    "deliveries": entry["deliveries"],
                    "stale_base": entry["stale_base"],
                }
                for work_id, entry in state["work"].items()
            },
            "events": len(state["events"]),
        }

    def operator_work_items(self, credential: str) -> list[dict[str, Any]]:
        """Return reviewable queued work to the authenticated local operator UI."""
        state = self._load(credential)
        return [
            {
                "work_id": work_id,
                "item": entry["item"],
                "state": entry["state"],
                "knowledge": entry["knowledge"],
                "deliveries": entry["deliveries"],
                "stale_base": entry["stale_base"],
            }
            for work_id, entry in state["work"].items()
        ]

    def operator_events(
        self, credential: str, *, limit: int = 100
    ) -> tuple[list[dict[str, Any]], int]:
        """Return the newest lifecycle audit entries and their total count."""
        if not 1 <= limit <= 500:
            raise ValueError("operator event limit must be between 1 and 500")
        events = self._load(credential)["events"]
        return [dict(event) for event in events[-limit:]], len(events)

    def record_blender_artifact_built(
        self,
        credential: str,
        *,
        recipe_name: str,
        object_count: int,
        request_id: str,
        artifact_id: str,
        artifact_sha256: str,
        remote_host: str,
    ) -> None:
        """Record a remote GLB build without retaining the scene recipe."""
        if (
            not recipe_name
            or not 1 <= object_count <= 528
            or not request_id
            or not artifact_id
            or not re.fullmatch(r"[0-9a-f]{64}", artifact_sha256)
            or not remote_host
        ):
            raise ValueError("Blender artifact audit details are invalid")
        state = self._load(credential)
        self._record(
            state,
            "blender_artifact_built",
            recipe_name=recipe_name[:64],
            object_count=object_count,
            request_id=request_id,
            artifact_id=artifact_id,
            artifact_sha256=artifact_sha256,
            remote_host=remote_host,
        )
        self._commit(credential, state)

    def record_roblox_model_asset_uploaded(
        self,
        credential: str,
        *,
        request_id: str,
        approval_id: str,
        artifact_sha256: str,
        asset_id: str,
        moderation_state: str,
        status: str,
        remote_host: str,
    ) -> None:
        """Audit a reviewed model upload without retaining its GLB or credentials."""
        try:
            request_id = str(uuid.UUID(request_id))
            approval_id = str(uuid.UUID(approval_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("Roblox asset request and approval IDs must be UUIDs") from exc
        if (
            not re.fullmatch(r"[0-9a-f]{64}", artifact_sha256)
            or not re.fullmatch(r"[1-9][0-9]{0,19}", asset_id)
            or not moderation_state.startswith("MODERATION_STATE_")
            or status not in {"approved", "moderation_pending", "rejected"}
            or not remote_host
            or len(remote_host) > 253
        ):
            raise ValueError("Roblox asset upload audit details are invalid")
        state = self._load(credential)
        self._record(
            state,
            "roblox_model_asset_uploaded",
            request_id=request_id,
            approval_id=approval_id,
            artifact_sha256=artifact_sha256,
            asset_id=asset_id,
            moderation_state=moderation_state,
            status=status,
            remote_host=remote_host,
        )
        self._commit(credential, state)

    def record_roblox_place_published(
        self,
        credential: str,
        *,
        request_id: str,
        approval_id: str,
        artifact_sha256: str,
        universe_id: str,
        place_id: str,
        version_number: int,
        remote_host: str,
    ) -> None:
        """Audit a digest-bound publish receipt without retaining place contents."""
        try:
            request_id = str(uuid.UUID(request_id))
            approval_id = str(uuid.UUID(approval_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("Roblox publish request and approval IDs must be UUIDs") from exc
        numeric_id = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
        if (
            not re.fullmatch(r"[0-9a-f]{64}", artifact_sha256)
            or not numeric_id.fullmatch(universe_id)
            or not numeric_id.fullmatch(place_id)
            or type(version_number) is not int
            or version_number < 1
            or not remote_host
            or len(remote_host) > 253
        ):
            raise ValueError("Roblox publish audit details are invalid")
        state = self._load(credential)
        duplicate = any(
            event.get("kind") == "roblox_place_published" and event.get("request_id") == request_id
            for event in state["events"]
        )
        if duplicate:
            return
        self._record(
            state,
            "roblox_place_published",
            request_id=request_id,
            approval_id=approval_id,
            artifact_sha256=artifact_sha256,
            universe_id=universe_id,
            place_id=place_id,
            version_number=version_number,
            remote_host=remote_host,
        )
        self._commit(credential, state)

    def record_roblox_map_validation(
        self,
        credential: str,
        *,
        request_id: str,
        place_version: str,
        task_id: str,
        recipe_name: str,
        object_count: int,
        path_feature_count: int,
        navigation_waypoint_count: int,
        navigation_connected: bool,
        validation_status: str,
        remote_host: str,
        navigation_failed_leg: dict[str, object] | None = None,
    ) -> None:
        """Record bounded evidence from the fixed-harness remote Roblox runner."""
        try:
            request_id = str(uuid.UUID(request_id))
            task_id = str(uuid.UUID(task_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("Roblox validation task IDs are invalid") from exc
        if (
            not place_version.isascii()
            or not place_version.isdecimal()
            or not 1 <= len(place_version) <= 20
            or not recipe_name
            or len(recipe_name) > 64
            or type(object_count) is not int
            or not 0 <= object_count <= 512
            or type(path_feature_count) is not int
            or not 0 <= path_feature_count <= object_count
            or type(navigation_waypoint_count) is not int
            or not 0 <= navigation_waypoint_count <= 512
            or type(navigation_connected) is not bool
            or validation_status not in {"structure_only", "navigation_pass", "navigation_failed"}
            or (
                validation_status == "structure_only"
                and (
                    path_feature_count >= 2
                    or navigation_waypoint_count != 0
                    or navigation_connected
                )
            )
            or (
                validation_status == "navigation_pass"
                and (
                    path_feature_count < 2
                    or not navigation_connected
                    or navigation_waypoint_count < min(path_feature_count - 1, 512)
                )
            )
            or (
                validation_status == "navigation_failed"
                and (path_feature_count < 2 or navigation_connected)
            )
            or (validation_status == "navigation_failed") != (navigation_failed_leg is not None)
            or (
                navigation_failed_leg is not None
                and (
                    not isinstance(navigation_failed_leg, dict)
                    or set(navigation_failed_leg) != {"leg_index", "from", "to"}
                    or type(navigation_failed_leg["leg_index"]) is not int
                    or not 0 <= navigation_failed_leg["leg_index"] < path_feature_count - 1
                    or navigation_waypoint_count < navigation_failed_leg["leg_index"]
                    or (navigation_failed_leg["leg_index"] == 0 and navigation_waypoint_count != 0)
                    or (navigation_failed_leg["leg_index"] > 0 and navigation_waypoint_count == 0)
                    or not isinstance(navigation_failed_leg["from"], str)
                    or not isinstance(navigation_failed_leg["to"], str)
                    or len(navigation_failed_leg["from"]) > 64
                    or len(navigation_failed_leg["to"]) > 64
                )
            )
            or not remote_host
            or len(remote_host) > 253
        ):
            raise ValueError("Roblox validation audit details are invalid")
        state = self._load(credential)
        self._record(
            state,
            "roblox_map_validation_completed",
            request_id=request_id,
            place_version=place_version,
            task_id=task_id,
            recipe_name=recipe_name,
            object_count=object_count,
            path_feature_count=path_feature_count,
            navigation_waypoint_count=navigation_waypoint_count,
            navigation_connected=navigation_connected,
            validation_status=validation_status,
            navigation_failed_leg=navigation_failed_leg,
            remote_host=remote_host,
        )
        self._commit(credential, state)

    def record_generation_attempt(
        self,
        credential: str,
        *,
        run_id: str,
        operation: str,
        succeeded: bool,
        duration_ms: int,
        summary: dict[str, Any] | None = None,
        failure_stage: str = "generation",
    ) -> None:
        """Record a model run without storing its prompt or generated content."""
        kind, details = _generation_event_details(
            run_id=run_id,
            operation=operation,
            succeeded=succeeded,
            duration_ms=duration_ms,
            summary=summary,
            failure_stage=failure_stage,
        )
        state = self._load(credential)
        self._record(state, kind, **details)
        self._commit(credential, state)

    # ------------------------------------------------------------------ the wire

    def handle(self, credential: str, request: Request, body: bytes) -> Outcome:
        """Answer one validated request. `body` is the bytes it arrived as."""
        state = self._load(credential)
        if request.type == "session.hello":
            return self._handle_hello(credential, state, request, body)

        session = state["session"]
        if session is None or session["session_id"] != request.session_id:
            return Outcome(self._error(request, None, "session_expired", "Send session.hello."))
        if self._clock() - session["last_seen"] > self._inactivity_s:
            self._expire(credential, state, "inactivity")
            return Outcome(self._error(request, None, "session_expired", "Send session.hello."))

        cached = self._replay(state, request, body)
        if cached is not None:
            return Outcome(cached)

        session["last_seen"] = self._clock()
        handler = {
            "work.poll": self._handle_poll,
            "project.state": self._handle_snapshot,
            "edit.result": self._handle_result,
            "playtest.report": self._handle_result,
        }[request.type]
        outcome = handler(credential, state, request)
        if not outcome.hold:
            # A poll still waiting has nothing to be idempotent about yet: it has not
            # been answered. Remembering it would make the long poll answer itself.
            self._remember(state, request, body, outcome.response)
        self._commit(credential, state)
        return outcome

    # ------------------------------------------------------------------ handshake

    def _handle_hello(
        self, credential: str, state: dict[str, Any], request: Request, body: bytes
    ) -> Outcome:
        key = request.message_id
        held = state["hello_replay"].get(key)
        if held is not None:
            if held["digest"] == _digest(body):
                return Outcome(held["response"])
            return Outcome(self._error(request, None, "invalid_message", "message_id reused."))

        majors = {entry["major"]: entry["max_minor"] for entry in request.payload["supported"]}
        if 1 not in majors:
            response = error_response(
                "session.hello",
                _new_id("m"),
                request.message_id,
                None,
                "unsupported_version",
                "No common major version.",
                details={"supported": [{"major": 1, "max_minor": 0}]},
            )
            state["hello_replay"][key] = {"digest": _digest(body), "response": response}
            self._commit(credential, state)
            return Outcome(response)

        previous = state["session"]
        if previous is not None:
            self._expire(credential, state, "superseded", commit=False)

        session_id = _new_id("s")
        state["session"] = {
            "session_id": session_id,
            "opened_at": self._clock(),
            "last_seen": self._clock(),
            "minor": min(API_MAX_MINOR, majors[1]),
        }
        state["current_snapshot"] = None
        self._record(state, "session_opened", client=request.payload["client"]["name"])
        response = ok_response(
            "session.hello",
            _new_id("m"),
            request.message_id,
            session_id,
            {
                "negotiated": {"major": 1, "minor": min(API_MAX_MINOR, majors[1])},
                "server": {"version": self._server_version},
            },
        )
        state["hello_replay"][key] = {"digest": _digest(body), "response": response}
        self._commit(credential, state)
        return Outcome(response)

    def _expire(
        self, credential: str, state: dict[str, Any], reason: str, *, commit: bool = True
    ) -> None:
        """End the session. P4: every item it delivered and left unresolved is unknown."""
        session_id = _session_id(state)
        state["session"] = None
        state["current_snapshot"] = None
        self._record(state, "session_ended", reason=reason, session=session_id)
        for work_id, entry in state["work"].items():
            if entry["state"] == "delivered":
                entry["state"] = "closed"
                entry["knowledge"] = "unknown"
                self._record(state, "outcome_inferred_unknown", work_id=work_id)
                self._engage(state, "T1", work_id)
        if commit:
            self._commit(credential, state)

    # ------------------------------------------------------------------ the lock

    def _engage(self, state: dict[str, Any], trigger: str, work_id: str | None) -> None:
        """Engage the per-credential lock. Only an attestation releases it (section 7)."""
        state["lock"]["engaged"] = True
        state["lock"]["triggers"].append(
            {"trigger": trigger, "work_id": work_id, "at": self._clock()}
        )
        self._record(state, "lock_engaged", trigger=trigger, work_id=work_id)
        requeued = []
        for other_id, entry in state["work"].items():
            if entry["state"] == "approved":
                entry["state"] = "queued"
                entry["stale_base"] = True
                requeued.append(other_id)
        if requeued:
            self._record(state, "stale_base_requeued", work_ids=requeued)

    # ------------------------------------------------------------------ delivery

    def _handle_poll(self, credential: str, state: dict[str, Any], request: Request) -> Outcome:
        if state["lock"]["engaged"]:
            # Nothing is delivered while the lock holds, so the poll waits like any other
            # poll with no work: the plugin keeps one long poll open (ADR-0007).
            return Outcome(self._ok(request, state, {}), hold=True)

        session_id = _session_id(state)
        for work_id, entry in state["work"].items():
            if entry["state"] == "delivered" and entry["delivered_in"] == session_id:
                # RD1: a poll with a new message_id proves the plugin never received it.
                entry["deliveries"] += 1
                self._record(state, "delivered", work_id=work_id, delivery=entry["deliveries"])
                self._commit(credential, state)
                return Outcome(self._ok(request, state, {"work": entry["item"]}))

        for work_id, entry in state["work"].items():
            if entry["state"] == "approved":
                try:
                    validate_work_item(entry["item"])
                except ActionPolicyError as exc:
                    entry["state"] = "cancelled"
                    self._record(state, "work_blocked_by_policy", work_id=work_id, reason=str(exc))
                    continue
                entry["state"] = "delivered"
                entry["delivered_in"] = session_id
                entry["deliveries"] = 1
                self._record(state, "delivered", work_id=work_id, delivery=1)
                # The write-ahead record of section 3: durable before the response leaves.
                self._commit(credential, state)
                return Outcome(self._ok(request, state, {"work": entry["item"]}))

        return Outcome(self._ok(request, state, {}), hold=True)

    # ------------------------------------------------------------------ snapshots

    def _handle_snapshot(self, credential: str, state: dict[str, Any], request: Request) -> Outcome:
        payload = request.payload
        snapshot_id = payload["snapshot_id"]
        session_id = _session_id(state)
        known = {(s["session_id"], s["snapshot_id"]) for s in state["snapshots"]}
        if (session_id, snapshot_id) in known:
            self._record(state, "snapshot_conflict", snapshot_id=snapshot_id)
            return Outcome(self._ok(request, state, {}))
        state["snapshots"].append(
            {
                "snapshot_id": snapshot_id,
                "session_id": session_id,
                "reason": payload["reason"],
                "after_action_id": payload.get("after_action_id"),
                "entries": len(payload["entries"]),
                "truncated": payload["truncated"],
                "at": self._clock(),
            }
        )
        self._record(state, "snapshot", snapshot_id=snapshot_id, reason=payload["reason"])
        if any(e["state"] == "delivered" for e in state["work"].values()):
            # A snapshot taken while an item is out is not a baseline for planning.
            self._record(state, "snapshot_superseded", snapshot_id=snapshot_id)
        else:
            state["current_snapshot"] = snapshot_id
            if not state["lock"]["engaged"] and not state["recovered"]:
                state["recovered"] = True
                self._record(state, "recovery_enabled", snapshot_id=snapshot_id)
        return Outcome(self._ok(request, state, {}))

    # ------------------------------------------------------------------ results

    def _handle_result(self, credential: str, state: dict[str, Any], request: Request) -> Outcome:
        payload = request.payload
        is_action = request.type == "edit.result"
        work_id = payload["action_id" if is_action else "playtest_id"]
        entry = state["work"].get(work_id)
        accepts = {"delivered", "closed"}
        if entry is None or entry["state"] not in accepts:
            self._record(state, "unknown_work", work_id=work_id)
            return Outcome(self._error(request, state, "unknown_work", "No such work item."))
        if (entry["kind"] == "edit.action") != is_action:
            return Outcome(self._error(request, state, "unknown_work", "Wrong kind of result."))

        projection = _projection(payload, is_action=is_action)
        recorded = entry["result"]
        if recorded is None:
            entry["result"] = {"payload": payload, "projection": projection}
            entry["state"] = "closed"
            late = entry["knowledge"] == "unknown"
            entry["knowledge"] = "unknown" if payload.get("outcome") == "indeterminate" else "known"
            self._record(
                state,
                "result_received",
                work_id=work_id,
                outcome=payload.get("outcome"),
                replayed=payload.get("replayed"),
                late=late,
            )
            if payload.get("outcome") == "indeterminate":
                self._engage(state, "T3", work_id)
            return Outcome(self._ok(request, state, {}))

        if recorded["projection"] == projection:
            self._record(state, "duplicate", work_id=work_id, replayed=payload.get("replayed"))
            return Outcome(self._ok(request, state, {}))

        self._record(state, "conflict", work_id=work_id)
        self._engage(state, "T4", work_id)
        return Outcome(
            self._error(
                request, state, "result_conflict", "A different result is already recorded."
            )
        )

    # ------------------------------------------------------------------ idempotency

    def _replay(
        self, state: dict[str, Any], request: Request, body: bytes
    ) -> dict[str, Any] | None:
        """P3: a held key answers with the stored response; a changed body is refused."""
        held = state["replay"].get(_replay_key(request))
        if held is None:
            return None
        if held["digest"] == _digest(body):
            return held["response"]
        self._record(state, "message_id_reuse", message_id=request.message_id)
        return self._error(request, state, "invalid_message", "message_id reused.")

    def _remember(
        self, state: dict[str, Any], request: Request, body: bytes, response: dict[str, Any]
    ) -> None:
        state["replay"][_replay_key(request)] = {"digest": _digest(body), "response": response}

    # ------------------------------------------------------------------ envelopes

    def _ok(
        self, request: Request, state: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        return ok_response(
            request.type,
            _new_id("m"),
            request.message_id,
            _session_id(state) or "",
            payload,
            minor=request.minor,
        )

    def _error(
        self, request: Request, state: dict[str, Any] | None, code: str, text: str
    ) -> dict[str, Any]:
        return error_response(
            request.type,
            _new_id("m"),
            request.message_id,
            _session_id(state) if state else None,
            code,
            text,
            retryable=code == "internal",
            minor=request.minor,
        )


def _session_id(state: dict[str, Any] | None) -> str | None:
    if state is None:
        return None
    session = state.get("session")
    return None if session is None else str(session["session_id"])


def _replay_key(request: Request) -> str:
    return f"{request.session_id}|{request.message_id}"


def _digest(body: bytes) -> str:
    """Decided in ADR-0011 (section 6): the digest is over the bytes of the body.

    A canonical form of the parsed value would need the strict JSON profile to fix a
    canonical form for a number, which it does not. Over the bytes, a retry must be
    byte-identical.
    """
    return hashlib.sha256(body).hexdigest()


def _projection(payload: dict[str, Any], *, is_action: bool) -> list[Any]:
    """Decided in ADR-0011 (section 5): what makes two results the same.

    Operations are paired by position, so a permutation is a different result.
    `replayed`, the envelope and the text of an error are not compared.
    """
    if not is_action:
        return [
            payload["outcome"],
            payload["duration_ms"],
            payload.get("output_truncated"),
            [[line["t_ms"], line["level"], line["text"]] for line in payload.get("output", [])],
        ]
    return [
        payload["outcome"],
        [
            [
                operation["op_id"],
                operation["status"],
                operation.get("path"),
                (operation.get("error") or {}).get("code"),
            ]
            for operation in payload["operations"]
        ],
    ]


def handle_message(service: Service, credential: str, body: bytes) -> tuple[dict[str, Any], bool]:
    """Parse, validate and answer. Returns the envelope and whether to hold the poll."""
    try:
        message = parse_strict(body)
    except ProfileError as exc:
        failure = error_response(
            None, _new_id("m"), None, None, "invalid_message", f"Parse: {exc.reason}"
        )
        return failure, False
    try:
        request = validate_request(message)
    except MessageError as exc:
        sent_id = message.get("message_id")
        correlation = sent_id if isinstance(sent_id, str) else None
        message_type = message.get("type")
        return (
            error_response(
                message_type if message_type in ("session.hello", *_TYPES) else None,
                _new_id("m"),
                correlation,
                None,
                exc.code,
                exc.detail or exc.code,
                retryable=exc.retryable,
            ),
            False,
        )
    outcome = service.handle(credential, request, body)
    return outcome.response, outcome.hold


_TYPES = ("work.poll", "project.state", "edit.result", "playtest.report")
