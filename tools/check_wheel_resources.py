"""Fail when a built wheel omits repository-owned Roblox Luau harnesses."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

REQUIRED_RESOURCES = {
    "apps/roblox_mcp_server/harness.luau",
    "apps/roblox_mcp_server/model_import_harness.luau",
    "core/reference_scenes.json",
}


def check_wheel(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            members = set(archive.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"not a readable wheel archive: {path}") from exc

    missing = REQUIRED_RESOURCES - members
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"wheel is missing required Roblox harness resources: {names}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    try:
        check_wheel(args.wheel)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Roblox harness resources are present in {args.wheel.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
