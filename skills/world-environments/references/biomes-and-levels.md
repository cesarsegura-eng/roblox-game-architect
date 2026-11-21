# Biomes and playable-space reference

## Biome is a system, not a color preset

Start with the interactions among climate, terrain, geology, soil, hydrology,
vegetation, wildlife, and human modification. Use gradients and transition zones;
real ecological boundaries are often gradual. For a specific place, prefer
regional climate and ecoregion data over generic labels.

| Setting | Environmental logic to preserve | Visual and play opportunities |
|---|---|---|
| Tropical rainforest | Warmth, high moisture, dense canopy, water flow, layered light; the forest floor may receive little direct light | Canopy routes, ravines, streams, wet surfaces, filtered views, layered vertical navigation |
| Temperate forest | Seasonal change, deciduous/conifer mix, leaf litter, understory, streams and varied soils | Seasonal landmarks, readable clearings, fallen timber, canopy gaps, paths shaped by slope and water |
| Coniferous/boreal forest | Long cold season, snow or bog variation, evergreen canopy and low winter light | Strong tree silhouettes, frozen/wet transitions, sheltered clearings, warm/cold contrast |
| Grassland/savanna | Open sightlines, seasonal rainfall, grasses, scattered trees, fire and grazing influence | Distant landmarks, wind-driven motion, exposed traversal, tree islands and water as route anchors |
| Desert | Water scarcity, strong sun/shade contrast, sparse cover, wind and erosion; deserts differ by temperature and substrate | Shade as navigation, dry washes, rock strata, oasis/ecotone transitions, long-distance silhouettes |
| Tundra/alpine | Cold, short growing season, exposed rock, snow/ice, low vegetation and elevation effects | Weather exposure, sheltered pockets, ridge silhouettes, snowdrifts and careful route readability |
| Wetland/freshwater | Saturated soils, shallow water, reeds, channels and seasonal flooding | Raised paths, pools, soft ground boundaries, reflections, obscured low routes and dry refuge |
| Coastal/marine edge | Tides, wave exposure, salt, sediment and freshwater mixing shape land and life | Tide-revealed routes, cliffs/beaches/mangroves, spray, horizon landmarks, safe high ground |

## Specialized settings and connected habitats

The broad labels above hide environmental behavior that changes routes, sight,
sound, and settlement design. Identify the regional subtype and its seasonal or
tidal cycle before choosing props. The following cases are distinct starting
points, not universal asset recipes:

| Setting | Drivers and spatial cues | Useful level and ambience ideas |
|---|---|---|
| Cloud or fog forest | Persistent ridge fog, water capture on leaves, layered canopy, moss and deep leaf litter; the balance of wind, slope, and shelter matters | Let fog soften distant views while canopy breaks reveal landmarks; use dripping leaves, muted distance, and sheltered clearings. Preserve nearby route contrast in low visibility. |
| Tropical seasonal forest and monsoon woodland | Rainfall and plant growth can vary strongly by season; dry-season light, wet-season runoff, and persistent groundwater differ by region | Show the same route in contrasting wet and dry states; make drainage lines, seasonal pools, and dry refuges explain route changes. Do not assume every tropical forest has year-round rain or that rainfall and greenness peak together. |
| Mediterranean shrubland / chaparral | Mild wet season and hot dry season; drought-adapted shrubs, slope/aspect mosaics, and region-specific fire regimes | Use dense scrub to shape partial sightlines and open ridges as navigation points. If showing a burn scar, research its age and recovery stage; fire adaptation does not mean every chaparral system needs frequent fire. |
| Volcanic landscape and lava field | Lava, ash, and cinder create substrates of different ages; weathering and ecological succession gradually establish soils and plant cover | Contrast bare dark flows with older vegetated pockets, fissures, and windblown soil. Treat lava tubes and steep flow edges as site-specific features; the geological setting is not a single biome. |
| River floodplain and seasonal wetland | Flood frequency, flow, water depth, connectivity, sediment, and elevation determine the habitat mosaic | Let raised natural ground carry reliable routes while low channels, ponds, and wetlands change seasonally. Use flood marks, deposition, drift, or cut banks as readable evidence of water movement. |
| Estuary: mangrove, salt marsh, mudflat, and seagrass mosaic | Tides and a fresh-to-salt water gradient control flooding, sediment, vegetation zones, and connections to offshore habitats | Make tidal creeks and elevated refuge routes legible; distinguish tangled mangrove roots, open marsh, exposed mudflat, and submerged grass beds. A Caribbean design may connect mangroves, seagrass, and reefs, but do not treat that arrangement as global. |
| Shallow coral reef, rocky shore, or kelp forest | Depth, light, wave exposure, water clarity, temperature, and substrate support different communities; these are marine habitats, not interchangeable coastal decoration | Use depth bands and reef structure to frame swim routes, shelter, and discovery. In reef scenes, build visual density from habitat structure and preserve clear navigation gaps; in kelp scenes, use vertical motion and filtered light rather than coral props. |
| Cave and subterranean habitat | Entrance, twilight, dark, and submerged zones differ in light, temperature, humidity, water, and available food | Progress from daylight and exterior sound to low-light silhouettes, localized sound, and water echoes. Put natural light only near openings; use authored light sources as explicit game-world fixtures deeper inside. |

