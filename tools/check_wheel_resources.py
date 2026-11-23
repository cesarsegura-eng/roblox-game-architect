"""Fail when a built wheel omits resources required by deployed services."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

REQUIRED_RESOURCES = {
    "apps/roblox_mcp_server/harness.luau",
    "apps/roblox_mcp_server/model_import_harness.luau",
    "apps/blender_mcp_server/server.py",
    "apps/blender_mcp_server/worker.py",
    "apps/web/index.html",
    "apps/web/app.js",
    "apps/web/style.css",
    "core/schemas/game-plan-v2.schema.json",
    "core/schemas/game-plan-v1.schema.json",
    "core/schemas/release-evidence-bundle-v1.schema.json",
    "core/schemas/scene-recipe-v3.schema.json",
    "core/schemas/scene-recipe-v2.schema.json",
    "core/schemas/scene-recipe-v1.schema.json",
    "core/schemas/release-readiness-v1.schema.json",
    "core/skillpacks/blender-scene-authoring/SKILL.md",
    "core/skillpacks/blender-scene-authoring/references/scene-recipes.md",
    "core/skillpacks/character-modeling-animation/SKILL.md",
    "core/skillpacks/character-modeling-animation/references/character-art.md",
    "core/skillpacks/game-design-planning/SKILL.md",
    "core/skillpacks/game-design-planning/references/game-plan-v2.md",
    "core/skillpacks/game-design-planning/references/production-readiness.md",
    "core/skillpacks/roblox-game-architect/SKILL.md",
    "core/skillpacks/roblox-gameplay-engineering/SKILL.md",
    "core/skillpacks/roblox-gameplay-engineering/references/server-systems.md",
    "core/skillpacks/roblox-studio-map-blockouts/SKILL.md",
    "core/skillpacks/roblox-terrain-authoring/SKILL.md",
    "core/skillpacks/roblox-terrain-authoring/references/terrain-recipes.md",
    "core/skillpacks/roblox-ui-ux/SKILL.md",
    "core/skillpacks/roblox-ui-ux/references/ui-systems.md",
    "core/skillpacks/world-environments/SKILL.md",
    "core/skillpacks/world-environments/references/biomes-and-levels.md",
    "core/skillpacks/world-environments/references/environment-effects.md",
    "core/skillpacks/world-environments/references/playable-spaces.md",
    "core/reference_scenes.json",
    "sandbox/luau_policy.json",
    "sandbox/lute/check_syntax.luau",
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
        raise ValueError(f"wheel is missing required runtime resources: {names}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    try:
        check_wheel(args.wheel)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Required runtime resources are present in {args.wheel.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
