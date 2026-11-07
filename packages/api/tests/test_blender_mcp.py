import json

import pytest

from api.blender_mcp import BlenderMCPClient, BlenderMCPError


def _tool(name="rga_apply_scene_recipe"):
    return {
        "name": name,
        "inputSchema": {
            "type": "object",
            "properties": {"recipe": {"type": "object"}, "request_id": {"type": "string"}},
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
            return _Response(
                200,
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "result": {
                            "content": [],
                            "structuredContent": {
                                "request_id": message["params"]["arguments"]["request_id"],
                                "artifact_id": "53e2d255-fbf7-5bb2-9c15-0654e5cc9b30",
                                "recipe_name": message["params"]["arguments"]["recipe"]["name"],
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
