-- Interpreter for the closed JSON Schema subset audited by packages/protocol.
local SchemaValidator = {}

local function escapePointer(value)
	return (string.gsub(string.gsub(tostring(value), "~", "~0"), "/", "~1"))
end

local function valueType(value)
	if type(value) == "table" then
		local kind = getmetatable(value)
		return kind and kind.__json_kind or "object"
	elseif type(value) == "number" and value % 1 == 0 then
		return "integer"
	end
	return type(value)
end

local function sameType(value, expected)
	local actual = valueType(value)
	if expected == "number" then
		return actual == "number" or actual == "integer"
	end
	return actual == expected
end

local function normalizePath(path)
	local parts = {}
	for part in string.gmatch(path, "[^/]+") do
		if part == ".." then
			table.remove(parts)
		elseif part ~= "." then
			table.insert(parts, part)
		end
	end
	return table.concat(parts, "/")
end

local function resolveReference(schemas, currentFile, reference)
	local file, fragment = string.match(reference, "^([^#]*)#?(.*)$")
	local targetFile = currentFile
	if file ~= "" then
		local directory = string.match(currentFile, "^(.*)/[^/]+$")
		targetFile = normalizePath(if directory then directory .. "/" .. file else file)
	end
	local target = schemas[targetFile]
	if target == nil then
		return nil
	end
	if fragment == "" then
		return target, targetFile
	end
	local definition = string.match(fragment, "^/$defs/([%w_]+)$")
	if definition == nil or type(target["$defs"]) ~= "table" then
		return nil
	end
	return target["$defs"][definition], targetFile
end

local function addError(errors, path, keyword)
	table.insert(errors, { path = path, keyword = keyword })
end

local function validate(schema, value, schemas, schemaFile, instancePath, errors)
	if type(schema["$ref"]) == "string" then
		local target, targetFile = resolveReference(schemas, schemaFile, schema["$ref"])
		if target == nil then
			addError(errors, instancePath, "$ref")
			return
		end
		validate(target, value, schemas, targetFile, instancePath, errors)
		return
	end

	local expectedType = schema.type
	local typeMatches = expectedType == nil or sameType(value, expectedType)
	if not typeMatches then
		addError(errors, instancePath, "type")
	end
	if schema.const ~= nil and value ~= schema.const then
		addError(errors, instancePath, "const")
	end
	if type(schema.enum) == "table" then
		local found = false
		for _, option in ipairs(schema.enum) do
			if value == option then
				found = true
				break
			end
		end
		if not found then
			addError(errors, instancePath, "enum")
		end
	end
	if type(schema.oneOf) == "table" then
		local matching = 0
		for _, branch in ipairs(schema.oneOf) do
			local branchErrors = {}
			validate(branch, value, schemas, schemaFile, instancePath, branchErrors)
			if #branchErrors == 0 then
				matching += 1
			end
		end
		if matching ~= 1 then
			addError(errors, instancePath, "oneOf")
		end
	end

	if expectedType == "object" and typeMatches then
		local properties = schema.properties or {}
		for name, propertySchema in pairs(properties) do
			local child = value[name]
			if child ~= nil then
				validate(
					propertySchema,
					child,
					schemas,
					schemaFile,
					instancePath .. "/" .. escapePointer(name),
					errors
				)
			end
		end
		for _, name in ipairs(schema.required or {}) do
			if value[name] == nil then
				addError(errors, instancePath, "required")
				break
			end
		end
		if schema.additionalProperties == false then
			for name in pairs(value) do
				if properties[name] == nil then
					addError(errors, instancePath, "additionalProperties")
					break
				end
			end
		end
	elseif expectedType == "array" and typeMatches then
		local count = #value
		if schema.minItems ~= nil and count < schema.minItems then
			addError(errors, instancePath, "minItems")
		end
		if schema.maxItems ~= nil and count > schema.maxItems then
			addError(errors, instancePath, "maxItems")
		end
		if schema.items ~= nil then
			for index, item in ipairs(value) do
				validate(
					schema.items,
					item,
					schemas,
					schemaFile,
					instancePath .. "/" .. tostring(index - 1),
					errors
				)
			end
		end
	elseif expectedType == "string" and typeMatches then
		local count = utf8.len(value)
		if schema.minLength ~= nil and count < schema.minLength then
			addError(errors, instancePath, "minLength")
		end
		if schema.maxLength ~= nil and count > schema.maxLength then
			addError(errors, instancePath, "maxLength")
		end
	elseif (expectedType == "integer" or expectedType == "number") and typeMatches then
		if schema.minimum ~= nil and value < schema.minimum then
			addError(errors, instancePath, "minimum")
		end
		if schema.maximum ~= nil and value > schema.maximum then
			addError(errors, instancePath, "maximum")
		end
	end
end

local function firstError(errors)
	table.sort(errors, function(left, right)
		if left.path ~= right.path then
			return left.path < right.path
		end
		return left.keyword < right.keyword
	end)
	return errors[1]
end

function SchemaValidator.message(message, schemas, types)
	local kind = message.kind
	if kind ~= "request" and kind ~= "response" then
		return false, "dispatch", "/kind"
	end
	local envelopeFile
	if kind == "response" and message.type == nil then
		envelopeFile = "envelope.error.json"
	else
		local messageType = message.type
		local known = false
		if type(messageType) == "string" then
			for _, candidate in ipairs(types) do
				if messageType == candidate then
					known = true
					break
				end
			end
		end
		if not known then
			return false, "dispatch", "/type"
		end
		if messageType == "session.hello" then
			envelopeFile = "envelope.hello." .. kind .. ".json"
		else
			envelopeFile = "envelope." .. kind .. ".json"
		end
	end

	local envelopeErrors = {}
	validate(schemas[envelopeFile], message, schemas, envelopeFile, "", envelopeErrors)
	if #envelopeErrors > 0 then
		return false, "envelope", firstError(envelopeErrors).path
	end
	local payloadFile
	if message.kind == "request" then
		payloadFile = "messages/" .. message.type .. ".request.json"
	elseif message.status == "ok" then
		payloadFile = "messages/" .. message.type .. ".response.json"
	else
		payloadFile = "error.protocol.json"
	end
	local payloadSchema = schemas[payloadFile]
	if payloadSchema == nil then
		return false, "payload", "/payload"
	end
	local payloadErrors = {}
	validate(payloadSchema, message.payload, schemas, payloadFile, "/payload", payloadErrors)
	if #payloadErrors > 0 then
		return false, "payload", firstError(payloadErrors).path
	end
	return true
end

return SchemaValidator
