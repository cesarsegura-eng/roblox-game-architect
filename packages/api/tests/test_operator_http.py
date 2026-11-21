"""The local operator panel is same-origin and uses its own credential."""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import struct
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from api.http import ApiServer
from api.roblox_mcp import RobloxAssetUploadReceipt, RobloxPublishReceipt
from api.service import Service
from api.store import MemoryStore

PLUGIN_TOKEN = "p" * 40
OPERATOR_TOKEN = "o" * 40


@contextmanager
def _server(
    operator_token: str | None = OPERATOR_TOKEN,
    world_generator: Callable[[str], str] | None = None,
    world_quoter: Callable[[str], dict[str, str]] | None = None,
    game_plan_generator: Callable[[str], object] | None = None,
    game_plan_quoter: Callable[[str], dict[str, str]] | None = None,
    studio_action_generator: Callable[[str], dict[str, object]] | None = None,
    studio_action_quoter: Callable[[str], dict[str, str]] | None = None,
    code_preview_generator: Callable[[str, tuple[str, ...]], object] | None = None,
    code_preview_quoter: Callable[[str, tuple[str, ...]], dict[str, str]] | None = None,
    spend_status_provider: Callable[[], dict[str, str]] | None = None,
    blender_mcp: object | None = None,
    roblox_mcp: object | None = None,
    roblox_asset_approval_secret: str = "",
    roblox_publish_approval_secret: str = "",
    roblox_publish_universe_id: str = "",
    roblox_publish_place_id: str = "",
) -> Iterator[tuple[ApiServer, Service]]:
    service = Service(MemoryStore())
    server = ApiServer(
        service,
        port=0,
        plugin_token=PLUGIN_TOKEN,
        operator_token=operator_token,
        world_generator=world_generator,
        world_quoter=world_quoter,
        game_plan_generator=game_plan_generator,
        game_plan_quoter=game_plan_quoter,
        studio_action_generator=studio_action_generator,
        studio_action_quoter=studio_action_quoter,
        code_preview_generator=code_preview_generator,
        code_preview_quoter=code_preview_quoter,
        spend_status_provider=spend_status_provider,
        blender_mcp=blender_mcp,
        roblox_mcp=roblox_mcp,
        roblox_asset_approval_secret=roblox_asset_approval_secret,
        roblox_publish_approval_secret=roblox_publish_approval_secret,
        roblox_publish_universe_id=roblox_publish_universe_id,
        roblox_publish_place_id=roblox_publish_place_id,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, service
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _action() -> dict[str, object]:
    return {
        "type": "edit.action",
        "action_id": "action-web-1",
        "declared_scope": [{"path": ["Workspace"], "extent": "subtree"}],
        "operations": [
            {
                "op": "create_instance",
                "op_id": "create-1",
                "parent": {"path": ["Workspace"], "expect_class": "Workspace"},
                "name": "WebPanelPlatform",
                "class_name": "Part",
            }
        ],
    }


def _request(
    server: ApiServer,
    method: str,
    path: str,
    *,
    token: str | None = OPERATOR_TOKEN,
    payload: dict[str, object] | None = None,
    host: str | None = None,
    origin: str | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    port = server.server_address[1]
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if origin is not None:
        headers["Origin"] = origin
    body = None if payload is None else json.dumps(payload)
    if body is not None:
        headers["Content-Type"] = "application/json"
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    result = (
        response.status,
        response.read(),
        {key.lower(): value for key, value in response.getheaders()},
    )
    connection.close()
    return result


def test_panel_is_served():
    with _server() as (server, _service):
        status, body, headers = _request(server, "GET", "/", token=None)
        assert status == 200
        assert b"Roblox Game Architect" in body
        assert b'id="quote-button"' in body
        assert b'id="game-plan-generate-button"' in body
        script_status, script_body, _ = _request(server, "GET", "/app.js", token=None)
        assert script_status == 200
        assert b"/v1/operator/world-quote" in script_body
        assert b"/v1/operator/game-plan-quote" in script_body
        assert b"/v1/operator/release-readiness" in script_body
        assert b'id="review-release-readiness"' in body
        assert b"/v1/operator/studio-quote" in script_body
        assert b"/v1/operator/code-preview-quote" in script_body
        html_ids = set(re.findall(rb'\bid="([A-Za-z0-9_-]+)"', body))
        script_selectors = set(
            re.findall(rb'document\.querySelector\("#([A-Za-z0-9_-]+)"\)', script_body)
        )
        assert script_selectors <= html_ids
        assert server.operator_token == OPERATOR_TOKEN
        assert "default-src 'self'" in headers["content-security-policy"]
        assert headers["x-content-type-options"] == "nosniff"


def test_operator_routes_require_operator_token_and_canonical_host():
    with _server() as (server, _service):
        status, _, _ = _request(server, "GET", "/v1/operator/status", token=None)
        assert status == 401
        status, _, _ = _request(server, "GET", "/v1/operator/status", host="localhost")
        assert status == 401
        status, _, _ = _request(
            server,
            "GET",
            "/v1/operator/status",
            origin="http://attacker.example",
        )
        assert status == 401


def _minimal_mesh_glb() -> bytes:
    payload = json.dumps(
        {"asset": {"version": "2.0"}, "meshes": [{"primitives": [{"attributes": {}}]}]}
    ).encode()
    payload += b" " * ((-len(payload)) % 4)
    return (
        b"glTF"
        + struct.pack("<II", 2, 20 + len(payload))
        + struct.pack("<I4s", len(payload), b"JSON")
        + payload
    )


def test_operator_approves_remote_blender_glb_upload_with_auditable_receipt():
    glb = _minimal_mesh_glb()
    blender_calls = []
    roblox_calls = []
    request_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    approval_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    artifact_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"

    class Blender:
        audit_host = "blender.example"

        def download_artifact(self, observed_id, *, expected_sha256=None):
            blender_calls.append(observed_id)
            assert expected_sha256 is None
            return glb

    class Roblox:
        audit_host = "roblox.example"

        def upload_reviewed_model(self, artifact, **kwargs):
            roblox_calls.append((artifact, kwargs))
            return RobloxAssetUploadReceipt(
                request_id=kwargs["request_id"],
                approval_id=kwargs["approval_id"],
                artifact_sha256=hashlib.sha256(artifact).hexdigest(),
                asset_id="7654321",
                operation_id="operation-123",
                moderation_state="MODERATION_STATE_REVIEWING",
                status="moderation_pending",
            )

    with _server(
        blender_mcp=Blender(),
        roblox_mcp=Roblox(),
        roblox_asset_approval_secret="s" * 40,
    ) as (server, service):
        status, body, _ = _request(server, "GET", "/v1/operator/status")
        assert status == 200
        assert json.loads(body)["roblox_asset_upload_enabled"] is True
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/roblox-model-upload",
            payload={
                "artifact_id": artifact_id,
                "request_id": request_id,
                "approval_id": approval_id,
                "display_name": "Approved scene",
                "description": "Reviewed model upload",
            },
        )
        assert status == 200
        result = json.loads(body)["asset"]
        assert result["asset_id"] == "7654321"
        assert result["status"] == "moderation_pending"
        assert blender_calls == [artifact_id]
        assert roblox_calls[0][0] == glb
        assert roblox_calls[0][1]["approval_secret"] == "s" * 40
        events, _ = service.operator_events(PLUGIN_TOKEN)
        event = next(item for item in events if item["kind"] == "roblox_model_asset_uploaded")
        assert event["artifact_sha256"] == hashlib.sha256(glb).hexdigest()
        assert event["asset_id"] == "7654321"


def test_operator_checks_model_moderation_without_another_upload():
    request_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    calls = []

    class Roblox:
        def check_model_upload(self, observed):
            calls.append(observed)
            return RobloxAssetUploadReceipt(
                request_id=observed,
                approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                artifact_sha256="a" * 64,
                asset_id="7654321",
                operation_id="operation-123",
                moderation_state="MODERATION_STATE_APPROVED",
                status="approved",
            )

    endpoint = "/v1/operator/roblox-model-status"
    with _server(roblox_mcp=Roblox()) as (server, _):
        status, _, _ = _request(
            server, "POST", endpoint, token=None, payload={"request_id": request_id}
        )
        assert status == 401
        assert calls == []
        for payload in ({"request_id": "invalid"}, {"request_id": request_id, "asset_id": "1"}):
            status, _, _ = _request(server, "POST", endpoint, payload=payload)
            assert status == 400
        assert calls == []
        status, body, _ = _request(server, "POST", endpoint, payload={"request_id": request_id})
        assert status == 200
        assert json.loads(body)["asset"]["status"] == "approved"
        assert calls == [request_id]


def test_operator_model_status_sanitizes_remote_failure():
    class Roblox:
        def check_model_upload(self, request_id):
            raise RuntimeError("private upstream credential")

    with _server(roblox_mcp=Roblox()) as (server, _):
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/roblox-model-status",
            payload={"request_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"},
        )
        assert status == 502
        assert b"private upstream credential" not in body


