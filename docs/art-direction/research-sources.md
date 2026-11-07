# Environment, Blender, and character research sources

This is a curated research index for the project's worldbuilding skills. It is
not a scrape of the internet or a substitute for task-specific references.
The skills synthesize the linked material into project guidance. Verify platform
specifications again when exporting because product rules can change.

## Blender and Roblox asset pipeline

- [Blender 5.2 LTS release notes](https://www.blender.org/releases/5-2/) — pinned release family for the remote Blender worker; verify the deployed patch version and checksum.
- [Model Context Protocol: Streamable HTTP transport](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/streamable-http.mdx) — remote MCP transport used by the separate Blender host.
- [Model Context Protocol: Versioning and compatibility](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/versioning.mdx) — current stateless protocol revision and compatibility with earlier handshake-based servers.
- [Blender 5.2: Creating Extensions](https://docs.blender.org/manual/en/5.2/advanced/extensions/getting_started.html) — extension packaging, manifest, install-from-disk workflow.
- [Blender Python API, current](https://docs.blender.org/api/current/) — the `bpy` API for scenes, meshes, operators, materials, and UI.
- [Blender glTF export operators](https://docs.blender.org/api/dev/bpy.ops.export_scene.html) — current export options; pin and validate the actual Blender version used by the project.
- [Blender 4.2 glTF animation export](https://docs.blender.org/manual/en/4.2/addons/import_export/scene_gltf2.html) — active actions, NLA tracks, skinning and pose-bone animation export.
- [Blender 5.2 Manual: Mesh Structure and Topology](https://docs.blender.org/manual/en/5.2/modeling/meshes/structure.html) — edge and face loops, poles, and why deformation loops follow joint contours.
- [Blender 5.2 Manual: Animation and Rigging](https://docs.blender.org/manual/en/5.2/animation/) — current manual index for keyframes, armatures, bones, skinning, actions, and F-curves.
- [Roblox: Blender](https://create.roblox.com/docs/art/blender) — Blender/Studio axis, scale, and export workflow.
- [Roblox: Importer](https://create.roblox.com/docs/studio/importer) — supported FBX, glTF, and OBJ import, hierarchy and scale settings.
- [Roblox: Animation Editor](https://create.roblox.com/docs/animation/editor) — creating and editing animation clips on Studio rigs.
- [Roblox: Animation packs](https://create.roblox.com/docs/avatar/animation-packs) — standard R15 workflow and import of FBX animation clips.
- [Roblox: Mesh specifications](https://create.roblox.com/docs/art/modeling/specifications) — current mesh topology and triangle constraints.
- [Roblox: 3D art overview](https://create.roblox.com/docs/art) — official map of environmental art, modeling, texturing, lighting, effects, audio, import, and animation workflows.
- [Roblox: Animation Editor](https://create.roblox.com/docs/animation/editor) — keyframe poses, easing, timing, and animation preview on rigs.
- [Roblox: Rigging and skinning](https://create.roblox.com/docs/art/modeling/rigging) — how imported vertex influences and rig structures are handled by Studio.
- [Roblox: Environmental art curriculum](https://create.roblox.com/docs/tutorials/curriculums/environmental-art) — modular environment assembly and environment-art workflow.
- [Roblox: Performance optimization](https://create.roblox.com/docs/performance-optimization) — measure frame time, memory and join time; optimize iteratively rather than inferring runtime performance from source budgets.
- [Roblox: Improve performance](https://create.roblox.com/docs/performance-optimization/improve) — mesh reuse, draw calls, render fidelity, shadows, transparency, instance streaming, and profiling guidance for assembled places.
- [Roblox: Optimize your game environment](https://create.roblox.com/docs/tutorials/curriculums/environmental-art/optimize-your-experience) — environmental asset review for physics/rendering cost and excess geometry or transparency.
- [Roblox: Characters](https://create.roblox.com/docs/characters) — character creation pipeline, Avatar Setup, animation tooling, and differences between raw meshes and configured Roblox characters.
- [Roblox: Construct your world](https://create.roblox.com/docs/tutorials/curriculums/environmental-art/construct-your-world) — graybox-to-art pass, architecture and exterior asset placement, terrain routes, and indoor/outdoor lighting.
- [Roblox: 3D art and Studio](https://create.roblox.com/docs/art/overview-studio) — official overview of modeling, materials, environment tools, and the terrain-versus-interior workflow.
- [Roblox: Environmental terrain](https://create.roblox.com/docs/building-and-visuals/studio-modeling/terrain) — terrain editor, biome generation, materials, heightmaps, and sculpting operations.
- [Roblox: Lighting and effects](https://create.roblox.com/docs/environment) — global and local light, atmospheric effects, and mood controls.
- [Roblox: Audio objects](https://create.roblox.com/docs/audio/objects) — spatial emitters and listeners, routing, and positional audio behavior for environmental sound.
- [Roblox: Audio effects](https://create.roblox.com/docs/audio/effects) — effect routing and acoustic effects such as echo for spaces that need distinct interior or cave sound.
- [Roblox: Sound](https://create.roblox.com/docs/sound) — positional versus background playback, sound groups, and dynamic effects for ambient layers.
- [Roblox: Texture specifications](https://create.roblox.com/docs/art/modeling/texture-specifications) — image formats, UV, material, and PBR constraints.
- [Roblox: Custom 3D assets](https://create.roblox.com/docs/art/modeling) — mesh use cases and model structure.
- [Roblox reference Blender integration](https://devforum.roblox.com/t/reference-roblox-integration-for-blender/2546753) — open-source reference integration for Open Cloud; Roblox explicitly calls it sample code, not an official product.
- [Roblox Studio MCP server](https://create.roblox.com/docs/studio/mcp) — official local stdio integration for an open Studio session; its broad tools can edit scripts, execute Luau, and start playtests, so it is not treated as an isolated remote runner.
- [Roblox Open Cloud Luau Execution](https://create.roblox.com/docs/cloud/reference/features/luau-execution) — hosted version-scoped task API with engine access; the fixed harness and disposable-place controls in ADR-0015 are required before using it for map validation.

## Biomes, ecology, and place

- [USGS: Ecological Regions](https://www.usgs.gov/centers/eros/science/ecological-regions) — ecoregions arise from interacting geology, landforms, soils, vegetation, climate, hydrology, and human modification.
- [NASA: Mission Biomes](https://science.nasa.gov/kids/earth/mission-biomes/) — accessible overview connecting climate, temperature, precipitation, plants, and animals across major biome families.
- [NASA: Vegetation](https://science.nasa.gov/earth/earth-observatory/global-maps/vegetation/) — satellite measures and seasonal patterns in vegetation greenness.
- [NASA: Human Ecosystems](https://science.nasa.gov/earth/earth-observatory/human-ecosystems-40554/) — human activity is part of landscape ecology; avoid treating settlements as a separate decorative layer.
- [USGS ecoregion atlas examples](https://pubs.usgs.gov/pp/1567/report.pdf) — regional climate, physiography, geology, permafrost, soils, and vegetation can be cross-referenced for plausible local combinations.
- [U.S. Department of Energy: Climate Zones](https://www.energy.gov/cmei/buildings/climate-zones) — climate zones inform building practices; use regional guides rather than universal architectural formulas.
- [Climate-responsive strategies in Erbil vernacular architecture](https://www.tandfonline.com/doi/full/10.1080/00207233.2019.1619324) — a place-specific example of linking architecture to local climate.
- [Traditional Arab houses in the Eastern Mediterranean](https://onlinelibrary.wiley.com/doi/10.1111/1745-5871.12161) — a multi-site study of how one architectural tradition responds to varying local climates.
- [Systematic review of vernacular dwelling climate responsiveness](https://www.sciencedirect.com/science/article/abs/pii/S2352710222005277) — a review of 55 studies, useful for finding primary regional research.
- [Fischer et al., AutoBiomes: procedural generation of multi-biome landscapes](https://cgvr.cs.uni-bremen.de/papers/cgi20/AutoBiomes.pdf) — research pipeline combining synthetic landforms, simplified climate simulation, example-based elevation data, and rule-based asset distributions; treat its Unreal implementation as a transferable design pattern, not a Roblox runtime recipe.
- [Zhai et al., Developing an Ecology-Integrated Gaming Tool for Collaborative Landscape Design](https://www.dora.lib4ri.ch/wsl/islandora/object/wsl%3A40729/datastream/PDF/Zhai-2025-Developing_an_ecology-integrated_gaming_tool-%28published_version%29.pdf) — 2025 study using local vegetation communities and game-engine PCG; its placement rules consider slope, sunlight, water distance, infrastructure, and habitat data, and are intended for landscape co-design and restoration.

## Level design, visual storytelling, rigging, and motion

- [Christopher Worch, GDC: Player Stories, Designer Stories](https://www.worch.com/files/gdc/Player_Stories_Designer_Stories.pdf) — level space, player movement, environmental constraints, agency, and how static environment shapes play.
- [Wenya He, GDC 2026: Mastering Massive Worldbuilding](https://media.gdcvault.com/gdc2026/Slides/Wenya_He_Mastering_Massive_Worldbuilding.pdf) — a MechaBREAK case study covering biome rule tuning by landform, spline-designed paths and rivers, cultural-area layout, modular/tiled scene construction, and quality-tiered optimization. Treat these as pipeline examples for a large production, not as a Roblox recipe or universal budget.
- [Christopher W. Totten, GDC 2018: An Architectural Approach to Level Design](https://media.gdcvault.com/gdc2018/presentations/CWT_ArchitectureLevelDesign_GDC18.pdf) — applies architectural spatial arrangements, plans and sections, camera-aware space, modular whiteboxing, and prospect/refuge ideas to game levels and interiors.
- [GDC: What Modern Interior Design Teaches Us About Environment Art](https://www.gdcvault.com/play/1020135/What-Modern-Interior-Design-Teaches) — connects interior function and aesthetics with how players read game spaces.
- [Epic: Level Design Best Practices in Fortnite Creative](https://dev.epicgames.com/documentation/fortnite/level-design-best-practices-in-fortnite-creative) — entry and exit planning, sightline control, cover distribution, and using layered interiors as environmental narrative. Transfer spatial principles; do not copy Fortnite layouts or combat tuning.
- [Riot Games: Environment Art](https://www.riotgames.com/en/artedu/environment-art) — production overview emphasizing layout-to-asset scope, prioritization, and trade-offs around the desired player experience.
- [Epic: Building Virtual Worlds](https://dev.epicgames.com/documentation/unreal-engine/building-virtual-worlds-in-unreal-engine) — environment construction workflow spanning levels, landscapes, lighting, props, foliage, and large worlds.
- [Epic: Prototype Pass](https://dev.epicgames.com/documentation/unreal-engine/1---prototype-pass?application_version=4.27) — rough geometry and basic lighting used early to inspect route scale, relative sizing, and playability.
- [Ubisoft: Senior Level Artist](https://www.ubisoft.com/en-us/company/careers/search/744000145286684-senior-level-artist) — production description of environmental storytelling, composition, lighting, gameplay readability, and technical constraints.
- [Harvey Smith and Matthias Worch, GDC: What Happened Here? Environmental Storytelling](https://media.gdcvault.com/gdc10/slides/Smith_Harvey_WhatHappenedHereWeb_Notes.pdf) — clues, props, spatial context, and player-driven interpretation.
- [Blender Manual: Rigging introduction](https://docs.blender.org/manual/en/5.1/animation/introduction.html) — armatures, constraints, object modifiers, shape keys, and drivers as rigging tools.
- [Blender Manual: Armature Modifier](https://docs.blender.org/manual/en/latest/modeling/modifiers/deform/armature.html) — vertex-group and envelope deformation.
- [Roblox: Character body specifications](https://create.roblox.com/docs/avatar/character-bodies/specifications) — current avatar part, rig, pose, bounds, orientation, and triangle requirements.
- [Roblox: Avatar and movement system](https://create.roblox.com/docs/avatar) — avatar components, movement, facial animation, and adaptive animation.
- [Roblox: Animation](https://create.roblox.com/docs/animation) — keyframed joint poses and supported animation tooling.

## Live scene generation provider

- [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages) — request shape, output limit, token usage, and token-count endpoint used by the optional operator adapter.
- [Anthropic API pricing](https://platform.claude.com/docs/en/about-claude/pricing) — current standard token rates; the adapter enables only a model with an explicitly recorded rate and refuses unknown model IDs.

## How to use this research

Use NASA and USGS for factual ecological relationships, not for aesthetic
prescriptions. Use GDC and art references to reason about player experience,
composition, and storytelling. Use Blender and Roblox docs for implementation
details. For culturally specific architecture or anatomy, gather local and
domain-specific sources and keep those references attached to the design brief.
