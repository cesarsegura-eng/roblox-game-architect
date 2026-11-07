"""Package reviewed example inputs for agent access without a source checkout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "packages/core/reference_scenes.json"
SOURCES = {
    "rainforest-scene": (
        "rainforest-checkpoint-obby/scene-recipe.json",
        "Connected rainforest map with collectible, hazard and landmark roles.",
    ),
    "rainforest-plan": (
        "rainforest-checkpoint-obby/game-plan.json",
        "First playable collect-and-win plan; session-only prototype.",
    ),
    "rainforest-rules": (
        "rainforest-checkpoint-obby/gameplay-rules.json",
        "Data-only scoring, hazard and victory rules for the rainforest scene.",
    ),
    "desert-home": (
        "desert-courtyard-home-v3/scene-recipe.json",
        "Courtyard house with rooms, openings and environment settings.",
    ),
    "coastal-lookout": (
        "mistral-coast-lookout-v2/scene-recipe.json",
        "Coastal architecture and landscape with custom mesh geometry.",
    ),
    "alpine-inn": ("evaluation/alpine-inn.json", "Snowy biome and timber building blockout."),
    "mangrove-house": (
        "evaluation/mangrove-stilt-house.json",
        "Wetland house with connected interior and exterior spaces.",
    ),
    "character-movement": (
        "evaluation/guard-walk-cycle.json",
        "Blender character and motion recipes; Roblox rig import is not implied.",
    ),
}


def render() -> str:
    references = {}
    for name, (relative, description) in SOURCES.items():
        payload = json.loads((ROOT / "examples/worlds" / relative).read_bytes())
        references[name] = {
            "description": description + " Reference input, not production acceptance evidence.",
            "source": f"examples/worlds/{relative}",
            "text": json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        }
    return json.dumps(references, ensure_ascii=True, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            raise SystemExit(
                "Packaged reference scenes have drifted; run this tool without --check"
            )
    else:
        OUTPUT.write_text(expected, encoding="utf-8")
    print("Reference scenes are synchronized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
