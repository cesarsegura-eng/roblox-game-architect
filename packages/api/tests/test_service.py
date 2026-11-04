"""The lifecycle of ADR-0011, driven through the same path the transport uses.

Every test goes through `handle_message`, so the parser, the validator and the engine are
all exercised. The record is **Proposed**; these tests pin what this implementation of it
does, which is not the same as the record being approved.
"""

from __future__ import annotations

import json

import pytest

from api.service import Service, handle_message
from api.store import MemoryStore

TOKEN = "test-token"  # noqa: S105 - a local test credential, not a secret


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def service(clock):
    return Service(MemoryStore(), clock=clock)


def send(service, message):
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    response, hold = handle_message(service, TOKEN, body)
    return response, hold


def envelope(message_type, message_id, session_id, payload):
    body = {
        "protocol_version": {"major": 1, "minor": 0},
        "kind": "request",
        "type": message_type,
        "message_id": message_id,
        "payload": payload,
    }
    if session_id is not None:
        body["session_id"] = session_id
    return body


def hello(service, message_id="m-hello"):
    message = envelope(
        "session.hello",
        message_id,
        None,
        {"client": {"name": "test", "version": "1"}, "supported": [{"major": 1, "max_minor": 0}]},
    )
    response, _ = send(service, message)
    return response


def action(work_id="a-1", op_id="o1"):
    return {
        "type": "edit.action",
        "action_id": work_id,
        "declared_scope": [{"path": ["Workspace"], "extent": "subtree"}],
        "operations": [
            {
                "op": "create_instance",
                "op_id": op_id,
                "parent": {"path": ["Workspace"], "expect_class": "Workspace"},
                "name": "Part",
                "class_name": "Part",
            }
        ],
    }


def result(work_id="a-1", outcome="applied", statuses=("applied",), op_ids=("o1",)):
    operations = []
    for op_id, status in zip(op_ids, statuses, strict=True):
        node = {"op_id": op_id, "status": status}
        if status == "failed":
            node["error"] = {"code": "operation_failed", "message": "x"}
        operations.append(node)
    return {"action_id": work_id, "outcome": outcome, "operations": operations}


def snapshot(snapshot_id="snap-1"):
    return {
        "snapshot_id": snapshot_id,
        "reason": "session_start",
        "roots": ["Workspace"],
        "complete_depth": 1,
        "truncated": False,
        "entries": [{"path": ["Workspace"], "class_name": "Workspace"}],
    }


# ------------------------------------------------------------------ handshake


def test_hello_opens_a_session_and_negotiates(service):
    response = hello(service)
    assert response["status"] == "ok"
    assert response["payload"]["negotiated"] == {"major": 1, "minor": 0}
    assert response["session_id"].startswith("s-")
    assert response["correlation_id"] == "m-hello"


def test_hello_without_a_common_major_is_refused(service):
    message = envelope(
        "session.hello",
        "m-h",
        None,
        {"client": {"name": "t", "version": "1"}, "supported": [{"major": 9, "max_minor": 0}]},
    )
    response, _ = send(service, message)
    assert response["payload"]["code"] == "unsupported_version"
    assert "session_id" not in response


def test_a_request_in_an_unknown_session_is_expired(service):
    hello(service)
    response, _ = send(service, envelope("work.poll", "m-1", "s-nonsense", {}))
    assert response["payload"]["code"] == "session_expired"


def test_inactivity_expires_the_session(clock):
    service = Service(MemoryStore(), clock=clock, inactivity_s=10)
    session = hello(service)["session_id"]
    clock.advance(11)
    response, _ = send(service, envelope("work.poll", "m-1", session, {}))
    assert response["payload"]["code"] == "session_expired"


# ------------------------------------------------------------------ delivery


def test_a_poll_with_nothing_approved_is_held(service):
    session = hello(service)["session_id"]
    response, hold = send(service, envelope("work.poll", "m-1", session, {}))
    assert hold is True
    assert response["payload"] == {}


