-- Trusted syntax bridge for packages/sandbox/parser.py.
-- The source file is data: this script parses it and never loads or executes it.

local filesystem = require("@std/fs")
local process = require("@std/process")
local json = require("@std/json")
local parser = require("@std/syntax/parser")

local sourcePath = process.args[2]
if sourcePath == nil then
	process.exit(2)
end

local readOk, source = pcall(filesystem.readFileToString, sourcePath)
if not readOk or type(source) ~= "string" then
	process.exit(2)
end

local parseOk = pcall(parser.parse, source)
print(json.serialize({ syntax_valid = parseOk }))