def test_code_preview_quotes_exact_task_and_returns_only_policy_approved_source():
    from core.llm.types import GenerationResponse, Usage

    task = {"description": "Create a stone marker", "scope": ["Workspace/Town/**"]}
    calls = []

    def quote(description, scope):
        calls.append((description, scope))
        return {
            "provider": "test",
            "model": "fixture",
            "first_call_max_usd": "0.01",
            "session_limit_usd": "1.00",
            "session_remaining_usd": "1.00",
        }

    def generate(description, scope):
        calls.append((description, scope))
        return SimpleNamespace(
            succeeded=True,
            source="local marker",
            validation=SimpleNamespace(passed=True),
            iterations=1,
            usage=(
                GenerationResponse(
                    text="private generated source",
                    provider="test-provider",
                    model="test-model",
                    usage=Usage(12, 8, Decimal("0.005")),
                ),
            ),
        )

    with _server(code_preview_generator=generate, code_preview_quoter=quote) as (server, service):
        status, body, _ = _request(server, "GET", "/v1/operator/status")
        assert status == 200
        assert json.loads(body)["code_preview_enabled"] is True
        assert json.loads(body)["code_preview_quote_enabled"] is True

        status, body, _ = _request(server, "POST", "/v1/operator/code-preview-quote", payload=task)
        assert status == 200
        quote = json.loads(body)
        assert quote["first_call_max_usd"] == "0.01"
        assert isinstance(quote["quote_id"], str)

        status, body, _ = _request(server, "POST", "/v1/operator/code-preview", payload=task)
        assert status == 409
        preview_payload = {**task, "quote_id": quote["quote_id"]}
        status, body, _ = _request(
            server, "POST", "/v1/operator/code-preview", payload=preview_payload
        )
        assert status == 200
        result = json.loads(body)
        assert result["source"] == "local marker"
        assert result["validation"] == "passed"
        assert result["execution_enabled"] is False
        assert result["studio_delivery_enabled"] is False
        assert calls == [(task["description"], tuple(task["scope"]))] * 2
        events, _ = service.operator_events(PLUGIN_TOKEN)
        preview = events[-1]
        assert preview["operation"] == "luau_source_preview"
        assert preview["source_bytes"] == len("local marker")
        assert preview["model_trace"]["attempts"][0]["input_tokens"] == 12
        assert "source" not in preview
        assert "private generated source" not in json.dumps(preview)
        status, body, _ = _request(
            server, "POST", "/v1/operator/code-preview", payload=preview_payload
        )
        assert status == 409
        assert json.loads(body)["error"]["code"] == "quote_required"
        assert len(calls) == 2


