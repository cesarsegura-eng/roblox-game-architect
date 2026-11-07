"""Build a complete Roblox place artifact from a Scene Recipe using pinned Rojo."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from core.gameplay_templates import GAMEPLAY_MODES
from core.roblox_place import RobloxPlaceBuildError, RojoPlaceBuilder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipe", type=Path, help="path to a validated Scene Recipe JSON file")
    parser.add_argument("output", type=Path, help="destination .rbxlx place artifact")
    parser.add_argument(
        "--gameplay-mode",
        choices=sorted(GAMEPLAY_MODES),
        default="blockout",
        help="select a project-owned gameplay mode (default: blockout)",
    )
    parser.add_argument(
        "--gameplay-rules",
        type=Path,
        help="JSON array of bounded data-only rules required for rule_game mode",
    )
    parser.add_argument(
        "--rojo-bin",
        default="rojo",
        help="pinned Rojo executable or path (default: rojo on PATH)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing output artifact",
    )
    args = parser.parse_args()

    if args.output.suffix.lower() != ".rbxlx":
        parser.error("output must end in .rbxlx")
    if args.output.exists() and not args.overwrite:
        parser.error("output already exists; choose another path or pass --overwrite")

    try:
        payload = json.loads(args.recipe.read_text(encoding="utf-8"))
        gameplay_rules = (
            json.loads(args.gameplay_rules.read_text(encoding="utf-8"))
            if args.gameplay_rules is not None
            else None
        )
        build_arguments = {"gameplay_mode": args.gameplay_mode}
        if gameplay_rules is not None:
            build_arguments["gameplay_rules"] = gameplay_rules
        artifact = RojoPlaceBuilder(args.rojo_bin).build(payload, **build_arguments)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(artifact.place_file)
    except (OSError, UnicodeError, json.JSONDecodeError, RobloxPlaceBuildError) as exc:
        print(f"Place build failed: {exc}", file=sys.stderr)
        return 2

    digest = hashlib.sha256(artifact.place_file).hexdigest()
    print(
        f"Built {args.output} ({len(artifact.place_file)} bytes, SHA-256 {digest}, "
        f"mode {artifact.gameplay_mode}, {artifact.object_count} recipe objects, "
        f"{artifact.part_count} place Parts)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
