local Vector3 = {}
Vector3.__index = Vector3
function Vector3.new(x, y, z)
	return setmetatable({ X = x, Y = y, Z = z }, Vector3)
end
function Vector3.__add(left, right)
	return Vector3.new(left.X + right.X, left.Y + right.Y, left.Z + right.Z)
end

local Region3 = {}
Region3.__index = Region3
function Region3.new(minimum, maximum)
	return setmetatable({
		Size = Vector3.new(
			maximum.X - minimum.X,
			maximum.Y - minimum.Y,
			maximum.Z - minimum.Z
		),
	}, Region3)
end
function Region3:ExpandToGrid(resolution)
	assert(resolution == 4)
	return self
end

local Enum = {
	Material = {
		Air = "Air",
		Grass = "Grass",
		Ground = "Ground",
		Rock = "Rock",
	},
}
local function mockNoise(x, z)
	return math.sin(x + z) * 0.25
end

local isOccupied = false
local writeCount = 0
local firstMaterials = nil
local firstOccupancy = nil
local workspace = {
	Terrain = {
		ReadVoxels = function(_, region, resolution)
			assert(resolution == 4)
			local nx = region.Size.X / resolution
			local ny = region.Size.Y / resolution
			local nz = region.Size.Z / resolution
			local materials = table.create(nx)
			local occupancy = table.create(nx)
			for x = 1, nx do
				materials[x] = table.create(ny)
				occupancy[x] = table.create(ny)
				for y = 1, ny do
					materials[x][y] = table.create(nz, Enum.Material.Air)
					occupancy[x][y] = table.create(nz, 0)
				end
			end
			if isOccupied then
				occupancy[1][1][1] = 1
			end
			return materials, occupancy
		end,
		WriteVoxels = function(_, region, resolution, materials, occupancy)
			assert(resolution == 4)
			local nx = region.Size.X / resolution
			local ny = region.Size.Y / resolution
			local nz = region.Size.Z / resolution
			assert(#materials == nx and #occupancy == nx)
			local solid = 0
			for x = 1, nx do
				assert(#materials[x] == ny and #occupancy[x] == ny)
				for y = 1, ny do
					assert(#materials[x][y] == nz and #occupancy[x][y] == nz)
					for z = 1, nz do
						assert(typeof(occupancy[x][y][z]) == "number")
						if occupancy[x][y][z] > 0 then
							solid += 1
							assert(materials[x][y][z] ~= Enum.Material.Air)
						end
					end
				end
			end
			assert(solid > 0 and solid < nx * ny * nz)
			assert(materials[20][6][24] == Enum.Material.Ground, "route centerline should use its configured material")
			if firstMaterials == nil then
				firstMaterials = materials
				firstOccupancy = occupancy
			else
				for x = 1, nx do
					for y = 1, ny do
						for z = 1, nz do
							assert(firstMaterials[x][y][z] == materials[x][y][z], "terrain materials must be deterministic")
							assert(firstOccupancy[x][y][z] == occupancy[x][y][z], "terrain occupancy must be deterministic")
						end
					end
				end
			end
			writeCount += 1
			print(string.format("SIM_TERRAIN_WRITE %d", solid))
		end,
	},
}

local function runGenerator()
-- INSERT TERRAIN GENERATOR
end

runGenerator()
runGenerator()
assert(writeCount == 2, "repeatable empty patch should write twice")
isOccupied = true
local ok, reason = pcall(runGenerator)
assert(not ok and string.find(tostring(reason), "terrain patch is occupied"), "occupied patch must fail closed")
assert(writeCount == 2, "occupied patch must not write")
print("PASS terrain template bounds, array shapes, and occupied-region rejection")