def test_code_preview_never_returns_source_when_static_policy_rejects():
    def generate(_description, _scope):
        return SimpleNamespace(
            succeeded=False,
            source=None,
            validation=SimpleNamespace(passed=False, feedback=("unsafe",)),
            iterations=1,
        )

    def quote(_description, _scope):
        return {
            "provider": "test",
            "model": "fixture",
            "first_call_max_usd": "0.01",
            "session_limit_usd": "1.00",
            "session_remaining_usd": "1.00",
        }

    with _server(code_preview_generator=generate, code_preview_quoter=quote) as (server, service):
        task = {"description": "Create a marker", "scope": ["Workspace/Town/**"]}
        status, quote_body, _ = _request(
            server, "POST", "/v1/operator/code-preview-quote", payload=task
        )
        assert status == 200
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/code-preview",
            payload={**task, "quote_id": json.loads(quote_body)["quote_id"]},
        )
        assert status == 422
        assert "source" not in json.loads(body)
        events, _ = service.operator_events(PLUGIN_TOKEN)
        assert events[-1]["operation"] == "luau_source_preview"
        assert events[-1]["kind"] == "model_generation_failed"
        assert events[-1]["failure_stage"] == "validation"


def test_operator_can_review_queue_and_separately_approve():
    with _server() as (server, service):
        status, body, _headers = _request(
            server,
            "POST",
            "/v1/operator/work",
            payload={"item": _action()},
            origin=f"http://127.0.0.1:{server.server_address[1]}",
        )
        assert status == 200
        work_id = json.loads(body)["work_id"]
        assert work_id == "action-web-1"

        status, body, _ = _request(server, "GET", "/v1/operator/work")
        assert status == 200
        queued = json.loads(body)["items"][0]
        assert queued["state"] == "queued"
        assert queued["item"] == _action()

        status, body, _ = _request(server, "GET", "/v1/operator/events")
        assert status == 200
        events = json.loads(body)
        assert events["total"] == 1
        assert events["events"][0]["kind"] == "queued"
        assert events["events"][0]["at"] > 1_000_000_000

        status, _, _ = _request(
            server,
            "POST",
            "/v1/operator/approve",
            payload={"work_id": work_id},
        )
        assert status == 200
        assert service.status(PLUGIN_TOKEN)["work"][work_id]["state"] == "approved"


def test_operator_queue_still_rejects_non_declarative_actions():
    invalid = _action()
    invalid["operations"] = [{"op": "create_script", "op_id": "script-1"}]
    with _server() as (server, service):
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/work",
            payload={"item": invalid},
        )
        assert status == 400
        assert b"script" in body.lower()
        assert service.status(PLUGIN_TOKEN)["work"] == {}


def test_operator_can_run_and_audit_fixed_harness_validation():
    recipe = {
        "schema_version": 2,
        "name": "Test Meadow",
        "units": "blender_units",
        "up_axis": "Z",
        "objects": [
            {
                "name": "Trail floor",
                "role": "path",
                "primitive": "cube",
                "location": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [12, 2, 0.2],
            },
            {
                "name": "Trail floor two",
                "role": "path",
                "primitive": "cube",
                "location": [12, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [12, 2, 0.2],
            },
        ],
    }
    request_id = "00000000-0000-4000-8000-000000000001"

    class _RobloxMCP:
        audit_host = "roblox-validation.example"

        def validate_recipe(self, received: dict[str, object], received_id: str) -> SimpleNamespace:
            assert received == recipe
            assert received_id == request_id
            return SimpleNamespace(
                request_id=request_id,
                place_version="7",
                task_id="00000000-0000-4000-8000-000000000002",
                validation_status="navigation_pass",
                object_count=2,
                path_feature_count=2,
                navigation_waypoint_count=3,
                navigation_connected=True,
                navigation_failed_leg=None,
            )

    with _server(roblox_mcp=_RobloxMCP()) as (server, service):
        status, body, _ = _request(server, "GET", "/v1/operator/status")
        assert status == 200
        assert json.loads(body)["roblox_mcp_enabled"] is True
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/roblox-validate",
            payload={"recipe": recipe, "request_id": request_id},
        )
        assert status == 200
        result = json.loads(body)["validation"]
        assert result["validation_status"] == "navigation_pass"
        assert result["task_id"].endswith("000000000002")
        events, total = service.operator_events(PLUGIN_TOKEN)
        assert total == 1
        assert events[0]["kind"] == "roblox_map_validation_completed"
        assert events[0]["remote_host"] == "roblox-validation.example"


