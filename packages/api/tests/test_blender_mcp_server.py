import http.client
import json
import struct
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from api.blender_mcp import BlenderMCPClient, BlenderMCPError
from apps.blender_mcp_server.server import (
    ArtifactReceipt,
    BlenderMCPServer,
    BlenderSceneRenderer,
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


class _Renderer:
    ready = True

    def is_ready(self):
        return self.ready

    def apply_recipe(self, recipe, request_id):
        scene = SceneRecipe.from_mapping(recipe)
        return ArtifactReceipt(
            request_id=request_id,
            artifact_id=_ARTIFACT_ID,
            recipe_name=scene.name,
            object_count=len(scene.objects) + len(scene.lights),
        )

    def read_artifact(self, artifact_id):
        return _glb() if artifact_id == _ARTIFACT_ID else None


@contextmanager
def _server():
    server = BlenderMCPServer("127.0.0.1", 0, _Renderer(), _TOKEN)
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
        artifact = client.download_artifact(receipt.artifact_id)
        assert artifact == _glb()


def test_mcp_server_supports_standard_initialize_handshake_and_tool_call():
    with _server() as server:
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


def test_blender_worker_contract_is_present():
    from apps.blender_mcp_server.server import REPOSITORY_ROOT

    assert (Path(REPOSITORY_ROOT) / "apps" / "blender_mcp_server" / "worker.py").is_file()


def test_client_rejects_invalid_glb_download():
    with pytest.raises(BlenderMCPError, match="valid GLB"):
        BlenderMCPClient._validate_glb_bytes(b"not a glb" * 3)
