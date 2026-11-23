"""Validate a Blender Scene Recipe v1, v2, or v3 file before opening it in Blender."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.worldbuilding import SceneRecipe, WorldbuildingError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipe", type=Path, help="path to a Scene Recipe v1, v2, or v3 JSON file")
    args = parser.parse_args()
    try:
        text = args.recipe.read_text(encoding="utf-8")
        recipe = SceneRecipe.from_json(text)
    except (OSError, UnicodeError, WorldbuildingError) as exc:
        print(f"Invalid scene recipe: {exc}", file=sys.stderr)
        return 2
    print(
        f"Valid Scene Recipe v{recipe.schema_version}: {recipe.name} "
        f"({len(recipe.objects)} objects, {len(recipe.lights)} lights, "
        f"{len(recipe.characters)} characters, {recipe.rendered_object_count} Blender objects)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