def test_operator_classifies_contradictory_remote_navigation_as_invalid_receipt():
    recipe = {
        "schema_version": 2,
        "name": "Test Route",
        "units": "blender_units",
        "up_axis": "Z",
        "objects": [
            {
                "name": f"Path {index}",
                "role": "path",
                "primitive": "cube",
                "location": [index * 4, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [4, 1, 2],
            }
            for index in range(3)
        ],
    }
    request_id = "00000000-0000-4000-8000-000000000021"

    class _RobloxMCP:
        audit_host = "roblox-validation.example"

        def validate_recipe(self, received: dict[str, object], received_id: str) -> SimpleNamespace:
            return SimpleNamespace(
                request_id=received_id,
                place_version="7",
                task_id="00000000-0000-4000-8000-000000000022",
                validation_status="navigation_failed",
                object_count=len(received["objects"]),
                path_feature_count=3,
                navigation_waypoint_count=2,
                navigation_connected=False,
                navigation_failed_leg={"leg_index": 0, "from": "Path 0", "to": "Path 1"},
            )

    with _server(roblox_mcp=_RobloxMCP()) as (server, _service):
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/roblox-validate",
            payload={"recipe": recipe, "request_id": request_id},
        )

    assert status == 502
    assert json.loads(body)["error"]["code"] == "remote_receipt_invalid"


def test_operator_can_review_and_download_remote_script_free_place_artifact():
    import base64
    import hashlib

    recipe = {
        "schema_version": 2,
        "name": "Test Place",
        "units": "blender_units",
        "up_axis": "Z",
        "objects": [
            {
                "name": "Ground",
                "role": "terrain",
                "primitive": "cube",
                "location": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [4, 4, 0.25],
            }
        ],
    }
    request_id = "00000000-0000-4000-8000-000000000010"
    place_file = b'<roblox version="4"><Item class="DataModel"/></roblox>'

    class _RobloxMCP:
        audit_host = "roblox-build.example"

        def build_place(
            self,
            received: dict[str, object],
            received_id: str,
            *,
            gameplay_mode: str = "blockout",
        ) -> SimpleNamespace:
            assert received == recipe
            assert received_id == request_id
            assert gameplay_mode == "blockout"
            return SimpleNamespace(
                request_id=request_id,
                place_file=place_file,
                sha256=hashlib.sha256(place_file).hexdigest(),
                object_count=len(received["objects"]),
                part_count=len(received["objects"]),
                light_count=0,
                approximated_object_count=0,
                omitted_character_count=0,
                omitted_sun_light_count=0,
                gameplay_mode=gameplay_mode,
            )

    with _server(roblox_mcp=_RobloxMCP()) as (server, _service):
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/roblox-build",
            payload={"recipe": recipe, "request_id": request_id},
        )
        assert status == 200
        result = json.loads(body)
        assert result["sha256"] == hashlib.sha256(place_file).hexdigest()
        assert base64.b64decode(result["place_file_base64"]) == place_file
        assert result["filename"] == "Test Place-blockout.rbxlx"
        assert result["gameplay_mode"] == "blockout"


def test_place_publish_requires_cached_studio_reviewed_digest_and_audits_receipt():
    request_id = "00000000-0000-4000-8000-000000000020"
    approval_id = "00000000-0000-4000-8000-000000000021"
    place_file = b'<roblox version="4"><Item class="DataModel"/></roblox>'
    digest = hashlib.sha256(place_file).hexdigest()
    recipe = {
        "schema_version": 2,
        "name": "Test Place",
        "units": "blender_units",
        "up_axis": "Z",
        "objects": [
            {
                "name": "Ground",
                "role": "terrain",
                "primitive": "cube",
                "location": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [4, 4, 0.25],
            }
        ],
    }

    class _RobloxMCP:
        audit_host = "roblox-publish.example"

        def build_place(self, received, received_id, *, gameplay_mode="blockout"):
            assert received_id == request_id
            return SimpleNamespace(
                request_id=request_id,
                place_file=place_file,
                sha256=digest,
                object_count=len(received["objects"]),
                part_count=len(received["objects"]),
                light_count=0,
                approximated_object_count=0,
                omitted_character_count=0,
                omitted_sun_light_count=0,
                gameplay_mode=gameplay_mode,
            )

        def publish_reviewed_place(
            self,
            artifact,
            *,
            request_id,
            approval_id,
            approval_secret,
            universe_id,
            place_id,
        ):
            assert artifact == place_file
            assert request_id == "00000000-0000-4000-8000-000000000020"
            assert approval_id == "00000000-0000-4000-8000-000000000021"
            assert approval_secret == "p" * 40
            assert universe_id == "1234" and place_id == "5678"
            return RobloxPublishReceipt(
                request_id,
                approval_id,
                digest,
                universe_id,
                place_id,
                3,
            )

    with _server(
        roblox_mcp=_RobloxMCP(),
        roblox_publish_approval_secret="p" * 40,
        roblox_publish_universe_id="1234",
        roblox_publish_place_id="5678",
    ) as (server, service):
        missing_status, _, _ = _request(
            server,
            "POST",
            "/v1/operator/roblox-publish",
            payload={
                "request_id": request_id,
                "approval_id": approval_id,
                "sha256": digest,
                "reviewed_in_studio": True,
            },
        )
        assert missing_status == 409

        build_status, _, _ = _request(
            server,
            "POST",
            "/v1/operator/roblox-build",
            payload={"recipe": recipe, "request_id": request_id},
        )
        assert build_status == 200
        mismatch_status, _, _ = _request(
            server,
            "POST",
            "/v1/operator/roblox-publish",
            payload={
                "request_id": request_id,
                "approval_id": approval_id,
                "sha256": "0" * 64,
                "reviewed_in_studio": True,
            },
        )
        assert mismatch_status == 409
        unreviewed_status, _, _ = _request(
            server,
            "POST",
            "/v1/operator/roblox-publish",
            payload={
                "request_id": request_id,
                "approval_id": approval_id,
                "sha256": digest,
                "reviewed_in_studio": False,
            },
        )
        assert unreviewed_status == 400
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/roblox-publish",
            payload={
                "request_id": request_id,
                "approval_id": approval_id,
                "sha256": digest,
                "reviewed_in_studio": True,
            },
        )
        assert status == 200
        result = json.loads(body)["publication"]
        assert result["version_number"] == 3
        assert result["artifact_sha256"] == digest
        events, _ = service.operator_events(PLUGIN_TOKEN)
        audit = next(event for event in events if event["kind"] == "roblox_place_published")
        assert audit["place_id"] == "5678"
        assert audit["request_id"] == request_id


