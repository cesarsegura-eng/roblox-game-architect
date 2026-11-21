"""Agent access to packaged guides through the authenticated MCP endpoint."""

from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

import pytest

from apps.roblox_mcp_server.server import RobloxMCPServer


@pytest.fixture
def rpc():
    token = "k" * 40
    with RobloxMCPServer("127.0.0.1", 0, None, None, token) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def post(method, params, *, authorized=True):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            headers = {"Content-Type": "application/json", "MCP-Protocol-Version": "2025-11-25"}
            if authorized:
                headers["Authorization"] = f"Bearer {token}"
            try:
                connection.request(
                    "POST",
                    "/mcp",
                    body=json.dumps(
                        {"jsonrpc": "2.0", "method": method, "id": 7, "params": params}
                    ),
                    headers=headers,
                )
                response = connection.getresponse()
                body = response.read()
                return response.status, json.loads(body) if response.status == 200 else None
            finally:
                connection.close()

        try:
            yield post
        finally:
            server.shutdown()
            worker.join(timeout=2)


def test_agent_corrects_recipe_and_unwinnable_plan_before_building(rpc):
    sample = Path(__file__).resolve().parents[3] / "examples/worlds/rainforest-checkpoint-obby"
    plan = json.loads((sample / "game-plan.json").read_bytes())
    recipe = json.loads((sample / "scene-recipe.json").read_bytes())
    _, listing = rpc("tools/list", {})
    assert "rga_review_game_plan" in {tool["name"] for tool in listing["result"]["tools"]}

    def review(**inputs):
        _, reply = rpc("tools/call", {"name": "rga_review_game_plan", "arguments": inputs})
        return reply["result"]

    plan_only = review(plan=plan)["structuredContent"]
    assert plan_only["review"] == "plan_only"
    assert set(plan_only["required_scene_roles"]) == {"path", "collectible", "landmark", "hazard"}
    item = recipe["objects"][0]
    original_scale = item["scale"]
    item["scale"] = [10**400, 1, 1]
    invalid = review(plan=plan, recipe=recipe)
    assert invalid["isError"] and "objects[0]: scale" in invalid["content"][0]["text"]
    item["scale"] = original_scale
    rules = plan["playable_slice"]["gameplay_rules"]
    rules[-1]["minimum_points"] = 4
    invalid = review(plan=plan, recipe=recipe)
    assert invalid["isError"] and "3 per round" in invalid["content"][0]["text"]
    rules[-1]["minimum_points"] = 3
    valid = review(plan=plan, recipe=recipe)["structuredContent"]
    assert valid["review"] == "plan_and_recipe"
    assert valid["build_settings"] == {
        "gameplay_mode": "rule_game",
        "gameplay_rules": json.loads((sample / "gameplay-rules.json").read_bytes()),
    }
    rules = valid["build_settings"]["gameplay_rules"]
    accepted = rpc(
        "tools/call",
        {
            "name": "rga_build_place",
            "arguments": {
                "plan": plan,
                "recipe": recipe,
                "request_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                **valid["build_settings"],
            },
        },
    )[1]
    assert (
        accepted["result"]["structuredContent"]["gameplay_mode"]
        == valid["build_settings"]["gameplay_mode"]
    )
    mode_mismatch = rpc(
        "tools/call",
        {
            "name": "rga_build_place",
            "arguments": {
                "plan": plan,
                "recipe": recipe,
                "request_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "gameplay_mode": "obby",
            },
        },
    )[1]["result"]
    assert mode_mismatch["isError"]
    assert "do not match" in mode_mismatch["content"][0]["text"]
    rule_mismatch = rpc(
        "tools/call",
        {
            "name": "rga_build_place",
            "arguments": {
                "plan": plan,
                "recipe": recipe,
                "request_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                "gameplay_mode": "rule_game",
                "gameplay_rules": [
                    {**rules[0], "amount": rules[0]["amount"] + 1},
                    *rules[1:],
                ],
            },
        },
    )[1]["result"]
    assert rule_mismatch["isError"]
    assert "do not match" in rule_mismatch["content"][0]["text"]


