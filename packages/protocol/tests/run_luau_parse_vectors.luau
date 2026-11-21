-- Run Python-prepared shared parse vectors through the production Luau parser.
local filesystem = require("@std/fs")
local process = require("@std/process")
local StrictJson = require("../../../apps/studio-plugin/src/Protocol/StrictJson")

if #process.args < 2 then
	process.exit(2)
end
local failures = {}
local caseCount = 0
for argumentIndex = 2, #process.args do
	local path = process.args[argumentIndex]
	local readOk, text = pcall(filesystem.readFileToString, path)
	if not readOk or type(text) ~= "string" then
		process.exit(2)
	end
	local name = string.match(path, "([^/\\]+)$") or path
	local expectedValid = string.sub(name, 1, 8) == "accept__"
	if not expectedValid and string.sub(name, 1, 8) ~= "reject__" then
		process.exit(2)
	end
	local value = StrictJson.parse(text)
	local actual = value ~= nil
	caseCount += 1
	if actual ~= expectedValid then
		table.insert(failures, name)
	end
end

if #failures > 0 then
	for _, name in ipairs(failures) do
		print("FAIL " .. name)
	end
	process.exit(1)
end
print(string.format("PASS %d strict JSON vectors", caseCount))
