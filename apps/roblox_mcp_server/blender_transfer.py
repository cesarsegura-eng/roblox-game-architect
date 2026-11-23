"""Fixed-host Blender artifact retrieval and human-confirmed Roblox upload flow."""

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
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .assets import (
    MAX_GLB_BYTES,
    AssetUploadLedger,
    OpenCloudModelAssetUploader,
    RobloxAssetError,
    RobloxAssetReceipt,
    _validate_glb,
)

MAX_ARTIFACT_DOWNLOAD_BYTES = MAX_GLB_BYTES
PREPARED_APPROVAL_SECONDS = 300
_ARTIFACT_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z",
    re.ASCII,
)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class BlenderArtifactError(RuntimeError):
    """The fixed Blender service could not return a valid approved artifact."""


@dataclass(frozen=True, slots=True)
class PreparedModelUpload:
    request_id: str
    approval_id: str
    artifact_id: str
    artifact_sha256: str
    expires_at: int
    display_name: str
    description: str

    @property
    def confirmation_phrase(self) -> str:
        return f"I_APPROVE_ROBLOX_MODEL_UPLOAD_{self.artifact_sha256[:12]}"

    def to_mapping(self) -> dict[str, str | int]:
        return {
            "request_id": self.request_id,
            "approval_id": self.approval_id,
            "artifact_id": self.artifact_id,
            "artifact_sha256": self.artifact_sha256,
            "expires_at": self.expires_at,
            "display_name": self.display_name,
            "description": self.description,
            "confirmation_phrase": self.confirmation_phrase,
        }


class BlenderArtifactSource:
    """Download only UUID-addressed GLBs from one fixed authenticated MCP host."""

    def __init__(self, endpoint: str, bearer_token: str, *, timeout: float = 30.0) -> None:
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/").split("/")[-1] != "mcp"
        ):
            raise ValueError("BLENDER_MCP_URL must be an HTTPS MCP endpoint")
        if (
            not isinstance(bearer_token, str)
            or not 32 <= len(bearer_token) <= 512
            or not bearer_token.isascii()
            or any(ord(char) < 33 or ord(char) > 126 for char in bearer_token)
        ):
            raise ValueError("BLENDER_MCP_BEARER_TOKEN must contain 32-512 printable characters")
        if not 1 <= timeout <= 60:
            raise ValueError("Blender artifact download timeout must be between 1 and 60 seconds")
        self._host = parsed.hostname
        self._port = parsed.port or 443
        self._base_path = parsed.path.rstrip("/")[: -len("/mcp")]
        self._token = bearer_token
        self._timeout = timeout

    @classmethod
    def from_env(cls) -> BlenderArtifactSource:
        if os.environ.get("RGA_ROBLOX_BLENDER_TRANSFER_CONFIRMED") != (
            "I_ACCEPT_ROBLOX_MODEL_TRANSFER"
        ):
            raise ValueError("explicit Blender-to-Roblox model transfer confirmation is required")
        return cls(
            os.environ.get("BLENDER_MCP_URL", ""),
            os.environ.get("BLENDER_MCP_BEARER_TOKEN", ""),
        )

    def fetch(self, artifact_id: str, *, max_bytes: int = MAX_ARTIFACT_DOWNLOAD_BYTES) -> bytes:
        try:
            canonical_id = str(uuid.UUID(artifact_id))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("artifact_id must be a UUID") from exc
        if canonical_id != artifact_id.lower() or not _ARTIFACT_ID.fullmatch(canonical_id):
            raise ValueError("artifact_id must be a canonical UUID")
        if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_ARTIFACT_DOWNLOAD_BYTES:
            raise ValueError("artifact size limit is invalid")
        connection = http.client.HTTPSConnection(
            self._host,
            self._port,
            timeout=self._timeout,
            context=ssl.create_default_context(),
        )
        path = f"{self._base_path}/artifacts/{canonical_id}.glb"
        try:
            connection.request(
                "GET",
                path,
                headers={"Authorization": f"Bearer {self._token}", "Accept": "model/gltf-binary"},
            )
            response = connection.getresponse()
            if response.status != 200 or response.getheader("Content-Type", "").split(";")[0] != (
                "model/gltf-binary"
            ):
                raise BlenderArtifactError("fixed Blender artifact download was rejected")
            length = response.getheader("Content-Length")
            if length is not None and (not length.isdecimal() or int(length) > max_bytes):
                raise BlenderArtifactError("Blender GLB exceeds the configured transfer limit")
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise BlenderArtifactError("Blender GLB exceeds the configured transfer limit")
            _validate_glb(data, max_bytes)
            return data
        except BlenderArtifactError:
            raise
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise BlenderArtifactError("fixed Blender artifact download failed") from exc
        finally:
            connection.close()


