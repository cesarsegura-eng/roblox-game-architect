-- Execute the shipped cloud harness with controlled pathfinding outcomes.
local input = {}
local queries = {}
local failAt = nil
local destroyed = false
local path = {
    ComputeAsync = function(self, startPoint, endPoint)
        table.insert(queries, {startPoint.X, endPoint.X})
        self.Status = if #queries == failAt then "NoPath" else "Success"
    end,
    GetWaypoints = function() return {{}, {}} end,
}
local services = {
    HttpService = {JSONDecode = function() return input end},
    PathfindingService = {CreatePath = function() return path end},
}
local game = {GetService = function(_, name) return services[name] end}
local buffer = {tostring = function(value) return value end}
local Enum = {PartType = {Block = "Block", Ball = "Ball", Cylinder = "Cylinder"},
    PathStatus = {Success = "Success"}}
local Vector3 = {new = function(x, y, z) return {X = x, Y = y, Z = z} end}
local CFrame = {new = function(x, y, z)
    return {PointToWorldSpace = function(_, point)
        return {X = x + point.X, Y = y + point.Y, Z = z + point.Z}
    end}
end}
local Instance = {new = function()
    return {Destroy = function() destroyed = true end}
end}
local workspace = {}
local function runHarness(...)
    -- INSERT CLOUD HARNESS
end

for _, scenario in {{10, 5, 20}, {10}, {}} do
    for _, failingLeg in {0, 2} do
        queries = {}
        destroyed = false
        failAt = failingLeg
        input = {schema_version = 3, geometry_version = 1, name = "Test", objects = {}}
        for _, x in scenario do
            table.insert(input.objects, {name = "Path", role = "path", size = {4, 1, 4},
                cframe = {x, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1}, shape = "Block", can_collide = true})
        end
        local result = runHarness({BinaryInput = "data only"})
        assert(destroyed, "Harness did not clean up")
        assert(result.path_feature_count == #scenario)
        if #scenario < 2 then
            assert(#queries == 0 and not result.navigation_connected)
        else
            assert(#queries == 2, "An intermediate route leg was skipped")
            assert(queries[1][1] == 10 and queries[1][2] == 5, "Recipe order changed")
            assert(queries[2][1] == 5 and queries[2][2] == 20)
            assert(result.navigation_connected == (failingLeg == 0))
            assert(result.navigation_waypoint_count == (if failingLeg == 0 then 4 else 2))
        end
    end
end
print("All route legs, authored order, failure, and cleanup checks passed")
