"""Durable storage for the lifecycle records, behind a seam.

ADR-0011 needs two things of whatever stores this: the state `delivered` persisted
*before* the response carrying a work item leaves, and an accepted result with its
idempotency record committed *before* `ok` is emitted. Neither is a transaction that
includes the network, and no store can offer one.

**The engine itself is still an open decision** (`ARCHITECTURE.md` section 6). What is
here is a provisional implementation, not that decision: one JSON document per
credential under `DATA_DIR`, replaced atomically. It is adequate for the local,
single-user service the design assumes, and it is behind `Store` so that choosing the
engine later does not reach into the service.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol


class Store(Protocol):
    """Somewhere a credential's lifecycle state can be read and durably written."""

    def load(self, credential: str) -> dict[str, Any] | None:
        """The stored state, or None when this credential has none yet."""
        ...

    def commit(self, credential: str, state: dict[str, Any]) -> None:
        """Write `state` so that it survives a crash. Raises on failure; never partially."""
        ...


class MemoryStore:
    """A store that keeps state in memory. For tests, and never durable."""

    def __init__(self) -> None:
        self._states: dict[str, str] = {}

    def load(self, credential: str) -> dict[str, Any] | None:
        raw = self._states.get(credential)
        return None if raw is None else json.loads(raw)

    def commit(self, credential: str, state: dict[str, Any]) -> None:
        self._states[credential] = json.dumps(state)


class FileStore:
    """One JSON document per credential under `root`, replaced atomically.

    `commit` returns only once the bytes and the directory entry are on the device, so a
    caller that responds after it returns satisfies ADR-0011's durability rules.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, credential: str) -> Path:
        # The credential is a secret and never becomes a file name: the file is named
        # after a stable digest of it, so DATA_DIR cannot leak the token.
        import hashlib

        digest = hashlib.sha256(credential.encode("utf-8")).hexdigest()[:32]
        return self._root / f"{digest}.json"

    def load(self, credential: str) -> dict[str, Any] | None:
        path = self._path(credential)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def commit(self, credential: str, state: dict[str, Any]) -> None:
        path = self._path(credential)
        body = json.dumps(state, ensure_ascii=False, indent=1).encode("utf-8")
        handle = tempfile.NamedTemporaryFile(
            mode="wb", dir=str(self._root), prefix=".commit-", delete=False
        )
        try:
            with handle as temporary:
                temporary.write(body)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(handle.name, path)
        except BaseException:
            Path(handle.name).unlink(missing_ok=True)
            raise
        self._sync_directory()

    def _sync_directory(self) -> None:
        """Make the rename itself durable. Not available on every platform."""
        try:
            fd = os.open(str(self._root), os.O_RDONLY)
        except OSError:
            return  # Windows cannot open a directory this way; the replace is atomic there
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)
