import ast
import base64
import hashlib
import http.client
import json
import struct
import sys
import threading
import time
import uuid
import zlib
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from api.blender_mcp import BlenderMCPClient, BlenderMCPError
from apps.blender_mcp_server.server import (
    ARTIFACT_RETENTION_SECONDS,
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACT_STORE_FILES,
    MAX_PREVIEW_BYTES,
    PREVIEW_SIZE,
    ArtifactReceipt,
    BlenderMCPServer,
    BlenderSceneRenderer,
    MCPServiceError,
)
from core.worldbuilding import SceneRecipe

_TOKEN = "b" * 40
_REQUEST_ID = "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329"
_ARTIFACT_ID = "53e2d255-fbf7-5bb2-9c15-0654e5cc9b30"
_RECIPE = {
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


def _glb() -> bytes:
    payload = json.dumps({"asset": {"version": "2.0"}, "meshes": [{}]}).encode()
    payload += b" " * (-len(payload) % 4)
    return (
        struct.pack("<4sII", b"glTF", 2, len(payload) + 20)
        + struct.pack("<I4s", len(payload), b"JSON")
        + payload
    )


def _png(width=PREVIEW_SIZE, height=PREVIEW_SIZE) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        content = kind + data
        return struct.pack(">I", len(data)) + content + struct.pack(">I", zlib.crc32(content))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    pixels = b"\x00" + b"\x00\x00\x00\xff" * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(pixels * height))
        + chunk(b"IEND", b"")
    )


class _Renderer:
    ready = True

    def is_ready(self):
        return self.ready

    def apply_recipe(self, recipe, request_id, *, include_preview=False, preview_mode="isometric"):
        scene = SceneRecipe.from_mapping(recipe)
        return ArtifactReceipt(
            request_id=request_id,
            artifact_id=_ARTIFACT_ID,
            recipe_name=scene.name,
            object_count=len(scene.objects) + len(scene.lights),
            artifact_sha256=hashlib.sha256(_glb()).hexdigest(),
            preview_png=_png() if include_preview else None,
        )

    def read_artifact(self, artifact_id):
        return _glb() if artifact_id == _ARTIFACT_ID else None


@contextmanager
def _server(public_origin=None):
    server = BlenderMCPServer("127.0.0.1", 0, _Renderer(), _TOKEN, public_origin=public_origin)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_mcp_server_build_receipt_and_artifact_download():
    with _server() as server:
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/mcp"
        client = BlenderMCPClient(endpoint, _TOKEN)
        receipt = client.apply_recipe(_RECIPE, _REQUEST_ID)
        assert receipt.request_id == _REQUEST_ID
        assert receipt.artifact_id == _ARTIFACT_ID
        assert receipt.recipe_name == "Test Grove"
        assert receipt.object_count == 1
        assert receipt.artifact_download_url is None
        artifact = client.download_artifact(
            receipt.artifact_id, expected_sha256=receipt.artifact_sha256
        )
        assert artifact == _glb()
        assert receipt.artifact_sha256 == hashlib.sha256(artifact).hexdigest()
        with pytest.raises(BlenderMCPError, match="does not match its receipt SHA-256"):
            client.download_artifact(receipt.artifact_id, expected_sha256="0" * 64)


def test_mcp_server_issues_short_lived_single_artifact_download_url():
    with _server("https://blender.example.test") as server:
        download_url = server.artifact_download_url(_ARTIFACT_ID)
        assert download_url is not None
        parsed_url = urlsplit(download_url)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        try:
            connection.request("GET", f"{parsed_url.path}?{parsed_url.query}")
            response = connection.getresponse()
            assert response.status == 200
            assert response.getheader("Cache-Control") == "private, no-store"
            assert response.getheader("Referrer-Policy") == "no-referrer"
            assert response.read() == _glb()
        finally:
            connection.close()