def test_operator_passes_fixed_gameplay_mode_to_remote_roblox_mcp():
    request_id = "00000000-0000-4000-8000-000000000011"
    recipe = {
        "schema_version": 2,
        "name": "Treasure Cove",
        "units": "blender_units",
        "up_axis": "Z",
        "objects": [
            {
                "name": "Coast Trail",
                "role": "path",
                "primitive": "cube",
                "location": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [8, 2, 0.2],
            },
            {
                "name": "Coin",
                "role": "collectible",
                "primitive": "uv_sphere",
                "location": [0, 0, 1],
                "rotation_deg": [0, 0, 0],
                "scale": [0.5, 0.5, 0.5],
            },
        ],
    }
    place_file = b'<roblox version="4"><Item class="DataModel"/></roblox>'

    class _RobloxMCP:
        audit_host = "roblox-build.example"

        def build_place(self, received, received_id, *, gameplay_mode="blockout"):
            assert received == recipe
            assert received_id == request_id
            assert gameplay_mode == "treasure_hunt"
            return SimpleNamespace(
                request_id=request_id,
                place_file=place_file,
                sha256=hashlib.sha256(place_file).hexdigest(),
                object_count=len(received["objects"]),
                part_count=len(received["objects"]),
                light_count=0,
                approximated_object_count=0,
                omitted_character_count=0,
                omitted_sun_light_count=0,
                gameplay_mode=gameplay_mode,
            )

    with _server(roblox_mcp=_RobloxMCP()) as (server, _service):
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/roblox-build",
            payload={
                "recipe": recipe,
                "request_id": request_id,
                "gameplay_mode": "treasure_hunt",
            },
        )
        assert status == 200
        result = json.loads(body)
        assert result["gameplay_mode"] == "treasure_hunt"
        assert result["filename"] == "Treasure Cove-treasure_hunt.rbxlx"


def test_operator_passes_data_only_gameplay_rules_to_remote_roblox_mcp():
    request_id = "00000000-0000-4000-8000-000000000021"
    recipe = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "examples/worlds/rainforest-checkpoint-obby/scene-recipe.json"
        ).read_text(encoding="utf-8")
    )
    rules = [{"trigger_role": "hazard", "action": "eliminate"}]
    place_file = b'<roblox version="4"><Item class="DataModel"/></roblox>'

    class _RobloxMCP:
        audit_host = "roblox-build.example"

        def build_place(
            self, received, received_id, *, gameplay_mode="blockout", gameplay_rules=None
        ):
            assert received == recipe
            assert received_id == request_id
            assert gameplay_mode == "rule_game"
            assert gameplay_rules == rules
            return SimpleNamespace(
                request_id=request_id,
                place_file=place_file,
                sha256=hashlib.sha256(place_file).hexdigest(),
                object_count=len(received["objects"]),
                part_count=len(received["objects"]),
                light_count=0,
                approximated_object_count=0,
                omitted_character_count=0,
                omitted_sun_light_count=0,
                gameplay_mode=gameplay_mode,
            )

    with _server(roblox_mcp=_RobloxMCP()) as (server, _service):
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/roblox-build",
            payload={
                "recipe": recipe,
                "request_id": request_id,
                "gameplay_mode": "rule_game",
                "gameplay_rules": rules,
            },
        )
        assert status == 200
        result = json.loads(body)
        assert result["gameplay_mode"] == "rule_game"
        assert result["filename"] == "Rainforest Canopy Obby-rule_game.rbxlx"


def test_operator_world_generation_uses_operator_auth_without_blender_token():
    from core.llm.types import GenerationResponse, Usage
    from core.worldbuilding import SceneRecipe, WorldBuildResult

    received: list[str] = []
    recipe = json.dumps(
        {
            "schema_version": 2,
            "name": "Test Meadow",
            "units": "blender_units",
            "up_axis": "Z",
            "objects": [
                {
                    "name": "Trail floor",
                    "role": "terrain",
                    "primitive": "cube",
                    "location": [0, 0, 0],
                    "rotation_deg": [0, 0, 0],
                    "scale": [12, 2, 0.2],
                }
            ],
            "lights": [],
        }
    )

    def generate(brief: str) -> WorldBuildResult:
        received.append(brief)
        return WorldBuildResult(
            recipe=SceneRecipe.from_json(recipe),
            iterations=1,
            responses=(
                GenerationResponse(
                    text=recipe,
                    provider="test-provider",
                    model="test-model",
                    usage=Usage(10, 20, Decimal("0.01")),
                ),
            ),
            skill_names=("world-environments", "blender-scene-authoring"),
        )

    with _server(world_generator=generate) as (server, _service):
        status, body, _ = _request(server, "GET", "/v1/operator/status")
        assert status == 200
        assert json.loads(body)["world_generation_enabled"] is True

        status, body, headers = _request(
            server,
            "POST",
            "/v1/operator/world-recipe",
            payload={"brief": "A rain-washed meadow with a stone cottage."},
        )
        assert status == 200
        assert json.loads(body)["name"] == "Test Meadow"
        assert received == ["A rain-washed meadow with a stone cottage."]
        run_id = headers["x-rga-run-id"]
        trace, total = _service.operator_events(PLUGIN_TOKEN)
        assert total == 1
        assert trace[-1]["kind"] == "model_generation_succeeded"
        assert trace[-1]["run_id"] == run_id
        assert trace[-1]["object_count"] == 1
        assert trace[-1]["model_trace"]["attempts"][0] == {
            "attempt": 1,
            "provider": "test-provider",
            "model": "test-model",
            "input_tokens": 10,
            "output_tokens": 20,
            "cost_usd": "0.01",
        }
        assert "recipe" not in trace[-1] and "brief" not in trace[-1]


