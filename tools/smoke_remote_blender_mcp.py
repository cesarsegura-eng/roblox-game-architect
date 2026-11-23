"""Exercise the remote MCP contract against a live Blender server container."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))

from api.blender_mcp import BlenderMCPClient  # noqa: E402
from apps.roblox_mcp_server.assets import MAX_GLB_BYTES, _validate_glb  # noqa: E402
from core.worldbuilding import SceneRecipe  # noqa: E402


def _load_recipe() -> dict[str, object]:
    path = ROOT / "examples" / "worlds" / "mistral-coast-lookout-v2" / "scene-recipe.json"
    recipe = json.loads(path.read_text(encoding="utf-8"))
    recipe["characters"] = [
        {
            "name": "Remote Smoke Walker",
            "motion": "WALK",
            "location": [20, 0, 0],
            "scale": [1, 1, 1],
        },
        {
            "name": "Remote Smoke Idle",
            "motion": "IDLE",
            "location": [24, 0, 0],
            "scale": [1, 1, 1],
        },
    ]
    return recipe


def _read_glb_document(data: bytes) -> dict[str, object]:
    if len(data) < 20:
        raise RuntimeError("remote MCP returned a truncated GLB")
    magic, version, total_size = struct.unpack("<4sII", data[:12])
    json_size, chunk_type = struct.unpack("<I4s", data[12:20])
    if (
        magic != b"glTF"
        or version != 2
        or total_size != len(data)
        or chunk_type != b"JSON"
        or json_size > len(data) - 20
    ):
        raise RuntimeError("remote MCP returned an invalid GLB v2 container")
    document = json.loads(data[20 : 20 + json_size])
    if not isinstance(document, dict):
        raise RuntimeError("remote MCP GLB JSON chunk is not an object")
    return document


def main() -> None:
    endpoint = os.environ.get("BLENDER_MCP_URL", "")
    token = os.environ.get("BLENDER_MCP_BEARER_TOKEN", "")
    if not endpoint or not token:
        raise RuntimeError("BLENDER_MCP_URL and BLENDER_MCP_BEARER_TOKEN are required")

    recipe = _load_recipe()
    expected_objects = SceneRecipe.from_mapping(recipe).rendered_object_count
    request_id = str(uuid.uuid4())
    client = BlenderMCPClient(endpoint, token, timeout=240)
    receipt = client.apply_recipe(recipe, request_id, include_preview=True)
    if receipt.request_id != request_id or receipt.object_count != expected_objects:
        raise RuntimeError("remote MCP returned an unexpected build receipt")
    if not receipt.preview_png or receipt.preview_png[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("remote MCP did not return the requested PNG preview")

    artifact = client.download_artifact(
        receipt.artifact_id, expected_sha256=receipt.artifact_sha256
    )
    artifact_sha256 = hashlib.sha256(artifact).hexdigest()
    if not hmac.compare_digest(artifact_sha256, receipt.artifact_sha256):
        raise RuntimeError("remote MCP GLB does not match its receipt SHA-256")
    try:
        _validate_glb(artifact, MAX_GLB_BYTES)
    except ValueError as exc:
        raise RuntimeError("remote Blender GLB failed the Roblox asset preflight") from exc
    document = _read_glb_document(artifact)
    extensions = document.get("extensionsUsed", [])
    if not isinstance(extensions, list) or "KHR_lights_punctual" in extensions:
        raise RuntimeError("remote Blender GLB contains a Roblox-unsupported light extension")
    if any(
        not isinstance(document.get(key), list) or not document[key]
        for key in ("meshes", "skins", "animations")
    ):
        raise RuntimeError("remote GLB is missing meshes, skins, or animations")
    print(
        "RGA_REMOTE_BLENDER_SMOKE_OK "
        f"objects={receipt.object_count} meshes={len(document['meshes'])} "
        f"skins={len(document['skins'])} animations={len(document['animations'])} "
        f"preview_bytes={len(receipt.preview_png)} "
        "roblox_preflight=passed "
        f"sha256={artifact_sha256}"
    )


if __name__ == "__main__":
    main()
