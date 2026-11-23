-- Strict JSON profile shared with packages/protocol/tests/protocol_strict_json.py.
-- It intentionally rejects null because Luau tables cannot preserve its presence.

local StrictJson = {}

StrictJson.MAX_MESSAGE_BYTES = 1_048_576
StrictJson.MAX_DEPTH = 12

local ARRAY_METATABLE = { __json_kind = "array" }
local OBJECT_METATABLE = { __json_kind = "object" }
local SIMPLE_ESCAPES = {
	['"'] = '"',
	["\\"] = "\\",
	["/"] = "/",
	b = "\b",
	f = "\f",
	n = "\n",
	r = "\r",
	t = "\t",
}

local function isDigit(byte)
	return byte ~= nil and byte >= 48 and byte <= 57
end

local function isWhitespace(byte)
	return byte == 0x20 or byte == 0x09 or byte == 0x0A or byte == 0x0D
end

local function codepointUtf8(codepoint)
	return utf8.char(codepoint)
end

function StrictJson.parse(text)
	if type(text) ~= "string" then
		return nil, "invalid_utf8"
	end
	if #text > StrictJson.MAX_MESSAGE_BYTES then
		return nil, "size_exceeded"
	end
	local utf8Ok, codepointCount = pcall(utf8.len, text)
	if not utf8Ok or codepointCount == nil then
		return nil, "invalid_utf8"
	end
	if string.sub(text, 1, 3) == "\239\187\191" then
		return nil, "invalid_json"
	end
	local first = 1
	while first <= #text and isWhitespace(string.byte(text, first)) do
		first += 1
	end
	if string.sub(text, first, first) ~= "{" then
		return nil, "not_object"
	end

	local index = first
	local length = #text
	local function fail(reason)
		error({ reason = reason }, 0)
	end
	local function skipWhitespace()
		while index <= length and isWhitespace(string.byte(text, index)) do
			index += 1
		end
	end
	local function parseString()
		if string.byte(text, index) ~= 34 then
			fail("invalid_json")
		end
		index += 1
		local chunks = {}
		local chunkStart = index
		while index <= length do
			local byte = string.byte(text, index)
			if byte == 34 then
				table.insert(chunks, string.sub(text, chunkStart, index - 1))
				index += 1
				return table.concat(chunks)
			elseif byte == 92 then
				table.insert(chunks, string.sub(text, chunkStart, index - 1))
				index += 1
				local escaped = string.sub(text, index, index)
				if SIMPLE_ESCAPES[escaped] ~= nil then
					table.insert(chunks, SIMPLE_ESCAPES[escaped])
					index += 1
				elseif escaped == "u" then
					local hex = string.sub(text, index + 1, index + 4)
					if #hex ~= 4 or not string.match(hex, "^%x%x%x%x$") then
						fail("invalid_json")
					end
					local codepoint = tonumber(hex, 16)
					index += 5
					if codepoint >= 0xD800 and codepoint <= 0xDBFF then
						if string.sub(text, index, index + 1) ~= "\\u" then
							fail("lone_surrogate")
						end
						local lowHex = string.sub(text, index + 2, index + 5)
						if #lowHex ~= 4 or not string.match(lowHex, "^%x%x%x%x$") then
							fail("invalid_json")
						end
						local low = tonumber(lowHex, 16)
						if low < 0xDC00 or low > 0xDFFF then
							fail("lone_surrogate")
						end
						codepoint = 0x10000 + (codepoint - 0xD800) * 0x400 + (low - 0xDC00)
						index += 6
					elseif codepoint >= 0xDC00 and codepoint <= 0xDFFF then
						fail("lone_surrogate")
					end
					table.insert(chunks, codepointUtf8(codepoint))
				else
					fail("invalid_json")
				end
				chunkStart = index
			elseif byte < 0x20 then
				fail("invalid_json")
			else
				index += 1
			end
		end
		fail("invalid_json")
	end

	local parseValue
	local function parseObject(depth)
		if depth > StrictJson.MAX_DEPTH then
			fail("depth_exceeded")
		end
		index += 1
		local result = setmetatable({}, OBJECT_METATABLE)
		local seen = {}
		skipWhitespace()
		if string.byte(text, index) == 125 then
			index += 1
			return result
		end
		while true do
			skipWhitespace()
			if string.byte(text, index) ~= 34 then
				fail("invalid_json")
			end
			local key = parseString()
			if seen[key] then
				fail("duplicate_key")
			end
			seen[key] = true
			skipWhitespace()
			if string.byte(text, index) ~= 58 then
				fail("invalid_json")
			end
			index += 1
			skipWhitespace()
			result[key] = parseValue(depth + 1)
			skipWhitespace()
			local delimiter = string.byte(text, index)
			if delimiter == 125 then
				index += 1
				return result
			elseif delimiter ~= 44 then
				fail("invalid_json")
			end
			index += 1
		end
	end
	local function parseArray(depth)
		if depth > StrictJson.MAX_DEPTH then
			fail("depth_exceeded")
		end
		index += 1
		local result = setmetatable({}, ARRAY_METATABLE)
		skipWhitespace()
		if string.byte(text, index) == 93 then
			index += 1
			return result
		end
		while true do
			skipWhitespace()
			table.insert(result, parseValue(depth + 1))
			skipWhitespace()
			local delimiter = string.byte(text, index)
			if delimiter == 93 then
				index += 1
				return result
			elseif delimiter ~= 44 then
				fail("invalid_json")
			end
			index += 1
		end
	end
	local function parseNumber()
		local start = index
		if string.byte(text, index) == 45 then
			index += 1
		end
		local firstByte = string.byte(text, index)
		if firstByte == 48 then
			index += 1
			if isDigit(string.byte(text, index)) then
				fail("invalid_json")
			end
		elseif firstByte ~= nil and firstByte >= 49 and firstByte <= 57 then
			repeat
				index += 1
			until not isDigit(string.byte(text, index))
		else
			fail("invalid_json")
		end
		local integerOnly = true
		if string.byte(text, index) == 46 then
			integerOnly = false
			index += 1
			if not isDigit(string.byte(text, index)) then
				fail("invalid_json")
			end
			repeat
				index += 1
			until not isDigit(string.byte(text, index))
		end
		local exponent = string.byte(text, index)
		if exponent == 69 or exponent == 101 then
			integerOnly = false
			index += 1
			local sign = string.byte(text, index)
			if sign == 43 or sign == 45 then
				index += 1
			end
			if not isDigit(string.byte(text, index)) then
				fail("invalid_json")
			end
			repeat
				index += 1
			until not isDigit(string.byte(text, index))
		end
		local literal = string.sub(text, start, index - 1)
		if integerOnly then
			local digits = if string.sub(literal, 1, 1) == "-"
				then string.sub(literal, 2)
				else literal
			local maximumDigits = "9007199254740992"
			if
				#digits > #maximumDigits or (#digits == #maximumDigits and digits > maximumDigits)
			then
				fail("integer_out_of_range")
			end
		end
		local number = tonumber(literal)
		if number == nil or number ~= number or number == math.huge or number == -math.huge then
			fail(if integerOnly then "integer_out_of_range" else "non_finite")
		end
		return number
	end
	parseValue = function(depth)
		skipWhitespace()
		local byte = string.byte(text, index)
		if byte == 123 then
			return parseObject(depth)
		elseif byte == 91 then
			return parseArray(depth)
		elseif byte == 34 then
			return parseString()
		elseif byte == 116 and string.sub(text, index, index + 3) == "true" then
			index += 4
			return true
		elseif byte == 102 and string.sub(text, index, index + 4) == "false" then
			index += 5
			return false
		elseif byte == 110 and string.sub(text, index, index + 3) == "null" then
			fail("null_value")
		elseif byte == 45 or isDigit(byte) then
			return parseNumber()
		end
		fail("invalid_json")
	end

	local success, value = pcall(parseObject, 1)
	if not success then
		if type(value) == "table" and type(value.reason) == "string" then
			return nil, value.reason
		end
		return nil, "invalid_json"
	end
	skipWhitespace()
	if index <= length then
		return nil, "invalid_json"
	end
	return value
end

function StrictJson.kind(value)
	local metatable = type(value) == "table" and getmetatable(value) or nil
	return metatable and metatable.__json_kind or nil
end

return StrictJson
