---
name: roblox-studio-map-blockouts
description: Design readable, playable Roblox Studio map blockouts using the currently enabled declarative primitive subset.
---
# Roblox Studio map blockouts

This skill describes the restricted blockout shape supported by RGA's remote
Roblox builder and the optional local Studio compatibility queue. The end user
can build and validate through the remote MCP service without installing Studio;
use Studio only when an authorized operator chooses that inspection path.

Plan from player scale outward: establish a landmark, a legible route, safe navigation widths, and a few changes in elevation expressed through simple forms. Translate the requested biome into a compact palette, silhouettes, and spatial rhythm. For houses and interiors, distinguish floor, walls, openings, and a focal furnishing so players can read entrances and circulation.

Name Parts after requested features so the generated blockout can be checked before it reaches the remote build or optional Studio approval queue. House requests default to named exterior, entry, and roof Parts; an explicit `interior only` brief keeps that scope narrow. Route requests need a named, flat, elongated Part whose longer horizontal size is at least twice its width. This is a blockout coverage check, not proof of a connected route or collision-free traversal.

The current Studio tool can create Parts and WedgeParts, Models and Folders in Workspace, and the approved property subset includes bounded Part rotation. The generated map blockout currently sticks to axis-aligned rectangles; recipe-to-Studio proxies preserve rotation. It cannot add meshes, terrain, scripts, audio, particles, or production lighting. Use low-poly rectangular blockout shapes and supported materials only. Keep the map compact, anchored, collision-aware, and easy to inspect. Geometry is a first-pass layout, not finished architecture or natural terrain.

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
