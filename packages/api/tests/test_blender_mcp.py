import base64
import json
import struct
import time
import zlib

import pytest

from api.blender_mcp import BlenderMCPClient, BlenderMCPError


def _tool(name="rga_apply_scene_recipe"):
    return {
        "name": name,
        "inputSchema": {
            "type": "object",
            "properties": {
                "recipe": {"type": "object"},
                "request_id": {"type": "string"},
                "include_preview": {"type": "boolean"},
                "preview_mode": {"type": "string", "enum": ["isometric", "cutaway"]},
            },
            "required": ["recipe", "request_id"],
            "additionalProperties": False,
        },
    }


def _recipe():
    return {
        "schema_version": 2,
        "name": "Test",
        "units": "blender_units",
        "up_axis": "Z",
        "objects": [
            {
                "name": "Ground",
                "primitive": "cube",
                "role": "terrain",
                "location": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [1, 1, 1],
            }
        ],
    }


def _preview_png():
    def chunk(kind, data):
        value = kind + data
        return struct.pack(">I", len(data)) + value + struct.pack(">I", zlib.crc32(value))

    header = struct.pack(">IIBBBBB", 512, 512, 8, 6, 0, 0, 0)
    pixels = zlib.compress((b"\x00" + b"\x00\x00\x00\xff" * 512) * 512)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")
    )


class _Response:
    def __init__(self, status, body=b"", headers=None):
        self.status = status
        self._body = body
        self._headers = {"Content-Type": "application/json"} | (headers or {})

    def getheaders(self):
        return list(self._headers.items())

    def read(self, _limit=None):
        return self._body


class _Connection:
    def __init__(self, tool=None, *, modern=True):
        self.tool = tool or _tool()
        self.modern = modern
        self.current = None
        self.messages = []
        self.closed = False

    def request(self, method, path, body=None, headers=None):
        self.current = method, path, body, headers or {}
        if body:
            self.messages.append(json.loads(body))

    def getresponse(self):
        method, _path, _body, headers = self.current
        if method == "DELETE":
            return _Response(200, b"")
        message = self.messages[-1]
        if headers.get("MCP-Protocol-Version") == "2026-07-28" and not self.modern:
            return _Response(400, b'{"jsonrpc":"2.0","error":{"code":-32600}}')
        if message.get("method") == "notifications/initialized":
            return _Response(202, b"")
        if message.get("method") == "initialize":
            result = {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "serverInfo": {"name": "test", "version": "1"},
            }
            return _Response(
                200,
                json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode(),
                {"Mcp-Session-Id": "session-1"},
            )
        if message.get("method") == "tools/list":
            return _Response(
                200,
                json.dumps(
                    {"jsonrpc": "2.0", "id": message["id"], "result": {"tools": [self.tool]}}
                ).encode(),
            )
        if message.get("method") == "tools/call":
            arguments = message["params"]["arguments"]
            content = []
            if arguments.get("include_preview") is True:
                content.append(
                    {
                        "type": "image",
                        "mimeType": "image/png",
                        "data": base64.b64encode(_preview_png()).decode("ascii"),
                    }
                )
            return _Response(
                200,
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "result": {
                            "content": content,
                            "structuredContent": {
                                "request_id": message["params"]["arguments"]["request_id"],
                                "artifact_id": "53e2d255-fbf7-5bb2-9c15-0654e5cc9b30",
                                "recipe_name": message["params"]["arguments"]["recipe"]["name"],
                                "artifact_sha256": "a" * 64,
                                "artifact_download_url": (
                                    "https://blender.example.test/artifacts/"
                                    "53e2d255-fbf7-5bb2-9c15-0654e5cc9b30.glb?"
                                    f"expires={int(time.time()) + 60}&signature=" + "a" * 64
                                ),
                                "object_count": len(
                                    message["params"]["arguments"]["recipe"]["objects"]
                                )
                                + len(message["params"]["arguments"]["recipe"].get("lights", []))
                                + 17
                                * len(
                                    message["params"]["arguments"]["recipe"].get("characters", [])
                                ),
                            },
                        },
                    }
                ).encode(),
            )
        raise AssertionError(message)

    def close(self):
        self.closed = True


