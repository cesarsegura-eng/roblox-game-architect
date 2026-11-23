---
name: roblox-game-architect
description: Plan and build Roblox games end to end with the user's existing Roblox Studio tools, remote Blender authoring, and dedicated environment, map, and character skills.
metadata:
  short-description: Build Roblox games with remote MCP tools
---

# Roblox Game Architect

Use this skill when the user wants an end-to-end Roblox game plan, map, 3D
scene, character, or reviewed place build through the Roblox Game Architect
services.

The product equips the user's existing agent with skills, knowledge, and tools.
Blender, RGA extensions, this source repository, and a local RGA MCP process are
not prerequisites on the user's PC. Keep remote-service credentials on their
trusted hosts. If an optional remote service is not connected, explain which
capability is missing and continue with work supported by the tools that are
available; do not pretend to have built or tested a place.

In Claude Code, discover and use the MCP tools already available to the user.
Roblox Studio's native MCP is the user's existing live-Studio integration: never
create, install, replace, rename, proxy, or route it through an RGA server. The
Claude Code plugin adds only the separately hosted RGA Blender MCP for bounded
3D authoring; it must not add a Roblox connection. Use the native Studio MCP for
the requested direct Roblox work under its own tool descriptions, approval
rules, and test-place safeguards. The repository's separate RGA Roblox MCP is
an optional server-side artifact and validation service for environments that
already expose it; it is not part of the intended Claude setup and does not
replace or create a Claude-to-Studio bridge. Do not infer that a place was
opened, tested, or changed in Studio unless the native Studio tool call and its
result provide evidence.

## Workflow

1. Turn the request into a small game brief: player promise, core loop, target
   device and camera, map needs, requested gameplay, and acceptance checks.
2. Use the dedicated `game-design-planning` skill for planning. Read the plan's
   `playable_slice` and carry its supported `gameplay_mode`, included systems,
   deferred systems, limitations, world brief, and acceptance checks through
   each build and validation request. The local operator panel can copy these
   values as an optional compatibility path; it is not required for the agent
   workflow. Then use `world-environments` for biomes, architecture, interiors,
   exteriors, and atmosphere. Read only the skill references needed for the
   requested work.
3. Build a bounded Scene Recipe from the validated schema in the project's
   skillpack when available. Use `blender-scene-authoring` for 3D scenes and
   props, `character-modeling-animation` for rigs and movement,
   `roblox-studio-map-blockouts` for the primitive Studio subset, and
   `roblox-terrain-authoring` for bounded voxel terrain through the user's
   existing Studio MCP. Do not place
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
   on `hazard` (1-100), `eliminate` on `hazard`, `speed_boost` on a `collectible`
   or `prop` (`amount` 1-16 and `duration_seconds` 1-30), and `award_win` on
   `landmark` when `minimum_points` is reached. A win pauses nonlethal touch
   effects for one second to suppress duplicate touches while the round resets;
   lethal hazards stay active. A speed boost adds to the
   player's current WalkSpeed, caps it at 32, and restores the saved original
   WalkSpeed when the latest boost expires. A win resets session points and
   per-part collection for another round. Each collectible or prop action fires
   once per player per part per round; lethal hazards fire on every touch.
   Multiple different rules may use the same role. The optional RGA place
   builder supplies a fixed server interpreter and never accepts caller source.
   These named build modes apply only when using that builder; otherwise follow
   the native Studio MCP's actual capabilities and select a data-only blockout
   when the available tools do not support gameplay scripting.
