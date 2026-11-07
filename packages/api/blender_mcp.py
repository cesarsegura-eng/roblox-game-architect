"""Fail-closed client for the project's remote Blender MCP tool contract.

This client never calls Blender's generic Python execution tools. The configured
server must expose ``rga_apply_scene_recipe`` with the exact input shape below.
"""

from __future__ import annotations

import http.client
import json
import re
import ssl
import struct
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

MODERN_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
CLIENT_NAME = "roblox-game-architect"
CLIENT_VERSION = "0.0.0"
RECIPE_TOOL = "rga_apply_scene_recipe"
_MAX_RESPONSE_BYTES = 1_200_000
_MAX_TOOL_PAGES = 8
_BEARER = re.compile(r"[A-Za-z0-9._~+/-]+=*\Z", re.ASCII)
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class BlenderMCPReceipt:
    """Verified metadata for a remotely rendered, downloadable GLB artifact."""

    request_id: str
    artifact_id: str
    recipe_name: str
    object_count: int


def _parse_json(body: bytes) -> object:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON number {value}")

    if len(body) > _MAX_RESPONSE_BYTES:
        raise ValueError("MCP response exceeds the size limit")
    return json.loads(body, object_pairs_hook=unique, parse_constant=reject_constant)


class BlenderMCPError(RuntimeError):
    """The remote MCP server is unavailable or does not satisfy the safe contract."""


class _LegacyServerDetected(BlenderMCPError):
    """The endpoint rejected modern metadata and may use a handshake protocol."""


