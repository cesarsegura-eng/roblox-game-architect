from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from api.store import FileStore, SQLiteStore


def test_sqlite_store_round_trips_across_instances(tmp_path):
    state = {"sequence": 3, "items": [{"id": "work-1", "status": "delivered"}]}
    SQLiteStore(tmp_path).commit("secret-token", state)

    assert SQLiteStore(tmp_path).load("secret-token") == state
    assert SQLiteStore(tmp_path).load("another-token") is None


def test_sqlite_store_does_not_write_raw_credentials(tmp_path):
    credential = "private bearer token"
    store = SQLiteStore(tmp_path)
    store.commit(credential, {"events": []})

    database = (tmp_path / "api-state.sqlite3").read_bytes()
    assert credential.encode() not in database
    assert hashlib.sha256(credential.encode()).hexdigest().encode() in database


def test_sqlite_store_migrates_legacy_file_on_first_access(tmp_path):
    credential = "legacy credential"
    state = {"events": [{"kind": "session_opened", "sequence": 1}]}
    legacy_store = FileStore(tmp_path)
    legacy_store.commit(credential, state)
    legacy_path = legacy_store._path(credential)

    store = SQLiteStore(tmp_path)
    assert store.load(credential) == state
    assert not legacy_path.exists()
    assert store.load(credential) == state


def test_invalid_legacy_state_is_preserved_for_recovery(tmp_path):
    credential = "broken legacy credential"
    store = FileStore(tmp_path)
    legacy_path = store._path(credential)
    legacy_path.write_text('{"bad": NaN}', encoding="utf-8")

    with pytest.raises(ValueError):
        SQLiteStore(tmp_path).load(credential)

    assert legacy_path.exists()


def test_sqlite_store_rejects_non_json_numbers(tmp_path):
    store = SQLiteStore(tmp_path)

    with pytest.raises(ValueError):
        store.commit("credential", {"not_finite": float("nan")})


def test_sqlite_store_migrated_document_is_json(tmp_path):
    credential = "migration check"
    state = {"events": []}
    legacy = FileStore(tmp_path)
    legacy.commit(credential, state)
    SQLiteStore(tmp_path).load(credential)

    with sqlite3.connect(tmp_path / "api-state.sqlite3") as connection:
        body = connection.execute("SELECT state_json FROM credential_state").fetchone()[0]
    assert json.loads(body) == state
