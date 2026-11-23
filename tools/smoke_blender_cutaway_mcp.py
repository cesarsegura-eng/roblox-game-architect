"""Run the Blender cutaway preview through a real loopback MCP server."""

from __future__ import annotations

import json
import secrets
import struct
import sys
import tempfile
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))

from api.blender_mcp import BlenderMCPClient  # noqa: E402
from apps.blender_mcp_server.server import BlenderMCPServer, BlenderSceneRenderer  # noqa: E402
from apps.roblox_mcp_server.assets import MAX_GLB_BYTES, _validate_glb  # noqa: E402
from core.worldbuilding import SceneRecipe  # noqa: E402

RECIPE_PATH = ROOT / "examples" / "worlds" / "desert-courtyard-home-v3" / "scene-recipe.json"
ROOF_OBJECT = "Deep shade roof canopy"


def _read_glb_document(data: bytes) -> dict[str, object]:
    if len(data) < 20:
        raise RuntimeError("Blender MCP returned a truncated GLB")
    magic, version, total_size = struct.unpack("<4sII", data[:12])
    json_size, chunk_type = struct.unpack("<I4s", data[12:20])
    if (
        magic != b"glTF"
        or version != 2
        or total_size != len(data)
        or chunk_type != b"JSON"
        or json_size > len(data) - 20
    ):
        raise RuntimeError("Blender MCP returned an invalid GLB v2 container")
    value = json.loads(data[20 : 20 + json_size])
    if not isinstance(value, dict):
        raise RuntimeError("Blender MCP GLB JSON chunk is not an object")
    return value


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python tools/smoke_blender_cutaway_mcp.py <Blender executable path>"
        )
    executable = Path(sys.argv[1]).resolve()
    recipe_value = json.loads(RECIPE_PATH.read_text(encoding="utf-8"))
    recipe = SceneRecipe.from_mapping(recipe_value)
    if not any(item.name == ROOF_OBJECT for item in recipe.objects):
        raise RuntimeError("the cutaway smoke recipe no longer contains its roof object")

    with tempfile.TemporaryDirectory(prefix="rga-cutaway-mcp-smoke-") as output_dir:
        renderer = BlenderSceneRenderer(executable, output_dir, project_root=ROOT)
        local_token = secrets.token_urlsafe(48)
        server = BlenderMCPServer("127.0.0.1", 0, renderer, local_token)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address[:2]
            client = BlenderMCPClient(f"http://{host}:{port}/mcp", local_token, timeout=240)
            client.check_connection()
            request_id = str(uuid.uuid4())
            receipt = client.apply_recipe(
                recipe_value,
                request_id,
                include_preview=True,
                preview_mode="cutaway",
            )
            if (
                receipt.request_id != request_id
                or receipt.object_count != recipe.rendered_object_count
            ):
                raise RuntimeError("Blender MCP returned an unexpected artifact receipt")
            preview = receipt.preview_png
            if not preview or preview[:8] != b"\x89PNG\r\n\x1a\n":
                raise RuntimeError("Blender MCP did not return the requested PNG preview")
            if struct.unpack(">II", preview[16:24]) != (512, 512):
                raise RuntimeError("Blender MCP preview is not 512x512")
            baseline = client.apply_recipe(
                recipe_value,
                str(uuid.uuid4()),
                include_preview=True,
            )
            if baseline.preview_png == preview:
                raise RuntimeError("cutaway preview is identical to the isometric roof view")

            artifact = client.download_artifact(
                receipt.artifact_id, expected_sha256=receipt.artifact_sha256
            )
            _validate_glb(artifact, MAX_GLB_BYTES)
            document = _read_glb_document(artifact)
            nodes = document.get("nodes")
            if not isinstance(nodes, list) or not any(
                isinstance(item, dict) and item.get("name") == ROOF_OBJECT for item in nodes
            ):
                raise RuntimeError("cutaway preview mode removed the roof from the exported GLB")
            print(
                "RGA_BLENDER_CUTAWAY_MCP_SMOKE_OK "
                f"objects={receipt.object_count} preview_bytes={len(preview)} "
                f"glb_bytes={len(artifact)} roof_retained=true "
                f"sha256={receipt.artifact_sha256}"
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    main()