class BlenderMCPClient:
    """Connect to an administrator-configured remote MCP endpoint and apply a recipe."""

    def __init__(self, endpoint: str, bearer_token: str = "", *, timeout: float = 120.0) -> None:
        if not isinstance(endpoint, str) or not endpoint:
            raise ValueError("BLENDER_MCP_URL must be a non-empty HTTPS URL")
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("BLENDER_MCP_URL must be a plain HTTP(S) endpoint without userinfo")
        loopback = parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not loopback:
            raise ValueError("remote Blender MCP endpoints must use HTTPS")
        if not loopback and not 32 <= len(bearer_token) <= 512:
            raise ValueError("remote Blender MCP requires a 32-512 character bearer token")
        if bearer_token and (not bearer_token.isascii() or not _BEARER.fullmatch(bearer_token)):
            raise ValueError("BLENDER_MCP_BEARER_TOKEN has invalid characters")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 1 <= timeout <= 300
        ):
            raise ValueError("Blender MCP timeout must be between 1 and 300 seconds")
        self._endpoint = parsed
        self._token = bearer_token
        self._timeout = float(timeout)

    @property
    def audit_host(self) -> str:
        """The configured server host, safe for the local audit log."""
        return self._endpoint.hostname or "unknown"

    def apply_recipe(self, recipe: Mapping[str, Any], request_id: str) -> BlenderMCPReceipt:
        """Send a recipe to the fixed Blender tool and verify its artifact receipt."""
        try:
            uuid.UUID(request_id)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("request_id must be a UUID") from exc
        connection = self._connection()
        try:
            try:
                receipt = self._apply_modern(connection, dict(recipe), request_id)
            except _LegacyServerDetected:
                receipt = self._apply_legacy(connection, dict(recipe), request_id)
            return receipt
        except BlenderMCPError:
            raise
        except (OSError, http.client.HTTPException, ValueError, TypeError, RecursionError) as exc:
            raise BlenderMCPError("remote Blender MCP request failed") from exc
        finally:
            connection.close()

    def check_connection(self, *, timeout: float = 5.0) -> None:
        """Confirm the remote MCP responds and exposes the fixed recipe tool."""
        if not 1 <= timeout <= 15:
            raise ValueError("health-check timeout must be between 1 and 15 seconds")
        connection = self._connection()
        connection.timeout = timeout
        try:
            try:
                response = self._post(
                    connection,
                    self._modern_message(1, "tools/list", {}),
                    modern=True,
                )[0]
                tool = self._find_recipe_tool(connection, response, modern=True)
            except _LegacyServerDetected as exc:
                initialized = self._post(
                    connection,
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": LEGACY_PROTOCOL_VERSION,
                            "capabilities": {},
                            "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
                        },
                    },
                    protocol_version=None,
                )
                session_id = initialized[1].get("mcp-session-id")
                init_result = initialized[0].get("result")
                if (
                    not isinstance(init_result, dict)
                    or init_result.get("protocolVersion") != LEGACY_PROTOCOL_VERSION
                ):
                    raise BlenderMCPError(
                        "remote Blender MCP initialization is incompatible"
                    ) from exc
                try:
                    self._post(
                        connection,
                        {"jsonrpc": "2.0", "method": "notifications/initialized"},
                        session_id=session_id,
                        protocol_version=LEGACY_PROTOCOL_VERSION,
                        allow_accepted=True,
                    )
                    tool = self._find_recipe_tool(connection, modern=False, session_id=session_id)
                finally:
                    if session_id:
                        self._delete_session(connection, session_id, LEGACY_PROTOCOL_VERSION)
            self._check_tool_schema(tool)
        except BlenderMCPError:
            raise
        except (OSError, http.client.HTTPException, ValueError, TypeError, RecursionError) as exc:
            raise BlenderMCPError("remote Blender MCP health check failed") from exc
        finally:
            connection.close()

    def _apply_modern(
        self, connection: http.client.HTTPConnection, recipe: dict[str, Any], request_id: str
    ) -> BlenderMCPReceipt:
        response = self._post(
            connection,
            self._modern_message(1, "tools/list", {}),
            modern=True,
        )[0]
        tool = self._find_recipe_tool(connection, response, modern=True)
        self._check_tool_schema(tool)
        call = self._post(
            connection,
            self._modern_message(
                2,
                "tools/call",
                {
                    "name": RECIPE_TOOL,
                    "arguments": {"recipe": recipe, "request_id": request_id},
                },
            ),
            modern=True,
        )[0]
        result = call.get("result")
        if call.get("id") != 2 or not isinstance(result, dict):
            raise BlenderMCPError("remote Blender MCP tool returned an invalid response")
        if result.get("isError") is True:
            raise BlenderMCPError("remote Blender MCP rejected the scene recipe")
        return self._receipt(result, request_id, recipe)

    def _apply_legacy(
        self, connection: http.client.HTTPConnection, recipe: dict[str, Any], request_id: str
    ) -> BlenderMCPReceipt:
        initialized = self._post(
            connection,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": LEGACY_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
                },
            },
            protocol_version=None,
        )
        session_id = initialized[1].get("mcp-session-id")
        init_result = initialized[0].get("result")
        if not isinstance(init_result, dict):
            raise BlenderMCPError("remote MCP initialization returned no result")
        if init_result.get("protocolVersion") != LEGACY_PROTOCOL_VERSION:
            raise BlenderMCPError("remote Blender MCP protocol version is unsupported")
        try:
            self._post(
                connection,
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                session_id=session_id,
                protocol_version=LEGACY_PROTOCOL_VERSION,
                allow_accepted=True,
            )
            tool = self._find_recipe_tool(connection, modern=False, session_id=session_id)
            self._check_tool_schema(tool)
            call = self._post(
                connection,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": RECIPE_TOOL,
                        "arguments": {"recipe": recipe, "request_id": request_id},
                    },
                },
                session_id=session_id,
                protocol_version=LEGACY_PROTOCOL_VERSION,
            )[0]
            result = call.get("result")
            if call.get("id") != 2 or not isinstance(result, dict):
                raise BlenderMCPError("remote Blender MCP tool returned an invalid response")
            if result.get("isError") is True:
                raise BlenderMCPError("remote Blender MCP rejected the scene recipe")
            return self._receipt(result, request_id, recipe)
        finally:
            if session_id:
                self._delete_session(connection, session_id, LEGACY_PROTOCOL_VERSION)

    @staticmethod
    def _receipt(
        result: dict[str, Any], request_id: str, recipe: dict[str, Any]
    ) -> BlenderMCPReceipt:
        value = result.get("structuredContent")
        try:
            from core.worldbuilding import SceneRecipe

            expected_count = SceneRecipe.from_mapping(recipe).rendered_object_count
            if (
                not isinstance(value, dict)
                or set(value) != {"request_id", "artifact_id", "recipe_name", "object_count"}
                or value["request_id"] != request_id
                or value["recipe_name"] != recipe.get("name")
                or type(value["object_count"]) is not int
                or value["object_count"] != expected_count
            ):
                raise ValueError("receipt fields differ from the requested recipe")
            artifact_id = str(uuid.UUID(value["artifact_id"]))
            if artifact_id != value["artifact_id"].lower():
                raise ValueError("artifact id is not canonical")
            return BlenderMCPReceipt(
                request_id=request_id,
                artifact_id=artifact_id,
                recipe_name=value["recipe_name"],
                object_count=value["object_count"],
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise BlenderMCPError(
                "remote Blender MCP returned an invalid artifact receipt"
            ) from exc

    def download_artifact(self, artifact_id: str) -> bytes:
        """Fetch only an ID-addressed GLB from the configured authenticated server."""
        try:
            canonical = str(uuid.UUID(artifact_id))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("artifact_id must be a UUID") from exc
        if canonical != artifact_id.lower():
            raise ValueError("artifact_id must use canonical UUID syntax")
        connection = self._connection()
        try:
            connection.request(
                "GET",
                f"/artifacts/{canonical}.glb",
                headers={"Authorization": f"Bearer {self._token}", "Accept": "model/gltf-binary"},
            )
            response = connection.getresponse()
            content_type = response.getheader("Content-Type", "").split(";", 1)[0].lower()
            if response.status != 200 or content_type != "model/gltf-binary":
                response.read(1024)
                raise BlenderMCPError("remote Blender MCP artifact is unavailable")
            data = response.read(_MAX_ARTIFACT_BYTES + 1)
            if len(data) > _MAX_ARTIFACT_BYTES:
                raise BlenderMCPError("remote Blender MCP artifact exceeds the size limit")
            self._validate_glb_bytes(data)
            return data
        except BlenderMCPError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise BlenderMCPError("remote Blender MCP artifact download failed") from exc
        finally:
            connection.close()

    @staticmethod
    def _validate_glb_bytes(data: bytes) -> None:
        if len(data) < 20:
            raise BlenderMCPError("remote Blender MCP artifact is not a valid GLB")
        magic, version, total_size = struct.unpack("<4sII", data[:12])
        json_size, chunk_type = struct.unpack("<I4s", data[12:20])
        if (
            magic != b"glTF"
            or version != 2
            or total_size != len(data)
            or chunk_type != b"JSON"
            or json_size > len(data) - 20
        ):
            raise BlenderMCPError("remote Blender MCP artifact is not a valid GLB")
        try:
            document = _parse_json(data[20 : 20 + json_size])
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise BlenderMCPError("remote Blender MCP artifact has an invalid JSON chunk") from exc
        if not isinstance(document, dict) or not isinstance(document.get("meshes"), list):
            raise BlenderMCPError("remote Blender MCP artifact contains no mesh data")

    @staticmethod
    def _modern_message(request_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": MODERN_PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}

    def _connection(self) -> http.client.HTTPConnection:
        host = self._endpoint.hostname
        port = self._endpoint.port
        if self._endpoint.scheme == "https":
            return http.client.HTTPSConnection(
                host, port=port, timeout=self._timeout, context=ssl.create_default_context()
            )
        return http.client.HTTPConnection(host, port=port, timeout=self._timeout)

    def _headers(
        self,
        *,
        session_id: str | None,
        protocol_version: str | None,
        event_stream: bool = False,
        modern_method: str | None = None,
        modern_name: str | None = None,
    ) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        if protocol_version:
            headers["MCP-Protocol-Version"] = protocol_version
        if modern_method:
            headers["Mcp-Method"] = modern_method
        if modern_name:
            headers["Mcp-Name"] = modern_name
        if event_stream:
            headers["Accept"] = "text/event-stream"
        return headers

    def _post(
        self,
        connection: http.client.HTTPConnection,
        message: dict[str, Any],
        *,
        session_id: str | None = None,
        protocol_version: str | None = LEGACY_PROTOCOL_VERSION,
        allow_accepted: bool = False,
        modern: bool = False,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        if modern:
            protocol_version = MODERN_PROTOCOL_VERSION
            params = message.get("params")
            if not isinstance(params, dict) or not isinstance(params.get("_meta"), dict):
                raise BlenderMCPError("modern MCP request is missing protocol metadata")
            modern_name = params.get("name")
        else:
            modern_name = None
        body = json.dumps(message, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        path = self._endpoint.path or "/"
        connection.request(
            "POST",
            path,
            body=body.encode("utf-8"),
            headers=self._headers(
                session_id=session_id,
                protocol_version=protocol_version,
                modern_method=message.get("method") if modern else None,
                modern_name=modern_name if isinstance(modern_name, str) else None,
            ),
        )
        response = connection.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
        if response.status == 202 and allow_accepted and not raw:
            return {}, headers
        if modern and response.status in {400, 404}:
            error = None
            try:
                error = _parse_json(raw)
            except (ValueError, UnicodeError, RecursionError):
                pass
            code = error.get("error", {}).get("code") if isinstance(error, dict) else None
            if code not in {-32020, -32021, -32022}:
                raise _LegacyServerDetected("endpoint uses handshake-era MCP")
        if response.status != 200 or len(raw) > _MAX_RESPONSE_BYTES:
            raise BlenderMCPError("remote Blender MCP returned an invalid HTTP response")
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type == "application/json":
            try:
                parsed = _parse_json(raw)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise BlenderMCPError("remote Blender MCP returned invalid JSON") from exc
            return self._rpc_response(parsed), headers
        if content_type == "text/event-stream":
            messages = []
            for event in raw.decode("utf-8", errors="strict").split("\n\n"):
                data_lines = [
                    line[5:].lstrip() for line in event.splitlines() if line.startswith("data:")
                ]
                if data_lines:
                    try:
                        value = _parse_json("\n".join(data_lines).encode("utf-8"))
                    except (ValueError, UnicodeError, RecursionError) as exc:
                        raise BlenderMCPError(
                            "remote Blender MCP returned invalid event JSON"
                        ) from exc
                    if isinstance(value, dict) and "method" in value:
                        if "id" in value:
                            raise BlenderMCPError(
                                "remote Blender MCP requested an unsupported client action"
                            )
                        continue
                    messages.append(self._rpc_response(value))
            for item in messages:
                if item.get("id") == message.get("id"):
                    return item, headers
            raise BlenderMCPError("remote Blender MCP stream omitted the requested response")
        raise BlenderMCPError("remote Blender MCP used an unsupported response content type")

    @staticmethod
    def _rpc_response(value: object) -> dict[str, Any]:
        if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
            raise BlenderMCPError("remote Blender MCP returned an invalid JSON-RPC message")
        if "method" in value or "error" in value:
            raise BlenderMCPError("remote Blender MCP sent an unsupported or failed request")
        return value

    def _find_recipe_tool(
        self,
        connection: http.client.HTTPConnection,
        first_response: dict[str, Any] | None = None,
        *,
        modern: bool,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        cursor: str | None = None
        for page in range(_MAX_TOOL_PAGES):
            expected_id = 1 + page if modern else 3 + page
            params = {} if cursor is None else {"cursor": cursor}
            if modern:
                if page == 0 and first_response is not None:
                    response = first_response
                else:
                    response = self._post(
                        connection,
                        self._modern_message(expected_id, "tools/list", params),
                        modern=True,
                    )[0]
            else:
                response = self._post(
                    connection,
                    {"jsonrpc": "2.0", "id": expected_id, "method": "tools/list", "params": params},
                    session_id=session_id,
                    protocol_version=LEGACY_PROTOCOL_VERSION,
                )[0]
            result = response.get("result")
            tools = result.get("tools") if isinstance(result, dict) else None
            if response.get("id") != expected_id or not isinstance(tools, list):
                raise BlenderMCPError("remote Blender MCP returned an invalid tool list")
            for tool in tools:
                if isinstance(tool, dict) and tool.get("name") == RECIPE_TOOL:
                    return tool
            cursor = result.get("nextCursor")
            if cursor is None:
                break
            if not isinstance(cursor, str) or not cursor:
                raise BlenderMCPError("remote Blender MCP returned an invalid pagination cursor")
        raise BlenderMCPError(f"remote server must expose the {RECIPE_TOOL} tool")

    @staticmethod
    def _check_tool_schema(tool: dict[str, Any]) -> None:
        schema = tool.get("inputSchema")
        if not isinstance(schema, dict):
            raise BlenderMCPError("remote recipe tool has no input schema")
        properties = schema.get("properties")
        if (
            schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
            or not isinstance(properties, dict)
            or set(properties) != {"recipe", "request_id"}
            or set(schema.get("required", [])) != {"recipe", "request_id"}
            or not isinstance(properties.get("recipe"), dict)
            or properties["recipe"].get("type") != "object"
            or not isinstance(properties.get("request_id"), dict)
            or properties["request_id"].get("type") != "string"
        ):
            raise BlenderMCPError("remote recipe tool does not match the safe RGA tool contract")

    def _delete_session(
        self, connection: http.client.HTTPConnection, session_id: str, protocol_version: str
    ) -> None:
        try:
            connection.request(
                "DELETE",
                self._endpoint.path or "/",
                headers=self._headers(session_id=session_id, protocol_version=protocol_version),
            )
            response = connection.getresponse()
            response.read(1024)
        except (OSError, http.client.HTTPException):
            pass