def test_remote_client_uses_modern_stateless_transport_and_only_recipe_tool(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr("api.blender_mcp.http.client.HTTPSConnection", lambda *a, **k: connection)
    client = BlenderMCPClient("https://blender.example.test/mcp", "a" * 40)
    client.apply_recipe(_recipe(), "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329")
    assert [message.get("method") for message in connection.messages] == [
        "tools/list",
        "tools/call",
    ]
    call = connection.messages[-1]
    assert call["params"]["name"] == "rga_apply_scene_recipe"
    assert call["params"]["arguments"]["request_id"] == "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329"
    assert call["params"]["_meta"]["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
    assert connection.current[3]["Mcp-Method"] == "tools/call"
    assert connection.current[3]["Mcp-Name"] == "rga_apply_scene_recipe"
    assert connection.current[3]["Authorization"] == f"Bearer {'a' * 40}"
    assert connection.closed


def test_remote_client_returns_verified_artifact_receipt(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr("api.blender_mcp.http.client.HTTPSConnection", lambda *a, **k: connection)
    client = BlenderMCPClient("https://blender.example.test/mcp", "a" * 40)
    receipt = client.apply_recipe(
        _recipe(),
        "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329",
    )
    assert receipt.artifact_id == "53e2d255-fbf7-5bb2-9c15-0654e5cc9b30"
    assert receipt.object_count == 1
    assert receipt.artifact_sha256 == "a" * 64
    assert receipt.artifact_download_url.startswith(
        "https://blender.example.test/artifacts/53e2d255-fbf7-5bb2-9c15-0654e5cc9b30.glb?"
    )


def test_remote_client_requests_and_verifies_optional_preview(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr("api.blender_mcp.http.client.HTTPSConnection", lambda *a, **k: connection)
    receipt = BlenderMCPClient("https://blender.example.test/mcp", "a" * 40).apply_recipe(
        _recipe(), "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329", include_preview=True
    )
    assert connection.messages[-1]["params"]["arguments"]["include_preview"] is True
    assert receipt.preview_png == _preview_png()


def test_remote_client_requests_cutaway_preview(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr("api.blender_mcp.http.client.HTTPSConnection", lambda *a, **k: connection)

    BlenderMCPClient("https://blender.example.test/mcp", "x" * 32).apply_recipe(
        _recipe(),
        "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329",
        include_preview=True,
        preview_mode="cutaway",
    )

    arguments = connection.messages[-1]["params"]["arguments"]
    assert arguments["include_preview"] is True
    assert arguments["preview_mode"] == "cutaway"


def test_remote_client_rejects_preview_when_server_does_not_advertise_it(monkeypatch):
    connection = _Connection()
    connection.tool["inputSchema"]["properties"].pop("include_preview")
    monkeypatch.setattr("api.blender_mcp.http.client.HTTPSConnection", lambda *a, **k: connection)
    client = BlenderMCPClient("https://blender.example.test/mcp", "a" * 40)
    with pytest.raises(BlenderMCPError, match="safe RGA tool contract"):
        client.apply_recipe(_recipe(), "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329", include_preview=True)
    assert not any(message.get("method") == "tools/call" for message in connection.messages)


def test_remote_client_accepts_explicit_default_https_port_for_signed_link(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr("api.blender_mcp.http.client.HTTPSConnection", lambda *a, **k: connection)
    client = BlenderMCPClient("https://blender.example.test:443/mcp", "a" * 40)

    receipt = client.apply_recipe(_recipe(), "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329")

    assert receipt.artifact_download_url.startswith(
        "https://blender.example.test/artifacts/53e2d255-fbf7-5bb2-9c15-0654e5cc9b30.glb?"
    )


@pytest.mark.parametrize(
    "download_url",
    [
        "https://attacker.test/artifacts/53e2d255-fbf7-5bb2-9c15-0654e5cc9b30.glb"
        "?expires=0&signature=" + "a" * 64,
        "https://blender.example.test:444/artifacts/53e2d255-fbf7-5bb2-9c15-0654e5cc9b30.glb"
        f"?expires={int(time.time()) + 60}&signature=" + "a" * 64,
        "https://blender.example.test/artifacts/cccccccc-cccc-4ccc-8ccc-cccccccccccc.glb"
        "?expires=0&signature=" + "a" * 64,
        "https://blender.example.test/artifacts/53e2d255-fbf7-5bb2-9c15-0654e5cc9b30.glb"
        f"?expires={int(time.time()) + 16 * 60}&signature=" + "a" * 64,
        "https://blender.example.test/artifacts/53e2d255-fbf7-5bb2-9c15-0654e5cc9b30.glb"
        "?expires=0&signature=" + "a" * 64,
    ],
)
def test_remote_client_rejects_untrusted_artifact_download_links(monkeypatch, download_url):
    connection = _Connection()
    original_getresponse = connection.getresponse

    def getresponse_with_url():
        response = original_getresponse()
        if connection.messages[-1].get("method") == "tools/call":
            payload = json.loads(response._body)
            payload["result"]["structuredContent"]["artifact_download_url"] = download_url
            response._body = json.dumps(payload).encode()
        return response

    connection.getresponse = getresponse_with_url
    monkeypatch.setattr("api.blender_mcp.http.client.HTTPSConnection", lambda *a, **k: connection)
    client = BlenderMCPClient("https://blender.example.test/mcp", "a" * 40)
    with pytest.raises(BlenderMCPError, match="invalid artifact receipt"):
        client.apply_recipe(_recipe(), "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329")


@pytest.mark.parametrize("digest", [None, "A" * 64, "0" * 63, 123])
def test_remote_client_rejects_invalid_artifact_digest(monkeypatch, digest):
    connection = _Connection()
    original_getresponse = connection.getresponse

    def response_with_invalid_digest():
        response = original_getresponse()
        if connection.messages[-1].get("method") == "tools/call":
            payload = json.loads(response._body)
            if digest is None:
                del payload["result"]["structuredContent"]["artifact_sha256"]
            else:
                payload["result"]["structuredContent"]["artifact_sha256"] = digest
            response._body = json.dumps(payload).encode()
        return response

    connection.getresponse = response_with_invalid_digest
    monkeypatch.setattr("api.blender_mcp.http.client.HTTPSConnection", lambda *a, **k: connection)
    client = BlenderMCPClient("https://blender.example.test/mcp", "a" * 40)
    with pytest.raises(BlenderMCPError, match="invalid artifact receipt"):
        client.apply_recipe(_recipe(), "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329")


def test_remote_client_verifies_character_rig_object_count(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr("api.blender_mcp.http.client.HTTPSConnection", lambda *a, **k: connection)
    recipe = _recipe()
    recipe["characters"] = [
        {"name": "Coast Guard", "motion": "WALK", "location": [0, 0, 0], "scale": [1, 1, 1]}
    ]

    receipt = BlenderMCPClient("https://blender.example.test/mcp", "a" * 40).apply_recipe(
        recipe, "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329"
    )

    assert receipt.object_count == 18


def test_remote_client_refuses_generic_python_execution_tools(monkeypatch):
    connection = _Connection(_tool("execute_blender_code"))
    monkeypatch.setattr("api.blender_mcp.http.client.HTTPSConnection", lambda *a, **k: connection)
    client = BlenderMCPClient("https://blender.example.test/mcp", "a" * 40)
    with pytest.raises(BlenderMCPError, match="must expose"):
        client.apply_recipe({}, "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329")
    assert not any(message.get("method") == "tools/call" for message in connection.messages)


def test_remote_client_falls_back_to_legacy_handshake_server(monkeypatch):
    connection = _Connection(modern=False)
    monkeypatch.setattr("api.blender_mcp.http.client.HTTPSConnection", lambda *a, **k: connection)
    client = BlenderMCPClient("https://blender.example.test/mcp", "a" * 40)
    client.apply_recipe(_recipe(), "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329")
    methods = [message.get("method") for message in connection.messages]
    assert methods == [
        "tools/list",
        "initialize",
        "notifications/initialized",
        "tools/list",
        "tools/call",
    ]
    assert connection.closed


def test_remote_client_rejects_receipt_for_another_request(monkeypatch):
    connection = _Connection()
    original_response = connection.getresponse

    def mismatched_response():
        response = original_response()
        if connection.messages[-1].get("method") == "tools/call":
            payload = json.loads(response._body)
            payload["result"]["structuredContent"]["request_id"] = (
                "53e2d255-fbf7-5bb2-9c15-0654e5cc9b30"
            )
            response._body = json.dumps(payload).encode()
        return response

    connection.getresponse = mismatched_response
    monkeypatch.setattr("api.blender_mcp.http.client.HTTPSConnection", lambda *a, **k: connection)
    client = BlenderMCPClient("https://blender.example.test/mcp", "a" * 40)
    with pytest.raises(BlenderMCPError, match="invalid artifact receipt"):
        client.apply_recipe(
            _recipe(),
            "7a4814a5-b959-4fad-8c4e-4d9d3f5ab329",
        )


def test_remote_endpoint_requires_tls_and_authentication():
    with pytest.raises(ValueError, match="HTTPS"):
        BlenderMCPClient("http://blender.example.test/mcp", "a" * 40)
    with pytest.raises(ValueError, match="bearer token"):
        BlenderMCPClient("https://blender.example.test/mcp")


def test_localhost_mcp_is_available_for_local_development():
    client = BlenderMCPClient("http://127.0.0.1:8788/mcp")
    assert client.audit_host == "127.0.0.1"
