"""Remote MCP service that validates scene recipes and renders GLB artifacts.

The service exposes a fixed data-only tool. Blender runs as a trusted background
worker in the server environment; recipe payloads are never evaluated as code.
Terminate TLS at a trusted reverse proxy before exposing this process publicly.
"""

from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import os
import re
import socket
import sqlite3
import struct
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "packages"))
from core.worldbuilding import MAX_RENDERED_OBJECTS, SceneRecipe, WorldbuildingError  # noqa: E402
from sandbox.parser import _run_bounded  # noqa: E402

PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSION = "2025-11-25"
TOOL_NAME = "rga_apply_scene_recipe"
MAX_REQUEST_BYTES = 1_200_000
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
WORKER_TIMEOUT_SECONDS = 180
WORKER_MEMORY_LIMIT_BYTES = 4 * 1024 * 1024 * 1024
ARTIFACT_RETENTION_SECONDS = 7 * 24 * 60 * 60
MAX_ARTIFACT_STORE_BYTES = 2 * 1024 * 1024 * 1024
_ARTIFACT_ROUTE = re.compile(r"/artifacts/([0-9a-f-]{36})\.glb\Z", re.ASCII)
_BEARER = re.compile(r"[A-Za-z0-9._~+/-]+=*\Z", re.ASCII)
_REQUEST_NAMESPACE = uuid.UUID("0c59cf7a-49ee-46a6-8ce7-c37c9b8a3d5a")


class MCPServiceError(RuntimeError):
    """A request or the isolated Blender worker could not be completed."""


@dataclass(frozen=True, slots=True)
class ArtifactReceipt:
    request_id: str
    artifact_id: str
    recipe_name: str
    object_count: int

    def as_mapping(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "artifact_id": self.artifact_id,
            "recipe_name": self.recipe_name,
            "object_count": self.object_count,
        }


def _strict_json(raw: bytes) -> object:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    return json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)),
    )


