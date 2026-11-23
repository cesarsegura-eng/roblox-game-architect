"""Keep the CI Luau tool manager at the same pinned version as local builds."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ci_pins_rokit_in_every_install_job() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    action_count = workflow.count("uses: CompeyDev/setup-rokit@v0.2.1")
    version_count = workflow.count("version: v1.2.0")

    assert action_count == 2
    assert version_count == action_count


def test_selene_uses_a_checked_in_roblox_standard_library() -> None:
    config = tomllib.loads((ROOT / "selene.toml").read_text(encoding="utf-8"))
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert config["roblox-std-source"] == "pinned"
    assert (ROOT / "roblox.yml").is_file()
    assert "test -s roblox.yml" in workflow
    assert "selene update-roblox-std" not in workflow
