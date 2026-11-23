"""Package release evidence files without certifying their claims."""

from __future__ import annotations

import hashlib
import io
import json
import mimetypes
import re
import stat
import zipfile
from collections.abc import Iterable
from pathlib import Path

RELEASE_GATE_IDS = (
    "release_scope",
    "server_authority_and_abuse",
    "persistence_and_recovery",
    "commerce_and_policy",
    "multiplayer_and_network",
    "device_playability_and_performance",
    "content_rights_and_safety",
    "operations_and_rollback",
    "human_release_approval",
)
MAX_EVIDENCE_FILES = 64
MAX_EVIDENCE_FILE_BYTES = 16 * 1024 * 1024
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
MAX_BUNDLE_BYTES = 72 * 1024 * 1024
MAX_REPORT_BYTES = 1 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_ARCHIVE_ENTRIES = MAX_EVIDENCE_FILES + 2
_REPORT_FIELDS = {
    "schema_version",
    "plan_title",
    "readiness",
    "verified_gate_count",
    "pending_gate_count",
    "notice",
    "gates",
}
_GATE_FIELDS = {
    "id",
    "title",
    "owner_role",
    "applicability",
    "status",
    "verification_method",
    "evidence_required",
    "evidence",
}


class ReleaseEvidenceError(ValueError):
    """A release report, evidence path, or evidence archive is invalid."""


