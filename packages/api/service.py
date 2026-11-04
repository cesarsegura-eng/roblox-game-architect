"""The lifecycle of a unit of work: sessions, delivery, results and the lock.

This implements ADR-0011, which is **Proposed**. Three decisions that record leaves open
had to be made one way for a service to run at all. Each is marked `PROVISIONAL` at the
point where it is made, and making it here does not close it:

1. how two results are compared, to tell a duplicate from a conflict (section 5);
2. what the digest of a retried request is computed over (section 6);
3. what the API answers when a `message_id` is repeated with different content — the
   record leaves `message_id_reuse` unadded, so `invalid_message` is used.

The governing rule is kept whatever those become: **a unit of work whose outcome is
uncertain is never run again automatically.**
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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
# PROVISIONAL: ADR-0011 leaves session inactivity limits [Pending].
DEFAULT_INACTIVITY_S = 900.0

WORK_KINDS = ("edit.action", "playtest.request")

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
            {"at": self._clock(), "kind": kind, "session": _session_id(state), **detail}
        )

    # ------------------------------------------------------------------ operator surface

    def queue(self, credential: str, item: dict[str, Any]) -> str:
        """Add a work item as `queued`. It is delivered only after an approval."""
        kind = item.get("type")
        if kind not in WORK_KINDS:
            raise ValueError(f"a work item is one of {WORK_KINDS}, not {kind!r}")
        work_id = item.get("action_id" if kind == "edit.action" else "playtest_id")
        if not isinstance(work_id, str) or not work_id:
            raise ValueError("a work item carries its own id")
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
        self._record(state, "queued", work_id=work_id)
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
    """PROVISIONAL (ADR-0011 section 6): the digest is over the bytes of the body.

    The record leaves open whether it is these bytes or a canonical form of the parsed
    value, and the second cannot be written before the strict JSON profile fixes a
    canonical form for a number. Over the bytes, a retry must be byte-identical.
    """
    return hashlib.sha256(body).hexdigest()


def _projection(payload: dict[str, Any], *, is_action: bool) -> list[Any]:
    """PROVISIONAL (ADR-0011 section 5): what makes two results the same.

    This is the comparison the record *proposes*, not an adopted rule. Operations are
    paired by position, `replayed` and the text of an error are not compared, and whether
    a permutation is a different result is one of the open questions.
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
