import json
import re
from pathlib import Path
from zipfile import ZipFile

from tools.package_agent_skills import create_archive, synchronize

ROOT = Path(__file__).resolve().parents[1]
AGENT_SKILLS = ROOT / "skills"
CLAUDE_PLUGIN = ROOT / "apps" / "claude-code-plugin"


def test_agent_skill_distribution_matches_core_packs() -> None:
    assert synchronize(check=True)


def test_end_to_end_agent_skill_is_portable_and_discoverable() -> None:
    skill = AGENT_SKILLS / "roblox-game-architect" / "SKILL.md"
    body = skill.read_text(encoding="utf-8")
    assert body.startswith("---\nname: roblox-game-architect\n")
    assert "skills, knowledge, and tools" in body
    assert "not prerequisites on the user's PC" in body
    assert "never create, install, replace, rename, proxy" in body.replace("\n", " ")
    assert "Roblox Studio's native MCP" in body
    assert "rga_apply_scene_recipe" in body
    assert "rga_build_place" in body


def test_coordinator_documents_every_fixed_rule_gameplay_action() -> None:
    body = (AGENT_SKILLS / "roblox-game-architect" / "SKILL.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", body)

    for phrase in (
        "`speed_boost` on a `collectible` or `prop`",
        "`amount` 1-16 and `duration_seconds` 1-30",
        "caps it at 32",
        "per-part collection for another round",
    ):
        assert phrase in normalized


def test_game_plan_skill_reference_matches_fixed_rule_gameplay_contract() -> None:
    guide = (AGENT_SKILLS / "game-design-planning" / "references" / "game-plan-v2.md").read_text(
        encoding="utf-8"
    )
    normalized = re.sub(r"\s+", " ", guide)

    for phrase in (
        "`speed_boost` (collectible or prop role",
        "`amount` 1-16 and `duration_seconds` 1-30",
        "caps it at 32",
        "restores its saved original value",
    ):
        assert phrase in normalized


