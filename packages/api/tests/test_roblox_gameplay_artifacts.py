import hashlib
import uuid
import xml.etree.ElementTree as ET

import pytest

from api.roblox_mcp import (
    RobloxMCPClient,
    RobloxMCPError,
    RobloxPublishReceipt,
    _validate_place_scripts,
)
from apps.roblox_mcp_server.server import _place_publish_tool_definition
from core.gameplay_templates import obby_course_source, treasure_hunt_source
from core.place_approval import verify_place_publish_approval


def _artifact_script(source: str) -> ET.Element:
    root = ET.Element("roblox")
    model = ET.SubElement(root, "Item", {"class": "DataModel"})
    service = ET.SubElement(model, "Item", {"class": "ServerScriptService"})
    script = ET.SubElement(service, "Item", {"class": "Script"})
    properties = ET.SubElement(script, "Properties")
    ET.SubElement(properties, "string", {"name": "Name"}).text = "RGA Treasure Hunt"
    ET.SubElement(properties, "ProtectedString", {"name": "Source"}).text = source
    return root


def test_place_artifact_allows_only_exact_trusted_gameplay_template():
    _validate_place_scripts(_artifact_script(treasure_hunt_source()), "treasure_hunt")
    with pytest.raises(RobloxMCPError, match="fixed reviewed template"):
        _validate_place_scripts(
            _artifact_script(treasure_hunt_source() + "\nprint('changed')\n"), "treasure_hunt"
        )


def test_place_artifact_allows_only_exact_trusted_obby_template():
    script = _artifact_script(obby_course_source())
    next(
        node for node in script.iter("string") if node.get("name") == "Name"
    ).text = "RGA Obby Course"
    _validate_place_scripts(script, "obby")
    with pytest.raises(RobloxMCPError, match="fixed reviewed template"):
        _validate_place_scripts(_artifact_script(obby_course_source()), "obby")


def test_script_free_artifact_rejects_any_executable_instance():
    with pytest.raises(RobloxMCPError, match="executable classes"):
        _validate_place_scripts(_artifact_script(treasure_hunt_source()), "blockout")


def test_client_signs_exact_reviewed_place_for_fixed_target(monkeypatch):
    client = RobloxMCPClient("https://roblox-mcp.example.test/mcp", "m" * 40, timeout=5)
    place = b'<roblox version="4"><Item class="DataModel"/></roblox>'
    request_id = str(uuid.uuid4())
    approval_id = str(uuid.uuid4())
    target_universe = "1234"
    target_place = "5678"
    approval_key = "k" * 40
    digest = hashlib.sha256(place).hexdigest()
    seen: dict[str, object] = {}

    class Connection:
        @staticmethod
        def close() -> None:
            seen["closed"] = True

    monkeypatch.setattr(client, "_connection", Connection)

    def fake_post(connection, call_id, method, params):
        if method == "initialize":
            return {"result": {"protocolVersion": "2025-11-25"}}
        if method == "tools/list":
            return {"result": {"tools": [_place_publish_tool_definition()]}}
        assert method == "tools/call"
        arguments = params["arguments"]
        seen.update(arguments)
        assert arguments["artifact_sha256"] == digest
        assert arguments["place_file_base64"]
        assert verify_place_publish_approval(
            approval_key,
            arguments["approval_signature"],
            request_id=request_id,
            approval_id=approval_id,
            artifact_sha256=digest,
            universe_id=target_universe,
            place_id=target_place,
            expires_at=arguments["approval_expires_at"],
        )
        return {
            "result": {
                "structuredContent": {
                    "request_id": request_id,
                    "approval_id": approval_id,
                    "artifact_sha256": digest,
                    "universe_id": target_universe,
                    "place_id": target_place,
                    "version_number": 8,
                }
            }
        }

    monkeypatch.setattr(client, "_post", fake_post)
    monkeypatch.setattr(client, "_post_notification", lambda connection, method: None)
    receipt = client.publish_reviewed_place(
        place,
        request_id=request_id,
        approval_id=approval_id,
        approval_secret=approval_key,
        universe_id=target_universe,
        place_id=target_place,
    )
    assert receipt == RobloxPublishReceipt(
        request_id, approval_id, digest, target_universe, target_place, 8
    )
    assert seen["closed"] is True
