"""Operator command for generating a bounded Blender recipe through core."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.budget import SpendBudgetError
from core.llm import create_provider
from core.llm.types import LLMError
from core.worldbuilding import WorldbuildingError, WorldBuildResult, WorldDesignAgent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Blender scene recipe from a world brief"
    )
    parser.add_argument("brief", help="Describe the biome, gameplay, architecture, and mood")
    parser.add_argument("output", type=Path, help="New .json output path (must not already exist)")
    args = parser.parse_args(argv)
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        provider = create_provider()
        result: WorldBuildResult = WorldDesignAgent(provider).generate(args.brief)
        destination = result.write_recipe(args.output)
    except (WorldbuildingError, SpendBudgetError, LLMError, OSError, ValueError) as exc:
        print(f"world recipe generation failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"Wrote {destination} ({len(result.recipe.objects)} objects, "
        f"{len(result.recipe.lights)} lights; {result.iterations} generation call(s))."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
