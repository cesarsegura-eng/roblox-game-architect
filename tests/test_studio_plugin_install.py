"""The Studio plugin package includes protocol validation without user tooling."""

from pathlib import Path

from tools.package_luau_protocol_schemas import OUTPUT, render

PLUGIN_SOURCE = Path(__file__).resolve().parent.parent / "apps" / "studio-plugin" / "src"


def test_plugin_source_contains_main_and_strict_protocol_parser() -> None:
    files = sorted(
        path.relative_to(PLUGIN_SOURCE).as_posix()
        for path in PLUGIN_SOURCE.rglob("*")
        if path.is_file() and path.name != ".gitkeep"
    )

    assert files == [
        "Main.plugin.lua",
        "Protocol/SchemaValidator.lua",
        "Protocol/Schemas.lua",
        "Protocol/StrictJson.lua",
    ]


def test_plugin_loads_only_its_bundled_protocol_parser() -> None:
    source = (PLUGIN_SOURCE / "Main.plugin.lua").read_text(encoding="utf-8")
    code = "\n".join(line.split("--", 1)[0] for line in source.splitlines())

    assert 'require(script.Parent:WaitForChild("Protocol"):WaitForChild("StrictJson"))' in code
    assert 'require(script.Parent:WaitForChild("Protocol"):WaitForChild("Schemas"))' in code
    assert 'require(script.Parent:WaitForChild("Protocol"):WaitForChild("SchemaValidator"))' in code
    assert "SchemaValidator.message(" in code
    assert "HttpService:JSONDecode" not in code


def test_bundled_protocol_schemas_are_generated_from_the_contract() -> None:
    assert OUTPUT.read_text(encoding="utf-8") == render()