4. Discover the MCP tools already available to the user. Use the existing
   native Studio MCP directly for work in the user's open place when its
   documented tools support the requested action. Follow its own approvals,
   target restrictions, and test-place safeguards. Do not ask the user to
   install this project's Studio plugin or configure a second Roblox MCP
   connection.

   When the native MCP exposes `skill`, retrieve the relevant Roblox guidance
   for debugging, device simulation, asset import, permissions, or documentation
   search. In particular, load Roblox's native `rbx-permissions` and
   `rbx-import-asset` skills before using `open_cloud_invoke` for an asset
   upload. Let those skills handle current permission scopes, approved upload
   folders, moderation, and import adjustments; retain RGA's recipe, artifact
   digest, size, and provenance checks around that workflow. Use `http_get` for
   current Creator Hub API details instead of guessing. Inspect the connected
   tool list and each tool's actual schema; capabilities can vary by Studio
   version and client. The official tool guide is
   https://create.roblox.com/docs/studio/mcp.

   Open Cloud asset upload permissions require the selected Studio place to
   belong to a published experience. A local unpublished `.rbxlx` can be opened
   and engine-tested but cannot grant those per-game Open Cloud permissions. If
   there is no dedicated published test experience, keep the GLB as a reviewed
   local artifact and leave upload, moderation, and import pending; never use a
   production experience as a substitute test target.

   Before editing, call `list_roblox_studios` and select the intended instance
   by its `studio_id`; verify the place identity and inspect its current state
   before changing anything. Pass that `studio_id` on each subsequent call.
   If the target is ambiguous, do not guess. When available, inspect the
   relevant hierarchy and scripts before writing, then use the correct
   `datamodel_type` for Edit, Server, or Client operations. Run requested
   playtests in the intended test copy, inspect console evidence, and report
   only what the tools observed. For sustained player-input checks, use the
   native `user_keyboard_input` tool's ordered key-down, wait, and key-up
   actions when its live schema supports them. A short key-press action alone
   is not evidence that a route was traversed.

   When no published test universe is available, a local engine smoke can use
   an unpublished `.rbxlx` artifact. Build it from the validated recipe with
   the repository's `tools/build_roblox_place.py`, then open that file in
   Studio through its documented workflow; if no connected tool can open local
   files, give the user the exact path to open. Confirm the local place by name
   through `list_roblox_studios` (it may have no place ID), target its
   `studio_id`, and run Play Solo or Server & Clients only when the native MCP
   exposes those controls. This verifies local engine behavior only; it does
   not satisfy the published Open Cloud test-universe gate or prove production
   readiness.

   If the connected Studio MCP exposes its `subagent` tool, use its `explore`
   type for bounded hierarchy, script, or game-state investigations and its
   `playtest` type for a specific reviewed gameplay scenario. Read the live
   tool schema and pass the chosen `studio_id` and test target where required;
   the available arguments vary by Studio release. Do not delegate edits,
   asset uploads, publishing, or other persistent writes to a subagent. A
   subagent's summary is not proof by itself: inspect its returned evidence,
   relevant Studio state, screenshots, and console output, and report any
   checks it could not perform. Run playtest work only in an approved test copy.

   Studio's native MCP acts on an open place and may expose direct Luau
   execution and broad edit tools. Treat it as a powerful authoring surface,
   not as an isolated execution sandbox. Keep user content and production
   targets protected; an MCP playtest or successful tool call alone does not
   prove production readiness.

   Use `rga_apply_scene_recipe` on the remote Blender service when exposed and
   follow its actual schema; do not call generic Blender/Python execution
   tools. Do not send arbitrary source to the RGA Roblox service. Native
   Studio script-edit and execution tools are a separate direct workflow; use
   them only for user-requested work in the verified target place and under the
   Studio connection's safeguards. Specialized RGA Roblox operations such as
   `rga_review_game_plan`, `rga_build_place`, and `rga_validate_map` are optional
   server-side alternatives for other agent environments. They may be used
   only if already exposed in the agent's configured toolset. Never ask a
   Claude Code user to add an RGA Roblox endpoint. When an optional RGA Roblox
   tool is already available, use its fixed schema and report its results
   separately from native Studio operations.

   The Blender receipt may include `artifact_download_url`, a signed, 15-minute
   link for that one GLB. Treat it as a temporary secret: download only that
   artifact directly into a folder the user already approved for Studio MCP
   uploads, and do not log or repost the URL. Compare the downloaded file's
   SHA-256 to the receipt's `artifact_sha256`; stop if it differs. If Claude's
   native Studio MCP exposes `open_cloud_invoke`, its `files` parameter
   supports uploads from an approved local folder. Review the file and its
   verified SHA-256 with the source recipe and wait for explicit approval
   before calling the persistent upload. Request
   the asset permissions Studio documents and follow its moderation status
   before inserting the asset. The current Open Cloud asset-upload limit is 20
   MB per asset; check the source guide for the latest rules and do not use that
   route for larger GLBs. See Roblox's [Open Cloud with Studio MCP
   guide](https://create.roblox.com/docs/studio/mcp-open-cloud) and [asset usage
   guide](https://create.roblox.com/docs/cloud/guides/usage-assets). Never
   bypass the approved-folder check or claim remote artifact data is local. If
   no signed link or other supported handoff is available, report the artifact
   ID and that delivery is not configured. A
   separate RGA `.rbxlx` artifact does not contain an uploaded Blender mesh
   unless its asset-import workflow completed. Roblox asset
   handoff tools may be used only if they are already exposed; present the
   source recipe and digest, wait for explicit approval before persistent
   creation, and check moderation before import.
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
   separate from ordinary generation. Review the exact artifact and use the
   approval flow of the tool that will perform the operation. Native Studio
   MCP actions follow that connection's own safeguards. If an already
   configured RGA Roblox MCP exposes direct place publication, use
   `rga_prepare_test_place_publication` with the exact build request ID and
   SHA-256, present the returned digest, build summary, fixed test target,
   expiry, and confirmation phrase, and wait for explicit user approval before
   confirming. Never publish to production. A downloadable place artifact is
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
`roblox-gameplay-engineering`, `roblox-studio-map-blockouts`,
`roblox-terrain-authoring`, and `character-modeling-animation`. Load `roblox-ui-ux` for HUDs, menus,
onboarding, inventory, accessibility, and cross-device player flows.
