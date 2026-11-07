"""The Studio plugin must stay installable as one loose file.

A user installs Roblox Studio and nothing else. If the plugin were split into
modules it would need a build tool (Rojo, via rokit) just to be installed, so
the single-file shape is protected here rather than left to convention.
"""

import re
from pathlib import Path

PLUGIN_SOURCE = Path(__file__).resolve().parent.parent / "apps" / "studio-plugin" / "src"


def test_plugin_source_is_exactly_one_file() -> None:
    files = sorted(path.name for path in PLUGIN_SOURCE.iterdir() if path.name != ".gitkeep")

    assert files == ["Main.plugin.lua"]


def test_plugin_does_not_load_other_modules() -> None:
    source = (PLUGIN_SOURCE / "Main.plugin.lua").read_text(encoding="utf-8")
    # `require` of a sibling ModuleScript or of a script-relative path would make
    # a loose, single-file install impossible.
    code = "\n".join(line.split("--", 1)[0] for line in source.splitlines())

    assert re.search(r"\brequire\s*\(", code) is None
    assert "script.Parent" not in code
