"""Load version-controlled skill packs used by the project agent."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_SKILL_PACKS = Path(__file__).parent / "skillpacks"
_MAX_SKILL_BYTES = 96 * 1024


class SkillPackError(ValueError):
    """A requested built-in skill pack is missing or malformed."""


@dataclass(frozen=True, slots=True)
class SkillPack:
    name: str
    instructions: str


class SkillLibrary:
    """Resolve selected project skills to trusted, bounded prompt material."""

    def __init__(self, root: Path = _SKILL_PACKS) -> None:
        self._root = root

    @property
    def available(self) -> tuple[str, ...]:
        if not self._root.is_dir():
            return ()
        return tuple(sorted(path.name for path in self._root.iterdir() if path.is_dir()))

    def load(self, name: str) -> SkillPack:
        if not isinstance(name, str) or name not in self.available:
            raise SkillPackError(f"unknown skill pack {name!r}")
        folder = self._root / name
        entry = folder / "SKILL.md"
        try:
            body = _read_markdown(entry)
            references = [
                _read_markdown(path) for path in sorted((folder / "references").glob("*.md"))
            ]
        except OSError as exc:
            raise SkillPackError(f"skill pack {name!r} could not be loaded") from exc
        instructions = "\n\n".join((body, *references))
        if len(instructions.encode("utf-8")) > _MAX_SKILL_BYTES:
            raise SkillPackError(f"skill pack {name!r} exceeds its prompt size limit")
        return SkillPack(name=name, instructions=instructions)


def _read_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n"):
        _, _, text = text.partition("---\n")
        _, separator, body = text.partition("\n---\n")
        if not separator:
            raise SkillPackError(f"skill file {path.name!r} has malformed frontmatter")
        text = body
    return text.strip()
