from __future__ import annotations

import hashlib
import http.client
import json
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.roblox_mcp import RobloxMCPClient
from apps.roblox_mcp_server.publishing import (
    OpenCloudPlacePublisher,
    PlacePublicationLedger,
    RobloxPlacePublishError,
    RobloxPublishTarget,
    validate_place_file,
)
from apps.roblox_mcp_server.server import RobloxMCPServer, ValidationLedger
from core.gameplay_templates import obby_course_source, rule_game_source, treasure_hunt_source
from core.place_approval import sign_place_publish_approval

TEST_SIGNING_KEY = "rga-place-publish-approval-test-secret-32-chars"


def test_mcp_server_rejects_unapproved_origin_with_forbidden_status(tmp_path):
    token = "rga-origin-test-token-abcdefghijklmnopqrstuvwxyz"  # noqa: S105
    server = RobloxMCPServer(
        "127.0.0.1",
        0,
        None,  # type: ignore[arg-type]
        ValidationLedger(tmp_path / "origin-validation.sqlite3"),
        token,
        allowed_origins=("https://trusted.example",),
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
    try:
        connection.request(
            "POST",
            "/mcp",
            body=b"{}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Origin": "https://attacker.example",
            },
        )
        assert connection.getresponse().status == 403

        connection.request(
            "POST",
            "/mcp",
            body=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                }
            ).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Origin": "https://trusted.example",
            },
        )
        assert connection.getresponse().status == 200
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def _target(**overrides: object) -> RobloxPublishTarget:
    values: dict[str, object] = {
        "universe_id": "1234",
        "place_id": "5678",
        "api_key": "publish-test-api-key",
        "approval_secret": TEST_SIGNING_KEY,
        "production_universes": frozenset({"1111"}),
        "production_places": frozenset({"2222"}),
    }
    values.update(overrides)
    return RobloxPublishTarget(**values)  # type: ignore[arg-type]


def _place(
    *,
    surface_appearance: bool = False,
    script: str | None = None,
    script_name: str = "RGA Treasure Hunt",
    disabled: bool = False,
) -> bytes:
    from xml.etree import ElementTree as ET

    root = ET.Element("roblox", {"version": "4"})
    data_model = ET.SubElement(root, "Item", {"class": "DataModel"})
    workspace = ET.SubElement(data_model, "Item", {"class": "Workspace"})
    if surface_appearance:
        mesh = ET.SubElement(workspace, "Item", {"class": "MeshPart"})
        appearance = ET.SubElement(mesh, "Item", {"class": "SurfaceAppearance"})
        ET.SubElement(appearance, "Properties")
    if script is not None:
        service = ET.SubElement(data_model, "Item", {"class": "ServerScriptService"})
        item = ET.SubElement(service, "Item", {"class": "Script"})
        props = ET.SubElement(item, "Properties")
        ET.SubElement(props, "string", {"name": "Name"}).text = script_name
        ET.SubElement(props, "bool", {"name": "Disabled"}).text = str(disabled).lower()
        ET.SubElement(props, "ProtectedString", {"name": "Source"}).text = script
    return ET.tostring(root, encoding="utf-8")


def _approval(place: bytes, request: str, approval: str) -> dict[str, object]:
    digest = hashlib.sha256(place).hexdigest()
    expiry = int(time.time()) + 300
    signature = sign_place_publish_approval(
        TEST_SIGNING_KEY,
        request_id=request,
        approval_id=approval,
        artifact_sha256=digest,
        universe_id="1234",
        place_id="5678",
        expires_at=expiry,
    )
    return {
        "request_id": request,
        "approval_id": approval,
        "artifact_sha256": digest,
        "signature": signature,
        "expires_at": expiry,
    }


def test_target_requires_separate_publish_confirmation_and_denies_production_ids(monkeypatch):
    monkeypatch.delenv("RGA_ROBLOX_PLACE_PUBLISH_CONFIRMED", raising=False)
    with pytest.raises(ValueError, match="confirmation"):
        RobloxPublishTarget.from_env()
    with pytest.raises(ValueError, match="production"):
        _target(place_id="2222")


def test_place_file_rejects_dtd_surfaceappearance_and_untrusted_scripts():
    with pytest.raises(ValueError, match="safe XML"):
        validate_place_file(b'<!DOCTYPE roblox [<!ENTITY x "y">]><roblox></roblox>')
    with pytest.raises(ValueError, match="unsupported"):
        validate_place_file(_place(surface_appearance=True))
    with pytest.raises(ValueError, match="unapproved executable"):
        validate_place_file(_place(script="print('untrusted')"))
    validate_place_file(_place(script=treasure_hunt_source()))
    validate_place_file(_place(script=obby_course_source(), script_name="RGA Obby Course"))
    validate_place_file(_place(script=rule_game_source(), script_name="RGA Data Rules"))
    with pytest.raises(ValueError, match="unapproved executable"):
        validate_place_file(
            _place(
                script=rule_game_source().replace('action == "award_win"', "true"),
                script_name="RGA Data Rules",
            )
        )
    with pytest.raises(ValueError, match="unapproved executable"):
        validate_place_file(_place(script=treasure_hunt_source(), disabled=True))


