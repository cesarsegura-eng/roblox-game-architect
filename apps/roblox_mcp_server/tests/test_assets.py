from __future__ import annotations

import base64
import hashlib
import http.client
import json
import threading
import time
import uuid
from typing import Any

import pytest

from api.roblox_mcp import RobloxMCPClient
from apps.roblox_mcp_server.assets import (
    AssetUploadLedger,
    OpenCloudModelAssetUploader,
    RobloxAssetError,
    RobloxAssetTarget,
)
from apps.roblox_mcp_server.server import RobloxMCPServer
from core.asset_approval import sign_asset_approval, verify_asset_approval


def _glb(document: dict[str, Any] | None = None) -> bytes:
    value = document or {
        "asset": {"version": "2.0"},
        "meshes": [{"primitives": [{"attributes": {}}]}],
    }
    chunk = json.dumps(value, separators=(",", ":")).encode("utf-8")
    chunk += b" " * ((-len(chunk)) % 4)
    return (
        b"glTF"
        + (2).to_bytes(4, "little")
        + (20 + len(chunk)).to_bytes(4, "little")
        + len(chunk).to_bytes(4, "little")
        + (0x4E4F534A).to_bytes(4, "little")
        + chunk
    )


def _target() -> RobloxAssetTarget:
    return RobloxAssetTarget("groupId", "123456", "server-secret", poll_timeout_seconds=1)


class _FakeUploader(OpenCloudModelAssetUploader):
    def __init__(self, *, moderation: str = "MODERATION_STATE_APPROVED", fail: bool = False):
        super().__init__(_target(), poll_interval_seconds=0.1)
        self.calls: list[tuple[str, str, bytes | None, str | None]] = []
        self.moderation = moderation
        self.fail = fail

    def _request(
        self, method: str, path: str, body: bytes | None = None, content_type: str | None = None
    ) -> object:
        self.calls.append((method, path, body, content_type))
        if self.fail:
            raise RobloxAssetError("simulated uncertain outcome")
        if method == "POST":
            return {"path": "operations/operation-123"}
        if path == "/assets/v1/assets/987654321":
            return {
                "assetId": "987654321",
                "assetType": "Model",
                "revisionId": "1",
                "creationContext": {"creator": {"groupId": 123456}},
                "moderationResult": {"moderationState": self.moderation},
            }
        return {
            "path": "operations/operation-123",
            "done": True,
            "response": {
                "assetId": "987654321",
                "assetType": "ASSET_TYPE_MODEL",
                "moderationResult": {"moderationState": self.moderation},
            },
        }


def _upload(uploader: OpenCloudModelAssetUploader, request_id: str, data: bytes):
    return uploader.upload_glb(
        data,
        display_name="Reviewed scene",
        description="Generated model",
        request_id=request_id,
        approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        approved_sha256=hashlib.sha256(data).hexdigest(),
    )


