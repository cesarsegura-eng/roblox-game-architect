"""Synchronize the agent-facing skills with the canonical core skillpacks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages" / "core" / "skillpacks"
DESTINATION = ROOT / "skills"
CLAUDE_PLUGIN_DESTINATION = ROOT / "apps" / "claude-code-plugin" / "skills"
DESTINATIONS = (DESTINATION, CLAUDE_PLUGIN_DESTINATION)
CANONICAL_SKILL_RESOURCES = {
    "blender-scene-authoring": {
        Path("references/scene-recipe-v3.schema.json"): ROOT
        / "packages"
        / "core"
        / "schemas"
        / "scene-recipe-v3.schema.json",
        Path("references/research-sources.md"): ROOT
        / "docs"
        / "art-direction"
        / "research-sources.md",
    },
    "game-design-planning": {
        Path("references/game-plan-v2.schema.json"): ROOT
        / "packages"
        / "core"
        / "schemas"
        / "game-plan-v2.schema.json",
        Path("references/research-sources.md"): ROOT
        / "docs"
        / "art-direction"
        / "research-sources.md",
    },
    "world-environments": {
        Path("references/research-sources.md"): ROOT
        / "docs"
        / "art-direction"
        / "research-sources.md",
    },
    "character-modeling-animation": {
        Path("references/research-sources.md"): ROOT
        / "docs"
        / "art-direction"
        / "research-sources.md",
    },
}


def _skill_files(folder: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(folder): path.read_bytes()
        for suffix in ("*.md", "*.json")
        for path in folder.rglob(suffix)
        if path.is_file()
    }


def _expected_skill_files(source_folder: Path) -> dict[Path, bytes]:
    files = _skill_files(source_folder)
    for relative, source in CANONICAL_SKILL_RESOURCES.get(source_folder.name, {}).items():
        files[relative] = source.read_bytes()
    return files


def synchronize(*, check: bool) -> bool:
    valid = True
    for source_folder in sorted(path for path in SOURCE.iterdir() if path.is_dir()):
        expected = _expected_skill_files(source_folder)
        for root in DESTINATIONS:
            destination_folder = root / source_folder.name
            actual = _skill_files(destination_folder) if destination_folder.is_dir() else {}
            if check:
                if expected != actual:
                    missing = sorted(str(path) for path in expected.keys() - actual.keys())
                    extra = sorted(str(path) for path in actual.keys() - expected.keys())
                    changed = sorted(
                        str(path)
                        for path in expected.keys() & actual.keys()
                        if expected[path] != actual[path]
                    )
                    print(
                        f"{destination_folder.relative_to(ROOT)}: skill drift "
                        f"(missing={missing}, extra={extra}, changed={changed})",
                        file=sys.stderr,
                    )
                    valid = False
                continue
            destination_folder.mkdir(parents=True, exist_ok=True)
            for relative, content in expected.items():
                output = destination_folder / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(content)
    return valid


def create_archive(path: Path) -> None:
    """Write a reproducible ZIP of skills and their portable reference resources."""
    path = path.resolve()
    if path.is_relative_to(DESTINATION.resolve()):
        raise ValueError("archive path must be outside the skills source directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        skill_files = sorted(
            path
            for suffix in ("*.md", "*.json")
            for path in DESTINATION.rglob(suffix)
            if path.is_file()
        )
        for skill_file in skill_files:
            relative = skill_file.relative_to(DESTINATION.parent).as_posix()
            entry = ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(
                entry,
                skill_file.read_bytes(),
                compress_type=ZIP_DEFLATED,
                compresslevel=9,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if portable skills differ from packages/core/skillpacks",
    )
    parser.add_argument(
        "--archive",
        type=Path,
        metavar="PATH",
        help="write a reproducible ZIP containing the portable skills/ directory",
    )
    args = parser.parse_args()
    if not synchronize(check=args.check):
        return 1
    if args.archive:
        create_archive(args.archive)
        print(f"Agent skills archived at {args.archive}.")
        return 0
    print("Agent skill packs are synchronized." if args.check else "Agent skill packs packaged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
