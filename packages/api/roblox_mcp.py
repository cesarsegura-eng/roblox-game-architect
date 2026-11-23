"""Fail-closed client for the remote fixed-harness Roblox validation MCP tool."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import re
import ssl
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from core.asset_approval import sign_asset_approval
from core.asset_limits import ROBLOX_MODEL_UPLOAD_MAX_BYTES
from core.gameplay_templates import GAMEPLAY_MODES, gameplay_script, validate_gameplay_mode
from core.navigation import navigation_status, validate_failed_leg
from core.place_approval import sign_place_publish_approval
from core.roblox_place import _validate_imported_model_tree, validate_gameplay_rules_artifact
from core.worldbuilding import SceneRecipe

TOOL_NAME = "rga_validate_map"
_TOKEN = re.compile(r"[A-Za-z0-9._~+/-]+=*\Z", re.ASCII)
_MAX_RESPONSE_BYTES = 11_000_000
BUILD_TOOL_NAME = "rga_build_place"
ASSET_UPLOAD_TOOL_NAME = "rga_upload_reviewed_model"
ASSET_STATUS_TOOL_NAME = "rga_check_model_upload"
PLACE_PUBLISH_TOOL_NAME = "rga_publish_reviewed_place"
MAX_GLB_UPLOAD_BYTES = ROBLOX_MODEL_UPLOAD_MAX_BYTES
MAX_PLACE_PUBLISH_BYTES = 8_000_000


class RobloxMCPError(RuntimeError):
    """The configured remote map-validation tool is unavailable or invalid."""


@dataclass(frozen=True, slots=True)
class RobloxValidationReceipt:
    request_id: str
    place_version: str
    task_id: str
    validation_status: str
    object_count: int
    path_feature_count: int
    navigation_waypoint_count: int
    navigation_connected: bool
    navigation_failed_leg: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class RobloxPlaceArtifact:
    request_id: str
    place_file: bytes
    sha256: str
    object_count: int
    part_count: int
    light_count: int
    approximated_object_count: int
    omitted_character_count: int
    omitted_sun_light_count: int
    gameplay_mode: str = "blockout"
    imported_meshpart_count: int = 0


@dataclass(frozen=True, slots=True)
class RobloxAssetUploadReceipt:
    request_id: str
    approval_id: str
    artifact_sha256: str
    asset_id: str
    operation_id: str
    moderation_state: str
    status: str


@dataclass(frozen=True, slots=True)
class RobloxPublishReceipt:
    request_id: str
    approval_id: str
    artifact_sha256: str
    universe_id: str
    place_id: str
    version_number: int


class RobloxMCPClient:
    """Call only the fixed recipe validator; no arbitrary Luau tool is accepted."""

    def __init__(self, endpoint: str, bearer_token: str, *, timeout: float = 180.0) -> None:
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("ROBLOX_MCP_URL must be a plain HTTP(S) URL without userinfo")
        loopback = parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not loopback:
            raise ValueError("remote Roblox MCP endpoints must use HTTPS")
        if (
            not 32 <= len(bearer_token) <= 512
            or not bearer_token.isascii()
            or not _TOKEN.fullmatch(bearer_token)
        ):
            raise ValueError("ROBLOX_MCP_BEARER_TOKEN must be a 32-512 character token")
        if not 1 <= timeout <= 300:
            raise ValueError("Roblox MCP timeout must be between 1 and 300 seconds")
        self._endpoint = parsed
        self._token = bearer_token
        self._timeout = timeout
        self.map_validation_available = False
        self.place_publish_available = False

    @property
    def audit_host(self) -> str:
        return self._endpoint.hostname or "unknown"

    def validate_recipe(
        self, recipe_payload: dict[str, Any], request_id: str
    ) -> RobloxValidationReceipt:
        try:
            canonical_id = str(uuid.UUID(request_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("request_id must be a UUID") from exc
        if canonical_id != request_id.lower():
            raise ValueError("request_id must use canonical UUID syntax")
        recipe = SceneRecipe.from_mapping(recipe_payload)
        connection = self._connection()
        try:
            self._post(
                connection,
                1,
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "roblox-game-architect", "version": "0.0.0"},
                },
            )
            self._post_notification(connection, "notifications/initialized")
            tools = self._post(connection, 2, "tools/list", {}).get("result", {}).get("tools")
            tool = (
                next(
                    (
                        entry
                        for entry in tools
                        if isinstance(entry, dict) and entry.get("name") == TOOL_NAME
                    ),
                    None,
                )
                if isinstance(tools, list)
                else None
            )
            self._check_tool(tool)
            call = self._post(
                connection,
                3,
                "tools/call",
                {
                    "name": TOOL_NAME,
                    "arguments": {"recipe": recipe.to_mapping(), "request_id": canonical_id},
                },
            )
            result = call.get("result")
            if not isinstance(result, dict) or result.get("isError") is True:
                raise RobloxMCPError("remote Roblox validation task failed or is uncertain")
            value = result.get("structuredContent")
            return self._receipt(value, recipe, canonical_id)
        except RobloxMCPError:
            raise
        except (
            OSError,
            http.client.HTTPException,
            ValueError,
            TypeError,
            AttributeError,
            ET.ParseError,
        ) as exc:
            raise RobloxMCPError("remote Roblox validation MCP request failed") from exc
        finally:
            connection.close()

    def check_connection(self, *, timeout: float = 5.0) -> None:
        """Check the fixed build tool and each advertised cloud contract."""
        if not 1 <= timeout <= 15:
            raise ValueError("health-check timeout must be between 1 and 15 seconds")
        connection = self._connection()
        connection.timeout = timeout
        try:
            initialized = self._post(
                connection,
                1,
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "roblox-game-architect", "version": "0.0.0"},
                },
            )
            result = initialized.get("result")
            if not isinstance(result, dict) or result.get("protocolVersion") != "2025-11-25":
                raise RobloxMCPError("remote Roblox MCP initialization is incompatible")
            self._post_notification(connection, "notifications/initialized")
            response = self._post(connection, 2, "tools/list", {})
            tools = response.get("result", {}).get("tools")
            tool = (
                next(
                    (
                        entry
                        for entry in tools
                        if isinstance(entry, dict) and entry.get("name") == TOOL_NAME
                    ),
                    None,
                )
                if isinstance(tools, list)
                else None
            )
            if tool is not None:
                self._check_tool(tool)
            build_tool = (
                next(
                    (
                        entry
                        for entry in tools
                        if isinstance(entry, dict) and entry.get("name") == BUILD_TOOL_NAME
                    ),
                    None,
                )
                if isinstance(tools, list)
                else None
            )
            self._check_build_tool(build_tool)
            publish_tool = next(
                (
                    entry
                    for entry in tools or []
                    if isinstance(entry, dict) and entry.get("name") == PLACE_PUBLISH_TOOL_NAME
                ),
                None,
            )
            if publish_tool is not None:
                self._check_place_publish_tool(publish_tool)
            self.map_validation_available = tool is not None
            self.place_publish_available = publish_tool is not None
        except RobloxMCPError:
            raise
        except (OSError, http.client.HTTPException, ValueError, TypeError, AttributeError) as exc:
            raise RobloxMCPError("remote Roblox MCP health check failed") from exc
        finally:
            connection.close()

    def build_place(
        self,
        recipe_payload: dict[str, Any],
        request_id: str,
        *,
        gameplay_mode: str = "blockout",
        gameplay_rules: list[dict[str, Any]] | None = None,
        model_asset_id: str | None = None,
    ) -> RobloxPlaceArtifact:
        """Build a fixed-mode place artifact; never publish it."""
        try:
            canonical_id = str(uuid.UUID(request_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("request_id must be a UUID") from exc
        if canonical_id != request_id.lower():
            raise ValueError("request_id must use canonical UUID syntax")
        if not isinstance(gameplay_mode, str) or gameplay_mode not in GAMEPLAY_MODES:
            raise ValueError("gameplay_mode is unsupported")
        if model_asset_id is not None and (
            not isinstance(model_asset_id, str)
            or not re.fullmatch(r"[1-9][0-9]{0,19}", model_asset_id, re.ASCII)
        ):
            raise ValueError("model_asset_id must be a positive decimal Roblox asset ID")
        if model_asset_id is not None and gameplay_mode != "blockout":
            raise ValueError("imported Blender models require the script-free blockout mode")
        recipe = SceneRecipe.from_mapping(recipe_payload)
        validate_gameplay_mode(gameplay_mode, recipe, gameplay_rules)
        connection = self._connection()
        try:
            self._post(
                connection,
                1,
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "roblox-game-architect", "version": "0.0.0"},
                },
            )
            self._post_notification(connection, "notifications/initialized")
            listing = self._post(connection, 2, "tools/list", {}).get("result", {}).get("tools")
            tool = (
                next(
                    (
                        entry
                        for entry in listing
                        if isinstance(entry, dict) and entry.get("name") == BUILD_TOOL_NAME
                    ),
                    None,
                )
                if isinstance(listing, list)
                else None
            )
            self._check_build_tool(tool)
            arguments = {
                "recipe": recipe.to_mapping(),
                "request_id": canonical_id,
                "gameplay_mode": gameplay_mode,
            }
            if gameplay_rules is not None:
                arguments["gameplay_rules"] = gameplay_rules
            if model_asset_id is not None:
                arguments["model_asset_id"] = model_asset_id
            call = self._post(
                connection,
                3,
                "tools/call",
                {
                    "name": BUILD_TOOL_NAME,
                    "arguments": arguments,
                },
            )
            result = call.get("result")
            value = (
                result.get("structuredContent")
                if isinstance(result, dict) and result.get("isError") is not True
                else None
            )
            required = {
                "request_id",
                "sha256",
                "place_file_base64",
                "object_count",
                "part_count",
                "light_count",
                "approximated_object_count",
                "omitted_character_count",
                "omitted_sun_light_count",
                "gameplay_mode",
                "imported_meshpart_count",
            }
            if (
                not isinstance(value, dict)
                or set(value) != required
                or value.get("request_id") != canonical_id
            ):
                raise RobloxMCPError("remote place build returned an invalid receipt")
            encoded = value["place_file_base64"]
            if not isinstance(encoded, str) or len(encoded) > 10_700_000:
                raise RobloxMCPError("remote place artifact exceeded its size limit")
            place_file = base64.b64decode(encoded, validate=True)
            if (
                len(place_file) > 8_000_000
                or b"<!DOCTYPE" in place_file.upper()
                or b"<!ENTITY" in place_file.upper()
            ):
                raise RobloxMCPError("remote place artifact exceeded its safety limits")
            digest = hashlib.sha256(place_file).hexdigest()
            if not place_file.startswith(b"<roblox") or digest != value["sha256"]:
                raise RobloxMCPError("remote place artifact failed integrity validation")
            document = ET.fromstring(place_file)  # noqa: S314 - DTD and entities are rejected above.
            if value["gameplay_mode"] != gameplay_mode:
                raise RobloxMCPError("remote place build returned a different gameplay mode")
            _validate_place_scripts(document, gameplay_mode)
            try:
                validate_gameplay_rules_artifact(document, gameplay_mode, gameplay_rules, recipe)
            except ValueError as exc:
                raise RobloxMCPError(
                    "remote place artifact gameplay rules failed validation"
                ) from exc
            imported_count = value["imported_meshpart_count"]
            if (
                type(imported_count) is not int
                or not 0 <= imported_count <= 128
                or (model_asset_id is None and imported_count != 0)
                or (model_asset_id is not None and imported_count < 1)
            ):
                raise RobloxMCPError("remote place build returned invalid imported model count")
            _validate_imported_model_tree(document, imported_count)
            counts = [
                value[key]
                for key in (
                    "object_count",
                    "part_count",
                    "light_count",
                    "approximated_object_count",
                    "omitted_character_count",
                    "omitted_sun_light_count",
                )
            ]
            if any(type(count) is not int or count < 0 for count in counts):
                raise RobloxMCPError("remote place build returned invalid counts")
            expected_proxy_count = 0 if model_asset_id is not None else len(recipe.objects)
            if counts[0] != len(recipe.objects) or counts[1] != expected_proxy_count:
                raise RobloxMCPError("remote place build counts do not match the scene recipe")
            return RobloxPlaceArtifact(
                canonical_id, place_file, digest, *counts, gameplay_mode, imported_count
            )
        except RobloxMCPError:
            raise
        except (
            OSError,
            http.client.HTTPException,
            ValueError,
            TypeError,
            AttributeError,
            ET.ParseError,
        ) as exc:
            raise RobloxMCPError("remote Roblox place build request failed") from exc
        finally:
            connection.close()

    def upload_reviewed_model(
        self,
        glb: bytes,
        *,
        request_id: str,
        approval_id: str,
        display_name: str,
        description: str,
        approval_secret: str,
    ) -> RobloxAssetUploadReceipt:
        """Send GLB to the fixed asset tool with an exact, short-lived approval."""
        if not isinstance(glb, bytes) or not 20 <= len(glb) <= MAX_GLB_UPLOAD_BYTES:
            raise ValueError("GLB exceeds the remote Roblox Model upload limit")
        try:
            canonical_request = str(uuid.UUID(request_id))
            canonical_approval = str(uuid.UUID(approval_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("request_id and approval_id must be UUIDs") from exc
        if request_id != canonical_request.lower() or approval_id != canonical_approval.lower():
            raise ValueError("request and approval IDs must use canonical UUID syntax")
        digest = hashlib.sha256(glb).hexdigest()
        expires_at = int(time.time()) + 300
        signature = sign_asset_approval(
            approval_secret,
            request_id=canonical_request,
            approval_id=canonical_approval,
            artifact_sha256=digest,
            display_name=display_name,
            description=description,
            expires_at=expires_at,
        )
        receipt = self._call_model_tool(
            ASSET_UPLOAD_TOOL_NAME,
            {
                "request_id": canonical_request,
                "approval_id": canonical_approval,
                "artifact_sha256": digest,
                "approval_signature": signature,
                "approval_expires_at": expires_at,
                "display_name": display_name,
                "description": description,
                "glb_base64": base64.b64encode(glb).decode("ascii"),
            },
        )
        if receipt.approval_id != canonical_approval or receipt.artifact_sha256 != digest:
            raise RobloxMCPError("remote Roblox Model upload receipt failed verification")
        return receipt

    def check_model_upload(self, request_id: str) -> RobloxAssetUploadReceipt:
        """Read moderation for the original request from the configured asset server."""
        return self._call_model_tool(
            ASSET_STATUS_TOOL_NAME, {"request_id": _canonical_uuid(request_id)}
        )

    def _call_model_tool(self, name: str, arguments: dict[str, Any]) -> RobloxAssetUploadReceipt:
        connection = self._connection()
        try:
            init = self._post(
                connection,
                1,
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "roblox-game-architect", "version": "0.0.0"},
                },
            )
            if init.get("result", {}).get("protocolVersion") != "2025-11-25":
                raise RobloxMCPError("remote Roblox MCP initialization is incompatible")
            self._post_notification(connection, "notifications/initialized")
            tools = self._post(connection, 2, "tools/list", {}).get("result", {}).get("tools")
            tool = next(
                (
                    item
                    for item in tools or []
                    if isinstance(item, dict) and item.get("name") == name
                ),
                None,
            )
            if name == ASSET_UPLOAD_TOOL_NAME:
                self._check_asset_upload_tool(tool)
            else:
                schema = (tool or {}).get("inputSchema", {})
                props = schema.get("properties", {})
                if (
                    schema.get("type") != "object"
                    or schema.get("additionalProperties") is not False
                    or schema.get("required") != ["request_id"]
                    or set(props) != {"request_id"}
                    or props["request_id"].get("type") != "string"
                ):
                    raise RobloxMCPError(
                        "remote Model status tool does not match the fixed RGA contract"
                    )
            result = self._post(
                connection, 3, "tools/call", {"name": name, "arguments": arguments}
            ).get("result")
            if not isinstance(result, dict) or result.get("isError") is True:
                raise RobloxMCPError("remote Roblox Model request failed or is uncertain")
            receipt = result.get("structuredContent")
            if not isinstance(receipt, dict) or set(receipt) != set(
                RobloxAssetUploadReceipt.__dataclass_fields__
            ):
                raise RobloxMCPError("remote Roblox Model returned an invalid receipt")
            if not all(isinstance(value, str) for value in receipt.values()):
                raise RobloxMCPError("remote Roblox Model receipt contains invalid values")
            state = receipt["moderation_state"]
            if state == "MODERATION_STATE_APPROVED":
                status = "approved"
            elif "REJECT" in state or "FAIL" in state:
                status = "rejected"
            else:
                status = "moderation_pending"
            if (
                receipt["request_id"] != arguments["request_id"]
                or not _is_canonical_uuid(receipt["approval_id"])
                or not re.fullmatch(r"[0-9a-f]{64}", receipt["artifact_sha256"])
                or not re.fullmatch(r"[1-9][0-9]{0,19}", receipt["asset_id"])
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", receipt["operation_id"])
                or not re.fullmatch(r"MODERATION_STATE_[A-Z_]{1,80}", state)
                or receipt["status"] != status
            ):
                raise RobloxMCPError("remote Roblox Model receipt failed verification")
            return RobloxAssetUploadReceipt(**receipt)
        except RobloxMCPError:
            raise
        except (OSError, http.client.HTTPException, ValueError, TypeError, AttributeError) as exc:
            raise RobloxMCPError("remote Roblox Model request failed or is uncertain") from exc
        finally:
            connection.close()

    def publish_reviewed_place(
        self,
        place_file: bytes,
        *,
        request_id: str,
        approval_id: str,
        approval_secret: str,
        universe_id: str,
        place_id: str,
    ) -> RobloxPublishReceipt:
        """Publish only the exact artifact under a digest- and target-bound approval."""
        if (
            not isinstance(place_file, bytes)
            or not 32 <= len(place_file) <= MAX_PLACE_PUBLISH_BYTES
        ):
            raise ValueError("place file is empty or exceeds the remote publish limit")
        upper = place_file.upper()
        if not place_file.startswith(b"<roblox") or b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
            raise ValueError("place file is not safe Roblox XML")
        document = ET.fromstring(place_file)  # noqa: S314 - DTD and entities are rejected above.
        if document.tag != "roblox":
            raise ValueError("place file has an invalid Roblox XML root")
        canonical_request = _canonical_uuid(request_id)
        canonical_approval = _canonical_uuid(approval_id)
        digest = hashlib.sha256(place_file).hexdigest()
        expires_at = int(time.time()) + 300
        signature = sign_place_publish_approval(
            approval_secret,
            request_id=canonical_request,
            approval_id=canonical_approval,
            artifact_sha256=digest,
            universe_id=universe_id,
            place_id=place_id,
            expires_at=expires_at,
        )
        connection = self._connection()
        try:
            self._post(
                connection,
                1,
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "roblox-game-architect", "version": "0.0.0"},
                },
            )
            self._post_notification(connection, "notifications/initialized")
            tools = self._post(connection, 2, "tools/list", {}).get("result", {}).get("tools")
            tool = next(
                (
                    entry
                    for entry in tools or []
                    if isinstance(entry, dict) and entry.get("name") == PLACE_PUBLISH_TOOL_NAME
                ),
                None,
            )
            self._check_place_publish_tool(tool)
            call = self._post(
                connection,
                3,
                "tools/call",
                {
                    "name": PLACE_PUBLISH_TOOL_NAME,
                    "arguments": {
                        "request_id": canonical_request,
                        "approval_id": canonical_approval,
                        "artifact_sha256": digest,
                        "approval_signature": signature,
                        "approval_expires_at": expires_at,
                        "place_file_base64": base64.b64encode(place_file).decode("ascii"),
                    },
                },
            )
            result = call.get("result")
            value = (
                result.get("structuredContent")
                if isinstance(result, dict) and result.get("isError") is not True
                else None
            )
            required = {
                "request_id",
                "approval_id",
                "artifact_sha256",
                "universe_id",
                "place_id",
                "version_number",
            }
            if not isinstance(value, dict) or set(value) != required:
                raise RobloxMCPError("remote place publish returned an invalid receipt")
            if (
                value["request_id"] != canonical_request
                or value["approval_id"] != canonical_approval
                or value["artifact_sha256"] != digest
                or value["universe_id"] != universe_id
                or value["place_id"] != place_id
                or type(value["version_number"]) is not int
                or value["version_number"] < 1
            ):
                raise RobloxMCPError("remote place publish receipt failed verification")
            return RobloxPublishReceipt(**value)
        except RobloxMCPError:
            raise
        except (
            OSError,
            http.client.HTTPException,
            ValueError,
            TypeError,
            AttributeError,
            ET.ParseError,
        ) as exc:
            raise RobloxMCPError("remote Roblox place publish failed or is uncertain") from exc
        finally:
            connection.close()

    @staticmethod
    def _check_tool(tool: object) -> None:
        if not isinstance(tool, dict):
            raise RobloxMCPError(f"remote server must expose {TOOL_NAME}")
        schema = tool.get("inputSchema")
        props = schema.get("properties") if isinstance(schema, dict) else None
        if (
            not isinstance(props, dict)
            or schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
            or set(props) != {"recipe", "request_id"}
            or set(schema.get("required", [])) != {"recipe", "request_id"}
            or not isinstance(props.get("recipe"), dict)
            or props["recipe"].get("type") != "object"
            or not isinstance(props.get("request_id"), dict)
            or props["request_id"].get("type") != "string"
        ):
            raise RobloxMCPError("remote validation tool does not match the fixed RGA contract")

    @staticmethod
    def _check_build_tool(tool: object) -> None:
        if not isinstance(tool, dict):
            raise RobloxMCPError(f"remote server must expose {BUILD_TOOL_NAME}")
        schema = tool.get("inputSchema")
        props = schema.get("properties") if isinstance(schema, dict) else None
        if (
            not isinstance(props, dict)
            or schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
            or set(props)
            != {"recipe", "plan", "request_id", "gameplay_mode", "gameplay_rules", "model_asset_id"}
            or set(schema.get("required", [])) != {"recipe", "request_id"}
            or not isinstance(props.get("recipe"), dict)
            or props["recipe"].get("type") != "object"
            or not isinstance(props.get("plan"), dict)
            or props["plan"].get("type") != "object"
            or not isinstance(props.get("request_id"), dict)
            or props["request_id"].get("type") != "string"
            or not isinstance(props.get("gameplay_mode"), dict)
            or props["gameplay_mode"].get("enum") != sorted(GAMEPLAY_MODES)
            or not isinstance(props.get("gameplay_rules"), dict)
            or props["gameplay_rules"].get("type") != "array"
            or props["gameplay_rules"].get("maxItems") != 16
            or props["model_asset_id"].get("pattern") != "^[1-9][0-9]{0,19}$"
        ):
            raise RobloxMCPError("remote place-build tool does not match the fixed RGA contract")

    @staticmethod
    def _check_asset_upload_tool(tool: object) -> None:
        fields = {
            "request_id",
            "approval_id",
            "artifact_sha256",
            "approval_signature",
            "approval_expires_at",
            "display_name",
            "description",
            "glb_base64",
        }
        if not isinstance(tool, dict):
            raise RobloxMCPError(f"remote server must expose {ASSET_UPLOAD_TOOL_NAME}")
        schema = tool.get("inputSchema")
        props = schema.get("properties") if isinstance(schema, dict) else None
        if (
            not isinstance(props, dict)
            or schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
            or set(props) != fields
            or set(schema.get("required", [])) != fields
        ):
            raise RobloxMCPError("remote Model upload tool does not match the fixed RGA contract")

    @staticmethod
    def _check_place_publish_tool(tool: object) -> None:
        fields = {
            "request_id",
            "approval_id",
            "artifact_sha256",
            "approval_signature",
            "approval_expires_at",
            "place_file_base64",
        }
        if not isinstance(tool, dict):
            raise RobloxMCPError(f"remote server must expose {PLACE_PUBLISH_TOOL_NAME}")
        schema = tool.get("inputSchema")
        props = schema.get("properties") if isinstance(schema, dict) else None
        if (
            not isinstance(props, dict)
            or schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
            or set(props) != fields
            or set(schema.get("required", [])) != fields
            or props["place_file_base64"].get("maxLength") != 10_666_668
        ):
            raise RobloxMCPError("remote place publish tool does not match the fixed RGA contract")

    @staticmethod
    def _receipt(value: object, recipe: SceneRecipe, request_id: str) -> RobloxValidationReceipt:
        keys = {
            "request_id",
            "place_version",
            "task_id",
            "validation_status",
            "object_count",
            "path_feature_count",
            "navigation_waypoint_count",
            "navigation_connected",
            "navigation_failed_leg",
        }
        if not isinstance(value, dict) or set(value) != keys:
            raise RobloxMCPError("remote Roblox validation returned an invalid receipt")
        if (
            value["request_id"] != request_id
            or not isinstance(value["place_version"], str)
            or not re.fullmatch(r"[1-9][0-9]{0,19}", value["place_version"])
            or not isinstance(value["task_id"], str)
            or not _is_canonical_uuid(value["task_id"])
            or value["validation_status"]
            not in {"structure_only", "navigation_pass", "navigation_failed"}
            or type(value["object_count"]) is not int
            or value["object_count"] != len(recipe.objects)
            or type(value["path_feature_count"]) is not int
            or not 0 <= value["path_feature_count"] <= len(recipe.objects)
            or type(value["navigation_waypoint_count"]) is not int
            or not 0 <= value["navigation_waypoint_count"] <= 512
            or type(value["navigation_connected"]) is not bool
        ):
            raise RobloxMCPError("remote Roblox validation returned an invalid receipt")
        try:
            expected_status = navigation_status(
                recipe,
                value["path_feature_count"],
                value["navigation_waypoint_count"],
                value["navigation_connected"],
            )
        except ValueError as exc:
            raise RobloxMCPError(
                "remote Roblox returned contradictory navigation evidence"
            ) from exc
        if value["validation_status"] != expected_status:
            raise RobloxMCPError("remote Roblox validation status contradicts its evidence")
        try:
            validate_failed_leg(
                recipe,
                expected_status,
                value["navigation_failed_leg"],
                value["navigation_waypoint_count"],
            )
        except ValueError as exc:
            raise RobloxMCPError("remote Roblox returned an invalid route diagnostic") from exc
        return RobloxValidationReceipt(**value)

    def _post(
        self: RobloxMCPClient,
        connection: http.client.HTTPConnection,
        call_id: int,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        message = {"jsonrpc": "2.0", "id": call_id, "method": method, "params": params}
        connection.request(
            "POST", self._endpoint.path or "/", json.dumps(message).encode(), self._headers()
        )
        response = connection.getresponse()
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
        if response.status != 200 or len(raw) > _MAX_RESPONSE_BYTES:
            raise RobloxMCPError("remote Roblox MCP returned an invalid HTTP response")
        value = json.loads(raw)
        if (
            not isinstance(value, dict)
            or value.get("id") != call_id
            or value.get("jsonrpc") != "2.0"
        ):
            raise RobloxMCPError("remote Roblox MCP returned an invalid JSON-RPC response")
        if "error" in value:
            raise RobloxMCPError("remote Roblox MCP rejected the fixed validation request")
        return value

    def _post_notification(
        self: RobloxMCPClient, connection: http.client.HTTPConnection, method: str
    ) -> None:
        message = {"jsonrpc": "2.0", "method": method}
        connection.request(
            "POST", self._endpoint.path or "/", json.dumps(message).encode(), self._headers()
        )
        response = connection.getresponse()
        body = response.read(1024)
        if response.status != 202 or body:
            raise RobloxMCPError("remote Roblox MCP rejected session initialization")

    def _headers(self: RobloxMCPClient) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25",
        }

    def _connection(self: RobloxMCPClient) -> http.client.HTTPConnection:
        if self._endpoint.scheme == "https":
            return http.client.HTTPSConnection(
                self._endpoint.hostname,
                port=self._endpoint.port,
                timeout=self._timeout,
                context=ssl.create_default_context(),
            )
        return http.client.HTTPConnection(
            self._endpoint.hostname, port=self._endpoint.port, timeout=self._timeout
        )


def _validate_place_scripts(document: ET.Element, gameplay_mode: str) -> None:
    """Allow only the exact repository-owned script for an explicitly selected mode."""
    items = [node for node in document.iter("Item")]
    executable = [
        node
        for node in items
        if node.get("class") in {"Script", "LocalScript", "ModuleScript", "Actor"}
    ]
    if gameplay_mode == "blockout":
        if executable:
            raise RobloxMCPError("remote blockout contains executable classes")
        return
    template = gameplay_script(gameplay_mode)
    if template is None:
        raise RobloxMCPError("remote place has an unsupported gameplay mode")
    scripts = [node for node in items if node.get("class") == "Script"]
    if len(scripts) != 1 or len(executable) != 1:
        raise RobloxMCPError("remote gameplay place contains unexpected executable classes")
    parents = {child: parent for parent in document.iter() for child in parent}
    script = scripts[0]
    parent = parents.get(script)
    if parent is None or parent.get("class") != "ServerScriptService":
        raise RobloxMCPError("fixed gameplay Script is outside ServerScriptService")
    properties = script.find("Properties")
    if properties is None:
        raise RobloxMCPError("fixed gameplay Script has no serialized properties")
    name = next(
        (value.text for value in properties if value.get("name") == "Name"),
        None,
    )
    disabled = next(
        (value.text for value in properties if value.get("name") == "Disabled"),
        "false",
    )
    source = next(
        (
            value.text or ""
            for value in properties
            if value.tag in {"ProtectedString", "string"} and value.get("name") == "Source"
        ),
        None,
    )
    expected_name, expected_source = template
    if name != expected_name or disabled != "false" or source != expected_source:
        raise RobloxMCPError("remote gameplay Script does not match the fixed reviewed template")


def _is_canonical_uuid(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False


def _canonical_uuid(value: str) -> str:
    try:
        canonical = str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("request and approval IDs must be UUIDs") from exc
    if canonical != value.lower():
        raise ValueError("request and approval IDs must be canonical UUIDs")
    return canonical