class BlenderSceneRenderer:
    """Serialize Blender jobs and keep idempotent records in a SQLite ledger."""

    def __init__(
        self,
        blender_executable: str | Path,
        output_dir: str | Path,
        *,
        project_root: str | Path = REPOSITORY_ROOT,
        artifact_retention_seconds: int = ARTIFACT_RETENTION_SECONDS,
        max_store_bytes: int = MAX_ARTIFACT_STORE_BYTES,
    ) -> None:
        executable = Path(blender_executable).resolve()
        if not executable.is_file():
            raise ValueError("BLENDER_EXECUTABLE must point to a Blender executable")
        root = Path(project_root).resolve()
        addon = root / "apps" / "blender-addon" / "rga_scene_builder" / "__init__.py"
        worker = root / "apps" / "blender_mcp_server" / "worker.py"
        if not addon.is_file() or not worker.is_file():
            raise ValueError("RGA Blender extension or trusted worker is missing")
        self.executable = executable
        self.project_root = root
        self.worker = worker
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.output_dir.is_symlink():
            raise ValueError("artifact directory must not be a symlink")
        self.database_path = self.output_dir / "requests.sqlite3"
        if artifact_retention_seconds < 60 or max_store_bytes < MAX_ARTIFACT_BYTES:
            raise ValueError("artifact retention and storage limits are too small")
        self.artifact_retention_seconds = artifact_retention_seconds
        self.max_store_bytes = max_store_bytes
        self._job_lock = threading.Lock()
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS requests ("
                "request_id TEXT PRIMARY KEY, recipe_digest TEXT NOT NULL, "
                "artifact_id TEXT NOT NULL, created_at INTEGER NOT NULL)"
            )
            self._prune_artifacts(db, int(time.time()))

    def is_ready(self) -> bool:
        """Check worker inputs and the artifact ledger without launching Blender."""
        if not self.executable.is_file() or not self.worker.is_file():
            return False
        if (
            not self.output_dir.is_dir()
            or self.output_dir.is_symlink()
            or not self.database_path.is_file()
        ):
            return False
        db: sqlite3.Connection | None = None
        try:
            # Health probes must not switch journal mode or wait behind a render job.
            db = sqlite3.connect(self.database_path, timeout=1.0)
            db.execute("SELECT 1 FROM requests LIMIT 1").fetchone()
        except sqlite3.Error:
            return False
        finally:
            if db is not None:
                db.close()
        return True

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.database_path, timeout=15)
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

    def apply_recipe(self, recipe_payload: object, request_id: str) -> ArtifactReceipt:
        try:
            request_uuid = uuid.UUID(request_id)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("request_id must be a UUID") from exc
        if str(request_uuid) != request_id.lower():
            raise ValueError("request_id must use canonical UUID syntax")
        recipe = SceneRecipe.from_mapping(recipe_payload)
        normalized = recipe.to_json().encode("utf-8")
        digest = hashlib.sha256(normalized).hexdigest()
        artifact_id = str(uuid.uuid5(_REQUEST_NAMESPACE, str(request_uuid)))
        artifact_path = self._artifact_path(artifact_id)
        object_count = recipe.rendered_object_count

        with self._job_lock, self._connect() as db:
            self._prune_artifacts(db, int(time.time()), preserve_artifact=artifact_id)
            existing = db.execute(
                "SELECT recipe_digest, artifact_id FROM requests WHERE request_id = ?",
                (str(request_uuid),),
            ).fetchone()
            if existing is not None:
                if existing[0] != digest or existing[1] != artifact_id:
                    raise ValueError("request_id was already used for a different scene recipe")
                if artifact_path.is_file():
                    self._validate_glb(artifact_path)
                    return ArtifactReceipt(
                        str(request_uuid), artifact_id, recipe.name, object_count
                    )
            else:
                db.execute(
                    "INSERT INTO requests(request_id, recipe_digest, artifact_id, created_at) "
                    "VALUES(?, ?, ?, ?)",
                    (str(request_uuid), digest, artifact_id, int(time.time())),
                )

            with tempfile.TemporaryDirectory(prefix="rga-blender-job-") as temp:
                job_dir = Path(temp)
                recipe_path = job_dir / "recipe.json"
                temporary_glb = job_dir / "scene.glb"
                result_path = job_dir / "result.json"
                recipe_path.write_bytes(normalized)
                command = [
                    str(self.executable),
                    "--background",
                    "--factory-startup",
                    "--python-exit-code",
                    "1",
                    "--python",
                    str(self.worker),
                    "--",
                    "--project-root",
                    str(self.project_root),
                    "--recipe",
                    str(recipe_path),
                    "--output",
                    str(temporary_glb),
                    "--result",
                    str(result_path),
                ]
                try:
                    _run_bounded(
                        command,
                        cwd=job_dir,
                        env={
                            key: os.environ[key]
                            for key in ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
                            if os.environ.get(key)
                        }
                        | {
                            "HOME": str(job_dir),
                            "TMPDIR": str(job_dir),
                            "XDG_CONFIG_HOME": str(job_dir / ".config"),
                        },
                        timeout_seconds=WORKER_TIMEOUT_SECONDS,
                        max_stdout_bytes=512 * 1024,
                        max_stderr_bytes=64 * 1024,
                        memory_limit_bytes=WORKER_MEMORY_LIMIT_BYTES,
                    )
                    result = _strict_json(result_path.read_bytes())
                except Exception as exc:
                    raise MCPServiceError("Blender could not build the reviewed recipe") from exc
                if (
                    not isinstance(result, dict)
                    or set(result) != {"created_objects"}
                    or result["created_objects"] != object_count
                ):
                    raise MCPServiceError("Blender worker returned an invalid result")
                if not temporary_glb.is_file() or temporary_glb.stat().st_size > MAX_ARTIFACT_BYTES:
                    raise MCPServiceError("Blender GLB is missing or exceeds the artifact limit")
                self._validate_glb(temporary_glb)
                staging_path = artifact_path.with_suffix(".glb.tmp")
                temporary_glb.replace(staging_path)
                staging_path.replace(artifact_path)
                self._prune_artifacts(db, int(time.time()), preserve_artifact=artifact_id)

            return ArtifactReceipt(str(request_uuid), artifact_id, recipe.name, object_count)

    def _artifact_path(self, artifact_id: str) -> Path:
        path = self.output_dir / f"{artifact_id}.glb"
        if path.parent != self.output_dir or path.is_symlink():
            raise MCPServiceError("artifact path is invalid")
        return path

    @staticmethod
    def _validate_glb(path: Path) -> None:
        size = path.stat().st_size
        if not 20 <= size <= MAX_ARTIFACT_BYTES:
            raise MCPServiceError("artifact is not a supported GLB file")
        with path.open("rb") as stream:
            magic, version, total_size = struct.unpack("<4sII", stream.read(12))
            json_size, chunk_type = struct.unpack("<I4s", stream.read(8))
            payload = _strict_json(stream.read(json_size))
        if (
            magic != b"glTF"
            or version != 2
            or total_size != size
            or chunk_type != b"JSON"
            or not isinstance(payload, dict)
            or not isinstance(payload.get("meshes"), list)
            or not payload["meshes"]
        ):
            raise MCPServiceError("Blender output is not a valid GLB scene")

    def read_artifact(self, artifact_id: str) -> bytes | None:
        try:
            canonical_id = str(uuid.UUID(artifact_id))
        except ValueError:
            return None
        with self._connect() as db:
            found = db.execute(
                "SELECT 1 FROM requests WHERE artifact_id = ?", (canonical_id,)
            ).fetchone()
        if found is None:
            return None
        path = self._artifact_path(canonical_id)
        try:
            if path.stat().st_size > MAX_ARTIFACT_BYTES:
                return None
            with path.open("rb") as stream:
                data = stream.read(MAX_ARTIFACT_BYTES + 1)
        except OSError:
            return None
        return data if len(data) <= MAX_ARTIFACT_BYTES else None

    def _prune_artifacts(
        self, db: sqlite3.Connection, now: int, *, preserve_artifact: str | None = None
    ) -> None:
        expired_before = now - self.artifact_retention_seconds
        expired = db.execute(
            "SELECT request_id, artifact_id FROM requests WHERE created_at < ?",
            (expired_before,),
        ).fetchall()
        for request_id, artifact_id in expired:
            if artifact_id != preserve_artifact:
                self._remove_artifact_file(artifact_id)
                db.execute("DELETE FROM requests WHERE request_id = ?", (request_id,))

        files = {path.stem: path for path in self.output_dir.glob("*.glb") if path.is_file()}
        total = sum(path.stat().st_size for path in files.values())
        oldest = db.execute(
            "SELECT request_id, artifact_id FROM requests ORDER BY created_at ASC"
        ).fetchall()
        for request_id, artifact_id in oldest:
            if total <= self.max_store_bytes:
                break
            if artifact_id == preserve_artifact:
                continue
            path = files.pop(artifact_id, None)
            if path is not None:
                try:
                    total -= path.stat().st_size
                except OSError:
                    pass
                self._remove_artifact_file(artifact_id)
            db.execute("DELETE FROM requests WHERE request_id = ?", (request_id,))

    def _remove_artifact_file(self, artifact_id: str) -> None:
        try:
            self._artifact_path(artifact_id).unlink(missing_ok=True)
        except OSError:
            pass


