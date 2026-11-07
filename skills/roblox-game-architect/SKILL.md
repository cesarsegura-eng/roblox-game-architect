---
name: roblox-game-architect
description: Plan and build Roblox games end to end with the Roblox Game Architect remote MCP services and dedicated environment, Blender, Studio-map, and character skills.
metadata:
  short-description: Build Roblox games with remote MCP tools
---

# Roblox Game Architect

Use this skill when the user wants an end-to-end Roblox game plan, map, 3D
scene, character, or reviewed place build through the Roblox Game Architect
services.

The product's execution model is the user's existing agent connected to
separately hosted MCP services. Blender, Roblox Studio, extensions, this source
repository, and a local MCP process are not prerequisites on the user's PC.
Keep server credentials on the trusted MCP hosts. If the remote services are
not connected, explain which tool is missing and continue with a design or
data-only plan that does not pretend to have built or tested a place.

## Workflow

1. Turn the request into a small game brief: player promise, core loop, target
   device and camera, map needs, requested gameplay, and acceptance checks.
2. Use the dedicated `game-design-planning` skill for planning. Read the plan's
   `playable_slice` and carry its supported `gameplay_mode`, included systems,
   deferred systems, and limitations through the build. In the operator panel,
   **Set up map build** copies the plan's world brief and selects that mode.
   Then use `world-environments` for biomes, architecture, interiors, exteriors,
   and atmosphere. Read only the skill references needed for the requested work.
3. Build a bounded Scene Recipe from the validated schema in the project's
   skillpack when available. Use `blender-scene-authoring` for 3D scenes and
   props, `character-modeling-animation` for rigs and movement, and
   `roblox-studio-map-blockouts` for the primitive Studio subset. Do not place
   code, file paths, or executable expressions in a scene recipe.
   For an Obby request, choose the fixed `obby` build mode only when the recipe
   contains at least two ordered route segments with the `path` role; it adds
   server-owned sequential checkpoints, respawn positions, stage stats, and
   session-only wins and supports optional `hazard` role obstacles. Persistent
   progression is unsupported. For a
   Treasure Hunt request, use `treasure_hunt` with route-adjacent `collectible`
   objects. For other touch-based collection or hazard interactions, use
   `rule_game` and pass `gameplay_rules` matching roles in the recipe. Supported
   actions are `award_points` (1-1000), `heal` (1-100), nonlethal `damage`
   on `hazard` (1-100), `eliminate` on
   `hazard`, and `award_win` on `landmark` when `minimum_points` is reached.
   A win resets session points for another round. Each repeatable collection
   rule fires once per player per part; lethal hazards fire on every touch.
   Multiple different rules may use the same role. The
   tool supplies a fixed server interpreter and never accepts caller source.
   Otherwise select script-free `blockout`.
4. Call `rga_review_game_plan` on the Roblox host with the structured plan.
   Use the returned roles when designing the scene. Call it again with both
   `plan` and `recipe`. Correct validation errors in the indicated input and
   use the returned `build_settings` with the reviewed recipe for the place
   build. The review checks data and map layout before engine testing.
   Discover the connected MCP tools and use only the fixed RGA operations:
   `rga_apply_scene_recipe` on the Blender service, and `rga_build_place` or
   `rga_validate_map` on the Roblox service when exposed. Follow each server's
   instructions and actual schemas. Do not call generic Blender/Python or
   arbitrary Luau execution tools.
   The Blender operation returns an artifact receipt; it does not place the GLB
   bytes in the agent's context. Use a configured, reviewed artifact handoff
   when available. Otherwise report the artifact ID and that delivery is not
   configured. A Roblox `.rbxlx` build from the same recipe is a separate place
   artifact and does not contain an uploaded Blender mesh unless that asset
   import workflow completed.
   If the Roblox service exposes `rga_prepare_blender_model_upload` and
   `rga_upload_prepared_blender_model`, use the first to have the Roblox MCP
   host fetch the UUID-addressed artifact from its fixed Blender host. Present
   the source recipe and returned digest/confirmation phrase, then wait for the
   user to approve persistent Roblox asset creation before calling the second.
   For a pending receipt, call `rga_check_model_upload` with the upload's
   original request ID to read the moderation decision. Import the resulting
   asset only after Roblox reports moderation approval.
   When delivering a place directly to a user and the Roblox host advertises
   `rga_build_place_download`, use it with the reviewed build arguments.
   Give the requesting user the returned download link, its expiry, and the
   SHA-256. The private link grants access to that single artifact. Keep the
   original request ID and digest for a later test-place publication review.
5. Keep model upload, place publishing, and any other persistent operation
   separate from ordinary generation. They require their explicit service
   configuration, a review of the exact artifact, and the tool's approval
   flow. For direct MCP place publication, use
   `rga_prepare_test_place_publication` with the exact build request ID and
   SHA-256, then present the returned digest, build summary, fixed test
   universe/place IDs, expiry, and confirmation phrase. Wait for the user's
   explicit approval before calling `rga_publish_prepared_test_place` with the
   exact returned approval ID, digest, and phrase. Never call the compatibility
   `rga_publish_reviewed_place` tool directly. A downloadable place artifact is
   not a published or playtested game.
6. Report artifacts, checks run, and remaining work precisely. Distinguish
   structural recipe validation, Roblox engine validation, Studio inspection,
   gameplay playtest, and production acceptance; one does not prove the next.

For service setup, read the repository's
`docs/integrations/agent-skills.md` and
`docs/integrations/remote-application-architecture.md` when those files are
available. For Codex-specific client configuration, also read
`docs/integrations/roblox-game-architect-codex.md`. For tool use, load the
dedicated skills by task: the
`game-design-planning`, `world-environments`, `blender-scene-authoring`,
`roblox-studio-map-blockouts`, and `character-modeling-animation`.