def package_release_evidence(
    report_path: str | Path,
    evidence_files: Iterable[tuple[str, str | Path]],
    *,
    workspace_root: str | Path,
) -> tuple[bytes, dict[str, object]]:
    """Build a reproducible ZIP inventory and leave every release gate pending."""
    root = Path(workspace_root).resolve(strict=True)
    report_bytes = _read_workspace_file(root, report_path, max_bytes=MAX_REPORT_BYTES)
    report = _load_json_object(report_bytes, "release report")
    _validate_pending_report(report)

    entries: list[tuple[str, str, bytes]] = []
    seen_sources: set[str] = set()
    total_bytes = 0
    if isinstance(evidence_files, (str, bytes)) or not isinstance(evidence_files, Iterable):
        raise ReleaseEvidenceError("evidence_files must be an iterable of gate/path pairs")
    for index, entry in enumerate(evidence_files, start=1):
        if index > MAX_EVIDENCE_FILES:
            raise ReleaseEvidenceError("too many evidence files")
        if (
            not isinstance(entry, (tuple, list))
            or len(entry) != 2
            or not isinstance(entry[0], str)
            or entry[0] not in RELEASE_GATE_IDS
        ):
            raise ReleaseEvidenceError("each evidence item must name a known release gate")
        gate_id, source = entry
        source_path, source_bytes = _read_workspace_file_with_path(
            root, source, max_bytes=MAX_EVIDENCE_FILE_BYTES
        )
        relative_source = source_path.relative_to(root).as_posix()
        if relative_source in seen_sources:
            raise ReleaseEvidenceError("an evidence file may be included only once")
        seen_sources.add(relative_source)
        if not source_bytes:
            raise ReleaseEvidenceError("evidence files cannot be empty")
        total_bytes += len(source_bytes)
        if total_bytes > MAX_EVIDENCE_BYTES:
            raise ReleaseEvidenceError("combined evidence exceeds its size limit")
        entries.append((gate_id, relative_source, source_bytes))
    if not entries:
        raise ReleaseEvidenceError("at least one evidence file is required")

    canonical_report = _canonical_json(report)
    evidence: list[dict[str, object]] = []
    archive_files: list[tuple[str, bytes]] = [("release-readiness.json", canonical_report)]
    for index, (gate_id, source, data) in enumerate(entries, start=1):
        source_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(source).name).strip("._")[:120]
        if not source_name:
            source_name = "evidence.bin"
        archive_path = f"evidence/{gate_id}/{index:03d}-{source_name}"
        media_type = mimetypes.guess_type(source_name)[0] or "application/octet-stream"
        evidence.append(
            {
                "gate_id": gate_id,
                "source_path": source,
                "archive_path": archive_path,
                "byte_length": len(data),
                "media_type": media_type,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        archive_files.append((archive_path, data))

    manifest: dict[str, object] = {
        "schema_version": 1,
        "plan_title": report["plan_title"],
        "readiness": "not_ready",
        "verified_gate_count": 0,
        "pending_gate_ids": list(RELEASE_GATE_IDS),
        "release_readiness_sha256": hashlib.sha256(canonical_report).hexdigest(),
        "evidence": evidence,
        "notice": (
            "Evidence inventory only. File contents and claims are unverified; owners must "
            "review each item. This bundle does not change any release-gate status."
        ),
    }
    archive_files.append(("manifest.json", _canonical_json(manifest)))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for archive_path, data in archive_files:
            info = zipfile.ZipInfo(archive_path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    bundle = buffer.getvalue()
    if len(bundle) > MAX_BUNDLE_BYTES:
        raise ReleaseEvidenceError("release evidence bundle exceeds its size limit")
    return bundle, manifest


def verify_release_evidence_bundle(
    bundle: bytes, *, expected_sha256: str | None = None
) -> dict[str, object]:
    """Verify archive integrity while leaving the evidence claims unverified.

    The archive is inspected in memory and is never extracted. A successful
    result proves only that the packaged files match the manifest and that the
    report still contains the ordered pending checklist.
    """
    if not isinstance(bundle, bytes) or not bundle:
        raise ReleaseEvidenceError("release evidence bundle must be non-empty bytes")
    if len(bundle) > MAX_BUNDLE_BYTES:
        raise ReleaseEvidenceError("release evidence bundle exceeds its size limit")
    if expected_sha256 is not None:
        if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
            raise ReleaseEvidenceError(
                "expected SHA-256 must be 64 lowercase hexadecimal characters"
            )
        if hashlib.sha256(bundle).hexdigest() != expected_sha256:
            raise ReleaseEvidenceError("release evidence archive SHA-256 does not match")
    try:
        with zipfile.ZipFile(io.BytesIO(bundle), mode="r") as archive:
            infos = archive.infolist()
            if not 3 <= len(infos) <= MAX_ARCHIVE_ENTRIES:
                raise ReleaseEvidenceError("release evidence archive has an invalid entry count")
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ReleaseEvidenceError("release evidence archive contains duplicate paths")
            if any(
                info.is_dir()
                or info.flag_bits & 0x1
                or info.compress_type != zipfile.ZIP_DEFLATED
                or stat.S_ISLNK(info.external_attr >> 16)
                or info.file_size > MAX_EVIDENCE_FILE_BYTES
                for info in infos
            ):
                raise ReleaseEvidenceError("release evidence archive contains an invalid entry")
            if (
                sum(info.file_size for info in infos)
                > MAX_EVIDENCE_BYTES + MAX_REPORT_BYTES + MAX_MANIFEST_BYTES
            ):
                raise ReleaseEvidenceError(
                    "release evidence archive exceeds its expanded size limit"
                )
            if "release-readiness.json" not in names or "manifest.json" not in names:
                raise ReleaseEvidenceError(
                    "release evidence archive is missing its report or manifest"
                )
            info_by_name = {info.filename: info for info in infos}
            if (
                info_by_name["release-readiness.json"].file_size > MAX_REPORT_BYTES
                or info_by_name["manifest.json"].file_size > MAX_MANIFEST_BYTES
            ):
                raise ReleaseEvidenceError("release report or manifest exceeds its size limit")

            report_bytes = archive.read("release-readiness.json")
            manifest_bytes = archive.read("manifest.json")
            if len(report_bytes) > MAX_REPORT_BYTES or len(manifest_bytes) > MAX_MANIFEST_BYTES:
                raise ReleaseEvidenceError("release report or manifest exceeds its size limit")
            report = _load_json_object(report_bytes, "release report")
            _validate_pending_report(report)
            if report_bytes != _canonical_json(report):
                raise ReleaseEvidenceError("release report is not in canonical form")
            manifest = _load_json_object(manifest_bytes, "release evidence manifest")
            if manifest_bytes != _canonical_json(manifest):
                raise ReleaseEvidenceError("release evidence manifest is not in canonical form")
            _validate_manifest(manifest, report, report_bytes, archive, names)
            return manifest
    except ReleaseEvidenceError:
        raise
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ReleaseEvidenceError("release evidence archive is invalid or unreadable") from exc


def _validate_manifest(
    manifest: dict[str, object],
    report: dict[str, object],
    report_bytes: bytes,
    archive: zipfile.ZipFile,
    names: list[str],
) -> None:
    if set(manifest) != {
        "schema_version",
        "plan_title",
        "readiness",
        "verified_gate_count",
        "pending_gate_ids",
        "release_readiness_sha256",
        "evidence",
        "notice",
    }:
        raise ReleaseEvidenceError("release evidence manifest has unexpected fields")
    if (
        type(manifest.get("schema_version")) is not int
        or manifest.get("schema_version") != 1
        or manifest.get("plan_title") != report.get("plan_title")
        or manifest.get("readiness") != "not_ready"
        or type(manifest.get("verified_gate_count")) is not int
        or manifest.get("verified_gate_count") != 0
        or manifest.get("pending_gate_ids") != list(RELEASE_GATE_IDS)
        or manifest.get("release_readiness_sha256") != hashlib.sha256(report_bytes).hexdigest()
        or manifest.get("notice")
        != (
            "Evidence inventory only. File contents and claims are unverified; owners must "
            "review each item. This bundle does not change any release-gate status."
        )
    ):
        raise ReleaseEvidenceError("release evidence manifest does not match its pending report")
    if len(_canonical_json(manifest)) > MAX_MANIFEST_BYTES:
        raise ReleaseEvidenceError("release evidence manifest exceeds its size limit")
    evidence = manifest.get("evidence")
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= MAX_EVIDENCE_FILES:
        raise ReleaseEvidenceError("release evidence manifest has an invalid evidence list")
    if len(names) != len(evidence) + 2:
        raise ReleaseEvidenceError("release evidence archive has unlisted or missing files")
    expected_names = {"release-readiness.json", "manifest.json"}
    seen_sources: set[str] = set()
    for index, item in enumerate(evidence, start=1):
        if not isinstance(item, dict) or set(item) != {
            "gate_id",
            "source_path",
            "archive_path",
            "byte_length",
            "media_type",
            "sha256",
        }:
            raise ReleaseEvidenceError("release evidence entry has unexpected fields")
        gate_id = item.get("gate_id")
        source_path = item.get("source_path")
        archive_path = item.get("archive_path")
        byte_length = item.get("byte_length")
        media_type = item.get("media_type")
        digest = item.get("sha256")
        if (
            gate_id not in RELEASE_GATE_IDS
            or not isinstance(source_path, str)
            or not 1 <= len(source_path) <= 260
            or source_path.startswith("/")
            or "\\" in source_path
            or any(
                part in {"", ".", ".."} or ":" in part or "\0" in part
                for part in source_path.split("/")
            )
            or source_path in seen_sources
            or not isinstance(archive_path, str)
            or re.fullmatch(
                rf"evidence/{re.escape(str(gate_id))}/{index:03d}-[A-Za-z0-9._-]{{1,120}}",
                archive_path,
            )
            is None
            or archive_path in expected_names
            or type(byte_length) is not int
            or not 1 <= byte_length <= MAX_EVIDENCE_FILE_BYTES
            or not isinstance(media_type, str)
            or not 1 <= len(media_type) <= 127
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise ReleaseEvidenceError("release evidence entry has invalid metadata")
        seen_sources.add(source_path)
        expected_names.add(archive_path)
        data = archive.read(archive_path)
        if len(data) != byte_length or hashlib.sha256(data).hexdigest() != digest:
            raise ReleaseEvidenceError("release evidence file does not match its manifest digest")
    if set(names) != expected_names:
        raise ReleaseEvidenceError("release evidence archive paths do not match the manifest")


def _read_workspace_file(root: Path, path: str | Path, *, max_bytes: int) -> bytes:
    return _read_workspace_file_with_path(root, path, max_bytes=max_bytes)[1]


def _read_workspace_file_with_path(
    root: Path, path: str | Path, *, max_bytes: int
) -> tuple[Path, bytes]:
    try:
        relative = Path(path)
    except (TypeError, ValueError) as exc:
        raise ReleaseEvidenceError("workspace file path is invalid") from exc
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {".", ".."} or ":" in part or "\0" in part for part in relative.parts)
    ):
        raise ReleaseEvidenceError(
            "workspace file paths must be relative and stay in the workspace"
        )
    current = root
    for part in relative.parts:
        current = current / part
        try:
            if current.is_symlink():
                raise ReleaseEvidenceError("symlink evidence paths are not allowed")
        except OSError as exc:
            raise ReleaseEvidenceError("workspace file could not be inspected") from exc
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
        if not resolved.is_file():
            raise ReleaseEvidenceError("workspace evidence must be a regular file")
        if resolved.stat().st_size > max_bytes:
            raise ReleaseEvidenceError("workspace file exceeds its size limit")
        data = resolved.read_bytes()
        if len(data) > max_bytes:
            raise ReleaseEvidenceError("workspace file exceeds its size limit")
        return resolved, data
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, ReleaseEvidenceError):
            raise
        raise ReleaseEvidenceError("workspace file is unavailable") from exc


def _load_json_object(raw: bytes, label: str) -> dict[str, object]:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ReleaseEvidenceError(f"{label} contains a duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ReleaseEvidenceError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ReleaseEvidenceError(f"{label} must be a JSON object")
    return value


def _validate_pending_report(report: dict[str, object]) -> None:
    if (
        set(report) != _REPORT_FIELDS
        or type(report.get("schema_version")) is not int
        or report.get("schema_version") != 1
        or report.get("readiness") != "not_ready"
        or type(report.get("verified_gate_count")) is not int
        or report.get("verified_gate_count") != 0
        or type(report.get("pending_gate_count")) is not int
        or report.get("pending_gate_count") != len(RELEASE_GATE_IDS)
        or not isinstance(report.get("plan_title"), str)
        or not 1 <= len(report["plan_title"]) <= 80
        or not isinstance(report.get("gates"), list)
        or len(report["gates"]) != len(RELEASE_GATE_IDS)
        or not isinstance(report.get("notice"), str)
        or not 1 <= len(report["notice"]) <= 500
    ):
        raise ReleaseEvidenceError("release report must be the pending v1 checklist")
    gates = report["gates"]
    if not all(
        isinstance(gate, dict)
        and set(gate) == _GATE_FIELDS
        and gate.get("id") == gate_id
        and gate.get("status") == "pending"
        and gate.get("evidence") == []
        and gate.get("applicability")
        in (
            "required",
            "likely_in_scope",
            "owner_scope_decision_required",
        )
        and all(
            isinstance(gate.get(field), str) and 1 <= len(gate[field]) <= limit
            for field, limit in (
                ("title", 100),
                ("owner_role", 80),
                ("verification_method", 500),
            )
        )
        and isinstance(gate.get("evidence_required"), list)
        and 1 <= len(gate["evidence_required"]) <= 5
        and all(
            isinstance(item, str) and 1 <= len(item) <= 160 for item in gate["evidence_required"]
        )
        for gate_id, gate in zip(RELEASE_GATE_IDS, gates, strict=True)
    ):
        raise ReleaseEvidenceError("release report must contain the nine ordered pending gates")


def _canonical_json(value: object) -> bytes:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (serialized + "\n").encode("utf-8")
