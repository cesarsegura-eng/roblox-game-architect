from __future__ import annotations

from pathlib import Path

from api.roblox_mcp import MAX_GLB_UPLOAD_BYTES
from apps.roblox_mcp_server.assets import MAX_GLB_BYTES
from apps.roblox_mcp_server.blender_transfer import MAX_ARTIFACT_DOWNLOAD_BYTES
from apps.roblox_mcp_server.server import (
    MAX_GLB_BASE64_LENGTH,
    MAX_REQUEST_BYTES,
    _asset_upload_tool_definition,
)
from core.asset_limits import ROBLOX_MODEL_UPLOAD_MAX_BYTES

ROOT = Path(__file__).resolve().parents[1]


def test_model_size_limit_is_shared_by_upload_and_transfer_paths() -> None:
    assert ROBLOX_MODEL_UPLOAD_MAX_BYTES == 19 * 1024 * 1024
    assert MAX_GLB_UPLOAD_BYTES == ROBLOX_MODEL_UPLOAD_MAX_BYTES
    assert MAX_GLB_BYTES == ROBLOX_MODEL_UPLOAD_MAX_BYTES
    assert MAX_ARTIFACT_DOWNLOAD_BYTES == ROBLOX_MODEL_UPLOAD_MAX_BYTES
    env_example = (ROOT / "apps/roblox_mcp_server/deploy/server.env.example").read_text(
        encoding="utf-8"
    )
    assert f"RGA_ROBLOX_MAX_GLB_BYTES={ROBLOX_MODEL_UPLOAD_MAX_BYTES}" in env_example


def test_mcp_base64_schema_and_http_limit_cover_the_shared_glb_cap() -> None:
    expected_base64_length = 4 * ((ROBLOX_MODEL_UPLOAD_MAX_BYTES + 2) // 3)
    assert MAX_GLB_BASE64_LENGTH == expected_base64_length
    assert MAX_REQUEST_BYTES > expected_base64_length + 4_096

    tool = _asset_upload_tool_definition()
    encoded_glb = tool["inputSchema"]["properties"]["glb_base64"]
    assert encoded_glb["maxLength"] == MAX_GLB_BASE64_LENGTH