These distinctions make level logic more specific: a floodplain needs elevation
and water connectivity; an estuary needs tidal and salinity zones; a cave needs
light and nutrient transitions. Use a local field guide, ecoregion atlas, or
regional authority when a brief names a real place. A general source can inform
the ecological relationship, but it cannot determine culturally accurate
architecture, species placement, exact seasonal color, or a particular site's
history.

These are starting questions, not biome asset lists. Avoid mixing plants and
landforms that need incompatible climates unless the transition is explained.
For a real or ecologically grounded location, reason about habitat communities
through multiple inputs such as landform, slope, water distance, sun exposure,
and human use; noise or a biome label alone does not establish plausible
placement. The AutoBiomes research demonstrates a staged terrain, climate,
elevation, and asset-distribution pipeline, while Zhai et al. describe local
vegetation rules for collaborative landscape design. The current Scene Recipe
does not implement climate or ecology simulation: use these factors as design
checks and handoff guidance, not as claims about generated terrain accuracy.

## Settlement and building logic

- Connect building form to local materials, rainfall, heat/cold, wind, slope,
  available water, transport, and the community's way of life.
- Make construction believable at the chosen stylization level: load-bearing
  masses, supports, openings, roof pitch, drainage, thresholds, and stairs should
  agree with each other.
- For a house, decide who uses each room and why. Keep the entrance readable;
  use circulation rather than doors that lead nowhere; reserve space for camera
  framing, interaction, and character movement.
- For exterior-to-interior transitions, use thresholds, lighting shifts, sound,
  material change, and partial occlusion to communicate shelter and destination.
- Do not treat a real culture's sacred, domestic, or ceremonial forms as generic
  props. Name the reference, research context, and make an original adaptation.

Climate-response ideas are prompts for research, not universal rules: hot-humid
sites may benefit from deep shade, protected rain edges, and cross ventilation;
hot-arid sites may use shade, compact openings, courtyards, or thermal mass;
cold or windy sites may favor compact forms, sheltered entries, and wind breaks;
flood-prone coasts may need raised floors and water-resistant construction.
Validate each idea against the exact region, materials, culture, and period before
using it as a visual cue. The same feature can have different meanings and
performance in different places.

## Map readability and atmosphere

- First pass: route, playable boundaries, vertical changes, chokepoints, loops,
  sightlines, and landmark placement using simple shapes.
- Keep the primary objective and the next useful landmark distinguishable from
  secondary points of interest. Re-test at actual camera height and movement speed.
- Layer the composition: large silhouettes orient; medium shapes frame routes;
  small details reward close inspection. Detail must not drown out traversal cues.
- Use contrast deliberately. Color, luminance, motion, sound, and lighting can
  each signal affordance or mood, but reserve strongest contrast for important
  information. Preserve visibility for color-vision differences.
- Use weather and sound as changing information: rain changes surface sheen and
  audibility; wind reveals exposure; interior reverberation signals enclosure.
  Keep ambience subordinate to gameplay-critical sounds.
- Place narrative evidence where the player can see it along a natural route.
  Props should answer what happened, who used the place, or what changed.
- Assign vegetation, rock, and surface palettes by landform and ecological
  transition instead of scattering biome props uniformly. Treat rivers, roads,
  and trails as continuous route features; make authored settlements readable
  as coherent subareas with their own entry, focal point, and local material
  logic. Keep this design pass separate from later asset-density and device-
  quality optimization.
- Translate the design to the target engine honestly. Roblox recommends native
  Terrain for outdoor environments where it fits the experience's performance
  and lighting needs. RGA's current Scene Recipe emits bounded parts and meshes
  and can configure dynamic Clouds, but it does not generate terrain voxels or
  sculpted heightfields; keep the geometry as a readable blockout and create a
  concrete Terrain-authoring handoff instead of claiming a sculpted landscape.
- Treat lighting as a layered system: global Lighting establishes time, color,
  and shadow style; Atmosphere shapes distant air; local sources identify lamps,
  fires, and focal interactions. Use the schema's supported subset and list
  unavailable post-processing, cloud, or time-transition work as follow-up.
- Make performance a measured art pass. Inspect assembled scenes for unnecessary
  geometry, texture duplication, shadow cost, and overlapping transparency.
  Profile with Roblox Studio's Scene Analysis and MicroProfiler on representative
  devices; recipe object or triangle counts alone do not prove frame-rate or
  memory performance.

## Source notes

- USGS describes ecoregions through interacting geology, geomorphology, soils,
  vegetation, climate, hydrology, and human modification. This supports the
  system-based method above.
- NASA's biome teaching material connects biome patterns to climate, vegetation,
  animals, temperature, and precipitation; use it as an accessible overview,
  then seek local data for precision.
- Christopher Worch's GDC material frames level space through player movement,
  spatial agency, environmental constraints, and the stories produced by a place.
- Wenya He's GDC 2026 MechaBREAK case study describes landform-specific biome
  rules, spline-based rivers and paths, cultural-area modules, and tile-based
  scene restoration. Transfer those production patterns only at the scale the
  target platform supports; the talk's large-world pipeline is not a Roblox
  implementation prescription.
- Epic's Fortnite Creative guidance supports planning entrances, sightlines,
  cover, and layered interior storytelling. Use those spatial checks without
  importing its game-specific layouts or combat balance.

Full links and additional technical sources are in
`references/research-sources.md`.
For route archetypes, house programs, interior circulation, and lighting/sound
handoffs, also read `playable-spaces.md`.
