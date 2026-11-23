"""Run shared valid and invalid protocol vectors through the Luau validator."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from protocol_schemas import EXAMPLES_DIR, load_vector, vector_text

from tools.package_luau_protocol_schemas import OUTPUT, render

ROOT = Path(__file__).resolve().parents[3]
RUNNER = Path(__file__).with_name("run_luau_schema_vectors.luau")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("lute") is None, reason="Lute is not installed"),
]


def test_luau_schema_validator_matches_all_shared_message_vectors(tmp_path: Path) -> None:
    assert OUTPUT.read_text(encoding="utf-8") == render()
    index = json.loads((EXAMPLES_DIR / "index.json").read_text(encoding="utf-8"))
    cases = []
    for group in ("valid", "invalid"):
        for relative in index[group]:
            vector = load_vector(relative)
            cases.append(
                {
                    "name": relative,
                    "text": vector_text(vector),
                    "expect": {
                        key: vector["expect"][key]
                        for key in ("valid", "stage", "path")
                        if key in vector["expect"]
                    },
                }
            )
    manifest = {"cases": cases}
    manifest_path = tmp_path / "schema-vectors.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    completed = subprocess.run(  # noqa: S603 - pinned runtime executes repository-owned harness.
        [shutil.which("lute"), "run", str(RUNNER), str(manifest_path)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
        env=os.environ.copy(),
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert f"PASS {len(cases)} protocol schema vectors" in completed.stdout
