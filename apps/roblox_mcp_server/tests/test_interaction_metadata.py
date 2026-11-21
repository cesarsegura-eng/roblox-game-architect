from __future__ import annotations

from types import SimpleNamespace

from apps.roblox_mcp_server.server import (
    ASSET_UPLOAD_TOOL_NAME,
    COMMIT_BLENDER_UPLOAD_TOOL_NAME,
    COMMIT_DIRECT_PUBLISH_TOOL_NAME,
    PLACE_PUBLISH_TOOL_NAME,
    _tool_definitions_for_server,
)


def test_persistent_roblox_writes_in_the_published_tool_list_require_human_interaction() -> None:
    server = SimpleNamespace(
        validation_enabled=True,
        place_builder=object(),
        downloads=object(),
        asset_uploader=object(),
        blender_artifact_source=object(),
        model_upload_ledger=object(),
        place_publisher=object(),
    )
    tools = {tool["name"]: tool for tool in _tool_definitions_for_server(server)}

    for name in (
        ASSET_UPLOAD_TOOL_NAME,
        COMMIT_BLENDER_UPLOAD_TOOL_NAME,
        COMMIT_DIRECT_PUBLISH_TOOL_NAME,
        PLACE_PUBLISH_TOOL_NAME,
    ):
        assert tools[name]["_meta"]["anthropic/requiresUserInteraction"] is True
