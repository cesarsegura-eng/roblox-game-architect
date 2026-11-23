import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import build_roblox_place


def test_cli_builds_and_reports_fixed_mode_artifact(tmp_path: Path, monkeypatch, capsys) -> None:
    recipe = tmp_path / "recipe.json"
    recipe.write_text('{"schema_version": 3}', encoding="utf-8")
    output = tmp_path / "build" / "place.rbxlx"
    place_bytes = b"<roblox/>"

    class FakeBuilder:
        def __init__(self, executable: str) -> None:
            assert executable == "rojo-test"

        def build(self, payload: object, *, gameplay_mode: str):
            assert payload == {"schema_version": 3}
            assert gameplay_mode == "treasure_hunt"
            return SimpleNamespace(
                place_file=place_bytes,
                gameplay_mode=gameplay_mode,
                object_count=3,
                part_count=4,
            )

    monkeypatch.setattr(build_roblox_place, "RojoPlaceBuilder", FakeBuilder)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_roblox_place.py",
            str(recipe),
            str(output),
            "--gameplay-mode",
            "treasure_hunt",
            "--rojo-bin",
            "rojo-test",
        ],
    )

    assert build_roblox_place.main() == 0
    assert output.read_bytes() == place_bytes
    assert hashlib.sha256(place_bytes).hexdigest() in capsys.readouterr().out


def test_cli_does_not_overwrite_existing_place_without_explicit_flag(
    tmp_path: Path, monkeypatch
) -> None:
    recipe = tmp_path / "recipe.json"
    recipe.write_text("{}", encoding="utf-8")
    output = tmp_path / "place.rbxlx"
    output.write_bytes(b"keep")
    monkeypatch.setattr(sys, "argv", ["build_roblox_place.py", str(recipe), str(output)])

    with pytest.raises(SystemExit, match="2"):
        build_roblox_place.main()
    assert output.read_bytes() == b"keep"
