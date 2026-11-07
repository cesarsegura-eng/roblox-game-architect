from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.roblox_mcp_server.smoke_server import _SmokeValidator, main

_ROOT = Path(__file__).resolve().parents[3]
_RECIPE = json.loads(
    (_ROOT / "examples/worlds/mistral-coast-lookout-v2/scene-recipe.json").read_text(
        encoding="utf-8"
    )
)


def test_fake_mcp_server_requires_explicit_test_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RGA_ROBLOX_MCP_SMOKE", raising=False)

    with pytest.raises(SystemExit, match="test-only fake validator mode"):
        main()


def test_smoke_validator_returns_only_a_fake_bounded_receipt() -> None:
    receipt = _SmokeValidator().validate_recipe(_RECIPE)

    assert receipt == {
        "task_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "validation_status": "structure_only",
        "object_count": len(_RECIPE["objects"]),
        "path_feature_count": sum(item["role"] == "path" for item in _RECIPE["objects"]),
        "navigation_waypoint_count": 0,
        "navigation_connected": False,
    }