def test_world_generation_failures_are_audited_without_storing_sensitive_content():
    def generate(_brief: str) -> str:
        raise RuntimeError("provider details must not enter the audit log")

    with _server(world_generator=generate) as (server, service):
        status, body, _headers = _request(
            server,
            "POST",
            "/v1/operator/world-recipe",
            payload={"brief": "A private environment brief"},
        )

    assert status == 502
    assert json.loads(body)["error"]["code"] == "generation_failed"
    events, _total = service.operator_events(PLUGIN_TOKEN)
    assert events[-1]["kind"] == "model_generation_failed"
    assert events[-1]["failure_stage"] == "generation"
    assert "private" not in json.dumps(events[-1])
    assert "provider details" not in json.dumps(events[-1])


def test_game_plan_is_quoted_generated_validated_and_audited():
    from core.game_planning import GamePlan, GamePlanBuildResult
    from core.llm.types import GenerationResponse, Usage

    plan = {
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
                "purpose": "Give expeditions a return objective.",
                "implementation_stage": "later",
            },
            {
                "name": "Harbor upgrades",
                "purpose": "Show long-term progress.",
                "implementation_stage": "later",
            },
        ],
        "playable_slice": {
            "gameplay_mode": "blockout",
            "gameplay_rules": [],
            "included_systems": ["Exploration"],
            "deferred_systems": ["Resources", "Harbor upgrades"],
            "limitations": ["Custom gameplay code and persistent progression are deferred."],
        },
        "world_brief": (
            "Create a readable floating harbor hub with a central spawn and clear routes to "
            "three island landmarks, safe return paths, and a sheltered workshop interior."
        ),
        "milestones": ["Greybox the hub", "Validate routes", "Prototype one expedition"],
        "validation_goals": [
            "Players can find the first island route",
            "Players can return from an expedition",
            "The blockout reads at mobile scale",
        ],
    }
    received: list[str] = []

    def generate(brief: str) -> GamePlanBuildResult:
        received.append(brief)
        response = GenerationResponse(
            text=json.dumps(plan),
            provider="test-provider",
            model="test-model",
            usage=Usage(120, 84, Decimal("0.01")),
        )
        return GamePlanBuildResult(
            GamePlan.from_mapping(plan),
            iterations=1,
            responses=(response,),
            skill_names=("game-design-planning",),
        )

    def quote(brief: str) -> dict[str, str]:
        received.append(f"quote:{brief}")
        return {
            "provider": "test-provider",
            "model": "test-model",
            "first_call_max_usd": "0.012",
            "session_limit_usd": "2.00",
            "session_remaining_usd": "1.50",
        }

    with _server(game_plan_generator=generate, game_plan_quoter=quote) as (server, service):
        status, status_body, _ = _request(server, "GET", "/v1/operator/status")
        assert status == 200
        assert json.loads(status_body)["game_plan_enabled"] is True
        assert json.loads(status_body)["game_plan_quote_enabled"] is True

        denied = _request(
            server,
            "POST",
            "/v1/operator/game-plan-quote",
            token=None,
            payload={"brief": "Plan a cooperative exploration game."},
        )
        assert denied[0] == 401

        quote_status, quote_body, _ = _request(
            server,
            "POST",
            "/v1/operator/game-plan-quote",
            payload={"brief": "  Plan a cooperative exploration game.  "},
        )
        assert quote_status == 200
        assert json.loads(quote_body)["first_call_max_usd"] == "0.012"

        status, body, headers = _request(
            server,
            "POST",
            "/v1/operator/game-plan",
            payload={"brief": "  Plan a cooperative exploration game.  "},
        )
        assert status == 200
        generated_plan = GamePlan.from_json(body.decode())
        assert generated_plan.title == "Sky Harbor"
        assert generated_plan.playable_slice.gameplay_mode == "blockout"
        assert received == [
            "quote:Plan a cooperative exploration game.",
            "Plan a cooperative exploration game.",
        ]
        events, total = service.operator_events(PLUGIN_TOKEN)
        assert total == 1
        assert events[0]["operation"] == "game_plan"
        assert events[0]["run_id"] == headers["x-rga-run-id"]
        assert events[0]["system_count"] == 3
        assert events[0]["milestone_count"] == 3
        assert events[0]["provider"] == "test-provider"
        assert events[0]["model"] == "test-model"
        assert events[0]["iterations"] == 1
        assert events[0]["input_tokens"] == 120
        assert events[0]["output_tokens"] == 84
        assert events[0]["cost_usd"] == "0.01"
        assert events[0]["model_trace"]["attempts"] == [
            {
                "attempt": 1,
                "provider": "test-provider",
                "model": "test-model",
                "input_tokens": 120,
                "output_tokens": 84,
                "cost_usd": "0.01",
            }
        ]
        assert "Sky Harbor" not in json.dumps(events[0])
        assert "Create a readable floating harbor" not in json.dumps(events[0])


