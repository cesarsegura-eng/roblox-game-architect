"""Validate a generated Treasure Hunt place and simulate its trusted template."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from api.roblox_mcp import RobloxMCPError, _validate_place_scripts
from core.gameplay_templates import (
    GameplayTemplateError,
    treasure_hunt_source,
    validate_gameplay_mode,
)
from core.roblox_place import MAX_PLACE_FILE_BYTES
from core.worldbuilding import SceneRecipe

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/worlds/rainforest-checkpoint-obby"
INTERACTIVE_ROLES = frozenset({"collectible", "hazard"})


def check(place: Path, lute: str, recipe_path: Path = EXAMPLE / "scene-recipe.json") -> None:
    """Verify the generated place shape and run only the repository-owned source."""
    with place.open("rb") as stream:
        data = stream.read(MAX_PLACE_FILE_BYTES + 1)
    if (
        len(data) > MAX_PLACE_FILE_BYTES
        or not data.startswith(b"<roblox")
        or b"<!DOCTYPE" in data.upper()
        or b"<!ENTITY" in data.upper()
    ):
        raise ValueError("Expected a bounded RBXLX from the rainforest build")
    document = ET.fromstring(data)  # noqa: S314 - bounded XML with DTD and entities rejected.
    recipe = SceneRecipe.from_mapping(json.loads(recipe_path.read_bytes()))
    try:
        validate_gameplay_mode("treasure_hunt", recipe, None)
        _validate_place_scripts(document, "treasure_hunt")
    except (GameplayTemplateError, RobloxMCPError) as exc:
        raise ValueError("The place does not contain the reviewed Treasure Hunt template") from exc

    map_model = next(
        (
            item
            for item in document.iter("Item")
            if item.get("class") == "Model"
            and item.findtext("Properties/string[@name='Name']") == recipe.name
        ),
        None,
    )
    if map_model is None:
        raise ValueError("The generated place is missing its recipe model")
    folders = {
        item.findtext("Properties/string[@name='Name']"): item
        for item in map_model.findall("Item[@class='Folder']")
    }
    expected_counts = Counter(
        item.role for item in recipe.objects if item.role in INTERACTIVE_ROLES
    )
    for role, expected_count in expected_counts.items():
        folder = folders.get(role.title())
        parts = folder.findall("Item") if folder is not None else []
        if len(parts) != expected_count or any(
            part.get("class") != "Part"
            or part.findtext("Properties/bool[@name='CanTouch']", "true") != "true"
            for part in parts
        ):
            raise ValueError(f"Serialized {role} triggers do not match the reviewed recipe")

    spawn_locations = [
        item
        for item in map_model.iter("Item")
        if item.get("class") == "SpawnLocation"
        and item.findtext("Properties/string[@name='Name']") == "RGA Spawn"
    ]
    if (
        len(spawn_locations) != 1
        or spawn_locations[0].findtext("Properties/bool[@name='CanTouch']", "true") != "true"
    ):
        raise ValueError("The generated Treasure Hunt place needs one touch-enabled start spawn")

    with tempfile.TemporaryDirectory(prefix="rga-treasure-hunt-") as temporary:
        root = Path(temporary)
        (root / "server.luau").write_text(
            "return function(game, Instance, task)\n" + treasure_hunt_source() + "\nend\n",
            encoding="utf-8",
        )
        scenario = root / "treasure_hunt_simulation.luau"
        fixture = (
            Path(__file__).resolve().parents[1]
            / "packages/sandbox/tests/treasure_hunt_simulation.luau"
        )
        shutil.copyfile(fixture, scenario)
        subprocess.run([lute, "run", str(scenario)], check=True, timeout=15)  # noqa: S603


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("place", type=Path)
    parser.add_argument(
        "--recipe",
        type=Path,
        default=EXAMPLE / "scene-recipe.json",
        help="scene recipe used to build this place (default: rainforest checkpoint fixture)",
    )
    parser.add_argument("--lute", default="lute")
    arguments = parser.parse_args()
    check(arguments.place, arguments.lute, arguments.recipe)
