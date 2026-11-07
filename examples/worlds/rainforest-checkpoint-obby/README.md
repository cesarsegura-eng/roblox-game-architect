# Rainforest Canopy Obby

A low-poly rainforest checkpoint course with three sections joined by two
walkways.
The fixed `obby` mode adds a neutral start/checkpoint spawn on each segment,
sequential touch progression, respawn checkpoints, and session-only Stage and
Wins leaderboard stats. The map uses the same recipe and remote build pipeline
as other examples; no model-generated Luau is included.

## Build through the two MCP services

For an agent connected to the hosted Roblox MCP service, first call
`rga_review_game_plan` with the contents of `game-plan.json` as `plan` and
`scene-recipe.json` as `recipe`. This reviews the collect-and-win variant.
Correct any reported errors, then pass the returned `build_settings` together
with the same `recipe` and a new UUID `request_id` to `rga_build_place`.
When the host enables download links, `rga_build_place_download` accepts the
same inputs and returns a temporary private link instead of embedding the
place file in the agent's context. Neither route requires installations on
the end user's computer.

The review checks that the three available coins can satisfy the three-point
win threshold, that the required roles exist, and that the route passes the
static geometry checks. It does not certify Roblox physics or production
readiness. Keep `game-plan.json` and `gameplay-rules.json` consistent when
changing the example; the MCP smoke test compares them before building.

From a contributor checkout with the Python package installed, set
`BLENDER_MCP_URL`, `BLENDER_MCP_BEARER_TOKEN`, `ROBLOX_MCP_URL` and
`ROBLOX_MCP_BEARER_TOKEN` for the two service connections. Run
`python tools/build_rainforest_demo.py`. The run directory contains Blender's
`rainforest.glb`, a playable `rainforest.rbxlx` built from recipe Parts, and a
receipt with their hashes. Both services work with Roblox cloud settings empty.

With Lute 1.0.0 on the contributor PATH, run
`python tools/check_rainforest_round.py <run-directory>/rainforest.rbxlx`.
The check verifies the artifact's server script, rules and touch targets, then
exercises two rounds with simulated players. Roblox physics, actual avatar
contacts, networking and respawn still require an engine playtest.

## Build a single place on the authoring host

Build an `.rbxlx` place artifact with pinned Rojo 7.7.1 available on the
contributor's path:

```sh
python tools/build_roblox_place.py \
  examples/worlds/rainforest-checkpoint-obby/scene-recipe.json \
  dist/rainforest-checkpoint-obby.rbxlx \
  --gameplay-mode obby
```

The same recipe also demonstrates a complete data-driven collect-and-win loop.
Collect the three canopy coins along the route (one session point each), then
touch the summit lookout to win. The win resets points so the round can be
replayed. Touching the lava vent near the path edge eliminates the player and
uses the standard respawn:

```sh
python tools/build_roblox_place.py \
  examples/worlds/rainforest-checkpoint-obby/scene-recipe.json \
  dist/rainforest-rule-game.rbxlx \
  --gameplay-mode rule_game \
  --gameplay-rules examples/worlds/rainforest-checkpoint-obby/gameplay-rules.json
```

`rule_game` supports touch-triggered `award_points`, `heal`, `eliminate`, and
threshold-based `award_win` effects through one repository-owned server script.
The fixed server template creates a per-player objective panel with points and
wins, updates it on interactions, and retains it through character respawns.
The panel states that progress lasts for the session. Wins and points are
session-only; this does not add quests, custom UI layouts, saved progress, or
arbitrary Luau. The simulated round check covers panel text updates; visual
layout and readability on Roblox devices still require engine review.

This is a playable mechanics prototype, not a production-complete Obby. This
recipe includes a lava vent tagged with the `hazard` role, which the fixed Obby
template connects to server-side lethal touch behavior. Moving obstacles, saved
progression, client UI, and multiplayer runtime evidence are not included. Users
of the hosted agent/MCP workflow do not install Rojo or
Roblox Studio; this command is for repository contributors. The generated
server script is project-owned and must be checked against the current trusted
template in `packages/core/gameplay_templates.py`.

