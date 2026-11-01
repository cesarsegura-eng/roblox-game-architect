"""Checks on the scaffolding itself.

These exist so the test harness is proven to work before there is any engine to
test, and so two mistakes already made in this repository cannot come back
silently: a CRLF file committed from a Windows checkout, and a `pytest` step
that passes because it collected nothing.

The file list comes from git rather than from a directory walk, because the
invariants here are about what enters the repository. A walk also picks up
build artefacts — `.venv/`, `*.egg-info/` — which are gitignored, are not ours,
and whose line endings we do not control.
"""

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".mp3",
    ".ogg",
    ".wav",
    ".fbx",
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".rbxl",
    ".rbxm",
    ".rbxlx",
    ".rbxmx",
}

ROBLOX_BINARY_SUFFIXES = {".rbxl", ".rbxlx", ".rbxm", ".rbxmx"}


def _repository_files() -> list[Path]:
    """Every file git tracks or would track: committed plus untracked, minus ignored."""
    git = shutil.which("git")
    assert git is not None, "git is required to run these checks"
    # S603 is suppressed on this one call rather than ignored project-wide, so
    # the rule stays on for any future subprocess use. Here the executable is an
    # absolute path resolved by shutil.which, the argument list is a constant,
    # and no shell is involved.
    # (Do not start this comment with the word that RUF100 scans for: ruff reads
    # a comment opening with it as a blanket directive of its own.)
    result = subprocess.run(  # noqa: S603
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return [REPO_ROOT / name for name in result.stdout.split("\0") if name]


def test_fake_provider_is_in_effect():
    """Invariant I7: the suite runs against the fake provider, no key, no network.

    This also proves pytest-env is installed and that [tool.pytest.ini_options]
    is being read at all.
    """
    assert os.environ.get("LLM_PROVIDER") == "fake"


def test_text_files_use_lf():
    """No CRLF in anything the repository holds.

    .editorconfig declares eol=lf and .gitattributes enforces it; stylua is
    configured for Unix line endings and fails on CRLF. This catches a file
    written by a tool that translated newlines.
    """
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _repository_files()
        if path.suffix.lower() not in BINARY_SUFFIXES
        and path.is_file()
        and b"\r\n" in path.read_bytes()
    ]
    assert offenders == [], f"CRLF line endings found in: {offenders}"


def test_gitattributes_enforces_lf():
    """The enforcement must be in git, not only in .editorconfig."""
    gitattributes = REPO_ROOT / ".gitattributes"
    assert gitattributes.is_file(), ".gitattributes is missing"
    assert "eol=lf" in gitattributes.read_text(encoding="utf-8")


def test_no_roblox_binaries_in_repository():
    """ADR-0004: place and model files never enter the repository."""
    found = [
        str(path.relative_to(REPO_ROOT))
        for path in _repository_files()
        if path.suffix.lower() in ROBLOX_BINARY_SUFFIXES
    ]
    assert found == [], f"Roblox binaries present: {found}"


def test_lockfile_exists():
    """CI installs with `uv sync --locked`, which cannot work without this file."""
    assert (REPO_ROOT / "uv.lock").is_file(), (
        "uv.lock is missing — run `uv lock` and commit it (CONTRIBUTING.md)"
    )
