"""Exercise Roblox build, validation, and publish-approval contracts without Open Cloud."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import re
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urlsplit

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / "examples/worlds/evaluation/coastal-wetland.json"


_TOKEN = re.compile(r"[A-Za-z0-9._~+/-]+=*\Z", re.ASCII)
MAX_RESPONSE_BYTES = 11_000_000


def _request(
    endpoint: SplitResult,
    token: str,
    message: dict[str, Any],
    protocol: bool = True,
) -> tuple[int, bytes]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if protocol:
        headers["MCP-Protocol-Version"] = "2025-11-25"
    connection = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=5)
    try:
        connection.request(
            "POST",
            endpoint.path,
            body=json.dumps(message, separators=(",", ":")).encode(),
            headers=headers,
        )
        response = connection.getresponse()
        return response.status, response.read(MAX_RESPONSE_BYTES + 1)
    finally:
        connection.close()


def _check(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    endpoint_text = os.environ.get("ROBLOX_MCP_URL", "")
    token = os.environ.get("ROBLOX_MCP_BEARER_TOKEN", "")
    endpoint = urlsplit(endpoint_text)
    expected_port = int(os.environ.get("ROBLOX_MCP_SMOKE_PORT", "8790"))
    if (
        endpoint.scheme != "http"
        or endpoint.hostname not in {"127.0.0.1", "localhost"}
        or endpoint.path != "/mcp"
        or endpoint.query
        or endpoint.fragment
        or endpoint.username is not None
        or endpoint.password is not None
        or endpoint.port != expected_port
        or not 32 <= len(token) <= 512
        or not token.isascii()
        or not _TOKEN.fullmatch(token)
    ):
        raise SystemExit("ROBLOX_MCP_URL and a 32-character smoke token are required")

    status, _ = _request(
        endpoint,
        "",
        {"jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {}},
        protocol=False,
    )
    _check(status == 401, "MCP endpoint accepted a request without authentication")

    status, body = _request(
        endpoint,
        token,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "rga-container-smoke", "version": "1"},
            },
        },
        protocol=False,
    )
    initialized = json.loads(body)
    _check(status == 200, "MCP initialization returned an invalid status")
    _check(
        initialized["result"]["protocolVersion"] == "2025-11-25",
        "MCP initialization negotiated the wrong protocol",
    )

    status, body = _request(
        endpoint,
        token,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    _check(status == 202 and body == b"", "MCP session initialization notification failed")

    status, body = _request(
        endpoint,
        token,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    _check(status == 200, "MCP tool listing returned an invalid status")
    tools = json.loads(body)["result"]["tools"]
    tools_by_name = {tool["name"]: tool for tool in tools}
    _check(
        set(tools_by_name)
        == {
            "rga_validate_map",
            "rga_review_game_plan",
            "rga_build_place",
            "rga_build_place_download",
            "rga_publish_reviewed_place",
            "rga_prepare_test_place_publication",
            "rga_publish_prepared_test_place",
        },
        "Expected fixed map, build, and two-step publication tools",
    )
    schema = tools_by_name["rga_validate_map"]["inputSchema"]
    _check(
        schema["additionalProperties"] is False
        and set(schema["properties"]) == {"recipe", "request_id"}
        and set(schema["required"]) == {"recipe", "request_id"},
        "MCP tool schema differs from the fixed recipe contract",
    )
    build_schema = tools_by_name["rga_build_place"]["inputSchema"]
    _check(
        build_schema["additionalProperties"] is False
        and set(build_schema["properties"])
        == {"recipe", "request_id", "gameplay_mode", "gameplay_rules", "model_asset_id"}
        and set(build_schema["required"]) == {"recipe", "request_id"},
        "MCP place-build schema differs from the fixed recipe contract",
    )
    _check(
        build_schema["properties"]["gameplay_mode"].get("enum")
        == ["blockout", "obby", "rule_game", "treasure_hunt"],
        "MCP place-build schema omitted a supported gameplay mode",
    )
    _check(
        build_schema["properties"]["model_asset_id"].get("pattern") == "^[1-9][0-9]{0,19}$",
        "MCP model-asset field is not constrained to a numeric Roblox asset ID",
    )
    rules_schema = build_schema["properties"]["gameplay_rules"]
    rule_variants = rules_schema.get("items", {}).get("oneOf", [])
    _check(
        rules_schema.get("minItems") == 1
        and rules_schema.get("maxItems") == 16
        and {item.get("properties", {}).get("action", {}).get("const") for item in rule_variants}
        == {"award_points", "heal", "damage", "eliminate", "award_win"},
        "MCP data-rule schema is missing a bounded supported interaction",
    )
    publish_schema = tools_by_name["rga_publish_reviewed_place"]["inputSchema"]
    publish_fields = {
        "request_id",
        "approval_id",
        "artifact_sha256",
        "approval_signature",
        "approval_expires_at",
        "place_file_base64",
    }
    _check(
        publish_schema["type"] == "object"
        and publish_schema["additionalProperties"] is False
        and set(publish_schema["properties"]) == publish_fields
        and set(publish_schema["required"]) == publish_fields
        and publish_schema["properties"]["place_file_base64"].get("maxLength") == 10_666_668,
        "MCP place-publish tool schema differs from the fixed approval contract",
    )
    prepare_schema = tools_by_name["rga_prepare_test_place_publication"]["inputSchema"]
    _check(
        prepare_schema["additionalProperties"] is False
        and set(prepare_schema["properties"]) == {"request_id", "artifact_sha256"}
        and tools_by_name["rga_prepare_test_place_publication"]["annotations"]["readOnlyHint"]
        is True,
        "MCP direct-publication prepare tool is not read-only and bounded",
    )
    commit_schema = tools_by_name["rga_publish_prepared_test_place"]["inputSchema"]
    _check(
        commit_schema["additionalProperties"] is False
        and set(commit_schema["properties"])
        == {"request_id", "approval_id", "artifact_sha256", "confirmation_phrase"}
        and tools_by_name["rga_publish_prepared_test_place"]["annotations"]["destructiveHint"]
        is True,
        "MCP direct-publication commit tool is not separately gated",
    )

    recipe = json.loads(RECIPE.read_text(encoding="utf-8"))
    _check(recipe.get("schema_version") == 3, "MCP smoke fixture must exercise Scene Recipe v3")
    _check("environment" in recipe, "MCP smoke fixture must include environment settings")
    request_id = str(uuid.uuid4())
    status, body = _request(
        endpoint,
        token,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "rga_validate_map",
                "arguments": {"recipe": recipe, "request_id": request_id},
            },
        },
    )
    _check(status == 200, "MCP tool call returned an invalid status")
    result = json.loads(body)["result"]
    _check(result.get("isError") is not True, "MCP tool call returned an error")
    receipt = result["structuredContent"]
    _check(receipt["request_id"] == request_id, "MCP receipt request ID mismatch")
    _check(receipt["place_version"] == "7", "MCP receipt place version mismatch")
    _check(receipt["validation_status"] == "structure_only", "MCP smoke result mismatch")
    _check(receipt["object_count"] == len(recipe["objects"]), "MCP receipt object count mismatch")
    _check(
        receipt["task_id"] == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "MCP receipt task ID mismatch",
    )

    build_id = str(uuid.uuid4())
    build_request = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "rga_build_place",
            "arguments": {"recipe": recipe, "request_id": build_id},
        },
    }
    status, body = _request(endpoint, token, build_request)
    _check(status == 200, "MCP place-build call returned an invalid status")
    build_result = json.loads(body)["result"]
    _check(build_result.get("isError") is not True, "MCP place build returned an error")
    artifact = build_result["structuredContent"]
    _check(artifact["request_id"] == build_id, "MCP build receipt request ID mismatch")
    place_file = base64.b64decode(artifact["place_file_base64"], validate=True)
    _check(place_file.startswith(b"<roblox"), "MCP build did not return an RBXLX file")
    _check(
        hashlib.sha256(place_file).hexdigest() == artifact["sha256"],
        "MCP place-build digest mismatch",
    )
    link_request = {
        **build_request,
        "id": 40,
        "params": {
            "name": "rga_build_place_download",
            "arguments": {"recipe": recipe, "request_id": str(uuid.uuid4())},
        },
    }
    status, body = _request(endpoint, token, link_request)
    _check(status == 200 and len(body) < 4096, "Expected compact MCP delivery receipt")
    link = json.loads(body)["result"]["structuredContent"]
    download = urlsplit(link["download_url"])
    _check(
        download.netloc == "download.example.test" and "place_file_base64" not in link,
        "Download tool returned an unexpected address or inline file",
    )
    connection = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=5)
    try:
        connection.request("GET", download.path)
        response = connection.getresponse()
        downloaded = response.read(MAX_RESPONSE_BYTES + 1)
        _check(
            response.status == 200
            and hashlib.sha256(downloaded).hexdigest() == link["sha256"]
            and downloaded.startswith(b"<roblox"),
            "Browser download did not return the receipted place",
        )
    finally:
        connection.close()
    _check(
        b"<!DOCTYPE" not in place_file.upper() and b"<!ENTITY" not in place_file.upper(),
        "MCP place file contained a forbidden XML declaration",
    )
    document = ET.fromstring(place_file)  # noqa: S314 - DTD and entities are rejected above.
    _check(
        not any(
            item.get("class") in {"Script", "LocalScript", "ModuleScript", "Actor"}
            for item in document.iter("Item")
        ),
        "MCP generated place contained executable classes",
    )
    items = list(document.iter("Item"))
    lighting = next((item for item in items if item.get("class") == "Lighting"), None)
    atmosphere = next((item for item in items if item.get("class") == "Atmosphere"), None)
    terrain = next((item for item in items if item.get("class") == "Terrain"), None)
    clouds = next((item for item in items if item.get("class") == "Clouds"), None)
    _check(lighting is not None, "MCP place omitted Roblox global Lighting")
    _check(atmosphere is not None, "MCP place omitted Roblox Atmosphere")
    _check(terrain is not None and clouds is not None, "MCP place omitted Terrain Clouds")

    def property_names(item: ET.Element) -> set[str]:
        properties = item.find("Properties")
        return {child.get("name", "") for child in properties or ()}

    _check(
        {"Ambient", "OutdoorAmbient", "Brightness", "ClockTime", "GlobalShadows"}
        <= property_names(lighting),
        "MCP place omitted bounded global lighting properties",
    )
    _check(
        {"Color", "Decay", "Density", "Glare", "Haze", "Offset"} <= property_names(atmosphere),
        "MCP place omitted bounded atmospheric properties",
    )
    _check(
        {"Color", "Cover", "Density", "Enabled"} <= property_names(clouds),
        "MCP place omitted bounded cloud properties",
    )
    prepare_status, prepare_body = _request(
        endpoint,
        token,
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "rga_prepare_test_place_publication",
                "arguments": {"request_id": build_id, "artifact_sha256": artifact["sha256"]},
            },
        },
    )
    _check(prepare_status == 200, "MCP publish preparation returned an invalid status")
    prepared_result = json.loads(prepare_body)["result"]
    _check(prepared_result.get("isError") is not True, "MCP rejected the server-built artifact")
    prepared = prepared_result["structuredContent"]
    _check(
        prepared["artifact_sha256"] == artifact["sha256"]
        and prepared["target_universe_id"] == "7"
        and prepared["target_place_id"] == "8"
        and prepared["confirmation_phrase"].endswith(artifact["sha256"][:12]),
        "MCP direct publish review is not bound to its artifact and fixed target",
    )
    invalid_commit_status, invalid_commit_body = _request(
        endpoint,
        token,
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "rga_publish_prepared_test_place",
                "arguments": {
                    "request_id": build_id,
                    "approval_id": prepared["approval_id"],
                    "artifact_sha256": artifact["sha256"],
                    "confirmation_phrase": "I_APPROVE_ROBLOX_TEST_PLACE_PUBLISH_000000000000",
                },
            },
        },
    )
    _check(invalid_commit_status == 200, "MCP direct publish commit returned an invalid status")
    _check(
        json.loads(invalid_commit_body)["result"].get("isError") is True,
        "MCP direct publish accepted a mismatched confirmation phrase",
    )
    rejected_place = b'<roblox version="4"><Item class="DataModel"/></roblox>'
    publish_status, publish_body = _request(
        endpoint,
        token,
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "rga_publish_reviewed_place",
                "arguments": {
                    "request_id": str(uuid.uuid4()),
                    "approval_id": str(uuid.uuid4()),
                    "artifact_sha256": hashlib.sha256(rejected_place).hexdigest(),
                    "approval_signature": "0" * 64,
                    "approval_expires_at": int(time.time()) + 300,
                    "place_file_base64": base64.b64encode(rejected_place).decode("ascii"),
                },
            },
        },
    )
    _check(publish_status == 200, "MCP place-publish contract call returned an invalid status")
    rejected = json.loads(publish_body)["result"]
    _check(rejected.get("isError") is True, "MCP accepted an unsigned place-publish approval")
    replay_request = {**build_request, "id": 5}
    replay_status, replay_body = _request(endpoint, token, replay_request)
    _check(replay_status == 200, "MCP place-build retry returned an invalid status")
    replay = json.loads(replay_body)["result"].get("structuredContent", {})
    _check(
        replay.get("sha256") == artifact["sha256"]
        and replay.get("place_file_base64") == artifact["place_file_base64"],
        "MCP retry with the same request ID was not deterministic",
    )

    _check_playable_plan(endpoint, token)
    print("Roblox plan review, build, validation, and publish-approval MCP smoke passed.")


def _check_playable_plan(endpoint: SplitResult, token: str) -> None:
    scene = ROOT / "examples/worlds/rainforest-checkpoint-obby"
    plan = json.loads((scene / "game-plan.json").read_bytes())
    recipe = json.loads((scene / "scene-recipe.json").read_bytes())

    def call(name: str, args: dict[str, Any]) -> dict[str, Any]:
        status, body = _request(
            endpoint,
            token,
            {
                "jsonrpc": "2.0",
                "id": 50,
                "method": "tools/call",
                "params": {"name": name, "arguments": args},
            },
        )
        _check(status == 200, "MCP review/build request failed")
        return json.loads(body)["result"]

    reviewed = call("rga_review_game_plan", {"plan": plan, "recipe": recipe})
    settings = reviewed["structuredContent"]["build_settings"]
    rules = json.loads((scene / "gameplay-rules.json").read_bytes())
    _check(
        settings == {"gameplay_mode": "rule_game", "gameplay_rules": rules},
        "Review lost the planned mode or rules",
    )
    built = call("rga_build_place", {"recipe": recipe, "request_id": str(uuid.uuid4()), **settings})
    receipt = built["structuredContent"]
    place = base64.b64decode(receipt["place_file_base64"], validate=True)
    _check(
        place.startswith(b"<roblox")
        and hashlib.sha256(place).hexdigest() == receipt["sha256"]
        and receipt["gameplay_mode"] == "rule_game",
        "Reviewed game build failed verification",
    )


if __name__ == "__main__":
    main()
