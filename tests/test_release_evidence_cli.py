from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.release_evidence import ReleaseEvidenceError, package_release_evidence
from core.release_readiness import review_release_readiness
from tools import verify_release_evidence as verifier_cli
from tools.package_release_evidence import _output_path
from tools.verify_release_evidence import _input_path


def test_evidence_cli_output_is_new_and_workspace_relative(tmp_path: Path) -> None:
    (tmp_path / "dist").mkdir()
    target = _output_path(tmp_path, "dist/release-evidence.zip")
    assert target == tmp_path / "dist" / "release-evidence.zip"

    target.write_bytes(b"existing")
    with pytest.raises(ReleaseEvidenceError, match="new file name"):
        _output_path(tmp_path, "dist/release-evidence.zip")


@pytest.mark.parametrize("path", ["../outside.zip", "", "."])
def test_evidence_cli_rejects_output_paths_outside_workspace(tmp_path: Path, path: str) -> None:
    with pytest.raises(ReleaseEvidenceError, match=r"relative|workspace"):
        _output_path(tmp_path, path)


def test_evidence_cli_rejects_absolute_output_paths(tmp_path: Path) -> None:
    with pytest.raises(ReleaseEvidenceError, match="relative"):
        _output_path(tmp_path, str(tmp_path.parent / "outside.zip"))


def test_evidence_cli_rejects_symlink_output_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "linked").mkdir()
    is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path.name == "linked" or is_symlink(path))

    with pytest.raises(ReleaseEvidenceError, match="symlink"):
        _output_path(tmp_path, "linked/release-evidence.zip")


def test_evidence_verifier_input_is_workspace_relative_and_bounded(tmp_path: Path) -> None:
    (tmp_path / "dist").mkdir()
    bundle = tmp_path / "dist" / "release-evidence.zip"
    bundle.write_bytes(b"zip placeholder")
    assert _input_path(tmp_path, "dist/release-evidence.zip") == bundle

    with pytest.raises(ReleaseEvidenceError, match="regular ZIP file"):
        _input_path(tmp_path, "dist")
    with pytest.raises(ReleaseEvidenceError, match="workspace"):
        _input_path(tmp_path, "../outside.zip")


def test_evidence_verifier_rejects_symlink_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "release-evidence.zip"
    bundle.write_bytes(b"zip placeholder")
    is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path.name == "release-evidence.zip" or is_symlink(path),
    )

    with pytest.raises(ReleaseEvidenceError, match="symlink"):
        _input_path(tmp_path, "release-evidence.zip")


def test_evidence_verifier_cli_reports_integrity_without_approving_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = {
        "schema_version": 1,
        "title": "Island Expedition",
        "genre": "Adventure",
        "pitch": "Explore islands and return artifacts to the harbor.",
        "target_players": "One to four players.",
        "core_loop": ["Explore an island", "Return to the harbor"],
        "systems": [
            {
                "name": "Exploration",
                "purpose": "Find landmarks.",
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
        "world_brief": "Build a harbor connected to island routes.",
        "milestones": ["Block out the harbor", "Build island routes", "Review the loop"],
        "validation_goals": ["Reach every island", "Return to the harbor", "Review mobile scale"],
    }
    (tmp_path / "dist").mkdir()
    report_path = tmp_path / "dist" / "release-readiness.json"
    report_path.write_text(json.dumps(review_release_readiness(report)), encoding="utf-8")
    proof = tmp_path / "dist" / "review.json"
    proof.write_text('{"review":"captured"}\n', encoding="utf-8")
    archive, _ = package_release_evidence(
        "dist/release-readiness.json",
        [("content_rights_and_safety", "dist/review.json")],
        workspace_root=tmp_path,
    )
    bundle_path = tmp_path / "dist" / "release-evidence.zip"
    bundle_path.write_bytes(archive)
    monkeypatch.setattr(verifier_cli, "ROOT", tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_release_evidence",
            "dist/release-evidence.zip",
            "--sha256",
            hashlib.sha256(archive).hexdigest(),
        ],
    )

    assert verifier_cli.main() == 0
    output = capsys.readouterr().out
    assert "Archive SHA-256 and internal consistency verified" in output
    assert "claims remain unverified" in output
