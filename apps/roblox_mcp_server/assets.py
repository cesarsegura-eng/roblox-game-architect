"""Bounded Roblox Open Cloud Model asset creation for reviewed Blender GLBs."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import secrets
import sqlite3
import ssl
import threading
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

ASSET_API_HOST = "apis.roblox.com"
MAX_GLB_BYTES = 19 * 1024 * 1024
MAX_RESPONSE_BYTES = 256_000
_ID = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
_OPERATION_PATH = re.compile(r"operations/([A-Za-z0-9_-]{1,128})\Z", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_APPROVAL = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class RobloxAssetError(RuntimeError):
    """An asset upload failed or its outcome could not be confirmed."""


@dataclass(frozen=True, slots=True)
class RobloxAssetTarget:
    """Fixed server-side Open Cloud asset creator configuration."""

    creator_type: str
    creator_id: str
    api_key: str
    max_glb_bytes: int = MAX_GLB_BYTES
    poll_timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if self.creator_type not in {"userId", "groupId"}:
            raise ValueError("asset creator type must be userId or groupId")
        if not isinstance(self.creator_id, str) or not _ID.fullmatch(self.creator_id):
            raise ValueError("asset creator ID must be a positive decimal ID")
        if (
            not isinstance(self.api_key, str)
            or not 1 <= len(self.api_key) <= 512
            or not self.api_key.isascii()
            or any(ord(char) < 33 or ord(char) > 126 for char in self.api_key)
        ):
            raise ValueError("a Roblox Open Cloud asset API key is required")
        if type(self.max_glb_bytes) is not int or not 1 <= self.max_glb_bytes <= MAX_GLB_BYTES:
            raise ValueError("asset GLB size limit must be between 1 byte and 19 MiB")
        if type(self.poll_timeout_seconds) is not int or not 1 <= self.poll_timeout_seconds <= 300:
            raise ValueError("asset operation timeout must be between 1 and 300 seconds")

    @classmethod
    def from_env(cls) -> RobloxAssetTarget:
        creator_type = os.environ.get("RGA_ROBLOX_ASSET_CREATOR_TYPE", "")
        creator_id = os.environ.get("RGA_ROBLOX_ASSET_CREATOR_ID", "")
        api_key = os.environ.get("ROBLOX_OPEN_CLOUD_ASSET_API_KEY", "")
        if not creator_type or not creator_id or not api_key:
            raise ValueError("Roblox asset creator and server-side API key are required")
        if os.environ.get("RGA_ROBLOX_ASSET_CREATION_CONFIRMED") != (
            "I_ACCEPT_ROBLOX_ASSET_CREATION"
        ):
            raise ValueError("explicit Roblox asset creation confirmation is required")
        try:
            maximum = int(os.environ.get("RGA_ROBLOX_MAX_GLB_BYTES", str(MAX_GLB_BYTES)))
            timeout = int(os.environ.get("RGA_ROBLOX_ASSET_POLL_TIMEOUT_SECONDS", "120"))
        except ValueError as exc:
            raise ValueError("Roblox asset limits must be decimal integers") from exc
        return cls(creator_type, creator_id, api_key, maximum, timeout)


@dataclass(frozen=True, slots=True)
class RobloxAssetReceipt:
    request_id: str
    approval_id: str
    artifact_sha256: str
    asset_id: str
    operation_id: str
    moderation_state: str
    status: str

    def to_mapping(self) -> dict[str, str]:
        return {
            "request_id": self.request_id,
            "approval_id": self.approval_id,
            "artifact_sha256": self.artifact_sha256,
            "asset_id": self.asset_id,
            "operation_id": self.operation_id,
            "moderation_state": self.moderation_state,
            "status": self.status,
        }


class OpenCloudModelAssetUploader:
    """Upload one approved GLB as a new Model; never update assets or places."""

    def __init__(self, target: RobloxAssetTarget, *, poll_interval_seconds: float = 2.0) -> None:
        self.target = target
        self.poll_interval_seconds = max(0.1, min(float(poll_interval_seconds), 5.0))

    def upload_glb(
        self,
        glb: bytes,
        *,
        display_name: str,
        description: str,
        request_id: str,
        approval_id: str,
        approved_sha256: str,
    ) -> RobloxAssetReceipt:
        _validate_glb(glb, self.target.max_glb_bytes)
        digest = hashlib.sha256(glb).hexdigest()
        if not isinstance(approved_sha256, str) or not _DIGEST.fullmatch(approved_sha256):
            raise ValueError("approved SHA-256 must be lowercase hexadecimal")
        if not secrets.compare_digest(digest, approved_sha256):
            raise ValueError("GLB digest does not match the reviewed approval")
        canonical_request = _canonical_uuid(request_id, "request_id")
        canonical_approval = _canonical_uuid(approval_id, "approval_id")
        name = _bounded_text(display_name, "display_name", 80)
        summary = _bounded_text(description, "description", 1000)

        boundary = "rga" + secrets.token_hex(24)
        metadata = json.dumps(
            {
                "assetType": "Model",
                "displayName": name,
                "description": summary,
                "creationContext": {"creator": {self.target.creator_type: self.target.creator_id}},
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        body = _multipart(boundary, metadata, glb)
        created = self._request(
            "POST",
            "/assets/v1/assets",
            body,
            f"multipart/form-data; boundary={boundary}",
        )
        operation_path = created.get("path") if isinstance(created, dict) else None
        match = (
            _OPERATION_PATH.fullmatch(operation_path) if isinstance(operation_path, str) else None
        )
        if match is None:
            raise RobloxAssetError("Open Cloud returned an invalid asset operation path")
        operation_id = match.group(1)
        deadline = time.monotonic() + self.target.poll_timeout_seconds
        operation: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            value = self._request("GET", "/assets/v1/operations/" + operation_id)
            if not isinstance(value, dict) or value.get("path") != operation_path:
                raise RobloxAssetError("Open Cloud returned an invalid asset operation")
            if value.get("done") is True:
                operation = value
                break
            if value.get("done") not in {False, None}:
                raise RobloxAssetError("Open Cloud returned an invalid operation state")
            time.sleep(self.poll_interval_seconds)
        if operation is None:
            raise RobloxAssetError("asset operation outcome is uncertain; do not resubmit")
        if "error" in operation:
            raise RobloxAssetError("Roblox rejected or failed the model asset upload")
        asset = operation.get("response")
        asset_id = asset.get("assetId") if isinstance(asset, dict) else None
        asset_type = asset.get("assetType") if isinstance(asset, dict) else None
        if (
            not isinstance(asset_id, str)
            or not _ID.fullmatch(asset_id)
            or asset_type not in ("ASSET_TYPE_MODEL", "Model")
        ):
            raise RobloxAssetError("Open Cloud returned an incomplete Model asset receipt")
        state, status = _moderation(asset)
        return RobloxAssetReceipt(
            canonical_request, canonical_approval, digest, asset_id, operation_id, state, status
        )

    def check_moderation(self, receipt: RobloxAssetReceipt) -> RobloxAssetReceipt:
        """Read the first revision of a Model created by this service."""
        if not _ID.fullmatch(receipt.asset_id):
            raise RobloxAssetError("Invalid Model asset ID in the upload receipt")
        asset = self._request("GET", "/assets/v1/assets/" + receipt.asset_id)
        if (
            not isinstance(asset, dict)
            or asset.get("assetId") != receipt.asset_id
            or asset.get("assetType") not in ("Model", "ASSET_TYPE_MODEL")
            or asset.get("revisionId") != "1"
        ):
            raise RobloxAssetError("Model metadata does not match the original upload")
        context = asset.get("creationContext")
        creator = context.get("creator") if isinstance(context, dict) else None
        if (
            not isinstance(creator, dict)
            or str(creator.get(self.target.creator_type)) != self.target.creator_id
        ):
            raise RobloxAssetError("Model creator differs from the configured upload target")
        state, status = _moderation(asset)
        return replace(receipt, moderation_state=state, status=status)

    def _request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> object:
        if not path.startswith("/assets/v1/") or ".." in path:
            raise RobloxAssetError("Open Cloud asset request path is invalid")
        connection = http.client.HTTPSConnection(
            ASSET_API_HOST, timeout=20, context=ssl.create_default_context()
        )
        try:
            headers = {"x-api-key": self.target.api_key, "Accept": "application/json"}
            if content_type:
                headers["Content-Type"] = content_type
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if response.status not in {200, 201} or len(raw) > MAX_RESPONSE_BYTES:
                raise RobloxAssetError("Roblox Open Cloud asset request failed")
            return json.loads(raw, object_pairs_hook=_unique_pairs)
        except RobloxAssetError:
            raise
        except (OSError, http.client.HTTPException, ValueError, UnicodeError) as exc:
            raise RobloxAssetError("Roblox Open Cloud asset request failed") from exc
        finally:
            connection.close()


class AssetUploadLedger:
    """Durable request idempotency; ambiguous writes are never resubmitted."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS asset_uploads ("
                "request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL, "
                "receipt_json TEXT, error TEXT)"
            )

    def run(
        self, uploader: OpenCloudModelAssetUploader, glb: bytes, **kwargs: str
    ) -> RobloxAssetReceipt:
        required = {"request_id", "approval_id", "approved_sha256", "display_name", "description"}
        if set(kwargs) != required:
            raise ValueError("asset upload arguments are incomplete")
        _validate_glb(glb, uploader.target.max_glb_bytes)
        request_id = _canonical_uuid(kwargs["request_id"], "request_id")
        approval_id = _canonical_uuid(kwargs["approval_id"], "approval_id")
        actual_sha = hashlib.sha256(glb).hexdigest()
        approved_sha = kwargs["approved_sha256"]
        if not _DIGEST.fullmatch(approved_sha) or not secrets.compare_digest(
            actual_sha, approved_sha
        ):
            raise ValueError("GLB digest does not match the reviewed approval")
        name = _bounded_text(kwargs["display_name"], "display_name", 80)
        description = _bounded_text(kwargs["description"], "description", 1000)
        digest = hashlib.sha256(
            json.dumps(
                [actual_sha, approval_id, name, description],
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
        ).hexdigest()
        with self._lock, sqlite3.connect(self.path, timeout=10) as db:
            db.execute("PRAGMA synchronous=FULL")
            row = db.execute(
                "SELECT digest,state,receipt_json FROM asset_uploads WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if row:
                if row[0] != digest:
                    raise ValueError("request_id was already used for different asset content")
                if row[1] == "complete" and isinstance(row[2], str):
                    return RobloxAssetReceipt(**json.loads(row[2]))
                raise RobloxAssetError("previous upload is uncertain; it will not be resubmitted")
            db.execute(
                "INSERT INTO asset_uploads(request_id,digest,state) VALUES(?,?,'pending')",
                (request_id, digest),
            )
        try:
            receipt = uploader.upload_glb(
                glb,
                request_id=request_id,
                approval_id=approval_id,
                approved_sha256=approved_sha,
                display_name=name,
                description=description,
            )
        except Exception as exc:
            with self._lock, sqlite3.connect(self.path, timeout=10) as db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute(
                    "UPDATE asset_uploads SET state='uncertain',error=? WHERE request_id=?",
                    (type(exc).__name__, request_id),
                )
            raise
        with self._lock, sqlite3.connect(self.path, timeout=10) as db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute(
                "UPDATE asset_uploads SET state='complete',receipt_json=? WHERE request_id=?",
                (json.dumps(receipt.to_mapping(), separators=(",", ":")), request_id),
            )
        return receipt

    def check_moderation(
        self, uploader: OpenCloudModelAssetUploader, request_id: str
    ) -> RobloxAssetReceipt:
        request_id = _canonical_uuid(request_id, "request_id")
        query = "SELECT receipt_json FROM asset_uploads WHERE request_id=? AND state='complete'"
        with sqlite3.connect(self.path, timeout=10) as db:
            row = db.execute(query, (request_id,)).fetchone()
        if row is None:
            raise RobloxAssetError("No completed Model upload for this request")
        stored = RobloxAssetReceipt(**json.loads(row[0]))
        if stored.status != "moderation_pending":
            return stored
        refreshed = uploader.check_moderation(stored)
        # Another process can finish moderation while Open Cloud answers this GET.
        # Compare the original JSON so a slower response cannot undo its decision.
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute(
                "UPDATE asset_uploads SET receipt_json=? "
                "WHERE request_id=? AND state='complete' AND receipt_json=?",
                (json.dumps(refreshed.to_mapping(), separators=(",", ":")), request_id, row[0]),
            )
            latest = db.execute(query, (request_id,)).fetchone()
        return RobloxAssetReceipt(**json.loads(latest[0]))

    def is_approved_model(self, asset_id: str) -> bool:
        """Accept only assets with an approved receipt from this uploader ledger."""
        if not isinstance(asset_id, str) or not _ID.fullmatch(asset_id):
            return False
        with self._lock, sqlite3.connect(self.path, timeout=10) as db:
            rows = db.execute(
                "SELECT receipt_json FROM asset_uploads "
                "WHERE state='complete' AND receipt_json IS NOT NULL"
            ).fetchall()
        for (receipt_json,) in rows:
            try:
                receipt = json.loads(receipt_json)
            except (TypeError, ValueError):
                continue
            if (
                isinstance(receipt, dict)
                and receipt.get("asset_id") == asset_id
                and receipt.get("status") == "approved"
            ):
                return True
        return False


def _moderation(asset: dict[str, Any]) -> tuple[str, str]:
    moderation = asset.get("moderationResult")
    state = moderation.get("moderationState") if isinstance(moderation, dict) else None
    if state is None:
        return "MODERATION_STATE_UNKNOWN", "moderation_pending"
    if not isinstance(state, str):
        raise RobloxAssetError("Invalid Model moderation state")
    if state in ("Approved", "Rejected", "Reviewing"):
        state = "MODERATION_STATE_" + state.upper()
    if not re.fullmatch(r"MODERATION_STATE_[A-Z_]{1,48}", state, re.ASCII):
        raise RobloxAssetError("Invalid Model moderation state")
    if state == "MODERATION_STATE_APPROVED":
        return state, "approved"
    if state in ("MODERATION_STATE_REJECTED", "MODERATION_STATE_FAILED"):
        return state, "rejected"
    return state, "moderation_pending"


def _multipart(boundary: str, metadata: bytes, glb: bytes) -> bytes:
    marker = boundary.encode("ascii")
    return (
        b"--" + marker + b"\r\n"
        b'Content-Disposition: form-data; name="request"\r\n'
        b"Content-Type: application/json\r\n\r\n" + metadata + b"\r\n--" + marker + b"\r\n"
        b'Content-Disposition: form-data; name="fileContent"; filename="scene.glb"\r\n'
        b"Content-Type: model/gltf-binary\r\n\r\n" + glb + b"\r\n--" + marker + b"--\r\n"
    )


def _validate_glb(glb: object, maximum: int) -> None:
    if not isinstance(glb, bytes) or not 20 <= len(glb) <= maximum:
        raise ValueError("GLB artifact is empty or exceeds the configured size limit")
    if glb[:4] != b"glTF" or int.from_bytes(glb[4:8], "little") != 2:
        raise ValueError("artifact is not a binary GLB 2.0 file")
    if int.from_bytes(glb[8:12], "little") != len(glb):
        raise ValueError("GLB header length does not match the artifact")
    offset = 12
    chunk_types: list[int] = []
    document: object = None
    while offset < len(glb):
        if len(glb) - offset < 8:
            raise ValueError("GLB contains a truncated chunk header")
        length = int.from_bytes(glb[offset : offset + 4], "little")
        kind = int.from_bytes(glb[offset + 4 : offset + 8], "little")
        offset += 8
        if length % 4 or length > len(glb) - offset:
            raise ValueError("GLB contains an invalid chunk length")
        chunk_types.append(kind)
        if kind == 0x4E4F534A and len(chunk_types) == 1:
            try:
                document = json.loads(
                    glb[offset : offset + length].decode("utf-8").rstrip(" \t\r\n\0"),
                    object_pairs_hook=_unique_pairs,
                )
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise ValueError("GLB JSON chunk is invalid") from exc
        elif kind != 0x004E4942 or len(chunk_types) != 2:
            raise ValueError("GLB contains an unsupported chunk layout")
        offset += length
    if chunk_types not in ([0x4E4F534A], [0x4E4F534A, 0x004E4942]):
        raise ValueError("GLB must contain a JSON chunk and at most one BIN chunk")
    asset = document.get("asset") if isinstance(document, dict) else None
    if not isinstance(asset, dict) or asset.get("version") != "2.0":
        raise ValueError("GLB does not contain a glTF 2.0 asset document")
    meshes = document.get("meshes")
    if (
        not isinstance(meshes, list)
        or not meshes
        or any(
            not isinstance(mesh, dict)
            or not isinstance(mesh.get("primitives"), list)
            or not mesh["primitives"]
            for mesh in meshes
        )
    ):
        raise ValueError("GLB does not contain any mesh primitives")

    pending: list[tuple[object, int]] = [(document, 0)]
    visited = 0
    while pending:
        value, depth = pending.pop()
        visited += 1
        if visited > 200_000 or depth > 64:
            raise ValueError("GLB JSON exceeds structural limits")
        if isinstance(value, dict):
            if "uri" in value:
                raise ValueError("GLB external resource URIs are not allowed")
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)


def _canonical_uuid(value: str, label: str) -> str:
    try:
        canonical = str(uuid.UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} must be a UUID") from exc
    if canonical != value.lower():
        raise ValueError(f"{label} must use canonical UUID syntax")
    return canonical


def _bounded_text(value: object, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{label} must be non-empty text of at most {maximum} characters")
    return value.strip()


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result
