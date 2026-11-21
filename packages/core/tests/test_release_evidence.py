from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from core.release_evidence import (
    MAX_EVIDENCE_FILE_BYTES,
    ReleaseEvidenceError,
    package_release_evidence,
    verify_release_evidence_bundle,
)
from core.release_readiness import review_release_readiness


def _pending_report() -> dict[str, object]:
    plan = {
        "schema_version": 1,
        "title": "Island Expedition",
        "genre": "Adventure",
        "pitch": "Explore three islands and return collected artifacts to the harbor.",
        "target_players": "One to four players, keyboard, controller, and touch.",
        "core_loop": ["Explore an island", "Return to the harbor"],
        "systems": [
            {
                "name": "Exploration",
                "purpose": "Find island landmarks.",
                "implementation_stage": "blockout",
            },
            {
                "name": "Artifacts",
                "purpose": "Collect objects.",
                "implementation_stage": "blockout",
            },
            {
                "name": "Harbor",
                "purpose": "Return and regroup.",
                "implementation_stage": "blockout",
            },
        ],
        "world_brief": "Build a readable harbor hub connected to three island routes.",
        "milestones": ["Block out the harbor", "Build island routes", "Review the loop"],
        "validation_goals": ["Reach every island", "Return to the harbor", "Review mobile scale"],
    }
    return review_release_readiness(plan)


def test_release_evidence_bundle_is_reproducible_and_keeps_gates_pending(tmp_path: Path) -> None:
    report = _pending_report()
    report_path = tmp_path / "release-readiness.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    source = tmp_path / "proofs" / "playtest.json"
    source.parent.mkdir()
    payload = b'{"result":"local simulation passed"}\n'
    source.write_bytes(payload)

    args = {
        "workspace_root": tmp_path,
        "report_path": "release-readiness.json",
        "evidence_files": [("device_playability_and_performance", "proofs/playtest.json")],
    }
    archive, manifest = package_release_evidence(**args)
    repeat, repeat_manifest = package_release_evidence(**args)

    assert archive == repeat
    assert manifest == repeat_manifest
    assert manifest["readiness"] == "not_ready"
    assert manifest["verified_gate_count"] == 0
    assert len(manifest["pending_gate_ids"]) == 9
    assert manifest["evidence"][0]["sha256"] == hashlib.sha256(payload).hexdigest()
    schema_path = (
        Path(__file__).resolve().parents[1] / "schemas" / "release-evidence-bundle-v1.schema.json"
    )
    Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(manifest)

    with zipfile.ZipFile(BytesIO(archive)) as bundle:
        assert set(bundle.namelist()) == {
            "release-readiness.json",
            "manifest.json",
            "evidence/device_playability_and_performance/001-playtest.json",
        }
        bundled_report = json.loads(bundle.read("release-readiness.json"))
        assert bundled_report["readiness"] == "not_ready"
        assert bundled_report["verified_gate_count"] == 0
        assert all(gate["status"] == "pending" for gate in bundled_report["gates"])
        assert bundle.read(manifest["evidence"][0]["archive_path"]) == payload


