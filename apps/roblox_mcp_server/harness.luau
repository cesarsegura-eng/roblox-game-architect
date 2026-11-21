--!strict
-- Fixed RGA harness. Recipe bytes arrive as binary task input, never as source.
local taskInput: LuauExecutionTaskInput = ({...})[1]
assert(taskInput and taskInput.BinaryInput, "RGA recipe binary input is missing")

local HttpService = game:GetService("HttpService")
local PathfindingService = game:GetService("PathfindingService")
local recipe = HttpService:JSONDecode(buffer.tostring(taskInput.BinaryInput))
assert(type(recipe) == "table" and type(recipe.objects) == "table", "invalid RGA recipe")
assert(#recipe.objects <= 512, "RGA object limit exceeded")

local created = Instance.new("Folder")
created.Name = "RGA_Disposable_Validation"
created.Parent = workspace
local function buildResult()
local routePoints = {}
local routeNames = {}
local objectCount = 0

assert(recipe.geometry_version == 1, "unsupported collision geometry version")
local shapes = {Block = Enum.PartType.Block, Ball = Enum.PartType.Ball,
    Cylinder = Enum.PartType.Cylinder}
for _, spec in ipairs(recipe.objects) do
    assert(type(spec) == "table" and type(spec.name) == "string", "invalid object data")
    assert(type(spec.size) == "table" and #spec.size == 3, "invalid object size")
    assert(type(spec.cframe) == "table" and #spec.cframe == 12, "invalid object transform")
    assert(type(spec.can_collide) == "boolean" and shapes[spec.shape], "invalid object collision")
    for _, value in ipairs(spec.size) do
        assert(type(value) == "number" and value > 0 and value < math.huge, "invalid dimension")
    end
    for _, value in ipairs(spec.cframe) do
        assert(type(value) == "number" and value == value and math.abs(value) < math.huge,
            "invalid transform component")
    end
    local part = Instance.new("Part")
    part.Name = string.sub(spec.name, 1, 64)
    part.Anchored = true
    part.Size = Vector3.new(table.unpack(spec.size))
    part.CFrame = CFrame.new(table.unpack(spec.cframe))
    part.Shape = shapes[spec.shape]
    part.CanCollide = spec.can_collide
    part.Parent = created
    objectCount += 1
    if spec.role == "path" then
        table.insert(routePoints, part.CFrame:PointToWorldSpace(Vector3.new(0, part.Size.Y / 2 + 2, 0)))
        table.insert(routeNames, string.sub(spec.name, 1, 64))
    end
end

local reachable = 0
local navigationConnected = false
local failedRouteLeg = nil
if #routePoints >= 2 then
	local path = PathfindingService:CreatePath({
		AgentRadius = 2,
		AgentHeight = 5,
		AgentCanJump = true,
	})
    navigationConnected = true
    for index = 2, #routePoints do
        local ok = pcall(function()
            path:ComputeAsync(routePoints[index - 1], routePoints[index])
        end)
        local count = if ok and path.Status == Enum.PathStatus.Success
            then #path:GetWaypoints() else 0
        if count == 0 then
            navigationConnected = false
            failedRouteLeg = {
                -- `index` is the 1-based destination point; leg indexes are 0-based.
                leg_index = index - 2,
                from = routeNames[index - 1],
                to = routeNames[index],
            }
            break
        end
        reachable = math.min(512, reachable + count)
    end
end

local result = {
	schema_version = recipe.schema_version,
	name = recipe.name,
	object_count = objectCount,
	path_feature_count = #routePoints,
	navigation_waypoint_count = reachable,
	navigation_connected = navigationConnected,
	navigation_failed_leg = failedRouteLeg,
}
return result
end

local ok, result = pcall(buildResult)
created:Destroy()
if not ok then
    error(result)
end
return result