def test_mcp_server_rejects_expired_or_modified_download_capabilities():
    with _server("https://blender.example.test") as server:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        try:
            expired = int(time.time()) - 1
            signature = server.artifact_download_signature(_ARTIFACT_ID, expired)
            connection.request(
                "GET",
                f"/artifacts/{_ARTIFACT_ID}.glb?expires={expired}&signature={signature}",
            )
            response = connection.getresponse()
            assert response.status == 401
            response.read()

            expires = int(time.time()) + 60
            connection.request(
                "GET",
                f"/artifacts/{_ARTIFACT_ID}.glb?expires={expires}&signature={'0' * 64}",
            )
            response = connection.getresponse()
            assert response.status == 401
            response.read()

            wrong_artifact = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
            signature = server.artifact_download_signature(_ARTIFACT_ID, expires)
            connection.request(
                "GET",
                f"/artifacts/{wrong_artifact}.glb?expires={expires}&signature={signature}",
            )
            response = connection.getresponse()
            assert response.status == 401
            response.read()

            excessive_expiry = int(time.time()) + 16 * 60
            signature = server.artifact_download_signature(_ARTIFACT_ID, excessive_expiry)
            connection.request(
                "GET",
                f"/artifacts/{_ARTIFACT_ID}.glb?expires={excessive_expiry}&signature={signature}",
            )
            response = connection.getresponse()
            assert response.status == 401
            response.read()

            connection.request(
                "GET",
                f"/artifacts/{_ARTIFACT_ID}.glb?expires={expires}&expires={expires}"
                f"&signature={'0' * 64}",
            )
            response = connection.getresponse()
            assert response.status == 401
            response.read()
        finally:
            connection.close()


@pytest.mark.parametrize(
    "origin",
    [
        "http://blender.example.test",
        "https://blender.example.test/mcp",
        "https://user@blender.example.test",
    ],
)
def test_server_rejects_invalid_public_artifact_origins(origin):
    with pytest.raises(ValueError, match="HTTPS origin"):
        BlenderMCPServer("127.0.0.1", 0, _Renderer(), _TOKEN, public_origin=origin)


def test_mcp_server_supports_standard_initialize_handshake_and_tool_call():
    with _server("https://blender.example.test") as server:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        base_headers = {
            "Authorization": f"Bearer {_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        def post(message, extra_headers=None):
            connection.request(
                "POST",
                "/mcp",
                body=json.dumps(message).encode(),
                headers=base_headers | (extra_headers or {}),
            )
            response = connection.getresponse()
            body = response.read()
            return response.status, json.loads(body) if body else None

        try:
            status, initialized = post(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "1.0"},
                    },
                }
            )
            assert status == 200
            assert initialized["result"]["protocolVersion"] == "2025-11-25"

            status, initialized_notice = post(
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"MCP-Protocol-Version": "2025-11-25"},
            )
            assert status == 202
            assert initialized_notice is None

            status, listed = post(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"MCP-Protocol-Version": "2025-11-25"},
            )
            assert status == 200
            assert [tool["name"] for tool in listed["result"]["tools"]] == [
                "rga_apply_scene_recipe"
            ]
            output_schema = listed["result"]["tools"][0]["outputSchema"]
            assert (
                listed["result"]["tools"][0]["inputSchema"]["properties"]["include_preview"]["type"]
                == "boolean"
            )
            assert listed["result"]["tools"][0]["inputSchema"]["properties"]["preview_mode"][
                "enum"
            ] == [
                "isometric",
                "cutaway",
            ]
            assert "artifact_download_url" in output_schema["properties"]
            assert "artifact_download_url" not in output_schema["required"]
            assert "artifact_sha256" in output_schema["required"]
            assert output_schema["properties"]["artifact_sha256"]["pattern"] == "^[0-9a-f]{64}$"

            status, called = post(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "rga_apply_scene_recipe",
                        "arguments": {"recipe": _RECIPE, "request_id": _REQUEST_ID},
                    },
                },
                {"MCP-Protocol-Version": "2025-11-25"},
            )
            assert status == 200
            assert called["result"]["structuredContent"]["artifact_id"] == _ARTIFACT_ID
            assert called["result"]["structuredContent"]["artifact_download_url"].startswith(
                "https://blender.example.test/artifacts/"
            )
            status, previewed = post(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "rga_apply_scene_recipe",
                        "arguments": {
                            "recipe": _RECIPE,
                            "request_id": "27b56f37-2797-4ab1-9b2c-0e7437c8787a",
                            "include_preview": True,
                            "preview_mode": "cutaway",
                        },
                    },
                },
                {"MCP-Protocol-Version": "2025-11-25"},
            )
            assert status == 200
            image = previewed["result"]["content"][1]
            assert image["type"] == "image"
            assert image["mimeType"] == "image/png"
            assert base64.b64decode(image["data"]) == _png()
        finally:
            connection.close()


