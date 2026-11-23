"""The whole loop over real HTTP: handshake, delivery, result, snapshot.

This crosses the transport, so it is an integration test (ADR-0001 puts those here
rather than beside the package). It drives the service the way the plugin will: every
exchange is started by the client, and the work item arrives inside a poll response
(ADR-0007).
"""

from __future__ import annotations

import http.client
import json
import threading
import urllib.error
import urllib.request

import pytest

from api.http import ApiServer
from api.service import Service
from api.store import FileStore

pytestmark = pytest.mark.integration

TOKEN = "e2e-only-token-with-at-least-32-printable-characters"  # noqa: S105 - local test credential


@pytest.fixture
def server(tmp_path):
    service = Service(FileStore(tmp_path / "api"))
    instance = ApiServer(service, port=0, poll_timeout_s=1.0, plugin_token=TOKEN)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance, service
    instance.shutdown()
    instance.server_close()
    thread.join(timeout=5)


def post(server, message, token=TOKEN):
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(  # noqa: S310 - a loopback URL this test just bound
        server.endpoint, data=body, method="POST"
    )
    request.add_header("Content-Type", "application/json")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def envelope(message_type, message_id, session_id, payload):
    message = {
        "protocol_version": {"major": 1, "minor": 0},
        "kind": "request",
        "type": message_type,
        "message_id": message_id,
        "payload": payload,
    }
    if session_id is not None:
        message["session_id"] = session_id
    return message


ACTION = {
    "type": "edit.action",
    "action_id": "a-e2e",
    "declared_scope": [{"path": ["Workspace"], "extent": "subtree"}],
    "operations": [
        {
            "op": "create_instance",
            "op_id": "o1",
            "parent": {"path": ["Workspace"], "expect_class": "Workspace"},
            "name": "Platform",
            "class_name": "Part",
        }
    ],
}


def test_the_whole_loop(server):
    instance, service = server

    status, hello = post(
        instance,
        envelope(
            "session.hello",
            "m-1",
            None,
            {
                "client": {"name": "e2e", "version": "1"},
                "supported": [{"major": 1, "max_minor": 0}],
            },
        ),
    )
    assert status == 200
    assert hello["payload"]["negotiated"] == {"major": 1, "minor": 0}
    session = hello["session_id"]

    snapshot = {
        "snapshot_id": "snap-1",
        "reason": "session_start",
        "roots": ["Workspace"],
        "complete_depth": 1,
        "truncated": False,
        "entries": [{"path": ["Workspace"], "class_name": "Workspace"}],
    }
    status, acknowledged = post(instance, envelope("project.state", "m-2", session, snapshot))
    assert (status, acknowledged["status"]) == (200, "ok")

    # Nothing is delivered before a human approves it (ADR-0002).
    service.queue(TOKEN, ACTION)
    status, held = post(instance, envelope("work.poll", "m-3", session, {}))
    assert (status, held["payload"]) == (200, {})

    service.approve(TOKEN, "a-e2e")
    status, delivered = post(instance, envelope("work.poll", "m-4", session, {}))
    assert status == 200
    assert delivered["payload"]["work"]["action_id"] == "a-e2e"

    result = {
        "action_id": "a-e2e",
        "outcome": "applied",
        "operations": [{"op_id": "o1", "status": "applied", "path": ["Workspace", "Platform"]}],
    }
    status, acknowledged = post(instance, envelope("edit.result", "m-5", session, result))
    assert (status, acknowledged["status"]) == (200, "ok")

    final = service.status(TOKEN)["work"]["a-e2e"]
    assert (final["state"], final["knowledge"]) == ("closed", "known")
    assert service.status(TOKEN)["locked"] is False


def test_a_request_without_a_token_is_unauthorized(server):
    instance, _ = server
    status, response = post(instance, envelope("work.poll", "m-1", "s-1", {}), token=None)
    assert status == 401
    assert response["payload"]["code"] == "unauthorized"


def test_an_unparseable_body_is_an_invalid_message(server):
    instance, _ = server
    body = b"{'kind': 'request'}"
    request = urllib.request.Request(instance.endpoint, data=body, method="POST")  # noqa: S310
    request.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read())["payload"]
    assert payload["code"] == "invalid_message"


def test_the_endpoint_is_the_only_path(server):
    instance, _ = server
    request = urllib.request.Request(  # noqa: S310
        instance.endpoint.replace("/v1/messages", "/"), data=b"{}", method="POST"
    )
    request.add_header("Authorization", f"Bearer {TOKEN}")
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=30)  # noqa: S310
    assert caught.value.code == 404


def test_state_survives_a_restart_of_the_process(tmp_path):
    """The write-ahead record is durable: a new Service sees what the old one stored."""
    root = tmp_path / "api"
    first = Service(FileStore(root))
    first.queue(TOKEN, ACTION)
    first.approve(TOKEN, "a-e2e")

    second = Service(FileStore(root))
    assert second.status(TOKEN)["work"]["a-e2e"]["state"] == "approved"


def test_a_data_directory_never_holds_the_token(tmp_path):
    root = tmp_path / "api"
    service = Service(FileStore(root))
    service.queue(TOKEN, ACTION)
    written = list(root.glob("*.json"))
    assert written
    for path in written:
        assert TOKEN not in path.name
        assert TOKEN not in path.read_text(encoding="utf-8")


def _raw_post(instance, content_length, body=b""):
    connection = http.client.HTTPConnection("127.0.0.1", instance.server_address[1], timeout=10)
    try:
        connection.putrequest("POST", "/v1/messages")
        connection.putheader("Authorization", f"Bearer {TOKEN}")
        connection.putheader("Content-Length", content_length)
        connection.endheaders(body)
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


@pytest.mark.parametrize("content_length", ["-1", "abc", "1e3", "+5"])
def test_a_malformed_content_length_is_rejected_not_waited_on(server, content_length):
    instance, _ = server
    # `read(-1)` would block until the client hung up; this must answer at once.
    assert _raw_post(instance, content_length, b"{}") == 400


def test_an_oversized_content_length_is_rejected_before_reading(server):
    instance, _ = server
    assert _raw_post(instance, str(1_048_577)) == 413
