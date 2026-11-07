"""Build the reference game's art and playable place on two configured MCP hosts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from pathlib import Path

from api.blender_mcp import BlenderMCPClient
from api.roblox_mcp import RobloxMCPClient

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/worlds/rainforest-checkpoint-obby"


def build(output: Path) -> Path:
    blender = BlenderMCPClient(
        os.environ["BLENDER_MCP_URL"], os.environ["BLENDER_MCP_BEARER_TOKEN"]
    )
    roblox = RobloxMCPClient(os.environ["ROBLOX_MCP_URL"], os.environ["ROBLOX_MCP_BEARER_TOKEN"])
    recipe = json.loads((EXAMPLE / "scene-recipe.json").read_text(encoding="utf-8"))
    rules = json.loads((EXAMPLE / "gameplay-rules.json").read_text(encoding="utf-8"))
    blender.check_connection()
    roblox.check_connection()
    run_id = str(uuid.uuid4())
    art = blender.apply_recipe(recipe, run_id)
    glb = blender.download_artifact(art.artifact_id)
    place = roblox.build_place(recipe, run_id, gameplay_mode="rule_game", gameplay_rules=rules)
    # The manifest is written last. Its presence marks a complete pair of downloads.
    folder = output / run_id
    folder.mkdir(parents=True)
    (folder / "rainforest.glb").write_bytes(glb)
    (folder / "rainforest.rbxlx").write_bytes(place.place_file)
    manifest = {
        "request_id": run_id,
        "scene": art.recipe_name,
        "blender_artifact_id": art.artifact_id,
        "glb_sha256": hashlib.sha256(glb).hexdigest(),
        "place_sha256": place.sha256,
        "place_parts": place.part_count,
        "gameplay_rules": rules,
        "imported_meshparts": place.imported_meshpart_count,
    }
    (folder / "receipt.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist/rainforest-builds"))
    try:
        print(build(parser.parse_args().output))
    except KeyError as exc:
        raise SystemExit(f"Missing configuration: {exc}") from exc