## Isolated playtest checklist

HUD check on 2026-11-07: `dist/rainforest-rule-game-hud.rbxlx` (33,721 bytes,
SHA-256 `d8daca7e7bac9f2556423567a940d888485bd3e5533518b5734121ca4a705fb9`)
opened in the installed Roblox Studio and started in Play Solo. The player
spawned on the start platform. The objective panel displayed the three-point
win condition, `Points: 0 | Wins: 0`, and the session-progress notice. All text
was visible in the approximately 530-by-675-pixel client viewport. Studio showed
the Compatibility-to-Voxel lighting migration notice before the test. Play
Solo was stopped afterward; the file was not saved or published through Studio.
This verifies initial HUD creation and desktop rendering, not collection,
winning, respawn persistence, mobile layouts, or multiplayer behavior.

Run this only in a local, disposable Studio session or through the configured
isolated test-place service. Opening the contributor artifact in Studio is an
optional developer check; hosted-agent users do not need Studio installed. Do
not publish this artifact to a production experience.

1. Open `dist/rainforest-rule-game-current.rbxlx` (or rebuild it with the
   command above) and start a one-player test.
2. Confirm the character spawns on the connected path and the `Points` and
   `Wins` stats appear. Confirm the objective panel states the three-point win
   condition, shows zero initial points and wins, and is legible at desktop and
   mobile viewport sizes.
3. Touch each of the three canopy coins once. Confirm `Points` increments once
   per coin, then touch the summit lookout. Confirm `Wins` increments and
   `Points` resets to zero. Confirm the objective panel matches both values.
4. Touch the lava vent. Confirm the character is eliminated and respawns on the
   start pad; confirm the panel remains visible, then collect again and complete
   a second round to check repeatability.
5. Inspect Studio Output for script errors. Record the Studio/engine version,
   player count, checks performed, and any errors before calling the runtime
   behavior verified.

For a repeatable developer engine check, start a fresh Play Solo session on
the current HUD artifact, select the **Server** context, and execute
`tools/studio_rainforest_round.luau` in Studio's command bar. It refuses to run
outside Studio server play mode or with more than one player. It teleports the
character through actual trigger contacts, checks early-goal rejection,
repeat-contact scoring, two wins, round resets, and hazard respawn with the HUD
retained. Successful Output includes `RGA_ENGINE_TWO_ROUNDS_PASS` and
`RGA_ENGINE_HAZARD_RESPAWN_PASS`. An assertion or missing marker is a failed or
incomplete check. Stop Play Solo afterward. Do not insert this test driver into
a delivered place. Teleportation does not validate the walking route or player
controls. The driver has passed syntax validation but has not yet completed
an engine run; it is not acceptance evidence by itself.

Partial Studio check on 2026-11-06: the current artifact opened and Play Solo
started; the character appeared on the start platform. Studio displayed its
Compatibility-to-Voxel lighting migration notice. Automated keyboard input did
not move the character, so collectible scoring, the win condition, hazard
respawn, repeatability, and the Output panel remain unverified. The full
checklist has not been completed. It also does not cover multiplayer races,
persistence, low-end device performance, or live Open Cloud behavior.

Artifact check on 2026-11-06: the current `rule_game` build contains 19 recipe
objects, 19 place Parts, and one server Script whose name and source match the
repository-owned template exactly. The validated artifact is 31,777 bytes with
SHA-256 `2375fae0c2230c191e1bc56a7463c1ecc91d0757b55b1e0976839f131034acca`.
This confirms artifact structure and trusted-script selection. The Studio
opening and Play Solo check confirms the place loads and starts locally; it does
not verify the collect-and-win flow or behavior against a live Roblox place.

