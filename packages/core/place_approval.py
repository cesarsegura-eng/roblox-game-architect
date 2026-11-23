"""Short-lived approvals bound to one place artifact and fixed Roblox target."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import uuid

_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SIGNATURE = _DIGEST
_ID = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)


def sign_place_publish_approval(
    secret: str,
    *,
    request_id: str,
    approval_id: str,
    artifact_sha256: str,
    universe_id: str,
    place_id: str,
    expires_at: int,
) -> str:
    if not isinstance(secret, str) or not 32 <= len(secret) <= 512 or not secret.isascii():
        raise ValueError("place publish approval secret must contain 32-512 ASCII characters")
    if not _DIGEST.fullmatch(artifact_sha256):
        raise ValueError("place artifact SHA-256 must be lowercase hexadecimal")
    payload = _payload(request_id, approval_id, artifact_sha256, universe_id, place_id, expires_at)
    return hmac.new(secret.encode("ascii"), payload, hashlib.sha256).hexdigest()


def verify_place_publish_approval(
    secret: str,
    signature: str,
    *,
    request_id: str,
    approval_id: str,
    artifact_sha256: str,
    universe_id: str,
    place_id: str,
    expires_at: int,
    now: int | None = None,
) -> bool:
    current = int(time.time()) if now is None else now
    if type(expires_at) is not int or not current < expires_at <= current + 900:
        return False
    if not isinstance(signature, str) or not _SIGNATURE.fullmatch(signature):
        return False
    try:
        expected = sign_place_publish_approval(
            secret,
            request_id=request_id,
            approval_id=approval_id,
            artifact_sha256=artifact_sha256,
            universe_id=universe_id,
            place_id=place_id,
            expires_at=expires_at,
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(signature, expected)


def _payload(
    request_id: str,
    approval_id: str,
    artifact_sha256: str,
    universe_id: str,
    place_id: str,
    expires_at: int,
) -> bytes:
    if type(expires_at) is not int:
        raise ValueError("approval expiry must be an integer")
    return json.dumps(
        {
            "request_id": _uuid(request_id),
            "approval_id": _uuid(approval_id),
            "artifact_sha256": artifact_sha256,
            "universe_id": _identifier(universe_id),
            "place_id": _identifier(place_id),
            "expires_at": expires_at,
        },
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _uuid(value: str) -> str:
    canonical = str(uuid.UUID(value))
    if canonical != value.lower():
        raise ValueError("approval IDs must use canonical UUID syntax")
    return canonical


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("Roblox target IDs must be positive decimal IDs")
    return value
