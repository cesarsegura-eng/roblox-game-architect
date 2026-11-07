# Playable map, architecture, and ambience patterns

These are blockout patterns for choosing and testing space. Combine them with
the project's biome and regional research; they are not universal templates.

## Choose a route structure from the game loop

| Pattern | Useful when | Check during blockout |
|---|---|---|
| Hub with spokes | Players choose missions, shops, or short destinations | Each spoke has a distinct landmark and the hub remains easy to return to |
| Loop | Exploration, collection, or repeated traversal | The loop has readable shortcuts and no accidental dead end |
| Branch and rejoin | Narrative choice or optional rewards | Branches feel meaningfully different and reconnect at a recognizable point |
| Three lanes | Symmetric team competition or parallel route choices | Cover, crossing distance, sightlines, and spawn safety are fair |
| Linear sequence | Guided tutorial or tightly paced story | Every bend hides and then reveals the next useful goal; backtracking is intentional |
| Vertical stack | Climbing, flying, or a compact landmark space | Elevation changes have safe readable transitions and clear navigation from above |

Block out circulation before decorating. Check routes at the actual camera and
avatar scale, with collision and movement abilities enabled. Test the first view
from spawn, the view after each major turn, and whether the player can identify
the next useful landmark without a marker.

## Exterior massing and transition

- Start with terrain, playable boundary, route width, elevation, and the largest
  landmark silhouettes. Leave intentional negative space around the objective.
- Make buildings respond to the chosen climate and site. Check foundations on
  slopes, roof drainage, openings, shade, wind exposure, access to water, and
  locally plausible materials together rather than as isolated details.
- Treat an entrance as a sequence: approach cue, threshold, compression or
  reveal, then a first interior landmark. Use material, light, sound, and partial
  occlusion to show that the player has moved into a different kind of space.
- Give paths and props a use. Wear, repairs, runoff, wind exposure, and moved
  objects should agree with the site's history and ordinary activity.

## House and interior planning

Before modeling a house, write a small room program: who uses it, which daily
activity happens there, what objects support that activity, and what route joins
it to the entry. Then block out:

1. **Threshold and arrival:** porch, vestibule, courtyard, or another locally
   appropriate transition; communicate public versus private access.
2. **Circulation spine:** a clear path through the rooms with turns and door
   openings scaled for the target avatar and camera. Avoid camera traps and
   furniture collisions.
3. **Room hierarchy:** give the main social or work space the strongest spatial
   identity; place quieter and service rooms according to the household's use.
4. **Light and ventilation logic:** choose window, courtyard, skylight, shade,
   and fire or heat sources in response to region, season, time of day, and
   cultural reference. Do not apply a climate feature as a decorative symbol.
5. **Play affordance:** reserve clear interaction areas, readable props, and
   alternate routes only when the game loop needs them.

Sketch a top-down plan and a simple section before set dressing. Check wall
thickness, ceiling height, stair and doorway clearance, camera clipping, and
whether the player can read the next room from the threshold. Use a framed view,
light change, or partial occlusion to reveal a destination; keep a safe refuge
and the next route legible when tension or risk is part of the game.

Review the floor plan from above and from the player camera. A room is not useful
just because its outline fits: it needs a clear purpose, traversable dimensions,
and a composition that reads while moving.

## Lighting, color, weather, and sound

- Establish a primary light direction and a value hierarchy: route/objective,
  landmark, then background. Reserve the strongest contrast for important play
  information and maintain readable silhouettes in shadow.
- Give each major area a small palette tied to materials and site conditions.
  Use area-to-area shifts to help navigation, not to make every prop compete.
- Use fog, precipitation, wind, and particles only when they reinforce distance,
  exposure, shelter, or danger. Test visibility in the worst intended weather.
- Design ambient audio as zones and transitions: exterior wash, sheltered entry,
  room tone, activity points, and distance falloff. Keep gameplay-critical cues
  distinct from the ambience.
- Check lighting and sound across the intended time/weather states and device
  quality levels. A beautiful still frame is not enough if the route or required
  sound becomes unreadable during play.

## Tool boundary and handoff

The current scene recipe supports simple lights and materials, but not audio
emitters, particles, terrain sculpting, volumetric weather, complex material
nodes, or scripted ambience. A generated recipe should make its geometry and
basic light pass explicit, then list unsupported atmosphere work as a later
authoring handoff. Do not imply those effects were created by the recipe or
require the end user to install Studio; an authorized operator may use it for
optional inspection.

Roblox's environmental art curriculum documents greyboxing, polishing assets,
assembling a reusable library, constructing the world, and optimization. Its
greybox lesson is a good check that the route is designed before the asset pass;
the construction lessons show how architecture and exterior assets preserve that
spatial intent. Roblox's audio documentation describes positional emitters,
listeners, routing, and effects; the current scene recipe cannot create those
audio objects, so the generated scene must carry them as an explicit handoff to
a service or authoring workflow instead of implying that ambience was built.
See the source index for links.

Production references reinforce the order of work: Riot's environment-art
overview stresses prioritizing layout and assets around the intended player
experience; Epic's level-design guide calls out entries, exits, refuge, and
sightline control; and GDC's MechaBREAK worldbuilding talk separates biome and
path design from tile restoration and later optimization. Adapt the principles
to the requested game's scale, camera, and device budget rather than copying a
specific game's map or art direction. Christopher Totten's GDC architecture
talk is a reference for spatial arrangements, camera-aware spaces, plans and
sections, whiteboxing, and prospect/refuge; GDC's interior-design talk links
room function and aesthetics to player readability.