def test_release_readiness_endpoint_returns_pending_gates_and_requires_operator_auth():
    plan_path = (
        Path(__file__).resolve().parents[3]
        / "examples"
        / "worlds"
        / "rainforest-checkpoint-obby"
        / "game-plan.json"
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    with _server() as (server, _service):
        denied = _request(
            server,
            "POST",
            "/v1/operator/release-readiness",
            token=None,
            payload={"plan": plan},
        )
        assert denied[0] == 401

        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/release-readiness",
            payload={"plan": plan},
        )
        assert status == 200
        report = json.loads(body)["report"]
        assert report["plan_title"] == plan["title"]
        assert report["readiness"] == "not_ready"
        assert report["verified_gate_count"] == 0
        assert report["pending_gate_count"] == 9

        malformed_status, malformed_body, _ = _request(
            server,
            "POST",
            "/v1/operator/release-readiness",
            payload={"plan": {"schema_version": 2, "title": "unsafe"}},
        )
        assert malformed_status == 400
        assert json.loads(malformed_body)["error"]["code"] == "invalid_request"


def test_world_cost_quote_requires_operator_auth_and_returns_bounded_cost_data():
    calls = []

    def quote(brief: str) -> dict[str, str]:
        calls.append(brief)
        return {
            "provider": "test-provider",
            "model": "test-model",
            "first_call_max_usd": "0.012",
            "session_limit_usd": "2.00",
            "session_remaining_usd": "1.50",
        }

    with _server(world_generator=lambda _brief: "{}", world_quoter=quote) as (server, _service):
        status, status_body, _ = _request(server, "GET", "/v1/operator/status")
        assert status == 200
        assert json.loads(status_body)["world_quote_enabled"] is True
        denied = _request(
            server,
            "POST",
            "/v1/operator/world-quote",
            token=None,
            payload={"brief": "A forest trail"},
        )
        assert denied[0] == 401
        assert calls == []

        status, raw, _ = _request(
            server,
            "POST",
            "/v1/operator/world-quote",
            payload={"brief": "  A forest trail  "},
        )

    assert status == 200
    assert json.loads(raw) == {
        "status": "ok",
        "provider": "test-provider",
        "model": "test-model",
        "first_call_max_usd": "0.012",
        "session_limit_usd": "2.00",
        "session_remaining_usd": "1.50",
    }
    assert calls == ["A forest trail"]


def test_world_cost_quote_fails_closed_when_provider_has_no_quote():
    def unavailable(_brief: str) -> dict[str, str]:
        raise ValueError("no quote")

    with _server(world_generator=lambda _brief: "{}", world_quoter=unavailable) as (
        server,
        _service,
    ):
        status, raw, _ = _request(
            server,
            "POST",
            "/v1/operator/world-quote",
            payload={"brief": "A forest trail"},
        )

    assert status == 503
    assert json.loads(raw)["error"]["code"] == "quote_unavailable"


def test_world_cost_quote_rejects_a_first_call_that_exceeds_remaining_budget():
    quote = {
        "provider": "test-provider",
        "model": "test-model",
        "first_call_max_usd": "0.6",
        "session_limit_usd": "1.00",
        "session_remaining_usd": "0.5",
    }
    with _server(world_generator=lambda _brief: "{}", world_quoter=lambda _brief: quote) as (
        server,
        _service,
    ):
        status, raw, _ = _request(
            server,
            "POST",
            "/v1/operator/world-quote",
            payload={"brief": "A forest trail"},
        )

    assert status == 409
    assert json.loads(raw)["error"]["code"] == "insufficient_budget"


def test_studio_blockout_cost_quote_uses_operator_auth_and_reports_session_budget():
    received = []

    def quote(brief: str) -> dict[str, str]:
        received.append(brief)
        return {
            "provider": "test-provider",
            "model": "test-model",
            "first_call_max_usd": "0.02",
            "session_limit_usd": "2.00",
            "session_remaining_usd": "1.90",
        }

    with _server(studio_action_generator=lambda _brief: _action(), studio_action_quoter=quote) as (
        server,
        _service,
    ):
        status, status_body, _ = _request(server, "GET", "/v1/operator/status")
        assert status == 200
        assert json.loads(status_body)["studio_action_quote_enabled"] is True
        status, raw, _ = _request(
            server,
            "POST",
            "/v1/operator/studio-quote",
            payload={"brief": "A forest trail"},
        )

    assert status == 200
    assert json.loads(raw)["first_call_max_usd"] == "0.02"
    assert received == ["A forest trail"]


def test_operator_status_reports_accumulated_spend_reservations_and_remaining_budget():
    budget = {
        "limit_usd": "2.00",
        "spent_usd": "0.12",
        "reserved_usd": "0.03",
        "remaining_usd": "1.85",
    }
    with _server(spend_status_provider=lambda: budget) as (server, _service):
        status, raw, _ = _request(server, "GET", "/v1/operator/status")

    assert status == 200
    assert json.loads(raw)["spend_budget"] == budget