def test_publisher_posts_exact_xml_to_fixed_target(monkeypatch):
    captured: dict[str, object] = {}

    class Response:
        status = 200

        @staticmethod
        def read(limit: int) -> bytes:
            assert limit == 64_001
            return b'{"versionNumber":12}'

    class Connection:
        def __init__(self, host: str, *, timeout: int, context: object) -> None:
            captured["host"] = host
            captured["timeout"] = timeout
            captured["context"] = context

        def request(self, method: str, path: str, *, body: bytes, headers: dict[str, str]):
            captured.update(method=method, path=path, body=body, headers=headers)

        @staticmethod
        def getresponse() -> Response:
            return Response()

        @staticmethod
        def close() -> None:
            captured["closed"] = True

    monkeypatch.setattr("apps.roblox_mcp_server.publishing.http.client.HTTPSConnection", Connection)
    place = _place()
    version = OpenCloudPlacePublisher(_target()).publish(place)
    assert version == 12
    assert captured["host"] == "apis.roblox.com"
    assert captured["method"] == "POST"
    assert captured["path"] == ("/universes/v1/1234/places/5678/versions?versionType=Published")
    assert captured["body"] == place
    assert captured["headers"]["Content-Type"] == "application/xml"
    assert captured["headers"]["x-api-key"] == "publish-test-api-key"
    assert captured["closed"] is True


def test_publication_ledger_binds_artifact_and_does_not_retry_uncertain_write(tmp_path: Path):
    place = _place()
    request = str(uuid.uuid4())
    approval = str(uuid.uuid4())
    approval_values = _approval(place, request, approval)
    ledger = PlacePublicationLedger(tmp_path / "publish.sqlite3")

    class Publisher:
        target = _target()
        calls = 0

        def publish(self, bytes_to_publish: bytes) -> int:
            assert bytes_to_publish == place
            self.calls += 1
            return 7

    publisher = Publisher()
    receipt = ledger.run(publisher, place, **approval_values)
    assert receipt.version_number == 7
    replay = ledger.run(
        publisher,
        place,
        **{**approval_values, "signature": "0" * 64, "expires_at": 1},
    )
    assert replay == receipt
    assert publisher.calls == 1

    other_request = str(uuid.uuid4())
    other_approval = str(uuid.uuid4())
    uncertain_values = _approval(place, other_request, other_approval)

    class UncertainPublisher(Publisher):
        def publish(self, bytes_to_publish: bytes) -> int:
            self.calls += 1
            raise RobloxPlacePublishError("network outcome uncertain")

    uncertain = UncertainPublisher()
    with pytest.raises(RobloxPlacePublishError, match="uncertain"):
        ledger.run(uncertain, place, **uncertain_values)
    with pytest.raises(RobloxPlacePublishError, match="will not be resubmitted"):
        ledger.run(uncertain, place, **uncertain_values)
    assert uncertain.calls == 1


def test_approval_rejects_modified_artifact(tmp_path: Path):
    place = _place()
    request = str(uuid.uuid4())
    approval = str(uuid.uuid4())
    values = _approval(place, request, approval)
    ledger = PlacePublicationLedger(tmp_path / "publish.sqlite3")

    class Publisher:
        target = _target()

        @staticmethod
        def publish(bytes_to_publish: bytes) -> int:
            raise AssertionError("invalid digest reached the publish call")

    with pytest.raises(ValueError, match="digest"):
        ledger.run(Publisher(), place + b" ", **values)


def test_direct_publication_uses_server_stored_digest_and_short_lived_confirmation(
    tmp_path: Path,
):
    place = _place()
    request = str(uuid.uuid4())
    ledger = PlacePublicationLedger(tmp_path / "direct-publish.sqlite3")
    summary = {"part_count": 4, "gameplay_mode": "blockout"}
    digest = ledger.store_built_artifact(place, request_id=request, summary=summary)
    calls: list[bytes] = []

    class Publisher:
        target = _target()

        @staticmethod
        def publish(artifact: bytes) -> int:
            calls.append(artifact)
            return 9

    publisher = Publisher()
    review = ledger.prepare_direct_publication(
        publisher, request_id=request, artifact_sha256=digest
    )
    assert review["artifact_sha256"] == digest
    assert review["target_universe_id"] == "1234"
    assert review["target_place_id"] == "5678"
    assert review["build_summary"] == summary
    assert review["confirmation_phrase"] == f"I_APPROVE_ROBLOX_TEST_PLACE_PUBLISH_{digest[:12]}"

    with pytest.raises(ValueError, match="phrase"):
        ledger.publish_prepared_artifact(
            publisher,
            request_id=request,
            approval_id=str(review["approval_id"]),
            artifact_sha256=digest,
            confirmation_phrase="I_APPROVE_ROBLOX_TEST_PLACE_PUBLISH_wrong",
        )
    with pytest.raises(ValueError, match="confirmation phrase is invalid"):
        ledger.publish_prepared_artifact(
            publisher,
            request_id=request,
            approval_id=str(review["approval_id"]),
            artifact_sha256=digest,
            confirmation_phrase="I_APPROVE_ROBLOX_TEST_PLACE_PUBLISH_é",
        )
    assert calls == []

    receipt = ledger.publish_prepared_artifact(
        publisher,
        request_id=request,
        approval_id=str(review["approval_id"]),
        artifact_sha256=digest,
        confirmation_phrase=str(review["confirmation_phrase"]),
    )
    assert receipt.version_number == 9
    assert receipt.artifact_sha256 == digest
    assert calls == [place]


