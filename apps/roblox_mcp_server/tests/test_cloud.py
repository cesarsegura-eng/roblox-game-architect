from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import threading
import uuid
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from api.roblox_mcp import RobloxMCPClient, RobloxMCPError
from apps.roblox_mcp_server import server as mcp_service
from apps.roblox_mcp_server.cloud import (
    OpenCloudMapValidator,
    RobloxCloudError,
    RobloxTarget,
)
from apps.roblox_mcp_server.server import (
    RobloxMCPServer,
    ValidationLedger,
    _build_tool_definition,
)
from core.gameplay_templates import rule_game_source, treasure_hunt_source
from core.roblox_place import RobloxPlaceBuild, scene_recipe_to_rojo_project
from core.worldbuilding import SceneRecipe

_ROOT = Path(__file__).resolve().parents[3]
_RECIPE_PATH = _ROOT / "examples" / "worlds" / "mistral-coast-lookout-v2" / "scene-recipe.json"
_RECIPE = json.loads(_RECIPE_PATH.read_text(encoding="utf-8"))
_TASK = (
    "universes/123456/places/234567/versions/7/luau-execution-sessions/"
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/tasks/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
)


def test_mcp_gameplay_rule_input_schema_is_closed_and_bounded():
    schema = _build_tool_definition()["inputSchema"]
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    payload = {
        "recipe": {},
        "request_id": str(uuid.uuid4()),
        "gameplay_mode": "rule_game",
        "gameplay_rules": [
            {"trigger_role": "collectible", "action": "award_points", "amount": 10},
            {"trigger_role": "hazard", "action": "damage", "amount": 20},
            {"trigger_role": "landmark", "action": "award_win", "minimum_points": 10},
        ],
    }
    assert validator.is_valid(payload)
    conflicting = json.loads(json.dumps(payload))
    conflicting["gameplay_rules"].append({"trigger_role": "hazard", "action": "eliminate"})
    assert not validator.is_valid(conflicting)
    invalid = json.loads(json.dumps(payload))
    invalid["gameplay_rules"][0]["source"] = "loadstring(...)"
    assert not validator.is_valid(invalid)
    invalid = json.loads(json.dumps(payload))
    invalid["gameplay_rules"][2]["minimum_points"] = 1001
    assert not validator.is_valid(invalid)
    invalid = json.loads(json.dumps(payload))
    invalid["gameplay_rules"][0] = {
        "trigger_role": "hazard",
        "action": "heal",
        "amount": 101,
    }
    assert not validator.is_valid(invalid)


def _target() -> RobloxTarget:
    return RobloxTarget("123456", "234567", "7", "open-cloud-key")


def _result(recipe: dict[str, Any]) -> dict[str, Any]:
    paths = sum(item["role"] == "path" for item in recipe["objects"])
    return {
        "schema_version": recipe["schema_version"],
        "name": recipe["name"],
        "object_count": len(recipe["objects"]),
        "path_feature_count": sum(item["role"] == "path" for item in recipe["objects"]),
        "navigation_waypoint_count": 4 if paths >= 2 else 0,
        "navigation_connected": paths >= 2,
    }


class _FakeCloud(OpenCloudMapValidator):
    def __init__(self, *, fail: bool = False) -> None:
        super().__init__(_target(), poll_interval_seconds=0.2)
        self.calls: list[tuple[str, str, bytes | None]] = []
        self.uploaded: bytes | None = None
        self.fail = fail

    def _create_binary_input(self, size: int) -> dict[str, str]:
        self.calls.append(("POST", "binary-input", str(size).encode()))
        return {
            "upload_uri": "https://apis.roblox.com/upload?signature=secret",
            "path": "input/path",
        }

    def _upload_binary_input(self, receipt: dict[str, str], payload: bytes) -> None:
        assert receipt["path"] == "input/path"
        self.uploaded = payload

    def _request(self, method: str, path: str, *, body: bytes | None = None) -> Any:
        self.calls.append((method, path, body))
        if method == "POST":
            assert (
                path == "/cloud/v2/universes/123456/places/234567/versions/7/"
                "luau-execution-session-tasks"
            )
            task_body = json.loads(body or b"{}")
            assert task_body["script"] == self.harness_path.read_text(encoding="utf-8")
            assert task_body["binaryInput"] == "input/path"
            assert "Mistral" not in task_body["script"]
            assert task_body["timeout"] == "60s"
            return {"path": _TASK}
        if self.fail:
            raise RobloxCloudError("simulated uncertain transport")
        assert path == "/cloud/v2/" + _TASK
        return {"state": "COMPLETE", "output": {"results": [_result(_RECIPE)]}}


