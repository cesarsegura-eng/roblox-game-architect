"""Short-lived, single-artifact browser downloads for direct MCP agents."""

from __future__ import annotations

import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from core.roblox_place import MAX_PLACE_FILE_BYTES

DOWNLOAD_LIFETIME = 15 * 60
_MAX_BYTES = 64 * 1024 * 1024
_MAX_FILES = 256


class PlaceDownloads:
    def __init__(self, origin: str) -> None:
        parsed = urlsplit(origin)
        if (
            not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/?", origin, re.ASCII)
            or not parsed.hostname
            or parsed.port == 0
        ):
            raise ValueError("RGA_ROBLOX_DOWNLOAD_ORIGIN must be a fixed HTTPS origin")
        self.origin = origin.rstrip("/")
        self._files: dict[str, tuple[float, bytes]] = {}
        self._lock = threading.Lock()

    def issue(self, data: bytes) -> str:
        if not 0 < len(data) <= MAX_PLACE_FILE_BYTES:
            raise ValueError("Place exceeds the download size limit")
        with self._lock:
            now = time.monotonic()
            for key in [key for key, (end, _) in self._files.items() if end <= now]:
                del self._files[key]
            if (
                len(self._files) >= _MAX_FILES
                or sum(len(blob) for _, blob in self._files.values()) + len(data) > _MAX_BYTES
            ):
                raise ValueError("Place download storage is full")
            ticket = secrets.token_urlsafe(32)
            self._files[ticket] = (now + DOWNLOAD_LIFETIME, data)
        return f"{self.origin}/downloads/{ticket}.rbxlx"

    def read(self, path: str) -> bytes | None:
        match = re.fullmatch(r"/downloads/([A-Za-z0-9_-]{43})\.rbxlx", path, re.ASCII)
        if not match:
            return None
        with self._lock:
            entry = self._files.get(match[1])
            if entry is None:
                return None
            expires, data = entry
            if expires <= time.monotonic():
                del self._files[match[1]]
                return None
            return data
