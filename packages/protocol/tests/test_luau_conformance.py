"""Exercise the production Luau strict parser against shared JSON vectors."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from protocol_schemas import EXAMPLES_DIR, load_vector, vector_text
from protocol_strict_json import MAX_MESSAGE_BYTES

ROOT = Path(__file__).resolve().parents[3]
RUNNER = Path(__file__).with_name("run_luau_parse_vectors.luau")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("lute") is None, reason="Lute is not installed"),
]


def test_luau_strict_json_parser_matches_all_shared_parse_vectors(tmp_path: Path) -> None:
    index = json.loads((EXAMPLES_DIR / "index.json").read_text(encoding="utf-8"))
    case_paths = []
    for relative in index["parse"]:
        vector = load_vector(relative)
        prefix = "accept__" if vector["expect"]["valid"] else "reject__"
        case_path = tmp_path / f"{prefix}{Path(relative).name}"
        case_path.write_text(vector_text(vector), encoding="utf-8")
        case_paths.append(str(case_path))

    exact_limit = tmp_path / "accept__exact-message-byte-limit.json"
    exact_limit.write_bytes(b'{"value":"' + b"x" * (MAX_MESSAGE_BYTES - 13) + b'"}')
    case_paths.append(str(exact_limit))
    invalid_utf8 = tmp_path / "reject__invalid-utf8.json"
    invalid_utf8.write_bytes(b'{"value":"\xff"}')
    case_paths.append(str(invalid_utf8))

    completed = subprocess.run(  # noqa: S603 - pinned runtime executes repository-owned harness.
        [shutil.which("lute"), "run", str(RUNNER), *case_paths],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
        env=os.environ.copy(),
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert f"PASS {len(case_paths)} strict JSON vectors" in completed.stdout
