"""Remote MCP service for bounded Roblox place builds and fixed validation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.server
import json
import os
import re
import socket
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

from core.game_planning import GamePlanningError
from core.gameplay_templates import GAMEPLAY_MODES, GameplayTemplateError, validate_gameplay_mode
from core.roblox_place import RobloxPlaceBuildError, RojoPlaceBuilder
from core.worldbuilding import SceneRecipe, WorldbuildingError

from . import plan_review
from .assets import (
    MAX_GLB_BYTES,
    AssetUploadLedger,
    OpenCloudModelAssetUploader,
    RobloxAssetError,
    RobloxAssetTarget,
)
from .blender_transfer import (
    BlenderArtifactError,
    BlenderArtifactSource,
    PreparedModelUploadLedger,
)
from .cloud import OpenCloudMapValidator, RobloxCloudError, RobloxTarget, recipe_digest
from .downloads import DOWNLOAD_LIFETIME, PlaceDownloads
from .knowledge import list_resources, read_resource
from .publishing import (
    OpenCloudPlacePublisher,
    PlacePublicationLedger,
    RobloxPlacePublishError,
    RobloxPublishTarget,
)

TOOL_NAME = "rga_validate_map"
BUILD_TOOL_NAME = "rga_build_place"
DOWNLOAD_TOOL_NAME = "rga_build_place_download"
MAX_REQUEST_BYTES = 28_000_000
MAX_RESPONSE_BYTES = 11_000_000
MAX_GLB_BASE64_LENGTH = 4 * ((MAX_GLB_BYTES + 2) // 3)
MAX_LEDGER_ENTRIES = 10_000
_TOKEN = re.compile(r"[A-Za-z0-9._~+/-]+=*\Z", re.ASCII)
_PROTOCOL_VERSION = "2025-11-25"
ASSET_UPLOAD_TOOL_NAME = "rga_upload_reviewed_model"
ASSET_STATUS_TOOL_NAME = "rga_check_model_upload"
PREPARE_BLENDER_UPLOAD_TOOL_NAME = "rga_prepare_blender_model_upload"
COMMIT_BLENDER_UPLOAD_TOOL_NAME = "rga_upload_prepared_blender_model"
PLACE_PUBLISH_TOOL_NAME = "rga_publish_reviewed_place"
PREPARE_DIRECT_PUBLISH_TOOL_NAME = "rga_prepare_test_place_publication"
COMMIT_DIRECT_PUBLISH_TOOL_NAME = "rga_publish_prepared_test_place"


def _strict_json(raw: bytes) -> object:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )


def _tool_definition() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Validate a bounded RGA scene recipe in the configured disposable Roblox test place "
            "using the repository's fixed harness. This tool cannot execute supplied code."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "recipe": {"type": "object"},
                "request_id": {"type": "string", "format": "uuid"},
            },
            "required": ["recipe", "request_id"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
                "place_version": {"type": "string"},
                "task_id": {"type": "string"},
                "validation_status": {
                    "enum": ["structure_only", "navigation_pass", "navigation_failed"]
                },
                "object_count": {"type": "integer"},
                "path_feature_count": {"type": "integer"},
                "navigation_waypoint_count": {"type": "integer"},
                "navigation_connected": {"type": "boolean"},
                "navigation_failed_leg": {
                    "anyOf": [
                        {"type": "null"},
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "leg_index": {"type": "integer", "minimum": 0, "maximum": 511},
                                "from": {"type": "string", "maxLength": 64},
                                "to": {"type": "string", "maxLength": 64},
                            },
                            "required": ["leg_index", "from", "to"],
                        },
                    ]
                },
            },
            "required": [
                "request_id",
                "place_version",
                "task_id",
                "validation_status",
                "object_count",
                "path_feature_count",
                "navigation_waypoint_count",
                "navigation_connected",
                "navigation_failed_leg",
            ],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    }


def _build_tool_definition() -> dict[str, Any]:
    return {
        "name": BUILD_TOOL_NAME,
        "description": (
            "Build a Roblox .rbxlx from a bounded RGA scene recipe. Optional gameplay uses a "
            "fixed template or a closed data-only rule list; caller supplied Luau is never "
            "accepted. In Obby mode, path objects define checkpoint order and consecutive "
            "segments must connect in that order. "
            "The result is a downloadable artifact; this tool never publishes to Roblox. "
            "When a Game Plan is supplied, its mode, rules, and scene requirements are checked "
            "against the exact recipe in this build request."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "recipe": {"type": "object"},
                "plan": {"type": "object"},
                "request_id": {"type": "string", "format": "uuid"},
                "gameplay_mode": {"enum": sorted(GAMEPLAY_MODES)},
                "gameplay_rules": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 16,
                    "contains": {
                        "type": "object",
                        "required": ["action"],
                        "properties": {"action": {"enum": ["damage", "eliminate"]}},
                    },
                    "minContains": 0,
                    "maxContains": 1,
                    "items": {
                        "oneOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "trigger_role": {
                                        "enum": ["collectible", "hazard", "prop", "landmark"]
                                    },
                                    "action": {"const": "award_points"},
                                    "amount": {"type": "integer", "minimum": 1, "maximum": 1000},
                                },
                                "required": ["trigger_role", "action", "amount"],
                                "additionalProperties": False,
                            },
                            {
                                "type": "object",
                                "properties": {
                                    "trigger_role": {"enum": ["collectible", "prop"]},
                                    "action": {"const": "speed_boost"},
                                    "amount": {"type": "integer", "minimum": 1, "maximum": 16},
                                    "duration_seconds": {
                                        "type": "integer",
                                        "minimum": 1,
                                        "maximum": 30,
                                    },
                                },
                                "required": [
                                    "trigger_role",
                                    "action",
                                    "amount",
                                    "duration_seconds",
                                ],
                                "additionalProperties": False,
                            },
                            {
                                "type": "object",
                                "properties": {
                                    "trigger_role": {"const": "hazard"},
                                    "action": {"const": "damage"},
                                    "amount": {"type": "integer", "minimum": 1, "maximum": 100},
                                },
                                "required": ["trigger_role", "action", "amount"],
                                "additionalProperties": False,
                            },
                            {
                                "type": "object",
                                "properties": {
                                    "trigger_role": {
                                        "enum": ["collectible", "hazard", "prop", "landmark"]
                                    },
                                    "action": {"const": "heal"},
                                    "amount": {"type": "integer", "minimum": 1, "maximum": 100},
                                },
                                "required": ["trigger_role", "action", "amount"],
                                "additionalProperties": False,
                            },
                            {
                                "type": "object",
                                "properties": {
                                    "trigger_role": {"const": "hazard"},
                                    "action": {"const": "eliminate"},
                                },
                                "required": ["trigger_role", "action"],
                                "additionalProperties": False,
                            },
                            {
                                "type": "object",
                                "properties": {
                                    "trigger_role": {"const": "landmark"},
                                    "action": {"const": "award_win"},
                                    "minimum_points": {
                                        "type": "integer",
                                        "minimum": 1,
                                        "maximum": 1000,
                                    },
                                },
                                "required": ["trigger_role", "action", "minimum_points"],
                                "additionalProperties": False,
                            },
                        ]
                    },
                },
                "model_asset_id": {"type": "string", "pattern": "^[1-9][0-9]{0,19}$"},
            },
            "required": ["recipe", "request_id"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
                "sha256": {"type": "string"},
                "place_file_base64": {"type": "string"},
                "object_count": {"type": "integer"},
                "part_count": {"type": "integer"},
                "light_count": {"type": "integer"},
                "approximated_object_count": {"type": "integer"},
                "omitted_character_count": {"type": "integer"},
                "omitted_sun_light_count": {"type": "integer"},
                "gameplay_mode": {"enum": sorted(GAMEPLAY_MODES)},
                "imported_meshpart_count": {"type": "integer"},
            },
            "required": [
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
            ],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    }


def _download_tool_definition() -> dict[str, Any]:
    definition = _build_tool_definition()
    definition["name"] = DOWNLOAD_TOOL_NAME
    definition["description"] = (
        "Build a place and return a private browser download link valid for 15 minutes. "
        "Anyone given the link can download this artifact. Return the link only to the "
        "requesting user. This tool does not publish to Roblox."
    )
    output = definition["outputSchema"]
    del output["properties"]["place_file_base64"]
    output["required"].remove("place_file_base64")
    output["properties"].update(
        download_url={"type": "string", "format": "uri"}, expires_in_seconds={"type": "integer"}
    )
    output["required"].extend(["download_url", "expires_in_seconds"])
    return definition


def _asset_upload_tool_definition() -> dict[str, Any]:
    return {
        "name": ASSET_UPLOAD_TOOL_NAME,
        "description": (
            "Create a new Roblox Model asset from an approved GLB. Requires a short-lived "
            "server-signed operator approval bound to the exact artifact SHA-256. Each mesh "
            "primitive must fit Roblox's 20,000-triangle limit; before upload the host checks "
            "embedded geometry, skinning, animation, texture dimensions, and material-to-image "
            "references."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "format": "uuid"},
                "approval_id": {"type": "string", "format": "uuid"},
                "artifact_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "approval_signature": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "approval_expires_at": {"type": "integer"},
                "display_name": {"type": "string", "maxLength": 80},
                "description": {"type": "string", "maxLength": 1000},
                "glb_base64": {"type": "string", "maxLength": MAX_GLB_BASE64_LENGTH},
            },
            "required": [
                "request_id",
                "approval_id",
                "artifact_sha256",
                "approval_signature",
                "approval_expires_at",
                "display_name",
                "description",
                "glb_base64",
            ],
            "additionalProperties": False,
        },
        "_meta": {"anthropic/requiresUserInteraction": True},
    }


def _prepare_blender_upload_tool_definition() -> dict[str, Any]:
    return {
        "name": PREPARE_BLENDER_UPLOAD_TOOL_NAME,
        "description": (
            "Fetch and inspect metadata for one UUID-addressed GLB from the fixed, configured "
            "Blender MCP host. This read-only step creates no Roblox asset. It returns "
            "a short-lived digest-bound review receipt for a separate user-confirmed upload call. "
            "The source GLB is limited to 19 MiB, triangle budgets, geometry, skinning, "
            "animation, texture dimensions, and material-to-image references are checked, and "
            "bytes never pass through the agent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"artifact_id": {"type": "string", "format": "uuid"}},
            "required": ["artifact_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    }


def _commit_blender_upload_tool_definition() -> dict[str, Any]:
    return {
        "name": COMMIT_BLENDER_UPLOAD_TOOL_NAME,
        "description": (
            "Create a persistent Roblox Model asset from the exact prepared Blender GLB. "
            "This writes a new Roblox asset and requires the user to explicitly approve the exact "
            "digest and repeat the confirmation phrase returned in the review instructions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "format": "uuid"},
                "approval_id": {"type": "string", "format": "uuid"},
                "artifact_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "confirmation_phrase": {
                    "type": "string",
                    "pattern": "^I_APPROVE_ROBLOX_MODEL_UPLOAD_[0-9a-f]{12}$",
                },
            },
            "required": [
                "request_id",
                "approval_id",
                "artifact_sha256",
                "confirmation_phrase",
            ],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "openWorldHint": True,
        },
        "_meta": {"anthropic/requiresUserInteraction": True},
    }


def _place_publish_tool_definition() -> dict[str, Any]:
    return {
        "name": PLACE_PUBLISH_TOOL_NAME,
        "description": (
            "Compatibility route for the RGA operator API. Direct agents should use "
            "rga_prepare_test_place_publication followed by the separately approved "
            "rga_publish_prepared_test_place tool. This route publishes an exact digest-approved "
            "artifact to the one configured disposable test place."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "format": "uuid"},
                "approval_id": {"type": "string", "format": "uuid"},
                "artifact_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "approval_signature": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "approval_expires_at": {"type": "integer"},
                "place_file_base64": {"type": "string", "maxLength": 10666668},
            },
            "required": [
                "request_id",
                "approval_id",
                "artifact_sha256",
                "approval_signature",
                "approval_expires_at",
                "place_file_base64",
            ],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "openWorldHint": True,
        },
        "_meta": {"anthropic/requiresUserInteraction": True},
    }


def _prepare_direct_publish_tool_definition() -> dict[str, Any]:
    return {
        "name": PREPARE_DIRECT_PUBLISH_TOOL_NAME,
        "description": (
            "Read-only review step for a place artifact previously built by this MCP server. "
            "Returns the exact SHA-256, bounded build summary, fixed disposable target, and a "
            "short-lived confirmation phrase. It does not publish or modify Roblox."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "format": "uuid"},
                "artifact_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            },
            "required": ["request_id", "artifact_sha256"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    }


def _commit_direct_publish_tool_definition() -> dict[str, Any]:
    return {
        "name": COMMIT_DIRECT_PUBLISH_TOOL_NAME,
        "description": (
            "Publish a server-built .rbxlx artifact to the one configured disposable Roblox test "
            "place. This is a persistent external write. Only call after showing the exact digest, "
            "build summary, and fixed target, then receiving explicit user approval. Requires the "
            "exact short-lived confirmation phrase from rga_prepare_test_place_publication."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "format": "uuid"},
                "approval_id": {"type": "string", "format": "uuid"},
                "artifact_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                "confirmation_phrase": {
                    "type": "string",
                    "pattern": "^I_APPROVE_ROBLOX_TEST_PLACE_PUBLISH_[0-9a-f]{12}$",
                },
            },
            "required": [
                "request_id",
                "approval_id",
                "artifact_sha256",
                "confirmation_phrase",
            ],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "openWorldHint": True,
        },
        "_meta": {"anthropic/requiresUserInteraction": True},
    }


class _ToolServerConfig(Protocol):
    validation_enabled: bool
    place_builder: object | None
    downloads: object | None
    asset_uploader: object | None
    blender_artifact_source: object | None
    model_upload_ledger: object | None
    place_publisher: object | None


def _tool_definitions_for_server(server: _ToolServerConfig) -> list[dict[str, Any]]:
    tools = [_tool_definition()] if server.validation_enabled else []
    tools.append(plan_review.tool_definition())
    if server.place_builder is not None:
        tools.append(_build_tool_definition())
        if server.downloads is not None:
            tools.append(_download_tool_definition())
    if server.asset_uploader is not None:
        tools.append(_asset_upload_tool_definition())
        tools.append(
            {
                "name": ASSET_STATUS_TOOL_NAME,
                "description": (
                    "Check the receipt of a completed RGA Model upload. While moderation "
                    "is pending, read its current decision from Roblox. Supply the "
                    "original upload request_id. The tool never submits an upload."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {"request_id": {"type": "string", "format": "uuid"}},
                    "required": ["request_id"],
                    "additionalProperties": False,
                },
                "annotations": {"readOnlyHint": True, "destructiveHint": False},
            }
        )
    if (
        server.blender_artifact_source is not None
        and server.model_upload_ledger is not None
        and server.asset_uploader is not None
    ):
        tools.extend(
            [
                _prepare_blender_upload_tool_definition(),
                _commit_blender_upload_tool_definition(),
            ]
        )
    if server.place_publisher is not None:
        tools.extend(
            [
                _place_publish_tool_definition(),
                _prepare_direct_publish_tool_definition(),
                _commit_direct_publish_tool_definition(),
            ]
        )
    return tools


class ValidationLedger:
    """Durable idempotency ledger; ambiguous upstream calls are never resubmitted."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS requests ("
                "request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL, "
                "result_json TEXT, error TEXT)"
            )

    def run(
        self, validator: OpenCloudMapValidator, recipe: dict[str, Any], request_id: str
    ) -> dict[str, Any]:
        try:
            canonical_id = str(uuid.UUID(request_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("request_id must be a UUID") from exc
        if canonical_id != request_id.lower():
            raise ValueError("request_id must use canonical UUID syntax")
        digest = recipe_digest(recipe, validator.target)
        with self.lock, self._connect() as db:
            row = db.execute(
                "SELECT digest, state, result_json FROM requests WHERE request_id = ?",
                (canonical_id,),
            ).fetchone()
            if row is not None:
                if row[0] != digest:
                    raise ValueError(
                        "request_id was already used for a different recipe, validation version, "
                        "or test target"
                    )
                if row[1] == "complete" and isinstance(row[2], str):
                    return json.loads(row[2])
                raise RobloxCloudError(
                    "previous task outcome is uncertain; this request will not be resubmitted"
                )
            count = db.execute("SELECT COUNT(*) FROM requests").fetchone()
            if count is None or count[0] >= MAX_LEDGER_ENTRIES:
                raise RobloxCloudError(
                    "validation ledger is full; operator maintenance is required"
                )
            db.execute(
                "INSERT INTO requests(request_id, digest, state) VALUES (?, ?, 'pending')",
                (canonical_id, digest),
            )

        try:
            result = validator.validate_recipe(recipe)
            result["request_id"] = canonical_id
            result["place_version"] = validator.target.place_version
            with self.lock, self._connect() as db:
                db.execute(
                    "UPDATE requests SET state='complete', result_json=? WHERE request_id=?",
                    (json.dumps(result, separators=(",", ":")), canonical_id),
                )
            return result
        except (ValueError, RobloxCloudError) as exc:
            with self.lock, self._connect() as db:
                db.execute(
                    "UPDATE requests SET state='uncertain', error=? WHERE request_id=?",
                    (str(exc)[:500], canonical_id),
                )
            raise

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


class RobloxMCPHandler(http.server.BaseHTTPRequestHandler):
    server_version = "rga-roblox-mcp"
    sys_version = ""
    # A client that opens a connection and then stalls must not hold a thread
    # indefinitely; tool calls run with no socket read in progress.
    timeout = 30

    def do_GET(self) -> None:
        if not self._origin_allowed():
            self._plain(403, "Origin is not allowed.")
            return
        if self.path == "/mcp":
            self.send_response(405)
            self.send_header("Allow", "POST")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path == "/healthz":
            self._json(200, {"status": "ok"})
        elif self.path.startswith("/downloads/") and self.server.downloads is not None:  # type: ignore[attr-defined]
            data = self.server.downloads.read(self.path)  # type: ignore[attr-defined]
            if data is None:
                self._plain(404, "Download unavailable or expired.")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="game.rbxlx"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
        else:
            self._plain(404, "Not found.")

    def do_POST(self) -> None:
        if self.path != "/mcp":
            self._plain(404, "Not found.")
            return
        if not self._origin_allowed():
            self._plain(403, "Origin is not allowed.")
            return
        if not self._authorized():
            self._plain(401, "Unauthorized.")
            return
        if (
            self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            != "application/json"
        ):
            self._plain(415, "Content-Type must be application/json.")
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            self._plain(400, "Invalid Content-Length.")
            return
        if length < 1 or length > MAX_REQUEST_BYTES or self.headers.get("Transfer-Encoding"):
            self.close_connection = True
            self._plain(413 if length > MAX_REQUEST_BYTES else 400, "Request size is invalid.")
            return
        try:
            message = _strict_json(self._read_body(length))
        except (ValueError, UnicodeError, RecursionError):
            self._plain(400, "Request must be strict JSON.")
            return
        if (
            not isinstance(message, dict)
            or message.get("jsonrpc") != "2.0"
            or not isinstance(message.get("method"), str)
        ):
            self._plain(400, "Invalid JSON-RPC request.")
            return
        method = message["method"]
        if method != "initialize" and self.headers.get("MCP-Protocol-Version") != _PROTOCOL_VERSION:
            self._plain(400, "MCP-Protocol-Version is invalid.")
            return
        if method == "notifications/initialized" and "id" not in message:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if (
            "id" not in message
            or isinstance(message.get("id"), bool)
            or not isinstance(message.get("id"), (int, str))
        ):
            self._plain(400, "Invalid JSON-RPC request ID.")
            return
        if method == "initialize":
            self._rpc_result(
                message["id"],
                {
                    "protocolVersion": _PROTOCOL_VERSION,
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "rga-roblox-mcp", "version": "0.4.0"},
                    "instructions": (
                        "Start with resources/read at rga://skills/roblox-game-architect. "
                        "Use resources/list for domain guides, input schemas, and "
                        "rga://examples/ recipes, plans, and gameplay rules. "
                        "Build places only from bounded validated Scene Recipes with "
                        "rga_build_place. The default is script-free; caller-provided Luau is "
                        "never accepted. Use rga_validate_map only for the configured disposable "
                        "test place. For Blender meshes, use the fixed Blender MCP host. When "
                        "model transfer is enabled, prepare by artifact ID, show the digest and "
                        "exact confirmation phrase to the user, and upload only after explicit "
                        "approval to create that Roblox asset. Then build with its approved asset "
                        "ID. After a place build, direct agent clients may prepare a read-only "
                        "test-place publication review, show its exact digest, summary, target, "
                        "and phrase, then call the separate publish tool only after user approval. "
                        "Place publishing is limited to the configured disposable test place."
                    ),
                },
            )
            return
        params = message.get("params", {})
        if not isinstance(params, dict):
            self._rpc_error(message["id"], -32602, "Invalid request parameters")
            return
        if method == "ping":
            self._rpc_result(message["id"], {})
        elif method in {"resources/list", "resources/templates/list"}:
            if set(params) - {"_meta"}:
                self._rpc_error(message["id"], -32602, "Invalid resource list parameters")
            elif method == "resources/list":
                self._rpc_result(message["id"], {"resources": list_resources()})
            else:
                self._rpc_result(message["id"], {"resourceTemplates": []})
        elif method == "resources/read":
            uri = params.get("uri")
            if set(params) - {"uri", "_meta"} or not isinstance(uri, str) or not 0 < len(uri) < 256:
                self._rpc_error(message["id"], -32602, "Invalid resource read parameters")
                return
            try:
                resource = read_resource(uri)
            except (OSError, ValueError):
                self._rpc_error(message["id"], -32603, "Packaged resource is unavailable")
                return
            if resource is None:
                self._rpc_error(message["id"], -32002, "Resource not found")
            else:
                self._rpc_result(message["id"], {"contents": [resource]})
        elif method == "tools/list":
            tools = _tool_definitions_for_server(self.server)
            self._rpc_result(message["id"], {"tools": tools})
        elif method == "tools/call":
            self._call_tool(message["id"], params)
        else:
            self._rpc_error(message["id"], -32601, "Method not found")

    def _call_tool(self, call_id: object, params: dict[str, Any]) -> None:
        args = params.get("arguments")
        tool_name = params.get("name")
        if not isinstance(tool_name, str):
            self._rpc_error(call_id, -32602, "Invalid tool name")
            return
        if tool_name == plan_review.TOOL_NAME:
            if not isinstance(args, dict) or "plan" not in args or set(args) - {"plan", "recipe"}:
                self._rpc_error(call_id, -32602, "Expected plan and optional recipe")
                return
            try:
                review = plan_review.review(args)
            except (GamePlanningError, WorldbuildingError, GameplayTemplateError) as exc:
                self._review_error(call_id, exc)
                return
            self._rpc_result(
                call_id,
                {
                    "content": [{"type": "text", "text": json.dumps(review)}],
                    "structuredContent": review,
                },
            )
            return
        if tool_name == TOOL_NAME and not self.server.validation_enabled:  # type: ignore[attr-defined]
            self._rpc_error(call_id, -32602, "Map validation is not configured")
            return
        if tool_name in {PREPARE_BLENDER_UPLOAD_TOOL_NAME, COMMIT_BLENDER_UPLOAD_TOOL_NAME}:
            self._call_blender_asset_transfer(call_id, tool_name, args)
            return
        if tool_name == PREPARE_DIRECT_PUBLISH_TOOL_NAME:
            self._call_prepare_direct_publication(call_id, args)
            return
        if tool_name == COMMIT_DIRECT_PUBLISH_TOOL_NAME:
            self._call_commit_direct_publication(call_id, args)
            return
        if tool_name == ASSET_UPLOAD_TOOL_NAME:
            self._call_asset_upload(call_id, args)
            return
        if tool_name == ASSET_STATUS_TOOL_NAME:
            self._call_asset_status(call_id, args)
            return
        if tool_name == PLACE_PUBLISH_TOOL_NAME:
            self._call_place_publish(call_id, args)
            return
        allowed_arguments = (
            {"recipe", "request_id"}
            if tool_name == TOOL_NAME
            else {
                "recipe",
                "plan",
                "request_id",
                "gameplay_mode",
                "gameplay_rules",
                "model_asset_id",
            }
        )

        if (
            not isinstance(tool_name, str)
            or tool_name not in {TOOL_NAME, BUILD_TOOL_NAME, DOWNLOAD_TOOL_NAME}
            or not isinstance(args, dict)
            or set(args) - allowed_arguments
            or not {"recipe", "request_id"} <= set(args)
            or not isinstance(args.get("recipe"), dict)
            or not isinstance(args.get("request_id"), str)
        ):
            self._rpc_error(call_id, -32602, "Invalid tool arguments")
            return
        if tool_name in {BUILD_TOOL_NAME, DOWNLOAD_TOOL_NAME}:
            try:
                downloads = self.server.downloads  # type: ignore[attr-defined]
                if tool_name == DOWNLOAD_TOOL_NAME and downloads is None:
                    self._rpc_error(call_id, -32602, "Browser downloads are not configured")
                    return
                request_id = str(uuid.UUID(args["request_id"]))
                if request_id != args["request_id"].lower():
                    raise ValueError("request ID must use canonical UUID syntax")
                gameplay_mode = args.get("gameplay_mode", "blockout")
                gameplay_rules = args.get("gameplay_rules")
                try:
                    recipe = SceneRecipe.from_mapping(args["recipe"])
                    validate_gameplay_mode(gameplay_mode, recipe, gameplay_rules)
                    if "plan" in args:
                        plan_review.validate_build_request(
                            args["plan"], args["recipe"], gameplay_mode, gameplay_rules
                        )
                except ValueError as exc:
                    self._review_error(call_id, exc)
                    return
                if self.server.place_builder is None:  # type: ignore[attr-defined]
                    raise RobloxPlaceBuildError("Rojo is unavailable")
                imported_model = None
                imported_meshpart_count = 0
                model_asset_id = args.get("model_asset_id")
                if model_asset_id is not None:
                    if self.server.validator is None:  # type: ignore[attr-defined]
                        raise ValueError("Model import requires the configured Open Cloud harness")
                    if not isinstance(model_asset_id, str):
                        raise ValueError("model asset ID must be a decimal string")
                    if (
                        self.server.asset_ledger is None  # type: ignore[attr-defined]
                        or not self.server.asset_ledger.is_approved_model(model_asset_id)  # type: ignore[attr-defined]
                    ):
                        raise ValueError("model asset has no approved RGA upload receipt")
                    if gameplay_mode != "blockout":
                        raise ValueError(
                            "imported Blender models currently require script-free blockout mode"
                        )
                    imported_model, model_info = self.server.validator.serialize_approved_model(  # type: ignore[attr-defined]
                        model_asset_id
                    )
                    imported_meshpart_count = model_info["meshpart_count"]
                if imported_model is None:
                    if gameplay_mode == "blockout":
                        built = self.server.place_builder.build(args["recipe"])  # type: ignore[attr-defined]
                    elif gameplay_rules is None:
                        built = self.server.place_builder.build(  # type: ignore[attr-defined]
                            args["recipe"], gameplay_mode=gameplay_mode
                        )
                    else:
                        built = self.server.place_builder.build(  # type: ignore[attr-defined]
                            args["recipe"],
                            gameplay_mode=gameplay_mode,
                            gameplay_rules=gameplay_rules,
                        )
                else:
                    built = self.server.place_builder.build(  # type: ignore[attr-defined]
                        args["recipe"],
                        gameplay_mode=gameplay_mode,
                        imported_model=imported_model,
                        imported_meshpart_count=imported_meshpart_count,
                    )
                receipt = {
                    "request_id": request_id,
                    "sha256": hashlib.sha256(built.place_file).hexdigest(),
                    "object_count": built.object_count,
                    "part_count": built.part_count,
                    "light_count": built.light_count,
                    "approximated_object_count": built.approximated_object_count,
                    "omitted_character_count": built.omitted_character_count,
                    "omitted_sun_light_count": built.omitted_sun_light_count,
                    "gameplay_mode": getattr(built, "gameplay_mode", gameplay_mode),
                    "imported_meshpart_count": getattr(built, "imported_meshpart_count", 0),
                }
                if tool_name == DOWNLOAD_TOOL_NAME:
                    receipt["download_url"] = downloads.issue(built.place_file)
                    receipt["expires_in_seconds"] = DOWNLOAD_LIFETIME
                else:
                    receipt["place_file_base64"] = base64.b64encode(built.place_file).decode(
                        "ascii"
                    )
                publication_ledger = self.server.publication_ledger  # type: ignore[attr-defined]
                if publication_ledger is not None:
                    try:
                        publication_ledger.store_built_artifact(
                            built.place_file,
                            request_id=request_id,
                            summary={
                                key: receipt[key]
                                for key in (
                                    "object_count",
                                    "part_count",
                                    "light_count",
                                    "approximated_object_count",
                                    "omitted_character_count",
                                    "omitted_sun_light_count",
                                    "gameplay_mode",
                                    "imported_meshpart_count",
                                )
                            },
                        )
                    except (ValueError, RobloxPlacePublishError, sqlite3.Error):
                        # Artifact delivery remains useful even when this file is not publishable.
                        pass
            except (ValueError, RobloxPlaceBuildError, RobloxCloudError, OSError):
                self._rpc_result(
                    call_id,
                    {
                        "content": [
                            {"type": "text", "text": "The bounded Roblox place build failed."}
                        ],
                        "isError": True,
                    },
                )
                return
            self._rpc_result(
                call_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Download within 15 minutes: {receipt['download_url']}\n"
                                f"SHA-256: {receipt['sha256']}"
                                if tool_name == DOWNLOAD_TOOL_NAME
                                else "Roblox place artifact built. It was not published."
                            ),
                        }
                    ],
                    "structuredContent": receipt,
                },
            )
            return
        try:
            result = self.server.ledger.run(  # type: ignore[attr-defined]
                self.server.validator,
                args["recipe"],
                args["request_id"],  # type: ignore[attr-defined]
            )
        except (ValueError, RobloxCloudError):
            self._rpc_result(
                call_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "The fixed Roblox validation task failed or is uncertain.",
                        }
                    ],
                    "isError": True,
                },
            )
            return
        self._rpc_result(
            call_id,
            {
                "content": [
                    {"type": "text", "text": "Fixed-harness Roblox map validation completed."}
                ],
                "structuredContent": result,
            },
        )

    def _call_blender_asset_transfer(
        self, call_id: object, tool_name: object, args: object
    ) -> None:
        source = self.server.blender_artifact_source  # type: ignore[attr-defined]
        transfer_ledger = self.server.model_upload_ledger  # type: ignore[attr-defined]
        uploader = self.server.asset_uploader  # type: ignore[attr-defined]
        upload_ledger = self.server.asset_ledger  # type: ignore[attr-defined]
        if source is None or transfer_ledger is None or uploader is None or upload_ledger is None:
            self._rpc_error(call_id, -32602, "Blender-to-Roblox model transfer is not configured")
            return
        try:
            if tool_name == PREPARE_BLENDER_UPLOAD_TOOL_NAME:
                if not isinstance(args, dict) or set(args) != {"artifact_id"}:
                    raise ValueError("invalid prepare arguments")
                prepared = transfer_ledger.prepare(
                    source,
                    args["artifact_id"],
                    max_bytes=uploader.target.max_glb_bytes,
                )
                self._rpc_result(
                    call_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "No Roblox asset was created. Review the source artifact and "
                                    "recipe with the user. Only if the user approves creating a "
                                    "persistent Roblox Model, repeat the exact SHA-256 and the "
                                    "digest-bound confirmation phrase from structuredContent."
                                ),
                            }
                        ],
                        "structuredContent": prepared.to_mapping(),
                    },
                )
                return
            expected = {
                "request_id",
                "approval_id",
                "artifact_sha256",
                "confirmation_phrase",
            }
            if not isinstance(args, dict) or set(args) != expected:
                raise ValueError("invalid upload confirmation arguments")
            receipt = transfer_ledger.upload(
                source,
                uploader,
                upload_ledger,
                request_id=args["request_id"],
                approval_id=args["approval_id"],
                artifact_sha256=args["artifact_sha256"],
                confirmation_phrase=args["confirmation_phrase"],
            )
        except (ValueError, BlenderArtifactError, RobloxAssetError):
            self._rpc_result(
                call_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "Reviewed Blender model transfer failed.",
                        }
                    ],
                    "isError": True,
                },
            )
            return
        self._rpc_result(
            call_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Roblox Model asset creation request completed. Check moderation state "
                            "before attempting to import the asset into a place."
                        ),
                    }
                ],
                "structuredContent": receipt.to_mapping(),
            },
        )

    def _review_error(self, call_id: object, exc: ValueError) -> None:
        self._rpc_result(
            call_id,
            {
                "isError": True,
                "content": [
                    {"type": "text", "text": f"Revise the proposed input: {str(exc)[:512]}"}
                ],
            },
        )

    def _call_asset_status(self, call_id: object, args: object) -> None:
        uploader = self.server.asset_uploader  # type: ignore[attr-defined]
        ledger = self.server.asset_ledger  # type: ignore[attr-defined]
        if uploader is None or ledger is None:
            self._rpc_error(call_id, -32602, "Asset upload is not configured")
            return
        if not isinstance(args, dict) or set(args) != {"request_id"}:
            self._rpc_error(call_id, -32602, "Expected the original upload request_id")
            return
        try:
            receipt = ledger.check_moderation(uploader, args["request_id"])
        except (ValueError, RobloxAssetError, sqlite3.Error):
            self._rpc_result(
                call_id,
                {
                    "isError": True,
                    "content": [{"type": "text", "text": "Model status unavailable."}],
                },
            )
            return
        self._rpc_result(
            call_id,
            {
                "content": [{"type": "text", "text": f"Roblox Model upload: {receipt.status}."}],
                "structuredContent": receipt.to_mapping(),
            },
        )

    def _call_asset_upload(self, call_id: object, args: object) -> None:
        from core.asset_approval import verify_asset_approval

        from .assets import RobloxAssetError

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
        if not isinstance(args, dict) or set(args) != fields:
            self._rpc_error(call_id, -32602, "Invalid tool arguments")
            return
        uploader = self.server.asset_uploader  # type: ignore[attr-defined]
        if uploader is None:
            self._rpc_error(call_id, -32602, "Asset upload is not configured")
            return
        request_id = args["request_id"]
        approval_id = args["approval_id"]
        digest = args["artifact_sha256"]
        signature = args["approval_signature"]
        name = args["display_name"]
        description = args["description"]
        encoded = args["glb_base64"]
        if (
            not isinstance(request_id, str)
            or not isinstance(approval_id, str)
            or not isinstance(digest, str)
            or not isinstance(signature, str)
            or not isinstance(name, str)
            or not isinstance(description, str)
            or not isinstance(encoded, str)
            or len(encoded) > MAX_GLB_BASE64_LENGTH
        ):
            self._rpc_error(call_id, -32602, "Invalid tool arguments")
            return
        try:
            glb = base64.b64decode(encoded, validate=True)
            if hashlib.sha256(glb).hexdigest() != digest:
                raise ValueError("artifact digest mismatch")
            if not verify_asset_approval(
                self.server.asset_approval_secret,  # type: ignore[attr-defined]
                signature,
                request_id=request_id,
                approval_id=approval_id,
                artifact_sha256=digest,
                display_name=name,
                description=description,
                expires_at=args["approval_expires_at"],
            ):
                raise ValueError("approval signature is invalid or expired")
            result = self.server.asset_ledger.run(  # type: ignore[attr-defined]
                uploader,
                glb,
                request_id=request_id,
                approval_id=approval_id,
                approved_sha256=digest,
                display_name=name,
                description=description,
            )
        except (ValueError, RobloxAssetError):
            self._rpc_result(
                call_id,
                {
                    "content": [{"type": "text", "text": "Reviewed Roblox model upload failed."}],
                    "isError": True,
                },
            )
            return
        self._rpc_result(
            call_id,
            {
                "content": [{"type": "text", "text": "Reviewed Roblox model asset processed."}],
                "structuredContent": result.to_mapping(),
            },
        )

    def _call_place_publish(self, call_id: object, args: object) -> None:
        from .publishing import MAX_PLACE_BYTES

        fields = {
            "request_id",
            "approval_id",
            "artifact_sha256",
            "approval_signature",
            "approval_expires_at",
            "place_file_base64",
        }
        if not isinstance(args, dict) or set(args) != fields:
            self._rpc_error(call_id, -32602, "Invalid tool arguments")
            return
        publisher = self.server.place_publisher  # type: ignore[attr-defined]
        ledger = self.server.publication_ledger  # type: ignore[attr-defined]
        if publisher is None or ledger is None:
            self._rpc_error(call_id, -32602, "Place publishing is not configured")
            return
        if (
            any(not isinstance(args.get(key), str) for key in fields - {"approval_expires_at"})
            or type(args.get("approval_expires_at")) is not int
            or len(args["place_file_base64"]) > ((MAX_PLACE_BYTES + 2) // 3) * 4
        ):
            self._rpc_error(call_id, -32602, "Invalid tool arguments")
            return
        try:
            place_file = base64.b64decode(args["place_file_base64"], validate=True)
            receipt = ledger.run(
                publisher,
                place_file,
                request_id=args["request_id"],
                approval_id=args["approval_id"],
                artifact_sha256=args["artifact_sha256"],
                signature=args["approval_signature"],
                expires_at=args["approval_expires_at"],
            )
        except (ValueError, RobloxPlacePublishError):
            self._rpc_result(
                call_id,
                {
                    "content": [
                        {"type": "text", "text": "Reviewed Roblox place publication failed."}
                    ],
                    "isError": True,
                },
            )
            return
        self._rpc_result(
            call_id,
            {
                "content": [{"type": "text", "text": "Reviewed test-place publication completed."}],
                "structuredContent": receipt.to_mapping(),
            },
        )

    def _call_prepare_direct_publication(self, call_id: object, args: object) -> None:
        if (
            not isinstance(args, dict)
            or set(args) != {"request_id", "artifact_sha256"}
            or not all(isinstance(args.get(key), str) for key in args)
        ):
            self._rpc_error(call_id, -32602, "Invalid tool arguments")
            return
        publisher = self.server.place_publisher  # type: ignore[attr-defined]
        ledger = self.server.publication_ledger  # type: ignore[attr-defined]
        if publisher is None or ledger is None:
            self._rpc_error(call_id, -32602, "Direct place publishing is not configured")
            return
        try:
            review = ledger.prepare_direct_publication(
                publisher,
                request_id=args["request_id"],
                artifact_sha256=args["artifact_sha256"],
            )
        except (ValueError, RobloxPlacePublishError):
            self._rpc_result(
                call_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "The exact server-built artifact is unavailable for review.",
                        }
                    ],
                    "isError": True,
                },
            )
            return
        self._rpc_result(
            call_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Read-only publication review prepared. Show the digest, summary, "
                            "fixed test target, and confirmation phrase to the user. Publishing "
                            "requires separate approval for the publish tool call."
                        ),
                    }
                ],
                "structuredContent": review,
            },
        )

    def _call_commit_direct_publication(self, call_id: object, args: object) -> None:
        fields = {"request_id", "approval_id", "artifact_sha256", "confirmation_phrase"}
        if (
            not isinstance(args, dict)
            or set(args) != fields
            or not all(isinstance(args.get(key), str) for key in fields)
        ):
            self._rpc_error(call_id, -32602, "Invalid tool arguments")
            return
        publisher = self.server.place_publisher  # type: ignore[attr-defined]
        ledger = self.server.publication_ledger  # type: ignore[attr-defined]
        if publisher is None or ledger is None:
            self._rpc_error(call_id, -32602, "Direct place publishing is not configured")
            return
        try:
            receipt = ledger.publish_prepared_artifact(
                publisher,
                request_id=args["request_id"],
                approval_id=args["approval_id"],
                artifact_sha256=args["artifact_sha256"],
                confirmation_phrase=args["confirmation_phrase"],
            )
        except (ValueError, RobloxPlacePublishError):
            self._rpc_result(
                call_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "Reviewed test-place publication failed or is uncertain.",
                        }
                    ],
                    "isError": True,
                },
            )
            return
        self._rpc_result(
            call_id,
            {
                "content": [
                    {"type": "text", "text": "Reviewed Roblox test-place publication completed."}
                ],
                "structuredContent": receipt.to_mapping(),
            },
        )

    def _read_body(self, length: int) -> bytes:
        """Read the declared body, or give up on a client that stalls.

        The socket timeout above turns a stalled read into an error; it is reported as
        a bad body so the existing rejection path answers it, and the connection ends.
        """
        try:
            return self.rfile.read(length)
        except OSError as exc:
            self.close_connection = True
            raise ValueError("the request body was not received") from exc

    def _authorized(self) -> bool:
        scheme, _, token = (self.headers.get("Authorization") or "").partition(" ")
        expected = self.server.bearer_token  # type: ignore[attr-defined]
        return scheme.lower() == "bearer" and bool(token) and hmac.compare_digest(token, expected)

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in self.server.allowed_origins  # type: ignore[attr-defined]

    def _rpc_result(self, request_id: object, result: dict[str, Any]) -> None:
        self._json(200, {"jsonrpc": "2.0", "id": request_id, "result": result})

    def _rpc_error(self, request_id: object, code: int, message: str) -> None:
        self._json(
            200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
        )

    def _json(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > MAX_RESPONSE_BYTES:
            self._plain(500, "MCP response exceeded the configured limit.")
            return
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("MCP-Protocol-Version", _PROTOCOL_VERSION)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _plain(self, status: int, message: str) -> None:
        body = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


class RobloxMCPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(
        self,
        host: str,
        port: int,
        validator: OpenCloudMapValidator | None,
        ledger: ValidationLedger | None,
        bearer_token: str,
        place_builder: RojoPlaceBuilder | None = None,
        asset_uploader: OpenCloudModelAssetUploader | None = None,
        asset_ledger: AssetUploadLedger | None = None,
        asset_approval_secret: str = "",
        blender_artifact_source: BlenderArtifactSource | None = None,
        model_upload_ledger: PreparedModelUploadLedger | None = None,
        place_publisher: OpenCloudPlacePublisher | None = None,
        publication_ledger: PlacePublicationLedger | None = None,
        allowed_origins: tuple[str, ...] = (),
        download_origin: str = "",
    ) -> None:
        if not isinstance(bearer_token, str) or not 32 <= len(bearer_token) <= 512:
            raise ValueError("RGA_ROBLOX_MCP_TOKEN must contain 32-512 characters")
        if not bearer_token.isascii() or not _TOKEN.fullmatch(bearer_token):
            raise ValueError("RGA_ROBLOX_MCP_TOKEN has invalid characters")
        self.downloads = PlaceDownloads(download_origin) if download_origin else None
        super().__init__((host, port), RobloxMCPHandler)
        if any(
            not isinstance(origin, str) or not origin.startswith("https://")
            for origin in allowed_origins
        ):
            raise ValueError("allowed MCP origins must be HTTPS origins")
        self.allowed_origins = frozenset(allowed_origins)
        self.validator = validator
        self.ledger = ledger
        self.validation_enabled = validator is not None and ledger is not None
        self.bearer_token = bearer_token
        if place_builder is None:
            try:
                place_builder = RojoPlaceBuilder(os.environ.get("RGA_ROBLOX_ROJO_BIN", "rojo"))
            except RobloxPlaceBuildError:
                place_builder = None
        self.place_builder = place_builder
        if (asset_uploader is None) != (asset_ledger is None):
            raise ValueError("asset upload requires both an uploader and durable ledger")
        if asset_uploader is not None and (
            not isinstance(asset_approval_secret, str)
            or not 32 <= len(asset_approval_secret) <= 512
            or not asset_approval_secret.isascii()
            or any(ord(char) < 33 or ord(char) > 126 for char in asset_approval_secret)
        ):
            raise ValueError("asset upload requires a printable server-side approval secret")
        self.asset_uploader = asset_uploader
        self.asset_ledger = asset_ledger
        self.asset_approval_secret = asset_approval_secret
        if (blender_artifact_source is None) != (model_upload_ledger is None):
            raise ValueError(
                "Blender transfer requires both a fixed source and durable review ledger"
            )
        if blender_artifact_source is not None and asset_uploader is None:
            raise ValueError("Blender transfer requires the reviewed Roblox asset uploader")
        self.blender_artifact_source = blender_artifact_source
        self.model_upload_ledger = model_upload_ledger
        if (place_publisher is None) != (publication_ledger is None):
            raise ValueError("place publishing requires a publisher and durable ledger")
        self.place_publisher = place_publisher
        self.publication_ledger = publication_ledger
        self._request_slots = threading.BoundedSemaphore(2)

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        if not self._request_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Length: 0\r\nConnection: close\r\n\r\n"
                )
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(
        self, request: socket.socket, client_address: tuple[str, int]
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


def main() -> None:
    token = os.environ.get("RGA_ROBLOX_MCP_TOKEN", "").strip()
    asset_uploader = None
    asset_ledger = None
    asset_approval_secret = ""
    blender_artifact_source = None
    model_upload_ledger = None
    place_publisher = None
    publication_ledger = None
    asset_configured = any(
        os.environ.get(name)
        for name in (
            "RGA_ROBLOX_ASSET_CREATOR_TYPE",
            "RGA_ROBLOX_ASSET_CREATOR_ID",
            "ROBLOX_OPEN_CLOUD_ASSET_API_KEY",
            "RGA_ROBLOX_ASSET_CREATION_CONFIRMED",
        )
    )
    if asset_configured:
        asset_target = RobloxAssetTarget.from_env()
        asset_approval_secret = os.environ.get("RGA_ROBLOX_ASSET_APPROVAL_SECRET", "")
        if not 32 <= len(asset_approval_secret) <= 512:
            raise ValueError("asset approval signing secret must contain 32-512 characters")
        asset_uploader = OpenCloudModelAssetUploader(asset_target)
        asset_ledger = AssetUploadLedger(
            os.environ.get("RGA_ROBLOX_ASSET_LEDGER", "/var/lib/rga/asset_uploads.sqlite3")
        )
    blender_transfer_configured = any(
        os.environ.get(name)
        for name in (
            "BLENDER_MCP_URL",
            "BLENDER_MCP_BEARER_TOKEN",
            "RGA_ROBLOX_BLENDER_TRANSFER_CONFIRMED",
        )
    )
    if blender_transfer_configured:
        if asset_uploader is None:
            raise ValueError("Blender-to-Roblox transfer requires configured asset creation")
        blender_artifact_source = BlenderArtifactSource.from_env()
        model_upload_ledger = PreparedModelUploadLedger(
            os.environ.get(
                "RGA_ROBLOX_MODEL_TRANSFER_LEDGER", "/var/lib/rga/model_transfers.sqlite3"
            )
        )
    publish_configured = any(
        os.environ.get(name)
        for name in (
            "ROBLOX_OPEN_CLOUD_PUBLISH_API_KEY",
            "RGA_ROBLOX_PLACE_PUBLISH_CONFIRMED",
            "RGA_ROBLOX_PUBLISH_APPROVAL_SECRET",
        )
    )
    if publish_configured:
        publish_target = RobloxPublishTarget.from_env()
        place_publisher = OpenCloudPlacePublisher(publish_target)
        publication_ledger = PlacePublicationLedger(
            os.environ.get("RGA_ROBLOX_PUBLISH_LEDGER", "/var/lib/rga/place_publications.sqlite3")
        )
    validator = None
    ledger = None
    place_builder = None
    cloud_configured = (
        asset_configured
        or publish_configured
        or any(
            os.environ.get(name)
            for name in (
                "ROBLOX_OPEN_CLOUD_API_KEY",
                "RGA_ROBLOX_TEST_UNIVERSE_ID",
                "RGA_ROBLOX_TEST_PLACE_ID",
                "RGA_ROBLOX_TEST_PLACE_VERSION",
                "RGA_ROBLOX_PRODUCTION_UNIVERSE_IDS",
                "RGA_ROBLOX_PRODUCTION_PLACE_IDS",
                "RGA_ROBLOX_DISPOSABLE_CONFIRMED",
                "RGA_ROBLOX_PERSISTENCE_VERIFIED",
                "RGA_ROBLOX_PERSISTENCE_EVIDENCE",
            )
        )
    )
    if cloud_configured:
        validator = OpenCloudMapValidator(RobloxTarget.from_env())
        ledger = ValidationLedger(
            os.environ.get("RGA_ROBLOX_LEDGER", "/var/lib/rga/validation.sqlite3")
        )
    else:
        place_builder = RojoPlaceBuilder(os.environ.get("RGA_ROBLOX_ROJO_BIN", "rojo"))
    host = os.environ.get("RGA_ROBLOX_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("RGA_ROBLOX_MCP_PORT", "8790"))
    origins = tuple(
        item.strip()
        for item in os.environ.get("RGA_ROBLOX_MCP_ALLOWED_ORIGINS", "").split(",")
        if item.strip()
    )
    server = RobloxMCPServer(
        host,
        port,
        validator,
        ledger,
        token,
        place_builder=place_builder,
        asset_uploader=asset_uploader,
        asset_ledger=asset_ledger,
        asset_approval_secret=asset_approval_secret,
        blender_artifact_source=blender_artifact_source,
        model_upload_ledger=model_upload_ledger,
        place_publisher=place_publisher,
        publication_ledger=publication_ledger,
        allowed_origins=origins,
        download_origin=os.environ.get("RGA_ROBLOX_DOWNLOAD_ORIGIN", ""),
    )
    print(f"RGA Roblox MCP listening on {host}:{port}; TLS must terminate at a trusted proxy")
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
