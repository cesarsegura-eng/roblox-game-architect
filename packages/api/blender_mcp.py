"""Fail-closed client for the project's remote Blender MCP tool contract.

This client never calls Blender's generic Python execution tools. The configured
server must expose ``rga_apply_scene_recipe`` with the exact input shape below.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import re
import ssl
import struct
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult, parse_qsl, urlsplit

MODERN_PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
CLIENT_NAME = "roblox-game-architect"
CLIENT_VERSION = "0.0.0"
RECIPE_TOOL = "rga_apply_scene_recipe"
_MAX_RESPONSE_BYTES = 1_600_000
_MAX_TOOL_PAGES = 8
_BEARER = re.compile(r"[A-Za-z0-9._~+/-]+=*\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_MAX_PREVIEW_BYTES = 1 * 1024 * 1024
_PREVIEW_SIZE = 512
_ARTIFACT_DOWNLOAD_TTL_SECONDS = 15 * 60


@dataclass(frozen=True, slots=True)
class BlenderMCPReceipt:
    """Verified metadata for a remotely rendered, downloadable GLB artifact."""

    request_id: str
    artifact_id: str
    recipe_name: str
    object_count: int
    artifact_sha256: str
    artifact_download_url: str | None = None
    preview_png: bytes | None = None


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


def _same_http_authority(left: SplitResult, right: SplitResult) -> bool:
    """Compare URL hosts and effective ports, treating an explicit default port normally."""
    try:
        left_port = left.port
        right_port = right.port
    except ValueError:
        return False
    if left_port is None:
        left_port = 443 if left.scheme == "https" else 80
    if right_port is None:
        right_port = 443 if right.scheme == "https" else 80
    return bool(
        left.hostname
        and right.hostname
        and left.hostname.lower() == right.hostname.lower()
        and left_port == right_port
    )


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

    def apply_recipe(
        self,
        recipe: Mapping[str, Any],
        request_id: str,
        *,
        include_preview: bool = False,
        preview_mode: str = "isometric",
    ) -> BlenderMCPReceipt:
        """Send a recipe to the fixed Blender tool and verify its artifact receipt."""
        if not isinstance(include_preview, bool):
            raise ValueError("include_preview must be a boolean")
        if not isinstance(preview_mode, str) or preview_mode not in {"isometric", "cutaway"}:
            raise ValueError("preview_mode must be isometric or cutaway")
        if preview_mode != "isometric" and not include_preview:
            raise ValueError("preview_mode requires include_preview")
        try:
            uuid.UUID(request_id)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("request_id must be a UUID") from exc
        connection = self._connection()
        try:
            try:
                receipt = self._apply_modern(
                    connection,
                    dict(recipe),
                    request_id,
                    include_preview=include_preview,
                    preview_mode=preview_mode,
                )
            except _LegacyServerDetected:
                receipt = self._apply_legacy(
                    connection,
                    dict(recipe),
                    request_id,
                    include_preview=include_preview,
                    preview_mode=preview_mode,
                )
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
        self,
        connection: http.client.HTTPConnection,
        recipe: dict[str, Any],
        request_id: str,
        *,
        include_preview: bool,
        preview_mode: str,
    ) -> BlenderMCPReceipt:
        response = self._post(
            connection,
            self._modern_message(1, "tools/list", {}),
            modern=True,
        )[0]
        tool = self._find_recipe_tool(connection, response, modern=True)
        self._check_tool_schema(tool, include_preview=include_preview, preview_mode=preview_mode)
        arguments = {"recipe": recipe, "request_id": request_id}
        if include_preview:
            arguments["include_preview"] = True
            if preview_mode != "isometric":
                arguments["preview_mode"] = preview_mode
        call = self._post(
            connection,
            self._modern_message(
                2,
                "tools/call",
                {
                    "name": RECIPE_TOOL,
                    "arguments": arguments,
                },
            ),
            modern=True,
        )[0]
        result = call.get("result")
        if call.get("id") != 2 or not isinstance(result, dict):
            raise BlenderMCPError("remote Blender MCP tool returned an invalid response")
        if result.get("isError") is True:
            raise BlenderMCPError("remote Blender MCP rejected the scene recipe")
        return self._receipt(result, request_id, recipe, include_preview=include_preview)

    def _apply_legacy(
        self,
        connection: http.client.HTTPConnection,
        recipe: dict[str, Any],
        request_id: str,
        *,
        include_preview: bool,
        preview_mode: str,
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
            self._check_tool_schema(
                tool, include_preview=include_preview, preview_mode=preview_mode
            )
            arguments = {"recipe": recipe, "request_id": request_id}
            if include_preview:
                arguments["include_preview"] = True
                if preview_mode != "isometric":
                    arguments["preview_mode"] = preview_mode
            call = self._post(
                connection,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": RECIPE_TOOL,
                        "arguments": arguments,
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
            return self._receipt(result, request_id, recipe, include_preview=include_preview)
        finally:
            if session_id:
                self._delete_session(connection, session_id, LEGACY_PROTOCOL_VERSION)

    def _receipt(
        self,
        result: dict[str, Any],
        request_id: str,
        recipe: dict[str, Any],
        *,
        include_preview: bool,
    ) -> BlenderMCPReceipt:
        value = result.get("structuredContent")
        try:
            from core.worldbuilding import SceneRecipe

            expected_count = SceneRecipe.from_mapping(recipe).rendered_object_count
            required = {
                "request_id",
                "artifact_id",
                "recipe_name",
                "object_count",
                "artifact_sha256",
            }
            if (
                not isinstance(value, dict)
                or not required.issubset(value)
                or set(value) - required - {"artifact_download_url"}
                or value["request_id"] != request_id
                or value["recipe_name"] != recipe.get("name")
                or type(value["object_count"]) is not int
                or value["object_count"] != expected_count
                or not isinstance(value["artifact_sha256"], str)
                or not _SHA256.fullmatch(value["artifact_sha256"])
            ):
                raise ValueError("receipt fields differ from the requested recipe")
            artifact_id = str(uuid.UUID(value["artifact_id"]))
            if artifact_id != value["artifact_id"].lower():
                raise ValueError("artifact id is not canonical")
            artifact_download_url = value.get("artifact_download_url")
            if artifact_download_url is not None:
                parsed_download = urlsplit(artifact_download_url)
                if (
                    not isinstance(artifact_download_url, str)
                    or parsed_download.scheme != "https"
                    or not _same_http_authority(parsed_download, self._endpoint)
                    or parsed_download.path != f"/artifacts/{artifact_id}.glb"
                    or parsed_download.username is not None
                    or parsed_download.password is not None
                    or parsed_download.fragment
                ):
                    raise ValueError("artifact download URL is not bound to this Blender host")
                query_pairs = parse_qsl(
                    parsed_download.query, keep_blank_values=True, strict_parsing=True
                )
                query = dict(query_pairs)
                if (
                    len(query_pairs) != 2
                    or set(query) != {"expires", "signature"}
                    or not query["expires"].isdecimal()
                    or not re.fullmatch(r"[0-9a-f]{64}", query["signature"])
                ):
                    raise ValueError("artifact download URL has invalid capability fields")
                expires = int(query["expires"])
                now = int(time.time())
                if expires <= now or expires > now + _ARTIFACT_DOWNLOAD_TTL_SECONDS:
                    raise ValueError("artifact download URL is expired or has excessive lifetime")
            preview_png = (
                self._preview_from_content(result.get("content")) if include_preview else None
            )
            return BlenderMCPReceipt(
                request_id=request_id,
                artifact_id=artifact_id,
                recipe_name=value["recipe_name"],
                object_count=value["object_count"],
                artifact_sha256=value["artifact_sha256"],
                artifact_download_url=artifact_download_url,
                preview_png=preview_png,
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise BlenderMCPError(
                "remote Blender MCP returned an invalid artifact receipt"
            ) from exc

    def download_artifact(self, artifact_id: str, *, expected_sha256: str | None = None) -> bytes:
        """Fetch an ID-addressed GLB and, when supplied, bind it to its receipt digest."""
        try:
            canonical = str(uuid.UUID(artifact_id))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("artifact_id must be a UUID") from exc
        if canonical != artifact_id.lower():
            raise ValueError("artifact_id must use canonical UUID syntax")
        if expected_sha256 is not None and (
            not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256)
        ):
            raise ValueError("expected_sha256 must be 64 lowercase hexadecimal characters")
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
            if expected_sha256 is not None and not hmac.compare_digest(
                hashlib.sha256(data).hexdigest(), expected_sha256
            ):
                raise BlenderMCPError(
                    "remote Blender MCP artifact does not match its receipt SHA-256"
                )
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
    def _check_tool_schema(
        tool: dict[str, Any], *, include_preview: bool = False, preview_mode: str = "isometric"
    ) -> None:
        schema = tool.get("inputSchema")
        if not isinstance(schema, dict):
            raise BlenderMCPError("remote recipe tool has no input schema")
        properties = schema.get("properties")
        if (
            schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
            or not isinstance(properties, dict)
            or set(properties) - {"recipe", "request_id", "include_preview", "preview_mode"}
            or not {"recipe", "request_id"} <= set(properties)
            or set(schema.get("required", [])) != {"recipe", "request_id"}
            or not isinstance(properties.get("recipe"), dict)
            or properties["recipe"].get("type") != "object"
            or not isinstance(properties.get("request_id"), dict)
            or properties["request_id"].get("type") != "string"
            or (
                "include_preview" in properties
                and (
                    not isinstance(properties["include_preview"], dict)
                    or properties["include_preview"].get("type") != "boolean"
                )
            )
            or (include_preview and "include_preview" not in properties)
            or (
                "preview_mode" in properties
                and (
                    not isinstance(properties["preview_mode"], dict)
                    or properties["preview_mode"].get("type") != "string"
                    or properties["preview_mode"].get("enum") != ["isometric", "cutaway"]
                )
            )
            or (preview_mode == "cutaway" and "preview_mode" not in properties)
        ):
            raise BlenderMCPError("remote recipe tool does not match the safe RGA tool contract")

    @staticmethod
    def _preview_from_content(content: object) -> bytes:
        if not isinstance(content, list):
            raise BlenderMCPError("remote Blender MCP did not return the requested preview")
        image = next(
            (
                item
                for item in content
                if isinstance(item, dict)
                and item.get("type") == "image"
                and item.get("mimeType") == "image/png"
            ),
            None,
        )
        if not isinstance(image, dict) or not isinstance(image.get("data"), str):
            raise BlenderMCPError("remote Blender MCP did not return the requested preview")
        try:
            data = base64.b64decode(image["data"], validate=True)
        except (ValueError, TypeError) as exc:
            raise BlenderMCPError("remote Blender MCP returned an invalid preview image") from exc
        if (
            not 45 <= len(data) <= _MAX_PREVIEW_BYTES
            or data[:8] != b"\x89PNG\r\n\x1a\n"
            or data[12:16] != b"IHDR"
            or b"IDAT" not in data
            or data[-12:] != b"\x00\x00\x00\x00IEND\xaeB`\x82"
            or struct.unpack(">II", data[16:24]) != (_PREVIEW_SIZE, _PREVIEW_SIZE)
        ):
            raise BlenderMCPError("remote Blender MCP returned an invalid preview image")
        return data

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
