"""The transport: plugin-initiated HTTP with long-polling (ADR-0007).

Transport only. It holds no protocol knowledge beyond reading the credential from a
header and holding a poll open, and it carries no message shapes: those are
`messages.py` and `service.py`. The standard library is enough for a local,
single-user service, so this adds no dependency and forecloses no framework choice.
"""

from __future__ import annotations

import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .json_profile import MAX_MESSAGE_BYTES, serialise
from .service import Service, handle_message

ENDPOINT = "/v1/messages"
DEFAULT_POLL_TIMEOUT_S = 25.0
_WAKE_S = 0.1


class _Handler(BaseHTTPRequestHandler):
    """One request. The server instance carries the service and the settings."""

    server_version = "roblox-game-architect"
    sys_version = ""

    def do_POST(self) -> None:
        if self.path != ENDPOINT:
            self._plain(404, "No such endpoint.")
            return
        credential = self._credential()
        if credential is None:
            self._send(
                401,
                {
                    "protocol_version": {"major": 1, "minor": 0},
                    "kind": "response",
                    "message_id": "m-unauthorized",
                    "status": "error",
                    "payload": {
                        "code": "unauthorized",
                        "message": "A plugin token is required.",
                        "retryable": False,
                    },
                },
            )
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_MESSAGE_BYTES:
            self._plain(413, "The message is larger than the protocol allows.")
            return
        body = self.rfile.read(length)

        service: Service = self.server.service  # type: ignore[attr-defined]
        timeout: float = self.server.poll_timeout_s  # type: ignore[attr-defined]
        response, hold = handle_message(service, credential, body)
        if hold:
            response = self._wait(service, credential, body, response, timeout)
        self._send(200, response)

    def _wait(
        self,
        service: Service,
        credential: str,
        body: bytes,
        waiting: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        """Hold the poll open until there is work or the timeout elapses (ADR-0007)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(_WAKE_S)
            if service.has_deliverable(credential):
                answered, _ = handle_message(service, credential, body)
                return answered
        return waiting

    def _credential(self) -> str | None:
        header = self.headers.get("Authorization") or ""
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return None
        return token.strip()

    def _send(self, status: int, message: dict[str, Any]) -> None:
        body = serialise(message)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _plain(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Quiet by default: a request line can carry a token in a header, never logged."""


class ApiServer(ThreadingHTTPServer):
    """A local HTTP server bound to the loopback interface and nothing else."""

    daemon_threads = True

    def __init__(
        self,
        service: Service,
        *,
        host: str = "127.0.0.1",
        port: int = 8787,
        poll_timeout_s: float = DEFAULT_POLL_TIMEOUT_S,
    ) -> None:
        super().__init__((host, port), _Handler)
        self.service = service
        self.poll_timeout_s = poll_timeout_s

    @property
    def endpoint(self) -> str:
        """The URL a plugin posts to."""
        host, port = self.server_address[0], self.server_address[1]
        return f"http://{host}:{port}{ENDPOINT}"
