-- Validate Python-prepared shared message vectors with the production Luau interpreter.
local filesystem = require("@std/fs")
local process = require("@std/process")
local json = require("@std/json")
local StrictJson = require("../../../apps/studio-plugin/src/Protocol/StrictJson")
local SchemaValidator = require("../../../apps/studio-plugin/src/Protocol/SchemaValidator")
local ProtocolSchemas = require("../../../apps/studio-plugin/src/Protocol/Schemas")

local manifestPath = process.args[2]
if manifestPath == nil then
	process.exit(2)
end
local readOk, manifestText = pcall(filesystem.readFileToString, manifestPath)
if not readOk or type(manifestText) ~= "string" then
	process.exit(2)
end
local decodeOk, manifest = pcall(json.deserialize, manifestText)
if not decodeOk or type(manifest) ~= "table" or type(manifest.cases) ~= "table" then
	process.exit(2)
end

local failures = {}
for _, case in ipairs(manifest.cases) do
	if type(case) ~= "table" or type(case.name) ~= "string" or type(case.text) ~= "string"
		or type(case.expect) ~= "table" or type(case.expect.valid) ~= "boolean"
	then
		process.exit(2)
	end
	local message = StrictJson.parse(case.text)
	local actualValid, stage, path = SchemaValidator.message(
		message,
		ProtocolSchemas.schemas,
		ProtocolSchemas.types
	)
	if actualValid ~= case.expect.valid or (not actualValid
		and (stage ~= case.expect.stage or path ~= case.expect.path))
	then
		table.insert(failures, string.format(
			"%s expected=(%s,%s,%s) actual=(%s,%s,%s)",
			case.name,
			tostring(case.expect.valid),
			tostring(case.expect.stage),
			tostring(case.expect.path),
			tostring(actualValid),
			tostring(stage),
			tostring(path)
		))
	end
end

if #failures > 0 then
	for _, failure in ipairs(failures) do
		print("FAIL " .. failure)
	end
	process.exit(1)
end
print(string.format("PASS %d protocol schema vectors", #manifest.cases))
