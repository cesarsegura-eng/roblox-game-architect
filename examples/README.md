# examples/

Hand-curated, version-controlled example projects and scene recipes.

Examples include a small coastal lookout blockout in both v1 and v2 formats for
the Blender extension. The v2 example demonstrates a custom low-poly cliff mesh.
The desert courtyard home v2 example exercises separate interior and exterior
spaces. These are hand-authored contract examples, not AI output or finished
Roblox maps.

`worlds/rainforest-treasure-hunt/` is a Scene Recipe v3 blockout designed for
the fixed `treasure_hunt` place-build mode. It exercises route-aligned
collectibles, Roblox environment settings, and a generated neutral start pad.
`worlds/rainforest-checkpoint-obby/` is a three-segment Scene Recipe v3 route
for the fixed `obby` mode. It exercises ordered checkpoints, respawn points,
and session-only progress statistics.

## What belongs here

Small, readable, reproducible Roblox project definitions used as:

- **fixtures for the evaluation suite** — fixed inputs, so a change to a prompt
  or an agent can be shown to improve or regress behaviour,
- **integration-test inputs**,
- **documentation** of what the agent is expected to handle.
- **Blender integration fixtures** — data-only recipes to check the handoff and
  guide artists through supported scene parts.

Validate a recipe before importing it into Blender:

```powershell
uv run python tools/validate_scene_recipe.py examples/worlds/mistral-coast-lookout/scene-recipe.json
uv run python tools/validate_scene_recipe.py examples/worlds/mistral-coast-lookout-v2/scene-recipe.json
uv run python tools/validate_scene_recipe.py examples/worlds/desert-courtyard-home-v2/scene-recipe.json
uv run python tools/validate_scene_recipe.py examples/worlds/desert-courtyard-home-v3/scene-recipe.json
uv run python tools/validate_scene_recipe.py examples/worlds/rainforest-treasure-hunt/scene-recipe.json
uv run python tools/build_roblox_place.py examples/worlds/rainforest-treasure-hunt/scene-recipe.json dist/rainforest-treasure-hunt.rbxlx --gameplay-mode treasure_hunt
uv run python tools/validate_scene_recipe.py examples/worlds/rainforest-checkpoint-obby/scene-recipe.json
uv run python tools/build_roblox_place.py examples/worlds/rainforest-checkpoint-obby/scene-recipe.json dist/rainforest-checkpoint-obby.rbxlx --gameplay-mode obby
```

## What does not belong here

Projects the agent generated. Those are written to `DATA_DIR` (default `./data`,
gitignored) and never committed
([ADR-0004](../docs/architecture/adr/0004-generated-project-storage.md)). Keeping
generated output out of the source tree is what preserves the distinction
between what a human wrote and what the model wrote — which is exactly what you
need in order to audit the system.

## Rules

- Luau text and JSON only. No `.rbxl`, `.rbxlx`, `.rbxm` or `.rbxmx` — they are
  binary, they do not diff, and `.gitignore` blocks them.
- Small enough to read in one sitting. An example nobody reads is dead weight.
- Each example gets a README saying what it exercises and what good output
  looks like.