def test_authenticated_agent_can_discover_and_read_all_packaged_guides_and_schemas(rpc):
    status, init = rpc(
        "initialize",
        {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    )
    assert status == 200
    assert init["result"]["capabilities"]["resources"] == {}
    assert "rga://skills/roblox-game-architect" in init["result"]["instructions"]
    _, listing = rpc("resources/list", {"_meta": {}})
    assert "nextCursor" not in listing["result"]
    entries = listing["result"]["resources"]
    texts = {}
    for entry in entries:
        uri = entry["uri"]
        _, reply = rpc("resources/read", {"uri": uri})
        (content,) = reply["result"]["contents"]
        assert content["uri"] == uri
        assert content["mimeType"] == entry["mimeType"]
        assert 0 < len(content["text"].encode("utf-8")) <= 96 * 1024
        texts[uri] = content["text"]
    assert set(texts) == {
        "rga://skills/roblox-game-architect",
        "rga://skills/game-design-planning",
        "rga://skills/world-environments",
        "rga://skills/blender-scene-authoring",
        "rga://skills/character-modeling-animation",
        "rga://skills/roblox-studio-map-blockouts",
        "rga://schemas/scene-recipe-v3",
        "rga://schemas/game-plan-v2",
        "rga://examples/rainforest-scene",
        "rga://examples/rainforest-plan",
        "rga://examples/rainforest-rules",
        "rga://examples/desert-home",
        "rga://examples/coastal-lookout",
        "rga://examples/alpine-inn",
        "rga://examples/mangrove-house",
        "rga://examples/character-movement",
    }
    assert "# Biomes and playable-space reference" in texts["rga://skills/world-environments"]
    assert json.loads(texts["rga://schemas/scene-recipe-v3"])["properties"]["schema_version"] == {
        "const": 3
    }
    assert json.loads(texts["rga://schemas/game-plan-v2"])["properties"]["schema_version"] == {
        "const": 2
    }
    _, templates = rpc("resources/templates/list", {})
    assert templates["result"] == {"resourceTemplates": []}


def test_remote_examples_are_valid_inputs_and_can_be_reviewed_together(rpc):
    from core.worldbuilding import SceneRecipe

    def read(name):
        _, result = rpc("resources/read", {"uri": f"rga://examples/{name}"})
        return json.loads(result["result"]["contents"][0]["text"])

    for name in (
        "rainforest-scene",
        "desert-home",
        "coastal-lookout",
        "alpine-inn",
        "mangrove-house",
        "character-movement",
    ):
        SceneRecipe.from_mapping(read(name))
    plan, scene, rules = read("rainforest-plan"), read("rainforest-scene"), read("rainforest-rules")
    _, reviewed = rpc(
        "tools/call", {"name": "rga_review_game_plan", "arguments": {"plan": plan, "recipe": scene}}
    )
    assert reviewed["result"]["structuredContent"]["build_settings"] == {
        "gameplay_mode": "rule_game",
        "gameplay_rules": rules,
    }


def test_unknown_or_malformed_resource_requests_are_rejected(rpc):
    for method, params, code in [
        ("resources/list", {"cursor": "unknown"}, -32602),
        ("resources/read", {}, -32602),
        ("resources/read", {"uri": []}, -32602),
        ("resources/read", {"uri": "rga://skills/../../server.env"}, -32002),
        ("resources/read", {"uri": "file:///private.env"}, -32002),
        ("resources/read", {"uri": "https://example.invalid/private"}, -32002),
    ]:
        status, reply = rpc(method, params)
        assert status == 200
        assert reply["error"]["code"] == code
    assert rpc("resources/list", {}, authorized=False)[0] == 401
    assert (
        rpc("resources/read", {"uri": "rga://skills/world-environments"}, authorized=False)[0]
        == 401
    )
