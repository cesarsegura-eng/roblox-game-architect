"""Reviewed publishing to one pinned disposable Roblox place."""

from __future__ import annotations

import hashlib
import hmac
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
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from core.place_approval import sign_place_publish_approval, verify_place_publish_approval

PUBLISH_API_HOST = "apis.roblox.com"
MAX_PLACE_BYTES = 8_000_000
MAX_PUBLICATIONS = 10_000
MAX_STORED_BUILD_ARTIFACTS = 512
MAX_STORED_BUILD_BYTES = 512 * 1024 * 1024
BUILD_ARTIFACT_TTL_SECONDS = 24 * 60 * 60
PREPARED_APPROVAL_TTL_SECONDS = 5 * 60
_ID = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class RobloxPlacePublishError(RuntimeError):
    """A reviewed place publication failed or has an uncertain outcome."""


@dataclass(frozen=True, slots=True)
class RobloxPublishTarget:
    universe_id: str
    place_id: str
    api_key: str
    approval_secret: str
    production_universes: frozenset[str]
    production_places: frozenset[str]

    def __post_init__(self) -> None:
        for name in ("universe_id", "place_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise ValueError(f"{name} must be a positive decimal ID")
        if (
            not isinstance(self.api_key, str)
            or not 1 <= len(self.api_key) <= 512
            or not self.api_key.isascii()
            or any(ord(char) < 33 or ord(char) > 126 for char in self.api_key)
        ):
            raise ValueError("a Roblox place-publishing API key is required")
        if (
            not isinstance(self.approval_secret, str)
            or not 32 <= len(self.approval_secret) <= 512
            or not self.approval_secret.isascii()
        ):
            raise ValueError("place publishing requires a 32-512 character approval secret")
        for values in (self.production_universes, self.production_places):
            if not values or any(not _ID.fullmatch(value) for value in values):
                raise ValueError("production universe and place deny lists must be configured")
        if self.universe_id in self.production_universes or self.place_id in self.production_places:
            raise ValueError("place publishing target matches a configured production ID")

    @classmethod
    def from_env(cls) -> RobloxPublishTarget:
        if os.environ.get("RGA_ROBLOX_PLACE_PUBLISH_CONFIRMED") != (
            "I_ACCEPT_DISPOSABLE_TEST_PLACE_PUBLISHING"
        ):
            raise ValueError("explicit disposable-test-place publishing confirmation is required")
        return cls(
            universe_id=os.environ.get("RGA_ROBLOX_TEST_UNIVERSE_ID", ""),
            place_id=os.environ.get("RGA_ROBLOX_TEST_PLACE_ID", ""),
            api_key=os.environ.get("ROBLOX_OPEN_CLOUD_PUBLISH_API_KEY", ""),
            approval_secret=os.environ.get("RGA_ROBLOX_PUBLISH_APPROVAL_SECRET", ""),
            production_universes=_id_set("RGA_ROBLOX_PRODUCTION_UNIVERSE_IDS"),
            production_places=_id_set("RGA_ROBLOX_PRODUCTION_PLACE_IDS"),
        )


def _id_set(name: str) -> frozenset[str]:
    values = frozenset(
        value.strip() for value in os.environ.get(name, "").split(",") if value.strip()
    )
    if not values or any(not _ID.fullmatch(value) for value in values):
        raise ValueError(f"{name} must list one or more positive decimal IDs")
    return values


@dataclass(frozen=True, slots=True)
class RobloxPublishReceipt:
    request_id: str
    approval_id: str
    artifact_sha256: str
    universe_id: str
    place_id: str
    version_number: int

    def to_mapping(self) -> dict[str, str | int]:
        return {
            "request_id": self.request_id,
            "approval_id": self.approval_id,
            "artifact_sha256": self.artifact_sha256,
            "universe_id": self.universe_id,
            "place_id": self.place_id,
            "version_number": self.version_number,
        }


class OpenCloudPlacePublisher:
    """Call only Roblox's fixed place-version endpoint with XML place bytes."""

    def __init__(self, target: RobloxPublishTarget) -> None:
        self.target = target

    def publish(self, place_file: bytes) -> int:
        validate_place_file(place_file)
        path = (
            f"/universes/v1/{self.target.universe_id}/places/{self.target.place_id}"
            "/versions?versionType=Published"
        )
        connection = http.client.HTTPSConnection(
            PUBLISH_API_HOST, timeout=30, context=ssl.create_default_context()
        )
        try:
            connection.request(
                "POST",
                path,
                body=place_file,
                headers={
                    "x-api-key": self.target.api_key,
                    "Content-Type": "application/xml",
                    "Accept": "application/json",
                },
            )
            response = connection.getresponse()
            raw = response.read(64_001)
            if response.status not in {200, 201} or len(raw) > 64_000:
                raise RobloxPlacePublishError("Roblox place publication was not confirmed")
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise RobloxPlacePublishError("Roblox returned an invalid publish receipt") from exc
            version = result.get("versionNumber") if isinstance(result, dict) else None
            if type(version) is not int or version < 1:
                raise RobloxPlacePublishError("Roblox returned an invalid place version")
            return version
        except RobloxPlacePublishError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise RobloxPlacePublishError(
                "place publication outcome is uncertain; do not resubmit"
            ) from exc
        finally:
            connection.close()


def validate_place_file(place_file: object) -> None:
    if not isinstance(place_file, bytes) or not 32 <= len(place_file) <= MAX_PLACE_BYTES:
        raise ValueError("place artifact is empty or exceeds the publish limit")
    upper = place_file.upper()
    if not place_file.startswith(b"<roblox") or b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("place artifact is not safe XML")
    try:
        root = ET.fromstring(place_file)  # noqa: S314 - DTD and entities are rejected above.
    except ET.ParseError as exc:
        raise ValueError("place artifact is malformed XML") from exc
    if root.tag != "roblox":
        raise ValueError("place artifact has an invalid Roblox XML root")
    unsupported = {
        "SurfaceAppearance",
        "EditableImage",
        "EditableMesh",
        "PartOperation",
        "BaseWrap",
    }
    if any(node.get("class") in unsupported for node in root.iter("Item")):
        raise ValueError("place artifact contains content unsupported by Place Publishing API")
    parents = {child: parent for parent in root.iter() for child in parent}
    scripts = [
        node
        for node in root.iter("Item")
        if node.get("class") in {"Script", "LocalScript", "ModuleScript", "Actor"}
    ]
    if scripts:
        from core.gameplay_templates import GAMEPLAY_MODES, gameplay_script

        if len(scripts) != 1 or scripts[0].get("class") != "Script":
            raise ValueError("place artifact contains unsupported executable instances")
        script = scripts[0]
        parent = parents.get(script)
        properties = script.find("Properties")
        name = next(
            (value.text for value in properties or [] if value.get("name") == "Name"),
            None,
        )
        disabled = next(
            (value.text for value in properties or [] if value.get("name") == "Disabled"),
            "false",
        )
        source = next(
            (
                value.text
                for value in properties or []
                if value.get("name") == "Source" and value.tag in {"ProtectedString", "string"}
            ),
            None,
        )
        if parent is None or parent.get("class") != "ServerScriptService":
            raise ValueError("fixed gameplay script is outside ServerScriptService")
        trusted_templates = {
            template for mode in GAMEPLAY_MODES if (template := gameplay_script(mode)) is not None
        }
        if (name, source) not in trusted_templates or disabled != "false":
            raise ValueError("place artifact contains unapproved executable source")


class PlacePublicationLedger:
    """Durably record one digest-bound publish and never retry ambiguous writes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS place_publications ("
                "request_id TEXT PRIMARY KEY, approval_id TEXT NOT NULL, digest TEXT NOT NULL, "
                "state TEXT NOT NULL, receipt_json TEXT, error TEXT)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS place_build_artifacts ("
                "request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, artifact BLOB NOT NULL, "
                "summary_json TEXT NOT NULL, created_at INTEGER NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS prepared_place_publications ("
                "approval_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, digest TEXT NOT NULL, "
                "signature TEXT NOT NULL, expires_at INTEGER NOT NULL)"
            )

    def store_built_artifact(
        self, place_file: bytes, *, request_id: str, summary: dict[str, object]
    ) -> str:
        """Keep a bounded, short-lived server-side copy for direct MCP review/publish."""
        request_id = _canonical_uuid(request_id, "request_id")
        validate_place_file(place_file)
        digest = hashlib.sha256(place_file).hexdigest()
        created_at = int(time.time())
        summary_json = json.dumps(summary, separators=(",", ":"), sort_keys=True)
        with self._lock, self._connect() as db:
            db.execute(
                "DELETE FROM place_build_artifacts WHERE created_at < ?",
                (created_at - BUILD_ARTIFACT_TTL_SECONDS,),
            )
            row = db.execute(
                "SELECT digest FROM place_build_artifacts WHERE request_id=?", (request_id,)
            ).fetchone()
            if row is not None:
                if row[0] != digest:
                    raise ValueError("request_id was already used for a different place artifact")
                return digest
            totals = db.execute(
                "SELECT COUNT(*), COALESCE(SUM(length(artifact)),0) FROM place_build_artifacts"
            ).fetchone()
            if (
                totals is None
                or totals[0] >= MAX_STORED_BUILD_ARTIFACTS
                or totals[1] + len(place_file) > MAX_STORED_BUILD_BYTES
            ):
                raise RobloxPlacePublishError("temporary build artifact storage is full")
            db.execute(
                "INSERT INTO place_build_artifacts"
                "(request_id,digest,artifact,summary_json,created_at) VALUES(?,?,?,?,?)",
                (request_id, digest, place_file, summary_json, created_at),
            )
        return digest

    def prepare_direct_publication(
        self,
        publisher: OpenCloudPlacePublisher,
        *,
        request_id: str,
        artifact_sha256: str,
        now: int | None = None,
    ) -> dict[str, object]:
        """Create a short-lived approval receipt for a prior server-built artifact."""
        request_id = _canonical_uuid(request_id, "request_id")
        current = int(time.time()) if now is None else now
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT digest,artifact,summary_json FROM place_build_artifacts "
                "WHERE request_id=? AND created_at>=?",
                (request_id, current - BUILD_ARTIFACT_TTL_SECONDS),
            ).fetchone()
            if row is None:
                raise ValueError("no recent server-built artifact exists for this request")
            digest, artifact, summary_json = row
            if digest != artifact_sha256 or hashlib.sha256(artifact).hexdigest() != digest:
                raise ValueError("place artifact digest does not match the stored build")
            validate_place_file(artifact)
            summary = json.loads(summary_json)
            approval_id = str(uuid.uuid4())
            expires_at = current + PREPARED_APPROVAL_TTL_SECONDS
            signature = sign_place_publish_approval(
                publisher.target.approval_secret,
                request_id=request_id,
                approval_id=approval_id,
                artifact_sha256=digest,
                universe_id=publisher.target.universe_id,
                place_id=publisher.target.place_id,
                expires_at=expires_at,
            )
            db.execute("DELETE FROM prepared_place_publications WHERE expires_at<=?", (current,))
            db.execute(
                "INSERT INTO prepared_place_publications"
                "(approval_id,request_id,digest,signature,expires_at) VALUES(?,?,?,?,?)",
                (approval_id, request_id, digest, signature, expires_at),
            )
        return {
            "request_id": request_id,
            "approval_id": approval_id,
            "artifact_sha256": digest,
            "artifact_bytes": len(artifact),
            "target_universe_id": publisher.target.universe_id,
            "target_place_id": publisher.target.place_id,
            "confirmation_phrase": f"I_APPROVE_ROBLOX_TEST_PLACE_PUBLISH_{digest[:12]}",
            "expires_at": expires_at,
            "build_summary": summary,
        }

    def publish_prepared_artifact(
        self,
        publisher: OpenCloudPlacePublisher,
        *,
        request_id: str,
        approval_id: str,
        artifact_sha256: str,
        confirmation_phrase: str,
        now: int | None = None,
    ) -> RobloxPublishReceipt:
        request_id = _canonical_uuid(request_id, "request_id")
        approval_id = _canonical_uuid(approval_id, "approval_id")
        current = int(time.time()) if now is None else now
        if not isinstance(artifact_sha256, str) or not _DIGEST.fullmatch(artifact_sha256):
            raise ValueError("artifact SHA-256 must be lowercase hexadecimal")
        if not isinstance(confirmation_phrase, str) or not confirmation_phrase.isascii():
            raise ValueError("place publishing confirmation phrase is invalid")
        expected_phrase = f"I_APPROVE_ROBLOX_TEST_PLACE_PUBLISH_{artifact_sha256[:12]}"
        if not hmac.compare_digest(confirmation_phrase, expected_phrase):
            raise ValueError("place publishing confirmation phrase does not match")
        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT a.digest,a.artifact,p.signature,p.expires_at "
                "FROM prepared_place_publications p JOIN place_build_artifacts a "
                "ON a.request_id=p.request_id "
                "WHERE p.approval_id=? AND p.request_id=?",
                (approval_id, request_id),
            ).fetchone()
        if row is None:
            raise ValueError("place publication approval or stored artifact is unavailable")
        digest, artifact, signature, expires_at = row
        if digest != artifact_sha256 or expires_at <= current:
            raise ValueError("place publication approval is expired or bound to another artifact")
        return self.run(
            publisher,
            artifact,
            request_id=request_id,
            approval_id=approval_id,
            artifact_sha256=digest,
            signature=signature,
            expires_at=expires_at,
        )

    def run(
        self,
        publisher: OpenCloudPlacePublisher,
        place_file: bytes,
        *,
        request_id: str,
        approval_id: str,
        artifact_sha256: str,
        signature: str,
        expires_at: int,
    ) -> RobloxPublishReceipt:
        request_id = _canonical_uuid(request_id, "request_id")
        approval_id = _canonical_uuid(approval_id, "approval_id")
        validate_place_file(place_file)
        digest = hashlib.sha256(place_file).hexdigest()
        if not isinstance(artifact_sha256, str) or not _DIGEST.fullmatch(artifact_sha256):
            raise ValueError("artifact SHA-256 must be lowercase hexadecimal")
        if not secrets.compare_digest(digest, artifact_sha256):
            raise ValueError("place artifact digest does not match")
        target = publisher.target
        row_digest = hashlib.sha256(
            json.dumps(
                [digest, approval_id, target.universe_id, target.place_id],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

        with self._lock, self._connect() as db:
            row = db.execute(
                "SELECT approval_id,digest,state,receipt_json FROM place_publications "
                "WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if row is not None:
                if row[0] != approval_id or row[1] != row_digest:
                    raise ValueError("request_id was already used for a different place approval")
                if row[2] == "complete" and isinstance(row[3], str):
                    return RobloxPublishReceipt(**json.loads(row[3]))
                raise RobloxPlacePublishError(
                    "previous place publication is uncertain; it will not be resubmitted"
                )
            if not verify_place_publish_approval(
                target.approval_secret,
                signature,
                request_id=request_id,
                approval_id=approval_id,
                artifact_sha256=digest,
                universe_id=target.universe_id,
                place_id=target.place_id,
                expires_at=expires_at,
            ):
                raise ValueError("place publishing approval is invalid or expired")
            count = db.execute("SELECT COUNT(*) FROM place_publications").fetchone()
            if count is None or count[0] >= MAX_PUBLICATIONS:
                raise RobloxPlacePublishError("place publication ledger is full")
            db.execute(
                "INSERT INTO place_publications(request_id,approval_id,digest,state) "
                "VALUES(?,?,?,'pending')",
                (request_id, approval_id, row_digest),
            )

        try:
            version_number = publisher.publish(place_file)
        except Exception as exc:
            with self._lock, self._connect() as db:
                db.execute(
                    "UPDATE place_publications SET state='uncertain',error=? WHERE request_id=?",
                    (type(exc).__name__, request_id),
                )
            raise

        receipt = RobloxPublishReceipt(
            request_id,
            approval_id,
            digest,
            target.universe_id,
            target.place_id,
            version_number,
        )
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE place_publications SET state='complete',receipt_json=? WHERE request_id=?",
                (json.dumps(receipt.to_mapping(), separators=(",", ":")), request_id),
            )
        return receipt

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def _canonical_uuid(value: str, name: str) -> str:
    try:
        canonical = str(uuid.UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{name} must be a UUID") from exc
    if canonical != value.lower():
        raise ValueError(f"{name} must use canonical UUID syntax")
    return canonical
