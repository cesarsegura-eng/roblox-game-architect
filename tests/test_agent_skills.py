from pathlib import Path
from zipfile import ZipFile

from tools.package_agent_skills import create_archive, synchronize

ROOT = Path(__file__).resolve().parents[1]
AGENT_SKILLS = ROOT / "skills"


def test_agent_skill_distribution_matches_core_packs() -> None:
    assert synchronize(check=True)


def test_end_to_end_agent_skill_is_portable_and_discoverable() -> None:
    skill = AGENT_SKILLS / "roblox-game-architect" / "SKILL.md"
    body = skill.read_text(encoding="utf-8")
    assert body.startswith("---\nname: roblox-game-architect\n")
    assert "separately hosted MCP services" in body
    assert "not prerequisites on the user's PC" in body
    assert "rga_apply_scene_recipe" in body
    assert "rga_build_place" in body


def test_each_domain_skill_has_frontmatter() -> None:
    skill_names = {
        "blender-scene-authoring",
        "character-modeling-animation",
        "game-design-planning",
        "roblox-studio-map-blockouts",
        "world-environments",
    }
    assert {path.name for path in AGENT_SKILLS.iterdir() if path.is_dir()} == (
        skill_names | {"roblox-game-architect"}
    )
    for name in skill_names:
        body = (AGENT_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert body.startswith(f"---\nname: {name}\n")


def test_agent_neutral_archive_contains_all_skills_and_is_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "one.zip"
    second = tmp_path / "two.zip"

    create_archive(first)
    create_archive(second)

    assert first.read_bytes() == second.read_bytes()
    with ZipFile(first) as archive:
        names = archive.namelist()
        assert "skills/roblox-game-architect/SKILL.md" in names
        assert "skills/world-environments/SKILL.md" in names
        assert len([name for name in names if name.endswith("/SKILL.md")]) == 6