def test_each_domain_skill_has_frontmatter() -> None:
    skill_names = {
        "blender-scene-authoring",
        "character-modeling-animation",
        "game-design-planning",
        "roblox-gameplay-engineering",
        "roblox-terrain-authoring",
        "roblox-ui-ux",
        "roblox-studio-map-blockouts",
        "world-environments",
    }
    assert {path.name for path in AGENT_SKILLS.iterdir() if path.is_dir()} == (
        skill_names | {"roblox-game-architect"}
    )
    for name in skill_names:
        body = (AGENT_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert body.startswith(f"---\nname: {name}\n")


def test_map_skill_separates_character_traversal_from_teleport_checks() -> None:
    body = (AGENT_SKILLS / "roblox-studio-map-blockouts" / "SKILL.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", body).casefold()

    for phrase in (
        "character_navigation",
        "user_keyboard_input",
        "teleport-based gameplay drivers",
        "not that a player can traverse the route",
        "report which kind of movement evidence was actually collected",
    ):
        assert phrase in normalized


def test_architecture_guidance_requires_real_clearance_at_doorways() -> None:
    environment_skill = (AGENT_SKILLS / "world-environments" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    space_reference = (
        AGENT_SKILLS / "world-environments" / "references" / "playable-spaces.md"
    ).read_text(encoding="utf-8")
    blender_reference = (
        AGENT_SKILLS / "blender-scene-authoring" / "references" / "scene-recipes.md"
    ).read_text(encoding="utf-8")

    assert "actual empty clearance" in environment_skill
    assert "never fill the walk-through volume" in environment_skill
    assert "Build a doorway into the wall geometry" in space_reference
    assert "no faces across the aperture" in blender_reference


def test_world_environment_skill_requires_cited_regional_research_without_mcp_duplication() -> None:
    environment_skill = (AGENT_SKILLS / "world-environments" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    normalized = re.sub(r"\s+", " ", environment_skill).casefold()

    for phrase in (
        "host agent's available web-search and page-fetch tools",
        "record the source urls",
        "keep the location fictional",
        "do not invent citations",
    ):
        assert phrase in normalized


def test_world_environment_effects_use_native_tools_and_cover_audio_visuals() -> None:
    environment_skill = (AGENT_SKILLS / "world-environments" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    reference = (
        AGENT_SKILLS / "world-environments" / "references" / "environment-effects.md"
    ).read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", reference).casefold()

    assert "references/environment-effects.md" in environment_skill
    assert "existing native studio mcp" in environment_skill.casefold()
    for phrase in (
        "workspace.terrain",
        "workspace.globalwind",
        "particleemitter",
        "soundgroup",
        "do not invent audio asset ids",
        "execute_luau",
        "microprofiler",
    ):
        assert phrase.casefold() in normalized


def test_game_planning_skill_carries_production_release_gates() -> None:
    planning_skill = (AGENT_SKILLS / "game-design-planning" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    production_reference = (
        (AGENT_SKILLS / "game-design-planning" / "references" / "production-readiness.md")
        .read_text(encoding="utf-8")
        .replace("\n", " ")
    )

    assert "references/production-readiness.md" in planning_skill
    for phrase in (
        "Server authority and abuse cases",
        "Persistence, commerce, and recovery",
        "Playability, performance, and operations",
        "human-owned release gates",
        "A pass at one level does not imply the next.",
    ):
        assert phrase in production_reference


def test_gameplay_engineering_skill_uses_native_studio_tools_and_secure_patterns() -> None:
    skill = (AGENT_SKILLS / "roblox-gameplay-engineering" / "SKILL.md").read_text(encoding="utf-8")
    systems = (
        AGENT_SKILLS / "roblox-gameplay-engineering" / "references" / "server-systems.md"
    ).read_text(encoding="utf-8")
    normalized_skill = re.sub(r"\s+", " ", skill)

    for phrase in (
        "existing native Studio MCP",
        "Do not route gameplay edits through the optional RGA Roblox service",
        "RemoteEvent",
        "UpdateAsync",
        "Play Solo does not prove multiplayer correctness",
    ):
        assert phrase in normalized_skill
    assert "Security and cheat mitigation" in systems
    assert "Data store best practices" in systems
    assert "Studio testing modes" in systems
    for phrase in (
        "Profile lifecycle",
        "mark it `Unavailable`",
        "same atomic key update as the data",
        "ambiguous outcome",
        "Never enable Studio API access against production data",
        "crashed lock owner",
    ):
        assert phrase in systems
    assert "Player data and purchasing systems" in systems
    assert "Data store error codes and limits" in systems


def test_scene_authoring_routes_assets_through_existing_native_studio_tools() -> None:
    skill = (AGENT_SKILLS / "blender-scene-authoring" / "SKILL.md").read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", skill).casefold()

    for phrase in (
        "native `generate_mesh`, `generate_material`, and `generate_procedural_model`",
        "native `search_asset`",
        "before `insert_asset`",
        "embedded scripts",
        "remote blender mcp",
        "do not add a second roblox mcp connection",
    ):
        assert phrase.casefold() in normalized


def test_roblox_ui_skill_covers_accessibility_input_and_server_authority() -> None:
    skill = (AGENT_SKILLS / "roblox-ui-ux" / "SKILL.md").read_text(encoding="utf-8")
    references = (AGENT_SKILLS / "roblox-ui-ux" / "references" / "ui-systems.md").read_text(
        encoding="utf-8"
    )
    normalized = re.sub(r"\s+", " ", skill).casefold()

    for phrase in (
        "existing native Roblox Studio MCP",
        "never install a second Studio connection",
        "server",
        "preferredinput",
        "preferredtextsize",
        "gamepad focus",
        "controller emulator",
    ):
        assert phrase.casefold() in normalized
    assert "Adaptive design guidelines" in references
    assert "Accessibility guidelines" in references
    assert "Localization" in references
    assert "Server rejects forged" in references


def test_terrain_skill_uses_native_studio_with_bounded_voxel_writes() -> None:
    skill = (AGENT_SKILLS / "roblox-terrain-authoring" / "SKILL.md").read_text(encoding="utf-8")
    reference = (
        AGENT_SKILLS / "roblox-terrain-authoring" / "references" / "terrain-recipes.md"
    ).read_text(encoding="utf-8")
    normalized = re.sub(r"\s+", " ", skill).casefold()
    for phrase in (
        "existing native studio mcp",
        "does not add an mcp server",
        "list_roblox_studios",
        "execute_luau",
    ):
        assert phrase.casefold() in normalized
    environment = re.sub(
        r"\s+",
        " ",
        (AGENT_SKILLS / "world-environments" / "SKILL.md").read_text(encoding="utf-8"),
    )
    normalized_reference = re.sub(r"\s+", " ", reference)
    assert "dedicated `roblox-terrain-authoring` skill" in environment
    assert "131,072 voxels per" in normalized_reference
    assert "`WriteVoxels`" in normalized_reference
    assert "Terrain:Clear()" in normalized_reference
    assert "disposable copy" in normalized_reference
    assert "terrain patch is occupied" in normalized_reference
    assert "RGA_TERRAIN_HEIGHTFIELD_PASS" in normalized_reference


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
        game_plan_schema = "skills/game-design-planning/references/game-plan-v2.schema.json"
        scene_recipe_schema = (
            "skills/blender-scene-authoring/references/scene-recipe-v3.schema.json"
        )
        research_sources = (ROOT / "docs/art-direction/research-sources.md").read_bytes()
        portable_source_indexes = (
            "skills/blender-scene-authoring/references/research-sources.md",
            "skills/game-design-planning/references/research-sources.md",
            "skills/world-environments/references/research-sources.md",
            "skills/character-modeling-animation/references/research-sources.md",
        )
        assert game_plan_schema in names
        assert scene_recipe_schema in names
        assert all(name in names for name in portable_source_indexes)
        assert all(archive.read(name) == research_sources for name in portable_source_indexes)
        assert (
            archive.read(game_plan_schema)
            == (ROOT / "packages/core/schemas/game-plan-v2.schema.json").read_bytes()
        )
        assert (
            archive.read(scene_recipe_schema)
            == (ROOT / "packages/core/schemas/scene-recipe-v3.schema.json").read_bytes()
        )
        assert len([name for name in names if name.endswith("/SKILL.md")]) == 9


def test_claude_code_plugin_adds_blender_mcp_and_preserves_native_studio() -> None:
    manifest = json.loads(
        (CLAUDE_PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    servers = json.loads((CLAUDE_PLUGIN / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]

    assert manifest["name"] == "rga-game-architect"
    assert (CLAUDE_PLUGIN / manifest["icon"]).is_file()
    assert (CLAUDE_PLUGIN / "PRIVACY.md").is_file()
    assert manifest["privacyPolicyUrl"].endswith("/apps/claude-code-plugin/PRIVACY.md")
    assert len(list((CLAUDE_PLUGIN / "skills").iterdir())) == 9
    assert set(servers) == {"rga-blender"}
    assert servers["rga-blender"]["url"] == "https://${user_config.blender_mcp_host}/mcp"
    for name, server in servers.items():
        assert server["type"] == "http"
        assert "command" not in server
        assert server["headers"]["Authorization"] == (
            f"Bearer ${{user_config.{name.replace('rga-', '')}_mcp_token}}"
        )
        token_key = f"{name.replace('rga-', '')}_mcp_token"
        assert manifest["userConfig"][token_key]["sensitive"] is True
    assert manifest["userConfig"]["blender_mcp_host"]["required"] is True

    coordinator = (CLAUDE_PLUGIN / "skills" / "roblox-game-architect" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "native Studio MCP" in coordinator
    assert "configure a second Roblox MCP" in coordinator
    assert "install this project's Studio plugin" in coordinator
    assert "rbx-permissions" in coordinator
    assert "rbx-import-asset" in coordinator
    assert "optional compatibility path" in coordinator
    assert "Set up map build" not in coordinator
    assert "key-down, wait, and key-up" in coordinator

    marketplace = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert marketplace["plugins"][0]["name"] == manifest["name"]
    assert marketplace["plugins"][0]["source"]["path"] == "apps/claude-code-plugin"


def test_native_studio_asset_handoff_uses_temporary_blender_data_link() -> None:
    coordinator = (AGENT_SKILLS / "roblox-game-architect" / "SKILL.md").read_text(encoding="utf-8")
    blender_skill = (AGENT_SKILLS / "blender-scene-authoring" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "artifact_download_url" in coordinator
    assert "15-minute" in coordinator
    assert "open_cloud_invoke" in coordinator
    assert "20 MB per asset" in re.sub(r"\s+", " ", coordinator)
    assert "published experience" in coordinator
    assert "unpublished `.rbxlx`" in coordinator
    assert "folder the user already approved" in coordinator
    assert "configure a second Roblox MCP connection" in re.sub(r"\s+", " ", coordinator)
    assert "signed URL" in blender_skill
    assert "second Roblox MCP connection" in re.sub(r"\s+", " ", blender_skill)
    assert "rbx-permissions" in blender_skill
    assert "rbx-import-asset" in blender_skill
    assert "published, dedicated test experience" in re.sub(r"\s+", " ", blender_skill)


def test_native_studio_generation_and_reference_tools_are_documented() -> None:
    coordinator = (AGENT_SKILLS / "roblox-game-architect" / "SKILL.md").read_text(encoding="utf-8")
    blender_skill = (AGENT_SKILLS / "blender-scene-authoring" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "native MCP exposes `skill`" in coordinator
    assert "`http_get`" in coordinator
    assert "`generate_mesh`" in blender_skill
    assert "`generate_material`" in blender_skill
    assert "`generate_procedural_model`" in blender_skill
    assert "`wait_job_finished`" in blender_skill
    assert "permission, approval, and asset-persistence" in blender_skill


def test_roblox_domain_skills_refresh_native_platform_guidance() -> None:
    gameplay = (AGENT_SKILLS / "roblox-gameplay-engineering" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    ui = (AGENT_SKILLS / "roblox-ui-ux" / "SKILL.md").read_text(encoding="utf-8")
    character = (AGENT_SKILLS / "character-modeling-animation" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "its `skill` tool is available" in gameplay
    assert "`http_get`" in gameplay
    assert "exposes `skill`" in ui
    assert "`http_get`" in ui
    assert "exposes `skill`" in character
    assert "`http_get`" in character
