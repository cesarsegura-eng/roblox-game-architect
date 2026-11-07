"""Exercise the reference place's fixed gameplay script with simulated Roblox events."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from api.roblox_mcp import _validate_place_scripts
from core.gameplay_templates import rule_game_source, validate_gameplay_rules
from core.roblox_place import MAX_PLACE_FILE_BYTES, validate_gameplay_rules_artifact
from core.worldbuilding import SceneRecipe

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/worlds/rainforest-checkpoint-obby"


def check(place: Path, lute: str) -> None:
    with place.open("rb") as stream:
        data = stream.read(MAX_PLACE_FILE_BYTES + 1)
    if (
        len(data) > MAX_PLACE_FILE_BYTES
        or not data.startswith(b"<roblox")
        or b"<!DOCTYPE" in data.upper()
        or b"<!ENTITY" in data.upper()
    ):
        raise ValueError("Expected bounded RBXLX from the rainforest build")
    tree = ET.fromstring(data)  # noqa: S314 - bounded XML with no DTD or entities.
    recipe = SceneRecipe.from_mapping(json.loads((EXAMPLE / "scene-recipe.json").read_bytes()))
    rules = validate_gameplay_rules(
        json.loads((EXAMPLE / "gameplay-rules.json").read_bytes()), recipe
    )
    _validate_place_scripts(tree, "rule_game")
    validate_gameplay_rules_artifact(tree, "rule_game", rules, recipe)
    folders = {
        folder.findtext("Properties/string[@name='Name']"): folder
        for model in tree.iter("Item")
        if model.get("class") == "Model"
        and model.findtext("Properties/string[@name='Name']") == recipe.name
        for folder in model.findall("Item[@class='Folder']")
    }
    for role, count in (("Collectible", 3), ("Hazard", 1), ("Landmark", 1)):
        parts = folders[role].findall("Item")
        if len(parts) != count or any(
            part.get("class") != "Part"
            or part.findtext("Properties/bool[@name='CanTouch']", "true") != "true"
            for part in parts
        ):
            raise ValueError(f"The compiled {role} triggers differ from the round fixture")
    # Use the reviewed template after byte-for-byte source verification. Never
    # execute text taken from the supplied place.
    with tempfile.TemporaryDirectory(prefix="rga-round-") as temporary:
        root = Path(temporary)
        (root / "server.luau").write_text(
            "return function(game, Instance, task, UDim2, Color3)\n"
            + rule_game_source()
            + "\nend\n",
            encoding="utf-8",
        )
        rows = [
            "{" + ", ".join(f"{key} = {json.dumps(value)}" for key, value in rule.items()) + "}"
            for rule in rules
        ]
        (root / "rules.luau").write_text("return {" + ",\n".join(rows) + "}", encoding="utf-8")
        scenario = root / "rainforest_round.luau"
        shutil.copyfile(Path(__file__).with_name(scenario.name), scenario)
        subprocess.run([lute, "run", str(scenario)], check=True, timeout=15)  # noqa: S603


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("place", type=Path)
    parser.add_argument("--lute", default="lute")
    args = parser.parse_args()
    check(args.place, args.lute)
