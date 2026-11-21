---
name: roblox-studio-map-blockouts
description: Design readable, playable Roblox Studio map blockouts using the currently enabled declarative primitive subset.
---
# Roblox Studio map blockouts

This skill describes RGA's bounded primitive blockout shape. An agent can use
the user's existing Roblox Studio native MCP for direct map creation or edits
when its documented tools support the requested operation. Do not install this
project's optional local Studio compatibility plugin to enable that connection.
RGA's remote Roblox MCP builds a separate validated artifact and runs its fixed
remote checks; it does not control or test the open Studio session.

If the agent already has Roblox Studio's native MCP connection, leave its
configuration and ownership untouched. Use it for the user's requested direct
Studio work, within the connection's own tool limits, approvals, and test-copy
requirements. The RGA Roblox MCP is a separate optional service for validated
recipe artifacts and its configured fixed validation harness. Never claim that
the remote RGA build itself edited or tested the open Studio session.

Before direct edits, use the native MCP's `list_roblox_studios` tool to choose
the intended open instance by `studio_id`; verify its place identity and
current state, and pass that ID to later calls. Do not rely on whichever Studio
window happens to be active. Follow the official tool contract for `Edit`,
`Server`, and `Client` datamodel operations, and use a disposable test copy for
playtesting when one is available. Native MCP calls operate on the open place
and are not an isolation boundary.

For route playability, test the saved layout in a disposable local or test place
through Roblox Studio's existing native MCP. If exposed by that Studio version,
use `character_navigation` to move the actual Play Solo character through each
consecutive segment, and inspect the character, checkpoint state, console, and
viewport after each traversal. Use the native `playtest` subagent or
`user_keyboard_input` for controls that need jumps or deliberate key presses.
Keep these checks separate from `PathfindingService` waypoint queries and
teleport-based gameplay drivers: those verify geometric connectivity or game
logic, not that a player can traverse the route. Read the live tool schemas and
report which kind of movement evidence was actually collected.

Plan from player scale outward: establish a landmark, a legible route, safe navigation widths, and a few changes in elevation expressed through simple forms. Translate the requested biome into a compact palette, silhouettes, and spatial rhythm. For houses and interiors, distinguish floor, walls, openings, and a focal furnishing so players can read entrances and circulation.

Name Parts after requested features so the generated blockout can be checked before it reaches the remote build or optional Studio approval queue. House requests default to named exterior, entry, and roof Parts; an explicit `interior only` brief keeps that scope narrow. Route requests need a named, flat, elongated Part whose longer horizontal size is at least twice its width. This is a blockout coverage check, not proof of a connected route or collision-free traversal.

RGA's optional compatibility queue can create Parts and WedgeParts, Models,
and Folders in Workspace; its approved property subset includes bounded Part
rotation. RGA-generated map blockouts currently stick to axis-aligned
rectangles, while recipe-to-Studio proxies preserve rotation. This describes
the RGA queue only; use the native Studio MCP's documented capabilities for
direct Studio work. For RGA recipe blockouts, use low-poly rectangular shapes
and supported materials, keep the map compact, anchored, collision-aware, and
easy to inspect. Geometry is a first-pass layout, not finished architecture or
natural terrain. For native voxel terrain, read and use the dedicated
`roblox-terrain-authoring` skill through the user's existing Studio MCP; the
RGA Scene Recipe and optional queue do not create terrain voxels.

## Performance-aware handoff

- Design for a stated device range. Do not claim a frame-rate target from object
  counts alone. Profiling with MicroProfiler and representative devices is an
  operator acceptance task; do not require Studio on the end user's computer.
- Build large environments from reusable assets. When the approved remote asset
  pipeline is enabled, create unique assets once and reuse their asset IDs in
  the build. Otherwise list asset ingestion and reuse as an operator handoff.
- Avoid dense clusters of unique meshes, unnecessary transparent layers, and
  many small shadow-casting objects or lights. Preserve silhouette and route
  visibility first; tune shadow and render-fidelity settings during profiling.
- For large worlds, evaluate instance streaming and verify gameplay still works
  when distant Workspace content has not streamed to the client.
- Treat these as design checks, not a substitute for profiling the actual
  published target on representative low-end devices.

Use Roblox's [performance optimization guide](https://create.roblox.com/docs/performance-optimization)
and [environment optimization curriculum](https://create.roblox.com/docs/tutorials/curriculums/environmental-art/optimize-your-experience)
for current profiling and asset guidance.
