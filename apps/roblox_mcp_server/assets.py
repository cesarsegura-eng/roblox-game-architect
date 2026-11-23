"""Bounded Roblox Open Cloud Model asset creation for reviewed Blender GLBs."""

from __future__ import annotations

import hashlib
import http.client
import io
import json
import math
import os
import re
import secrets
import sqlite3
import ssl
import struct
import threading
import time
import uuid
import warnings
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from core.asset_limits import ROBLOX_MODEL_UPLOAD_MAX_BYTES

ASSET_API_HOST = "apis.roblox.com"
MAX_GLB_BYTES = ROBLOX_MODEL_UPLOAD_MAX_BYTES
MAX_ROBLOX_TRIANGLES_PER_MESH = 20_000
MAX_ROBLOX_VERTICES_PER_MESH = MAX_ROBLOX_TRIANGLES_PER_MESH * 3
MAX_GLTF_ANIMATION_ELEMENTS = 100_000
MAX_GLTF_VALIDATION_ELEMENTS = 1_000_000
MAX_GLTF_COLLECTION_ITEMS = 16_384
MAX_GLTF_IMAGES = 256
MAX_ROBLOX_TEXTURE_DIMENSION = 4_096
MAX_GLTF_TOTAL_TEXTURE_PIXELS = 64_000_000
MAX_RESPONSE_BYTES = 256_000
_ID = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
_OPERATION_PATH = re.compile(r"operations/([A-Za-z0-9_-]{1,128})\Z", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_APPROVAL = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_IMAGE_DECODE_LOCK = threading.Lock()


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


@dataclass(frozen=True, slots=True)
class _AccessorLayout:
    base_offset: int | None
    stride: int
    count: int
    component_type: int
    element_size: int
    sparse_indices_offset: int | None = None
    sparse_index_size: int = 0
    sparse_values_offset: int | None = None
    sparse_count: int = 0


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


def _image_dimensions(data: bytes, mime_type: object) -> tuple[int, int]:
    if mime_type == "image/png":
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("GLB PNG texture has an invalid image header")
        if int.from_bytes(data[8:12], "big") != 13 or data[12:16] != b"IHDR":
            raise ValueError("GLB PNG texture has an invalid IHDR chunk")
        dimensions = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        offset = 8
        chunk_index = 0
        has_image_data = False
        has_image_end = False
        while offset + 12 <= len(data):
            chunk_length = int.from_bytes(data[offset : offset + 4], "big")
            chunk_type = data[offset + 4 : offset + 8]
            chunk_end = offset + 12 + chunk_length
            if chunk_end > len(data):
                raise ValueError("GLB PNG texture has a truncated chunk")
            payload = data[offset + 8 : offset + 8 + chunk_length]
            expected_crc = int.from_bytes(data[offset + 8 + chunk_length : chunk_end], "big")
            if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != expected_crc:
                raise ValueError("GLB PNG texture has an invalid chunk checksum")
            if chunk_index == 0 and chunk_type != b"IHDR":
                raise ValueError("GLB PNG texture must start with IHDR")
            if chunk_type == b"IHDR" and chunk_index != 0:
                raise ValueError("GLB PNG texture contains a duplicate IHDR")
            if chunk_type == b"IDAT":
                has_image_data = True
            offset = chunk_end
            chunk_index += 1
            if chunk_type == b"IEND":
                has_image_end = chunk_length == 0
                break
        if (
            not has_image_data
            or not has_image_end
            or offset != len(data)
            or dimensions[0] < 1
            or dimensions[1] < 1
        ):
            raise ValueError("GLB PNG texture is incomplete or has invalid dimensions")
        return dimensions
    if mime_type == "image/jpeg":
        if not data.startswith(b"\xff\xd8"):
            raise ValueError("GLB JPEG texture has an invalid image header")
        offset = 2
        width: int | None = None
        height: int | None = None
        saw_scan = False
        in_scan = False
        scan_data_start = 0
        while offset < len(data):
            if in_scan:
                while offset < len(data):
                    if data[offset] != 0xFF:
                        offset += 1
                        continue
                    marker_start = offset
                    offset += 1
                    while offset < len(data) and data[offset] == 0xFF:
                        offset += 1
                    if offset >= len(data):
                        break
                    marker = data[offset]
                    offset += 1
                    if marker == 0x00 or 0xD0 <= marker <= 0xD7:
                        continue
                    if marker_start == scan_data_start:
                        raise ValueError("GLB JPEG texture has an empty image scan")
                    in_scan = False
                    offset = marker_start
                    break
                if in_scan:
                    break
            if data[offset] != 0xFF:
                raise ValueError("GLB JPEG texture has an invalid marker")
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                raise ValueError("GLB JPEG texture ends inside a marker")
            marker = data[offset]
            offset += 1
            if marker == 0xD9:
                if width is None or height is None or not saw_scan or offset != len(data):
                    raise ValueError("GLB JPEG texture is incomplete")
                return width, height
            if marker == 0xD8:
                raise ValueError("GLB JPEG texture contains a nested image header")
            if marker == 0x01 or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                raise ValueError("GLB JPEG texture has a truncated segment header")
            segment_length = int.from_bytes(data[offset : offset + 2], "big")
            if segment_length < 2 or offset + segment_length > len(data):
                raise ValueError("GLB JPEG texture has an invalid segment length")
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                if width is not None or segment_length < 11:
                    raise ValueError("GLB JPEG texture has a truncated frame header")
                height = int.from_bytes(data[offset + 3 : offset + 5], "big")
                width = int.from_bytes(data[offset + 5 : offset + 7], "big")
                components = data[offset + 7]
                if (
                    width < 1
                    or height < 1
                    or components < 1
                    or segment_length != 8 + 3 * components
                ):
                    raise ValueError("GLB JPEG texture has invalid frame dimensions")
            if marker == 0xDA:
                components = data[offset + 2] if segment_length >= 3 else 0
                if width is None or components < 1 or segment_length != 6 + 2 * components:
                    raise ValueError("GLB JPEG texture has an invalid scan header")
                saw_scan = True
                in_scan = True
                scan_data_start = offset + segment_length
            offset += segment_length
        raise ValueError("GLB JPEG texture has no complete image scan")
    raise ValueError("GLB texture MIME type must be image/png or image/jpeg")


def _decode_embedded_image(data: bytes, mime_type: str, dimensions: tuple[int, int]) -> None:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ValueError("the remote asset service requires its Pillow decoder extra") from exc
    expected_format = {"image/png": "PNG", "image/jpeg": "JPEG"}.get(mime_type)
    if expected_format is None:
        raise ValueError("GLB texture MIME type must be image/png or image/jpeg")
    try:
        with _IMAGE_DECODE_LOCK, warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data), formats=[expected_format]) as decoded:
                if decoded.format != expected_format or decoded.size != dimensions:
                    raise ValueError("GLB texture decoded format or dimensions do not match")
                decoded.load()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        ValueError,
    ) as exc:
        raise ValueError("GLB texture pixels could not be decoded safely") from exc


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"GLB JSON contains unsupported numeric constant {value}")