def test_a_queued_item_is_not_delivered_without_an_approval(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    response, hold = send(service, envelope("work.poll", "m-1", session, {}))
    assert hold is True
    assert response["payload"] == {}


def test_an_approved_item_is_delivered_and_recorded_before_the_response(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    response, hold = send(service, envelope("work.poll", "m-1", session, {}))
    assert hold is False
    assert response["payload"]["work"]["action_id"] == "a-1"
    # The write-ahead record of section 3: durable by the time the response exists.
    assert service.status(TOKEN)["work"]["a-1"]["state"] == "delivered"


def test_a_new_poll_redelivers_the_same_item_in_the_same_session(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    response, _ = send(service, envelope("work.poll", "m-2", session, {}))
    assert response["payload"]["work"]["action_id"] == "a-1"
    assert service.status(TOKEN)["work"]["a-1"]["deliveries"] == 2


def test_a_repeated_poll_returns_the_stored_response(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    first, _ = send(service, envelope("work.poll", "m-1", session, {}))
    again, _ = send(service, envelope("work.poll", "m-1", session, {}))
    assert again == first
    assert service.status(TOKEN)["work"]["a-1"]["deliveries"] == 1


def test_a_repeated_message_id_with_different_content_is_refused(service):
    session = hello(service)["session_id"]
    send(service, envelope("project.state", "m-1", session, snapshot("snap-1")))
    response, _ = send(service, envelope("project.state", "m-1", session, snapshot("snap-2")))
    assert response["payload"]["code"] == "invalid_message"


# ------------------------------------------------------------------ results


def test_a_first_result_closes_the_item_and_makes_the_outcome_known(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    response, _ = send(service, envelope("edit.result", "m-2", session, result()))
    assert response["status"] == "ok"
    state = service.status(TOKEN)["work"]["a-1"]
    assert (state["state"], state["knowledge"]) == ("closed", "known")


def test_the_same_result_again_changes_nothing(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    send(service, envelope("edit.result", "m-2", session, result()))
    response, _ = send(service, envelope("edit.result", "m-3", session, result()))
    assert response["status"] == "ok"
    assert service.status(TOKEN)["work"]["a-1"]["knowledge"] == "known"


def test_a_resend_differing_only_in_replayed_is_a_duplicate(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    send(service, envelope("edit.result", "m-2", session, result()))
    response, _ = send(
        service, envelope("edit.result", "m-3", session, {**result(), "replayed": True})
    )
    assert response["status"] == "ok"
    assert service.status(TOKEN)["locked"] is False


def test_a_different_result_conflicts_and_engages_the_lock(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    send(service, envelope("edit.result", "m-2", session, result()))
    response, _ = send(
        service,
        envelope("edit.result", "m-3", session, result(outcome="rejected", statuses=("failed",))),
    )
    assert response["payload"]["code"] == "result_conflict"
    status = service.status(TOKEN)
    assert status["locked"] is True
    assert "T4" in status["triggers"]


def test_an_indeterminate_result_engages_the_lock(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    payload = result(outcome="indeterminate", statuses=("unknown",))
    response, _ = send(service, envelope("edit.result", "m-2", session, payload))
    assert response["status"] == "ok"
    status = service.status(TOKEN)
    assert status["locked"] is True
    assert "T3" in status["triggers"]
    assert status["work"]["a-1"]["knowledge"] == "unknown"


def test_indeterminate_with_partial_knowledge_is_accepted(service):
    """ADR-0011 section 9, form (a): applied, then one unknown, then skipped."""
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    payload = result(
        outcome="indeterminate",
        statuses=("applied", "unknown", "skipped"),
        op_ids=("o1", "o2", "o3"),
    )
    response, _ = send(service, envelope("edit.result", "m-2", session, payload))
    assert response["status"] == "ok"


def test_a_result_for_a_queued_item_is_unknown_work(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    response, _ = send(service, envelope("edit.result", "m-1", session, result()))
    assert response["payload"]["code"] == "unknown_work"


# ------------------------------------------------------------------ session loss


def test_a_session_ending_with_an_item_out_makes_it_unknown_and_locks(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    hello(service, "m-hello-2")
    status = service.status(TOKEN)
    assert status["work"]["a-1"] == {
        "kind": "edit.action",
        "state": "closed",
        "knowledge": "unknown",
        "deliveries": 1,
        "stale_base": False,
    }
    assert status["locked"] is True
    assert "T1" in status["triggers"]


def test_a_late_result_is_accepted_and_nothing_is_run_again(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    new_session = hello(service, "m-hello-2")["session_id"]
    response, _ = send(service, envelope("edit.result", "m-2", new_session, result()))
    assert response["status"] == "ok"
    status = service.status(TOKEN)
    assert status["work"]["a-1"]["knowledge"] == "known"
    assert status["work"]["a-1"]["deliveries"] == 1
    # RD2: the lock holds, so the item is not delivered again by any automatic path.
    assert status["locked"] is True


def test_an_item_of_unknown_outcome_is_never_delivered_again(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    new_session = hello(service, "m-hello-2")["session_id"]
    service.attest(TOKEN, "tester", "warning")
    response, hold = send(service, envelope("work.poll", "m-2", new_session, {}))
    assert hold is True
    assert response["payload"] == {}


def test_the_lock_returns_approved_items_to_queued(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action("a-1"))
    service.queue(TOKEN, action("a-2", "o2"))
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    service.approve(TOKEN, "a-2")
    hello(service, "m-hello-2")
    status = service.status(TOKEN)
    assert status["work"]["a-2"]["state"] == "queued"
    assert status["work"]["a-2"]["stale_base"] is True


def test_nothing_can_be_approved_or_delivered_while_the_lock_is_engaged(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action("a-1"))
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    new_session = hello(service, "m-hello-2")["session_id"]
    service.queue(TOKEN, action("a-2", "o2"))
    with pytest.raises(ValueError, match="not queued"):
        service.approve(TOKEN, "a-1")
    with pytest.raises(ValueError, match="lock is engaged"):
        service.approve(TOKEN, "a-2")
    response, hold = send(service, envelope("work.poll", "m-2", new_session, {}))
    assert hold is True
    assert response["payload"] == {}


def test_planning_cannot_resume_before_a_fresh_snapshot(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action("a-1"))
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    new_session = hello(service, "m-hello-2")["session_id"]
    service.attest(TOKEN, "tester", "warning")
    service.queue(TOKEN, action("a-2", "o2"))
    with pytest.raises(ValueError, match="no fresh snapshot"):
        service.approve(TOKEN, "a-2")
    send(service, envelope("project.state", "m-2", new_session, snapshot("snap-2")))
    service.approve(TOKEN, "a-2")
    assert service.status(TOKEN)["work"]["a-2"]["state"] == "approved"


# ------------------------------------------------------------------ attestation


def test_only_an_attestation_releases_the_lock(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    new_session = hello(service, "m-hello-2")["session_id"]
    send(service, envelope("edit.result", "m-2", new_session, result()))
    assert service.status(TOKEN)["locked"] is True
    service.attest(TOKEN, "tester", "warning")
    assert service.status(TOKEN)["locked"] is False


def test_a_conflict_needs_a_recorded_review(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    send(service, envelope("edit.result", "m-2", session, result()))
    send(
        service,
        envelope("edit.result", "m-3", session, result(outcome="rejected", statuses=("failed",))),
    )
    with pytest.raises(ValueError, match="review"):
        service.attest(TOKEN, "tester", "warning")
    service.attest(TOKEN, "tester", "warning", review="the first result stands")
    assert service.status(TOKEN)["locked"] is False


def test_attesting_without_a_lock_is_refused(service):
    hello(service)
    with pytest.raises(ValueError, match="not engaged"):
        service.attest(TOKEN, "tester", "warning")


# ------------------------------------------------------------------ snapshots


def test_a_snapshot_becomes_the_current_one(service):
    session = hello(service)["session_id"]
    response, _ = send(service, envelope("project.state", "m-1", session, snapshot()))
    assert response["status"] == "ok"
    assert service.status(TOKEN)["current_snapshot"] == "snap-1"


def test_a_snapshot_taken_while_an_item_is_out_is_not_a_baseline(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    send(service, envelope("project.state", "m-2", session, snapshot()))
    assert service.status(TOKEN)["current_snapshot"] is None


def test_recovery_needs_the_lock_released_and_a_fresh_snapshot(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    new_session = hello(service, "m-hello-2")["session_id"]
    service.attest(TOKEN, "tester", "warning")
    assert service.status(TOKEN)["recovered"] is False
    send(service, envelope("project.state", "m-2", new_session, snapshot("snap-2")))
    assert service.status(TOKEN)["recovered"] is True


def test_a_snapshot_never_makes_an_unknown_outcome_known(service):
    session = hello(service)["session_id"]
    service.queue(TOKEN, action())
    service.approve(TOKEN, "a-1")
    send(service, envelope("work.poll", "m-1", session, {}))
    new_session = hello(service, "m-hello-2")["session_id"]
    service.attest(TOKEN, "tester", "warning")
    send(service, envelope("project.state", "m-2", new_session, snapshot("snap-2")))
    assert service.status(TOKEN)["work"]["a-1"]["knowledge"] == "unknown"


# ------------------------------------------------------------------ the operator surface


def test_queueing_the_same_id_twice_is_refused(service):
    service.queue(TOKEN, action())
    with pytest.raises(ValueError, match="already exists"):
        service.queue(TOKEN, action())


def test_a_work_item_must_be_one_of_the_two_kinds(service):
    with pytest.raises(ValueError, match="work item is one of"):
        service.queue(TOKEN, {"type": "edit.result", "action_id": "a-1"})


def test_the_event_history_only_grows(service):
    session = hello(service)["session_id"]
    before = service.status(TOKEN)["events"]
    send(service, envelope("project.state", "m-1", session, snapshot()))
    assert service.status(TOKEN)["events"] > before
