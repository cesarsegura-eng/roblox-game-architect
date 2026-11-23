"""Package the Blender extension as a ZIP that Blender installs from disk."""

from __future__ import annotations

import argparse
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "apps" / "blender-addon"
FILES = (
    Path("blender_manifest.toml"),
    Path("rga_scene_builder") / "__init__.py",
    Path("rga_scene_builder") / "character_tools.py",
    Path("rga_scene_builder") / "recipe_contract.py",
)


def extension_version() -> str:
    """Read the package version from Blender's canonical extension manifest."""
    with (EXTENSION / "blender_manifest.toml").open("rb") as manifest_file:
        manifest = tomllib.load(manifest_file)
    version = manifest.get("version")
    if (
        not isinstance(version, str)
        or not version
        or any(character not in "0123456789." for character in version)
    ):
        raise ValueError("Blender manifest has an invalid extension version")
    return version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=None,
        help="ZIP output path (default uses the extension version in blender_manifest.toml)",
    )
    args = parser.parse_args()
    try:
        version = extension_version()
    except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
        print(f"Could not read Blender extension version: {exc}", file=sys.stderr)
        return 2
    destination = (
        args.output.resolve()
        if args.output is not None
        else (ROOT / "dist" / f"roblox-game-architect-blender-{version}.zip").resolve()
    )
    if destination.suffix.lower() != ".zip":
        print("Output path must end with .zip", file=sys.stderr)
        return 2
    if destination.exists():
        print(f"Refusing to overwrite existing package: {destination}", file=sys.stderr)
        return 2
    missing = [relative for relative in FILES if not (EXTENSION / relative).is_file()]
    if missing:
        print(f"Extension source is incomplete: {missing}", file=sys.stderr)
        return 2
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in FILES:
            archive.write(EXTENSION / relative, relative.name)
    print(f"Created Blender extension package: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