def _parse_finite_json_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("GLB JSON contains a non-finite number")
    return result


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
    binary_chunk: bytes | None = None
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
                    parse_float=_parse_finite_json_float,
                    parse_constant=_reject_json_constant,
                )
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise ValueError("GLB JSON chunk is invalid") from exc
        elif kind == 0x004E4942 and len(chunk_types) == 2:
            binary_chunk = glb[offset : offset + length]
        elif kind != 0x004E4942 or len(chunk_types) != 2:
            raise ValueError("GLB contains an unsupported chunk layout")
        offset += length
    if chunk_types not in ([0x4E4F534A], [0x4E4F534A, 0x004E4942]):
        raise ValueError("GLB must contain a JSON chunk and at most one BIN chunk")
    asset = document.get("asset") if isinstance(document, dict) else None
    if not isinstance(asset, dict) or asset.get("version") != "2.0":
        raise ValueError("GLB does not contain a glTF 2.0 asset document")
    extensions_used = document.get("extensionsUsed", [])
    extensions_required = document.get("extensionsRequired", [])
    if (
        not isinstance(extensions_used, list)
        or not isinstance(extensions_required, list)
        or any(
            not isinstance(name, str) or not name
            for name in (*extensions_used, *extensions_required)
        )
        or len(set(extensions_used)) != len(extensions_used)
        or len(set(extensions_required)) != len(extensions_required)
        or not set(extensions_required).issubset(extensions_used)
    ):
        raise ValueError("GLB extension declarations are invalid")
    if extensions_used or extensions_required:
        raise ValueError("GLB uses extensions that the asset preflight does not inspect")
    meshes = document.get("meshes")
    if (
        not isinstance(meshes, list)
        or not meshes
        or len(meshes) > MAX_GLTF_COLLECTION_ITEMS
        or any(
            not isinstance(mesh, dict)
            or not isinstance(mesh.get("primitives"), list)
            or not mesh["primitives"]
            or len(mesh["primitives"]) > MAX_GLTF_COLLECTION_ITEMS
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
            if "extensions" in value:
                extensions = value["extensions"]
                if not isinstance(extensions, dict):
                    raise ValueError("GLB extension declarations are invalid")
                if extensions:
                    raise ValueError(
                        "GLB uses extensions that the asset preflight does not inspect"
                    )
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)

    accessors = document.get("accessors")
    buffer_views = document.get("bufferViews")
    buffers = document.get("buffers")
    if not isinstance(accessors, list) or not isinstance(buffer_views, list):
        raise ValueError("GLB mesh accessors are missing")
    if len(accessors) > MAX_GLTF_COLLECTION_ITEMS or len(buffer_views) > MAX_GLTF_COLLECTION_ITEMS:
        raise ValueError("GLB accessor or buffer view count exceeds structural limits")
    if (
        not isinstance(buffers, list)
        or len(buffers) != 1
        or not isinstance(buffers[0], dict)
        or type(buffers[0].get("byteLength")) is not int
        or buffers[0]["byteLength"] < 1
        or binary_chunk is None
        or not buffers[0]["byteLength"] <= len(binary_chunk) <= buffers[0]["byteLength"] + 3
    ):
        raise ValueError("GLB must contain one valid embedded binary buffer")

    images = document.get("images", [])
    if not isinstance(images, list):
        raise ValueError("GLB images are invalid")
    if len(images) > MAX_GLTF_IMAGES:
        raise ValueError("GLB image count exceeds structural limits")
    total_texture_pixels = 0
    image_sources: dict[tuple[int, str], tuple[bytes, tuple[int, int]]] = {}
    for image in images:
        if not isinstance(image, dict):
            raise ValueError("GLB image is invalid")
        view_index = image.get("bufferView")
        mime_type = image.get("mimeType")
        if type(view_index) is not int or not 0 <= view_index < len(buffer_views):
            raise ValueError("GLB image must reference an embedded buffer view")
        if not isinstance(mime_type, str):
            raise ValueError("GLB texture MIME type must be image/png or image/jpeg")
        view = buffer_views[view_index]
        if (
            not isinstance(view, dict)
            or type(view.get("buffer")) is not int
            or view["buffer"] != 0
            or type(view.get("byteOffset", 0)) is not int
            or type(view.get("byteLength")) is not int
            or view.get("byteOffset", 0) < 0
            or view["byteLength"] < 1
            or view.get("byteOffset", 0) + view["byteLength"] > buffers[0]["byteLength"]
            or "byteStride" in view
            or "target" in view
        ):
            raise ValueError("GLB image buffer view is invalid")
        source_key = (view_index, mime_type)
        source = image_sources.get(source_key)
        if source is None:
            image_bytes = binary_chunk[
                view.get("byteOffset", 0) : view.get("byteOffset", 0) + view["byteLength"]
            ]
            dimensions = _image_dimensions(image_bytes, mime_type)
            image_sources[source_key] = (image_bytes, dimensions)
        else:
            image_bytes, dimensions = source
        width, height = dimensions
        if (
            not 1 <= width <= MAX_ROBLOX_TEXTURE_DIMENSION
            or not 1 <= height <= MAX_ROBLOX_TEXTURE_DIMENSION
        ):
            raise ValueError("GLB texture exceeds Roblox's 4096x4096 texture limit")
        total_texture_pixels += width * height
        if total_texture_pixels > MAX_GLTF_TOTAL_TEXTURE_PIXELS:
            raise ValueError("GLB textures exceed the total pixel budget")
    textures = document.get("textures", [])
    samplers = document.get("samplers", [])
    materials = document.get("materials", [])
    if (
        not isinstance(textures, list)
        or not isinstance(samplers, list)
        or not isinstance(materials, list)
    ):
        raise ValueError("GLB textures, samplers, or materials are invalid")
    if any(len(items) > MAX_GLTF_COLLECTION_ITEMS for items in (textures, samplers, materials)):
        raise ValueError("GLB material or texture count exceeds structural limits")
    for texture in textures:
        if not isinstance(texture, dict):
            raise ValueError("GLB texture is invalid")
        texture_source = texture.get("source")
        if type(texture_source) is not int or not 0 <= texture_source < len(images):
            raise ValueError("GLB texture references a missing embedded image")
        sampler_index = texture.get("sampler")
        if sampler_index is not None and (
            type(sampler_index) is not int or not 0 <= sampler_index < len(samplers)
        ):
            raise ValueError("GLB texture references an invalid sampler")

    for material in materials:
        if not isinstance(material, dict):
            raise ValueError("GLB material is invalid")
        pending_materials = [material]
        while pending_materials:
            material_value = pending_materials.pop()
            if isinstance(material_value, dict):
                for key, value in material_value.items():
                    if isinstance(key, str) and key.endswith("Texture"):
                        if not isinstance(value, dict):
                            raise ValueError("GLB material texture reference is invalid")
                        texture_index = value.get("index")
                        if type(texture_index) is not int or not 0 <= texture_index < len(textures):
                            raise ValueError("GLB material references a missing texture")
                    if isinstance(value, (dict, list)):
                        pending_materials.append(value)
            elif isinstance(material_value, list):
                pending_materials.extend(
                    value for value in material_value if isinstance(value, (dict, list))
                )

    for (view_index, mime_type), (image_bytes, dimensions) in image_sources.items():
        try:
            _decode_embedded_image(image_bytes, mime_type, dimensions)
        except ValueError as exc:
            raise ValueError(f"GLB image {view_index} failed full pixel decoding") from exc

    component_sizes = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}

    def accessor_data(accessor: object, *, vertex_attribute: bool) -> _AccessorLayout:
        if not isinstance(accessor, dict):
            raise ValueError("GLB mesh accessor is invalid")
        component_type = accessor.get("componentType")
        component_size = component_sizes.get(component_type)
        component_count = {
            "SCALAR": 1,
            "VEC2": 2,
            "VEC3": 3,
            "VEC4": 4,
            "MAT4": 16,
        }.get(accessor.get("type"))
        count = accessor.get("count")
        view_index = accessor.get("bufferView")
        byte_offset = accessor.get("byteOffset", 0)
        if (
            component_size is None
            or component_count is None
            or type(count) is not int
            or count < 1
            or type(byte_offset) is not int
            or byte_offset < 0
        ):
            raise ValueError("GLB mesh accessor is missing valid embedded data")
        if vertex_attribute and count > MAX_ROBLOX_VERTICES_PER_MESH:
            raise ValueError("GLB mesh accessor exceeds the per-mesh vertex limit")
        if not vertex_attribute and count > MAX_GLTF_ANIMATION_ELEMENTS:
            raise ValueError("GLB accessor exceeds the animation element limit")
        element_size = component_size * component_count
        base_offset: int | None = None
        stride = element_size
        if view_index is not None:
            if type(view_index) is not int or not 0 <= view_index < len(buffer_views):
                raise ValueError("GLB mesh accessor references an invalid buffer view")
            view = buffer_views[view_index]
            if (
                not isinstance(view, dict)
                or type(view.get("buffer")) is not int
                or view["buffer"] != 0
                or type(view.get("byteLength")) is not int
                or view["byteLength"] < 1
            ):
                raise ValueError("GLB mesh buffer view is invalid")
            view_offset = view.get("byteOffset", 0)
            stride = view.get("byteStride", element_size)
            has_stride = "byteStride" in view
            if (
                type(view_offset) is not int
                or view_offset < 0
                or type(stride) is not int
                or stride < element_size
                or (has_stride and (not vertex_attribute or not 4 <= stride <= 252 or stride % 4))
                or view_offset % component_size != 0
                or byte_offset % component_size != 0
                or (view_offset + byte_offset) % component_size != 0
                or view_offset + view["byteLength"] > buffers[0]["byteLength"]
                or byte_offset + (count - 1) * stride + element_size > view["byteLength"]
                or view_offset + byte_offset + (count - 1) * stride + element_size
                > len(binary_chunk)
                or (vertex_attribute and byte_offset % 4 != 0)
            ):
                raise ValueError("GLB mesh accessor exceeds or misaligns its buffer view")
            base_offset = view_offset + byte_offset
        elif "sparse" not in accessor or byte_offset != 0:
            raise ValueError("GLB mesh accessor is missing valid embedded data")

        sparse = accessor.get("sparse")
        layout = _AccessorLayout(base_offset, stride, count, component_type, element_size)
        if sparse is None:
            if base_offset is None:
                raise ValueError("GLB mesh accessor is missing valid embedded data")
            return layout
        if not isinstance(sparse, dict):
            raise ValueError("GLB sparse accessor is invalid")
        sparse_count = sparse.get("count")
        indices = sparse.get("indices")
        values = sparse.get("values")
        if (
            type(sparse_count) is not int
            or not 1 <= sparse_count <= count
            or not isinstance(indices, dict)
            or not isinstance(values, dict)
        ):
            raise ValueError("GLB sparse accessor is invalid")

        sparse_index_component = indices.get("componentType")
        sparse_index_size = {5121: 1, 5123: 2, 5125: 4}.get(sparse_index_component)
        index_view_index = indices.get("bufferView")
        index_byte_offset = indices.get("byteOffset", 0)
        value_view_index = values.get("bufferView")
        value_byte_offset = values.get("byteOffset", 0)
        if (
            sparse_index_size is None
            or type(index_view_index) is not int
            or not 0 <= index_view_index < len(buffer_views)
            or type(index_byte_offset) is not int
            or index_byte_offset < 0
            or type(value_view_index) is not int
            or not 0 <= value_view_index < len(buffer_views)
            or type(value_byte_offset) is not int
            or value_byte_offset < 0
        ):
            raise ValueError("GLB sparse accessor has invalid buffer references")
        index_view = buffer_views[index_view_index]
        value_view = buffer_views[value_view_index]
        if (
            not isinstance(index_view, dict)
            or type(index_view.get("buffer")) is not int
            or index_view["buffer"] != 0
            or type(index_view.get("byteLength")) is not int
            or "byteStride" in index_view
            or "target" in index_view
            or not isinstance(value_view, dict)
            or type(value_view.get("buffer")) is not int
            or value_view["buffer"] != 0
            or type(value_view.get("byteLength")) is not int
            or "byteStride" in value_view
            or "target" in value_view
        ):
            raise ValueError("GLB sparse accessor buffer view is invalid")
        index_view_offset = index_view.get("byteOffset", 0)
        value_view_offset = value_view.get("byteOffset", 0)
        if (
            type(index_view_offset) is not int
            or index_view_offset < 0
            or type(value_view_offset) is not int
            or value_view_offset < 0
            or index_byte_offset % sparse_index_size != 0
            or index_view_offset % sparse_index_size != 0
            or value_byte_offset % component_size != 0
            or value_view_offset % component_size != 0
            or index_byte_offset + sparse_count * sparse_index_size > index_view["byteLength"]
            or value_byte_offset + sparse_count * element_size > value_view["byteLength"]
            or index_view_offset + index_view["byteLength"] > buffers[0]["byteLength"]
            or value_view_offset + value_view["byteLength"] > buffers[0]["byteLength"]
            or index_view_offset + index_byte_offset + sparse_count * sparse_index_size
            > len(binary_chunk)
            or value_view_offset + value_byte_offset + sparse_count * element_size
            > len(binary_chunk)
        ):
            raise ValueError("GLB sparse accessor exceeds or misaligns its buffer views")
        sparse_indices_offset = index_view_offset + index_byte_offset
        sparse_values_offset = value_view_offset + value_byte_offset
        index_format = {1: "B", 2: "H", 4: "I"}[sparse_index_size]
        previous_index = -1
        for sparse_index in range(sparse_count):
            item = struct.unpack_from(
                "<" + index_format,
                binary_chunk,
                sparse_indices_offset + sparse_index * sparse_index_size,
            )[0]
            if item <= previous_index or item >= count:
                raise ValueError("GLB sparse indices must be increasing and within the accessor")
            previous_index = item
        return _AccessorLayout(
            base_offset,
            stride,
            count,
            component_type,
            element_size,
            sparse_indices_offset,
            sparse_index_size,
            sparse_values_offset,
            sparse_count,
        )

    def accessor_elements(layout: _AccessorLayout) -> Iterator[bytes]:
        nonlocal validated_elements
        validated_elements += layout.count
        if validated_elements > MAX_GLTF_VALIDATION_ELEMENTS:
            raise ValueError("GLB exceeds the total accessor validation work limit")
        if binary_chunk is None:
            raise ValueError("GLB binary data is missing")
        index_format = {1: "B", 2: "H", 4: "I"}.get(layout.sparse_index_size)
        sparse_cursor = 0
        next_sparse_index: int | None = None
        if layout.sparse_count:
            if layout.sparse_indices_offset is None or index_format is None:
                raise ValueError("GLB sparse accessor is missing validated index data")
            next_sparse_index = struct.unpack_from(
                "<" + index_format, binary_chunk, layout.sparse_indices_offset
            )[0]
        for item_index in range(layout.count):
            if next_sparse_index == item_index:
                if layout.sparse_values_offset is None:
                    raise ValueError("GLB sparse accessor is missing validated replacement data")
                start = layout.sparse_values_offset + sparse_cursor * layout.element_size
                element = binary_chunk[start : start + layout.element_size]
                sparse_cursor += 1
                if sparse_cursor < layout.sparse_count:
                    if layout.sparse_indices_offset is None or index_format is None:
                        raise ValueError("GLB sparse accessor is missing validated index data")
                    next_sparse_index = struct.unpack_from(
                        "<" + index_format,
                        binary_chunk,
                        layout.sparse_indices_offset + sparse_cursor * layout.sparse_index_size,
                    )[0]
                else:
                    next_sparse_index = None
            elif layout.base_offset is None:
                element = bytes(layout.element_size)
            else:
                start = layout.base_offset + item_index * layout.stride
                element = binary_chunk[start : start + layout.element_size]
            yield element

    validated_elements = 0
    skins = document.get("skins", [])
    nodes = document.get("nodes", [])
    scenes = document.get("scenes", [])
    cameras = document.get("cameras", [])
    if (
        not isinstance(skins, list)
        or not isinstance(nodes, list)
        or not isinstance(scenes, list)
        or not isinstance(cameras, list)
    ):
        raise ValueError("GLB skins or nodes are invalid")
    if any(len(items) > MAX_GLTF_COLLECTION_ITEMS for items in (skins, nodes, scenes, cameras)):
        raise ValueError("GLB scene graph collection count exceeds structural limits")
    skin_joint_counts: dict[int, int] = {}
    for skin_index, skin in enumerate(skins):
        joints = skin.get("joints") if isinstance(skin, dict) else None
        if (
            not isinstance(joints, list)
            or not joints
            or len(joints) > len(nodes)
            or any(type(joint) is not int or not 0 <= joint < len(nodes) for joint in joints)
            or len(set(joints)) != len(joints)
        ):
            raise ValueError("GLB skin has invalid joint node references")
        skin_joint_counts[skin_index] = len(joints)
        skeleton = skin.get("skeleton")
        if skeleton is not None and (type(skeleton) is not int or not 0 <= skeleton < len(nodes)):
            raise ValueError("GLB skin references an invalid skeleton node")
        inverse_bind_index = skin.get("inverseBindMatrices")
        if inverse_bind_index is None:
            continue
        if type(inverse_bind_index) is not int or not 0 <= inverse_bind_index < len(accessors):
            raise ValueError("GLB skin references invalid inverse bind matrices")
        inverse_bind_accessor = accessors[inverse_bind_index]
        if (
            not isinstance(inverse_bind_accessor, dict)
            or inverse_bind_accessor.get("type") != "MAT4"
            or inverse_bind_accessor.get("componentType") != 5126
            or type(inverse_bind_accessor.get("count")) is not int
            or inverse_bind_accessor["count"] < len(joints)
            or inverse_bind_accessor["count"] > MAX_GLTF_COLLECTION_ITEMS
        ):
            raise ValueError("GLB inverse bind matrix accessor is invalid")
        inverse_bind_layout = accessor_data(inverse_bind_accessor, vertex_attribute=False)
        for matrix_bytes in accessor_elements(inverse_bind_layout):
            matrix = struct.unpack("<16f", matrix_bytes)
            if not all(math.isfinite(component) for component in matrix):
                raise ValueError("GLB inverse bind matrix contains a non-finite value")
            # glTF matrices are column-major; the fourth row is elements 3, 7, 11, and 15.
            if (matrix[3], matrix[7], matrix[11], matrix[15]) != (0.0, 0.0, 0.0, 1.0):
                raise ValueError("GLB inverse bind matrix has an invalid fourth row")

    parent_counts = [0] * len(nodes)
    children_by_node: list[list[int]] = []
    transform_limit = 1_000_000
    transform_shapes = {"matrix": 16, "translation": 3, "rotation": 4, "scale": 3}
    skin_joint_limits: dict[int, list[int]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("GLB node is invalid")
        if "matrix" in node and any(key in node for key in ("translation", "rotation", "scale")):
            raise ValueError("GLB node cannot combine matrix and TRS transforms")
        for key, expected_count in transform_shapes.items():
            if key not in node:
                continue
            values = node[key]
            if (
                not isinstance(values, list)
                or len(values) != expected_count
                or any(
                    type(value) not in {int, float}
                    or not math.isfinite(value)
                    or abs(value) > transform_limit
                    for value in values
                )
            ):
                raise ValueError("GLB node transform is invalid or exceeds coordinate limits")
        if "mesh" in node and (
            type(node["mesh"]) is not int or not 0 <= node["mesh"] < len(meshes)
        ):
            raise ValueError("GLB node references an invalid mesh")
        if "camera" in node and (
            type(node["camera"]) is not int or not 0 <= node["camera"] < len(cameras)
        ):
            raise ValueError("GLB node references an invalid camera")
        children = node.get("children", [])
        if (
            not isinstance(children, list)
            or len(children) > len(nodes)
            or any(type(child) is not int or not 0 <= child < len(nodes) for child in children)
            or len(set(children)) != len(children)
        ):
            raise ValueError("GLB node has invalid child references")
        children_by_node.append(children)
        for child in children:
            parent_counts[child] += 1
            if parent_counts[child] > 1:
                raise ValueError("GLB node hierarchy gives a node multiple parents")
        if "skin" not in node and "mesh" not in node:
            continue
        if "skin" not in node:
            continue
        mesh_index = node.get("mesh")
        skin_index = node.get("skin")
        if (
            type(mesh_index) is not int
            or not 0 <= mesh_index < len(meshes)
            or type(skin_index) is not int
            or not 0 <= skin_index < len(skins)
        ):
            raise ValueError("GLB skinned node has an invalid mesh or skin reference")
        skin = skins[skin_index]
        skin_joint_limits.setdefault(mesh_index, []).append(skin_joint_counts[skin_index])

    has_parent = [parent_count > 0 for parent_count in parent_counts]
    pending_nodes = [index for index, parent_count in enumerate(parent_counts) if parent_count == 0]
    visited_nodes = 0
    while pending_nodes:
        node_index = pending_nodes.pop()
        visited_nodes += 1
        for child in children_by_node[node_index]:
            parent_counts[child] -= 1
            if parent_counts[child] == 0:
                pending_nodes.append(child)
    if visited_nodes != len(nodes):
        raise ValueError("GLB node hierarchy contains a cycle")

    for scene in scenes:
        if not isinstance(scene, dict):
            raise ValueError("GLB scene is invalid")
        roots = scene.get("nodes", [])
        if (
            not isinstance(roots, list)
            or len(roots) > len(nodes)
            or any(type(root) is not int or not 0 <= root < len(nodes) for root in roots)
            or len(set(roots)) != len(roots)
            or any(has_parent[root] for root in roots)
        ):
            raise ValueError("GLB scene has invalid root nodes")
    default_scene = document.get("scene")
    if default_scene is not None and (
        type(default_scene) is not int or not 0 <= default_scene < len(scenes)
    ):
        raise ValueError("GLB default scene reference is invalid")

    mesh_morph_target_counts: list[int] = []
    for mesh_index, mesh in enumerate(meshes):
        mesh_morph_target_count: int | None = None
        for primitive in mesh["primitives"]:
            if not isinstance(primitive, dict):
                raise ValueError("GLB mesh primitive is invalid")
            mode = primitive.get("mode", 4)
            if type(mode) is not int or mode not in {4, 5, 6}:
                raise ValueError("GLB mesh primitive must use triangle geometry")
            material_index = primitive.get("material")
            if material_index is not None and (
                type(material_index) is not int or not 0 <= material_index < len(materials)
            ):
                raise ValueError("GLB mesh primitive references a missing material")
            attributes = primitive.get("attributes")
            if not isinstance(attributes, dict) or not attributes:
                raise ValueError("GLB mesh primitive has invalid vertex attributes")
            position_index = attributes.get("POSITION") if isinstance(attributes, dict) else None
            if type(position_index) is not int or not 0 <= position_index < len(accessors):
                raise ValueError("GLB mesh primitive has no valid POSITION accessor")
            positions = accessors[position_index]
            if (
                not isinstance(positions, dict)
                or positions.get("type") != "VEC3"
                or type(positions.get("count")) is not int
                or positions["count"] < 3
            ):
                raise ValueError("GLB POSITION accessor is invalid")
            position_layout = accessor_data(positions, vertex_attribute=True)
            position_count = position_layout.count
            position_component = position_layout.component_type
            if position_component != 5126 or positions.get("normalized", False) is not False:
                raise ValueError("GLB POSITION accessor must use 32-bit floats")

            indexed_semantics: dict[str, set[int]] = {
                "TEXCOORD": set(),
                "COLOR": set(),
                "JOINTS": set(),
                "WEIGHTS": set(),
            }
            for semantic, accessor_index in attributes.items():
                if not isinstance(semantic, str):
                    raise ValueError("GLB vertex attribute semantic is invalid")
                match = re.fullmatch(r"(TEXCOORD|COLOR|JOINTS|WEIGHTS)_([0-9]+)", semantic)
                if semantic in {"POSITION", "NORMAL", "TANGENT"}:
                    family = semantic
                    set_index = None
                elif match is not None:
                    family, raw_set_index = match.groups()
                    if (raw_set_index != "0" and raw_set_index.startswith("0")) or len(
                        raw_set_index
                    ) > 5:
                        raise ValueError("GLB vertex attribute set index is invalid")
                    if int(raw_set_index) >= MAX_GLTF_COLLECTION_ITEMS:
                        raise ValueError("GLB vertex attribute set index exceeds structural limits")
                    set_index = int(raw_set_index)
                    indexed_semantics[family].add(set_index)
                elif semantic.startswith("_") and len(semantic) > 1:
                    family = "CUSTOM"
                    set_index = None
                else:
                    raise ValueError("GLB mesh contains an unsupported vertex attribute semantic")
                if family == "POSITION":
                    if accessor_index != position_index:
                        raise ValueError("GLB POSITION attribute reference is inconsistent")
                    continue
                if type(accessor_index) is not int or not 0 <= accessor_index < len(accessors):
                    raise ValueError("GLB vertex attribute references an invalid accessor")
                attribute_accessor = accessors[accessor_index]
                if not isinstance(attribute_accessor, dict):
                    raise ValueError("GLB vertex attribute accessor is invalid")
                component_type = attribute_accessor.get("componentType")
                accessor_type = attribute_accessor.get("type")
                normalized = attribute_accessor.get("normalized", False)
                if type(normalized) is not bool:
                    raise ValueError("GLB vertex attribute normalization flag is invalid")
                supported_types = {
                    "NORMAL": ({"VEC3"}, {5120, 5122, 5126}, {False, True}),
                    "TANGENT": ({"VEC4"}, {5120, 5122, 5126}, {False, True}),
                    "TEXCOORD": ({"VEC2"}, {5121, 5123, 5126}, {False, True}),
                    "COLOR": ({"VEC3", "VEC4"}, {5121, 5123, 5126}, {False, True}),
                    "JOINTS": ({"VEC4"}, {5121, 5123}, {False}),
                    "WEIGHTS": ({"VEC4"}, {5121, 5123, 5126}, {False, True}),
                    "CUSTOM": (
                        {"SCALAR", "VEC2", "VEC3", "VEC4"},
                        set(component_sizes),
                        {False, True},
                    ),
                }
                allowed_types, allowed_components, allowed_normalized = supported_types[family]
                if (
                    accessor_type not in allowed_types
                    or component_type not in allowed_components
                    or normalized not in allowed_normalized
                    or (component_type == 5126 and normalized)
                    or (component_type in {5120, 5122} and not normalized)
                    or (
                        family in {"TEXCOORD", "COLOR", "WEIGHTS"}
                        and component_type in {5121, 5123}
                        and not normalized
                    )
                    or (
                        family in {"NORMAL", "TANGENT"}
                        and component_type in {5120, 5122}
                        and not normalized
                    )
                ):
                    raise ValueError(f"GLB {semantic} accessor has an unsupported type")
                attribute_layout = accessor_data(attribute_accessor, vertex_attribute=True)
                if attribute_layout.count != position_count:
                    raise ValueError("GLB vertex attribute counts do not match POSITION")
                if family in {"NORMAL", "TANGENT", "TEXCOORD", "COLOR", "CUSTOM"}:
                    component_format = {
                        5120: "b",
                        5121: "B",
                        5122: "h",
                        5123: "H",
                        5125: "I",
                        5126: "f",
                    }[component_type]
                    component_count = {
                        "SCALAR": 1,
                        "VEC2": 2,
                        "VEC3": 3,
                        "VEC4": 4,
                    }[accessor_type]
                    for attribute_bytes in accessor_elements(attribute_layout):
                        values = struct.unpack(
                            "<" + component_format * component_count, attribute_bytes
                        )
                        if not all(math.isfinite(value) for value in values):
                            raise ValueError(f"GLB {semantic} contains a non-finite value")
            for family, sets in indexed_semantics.items():
                if sets and sorted(sets) != list(range(len(sets))):
                    raise ValueError(f"GLB {family} attribute sets must be contiguous from zero")

            morph_targets = primitive.get("targets", [])
            if (
                not isinstance(morph_targets, list)
                or len(morph_targets) > MAX_GLTF_COLLECTION_ITEMS
            ):
                raise ValueError("GLB primitive morph target list exceeds structural limits")
            if mesh_morph_target_count is None:
                mesh_morph_target_count = len(morph_targets)
            elif len(morph_targets) != mesh_morph_target_count:
                raise ValueError("GLB mesh primitives have inconsistent morph target counts")
            for target in morph_targets:
                if not isinstance(target, dict) or not target:
                    raise ValueError("GLB morph target is invalid")
                for semantic, target_accessor_index in target.items():
                    if semantic not in {"POSITION", "NORMAL", "TANGENT"}:
                        raise ValueError("GLB morph target contains an unsupported attribute")
                    if not isinstance(attributes, dict) or semantic not in attributes:
                        raise ValueError(
                            "GLB morph target attribute is missing from its base primitive"
                        )
                    if type(
                        target_accessor_index
                    ) is not int or not 0 <= target_accessor_index < len(accessors):
                        raise ValueError("GLB morph target references an invalid accessor")
                    target_accessor = accessors[target_accessor_index]
                    if (
                        not isinstance(target_accessor, dict)
                        or target_accessor.get("type") != "VEC3"
                        or target_accessor.get("componentType") != 5126
                        or type(target_accessor.get("count")) is not int
                        or target_accessor["count"] != position_count
                    ):
                        raise ValueError("GLB morph target accessor does not match POSITION")
                    target_layout = accessor_data(target_accessor, vertex_attribute=True)
                    for target_bytes in accessor_elements(target_layout):
                        target_values = struct.unpack("<3f", target_bytes)
                        if not all(math.isfinite(component) for component in target_values):
                            raise ValueError("GLB morph target contains a non-finite value")

            skin_sets: dict[int, dict[str, int]] = {}
            if isinstance(attributes, dict):
                for semantic, accessor_index in attributes.items():
                    match = re.fullmatch(r"(JOINTS|WEIGHTS)_([0-9]+)", semantic)
                    if match is None:
                        continue
                    family, set_index = match.groups()
                    pair = skin_sets.setdefault(int(set_index), {})
                    pair[family] = accessor_index
            if skin_sets:
                limits = skin_joint_limits.get(mesh_index)
                if not limits:
                    raise ValueError("GLB skin attributes are not attached to a skinned node")
                if set(skin_sets[0]) != {"JOINTS", "WEIGHTS"}:
                    raise ValueError("GLB skin attributes must include JOINTS_0 and WEIGHTS_0")
                if sorted(skin_sets) != list(range(len(skin_sets))):
                    raise ValueError("GLB skin attribute sets must be contiguous from zero")
                influence_counts = [0] * position_count
                total_weights = [0.0] * position_count
                for set_index in sorted(skin_sets):
                    pair = skin_sets[set_index]
                    if set(pair) != {"JOINTS", "WEIGHTS"}:
                        raise ValueError("GLB JOINTS and WEIGHTS attributes must be paired")
                    joints_accessor_index = pair["JOINTS"]
                    weights_accessor_index = pair["WEIGHTS"]
                    if (
                        type(joints_accessor_index) is not int
                        or not 0 <= joints_accessor_index < len(accessors)
                        or type(weights_accessor_index) is not int
                        or not 0 <= weights_accessor_index < len(accessors)
                    ):
                        raise ValueError("GLB skin attributes reference invalid accessors")
                    joints_accessor = accessors[joints_accessor_index]
                    weights_accessor = accessors[weights_accessor_index]
                    if (
                        not isinstance(joints_accessor, dict)
                        or joints_accessor.get("type") != "VEC4"
                        or joints_accessor.get("componentType") not in {5121, 5123}
                        or not isinstance(weights_accessor, dict)
                        or weights_accessor.get("type") != "VEC4"
                        or weights_accessor.get("componentType") not in {5121, 5123, 5126}
                        or (
                            weights_accessor.get("componentType") in {5121, 5123}
                            and weights_accessor.get("normalized") is not True
                        )
                    ):
                        raise ValueError("GLB skin accessors have unsupported types")
                    joints_layout = accessor_data(joints_accessor, vertex_attribute=True)
                    weights_layout = accessor_data(weights_accessor, vertex_attribute=True)
                    joints_count = joints_layout.count
                    joints_component = joints_layout.component_type
                    weights_count = weights_layout.count
                    weights_component = weights_layout.component_type
                    if (
                        joints_count != position_count
                        or weights_count != position_count
                        or joints_component not in {5121, 5123}
                        or weights_component not in {5121, 5123, 5126}
                    ):
                        raise ValueError("GLB skin accessor counts do not match POSITION")
                    joints_format = "4B" if joints_component == 5121 else "4H"
                    weights_format = {
                        5121: "4B",
                        5123: "4H",
                        5126: "4f",
                    }[weights_component]
                    for vertex_index, (joint_bytes, weight_bytes) in enumerate(
                        zip(
                            accessor_elements(joints_layout),
                            accessor_elements(weights_layout),
                            strict=True,
                        )
                    ):
                        joint_values = struct.unpack("<" + joints_format, joint_bytes)
                        weight_values = struct.unpack("<" + weights_format, weight_bytes)
                        if weights_component in {5121, 5123}:
                            divisor = 255 if weights_component == 5121 else 65535
                            weight_values = tuple(value / divisor for value in weight_values)
                        if not all(
                            math.isfinite(weight) and weight >= 0 for weight in weight_values
                        ):
                            raise ValueError("GLB skin contains a negative or non-finite weight")
                        influence_counts[vertex_index] += sum(
                            weight > 0 for weight in weight_values
                        )
                        total_weights[vertex_index] += sum(weight_values)
                        if any(
                            joint >= min(limits)
                            for joint, weight in zip(joint_values, weight_values, strict=True)
                            if weight > 0
                        ):
                            raise ValueError("GLB skin joint index exceeds its skin's joint list")
                if any(count > 4 for count in influence_counts):
                    raise ValueError("GLB vertex exceeds Roblox's four-bone influence limit")
                if any(weight_sum <= 0 for weight_sum in total_weights):
                    raise ValueError("GLB skin vertex has no positive bone weights")
            element_count = positions["count"]
            if "indices" in primitive:
                index = primitive["indices"]
                if type(index) is not int or not 0 <= index < len(accessors):
                    raise ValueError("GLB mesh primitive has an invalid index accessor")
                indices = accessors[index]
                if (
                    not isinstance(indices, dict)
                    or indices.get("type") != "SCALAR"
                    or indices.get("componentType") not in {5121, 5123, 5125}
                    or type(indices.get("count")) is not int
                    or indices["count"] < 3
                ):
                    raise ValueError("GLB index accessor is invalid")
                index_layout = accessor_data(indices, vertex_attribute=False)
                index_count = index_layout.count
                index_component = index_layout.component_type
                if index_component not in {5121, 5123, 5125}:
                    raise ValueError("GLB index accessor must use unsigned integers")
                maximum_elements = (
                    MAX_ROBLOX_TRIANGLES_PER_MESH * 3
                    if mode == 4
                    else MAX_ROBLOX_TRIANGLES_PER_MESH + 2
                )
                if index_count > maximum_elements:
                    raise ValueError("GLB mesh exceeds Roblox's 20,000-triangle per-mesh limit")
                index_format = {5121: "B", 5123: "H", 5125: "I"}[index_component]
                for index_bytes in accessor_elements(index_layout):
                    vertex_index = struct.unpack("<" + index_format, index_bytes)[0]
                    if vertex_index >= position_count:
                        raise ValueError("GLB index value exceeds the POSITION accessor")
                element_count = indices["count"]
            elif position_count > (
                MAX_ROBLOX_TRIANGLES_PER_MESH * 3
                if mode == 4
                else MAX_ROBLOX_TRIANGLES_PER_MESH + 2
            ):
                raise ValueError("GLB mesh exceeds Roblox's 20,000-triangle per-mesh limit")
            for position_bytes in accessor_elements(position_layout):
                position = struct.unpack("<3f", position_bytes)
                if not all(math.isfinite(component) for component in position):
                    raise ValueError("GLB POSITION contains a non-finite value")
            if mode == 4:
                if element_count % 3:
                    raise ValueError("GLB triangle primitive has an incomplete face")
                triangle_count = element_count // 3
            else:
                triangle_count = element_count - 2
            if triangle_count > MAX_ROBLOX_TRIANGLES_PER_MESH:
                raise ValueError("GLB mesh exceeds Roblox's 20,000-triangle per-mesh limit")
        mesh_morph_target_counts.append(mesh_morph_target_count or 0)

    for mesh_index, mesh in enumerate(meshes):
        mesh_weights = mesh.get("weights")
        if mesh_weights is not None and (
            not isinstance(mesh_weights, list)
            or len(mesh_weights) != mesh_morph_target_counts[mesh_index]
            or any(
                type(weight) not in {int, float}
                or not math.isfinite(weight)
                or abs(weight) > transform_limit
                for weight in mesh_weights
            )
        ):
            raise ValueError("GLB mesh weights do not match its morph targets")
    for node in nodes:
        if "weights" not in node:
            continue
        mesh_index = node.get("mesh")
        node_weights = node["weights"]
        if (
            type(mesh_index) is not int
            or not 0 <= mesh_index < len(meshes)
            or not isinstance(node_weights, list)
            or len(node_weights) != mesh_morph_target_counts[mesh_index]
            or any(
                type(weight) not in {int, float}
                or not math.isfinite(weight)
                or abs(weight) > transform_limit
                for weight in node_weights
            )
        ):
            raise ValueError("GLB node weights do not match its mesh morph targets")

    animations = document.get("animations", [])
    if not isinstance(animations, list):
        raise ValueError("GLB animations are invalid")
    if len(animations) > MAX_GLTF_COLLECTION_ITEMS:
        raise ValueError("GLB animation count exceeds structural limits")
    for animation in animations:
        if not isinstance(animation, dict):
            raise ValueError("GLB animation is invalid")
        samplers = animation.get("samplers")
        channels = animation.get("channels")
        if (
            not isinstance(samplers, list)
            or not samplers
            or len(samplers) > MAX_GLTF_COLLECTION_ITEMS
            or not isinstance(channels, list)
            or not channels
            or len(channels) > MAX_GLTF_COLLECTION_ITEMS
        ):
            raise ValueError("GLB animation must contain channels and samplers")
        animation_inputs: list[int] = []
        animation_outputs: list[int] = []
        for sampler in samplers:
            if not isinstance(sampler, dict):
                raise ValueError("GLB animation sampler is invalid")
            interpolation = sampler.get("interpolation", "LINEAR")
            input_index = sampler.get("input")
            output_index = sampler.get("output")
            if (
                not isinstance(interpolation, str)
                or interpolation not in {"LINEAR", "STEP", "CUBICSPLINE"}
                or type(input_index) is not int
                or not 0 <= input_index < len(accessors)
                or type(output_index) is not int
                or not 0 <= output_index < len(accessors)
            ):
                raise ValueError("GLB animation sampler has invalid interpolation or accessors")
            input_accessor = accessors[input_index]
            output_accessor = accessors[output_index]
            if (
                not isinstance(input_accessor, dict)
                or input_accessor.get("type") != "SCALAR"
                or input_accessor.get("componentType") != 5126
                or not isinstance(output_accessor, dict)
                or output_accessor.get("componentType") != 5126
                or not isinstance(output_accessor.get("type"), str)
                or output_accessor.get("type") not in {"SCALAR", "VEC3", "VEC4"}
            ):
                raise ValueError("GLB animation sampler accessor types are unsupported")
            input_layout = accessor_data(input_accessor, vertex_attribute=False)
            output_layout = accessor_data(output_accessor, vertex_attribute=False)
            input_count = input_layout.count
            output_count = output_layout.count
            previous_time = -math.inf
            for time_bytes in accessor_elements(input_layout):
                key_time = struct.unpack("<f", time_bytes)[0]
                if not math.isfinite(key_time) or key_time <= previous_time:
                    raise ValueError("GLB animation key times must be finite and increasing")
                previous_time = key_time
            output_components = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[output_accessor["type"]]
            for output_bytes in accessor_elements(output_layout):
                values = struct.unpack("<" + "f" * output_components, output_bytes)
                if not all(math.isfinite(value) for value in values):
                    raise ValueError("GLB animation output contains a non-finite value")
            animation_inputs.append(input_count)
            animation_outputs.append(output_count)

        seen_targets: set[tuple[int, str]] = set()
        for channel in channels:
            if not isinstance(channel, dict):
                raise ValueError("GLB animation channel is invalid")
            sampler_index = channel.get("sampler")
            target = channel.get("target")
            node_index = target.get("node") if isinstance(target, dict) else None
            path = target.get("path") if isinstance(target, dict) else None
            if (
                type(sampler_index) is not int
                or not 0 <= sampler_index < len(samplers)
                or type(node_index) is not int
                or not 0 <= node_index < len(nodes)
                or not isinstance(path, str)
                or path not in {"translation", "rotation", "scale", "weights"}
            ):
                raise ValueError("GLB animation channel has an invalid target or sampler")
            if (node_index, path) in seen_targets:
                raise ValueError("GLB animation repeats a node property target")
            seen_targets.add((node_index, path))
            sampler = samplers[sampler_index]
            if path in {"translation", "rotation", "scale"} and "matrix" in nodes[node_index]:
                raise ValueError("GLB animation cannot target TRS on a matrix node")
            output_accessor = accessors[sampler["output"]]
            key_multiplier = 3 if sampler.get("interpolation", "LINEAR") == "CUBICSPLINE" else 1
            input_count = animation_inputs[sampler_index]
            output_count = animation_outputs[sampler_index]
            expected_type = {"translation": "VEC3", "rotation": "VEC4", "scale": "VEC3"}.get(path)
            if expected_type is not None:
                if (
                    output_accessor["type"] != expected_type
                    or output_count != input_count * key_multiplier
                ):
                    raise ValueError("GLB animation output does not match its target path")
            else:
                target_mesh_index = nodes[node_index].get("mesh")
                if (
                    type(target_mesh_index) is not int
                    or not 0 <= target_mesh_index < len(meshes)
                    or mesh_morph_target_counts[target_mesh_index] < 1
                    or output_accessor["type"] != "SCALAR"
                    or output_count
                    != input_count * mesh_morph_target_counts[target_mesh_index] * key_multiplier
                ):
                    raise ValueError("GLB morph-weight animation output has invalid dimensions")


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
