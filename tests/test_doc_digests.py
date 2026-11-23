"""A digest quoted in the documentation must be a whole SHA-256.

The status page once recorded a Treasure Hunt artifact digest that was three
characters short, so nobody could compare it with a fresh build. Digests are the
evidence these pages exist to keep, so a truncated or mistyped one is a defect.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Long enough to be a SHA-256 attempt (a git SHA-1 is 40), short or long enough to be wrong.
CANDIDATE = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{55,70}(?![0-9a-fA-F])")


def _documents() -> list[Path]:
    roots = [ROOT / "docs", ROOT / "apps", ROOT / "packages", ROOT / "skills", ROOT / "examples"]
    found = [ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "ARCHITECTURE.md"]
    for root in roots:
        found.extend(path for path in root.rglob("*.md") if "node_modules" not in path.parts)
    return sorted(set(found))


def test_every_quoted_digest_is_exactly_64_hex_characters() -> None:
    wrong = [
        f"{path.relative_to(ROOT).as_posix()}: {match.group(0)} ({len(match.group(0))})"
        for path in _documents()
        for match in CANDIDATE.finditer(path.read_text(encoding="utf-8"))
        if len(match.group(0)) != 64
    ]

    assert wrong == []
