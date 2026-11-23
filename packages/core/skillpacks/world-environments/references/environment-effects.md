# Roblox environmental effects and ambience

Use the user's existing native Studio MCP to create and inspect effects in the
open Roblox place. This guide adds no MCP connection and does not rely on the
optional local RGA Studio plugin. Run changes only in the reviewed target; use
a new, unpublished place or disposable copy for experiments.

## Inspect before authoring

1. Call `list_roblox_studios` and identify the intended place by `studio_id`.
   Confirm the edit/play state before changing the DataModel.
2. Use `search_game_tree` and `inspect_instance` to inspect `Lighting`,
   `Workspace.Terrain`, `SoundService`, existing effects, sound groups, and
   ambient audio. Preserve existing authored settings unless the task calls for
   replacing them.
3. Use native `http_get` for current Creator Hub documentation when a property,
   feature, or permission is uncertain. Ask the native `skill` tool for
   supported Studio lighting, audio, or device guidance when available.
4. Write down the intended mood and playable needs: time and weather, focal
   route and landmarks, interior/exterior transitions, gameplay sounds that
   must remain prominent, target devices, and accessibility settings.
5. Present global Lighting, Atmosphere, Clouds, and GlobalWind changes
   separately from local sound, particles, and light sources. These are
   different scopes and can affect a whole place.

## Visual atmosphere

- Establish global readability first with `Lighting.ClockTime`, brightness,
  ambient and outdoor colors, shadow direction, and the experience's selected
  lighting technology. Compare spawn, the main route, interiors, and distant
  landmarks before adding post-processing.
- Use one carefully tuned `Atmosphere` under `Lighting` to shape haze, distance,
  glare, and color. Keep important silhouettes, path edges, signs, and far
  objectives visible in the worst intended visibility condition.
- `Clouds` render when parented under `Workspace.Terrain`. Use `Cover`,
  `Density`, and `Color` as a broad sky treatment; use `Workspace.GlobalWind`
  deliberately because it affects dynamic clouds, terrain grass, and particles.
- Keep local `PointLight`, `SpotLight`, or `SurfaceLight` sources attached to
  the lamp, fire, or focal object that motivates them. Prefer a small number of
  purposeful lights over large overlapping pools of light.
- Use post-processing such as `ColorCorrectionEffect`, `BloomEffect`, or
  `DepthOfFieldEffect` only to support a measured focal point. Check contrast,
  color-vision differences, low graphics quality, and motion sensitivity.
- For rain, snow, leaves, spores, or dust, parent a `ParticleEmitter` to a
  purposeful `Attachment` and bound its rate, lifetime, speed, spread, and
  emitting area. Keep gameplay-critical objects visible. Avoid copying a dense
  emitter over every foliage instance; Roblox documents that excessive
  particles can increase draw calls and that changing emitters can cost
  performance.
- Use a consistent global profile for each intended state. If the game needs
  dynamic time or weather transitions, define the states and transition rules
  first; they require a reviewed gameplay script and runtime tests, not only
  visual effect instances.

## Soundscape and interior acoustics

- Layer sound by role: global music or world bed, regional exterior ambience,
  local activity, and gameplay-critical cues. Never let ambience mask UI or
  objective feedback.
- Put non-positional audio under `SoundService` or `Workspace`; put a positional
  `Sound` under its intended `BasePart` or `Attachment`. The parent determines
  how it emits and how it falls off with listener distance.
- Use `SoundGroup` to mix related audio. Use a small number of suitable effects
  such as reverb for a cavern or hall, equalization for muffling, or compression
  for level control. Keep effects connected to an audio graph that the current
  Roblox audio system supports.
- Do not invent audio asset IDs or assume an asset is usable. Reuse only sounds
  the experience owner has permission to use or assets they explicitly select;
  verify permissions and playback in the target experience.
- Design interior/exterior sound as a transition: change distance, room tone,
  or filtered ambience when the player crosses a real doorway or sound zone.
  Scripted zone switching needs server/client ownership, overlap handling,
  respawn behavior, and multi-client validation.
- Keep volume and effects accessible. Provide an experience-level way to reduce
  or mute ambience and music without removing required gameplay cues.

## Applying and reviewing changes

1. Use the native MCP's actual tool schemas. Read existing object values before
   editing; do not assume `execute_luau` is an isolation boundary.
2. Review the exact instances, global properties, audio IDs, and bounds that
   will change. If the request is limited to a lighting pass, do not create or
   delete audio, particle, script, or asset objects.
3. After applying, inspect the changed instances and capture the viewport at
   spawn, on the critical route, and at an interior threshold. Compare a
   representative low-quality device view and the requested time/weather
   states where Studio tools allow it.
4. Play the soundscape from each zone and transition. Verify attenuation,
   overlap, output volume, and gameplay-cue priority. Report the exact checks
   that actually ran.
5. Use Scene Analysis and MicroProfiler on representative devices before
   performance claims. Place count, emitter rate, or an attractive screenshot
   alone does not prove performance.

If the connected Studio MCP does not expose the needed operation, use a clear
manual handoff or the separately hosted Blender MCP for reusable 3D art. Do not
configure a second Roblox connection. Static effect instances do not create
dynamic weather, spatial audio logic, or a production-ready game loop by
themselves.

## Official references

- [Roblox Lighting and effects](https://create.roblox.com/docs/environment)
- [Roblox Atmosphere](https://create.roblox.com/docs/environment/atmosphere)
- [Roblox dynamic clouds](https://create.roblox.com/docs/environment/clouds)
- [Roblox global wind](https://create.roblox.com/docs/environment/global-wind)
- [Roblox sound objects](https://create.roblox.com/docs/sound/objects)
- [Roblox audio effects](https://create.roblox.com/docs/audio/effects)
- [Roblox ParticleEmitter API](https://create.roblox.com/docs/reference/engine/classes/ParticleEmitter)
- [Roblox performance optimization](https://create.roblox.com/docs/performance-optimization/improve)
