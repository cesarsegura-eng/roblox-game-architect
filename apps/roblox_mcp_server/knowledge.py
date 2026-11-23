"""Read the published authoring guides and input schemas from the installed package."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files

from core.skills import SkillLibrary

_SKILLS = {
    "roblox-game-architect": "Start here for the full remote game authoring workflow.",
    "game-design-planning": "Plan the game loop, first playable slice and acceptance checks.",
    "world-environments": "Design biomes, buildings, interiors, exteriors and player routes.",
    "blender-scene-authoring": "Construct scene recipes for remote Blender builds.",
    "character-modeling-animation": "Design character proportions, rigs and movement.",
    "roblox-studio-map-blockouts": "Lay out a playable Roblox blockout with supported primitives.",
}
_SCHEMAS = {
    "scene-recipe-v3": "Input contract for environments, models, rigs and animations.",
    "game-plan-v2": "Input contract for game plans, gameplay rules and the first playable slice.",
}
with files("core").joinpath("reference_scenes.json").open("rb") as _stream:
    _raw_references = _stream.read(256 * 1024 + 1)
if len(_raw_references) > 256 * 1024:
    raise ValueError("Packaged reference scenes exceed their size limit")
_REFERENCES = json.loads(_raw_references)
_RESOURCES = {
    **{
        f"rga://skills/{name}": (name, description, "text/markdown")
        for name, description in _SKILLS.items()
    },
    **{
        f"rga://schemas/{name}": (name, description, "application/schema+json")
        for name, description in _SCHEMAS.items()
    },
    **{
        f"rga://examples/{name}": (name, entry["description"], "application/json")
        for name, entry in _REFERENCES.items()
    },
}


def list_resources() -> list[dict[str, str]]:
    return [
        {"uri": uri, "name": name, "description": description, "mimeType": mime}
        for uri, (name, description, mime) in _RESOURCES.items()
    ]


@lru_cache(maxsize=len(_RESOURCES))
def _resource_text(name: str) -> str:
    if name in _SKILLS:
        return SkillLibrary().load(name).instructions
    if name in _REFERENCES:
        text = _REFERENCES[name]["text"]
        if len(text.encode("utf-8")) > 96 * 1024:
            raise ValueError("Packaged reference exceeds resource size limit")
        return text
    schema = files("core").joinpath("schemas", f"{name}.schema.json")
    with schema.open("rb") as stream:
        raw = stream.read(96 * 1024 + 1)
    if len(raw) > 96 * 1024:
        raise ValueError("Packaged schema exceeds resource size limit")
    return raw.decode("utf-8")


def read_resource(uri: str) -> dict[str, str] | None:
    entry = _RESOURCES.get(uri)
    if entry is None:
        return None
    name, _, mime = entry
    return {"uri": uri, "mimeType": mime, "text": _resource_text(name)}