def test_direct_mcp_build_review_and_confirm_publish_flow(tmp_path: Path):
    place = _place()
    published: list[bytes] = []
    target = _target()
    publisher = OpenCloudPlacePublisher(target)
    publisher.publish = lambda artifact: published.append(artifact) or 17  # type: ignore[method-assign]

    class Builder:
        @staticmethod
        def build(recipe: dict[str, object], **kwargs: object) -> SimpleNamespace:
            del recipe
            return SimpleNamespace(
                place_file=place,
                object_count=2,
                part_count=2,
                light_count=1,
                approximated_object_count=0,
                omitted_character_count=0,
                omitted_sun_light_count=0,
                gameplay_mode=kwargs.get("gameplay_mode", "blockout"),
                imported_meshpart_count=0,
            )

    token = "rga-direct-publish-test-token-abcdefghijklmnopqrstuvwxyz"  # noqa: S105
    server = RobloxMCPServer(
        "127.0.0.1",
        0,
        None,  # type: ignore[arg-type]
        ValidationLedger(tmp_path / "direct-validation.sqlite3"),
        token,
        place_builder=Builder(),  # type: ignore[arg-type]
        place_publisher=publisher,
        publication_ledger=PlacePublicationLedger(tmp_path / "direct-publishing.sqlite3"),
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def call(method: str, params: dict[str, object], call_id: int) -> dict[str, object]:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
        try:
            body = json.dumps(
                {"jsonrpc": "2.0", "id": call_id, "method": method, "params": params}
            ).encode()
            connection.request(
                "POST",
                "/mcp",
                body=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "MCP-Protocol-Version": "2025-11-25",
                },
            )
            response = connection.getresponse()
            assert response.status == 200
            return json.loads(response.read())
        finally:
            connection.close()

    request = str(uuid.uuid4())
    recipe = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "examples/worlds/rainforest-treasure-hunt/scene-recipe.json"
        ).read_text(encoding="utf-8")
    )
    try:
        listed = call("tools/list", {}, 1)["result"]["tools"]
        names = {tool["name"] for tool in listed}
        assert "rga_prepare_test_place_publication" in names
        assert "rga_publish_prepared_test_place" in names

        build_response = call(
            "tools/call",
            {
                "name": "rga_build_place",
                "arguments": {
                    "recipe": recipe,
                    "request_id": request,
                    "gameplay_mode": "blockout",
                },
            },
            2,
        )["result"]["structuredContent"]
        digest = hashlib.sha256(place).hexdigest()
        assert build_response["sha256"] == digest

        review_response = call(
            "tools/call",
            {
                "name": "rga_prepare_test_place_publication",
                "arguments": {"request_id": request, "artifact_sha256": digest},
            },
            3,
        )["result"]["structuredContent"]
        assert review_response["build_summary"]["part_count"] == 2

        commit_response = call(
            "tools/call",
            {
                "name": "rga_publish_prepared_test_place",
                "arguments": {
                    "request_id": request,
                    "approval_id": review_response["approval_id"],
                    "artifact_sha256": digest,
                    "confirmation_phrase": review_response["confirmation_phrase"],
                },
            },
            4,
        )["result"]["structuredContent"]
        assert commit_response["version_number"] == 17
        assert published == [place]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_remote_mcp_publish_tool_uses_signed_artifact_with_fake_publisher(tmp_path: Path):
    target = _target()
    publisher = OpenCloudPlacePublisher(target)
    calls: list[bytes] = []

    def fake_publish(place_file: bytes) -> int:
        calls.append(place_file)
        return 21

    publisher.publish = fake_publish  # type: ignore[method-assign]
    token = "mcp-publish-test-token-abcdefghijklmnopqrstuvwxyz"  # noqa: S105 - test credential
    server = RobloxMCPServer(
        "127.0.0.1",
        0,
        None,  # type: ignore[arg-type]
        ValidationLedger(tmp_path / "validation.sqlite3"),
        token,
        place_builder=object(),  # type: ignore[arg-type]
        place_publisher=publisher,
        publication_ledger=PlacePublicationLedger(tmp_path / "publishing.sqlite3"),
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    place = _place()
    request = str(uuid.uuid4())
    approval = str(uuid.uuid4())
    try:
        client = RobloxMCPClient(f"http://127.0.0.1:{server.server_address[1]}/mcp", token)
        receipt = client.publish_reviewed_place(
            place,
            request_id=request,
            approval_id=approval,
            approval_secret=TEST_SIGNING_KEY,
            universe_id="1234",
            place_id="5678",
        )
        assert receipt.version_number == 21
        assert receipt.artifact_sha256 == hashlib.sha256(place).hexdigest()
        assert calls == [place]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
