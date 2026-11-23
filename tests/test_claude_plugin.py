"""Keep the Claude plugin aligned with RGA's remote-tool architecture."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "apps/claude-code-plugin"


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_claude_plugin_only_adds_remote_blender_mcp() -> None:
    manifest = _read_json(PLUGIN_ROOT / ".claude-plugin/plugin.json")
    configuration = _read_json(PLUGIN_ROOT / ".mcp.json")
    user_config = manifest["userConfig"]
    servers = configuration["mcpServers"]

    assert isinstance(user_config, dict)
    assert isinstance(servers, dict)
    assert set(servers) == {"rga-blender"}
    assert set(user_config) == {"blender_mcp_host", "blender_mcp_token"}

    server = servers["rga-blender"]
    assert isinstance(server, dict)
    assert server == {
        "type": "http",
        "url": "https://${user_config.blender_mcp_host}/mcp",
        "headers": {
            "Authorization": "Bearer ${user_config.blender_mcp_token}",
        },
    }

    host = user_config["blender_mcp_host"]
    token = user_config["blender_mcp_token"]
    assert isinstance(host, dict)
    assert isinstance(token, dict)
    assert host["type"] == token["type"] == "string"
    assert host["required"] is True
    assert token["required"] is True
    assert token["sensitive"] is True


def test_claude_marketplace_points_to_the_plugin_directory() -> None:
    marketplace = _read_json(ROOT / ".claude-plugin/marketplace.json")
    plugins = marketplace["plugins"]

    assert isinstance(plugins, list)
    assert len(plugins) == 1
    plugin = plugins[0]
    assert isinstance(plugin, dict)
    source = plugin["source"]
    assert isinstance(source, dict)
    assert source["source"] == "git-subdir"
    assert source["path"] == "apps/claude-code-plugin"
