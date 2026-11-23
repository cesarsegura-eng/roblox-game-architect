"""Test-only MCP entry point with an in-memory fake for container smoke checks.

Never submit a validation task or contact Roblox Open Cloud from this server.
"""

from __future__ import annotations

import os
import tempfile

from .publishing import OpenCloudPlacePublisher, PlacePublicationLedger, RobloxPublishTarget
from .server import RobloxMCPServer, ValidationLedger


class _SmokeTarget:
    universe_id = "7"
    place_id = "8"
    place_version = "7"


class _SmokeValidator:
    target = _SmokeTarget()

    def validate_recipe(self, recipe: dict[str, object]) -> dict[str, object]:
        objects = recipe.get("objects")
        if not isinstance(objects, list):
            raise ValueError("recipe objects are malformed")
        paths = sum(isinstance(item, dict) and item.get("role") == "path" for item in objects)
        return {
            "task_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "validation_status": "structure_only" if paths < 2 else "navigation_failed",
            "object_count": len(objects),
            "path_feature_count": paths,
            "navigation_waypoint_count": 0,
            "navigation_connected": False,
        }


class _SmokePublisher(OpenCloudPlacePublisher):
    """Never contact Roblox; the publish tool is exposed only for schema smoke tests."""

    def __init__(self) -> None:
        super().__init__(
            RobloxPublishTarget(
                "7",
                "8",
                "test-only-invalid-key",
                "test-only-place-approval-secret-32-chars",
                frozenset({"70"}),
                frozenset({"80"}),
            )
        )

    def publish(self, place_file: bytes) -> int:
        del place_file
        raise AssertionError("the authenticated contract smoke must not publish")


def main() -> None:
    if os.environ.get("RGA_ROBLOX_MCP_SMOKE") != "I_ACCEPT_FAKE_VALIDATOR":
        raise SystemExit("test-only fake validator mode was not explicitly enabled")
    token = os.environ.get("RGA_ROBLOX_MCP_TOKEN", "")
    host = os.environ.get("RGA_ROBLOX_MCP_HOST", "127.0.0.1")
    server = RobloxMCPServer(
        host,
        int(os.environ.get("RGA_ROBLOX_MCP_PORT", "8790")),
        _SmokeValidator(),  # type: ignore[arg-type]
        ValidationLedger(os.path.join(tempfile.gettempdir(), "rga-roblox-mcp-smoke.sqlite3")),
        token,
        place_publisher=_SmokePublisher(),
        download_origin="https://download.example.test",
        publication_ledger=PlacePublicationLedger(
            os.path.join(tempfile.gettempdir(), "rga-roblox-publish-smoke.sqlite3")
        ),
    )
    print("RGA Roblox MCP fake smoke server ready; it does not contact Roblox Open Cloud.")
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