def test_target_pins_creator_and_requires_explicit_environment_confirmation(
    monkeypatch: pytest.MonkeyPatch,
):
    values = {
        "RGA_ROBLOX_ASSET_CREATOR_TYPE": "groupId",
        "RGA_ROBLOX_ASSET_CREATOR_ID": "123456",
        "ROBLOX_OPEN_CLOUD_ASSET_API_KEY": "server-key",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("RGA_ROBLOX_ASSET_CREATION_CONFIRMED", raising=False)
    with pytest.raises(ValueError, match="confirmation"):
        RobloxAssetTarget.from_env()
    monkeypatch.setenv("RGA_ROBLOX_ASSET_CREATION_CONFIRMED", "I_ACCEPT_ROBLOX_ASSET_CREATION")
    target = RobloxAssetTarget.from_env()
    assert target.creator_type == "groupId"
    assert target.creator_id == "123456"


def test_model_upload_pins_creator_binds_digest_and_reports_moderation():
    data = _glb()
    uploader = _FakeUploader(moderation="MODERATION_STATE_REVIEWING")
    request_id = str(uuid.uuid4())
    receipt = _upload(uploader, request_id, data)
    assert receipt.asset_id == "987654321"
    assert receipt.status == "moderation_pending"
    assert receipt.request_id == request_id
    post = uploader.calls[0]
    assert post[0:2] == ("POST", "/assets/v1/assets")
    assert post[3].startswith("multipart/form-data; boundary=rga")
    assert post[2] is not None and data in post[2]
    metadata = post[2].split(b"\r\n\r\n", 2)[1].split(b"\r\n--", 1)[0]
    request = json.loads(metadata)
    assert request["assetType"] == "Model"
    assert request["creationContext"]["creator"] == {"groupId": "123456"}


def test_upload_rejects_wrong_digest_invalid_glb_and_external_uri_before_network():
    uploader = _FakeUploader()
    data = _glb()
    with pytest.raises(ValueError, match="digest"):
        uploader.upload_glb(
            data,
            display_name="Scene",
            description="Scene model",
            request_id=str(uuid.uuid4()),
            approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            approved_sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="binary GLB"):
        uploader.upload_glb(
            b"nope"
            + (2).to_bytes(4, "little")
            + (20).to_bytes(4, "little")
            + (0).to_bytes(8, "little"),
            display_name="Scene",
            description="Scene model",
            request_id=str(uuid.uuid4()),
            approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            approved_sha256=hashlib.sha256(
                b"nope"
                + (2).to_bytes(4, "little")
                + (20).to_bytes(4, "little")
                + (0).to_bytes(8, "little")
            ).hexdigest(),
        )
    external = _glb(
        {
            "asset": {"version": "2.0"},
            "meshes": [{"primitives": [{"attributes": {}}]}],
            "buffers": [{"uri": "https://example"}],
        }
    )
    with pytest.raises(ValueError, match="external resource"):
        _upload(uploader, str(uuid.uuid4()), external)
    empty_mesh = _glb({"asset": {"version": "2.0"}, "meshes": []})
    with pytest.raises(ValueError, match="mesh primitives"):
        _upload(uploader, str(uuid.uuid4()), empty_mesh)
    limited = OpenCloudModelAssetUploader(
        RobloxAssetTarget("groupId", "123456", "server-secret", max_glb_bytes=20)
    )
    with pytest.raises(ValueError, match="size limit"):
        _upload(limited, str(uuid.uuid4()), data)
    assert uploader.calls == []


def test_upload_ledger_caches_success_and_rejects_request_reuse(tmp_path):
    ledger = AssetUploadLedger(tmp_path / "assets.sqlite3")
    request_id = str(uuid.uuid4())
    data = _glb()
    first_uploader = _FakeUploader()
    first = ledger.run(
        first_uploader,
        data,
        request_id=request_id,
        approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        approved_sha256=hashlib.sha256(data).hexdigest(),
        display_name="Reviewed scene",
        description="Generated model",
    )
    second_uploader = _FakeUploader()
    second = ledger.run(
        second_uploader,
        data,
        request_id=request_id,
        approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        approved_sha256=hashlib.sha256(data).hexdigest(),
        display_name="Reviewed scene",
        description="Generated model",
    )
    assert second == first
    assert ledger.is_approved_model("987654321")
    assert not ledger.is_approved_model("987654322")
    assert second_uploader.calls == []
    with pytest.raises(ValueError, match="different asset content"):
        ledger.run(
            _FakeUploader(),
            data,
            request_id=request_id,
            approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            approved_sha256=hashlib.sha256(data).hexdigest(),
            display_name="Different name",
            description="Generated model",
        )


def test_moderation_pending_model_cannot_be_imported_from_upload_ledger(tmp_path):
    ledger = AssetUploadLedger(tmp_path / "assets.sqlite3")
    data = _glb()
    ledger.run(
        _FakeUploader(moderation="MODERATION_STATE_REVIEWING"),
        data,
        request_id=str(uuid.uuid4()),
        approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        approved_sha256=hashlib.sha256(data).hexdigest(),
        display_name="Reviewed scene",
        description="Generated model",
    )
    assert not ledger.is_approved_model("987654321")


def test_uncertain_upload_is_never_submitted_twice(tmp_path):
    ledger = AssetUploadLedger(tmp_path / "assets.sqlite3")
    request_id = str(uuid.uuid4())
    data = _glb()
    args = {
        "request_id": request_id,
        "approval_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "approved_sha256": hashlib.sha256(data).hexdigest(),
        "display_name": "Reviewed scene",
        "description": "Generated model",
    }
    with pytest.raises(RobloxAssetError, match="uncertain outcome"):
        ledger.run(_FakeUploader(fail=True), data, **args)
    retry = _FakeUploader()
    with pytest.raises(RobloxAssetError, match="will not be resubmitted"):
        ledger.run(retry, data, **args)
    assert retry.calls == []


def test_approval_signature_expires_and_binds_exact_artifact():
    data = _glb()
    digest = hashlib.sha256(data).hexdigest()
    fields = {
        "request_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "approval_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "artifact_sha256": digest,
        "display_name": "Reviewed scene",
        "description": "Generated model",
        "expires_at": 1000,
    }
    signature = sign_asset_approval("a" * 40, **fields)
    assert verify_asset_approval("a" * 40, signature, **fields, now=999)
    assert not verify_asset_approval(
        "a" * 40,
        signature,
        **{**fields, "artifact_sha256": "0" * 64},
        now=999,
    )
    assert not verify_asset_approval("a" * 40, signature, **fields, now=1000)


def test_mcp_asset_upload_requires_signed_approval_and_is_idempotent(tmp_path):
    data = _glb()
    token = "t" * 40
    approval_secret = "s" * 40
    uploader = _FakeUploader(moderation="MODERATION_STATE_REVIEWING")
    server = RobloxMCPServer(
        "127.0.0.1",
        0,
        None,
        None,
        token,
        asset_uploader=uploader,
        asset_ledger=AssetUploadLedger(tmp_path / "assets.sqlite3"),
        asset_approval_secret=approval_secret,
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    request_id = str(uuid.uuid4())
    approval_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    digest = hashlib.sha256(data).hexdigest()
    expires_at = int(time.time()) + 300
    signature = sign_asset_approval(
        approval_secret,
        request_id=request_id,
        approval_id=approval_id,
        artifact_sha256=digest,
        display_name="Reviewed scene",
        description="Generated model",
        expires_at=expires_at,
    )

    def post(request: dict[str, Any]) -> dict[str, Any]:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            connection.request(
                "POST",
                "/mcp",
                body=json.dumps(request).encode(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "MCP-Protocol-Version": "2025-11-25",
                },
            )
            return json.loads(connection.getresponse().read())
        finally:
            connection.close()

    try:
        listing = post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "rga_upload_reviewed_model" in names
        client = RobloxMCPClient(f"http://127.0.0.1:{server.server_address[1]}/mcp", token)
        result = client.upload_reviewed_model(
            data,
            request_id=request_id,
            approval_id=approval_id,
            display_name="Reviewed scene",
            description="Generated model",
            approval_secret=approval_secret,
        )
        assert result.request_id == request_id
        assert result.status == "moderation_pending"
        assert len(uploader.calls) == 2
        replay = client.upload_reviewed_model(
            data,
            request_id=request_id,
            approval_id=approval_id,
            display_name="Reviewed scene",
            description="Generated model",
            approval_secret=approval_secret,
        )
        assert replay == result
        assert len(uploader.calls) == 2
        arguments = {
            "request_id": request_id,
            "approval_id": approval_id,
            "artifact_sha256": "0" * 64,
            "approval_signature": signature,
            "approval_expires_at": expires_at,
            "display_name": "Reviewed scene",
            "description": "Generated model",
            "glb_base64": base64.b64encode(data).decode("ascii"),
        }
        forged = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "rga_upload_reviewed_model", "arguments": arguments},
        }
        rejected = post(forged)["result"]
        assert rejected["isError"] is True
        assert len(uploader.calls) == 2
        uploader.moderation = "Approved"
        status_call = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "rga_check_model_upload", "arguments": {"request_id": request_id}},
        }
        refreshed = post(status_call)["result"]["structuredContent"]
        assert refreshed["status"] == "approved"
        assert refreshed["artifact_sha256"] == digest
        assert refreshed["operation_id"] == result.operation_id
        assert AssetUploadLedger(tmp_path / "assets.sqlite3").is_approved_model(
            refreshed["asset_id"]
        )
        assert post(status_call)["result"]["structuredContent"] == refreshed
        status_call["params"]["arguments"]["request_id"] = str(uuid.uuid4())
        assert post(status_call)["result"]["isError"]
        assert [call[:2] for call in uploader.calls] == [
            ("POST", "/assets/v1/assets"),
            ("GET", "/assets/v1/operations/operation-123"),
            ("GET", "/assets/v1/assets/987654321"),
        ]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
