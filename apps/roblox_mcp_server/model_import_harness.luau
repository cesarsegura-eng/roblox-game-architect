--!strict
-- Fixed RGA asset-import harness. The asset ID arrives only as binary data.
local taskInput: LuauExecutionTaskInput = ({...})[1]
assert(taskInput and taskInput.BinaryInput, "RGA model binary input is missing")

local HttpService = game:GetService("HttpService")
local AssetService = game:GetService("AssetService")
local SerializationService = game:GetService("SerializationService")
local EncodingService = game:GetService("EncodingService")
local CollectionService = game:GetService("CollectionService")
local request = HttpService:JSONDecode(buffer.tostring(taskInput.BinaryInput))
assert(type(request) == "table" and type(request.asset_id) == "string", "invalid asset request")
assert(string.match(request.asset_id, "^[1-9][0-9]*$") ~= nil, "invalid asset ID")

local loaded = AssetService:LoadAssetAsync(tonumber(request.asset_id))
assert(loaded:IsA("Model"), "asset root is not a Model")
local allowed = {
	Model = true,
	Folder = true,
	MeshPart = true,
	SurfaceAppearance = true,
}
local function isAssetUri(value: string): boolean
	return value == "" or string.match(value, "^rbxassetid://[1-9][0-9]*$") ~= nil
end
local descendants = loaded:GetDescendants()
assert(#descendants + 1 <= 512, "asset instance limit exceeded")
local meshpartCount = 0
for _, instance in ipairs(descendants) do
	assert(allowed[instance.ClassName] == true, "asset contains unsupported instance class")
	instance:ClearAllAttributes()
	for _, tag in ipairs(CollectionService:GetTags(instance)) do
		CollectionService:RemoveTag(instance, tag)
	end
	if instance:IsA("MeshPart") then
		meshpartCount += 1
		assert(meshpartCount <= 128, "asset MeshPart limit exceeded")
		assert(isAssetUri(instance.MeshId) and instance.MeshId ~= "", "unsupported MeshId")
		assert(isAssetUri(instance.TextureID), "unsupported MeshPart texture")
		instance.Anchored = true
		instance.CanCollide = true
		instance.CanTouch = true
		instance.CanQuery = true
		instance.CollisionFidelity = Enum.CollisionFidelity.Box
		instance.Name = string.format("MeshPart_%03d", meshpartCount)
	elseif instance:IsA("SurfaceAppearance") then
		assert(instance.Parent and instance.Parent:IsA("MeshPart"), "orphaned SurfaceAppearance")
		assert(
			isAssetUri(instance.ColorMap)
				and isAssetUri(instance.MetalnessMap)
				and isAssetUri(instance.NormalMap)
				and isAssetUri(instance.RoughnessMap),
			"unsupported SurfaceAppearance texture"
		)
		instance.Name = "SurfaceAppearance"
	elseif instance:IsA("Model") or instance:IsA("Folder") then
		instance.Name = "RGA Imported Group"
	end
end
assert(meshpartCount >= 1, "asset contains no MeshParts")
loaded:ClearAllAttributes()
loaded.Name = "RGA Imported Model"
for _, tag in ipairs(CollectionService:GetTags(loaded)) do
	CollectionService:RemoveTag(loaded, tag)
end

local serialized = SerializationService:SerializeInstancesAsync({loaded})
assert(buffer.len(serialized) <= 512000, "serialized model byte limit exceeded")
local encoded = EncodingService:Base64Encode(serialized)
return {
	schema_version = 1,
	asset_id = request.asset_id,
	instance_count = #descendants + 1,
	meshpart_count = meshpartCount,
	model_base64 = buffer.tostring(encoded),
}
