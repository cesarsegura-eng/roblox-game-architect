# Bounded terrain recipes

## Roblox terrain facts

Roblox terrain is a 4-stud voxel grid. The Terrain API supports primitive
volumes (`FillBlock`, `FillBall`, `FillCylinder`, `FillWedge`) and voxel arrays
(`WriteVoxels`). A `WriteVoxels` region must align to the grid, use resolution
4, and have material and occupancy arrays whose dimensions exactly match the
region. Roblox currently documents a hard upper bound of 4,194,304 voxels per
write; the supplied template uses a much smaller operational budget of 131,072
voxels per call (at most 64 × 64 × 32). Split larger terrain into reviewed
chunks and prefer a smaller first pass.

Use the live Roblox reference through the existing Studio MCP `http_get` tool
to confirm current API behavior before writing voxels:

- `https://create.roblox.com/docs/building-and-visuals/studio-modeling/terrain`
- `https://create.roblox.com/docs/reference/engine/classes/Terrain`
- `https://create.roblox.com/docs/studio/mcp`

## Select a construction method

| Need | Method | Review checks |
|---|---|---|
| Broad plateau or ledge | a few aligned `FillBlock` regions | exact bounds, exposed vertical faces, edge transitions |
| Rounded hill or island | overlapping, bounded `FillBall` volumes | avoid excessive overlap; preserve playable slope and skyline |
| Ridge or ravine wall | oriented `FillBlock` or `FillWedge` volumes | stable route width, fall distance, view obstruction |
| Low-resolution natural heightfield | bounded `WriteVoxels` patch | aligned region, exact 3D array sizes, deterministic seed, occupancy and material transitions |
| Roblox Generate-tool biome | Studio Terrain Editor on a disposable copy | treat its output as a starting point; inspect routes, biome seams, and spawn area |

Prefer the Studio Generate tool when its supported biome presets match the
brief and the user can review that interface. For repeatable scripted terrain,
choose a deterministic seed and record it with the generated bounds and
parameters. Do not describe random noise by itself as an ecological model.

## Heightfield design

Before building voxel arrays, create a small height and material plan from the
route, landform, water flow, slope, biome, and camera. Use a few broad elevation
bands and controlled noise to break up symmetry. Derive materials from explicit
rules such as elevation, slope, and water distance; avoid assigning plants or
materials uniformly across a biome label. Use transitions between sand, grass,
ground, rock, mud, snow, or water only where the site supports them.

For each voxel column, compute a deterministic height, then fill only the
bounded solids below it. Use occupancy to soften the surface near the top and
leave air above. Keep shoreline and water occupancy intentional. Clamp every
generated height to the reviewed vertical bounds. Validate the final dimensions
and voxel budget before calling `WriteVoxels`; the API replaces values in its
whole target region, so do not write over terrain the user expects to keep.

## Deterministic heightfield template

This is a small blockout generator, not a biome simulator or production
landscape. Inspect and edit the named configuration before use. Route points
are `(x, z)` voxel coordinates relative to the patch; terrain below the route
centerline blends toward the configured route elevation. The script refuses to
run when the bounds, total voxel count, route, or empty-region preflight fails.
It can take time in Studio, so keep the patch small and run it only through the
reviewed native Studio MCP call described in `SKILL.md`.