def test_generated_studio_action_is_validated_and_queued_unapproved():
    from core.llm.types import GenerationResponse, Usage
    from core.studio_building import StudioBlockoutBuildResult

    received: list[str] = []

    def generate(brief: str) -> StudioBlockoutBuildResult:
        received.append(brief)
        return StudioBlockoutBuildResult(
            action=_action(),
            responses=(
                GenerationResponse(
                    text="private generated action",
                    provider="test-provider",
                    model="test-model",
                    usage=Usage(15, 25, Decimal("0.02")),
                ),
            ),
        )

    with _server(studio_action_generator=generate) as (server, service):
        status, body, _ = _request(server, "GET", "/v1/operator/status")
        assert status == 200
        assert json.loads(body)["studio_action_generation_enabled"] is True
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/studio-action",
            payload={"brief": "A small forest lookout with a clear route."},
        )
        assert status == 200, (body, service.operator_events(PLUGIN_TOKEN)[0])
        response = json.loads(body)
        assert response["work_id"] == "action-web-1"
        assert response["run_id"]
        assert response["item"] == _action()
        assert service.status(PLUGIN_TOKEN)["work"]["action-web-1"]["state"] == "queued"
        assert received == ["A small forest lookout with a clear route."]
        events, _total = service.operator_events(PLUGIN_TOKEN)
        assert events[-1]["kind"] == "model_generation_succeeded"
        assert events[-1]["run_id"] == response["run_id"]
        assert events[-1]["operation_count"] == len(_action()["operations"])
        assert events[-1]["model_trace"]["attempts"][0]["cost_usd"] == "0.02"
        assert "private generated action" not in json.dumps(events[-1])
        queued = next(event for event in events if event["kind"] == "queued")
        assert queued["work_id"] == response["work_id"]
        assert queued["workflow_id"] == response["run_id"]


def test_generated_studio_action_rejected_by_queue_policy_is_not_persisted():
    invalid = _action()
    invalid["operations"] = [{"op": "create_script", "op_id": "script-1"}]
    with _server(studio_action_generator=lambda _brief: invalid) as (server, service):
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/studio-action",
            payload={"brief": "A village square."},
        )
        assert status == 502
        assert json.loads(body)["error"]["code"] == "queue_failed"
        assert service.status(PLUGIN_TOKEN)["work"] == {}
        events, _total = service.operator_events(PLUGIN_TOKEN)
        assert events[-1]["kind"] == "model_generation_failed"
        assert events[-1]["failure_stage"] == "queue"


def test_remote_blender_import_requires_review_and_is_audited():
    class RemoteBlender:
        audit_host = "blender.example.test"

        def __init__(self):
            self.calls = []

        def apply_recipe(self, recipe, request_id):
            self.calls.append((recipe, request_id))
            from api.blender_mcp import BlenderMCPReceipt

            return BlenderMCPReceipt(
                request_id=request_id,
                artifact_id="53e2d255-fbf7-5bb2-9c15-0654e5cc9b30",
                recipe_name=recipe["name"],
                object_count=len(recipe["objects"]),
                artifact_sha256=hashlib.sha256(b"test-glb").hexdigest(),
            )

        def download_artifact(self, _artifact_id, *, expected_sha256=None):
            assert expected_sha256 == hashlib.sha256(b"test-glb").hexdigest()
            return b"test-glb"

    remote = RemoteBlender()
    recipe = {
        "schema_version": 2,
        "name": "Test Grove",
        "units": "blender_units",
        "up_axis": "Z",
        "objects": [
            {
                "name": "Ground",
                "primitive": "cube",
                "role": "terrain",
                "location": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [4, 0.2, 4],
            }
        ],
    }
    request_id = "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329"
    with _server(blender_mcp=remote) as (server, service):
        status, body, _ = _request(server, "GET", "/v1/operator/status")
        assert status == 200
        assert json.loads(body)["blender_mcp_enabled"] is True
        status, body, _ = _request(
            server,
            "POST",
            "/v1/operator/blender-apply",
            payload={"recipe": recipe, "request_id": request_id},
        )
        assert status == 200
        assert len(remote.calls) == 1
        assert remote.calls[0][1] == request_id
        events, _total = service.operator_events(PLUGIN_TOKEN)
        result = json.loads(body)
        assert result["artifact_id"] == "53e2d255-fbf7-5bb2-9c15-0654e5cc9b30"
        assert result["object_count"] == 1
        assert result["artifact_sha256"] == hashlib.sha256(b"test-glb").hexdigest()
        assert events[-1]["kind"] == "blender_artifact_built"
        assert events[-1]["recipe_name"] == "Test Grove"
        assert events[-1]["artifact_id"] == result["artifact_id"]
        assert events[-1]["artifact_sha256"] == result["artifact_sha256"]
        assert "recipe" not in events[-1]
        status, artifact, headers = _request(
            server,
            "GET",
            f"/v1/operator/blender-artifact/{result['artifact_id']}",
        )
        assert status == 200
        assert artifact == b"test-glb"
        assert headers["content-type"] == "model/gltf-binary"

        remote.download_artifact = lambda _artifact_id, **_kwargs: b"altered-glb"
        mismatch_status, mismatch_body, _ = _request(
            server,
            "GET",
            f"/v1/operator/blender-artifact/{result['artifact_id']}",
        )
        assert mismatch_status == 502
        assert json.loads(mismatch_body)["error"]["code"] == "artifact_digest_mismatch"


def test_remote_blender_route_rejects_invalid_recipe_without_calling_server():
    class RemoteBlender:
        audit_host = "blender.example.test"

        def apply_recipe(self, _recipe, _request_id):
            raise AssertionError("invalid recipe reached remote MCP")

    with _server(blender_mcp=RemoteBlender()) as (server, _service):
        status, _body, _ = _request(
            server,
            "POST",
            "/v1/operator/blender-apply",
            payload={
                "recipe": {"type": "script", "source": "print('unsafe')"},
                "request_id": "invalid",
            },
        )
        assert status == 400


def test_operator_api_is_disabled_without_its_credential():
    with _server(operator_token=None) as (server, _service):
        status, _, _ = _request(server, "GET", "/v1/operator/status", token=PLUGIN_TOKEN)
        assert status == 401