def _tool_definition() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Build a validated, data-only RGA Scene Recipe with remote Blender and return an "
            "artifact ID and metadata. The GLB stays on this server; no Python, bpy code, file "
            "paths, or executable expressions are accepted. If the Roblox MCP host is configured "
            "to use this fixed Blender host, pass the artifact ID to its prepare-model-upload tool "
            "for a separate, user-confirmed transfer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "recipe": {"type": "object"},
                "request_id": {"type": "string"},
            },
            "required": ["recipe", "request_id"],
            "additionalProperties": False,
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "format": "uuid"},
                "artifact_id": {"type": "string", "format": "uuid"},
                "recipe_name": {"type": "string"},
                "object_count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_RENDERED_OBJECTS,
                },
            },
            "required": ["request_id", "artifact_id", "recipe_name", "object_count"],
            "additionalProperties": False,
        },
    }


class BlenderMCPHandler(http.server.BaseHTTPRequestHandler):
    server_version = "rga-blender-mcp"
    sys_version = ""

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
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
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
            message = _strict_json(self.rfile.read(length))
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
        if method == "notifications/initialized" and "id" not in message:
            if self.headers.get("MCP-Protocol-Version") != LEGACY_PROTOCOL_VERSION:
                self._plain(400, "MCP-Protocol-Version is invalid.")
                return
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
        request_id = message["id"]
        if method == "initialize":
            params = message.get("params")
            requested_version = params.get("protocolVersion") if isinstance(params, dict) else None
            if requested_version != LEGACY_PROTOCOL_VERSION:
                self._rpc_error(
                    200,
                    request_id,
                    -32022,
                    "Unsupported protocol version",
                    {"supported": [LEGACY_PROTOCOL_VERSION]},
                )
                return
            self._rpc_result(
                request_id,
                {
                    "protocolVersion": LEGACY_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "rga-blender-mcp", "version": "0.2.0"},
                    "instructions": (
                        "Use rga_apply_scene_recipe with a validated, data-only Scene Recipe. "
                        "Generated Python and arbitrary bpy commands are not accepted."
                    ),
                },
            )
            return
        legacy = self.headers.get("MCP-Protocol-Version") == LEGACY_PROTOCOL_VERSION
        params = message.get("params", {})
        if not isinstance(params, dict):
            self._rpc_error(400, request_id, -32020, "Request parameters are missing")
            return
        name = params.get("name")
        if legacy:
            if self.headers.get("Mcp-Name") not in {None, name}:
                self._rpc_error(400, request_id, -32020, "HTTP tool name does not match")
                return
        else:
            meta = params.get("_meta")
            if (
                not isinstance(meta, dict)
                or meta.get("io.modelcontextprotocol/protocolVersion") != PROTOCOL_VERSION
            ):
                self._rpc_error(
                    400,
                    request_id,
                    -32022,
                    "Unsupported protocol version",
                    {"supported": [PROTOCOL_VERSION, LEGACY_PROTOCOL_VERSION]},
                )
                return
            if (
                self.headers.get("MCP-Protocol-Version") != PROTOCOL_VERSION
                or self.headers.get("Mcp-Method") != method
                or (isinstance(name, str) and self.headers.get("Mcp-Name") != name)
            ):
                self._rpc_error(400, request_id, -32020, "HTTP headers do not match the request")
                return
        if method == "server/discover":
            self._rpc_result(
                request_id,
                {
                    "resultType": "complete",
                    "supportedVersions": [PROTOCOL_VERSION, LEGACY_PROTOCOL_VERSION],
                    "capabilities": {"tools": {}},
                    "_meta": {
                        "io.modelcontextprotocol/serverInfo": {
                            "name": "rga-blender-mcp",
                            "version": "0.2.0",
                        }
                    },
                    "instructions": (
                        "Use rga_apply_scene_recipe with a validated, data-only Scene Recipe. "
                        "Generated Python and arbitrary bpy commands are not accepted."
                    ),
                    "ttlMs": 0,
                    "cacheScope": "private",
                },
            )
        elif method == "ping":
            self._rpc_result(request_id, {"resultType": "complete"} if not legacy else {})
        elif method == "tools/list":
            result = {"tools": [_tool_definition()]}
            if not legacy:
                result.update({"resultType": "complete", "ttlMs": 0, "cacheScope": "private"})
            self._rpc_result(request_id, result)
        elif method == "tools/call":
            self._call_tool(message, params)
        else:
            self._rpc_error(404, request_id, -32601, "Method not found")

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
            if self.server.renderer.is_ready():  # type: ignore[attr-defined]
                self._json(200, {"status": "ok"})
            else:
                self._json(503, {"status": "unavailable"})
            return
        if not self._authorized():
            self._plain(401, "Unauthorized.")
            return
        match = _ARTIFACT_ROUTE.fullmatch(self.path)
        if match is None:
            self._plain(404, "Not found.")
            return
        if not self._authorized():
            self._plain(401, "Unauthorized.")
            return
        artifact_id = match.group(1)
        data = self.server.renderer.read_artifact(artifact_id)  # type: ignore[attr-defined]
        if data is None:
            self._plain(404, "Artifact not found.")
            return
        self.send_response(200)
        self.send_header("Content-Type", "model/gltf-binary")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="rga-{artifact_id}.glb"')
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _call_tool(self, message: dict[str, Any], params: dict[str, Any]) -> None:
        arguments = params.get("arguments")
        if (
            params.get("name") != TOOL_NAME
            or self.headers.get("Mcp-Name") not in {None, TOOL_NAME}
            or not isinstance(arguments, dict)
            or set(arguments) != {"recipe", "request_id"}
            or not isinstance(arguments["recipe"], dict)
            or not isinstance(arguments["request_id"], str)
        ):
            self._rpc_error(400, message.get("id"), -32602, "Invalid tool arguments")
            return
        try:
            receipt = self.server.renderer.apply_recipe(  # type: ignore[attr-defined]
                arguments["recipe"], arguments["request_id"]
            )
        except WorldbuildingError as exc:
            self._rpc_result(
                message["id"],
                {
                    "content": [{"type": "text", "text": f"Revise the recipe: {str(exc)[:512]}"}],
                    "isError": True,
                },
            )
            return
        except (ValueError, MCPServiceError):
            result = {
                "content": [{"type": "text", "text": "The recipe could not be built."}],
                "isError": True,
            }
            self._rpc_result(message["id"], result)
            return
        value = receipt.as_mapping()
        result = {
            "content": [{"type": "text", "text": "Validated scene built as a GLB artifact."}],
            "structuredContent": value,
        }
        request_params = message.get("params")
        request_meta = request_params.get("_meta") if isinstance(request_params, dict) else None
        if (
            isinstance(request_meta, dict)
            and request_meta.get("io.modelcontextprotocol/protocolVersion") == PROTOCOL_VERSION
        ):
            result["resultType"] = "complete"
        self._rpc_result(message["id"], result)

    def _authorized(self) -> bool:
        scheme, _, token = (self.headers.get("Authorization") or "").partition(" ")
        expected = self.server.bearer_token  # type: ignore[attr-defined]
        return scheme.lower() == "bearer" and bool(token) and hmac.compare_digest(token, expected)

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in self.server.allowed_origins  # type: ignore[attr-defined]

    def _rpc_result(self, request_id: object, result: dict[str, Any]) -> None:
        self._json(
            200,
            {"jsonrpc": "2.0", "id": request_id, "result": result},
        )

    def _rpc_error(
        self, status: int, request_id: object, code: int, message: str, data: object = None
    ) -> None:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        self._json(status, {"jsonrpc": "2.0", "id": request_id, "error": error})

    def _json(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
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
        # Never log request headers, payloads, or upstream Blender diagnostics.
        del format, args


class BlenderMCPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(
        self,
        host: str,
        port: int,
        renderer: BlenderSceneRenderer,
        bearer_token: str,
        allowed_origins: tuple[str, ...] = (),
    ) -> None:
        token = bearer_token.strip()
        if not 32 <= len(token) <= 512 or not token.isascii() or not _BEARER.fullmatch(token):
            raise ValueError("BLENDER_MCP_BEARER_TOKEN must be a 32-512 character token")
        super().__init__((host, port), BlenderMCPHandler)
        self.renderer = renderer
        self.bearer_token = token
        self.allowed_origins = frozenset(allowed_origins)
        self._request_slots = threading.BoundedSemaphore(8)

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
    token = os.environ.get("BLENDER_MCP_BEARER_TOKEN", "")
    renderer = BlenderSceneRenderer(
        os.environ.get("BLENDER_EXECUTABLE", ""),
        os.environ.get("BLENDER_MCP_OUTPUT_DIR", "artifacts"),
        project_root=os.environ.get("RGA_PROJECT_ROOT", REPOSITORY_ROOT),
    )
    origins = tuple(
        item.strip()
        for item in os.environ.get("BLENDER_MCP_ALLOWED_ORIGINS", "").split(",")
        if item.strip()
    )
    host = os.environ.get("BLENDER_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("BLENDER_MCP_PORT", "8788"))
    server = BlenderMCPServer(host, port, renderer, token, origins)
    print(f"RGA Blender MCP listening on {host}:{port}; TLS must terminate at the reverse proxy")
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