def test_mcp_server_modern_discovery_and_cacheable_tool_listing():
    with _server() as server:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        headers = {
            "Authorization": f"Bearer {_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2026-07-28",
        }

        def post(request_id, method, params):
            connection.request(
                "POST",
                "/mcp",
                body=json.dumps(
                    {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
                ).encode(),
                headers=headers | {"Mcp-Method": method},
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read())

        meta = {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientInfo": {"name": "test-client", "version": "1.0"},
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        try:
            status, discovered = post("d1", "server/discover", {"_meta": meta})
            assert status == 200
            discovery = discovered["result"]
            assert discovery["resultType"] == "complete"
            assert "2026-07-28" in discovery["supportedVersions"]
            assert discovery["ttlMs"] == 0
            assert discovery["cacheScope"] == "private"

            status, listed = post(1, "tools/list", {"_meta": meta})
            assert status == 200
            listing = listed["result"]
            assert listing["resultType"] == "complete"
            assert listing["ttlMs"] == 0
            assert listing["cacheScope"] == "private"
        finally:
            connection.close()


def test_mcp_server_rejects_unapproved_browser_origin():
    with _server() as server:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        try:
            connection.request(
                "POST",
                "/mcp",
                body=b"{}",
                headers={
                    "Authorization": f"Bearer {_TOKEN}",
                    "Origin": "https://attacker.test",
                },
            )
            assert connection.getresponse().status == 403
        finally:
            connection.close()


def test_mcp_health_endpoint_reports_renderer_state_without_auth():
    with _server() as server:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
        try:
            connection.request("GET", "/healthz")
            response = connection.getresponse()
            assert response.status == 200
            assert json.loads(response.read()) == {"status": "ok"}

            server.renderer.ready = False
            connection.request("GET", "/healthz")
            unavailable = connection.getresponse()
            assert unavailable.status == 503
            assert json.loads(unavailable.read()) == {"status": "unavailable"}
        finally:
            server.renderer.ready = True
            connection.close()


def test_renderer_health_check_requires_blender_worker_and_artifact_ledger(tmp_path):
    executable = tmp_path / "blender"
    executable.write_bytes(b"placeholder")
    project_root = tmp_path / "project"
    addon = project_root / "apps" / "blender-addon" / "rga_scene_builder"
    worker = project_root / "apps" / "blender_mcp_server" / "worker.py"
    addon.mkdir(parents=True)
    worker.parent.mkdir(parents=True)
    (addon / "__init__.py").write_text("", encoding="utf-8")
    worker.write_text("", encoding="utf-8")
    renderer = BlenderSceneRenderer(
        executable,
        tmp_path / "artifacts",
        project_root=project_root,
    )

    assert renderer.is_ready()
    worker.unlink()
    assert not renderer.is_ready()
    worker.write_text("", encoding="utf-8")
    renderer.database_path.unlink()
    assert not renderer.is_ready()
    renderer.database_path.touch()
    executable.unlink()
    assert not renderer.is_ready()


def _storage_renderer(
    tmp_path,
    *,
    max_store_bytes=MAX_ARTIFACT_BYTES * 2,
    max_store_files=MAX_ARTIFACT_STORE_FILES,
):
    executable = tmp_path / "blender"
    executable.write_bytes(b"placeholder")
    project_root = tmp_path / "project"
    addon = project_root / "apps" / "blender-addon" / "rga_scene_builder" / "__init__.py"
    worker = project_root / "apps" / "blender_mcp_server" / "worker.py"
    addon.parent.mkdir(parents=True, exist_ok=True)
    worker.parent.mkdir(parents=True, exist_ok=True)
    addon.write_text("", encoding="utf-8")
    worker.write_text("", encoding="utf-8")
    return BlenderSceneRenderer(
        executable,
        tmp_path / "artifacts",
        project_root=project_root,
        max_store_bytes=max_store_bytes,
        max_store_files=max_store_files,
    )


def test_renderer_removes_valid_uuid_artifact_orphans_on_startup(tmp_path):
    renderer = _storage_renderer(tmp_path)
    orphan_id = str(uuid.uuid4())
    orphan_path = renderer.output_dir / f"{orphan_id}.glb"
    orphan_path.write_bytes(b"orphaned after interrupted ledger commit")

    restarted = _storage_renderer(tmp_path)

    assert not orphan_path.exists()
    assert restarted.read_artifact(orphan_id) is None


def test_renderer_health_check_fails_when_glb_storage_exceeds_the_cap(tmp_path):
    renderer = _storage_renderer(tmp_path, max_store_bytes=MAX_ARTIFACT_BYTES)
    oversized_id = str(uuid.uuid4())
    oversized_path = renderer.output_dir / f"{oversized_id}.glb"
    oversized_path.touch()
    with oversized_path.open("r+b") as stream:
        stream.truncate(MAX_ARTIFACT_BYTES + 1)

    assert not renderer.is_ready()


def test_renderer_health_check_fails_when_glb_file_count_exceeds_the_cap(tmp_path):
    renderer = _storage_renderer(tmp_path, max_store_files=1)
    artifact_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    for index, artifact_id in enumerate(artifact_ids):
        (renderer.output_dir / f"{artifact_id}.glb").write_bytes(_glb())
        with renderer._connect() as db:
            db.execute(
                "INSERT INTO requests(request_id, recipe_digest, artifact_id, created_at) "
                "VALUES(?, ?, ?, ?)",
                (str(uuid.uuid4()), "0" * 64, artifact_id, int(time.time()) + index),
            )

    assert not renderer.is_ready()
    with renderer._connect() as db:
        renderer._prune_artifacts(db, int(time.time()), preserve_artifact=artifact_ids[1])

    assert not (renderer.output_dir / f"{artifact_ids[0]}.glb").exists()
    assert (renderer.output_dir / f"{artifact_ids[1]}.glb").is_file()
    assert renderer.is_ready()


def test_renderer_refuses_to_serve_artifacts_past_retention(tmp_path):
    renderer = _storage_renderer(tmp_path)
    artifact_id = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    (renderer.output_dir / f"{artifact_id}.glb").write_bytes(_glb())
    with renderer._connect() as db:
        db.execute(
            "INSERT INTO requests(request_id, recipe_digest, artifact_id, created_at) "
            "VALUES(?, ?, ?, ?)",
            (
                request_id,
                "0" * 64,
                artifact_id,
                int(time.time()) - ARTIFACT_RETENTION_SECONDS - 1,
            ),
        )

    assert renderer.read_artifact(artifact_id) is None


def test_renderer_does_not_forget_artifact_when_storage_prune_cannot_unlink(tmp_path, monkeypatch):
    renderer = _storage_renderer(tmp_path, max_store_bytes=MAX_ARTIFACT_BYTES)
    old_id = str(uuid.uuid4())
    current_id = str(uuid.uuid4())
    old_path = renderer.output_dir / f"{old_id}.glb"
    old_path.touch()
    with old_path.open("r+b") as stream:
        stream.truncate(MAX_ARTIFACT_BYTES)
    current_path = renderer.output_dir / f"{current_id}.glb"
    current_path.write_bytes(_glb())
    with renderer._connect() as db:
        for index, artifact_id in enumerate((old_id, current_id)):
            request_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO requests(request_id, recipe_digest, artifact_id, created_at) "
                "VALUES(?, ?, ?, ?)",
                (request_id, "0" * 64, artifact_id, int(time.time()) + index),
            )

    monkeypatch.setattr(renderer, "_remove_artifact_file", lambda artifact_id: False)
    with pytest.raises(MCPServiceError, match="storage limit cannot be enforced"):
        with renderer._connect() as db:
            renderer._prune_artifacts(db, int(time.time()), preserve_artifact=current_id)

    assert old_path.is_file()
    with renderer._connect() as db:
        assert (
            db.execute("SELECT 1 FROM requests WHERE artifact_id = ?", (old_id,)).fetchone()
            is not None
        )


def test_renderer_uses_only_trusted_bounded_worker_and_is_idempotent(tmp_path, monkeypatch):
    import apps.blender_mcp_server.server as blender_server

    executable = tmp_path / "blender"
    executable.write_bytes(b"placeholder")
    project_root = tmp_path / "project"
    worker = project_root / "apps" / "blender_mcp_server" / "worker.py"
    addon = project_root / "apps" / "blender-addon" / "rga_scene_builder" / "__init__.py"
    addon.parent.mkdir(parents=True)
    worker.parent.mkdir(parents=True)
    addon.write_text("", encoding="utf-8")
    worker.write_text("", encoding="utf-8")
    renderer = BlenderSceneRenderer(
        executable,
        tmp_path / "artifacts",
        project_root=project_root,
    )
    launches = []

    def fake_run(command, **kwargs):
        launches.append((command, kwargs))
        assert command[0] == str(executable)
        assert "--background" in command
        assert "--factory-startup" in command
        assert "--python-exit-code" in command
        assert "--python" in command
        assert command[command.index("--python") + 1] == str(worker)
        assert "--python-expr" not in command
        assert kwargs["timeout_seconds"] == blender_server.WORKER_TIMEOUT_SECONDS
        assert kwargs["memory_limit_bytes"] == blender_server.WORKER_MEMORY_LIMIT_BYTES
        assert kwargs["max_stdout_bytes"] == 512 * 1024
        assert kwargs["max_stderr_bytes"] == 64 * 1024
        recipe_path = Path(command[command.index("--recipe") + 1])
        output_path = Path(command[command.index("--output") + 1])
        result_path = Path(command[command.index("--result") + 1])
        assert json.loads(recipe_path.read_text(encoding="utf-8")) == _RECIPE
        assert kwargs["env"]["HOME"] == str(recipe_path.parent)
        assert kwargs["env"]["TMPDIR"] == str(recipe_path.parent)
        assert "SECRET_TEST_VALUE" not in kwargs["env"].values()
        output_path.write_bytes(_glb())
        if "--preview-output" in command:
            Path(command[command.index("--preview-output") + 1]).write_bytes(_png())
        result_path.write_text('{"created_objects":1}', encoding="utf-8")

    monkeypatch.setenv("SECRET_TEST_VALUE", "should-not-reach-worker")
    monkeypatch.setattr(blender_server, "_run_bounded", fake_run)

    receipt = renderer.apply_recipe(_RECIPE, _REQUEST_ID)

    assert receipt.request_id == _REQUEST_ID
    assert receipt.artifact_id == str(uuid.uuid5(blender_server._REQUEST_NAMESPACE, _REQUEST_ID))
    assert receipt.object_count == 1
    assert renderer.read_artifact(receipt.artifact_id) == _glb()
    assert len(launches) == 1
    replay = renderer.apply_recipe(_RECIPE, _REQUEST_ID)
    assert replay == receipt
    assert len(launches) == 1
    changed_recipe = dict(_RECIPE, name="Changed recipe")
    with pytest.raises(ValueError, match="different scene recipe"):
        renderer.apply_recipe(changed_recipe, _REQUEST_ID)
    assert len(launches) == 1
    preview_request = "b159a547-6f8f-4f99-a713-f440e7a9070c"
    previewed = renderer.apply_recipe(
        _RECIPE, preview_request, include_preview=True, preview_mode="cutaway"
    )
    assert previewed.preview_png == _png()
    assert "preview_png" not in previewed.as_mapping()
    assert len(previewed.preview_png) < MAX_PREVIEW_BYTES
    assert "--preview-output" in launches[-1][0]
    assert launches[-1][0][launches[-1][0].index("--preview-mode") + 1] == "cutaway"
    assert len(launches) == 2
    preview_retry = renderer.apply_recipe(_RECIPE, preview_request, include_preview=True)
    assert preview_retry.artifact_sha256 == previewed.artifact_sha256
    assert preview_retry.preview_png == _png()
    assert len(launches) == 3


@pytest.mark.parametrize("preview", [b"", b"not a png", _png(64, 64), _png() + b"x"])
def test_preview_validator_rejects_malformed_or_wrong_size_png(preview):
    with pytest.raises(MCPServiceError):
        BlenderSceneRenderer._validate_preview(preview)


def test_blender_worker_contract_is_present():
    from apps.blender_mcp_server.server import REPOSITORY_ROOT

    assert (Path(REPOSITORY_ROOT) / "apps" / "blender_mcp_server" / "worker.py").is_file()


def test_blender_worker_omits_unsupported_gltf_light_extension():
    from apps.blender_mcp_server.server import REPOSITORY_ROOT

    worker = Path(REPOSITORY_ROOT) / "apps" / "blender_mcp_server" / "worker.py"
    tree = ast.parse(worker.read_text(encoding="utf-8"))
    exporter_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "bpy.ops.export_scene.gltf"
    ]

    assert len(exporter_calls) == 1
    options = {item.arg: item.value for item in exporter_calls[0].keywords}
    assert isinstance(options.get("export_lights"), ast.Constant)
    assert options["export_lights"].value is False


def test_client_rejects_invalid_glb_download():
    with pytest.raises(BlenderMCPError, match="valid GLB"):
        BlenderMCPClient._validate_glb_bytes(b"not a glb" * 3)
