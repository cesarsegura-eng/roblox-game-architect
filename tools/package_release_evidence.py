"""Create a local, hash-bound ZIP inventory for a pending release checklist."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from core.release_evidence import ReleaseEvidenceError, package_release_evidence  # noqa: E402


def _output_path(root: Path, value: str) -> Path:
    relative = Path(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {".", ".."} or ":" in part or "\0" in part for part in relative.parts)
    ):
        raise ReleaseEvidenceError("output path must be relative and stay inside the workspace")
    target = root / relative
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ReleaseEvidenceError("output path cannot contain symlink directories")
    if not target.parent.is_dir() or target.is_symlink() or target.exists():
        raise ReleaseEvidenceError("output must use an existing directory and a new file name")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="pending release-readiness JSON relative to the workspace")
    parser.add_argument("output", help="new ZIP output path relative to the workspace")
    parser.add_argument(
        "--evidence",
        action="append",
        required=True,
        metavar="GATE_ID=PATH",
        help="evidence file path relative to the workspace; repeat for each artifact",
    )
    args = parser.parse_args()
    root = ROOT.resolve()
    try:
        output = _output_path(root, args.output)
        evidence: list[tuple[str, str]] = []
        for value in args.evidence:
            gate_id, separator, source_path = value.partition("=")
            if not separator or not gate_id or not source_path:
                raise ReleaseEvidenceError("--evidence must use GATE_ID=PATH syntax")
            evidence.append((gate_id, source_path))
        archive, manifest = package_release_evidence(
            args.report,
            evidence,
            workspace_root=root,
        )
        with output.open("xb") as stream:
            stream.write(archive)
    except (OSError, ReleaseEvidenceError) as exc:
        parser.error(str(exc))
    print(
        f"Release evidence inventory written to {output.relative_to(root)}; "
        f"{len(manifest['evidence'])} files, readiness remains not_ready, "
        f"sha256={hashlib.sha256(archive).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
