"""Validate and simulate the fixed Obby script in a built rainforest place."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from api.roblox_mcp import RobloxMCPError, _validate_place_scripts
from core.gameplay_templates import obby_course_source, validate_gameplay_mode
from core.roblox_place import MAX_PLACE_FILE_BYTES
from core.worldbuilding import SceneRecipe

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/worlds/rainforest-checkpoint-obby"


def check(place: Path, lute: str) -> None:
    """Validate a generated artifact, then exercise only the trusted template."""
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
    recipe = SceneRecipe.from_mapping(json.loads((EXAMPLE / "scene-recipe.json").read_bytes()))
    validate_gameplay_mode("obby", recipe, None)
    try:
        _validate_place_scripts(document, "obby")
    except RobloxMCPError as exc:
        raise ValueError("The place does not contain the reviewed Obby template") from exc

    expected_checkpoints = [
        f"{index:03d} Checkpoint"
        for index, _ in enumerate((item for item in recipe.objects if item.role == "path"), start=1)
    ]
    spawn_items = [item for item in document.iter("Item") if item.get("class") == "SpawnLocation"]
    serialized_names = [item.findtext("Properties/string[@name='Name']") for item in spawn_items]
    if sorted(serialized_names) != expected_checkpoints:
        raise ValueError("Serialized Obby checkpoints do not match the ordered path recipe")
    if any(
        item.findtext("Properties/bool[@name='Enabled']", "true") != "true"
        or item.findtext("Properties/bool[@name='CanTouch']", "true") != "true"
        for item in spawn_items
    ):
        raise ValueError("Serialized Obby checkpoints are not touch-enabled")

    with tempfile.TemporaryDirectory(prefix="rga-obby-") as temporary:
        root = Path(temporary)
        (root / "server.luau").write_text(
            "return function(game, Instance, Vector3)\n" + obby_course_source() + "\nend\n",
            encoding="utf-8",
        )
        scenario = root / "rainforest_obby.luau"
        shutil.copyfile(Path(__file__).with_name(scenario.name), scenario)
        subprocess.run([lute, "run", str(scenario)], check=True, timeout=15)  # noqa: S603


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("place", type=Path)
    parser.add_argument("--lute", default="lute")
    args = parser.parse_args()
    check(args.place, args.lute)
