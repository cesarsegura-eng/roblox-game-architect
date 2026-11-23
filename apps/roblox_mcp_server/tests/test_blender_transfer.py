from __future__ import annotations

import hashlib
import http.client
import json
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest

from apps.roblox_mcp_server.assets import (
    AssetUploadLedger,
    OpenCloudModelAssetUploader,
    RobloxAssetError,
    RobloxAssetTarget,
)
from apps.roblox_mcp_server.blender_transfer import (
    BlenderArtifactError,
    BlenderArtifactSource,
    PreparedModelUploadLedger,
)
from apps.roblox_mcp_server.server import (
    COMMIT_BLENDER_UPLOAD_TOOL_NAME,
    PREPARE_BLENDER_UPLOAD_TOOL_NAME,
    RobloxMCPServer,
)
from core.roblox_place import RobloxPlaceBuild


def _glb(document: dict[str, Any] | None = None, *, vertex_count: int = 3) -> bytes:
    value = document or {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": vertex_count * 12}],
        "bufferViews": [{"buffer": 0, "byteLength": vertex_count * 12}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": vertex_count, "type": "VEC3"}
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
    }
    chunk = json.dumps(value, separators=(",", ":")).encode("utf-8")
    chunk += b" " * ((-len(chunk)) % 4)
    binary = b"\0" * (vertex_count * 12) if document is None else b""
    chunks = len(chunk).to_bytes(4, "little") + (0x4E4F534A).to_bytes(4, "little") + chunk
    if binary:
        chunks += len(binary).to_bytes(4, "little") + (0x004E4942).to_bytes(4, "little") + binary
    return b"glTF" + (2).to_bytes(4, "little") + (12 + len(chunks)).to_bytes(4, "little") + chunks


class _MemorySource:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.calls: list[tuple[str, int]] = []

    def fetch(self, artifact_id: str, *, max_bytes: int) -> bytes:
        self.calls.append((artifact_id, max_bytes))
        if len(self.data) > max_bytes:
            raise BlenderArtifactError("artifact too large")
        return self.data


class _FakeUploader(OpenCloudModelAssetUploader):
    def __init__(self, *, fail: bool = False) -> None:
        target = RobloxAssetTarget("groupId", "123456", "test-key", poll_timeout_seconds=1)
        super().__init__(target, poll_interval_seconds=0.1)
        self.calls = 0
        self.fail = fail

    def _request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> object:
        del path, body, content_type
        self.calls += 1
        if self.fail:
            raise RobloxAssetError("simulated ambiguous Open Cloud result")
        if method == "POST":
            return {"path": "operations/operation-123"}
        return {
            "path": "operations/operation-123",
            "done": True,
            "response": {
                "assetId": "987654321",
                "assetType": "ASSET_TYPE_MODEL",
                "moderationResult": {"moderationState": "MODERATION_STATE_APPROVED"},
            },
        }


def _uploader() -> _FakeUploader:
    return _FakeUploader()


def test_source_accepts_only_fixed_https_mcp_host_and_valid_credentials() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        BlenderArtifactSource("http://blender.example.com/mcp", "t" * 40)
    with pytest.raises(ValueError, match="HTTPS"):
        BlenderArtifactSource("https://user:pass@blender.example.com/mcp", "t" * 40)
    with pytest.raises(ValueError, match="HTTPS"):
        BlenderArtifactSource("https://blender.example.com/mcp?next=https://evil", "t" * 40)
    with pytest.raises(ValueError, match="BEARER_TOKEN"):
        BlenderArtifactSource("https://blender.example.com/mcp", "short")


def test_source_download_is_uuid_addressed_bounded_and_authenticated(monkeypatch) -> None:
    data = _glb()
    artifact_id = str(uuid.uuid4())

    class Response:
        status = 200

        def getheader(self, name: str, default: str = "") -> str:
            return {"Content-Type": "model/gltf-binary", "Content-Length": str(len(data))}.get(
                name, default
            )

        def read(self, limit: int) -> bytes:
            assert limit == len(data) + 1
            return data

    class Connection:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs
            self.request_args: tuple[object, ...] | None = None
            self.closed = False

        def request(self, *args: object, **kwargs: object) -> None:
            self.request_args = (*args, kwargs)

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            self.closed = True

    connection: Connection | None = None

    def create_connection(*args: object, **kwargs: object) -> Connection:
        nonlocal connection
        connection = Connection(*args, **kwargs)
        return connection

    monkeypatch.setattr(
        "apps.roblox_mcp_server.blender_transfer.http.client.HTTPSConnection",
        create_connection,
    )
    source = BlenderArtifactSource("https://blender.example.com/service/mcp", "t" * 40)
    assert source.fetch(artifact_id, max_bytes=len(data)) == data
    assert connection is not None and connection.closed
    assert connection.args == ("blender.example.com", 443)
    assert connection.request_args is not None
    method, path, kwargs = connection.request_args
    assert method == "GET"
    assert path == f"/service/artifacts/{artifact_id}.glb"
    assert kwargs["headers"]["Authorization"] == f"Bearer {'t' * 40}"
    with pytest.raises(BlenderArtifactError, match="limit"):
        source.fetch(artifact_id, max_bytes=1)
    with pytest.raises(ValueError, match="UUID"):
        source.fetch("../other-host/model.glb")


def test_prepared_transfer_needs_confirmation_and_binds_exact_glb(tmp_path: Path) -> None:
    data = _glb()
    artifact_id = str(uuid.uuid4())
    source = _MemorySource(data)
    uploader = _uploader()
    transfer = PreparedModelUploadLedger(tmp_path / "transfers.sqlite3")
    upload_ledger = AssetUploadLedger(tmp_path / "assets.sqlite3")
    prepared = transfer.prepare(source, artifact_id, now=100)
    assert prepared.artifact_sha256 == hashlib.sha256(data).hexdigest()
    assert prepared.expires_at == 100 + 300
    assert len(source.calls) == 1

    with pytest.raises(ValueError, match="digest"):
        transfer.upload(
            source,
            uploader,
            upload_ledger,
            request_id=prepared.request_id,
            approval_id=prepared.approval_id,
            artifact_sha256="0" * 64,
            confirmation_phrase=prepared.confirmation_phrase,
            now=101,
        )
    assert uploader.calls == 0
    with pytest.raises(ValueError, match="confirmation"):
        transfer.upload(
            source,
            uploader,
            upload_ledger,
            request_id=prepared.request_id,
            approval_id=prepared.approval_id,
            artifact_sha256=prepared.artifact_sha256,
            confirmation_phrase="I_APPROVE_ROBLOX_MODEL_UPLOAD_000000000000",
            now=101,
        )
    assert uploader.calls == 0

    receipt = transfer.upload(
        source,
        uploader,
        upload_ledger,
        request_id=prepared.request_id,
        approval_id=prepared.approval_id,
        artifact_sha256=prepared.artifact_sha256,
        confirmation_phrase=prepared.confirmation_phrase,
        now=101,
    )
    assert receipt.asset_id == "987654321"
    assert receipt.artifact_sha256 == prepared.artifact_sha256
    assert uploader.calls == 2
    replay = transfer.upload(
        source,
        uploader,
        upload_ledger,
        request_id=prepared.request_id,
        approval_id=prepared.approval_id,
        artifact_sha256=prepared.artifact_sha256,
        confirmation_phrase=prepared.confirmation_phrase,
        now=500,
    )
    assert replay == receipt
    assert uploader.calls == 2
    assert len(source.calls) == 2


def test_changed_or_uncertain_blender_artifacts_never_resubmit(tmp_path: Path) -> None:
    artifact_id = str(uuid.uuid4())
    original = _glb()
    source = _MemorySource(original)
    transfer = PreparedModelUploadLedger(tmp_path / "transfers.sqlite3")
    upload_ledger = AssetUploadLedger(tmp_path / "assets.sqlite3")
    uploader = _uploader()
    prepared = transfer.prepare(source, artifact_id, now=100)
    source.data = _glb(vertex_count=6)
    with pytest.raises(ValueError, match="changed after the review"):
        transfer.upload(
            source,
            uploader,
            upload_ledger,
            request_id=prepared.request_id,
            approval_id=prepared.approval_id,
            artifact_sha256=prepared.artifact_sha256,
            confirmation_phrase=prepared.confirmation_phrase,
            now=101,
        )
    assert uploader.calls == 0
    with pytest.raises(RobloxAssetError, match="uncertain"):
        transfer.upload(
            source,
            uploader,
            upload_ledger,
            request_id=prepared.request_id,
            approval_id=prepared.approval_id,
            artifact_sha256=prepared.artifact_sha256,
            confirmation_phrase=prepared.confirmation_phrase,
            now=101,
        )

    failing_source = _MemorySource(original)
    failing_transfer = PreparedModelUploadLedger(tmp_path / "failed-transfers.sqlite3")
    failing_prepared = failing_transfer.prepare(failing_source, artifact_id, now=100)
    failing_uploader = _FakeUploader(fail=True)
    with pytest.raises(RobloxAssetError):
        failing_transfer.upload(
            failing_source,
            failing_uploader,
            AssetUploadLedger(tmp_path / "failed-assets.sqlite3"),
            request_id=failing_prepared.request_id,
            approval_id=failing_prepared.approval_id,
            artifact_sha256=failing_prepared.artifact_sha256,
            confirmation_phrase=failing_prepared.confirmation_phrase,
            now=101,
        )
    assert failing_uploader.calls == 1
    with pytest.raises(RobloxAssetError, match="uncertain"):
        failing_transfer.upload(
            failing_source,
            failing_uploader,
            AssetUploadLedger(tmp_path / "failed-assets.sqlite3"),
            request_id=failing_prepared.request_id,
            approval_id=failing_prepared.approval_id,
            artifact_sha256=failing_prepared.artifact_sha256,
            confirmation_phrase=failing_prepared.confirmation_phrase,
            now=101,
        )
    assert failing_uploader.calls == 1


def test_prepared_model_upload_expires_before_roblox_write(tmp_path: Path) -> None:
    source = _MemorySource(_glb())
    transfer = PreparedModelUploadLedger(tmp_path / "transfers.sqlite3")
    prepared = transfer.prepare(source, str(uuid.uuid4()), now=100)
    uploader = _uploader()
    with pytest.raises(ValueError, match="expired"):
        transfer.upload(
            source,
            uploader,
            AssetUploadLedger(tmp_path / "assets.sqlite3"),
            request_id=prepared.request_id,
            approval_id=prepared.approval_id,
            artifact_sha256=prepared.artifact_sha256,
            confirmation_phrase=prepared.confirmation_phrase,
            now=prepared.expires_at + 1,
        )
    assert uploader.calls == 0


def test_remote_roblox_mcp_exposes_two_step_blender_asset_handoff(tmp_path: Path) -> None:
    source = _MemorySource(_glb())
    uploader = _uploader()
    asset_ledger = AssetUploadLedger(tmp_path / "assets.sqlite3")

    class _FakeImportValidator:
        def serialize_approved_model(self, asset_id: str) -> tuple[bytes, dict[str, int]]:
            assert asset_id == "987654321"
            return b"engine-serialized-model", {"meshpart_count": 1}

    class _FakePlaceBuilder:
        def build(
            self,
            recipe: object,
            *,
            gameplay_mode: str = "blockout",
            imported_model: bytes | None = None,
            imported_meshpart_count: int = 0,
        ) -> RobloxPlaceBuild:
            del recipe
            assert gameplay_mode == "blockout"
            assert imported_model == b"engine-serialized-model"
            return RobloxPlaceBuild(
                place_file=b"fake-reviewed-place",
                object_count=0,
                part_count=0,
                light_count=0,
                approximated_object_count=0,
                omitted_character_count=0,
                omitted_sun_light_count=0,
                imported_meshpart_count=imported_meshpart_count,
            )

    server = RobloxMCPServer(
        "127.0.0.1",
        0,
        _FakeImportValidator(),  # type: ignore[arg-type]
        None,
        "m" * 40,
        asset_uploader=uploader,
        asset_ledger=asset_ledger,
        asset_approval_secret="s" * 40,
        blender_artifact_source=source,  # type: ignore[arg-type]
        model_upload_ledger=PreparedModelUploadLedger(tmp_path / "transfers.sqlite3"),
        place_builder=_FakePlaceBuilder(),  # type: ignore[arg-type]
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def post(message: dict[str, Any]) -> dict[str, Any]:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            connection.request(
                "POST",
                "/mcp",
                body=json.dumps(message).encode(),
                headers={
                    "Authorization": f"Bearer {'m' * 40}",
                    "Content-Type": "application/json",
                    "MCP-Protocol-Version": "2025-11-25",
                },
            )
            return json.loads(connection.getresponse().read())
        finally:
            connection.close()

    try:
        initialized = post({"jsonrpc": "2.0", "id": 0, "method": "initialize"})
        assert "caller-provided Luau is never accepted" in initialized["result"]["instructions"]
        listing = post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = {tool["name"]: tool for tool in listing["result"]["tools"]}
        assert PREPARE_BLENDER_UPLOAD_TOOL_NAME in tools
        assert COMMIT_BLENDER_UPLOAD_TOOL_NAME in tools
        assert tools[PREPARE_BLENDER_UPLOAD_TOOL_NAME]["annotations"]["readOnlyHint"] is True
        assert tools[COMMIT_BLENDER_UPLOAD_TOOL_NAME]["annotations"]["destructiveHint"] is True
        assert (
            "confirmation_phrase"
            in tools[COMMIT_BLENDER_UPLOAD_TOOL_NAME]["inputSchema"]["properties"]
        )
        artifact_id = str(uuid.uuid4())
        prepared_result = post(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": PREPARE_BLENDER_UPLOAD_TOOL_NAME,
                    "arguments": {"artifact_id": artifact_id},
                },
            }
        )["result"]
        prepared = prepared_result["structuredContent"]
        assert "No Roblox asset was created" in prepared_result["content"][0]["text"]
        rejected = post(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": COMMIT_BLENDER_UPLOAD_TOOL_NAME,
                    "arguments": {
                        "request_id": prepared["request_id"],
                        "approval_id": prepared["approval_id"],
                        "artifact_sha256": prepared["artifact_sha256"],
                        "confirmation_phrase": "I_APPROVE_ROBLOX_MODEL_UPLOAD_000000000000",
                    },
                },
            }
        )["result"]
        assert rejected["isError"] is True
        assert uploader.calls == 0
        uploaded = post(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": COMMIT_BLENDER_UPLOAD_TOOL_NAME,
                    "arguments": {
                        "request_id": prepared["request_id"],
                        "approval_id": prepared["approval_id"],
                        "artifact_sha256": prepared["artifact_sha256"],
                        "confirmation_phrase": prepared["confirmation_phrase"],
                    },
                },
            }
        )["result"]
        assert uploaded["structuredContent"]["asset_id"] == "987654321"
        assert asset_ledger.is_approved_model("987654321")
        assert uploader.calls == 2
        repository_root = Path(__file__).resolve().parents[3]
        recipe = json.loads(
            (
                repository_root
                / "examples"
                / "worlds"
                / "mistral-coast-lookout-v2"
                / "scene-recipe.json"
            ).read_text(encoding="utf-8")
        )
        place = post(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "rga_build_place",
                    "arguments": {
                        "recipe": recipe,
                        "request_id": str(uuid.uuid4()),
                        "model_asset_id": "987654321",
                    },
                },
            }
        )["result"]["structuredContent"]
        assert place["imported_meshpart_count"] == 1
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