class PreparedModelUploadLedger:
    """Durable two-step review ledger; interrupted external writes stay uncertain."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS prepared_model_uploads ("
                "request_id TEXT PRIMARY KEY, approval_id TEXT UNIQUE NOT NULL, "
                "artifact_id TEXT NOT NULL, digest TEXT NOT NULL, expires_at INTEGER NOT NULL, "
                "display_name TEXT NOT NULL, description TEXT NOT NULL, state TEXT NOT NULL, "
                "receipt_json TEXT)"
            )

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

    def prepare(
        self,
        source: BlenderArtifactSource,
        artifact_id: str,
        *,
        max_bytes: int = MAX_ARTIFACT_DOWNLOAD_BYTES,
        now: int | None = None,
    ) -> PreparedModelUpload:
        data = source.fetch(artifact_id, max_bytes=max_bytes)
        digest = hashlib.sha256(data).hexdigest()
        canonical_artifact_id = str(uuid.UUID(artifact_id))
        request_id = str(uuid.uuid4())
        approval_id = str(uuid.uuid4())
        expires_at = (int(time.time()) if now is None else now) + PREPARED_APPROVAL_SECONDS
        # Keep metadata deterministic and avoid accepting caller-controlled URLs or paths.
        display_name = f"RGA Scene {canonical_artifact_id[:8]}"
        description = f"Reviewed Blender artifact {canonical_artifact_id}; SHA-256 {digest}."
        with self._lock, self._connect() as db:
            count = db.execute("SELECT COUNT(*) FROM prepared_model_uploads").fetchone()[0]
            if count >= 10_000:
                db.execute(
                    "DELETE FROM prepared_model_uploads WHERE state IN ('complete','expired')"
                )
                count = db.execute("SELECT COUNT(*) FROM prepared_model_uploads").fetchone()[0]
                if count >= 10_000:
                    raise BlenderArtifactError("prepared upload ledger is full")
            db.execute(
                "INSERT INTO prepared_model_uploads VALUES(?,?,?,?,?,?,?,'prepared',NULL)",
                (
                    request_id,
                    approval_id,
                    canonical_artifact_id,
                    digest,
                    expires_at,
                    display_name,
                    description,
                ),
            )
        return PreparedModelUpload(
            request_id,
            approval_id,
            canonical_artifact_id,
            digest,
            expires_at,
            display_name,
            description,
        )

    def upload(
        self,
        source: BlenderArtifactSource,
        uploader: OpenCloudModelAssetUploader,
        upload_ledger: AssetUploadLedger,
        *,
        request_id: str,
        approval_id: str,
        artifact_sha256: str,
        confirmation_phrase: str,
        now: int | None = None,
    ) -> RobloxAssetReceipt:
        request_id = _canonical_uuid(request_id, "request_id")
        approval_id = _canonical_uuid(approval_id, "approval_id")
        if not isinstance(artifact_sha256, str) or not _DIGEST.fullmatch(artifact_sha256):
            raise ValueError("artifact_sha256 must be lowercase hexadecimal")
        now = int(time.time()) if now is None else now
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT artifact_id,digest,expires_at,display_name,description,state,receipt_json "
                "FROM prepared_model_uploads WHERE request_id=? AND approval_id=?",
                (request_id, approval_id),
            ).fetchone()
            if row is None:
                raise ValueError("prepared model upload was not found")
            artifact_id, digest, expires_at, name, description, state, receipt_json = row
            if not secrets.compare_digest(digest, artifact_sha256):
                raise ValueError("artifact digest does not match the prepared review")
            expected_phrase = f"I_APPROVE_ROBLOX_MODEL_UPLOAD_{digest[:12]}"
            if not isinstance(confirmation_phrase, str) or not secrets.compare_digest(
                confirmation_phrase, expected_phrase
            ):
                raise ValueError(
                    "explicit digest-bound model asset upload confirmation is required"
                )
            if state == "complete" and isinstance(receipt_json, str):
                return RobloxAssetReceipt(**json.loads(receipt_json))
            if state != "prepared":
                raise RobloxAssetError("model upload outcome is uncertain; do not resubmit")
            if now > expires_at:
                db.execute(
                    "UPDATE prepared_model_uploads SET state='expired' WHERE request_id=?",
                    (request_id,),
                )
                raise ValueError("prepared model upload approval has expired")
            db.execute(
                "UPDATE prepared_model_uploads SET state='committing' WHERE request_id=?",
                (request_id,),
            )

        try:
            data = source.fetch(artifact_id, max_bytes=uploader.target.max_glb_bytes)
            actual_digest = hashlib.sha256(data).hexdigest()
            if not secrets.compare_digest(actual_digest, digest):
                raise ValueError("Blender artifact changed after the review was prepared")
            receipt = upload_ledger.run(
                uploader,
                data,
                request_id=request_id,
                approval_id=approval_id,
                approved_sha256=digest,
                display_name=name,
                description=description,
            )
        except Exception:
            with self._lock, self._connect() as db:
                db.execute(
                    "UPDATE prepared_model_uploads SET state='uncertain' WHERE request_id=? "
                    "AND state='committing'",
                    (request_id,),
                )
            raise
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE prepared_model_uploads SET state='complete',receipt_json=? "
                "WHERE request_id=? AND state='committing'",
                (json.dumps(receipt.to_mapping(), separators=(",", ":")), request_id),
            )
        return receipt


def _canonical_uuid(value: str, label: str) -> str:
    try:
        canonical = str(uuid.UUID(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a UUID") from exc
    if canonical != value.lower():
        raise ValueError(f"{label} must use canonical UUID syntax")
    return canonical