def test_release_evidence_verifier_confirms_integrity_without_verifying_claims(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_pending_report()), encoding="utf-8")
    evidence_path = tmp_path / "playtest.json"
    evidence_path.write_text('{"result":"engine output captured"}\n', encoding="utf-8")
    archive, _ = package_release_evidence(
        "report.json",
        [("device_playability_and_performance", "playtest.json")],
        workspace_root=tmp_path,
    )

    archive_sha256 = hashlib.sha256(archive).hexdigest()
    manifest = verify_release_evidence_bundle(archive, expected_sha256=archive_sha256)

    assert manifest["readiness"] == "not_ready"
    assert manifest["verified_gate_count"] == 0
    assert manifest["pending_gate_ids"] == list(
        (
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
    )
    with pytest.raises(ReleaseEvidenceError, match="archive SHA-256"):
        verify_release_evidence_bundle(archive, expected_sha256="0" * 64)
    with pytest.raises(ReleaseEvidenceError, match="expected SHA-256"):
        verify_release_evidence_bundle(archive, expected_sha256="not a digest")


def test_release_evidence_verifier_rejects_tampered_payload_and_extra_files(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_pending_report()), encoding="utf-8")
    evidence_path = tmp_path / "proof.json"
    evidence_path.write_text('{"result":"captured"}\n', encoding="utf-8")
    archive, manifest = package_release_evidence(
        "report.json", [("release_scope", "proof.json")], workspace_root=tmp_path
    )

    with zipfile.ZipFile(BytesIO(archive)) as original:
        files = {name: original.read(name) for name in original.namelist()}
    evidence_name = manifest["evidence"][0]["archive_path"]
    files[evidence_name] = b'{"result":"changed"}\n'
    tampered = BytesIO()
    with zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as changed:
        for name, data in files.items():
            changed.writestr(name, data)
    with pytest.raises(ReleaseEvidenceError, match="digest"):
        verify_release_evidence_bundle(tampered.getvalue())

    files[evidence_name] = evidence_path.read_bytes()
    files["unexpected.txt"] = b"unlisted"
    extra = BytesIO()
    with zipfile.ZipFile(extra, "w", compression=zipfile.ZIP_DEFLATED) as changed:
        for name, data in files.items():
            changed.writestr(name, data)
    with pytest.raises(ReleaseEvidenceError, match=r"unlisted or missing|paths do not match"):
        verify_release_evidence_bundle(extra.getvalue())


@pytest.mark.parametrize(
    "path",
    ["../outside.json", "", ".", "proofs/../release-readiness.json"],
)
def test_release_evidence_rejects_paths_outside_workspace(tmp_path: Path, path: str) -> None:
    (tmp_path / "release-readiness.json").write_text(
        json.dumps(_pending_report()), encoding="utf-8"
    )
    with pytest.raises(ReleaseEvidenceError, match=r"relative|workspace"):
        package_release_evidence(
            "release-readiness.json",
            [("release_scope", path)],
            workspace_root=tmp_path,
        )


def test_release_evidence_rejects_non_pending_reports_and_duplicate_sources(tmp_path: Path) -> None:
    report = _pending_report()
    report["gates"][0]["status"] = "verified"
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")

    with pytest.raises(ReleaseEvidenceError, match="pending"):
        package_release_evidence(
            "report.json", [("release_scope", "evidence.json")], workspace_root=tmp_path
        )

    (tmp_path / "report.json").write_text(json.dumps(_pending_report()), encoding="utf-8")
    with pytest.raises(ReleaseEvidenceError, match="only once"):
        package_release_evidence(
            "report.json",
            [("release_scope", "evidence.json"), ("operations_and_rollback", "evidence.json")],
            workspace_root=tmp_path,
        )


def test_release_evidence_rejects_empty_and_oversized_inputs(tmp_path: Path) -> None:
    (tmp_path / "report.json").write_text(json.dumps(_pending_report()), encoding="utf-8")
    empty = tmp_path / "empty.json"
    empty.write_bytes(b"")
    with pytest.raises(ReleaseEvidenceError, match="empty"):
        package_release_evidence(
            "report.json", [("release_scope", "empty.json")], workspace_root=tmp_path
        )

    oversized = tmp_path / "oversized.bin"
    with oversized.open("wb") as stream:
        stream.truncate(MAX_EVIDENCE_FILE_BYTES + 1)
    with pytest.raises(ReleaseEvidenceError, match="size limit"):
        package_release_evidence(
            "report.json", [("release_scope", "oversized.bin")], workspace_root=tmp_path
        )


def test_release_evidence_rejects_symlink_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "report.json").write_text(json.dumps(_pending_report()), encoding="utf-8")
    (tmp_path / "link.json").write_text("{}", encoding="utf-8")
    is_symlink = Path.is_symlink

    def flag_link(path: Path) -> bool:
        return path.name == "link.json" or is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", flag_link)

    with pytest.raises(ReleaseEvidenceError, match="symlink"):
        package_release_evidence(
            "report.json", [("release_scope", "link.json")], workspace_root=tmp_path
        )
