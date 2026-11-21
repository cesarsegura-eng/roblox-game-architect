"""Verify a release-evidence ZIP's integrity without approving its claims."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from core.release_evidence import (  # noqa: E402
    MAX_BUNDLE_BYTES,
    ReleaseEvidenceError,
    verify_release_evidence_bundle,
)


def _input_path(root: Path, value: str) -> Path:
    relative = Path(value)
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {".", ".."} or ":" in part or "\0" in part for part in relative.parts)
    ):
        raise ReleaseEvidenceError("input path must be relative and stay inside the workspace")
    target = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ReleaseEvidenceError("input path cannot contain symlinks")
    try:
        resolved = target.resolve(strict=True)
        resolved.relative_to(root)
        if not resolved.is_file() or resolved.stat().st_size > MAX_BUNDLE_BYTES:
            raise ReleaseEvidenceError("input must be a regular ZIP file within the size limit")
    except ReleaseEvidenceError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise ReleaseEvidenceError("input file is unavailable inside the workspace") from exc
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="release-evidence ZIP relative to the workspace")
    parser.add_argument(
        "--sha256",
        help="trusted expected SHA-256 of the complete ZIP, obtained out of band",
    )
    args = parser.parse_args()
    root = ROOT.resolve()
    try:
        bundle_path = _input_path(root, args.bundle)
        manifest = verify_release_evidence_bundle(
            bundle_path.read_bytes(), expected_sha256=args.sha256
        )
    except (OSError, ReleaseEvidenceError) as exc:
        parser.error(str(exc))
    verification = (
        "Archive SHA-256 and internal consistency verified"
        if args.sha256
        else "Internal consistency verified"
    )
    print(
        f"{verification} for {len(manifest['evidence'])} evidence files; "
        "readiness remains not_ready and evidence claims remain unverified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
