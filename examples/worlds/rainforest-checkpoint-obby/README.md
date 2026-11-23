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

For the Obby mode, build the place as shown below, then run
`python tools/check_rainforest_obby.py dist/rainforest-checkpoint-obby.rbxlx
--lute .tools/lute-1.0.0/lute.exe`. This verifies the serialized checkpoint
order and exact fixed server script, then simulates out-of-order touches,
checkpoint progression, finish/reset, hazards and independent player progress.
The Lute simulation checks server-template logic; it does not simulate Roblox
physics, walking, network timing or actual character respawns.

For Treasure Hunt mode, run
`python tools/check_rainforest_treasure_hunt.py
dist/rainforest-treasure-hunt.rbxlx --lute .tools/lute-1.0.0/lute.exe` after
building the same recipe with `--gameplay-mode treasure_hunt`. The verifier
checks the serialized touch triggers, start spawn and exact fixed server
script, then simulates independent player progress, duplicate contacts, reset
debounce and two consecutive wins. It does not simulate Roblox engine
contacts, physics, networking or production-server behavior.

## Build a single place on the authoring host

Build an `.rbxlx` place artifact with pinned Rojo 7.7.1 available on the
contributor's path:

```sh
python tools/build_roblox_place.py \
  examples/worlds/rainforest-checkpoint-obby/scene-recipe.json \
  dist/rainforest-checkpoint-obby.rbxlx \
  --gameplay-mode obby
```

For this mode, the recipe's `path` objects define the checkpoint sequence. The
builder rejects consecutive pieces that are spatially disconnected, even if
the route pieces connect in some other ordering. This example lists the trail,
ridge connector, canopy bridge, summit connector, and summit walkway from start
to finish.

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

`rule_game` supports touch-triggered `award_points`, `heal`, timed `speed_boost`,
`eliminate`, and threshold-based `award_win` effects through one repository-owned server script.
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
controls.

Studio engine check on 2026-11-07: Roblox Studio `0.746.0.7461269`, Play Solo,
one player, on `dist/rainforest-rule-game-hud.rbxlx`. The server Output showed
`RGA_ENGINE_ROUND_PASS` for rounds 1 and 2, `RGA_ENGINE_TWO_ROUNDS_PASS`, and
`RGA_ENGINE_HAZARD_RESPAWN_PASS`. This verifies the fixed rule script's actual
engine contacts, score threshold, early-goal rejection, duplicate-contact
idempotency, score reset, win count, hazard elimination, respawn, and retained
HUD on this Studio build. The Studio driver teleports the character to trigger
parts; it does not verify walking controls, route navigability, multiplayer
races, persistence, low-end device performance, or live Open Cloud behavior.

Artifact check on 2026-11-07: `dist/rainforest-rule-game-hud.rbxlx` contains 19
recipe objects, 19 place Parts, and one server Script whose name and source
match the repository-owned template exactly. The current artifact is 33,721
bytes with SHA-256
`ecd46d16f0614c9ca96d05b19264f200e5e24271113b0ce0231fa50e12443cec`; the
`dist/rainforest-rule-game-e2e.rbxlx` build has the same digest. The current
artifact passed the fixed-template and two-round Luau simulation check.

Obby build check on 2026-11-07: `dist/rainforest-checkpoint-obby.rbxlx` is
32,747 bytes with SHA-256
`07278b2bc43de5324add2dda0ec5d26e00c54045cd8a33e009af96b6346cbd76`. Its five
generated checkpoints serialize in recipe order at Roblox Z positions
`-1, 14, 29, 44, 59`, confirming the fixed server template starts at the trail
and advances through the summit in sequence. This is structural build evidence,
not a walking, multiplayer, or production playtest.

Obby template simulation on 2026-11-07: the same artifact passed
`tools/check_rainforest_obby.py` with pinned Lute 1.0.0. It confirmed rejection
of early and skipped checkpoints, duplicate touch handling, finish/reset,
hazard elimination, and independent two-player route progress. This is a
deterministic simulation of the reviewed server template, not Roblox engine
evidence.

Obby Studio engine check on 2026-11-07: a fresh one-player Play Solo session
ran `tools/studio_rainforest_obby.luau` from the **Server** command bar. Output
showed `RGA_OBBY_NAVIGATION_PASS 4`, `RGA_OBBY_SEQUENCE_FINISH_PASS 1 1`,
and `RGA_OBBY_HAZARD_RESPAWN_PASS`. Roblox `PathfindingService` returned a
successful path with waypoints for each of the four consecutive checkpoint
legs using a 2-stud radius, 5-stud height, jump-capable agent. The test also
exercised actual engine touch events for early and skipped checkpoint
rejection, duplicate touches, sequential progress, one finish win, start
respawn selection, hazard elimination, and character respawn. The driver
teleports the character, so the pathfinding result does not prove that a human
can walk the route with normal controls; multiplayer, persistence, mobile
devices, and live servers also remain untested. Play Solo was stopped; the
artifact was not saved or published.

The rule-game Studio check ran against the earlier rule-game artifact before
the recipe path objects were reordered for Obby checkpoints. Its gameplay
template and collectible, hazard, and landmark positions are unchanged. The
current Obby artifact now also has the separate engine evidence above.

Fresh build check on 2026-11-07: `dist/rga-verified-obby.rbxlx` was generated
from the current recipe and passed the pinned Lute 1.0.0 artifact/template
simulation (`RGA_OBBY_ORDER_FINISH_PASS`, `RGA_OBBY_HAZARD_ISOLATION_PASS`,
`RGA_OBBY_MULTIPLAYER_PROGRESS_PASS`). It is 32,747 bytes with SHA-256
`07278b2bc43de5324add2dda0ec5d26e00c54045cd8a33e009af96b6346cbd76`.
`dist/rga-verified-treasure-hunt.rbxlx` was also freshly generated and passed
the artifact/template simulation for independent two-player progress, two
rounds, duplicate touches, and reset debounce. It is 28,266 bytes with SHA-256
`05f3bdace227e12324aa07c4d6beb8362a2d5e9982f1f4230bef72aeb26ff93f`.
These are newly generated local artifacts and deterministic template
simulations; neither is Roblox engine evidence. Roblox Studio was not available
in this session, so no new Studio run or place upload is claimed.