```luau
local CONFIG = {
	origin = Vector3.new(-96, 0, -96), -- world-space minimum; each component must align to 4 studs
	width_voxels = 48,
	depth_voxels = 48,
	height_voxels = 24,
	seed = 1729,
	noise_scale = 0.045,
	base_height_voxels = 7,
	height_amplitude_voxels = 4,
	route_height_voxels = 6,
	route_half_width_voxels = 2.5,
	route = {
		{ x = 4, z = 24 },
		{ x = 20, z = 24 },
		{ x = 44, z = 12 },
	},
	surface_material = Enum.Material.Grass,
	route_material = Enum.Material.Ground,
	subsoil_material = Enum.Material.Ground,
	base_material = Enum.Material.Rock,
}

local RESOLUTION = 4
local MAX_SIDE_VOXELS = 64
local MAX_HEIGHT_VOXELS = 32
local MAX_VOXELS_PER_CALL = 131072

local function isInteger(value)
	return typeof(value) == "number" and value == math.floor(value)
end

local function distanceToSegment(px, pz, a, b)
	local dx = b.x - a.x
	local dz = b.z - a.z
	local lengthSquared = dx * dx + dz * dz
	if lengthSquared == 0 then
		return math.sqrt((px - a.x) ^ 2 + (pz - a.z) ^ 2)
	end
	local projection = math.clamp(((px - a.x) * dx + (pz - a.z) * dz) / lengthSquared, 0, 1)
	local nearestX = a.x + projection * dx
	local nearestZ = a.z + projection * dz
	return math.sqrt((px - nearestX) ^ 2 + (pz - nearestZ) ^ 2)
end

local nx = CONFIG.width_voxels
local ny = CONFIG.height_voxels
local nz = CONFIG.depth_voxels
assert(isInteger(nx) and nx >= 4 and nx <= MAX_SIDE_VOXELS, "width_voxels is out of bounds")
assert(isInteger(nz) and nz >= 4 and nz <= MAX_SIDE_VOXELS, "depth_voxels is out of bounds")
assert(isInteger(ny) and ny >= 4 and ny <= MAX_HEIGHT_VOXELS, "height_voxels is out of bounds")
assert(nx * ny * nz <= MAX_VOXELS_PER_CALL, "terrain patch exceeds the voxel budget")
assert(typeof(CONFIG.seed) == "number" and isInteger(CONFIG.seed) and math.abs(CONFIG.seed) <= 1000000, "seed is out of bounds")
assert(typeof(CONFIG.noise_scale) == "number" and CONFIG.noise_scale > 0 and CONFIG.noise_scale <= 0.25, "noise_scale is out of bounds")
assert(
	typeof(CONFIG.base_height_voxels) == "number"
		and CONFIG.base_height_voxels >= 1
		and CONFIG.base_height_voxels < ny
		and typeof(CONFIG.height_amplitude_voxels) == "number"
		and CONFIG.height_amplitude_voxels >= 0
		and CONFIG.height_amplitude_voxels <= ny / 2,
	"height settings are out of bounds"
)
assert(typeof(CONFIG.route_height_voxels) == "number" and CONFIG.route_height_voxels >= 1 and CONFIG.route_height_voxels < ny, "route elevation is out of bounds")
assert(typeof(CONFIG.route_half_width_voxels) == "number" and CONFIG.route_half_width_voxels >= 1 and CONFIG.route_half_width_voxels <= 8, "route width is out of bounds")
assert(#CONFIG.route >= 2, "route needs at least two points")
for _, component in { CONFIG.origin.X, CONFIG.origin.Y, CONFIG.origin.Z } do
	assert(math.abs(component) <= 100000 and component % RESOLUTION == 0, "terrain origin must be bounded and align to the 4-stud voxel grid")
end
assert(#CONFIG.route <= 128, "route has too many points")
for _, point in CONFIG.route do
	assert(typeof(point.x) == "number" and typeof(point.z) == "number", "route point must contain numeric x and z")
	assert(point.x >= 1 and point.x <= nx and point.z >= 1 and point.z <= nz, "route point is outside the terrain patch")
end

local size = Vector3.new(nx * RESOLUTION, ny * RESOLUTION, nz * RESOLUTION)
local region = Region3.new(CONFIG.origin, CONFIG.origin + size):ExpandToGrid(RESOLUTION)
local regionSize = region.Size
assert(regionSize.X == size.X and regionSize.Y == size.Y and regionSize.Z == size.Z, "aligned region differs from the reviewed patch")

local terrain = workspace.Terrain
local _, existingOccupancy = terrain:ReadVoxels(region, RESOLUTION)
for x = 1, nx do
	for y = 1, ny do
		for z = 1, nz do
			assert(existingOccupancy[x][y][z] == 0, "terrain patch is occupied; choose an empty region or a disposable place")
		end
	end
end

local materials = table.create(nx)
local occupancy = table.create(nx)
for x = 1, nx do
	materials[x] = table.create(ny)
	occupancy[x] = table.create(ny)
	for y = 1, ny do
		materials[x][y] = table.create(nz)
		occupancy[x][y] = table.create(nz)
	end
	for z = 1, nz do
		local naturalHeight = CONFIG.base_height_voxels
			+ math.noise((x + CONFIG.seed) * CONFIG.noise_scale, (z - CONFIG.seed) * CONFIG.noise_scale)
			* CONFIG.height_amplitude_voxels
		local nearestRouteDistance = math.huge
		for index = 1, #CONFIG.route - 1 do
			nearestRouteDistance = math.min(
				nearestRouteDistance,
				distanceToSegment(x, z, CONFIG.route[index], CONFIG.route[index + 1])
			)
		end
		local blend = math.clamp(1 - nearestRouteDistance / CONFIG.route_half_width_voxels, 0, 1)
		blend = blend * blend * (3 - 2 * blend)
		local surfaceHeight = math.clamp(
			math.floor(naturalHeight * (1 - blend) + CONFIG.route_height_voxels * blend + 0.5),
			1,
			ny - 1
		)
		local onRoute = nearestRouteDistance <= CONFIG.route_half_width_voxels
		for height = 1, ny do
			if height <= surfaceHeight then
				if height == surfaceHeight then
					materials[x][height][z] = if onRoute then CONFIG.route_material else CONFIG.surface_material
				elseif height <= surfaceHeight - 3 then
					materials[x][height][z] = CONFIG.base_material
				else
					materials[x][height][z] = CONFIG.subsoil_material
				end
				occupancy[x][height][z] = 1
			else
				materials[x][height][z] = Enum.Material.Air
				occupancy[x][height][z] = 0
			end
		end
	end
end

terrain:WriteVoxels(region, RESOLUTION, materials, occupancy)
print(string.format("RGA_TERRAIN_HEIGHTFIELD_PASS %d %d %d %d", nx, ny, nz, nx * ny * nz))
```

## Safety and performance

- Treat `execute_luau` as a privileged Studio action, not as an RGA sandbox.
- Confirm the correct `studio_id`, place, edit/play state, and region first.
- Never call `Terrain:Clear()` or write unbounded regions for a map pass.
- For edits to occupied terrain, use a disposable copy or preserve the exact
  affected voxel data and verify an available restoration path before writing.
- Divide a patch into deterministic chunks; cap each chunk at 131,072 voxels
  and keep the first prototype smaller where possible.
- Avoid excessive voxel resolution, overlapping volumes, broad empty writes,
  and terrain that blocks spawn, exit, or required routes.
- After writing, inspect screenshots and route clearances; test on target
  devices before making performance claims. Voxel count alone is not a runtime
  performance result.
- Save or publish only through the user's requested and approved workflow.

## Validation checklist

- [ ] Terrain bounds and voxel budget match the reviewed plan.
- [ ] The generation is repeatable from its recorded seed and parameters.
- [ ] The spawn, route, objectives, and exits are reachable and readable.
- [ ] Slopes, cliffs, water depth, and collision suit the intended avatar.
- [ ] Terrain transitions support the selected biome and settlement.
- [ ] A viewport inspection and any playtest are reported separately.
- [ ] Unsupported foliage, audio, particles, weather, or polishing are listed as follow-up work.