def test_target_rejects_invalid_ids_and_unsafe_timeouts():
    with pytest.raises(ValueError, match="positive decimal ID"):
        RobloxTarget("1/places/2", "2", "3", "x")
    with pytest.raises(ValueError, match="safely exceed"):
        RobloxTarget("1", "2", "3", "key", task_timeout_seconds=60, poll_timeout_seconds=60)


def test_environment_target_requires_confirmation_and_production_ids(
    monkeypatch: pytest.MonkeyPatch,
):
    values = {
        "RGA_ROBLOX_TEST_UNIVERSE_ID": "123456",
        "RGA_ROBLOX_TEST_PLACE_ID": "234567",
        "RGA_ROBLOX_TEST_PLACE_VERSION": "7",
        "ROBLOX_OPEN_CLOUD_API_KEY": "server-only-key",
        "RGA_ROBLOX_DISPOSABLE_CONFIRMED": "I_ACCEPT_DISPOSABLE_TEST_ONLY",
        "RGA_ROBLOX_PERSISTENCE_VERIFIED": "I_VERIFIED_PINNED_PLACE_NONPERSISTENCE",
        "RGA_ROBLOX_PERSISTENCE_EVIDENCE": "ticket:runtime-verification-1",
        "RGA_ROBLOX_PRODUCTION_UNIVERSE_IDS": "7654321",
        "RGA_ROBLOX_PRODUCTION_PLACE_IDS": "8765432",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    target = RobloxTarget.from_env()
    assert target.place_version == "7"
    monkeypatch.setenv("RGA_ROBLOX_TEST_PLACE_ID", "8765432")
    with pytest.raises(ValueError, match="production ID"):
        RobloxTarget.from_env()
    monkeypatch.setenv("RGA_ROBLOX_TEST_PLACE_ID", "234567")
    monkeypatch.setenv("RGA_ROBLOX_DISPOSABLE_CONFIRMED", "yes")
    with pytest.raises(ValueError, match="confirmation"):
        RobloxTarget.from_env()
    monkeypatch.setenv("RGA_ROBLOX_DISPOSABLE_CONFIRMED", "I_ACCEPT_DISPOSABLE_TEST_ONLY")
    monkeypatch.delenv("RGA_ROBLOX_PERSISTENCE_VERIFIED")
    with pytest.raises(ValueError, match="persistence verification"):
        RobloxTarget.from_env()


def test_fixed_harness_receives_recipe_only_as_binary_data():
    cloud = _FakeCloud()
    receipt = cloud.validate_recipe(_RECIPE)
    assert receipt["validation_status"] == "structure_only"
    assert receipt["task_id"] == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    uploaded = json.loads(cloud.uploaded)
    assert uploaded["geometry_version"] == 1
    assert uploaded["name"] == _RECIPE["name"]
    project, _ = scene_recipe_to_rojo_project(_RECIPE)
    root = project["tree"]["Workspace"]["Roblox Game Architect"]
    map_node = next(
        value
        for value in root.values()
        if isinstance(value, dict) and value.get("$className") == "Model"
    )
    for spec, compiled in zip(_RECIPE["objects"], uploaded["objects"], strict=True):
        role = map_node[spec["role"].title()]
        part = next(
            node
            for name, node in role.items()
            if not name.startswith("$") and name.endswith(spec["name"])
        )
        properties = part["$properties"]
        assert compiled["cframe"] == properties["CFrame"]
        assert compiled["size"] == properties["Size"]
        assert compiled["shape"] == properties["Shape"]
        assert compiled["can_collide"] == properties["CanCollide"]
    assert len([call for call in cloud.calls if call[0] == "POST"]) == 2


def test_cloud_model_import_returns_only_bounded_engine_serialized_model():
    serialized = (
        b"<roblox!\x89\xff\r\n\x1a\n"
        + b"\x00\x00"
        + struct.pack("<ii", 3, 4)
        + (b"\x00" * 8)
        + (b"model-data" * 20)
    )

    class _ModelCloud(_FakeCloud):
        def _request(self, method: str, path: str, *, body: bytes | None = None) -> Any:
            self.calls.append((method, path, body))
            if method == "POST":
                task_body = json.loads(body or b"{}")
                assert task_body["script"] == self.harness_path.with_name(
                    "model_import_harness.luau"
                ).read_text(encoding="utf-8")
                assert task_body["binaryInput"] == "input/path"
                assert "loadstring" not in task_body["script"]
                return {"path": _TASK}
            return {
                "state": "COMPLETE",
                "output": {
                    "results": [
                        {
                            "schema_version": 1,
                            "asset_id": "987654321",
                            "instance_count": 4,
                            "meshpart_count": 2,
                            "model_base64": base64.b64encode(serialized).decode("ascii"),
                        }
                    ]
                },
            }

    cloud = _ModelCloud()
    model, summary = cloud.serialize_approved_model("987654321")
    assert model == serialized
    assert summary == {"instance_count": 4, "meshpart_count": 2}
    assert json.loads(cloud.uploaded or b"{}") == {"asset_id": "987654321"}


def test_cloud_model_import_rejects_unbounded_or_mismatched_output():
    class _WrongAsset(_FakeCloud):
        def _request(self, method: str, path: str, *, body: bytes | None = None) -> Any:
            if method == "POST":
                return {"path": _TASK}
            return {
                "state": "COMPLETE",
                "output": {
                    "results": [
                        {
                            "schema_version": 1,
                            "asset_id": "123456789",
                            "instance_count": 1,
                            "meshpart_count": 1,
                            "model_base64": "AAAA",
                        }
                    ]
                },
            }

    with pytest.raises(RobloxCloudError, match=r"malformed|invalid model limits"):
        _WrongAsset().serialize_approved_model("987654321")


def test_malformed_harness_result_is_rejected():
    class BadResult(_FakeCloud):
        def _request(self, method: str, path: str, *, body: bytes | None = None) -> Any:
            if method == "POST":
                return {"path": _TASK}
            return {"state": "COMPLETE", "output": {"results": [{"object_count": -1}]}}

    with pytest.raises(RobloxCloudError, match="malformed"):
        BadResult().validate_recipe(_RECIPE)


@pytest.mark.parametrize(
    "paths, waypoints, connected, status, valid",
    [
        (0, 0, False, "structure_only", True),
        (0, 2, True, "structure_only", False),
        (2, 2, True, "navigation_pass", True),
        (2, 0, True, "navigation_pass", False),
        (2, 0, False, "navigation_pass", False),
        (2, 0, False, "navigation_failed", True),
        (2, 2, False, "navigation_failed", False),
        (3, 2, False, "navigation_failed", True),
        (3, 1, True, "navigation_pass", False),
    ],
)
def test_navigation_receipt_rejects_contradictory_evidence(
    paths, waypoints, connected, status, valid
):
    payload = json.loads(json.dumps(_RECIPE))
    for index, item in enumerate(payload["objects"]):
        item["role"] = "path" if index < paths else "prop"
    recipe = SceneRecipe.from_mapping(payload)
    assert sum(item.role == "path" for item in recipe.objects) == paths
    request_id = str(uuid.uuid4())
    receipt = {
        "request_id": request_id,
        "place_version": "7",
        "task_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "object_count": len(recipe.objects),
        "path_feature_count": paths,
        "navigation_waypoint_count": waypoints,
        "navigation_connected": connected,
        "validation_status": status,
    }
    if valid:
        assert RobloxMCPClient._receipt(receipt, recipe, request_id).validation_status == status
    else:
        with pytest.raises(RobloxMCPError, match=r"contradictory|contradicts"):
            RobloxMCPClient._receipt(receipt, recipe, request_id)


def test_cloud_rejects_navigation_evidence_without_a_route():
    recipe = SceneRecipe.from_mapping(_RECIPE)
    result = _result(_RECIPE)
    assert result["path_feature_count"] < 2
    result["navigation_connected"] = True
    result["navigation_waypoint_count"] = 2
    with pytest.raises(RobloxCloudError, match="contradictory"):
        OpenCloudMapValidator._check_result(result, recipe)


def test_disconnected_route_is_reported_as_navigation_failure():
    recipe = json.loads(json.dumps(_RECIPE))
    recipe["objects"][0]["role"] = "path"
    recipe["objects"][1]["role"] = "path"

    class Disconnected(_FakeCloud):
        def _request(self, method: str, path: str, *, body: bytes | None = None) -> Any:
            if method == "POST":
                return {"path": _TASK}
            result = _result(recipe)
            result["navigation_connected"] = False
            result["navigation_waypoint_count"] = 0
            return {"state": "COMPLETE", "output": {"results": [result]}}

    receipt = Disconnected().validate_recipe(recipe)
    assert receipt["validation_status"] == "navigation_failed"


def test_uncertain_cloud_request_is_not_retried_for_same_id(tmp_path: Path):
    ledger = ValidationLedger(tmp_path / "validation.sqlite3")
    request_id = str(uuid.uuid4())
    with pytest.raises(RobloxCloudError, match="uncertain"):
        ledger.run(_FakeCloud(fail=True), _RECIPE, request_id)
    with pytest.raises(RobloxCloudError, match="will not be resubmitted"):
        ledger.run(_FakeCloud(), _RECIPE, request_id)


def test_legacy_endpoint_only_receipt_is_not_replayed_as_full_route_evidence(tmp_path: Path):
    ledger = ValidationLedger(tmp_path / "validation.sqlite3")
    request_id = str(uuid.uuid4())
    old_digest = hashlib.sha256(SceneRecipe.from_mapping(_RECIPE).to_json().encode()).hexdigest()
    with ledger._connect() as db:
        db.execute(
            "INSERT INTO requests(request_id, digest, state, result_json) VALUES (?, ?, ?, ?)",
            (
                request_id,
                old_digest,
                "complete",
                json.dumps({"validation_status": "navigation_pass"}),
            ),
        )
    cloud = _FakeCloud()
    with pytest.raises(ValueError, match="validation version"):
        ledger.run(cloud, _RECIPE, request_id)
    assert cloud.calls == []


@pytest.mark.parametrize("field", ["universe_id", "place_id", "place_version"])
def test_validation_cache_rejects_changed_pinned_target(tmp_path: Path, field: str):
    ledger = ValidationLedger(tmp_path / "validation.sqlite3")
    request_id = str(uuid.uuid4())
    first = _FakeCloud()
    ledger.run(first, _RECIPE, request_id)
    changed = _FakeCloud()
    changed.target = replace(changed.target, **{field: "999"})
    with pytest.raises(ValueError, match="test target"):
        ledger.run(changed, _RECIPE, request_id)
    assert changed.calls == []


def test_validation_cache_survives_key_rotation_for_the_same_target(tmp_path: Path):
    ledger = ValidationLedger(tmp_path / "validation.sqlite3")
    request_id = str(uuid.uuid4())
    original = ledger.run(_FakeCloud(), _RECIPE, request_id)
    rotated = _FakeCloud()
    rotated.target = replace(rotated.target, api_key="rotated-secret")
    assert ledger.run(rotated, _RECIPE, request_id) == original
    assert rotated.calls == []
    assert b"rotated-secret" not in (tmp_path / "validation.sqlite3").read_bytes()


def test_completed_cloud_request_is_cached_and_recipe_reuse_rejected(tmp_path: Path):
    ledger = ValidationLedger(tmp_path / "validation.sqlite3")
    request_id = str(uuid.uuid4())
    first = ledger.run(_FakeCloud(), _RECIPE, request_id)
    second_cloud = _FakeCloud()
    second = ledger.run(second_cloud, _RECIPE, request_id)
    assert second == first
    assert not second_cloud.calls
    different_recipe = {**_RECIPE, "name": "Different Map"}
    with pytest.raises(ValueError, match="different recipe"):
        ledger.run(_FakeCloud(), different_recipe, request_id)


def test_remote_mcp_exposes_only_fixed_validation_tool(tmp_path: Path):
    token = "b" * 40
    server = RobloxMCPServer(
        "127.0.0.1", 0, _FakeCloud(), ValidationLedger(tmp_path / "ledger.sqlite3"), token
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        request_id = str(uuid.uuid4())
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/mcp"
        receipt = RobloxMCPClient(endpoint, token).validate_recipe(_RECIPE, request_id)
        assert receipt.request_id == request_id
        assert receipt.validation_status == "structure_only"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_startup_accepts_build_only_and_rejects_incomplete_cloud_target(monkeypatch):
    for name in list(os.environ):
        if name.startswith(("RGA_ROBLOX_", "ROBLOX_OPEN_CLOUD_", "BLENDER_MCP_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("RGA_ROBLOX_MCP_TOKEN", "r" * 40)
    monkeypatch.setenv("RGA_ROBLOX_MCP_PORT", "0")
    builder = object()
    monkeypatch.setattr(mcp_service, "RojoPlaceBuilder", lambda _bin: builder)

    def inspect(server, *, poll_interval):
        assert server.place_builder is builder
        assert not server.validation_enabled
        assert server.ledger is None

    monkeypatch.setattr(RobloxMCPServer, "serve_forever", inspect)
    mcp_service.main()
    monkeypatch.setenv("RGA_ROBLOX_TEST_PLACE_ID", "123")
    with pytest.raises(ValueError, match="missing required Roblox validation configuration"):
        mcp_service.main()


@pytest.mark.parametrize("with_validation", [False, True])
def test_remote_mcp_place_build_roundtrips_through_verified_client(tmp_path: Path, with_validation):
    token = "c" * 40
    place_file = b'<roblox version="4"><Item class="DataModel" /></roblox>'

    class _PlaceBuilder:
        def build(self, recipe: object) -> RobloxPlaceBuild:
            parsed = SceneRecipe.from_mapping(recipe)
            return RobloxPlaceBuild(
                place_file=place_file,
                object_count=len(parsed.objects),
                part_count=len(parsed.objects),
                light_count=0,
                approximated_object_count=0,
                omitted_character_count=len(parsed.characters),
                omitted_sun_light_count=0,
            )

    server = RobloxMCPServer(
        "127.0.0.1",
        0,
        _FakeCloud() if with_validation else None,
        ValidationLedger(tmp_path / "ledger.sqlite3") if with_validation else None,
        token,
        place_builder=_PlaceBuilder(),  # type: ignore[arg-type]
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        request_id = str(uuid.uuid4())
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/mcp"
        client = RobloxMCPClient(endpoint, token)
        client.check_connection()
        assert client.map_validation_available is with_validation
        artifact = client.build_place(_RECIPE, request_id)
        assert artifact.request_id == request_id
        assert artifact.place_file == place_file
        assert artifact.sha256 == hashlib.sha256(place_file).hexdigest()
        assert artifact.object_count == len(_RECIPE["objects"])
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_remote_mcp_builds_only_the_verified_treasure_hunt_template(tmp_path: Path):
    token = "d" * 40
    root = ET.Element("roblox", {"version": "4"})
    datamodel = ET.SubElement(root, "Item", {"class": "DataModel"})
    service = ET.SubElement(datamodel, "Item", {"class": "ServerScriptService"})
    script = ET.SubElement(service, "Item", {"class": "Script"})
    properties = ET.SubElement(script, "Properties")
    ET.SubElement(properties, "string", {"name": "Name"}).text = "RGA Treasure Hunt"
    ET.SubElement(properties, "string", {"name": "Source"}).text = treasure_hunt_source()
    place_file = ET.tostring(root, encoding="utf-8")

    class _PlaceBuilder:
        def build(self, recipe: object, *, gameplay_mode: str = "blockout") -> RobloxPlaceBuild:
            parsed = SceneRecipe.from_mapping(recipe)
            return RobloxPlaceBuild(
                place_file=place_file,
                object_count=len(parsed.objects),
                part_count=len(parsed.objects),
                light_count=0,
                approximated_object_count=0,
                omitted_character_count=len(parsed.characters),
                omitted_sun_light_count=0,
                gameplay_mode=gameplay_mode,
            )

    server = RobloxMCPServer(
        "127.0.0.1",
        0,
        _FakeCloud(),
        ValidationLedger(tmp_path / "ledger.sqlite3"),
        token,
        place_builder=_PlaceBuilder(),  # type: ignore[arg-type]
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        request_id = str(uuid.uuid4())
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/mcp"
        recipe = json.loads(json.dumps(_RECIPE))
        recipe["objects"].append(
            {
                "name": "Coast Trail",
                "role": "path",
                "primitive": "cube",
                "location": [0, 0, 0],
                "rotation_deg": [0, 0, 0],
                "scale": [8, 2, 0.2],
            }
        )
        recipe["objects"].append(
            {
                "name": "Golden Coin",
                "role": "collectible",
                "primitive": "uv_sphere",
                "location": [1, 1, 1],
                "rotation_deg": [0, 0, 0],
                "scale": [0.4, 0.4, 0.4],
            }
        )
        artifact = RobloxMCPClient(endpoint, token).build_place(
            recipe, request_id, gameplay_mode="treasure_hunt"
        )
        assert artifact.gameplay_mode == "treasure_hunt"
        assert artifact.place_file == place_file
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_remote_mcp_builds_validated_data_driven_gameplay_rules(tmp_path: Path):
    token = "r" * 40
    recipe = json.loads(
        (_ROOT / "examples/worlds/rainforest-checkpoint-obby/scene-recipe.json").read_text(
            encoding="utf-8"
        )
    )
    rules = [
        {"trigger_role": "collectible", "action": "award_points", "amount": 1},
        {"trigger_role": "hazard", "action": "eliminate"},
        {"trigger_role": "landmark", "action": "award_win", "minimum_points": 3},
    ]
    root = ET.Element("roblox", {"version": "4"})
    datamodel = ET.SubElement(root, "Item", {"class": "DataModel"})
    workspace = ET.SubElement(datamodel, "Item", {"class": "Workspace"})
    package_root = ET.SubElement(workspace, "Item", {"class": "Folder"})
    package_properties = ET.SubElement(package_root, "Properties")
    ET.SubElement(package_properties, "string", {"name": "Name"}).text = "Roblox Game Architect"
    map_node = ET.SubElement(package_root, "Item", {"class": "Model"})
    map_properties = ET.SubElement(map_node, "Properties")
    ET.SubElement(map_properties, "string", {"name": "Name"}).text = recipe["name"]
    rules_value = ET.SubElement(map_node, "Item", {"class": "StringValue"})
    rule_properties = ET.SubElement(rules_value, "Properties")
    ET.SubElement(rule_properties, "string", {"name": "Name"}).text = "RGA Gameplay Rules"
    ET.SubElement(rule_properties, "string", {"name": "Value"}).text = json.dumps(
        rules, separators=(",", ":")
    )
    spawn_folder = ET.SubElement(map_node, "Item", {"class": "Folder"})
    spawn_properties = ET.SubElement(spawn_folder, "Properties")
    ET.SubElement(spawn_properties, "string", {"name": "Name"}).text = "RGA Spawn"
    ET.SubElement(spawn_folder, "Item", {"class": "SpawnLocation"})
    for role in ("collectible", "hazard", "landmark"):
        role_folder = ET.SubElement(map_node, "Item", {"class": "Folder"})
        role_properties = ET.SubElement(role_folder, "Properties")
        ET.SubElement(role_properties, "string", {"name": "Name"}).text = role.title()
        ET.SubElement(role_folder, "Item", {"class": "Part"})
    service = ET.SubElement(datamodel, "Item", {"class": "ServerScriptService"})
    script = ET.SubElement(service, "Item", {"class": "Script"})
    script_properties = ET.SubElement(script, "Properties")
    ET.SubElement(script_properties, "string", {"name": "Name"}).text = "RGA Data Rules"
    ET.SubElement(
        script_properties, "ProtectedString", {"name": "Source"}
    ).text = rule_game_source()
    place_file = ET.tostring(root, encoding="utf-8")

    class _PlaceBuilder:
        def build(
            self,
            received: object,
            *,
            gameplay_mode: str = "blockout",
            gameplay_rules: object = None,
        ) -> RobloxPlaceBuild:
            assert gameplay_mode == "rule_game"
            assert gameplay_rules == rules
            parsed = SceneRecipe.from_mapping(received)
            return RobloxPlaceBuild(
                place_file=place_file,
                object_count=len(parsed.objects),
                part_count=len(parsed.objects),
                light_count=0,
                approximated_object_count=0,
                omitted_character_count=len(parsed.characters),
                omitted_sun_light_count=0,
                gameplay_mode=gameplay_mode,
            )

    server = RobloxMCPServer(
        "127.0.0.1",
        0,
        _FakeCloud(),
        ValidationLedger(tmp_path / "ledger.sqlite3"),
        token,
        place_builder=_PlaceBuilder(),  # type: ignore[arg-type]
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        request_id = str(uuid.uuid4())
        endpoint = f"http://127.0.0.1:{server.server_address[1]}/mcp"
        artifact = RobloxMCPClient(endpoint, token).build_place(
            recipe, request_id, gameplay_mode="rule_game", gameplay_rules=rules
        )
        assert artifact.gameplay_mode == "rule_game"
        assert artifact.place_file == place_file
        assert 'action == "award_win"' in rule_game_source()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
