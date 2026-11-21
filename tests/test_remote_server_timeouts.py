"""A stalled client must not hold a thread of an internet-facing MCP server forever.

Both remote services sit behind a reverse proxy, but the backend cannot rely on it:
a client that connects and then sends nothing, or declares a body and never finishes
it, used to block a handler thread with no limit.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from apps.blender_mcp_server.server import BlenderMCPHandler, BlenderMCPServer
from apps.roblox_mcp_server.server import RobloxMCPHandler, RobloxMCPServer, ValidationLedger

TOKEN = "t" * 40
STALL_TIMEOUT = 0.5
GIVE_UP_AFTER = 8.0


@contextmanager
def _running(server: object) -> Iterator[int]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)  # type: ignore[attr-defined]
    thread.start()
    try:
        yield server.server_address[1]  # type: ignore[attr-defined]
    finally:
        server.shutdown()  # type: ignore[attr-defined]
        server.server_close()  # type: ignore[attr-defined]
        thread.join(timeout=2)


@pytest.fixture(params=["blender", "roblox"])
def port(
    request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[int]:
    if request.param == "blender":
        monkeypatch.setattr(BlenderMCPHandler, "timeout", STALL_TIMEOUT)
        server = BlenderMCPServer("127.0.0.1", 0, object(), TOKEN)  # type: ignore[arg-type]
    else:
        monkeypatch.setattr(RobloxMCPHandler, "timeout", STALL_TIMEOUT)
        ledger = ValidationLedger(tmp_path / "ledger.sqlite3")
        server = RobloxMCPServer("127.0.0.1", 0, object(), ledger, TOKEN)  # type: ignore[arg-type]
    with _running(server) as bound:
        yield bound


def _read_until_closed(connection: socket.socket) -> bytes:
    connection.settimeout(GIVE_UP_AFTER)
    received = b""
    while True:
        chunk = connection.recv(4096)
        if not chunk:
            return received
        received += chunk


def test_a_connection_that_sends_nothing_is_closed(port: int) -> None:
    started = time.monotonic()
    with socket.create_connection(("127.0.0.1", port), timeout=GIVE_UP_AFTER) as connection:
        assert _read_until_closed(connection) == b""

    assert time.monotonic() - started < GIVE_UP_AFTER - 1


def test_a_body_that_never_completes_is_abandoned(port: int) -> None:
    head = (
        "POST /mcp HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        f"Authorization: Bearer {TOKEN}\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: 1000\r\n\r\n"
    )
    started = time.monotonic()
    with socket.create_connection(("127.0.0.1", port), timeout=GIVE_UP_AFTER) as connection:
        connection.sendall(head.encode() + b'{"jsonrpc":')
        answer = _read_until_closed(connection)

    assert time.monotonic() - started < GIVE_UP_AFTER - 1
    # The server either just closes, or answers the incomplete body as a bad request.
    assert answer == b"" or answer.startswith(b"HTTP/1.")
    assert b" 200 " not in answer.split(b"\r\n", 1)[0]
