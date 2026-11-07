"""Durable storage for API lifecycle records, behind a small store seam.

The production store commits each state transition in a SQLite FULL-synchronous
transaction before the service sends its response. It is intended for the local,
single-user API and a local disk, not a multi-host deployment or network filesystem.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
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
    """Legacy per-credential JSON storage retained for migration compatibility.

    The API uses :class:`SQLiteStore`. This class can create legacy state in tests
    and supports tools that still need to read the old on-disk layout.
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
        """Best-effort directory sync for the legacy file format."""
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


class SQLiteStore:
    """Transactional, crash-durable lifecycle state for the local API.

    The DB stores a full SHA-256 credential key instead of the bearer credential.
    Existing FileStore documents are migrated on first access for that credential;
    the legacy file is removed only after the SQLite transaction commits.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._path = root / "api-state.sqlite3"
        with closing(self._connect()) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS credential_state ("
                "credential_hash TEXT PRIMARY KEY, state_json TEXT NOT NULL)"
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    @staticmethod
    def _key(credential: str) -> str:
        return hashlib.sha256(credential.encode("utf-8")).hexdigest()

    def _legacy_path(self, credential: str) -> Path:
        return self._root / f"{self._key(credential)[:32]}.json"

    def load(self, credential: str) -> dict[str, Any] | None:
        key = self._key(credential)
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT state_json FROM credential_state WHERE credential_hash = ?", (key,)
            ).fetchone()
            if row is not None:
                return json.loads(row[0])

            legacy = self._legacy_path(credential)
            if not legacy.exists():
                return None
            state = json.loads(legacy.read_text(encoding="utf-8"))
            body = json.dumps(state, ensure_ascii=False, allow_nan=False)
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT OR IGNORE INTO credential_state (credential_hash, state_json) "
                "VALUES (?, ?)",
                (key, body),
            )
            row = connection.execute(
                "SELECT state_json FROM credential_state WHERE credential_hash = ?", (key,)
            ).fetchone()
            connection.commit()
        legacy.unlink(missing_ok=True)
        return json.loads(row[0])

    def commit(self, credential: str, state: dict[str, Any]) -> None:
        body = json.dumps(state, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO credential_state (credential_hash, state_json) VALUES (?, ?) "
                "ON CONFLICT (credential_hash) DO UPDATE SET state_json = excluded.state_json",
                (self._key(credential), body),
            )
            connection.commit()
