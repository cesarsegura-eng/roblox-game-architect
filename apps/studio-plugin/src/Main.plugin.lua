-- Local Studio client for reviewing and applying the script-free action subset.
local HttpService = game:GetService("HttpService")
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local StrictJson = require(script.Parent:WaitForChild("Protocol"):WaitForChild("StrictJson"))
local ProtocolSchemas = require(script.Parent:WaitForChild("Protocol"):WaitForChild("Schemas"))
local SchemaValidator =
	require(script.Parent:WaitForChild("Protocol"):WaitForChild("SchemaValidator"))

local API_URL_PREFIX = "http://127.0.0.1:"
local activeToken = ""
local pendingAction = nil
local executionUncertain = false
local MAX_ENTRIES = 2000
local MAX_BODY_BYTES = 800_000
local MAX_DEPTH = 16
local function decodeProtocolResponse(body)
	local decoded, reason = StrictJson.parse(body)
	if decoded == nil then
		error("API response failed the strict JSON profile (" .. tostring(reason) .. ")")
	end
	local valid, stage, path =
		SchemaValidator.message(decoded, ProtocolSchemas.schemas, ProtocolSchemas.types)
	if not valid then
		error(string.format("API response failed protocol validation (%s at %s)", stage, path))
	end
	return decoded
end

local ROOT_NAMES = {
	"Workspace",
	"ReplicatedStorage",
	"ServerScriptService",
	"StarterGui",
	"StarterPlayer",
	"Lighting",
	"SoundService",
	"Teams",
	"ReplicatedFirst",
	"ServerStorage",
}

local toolbar = plugin:CreateToolbar("Roblox Game Architect")
local toggleButton =
	toolbar:CreateButton("RGAConnection", "Connect to the local Roblox Game Architect API", "")
toggleButton.ClickableWhenViewportHidden = true

local widgetInfo =
	DockWidgetPluginGuiInfo.new(Enum.InitialDockState.Float, false, false, 480, 490, 420, 450)
local widget = plugin:CreateDockWidgetPluginGuiAsync("RGAConnection", widgetInfo)
widget.Title = "Roblox Game Architect"

local frame = Instance.new("Frame")
frame.Size = UDim2.fromScale(1, 1)
frame.BackgroundColor3 = Color3.fromRGB(35, 38, 45)
frame.Parent = widget

local function makeLabel(name, text, position, size)
	local label = Instance.new("TextLabel")
	label.Name = name
	label.Text = text
	label.Position = position
	label.Size = size
	label.BackgroundTransparency = 1
	label.TextColor3 = Color3.fromRGB(235, 238, 245)
	label.TextXAlignment = Enum.TextXAlignment.Left
	label.TextWrapped = true
	label.Font = Enum.Font.SourceSans
	label.TextSize = 16
	label.Parent = frame
	return label
end

makeLabel(
	"TokenLabel",
	"Local API token (kept in this widget only)",
	UDim2.fromOffset(12, 10),
	UDim2.new(1, -24, 0, 24)
)
local tokenBox = Instance.new("TextBox")
tokenBox.Name = "Token"
tokenBox.Position = UDim2.fromOffset(12, 38)
tokenBox.Size = UDim2.new(1, -24, 0, 32)
tokenBox.PlaceholderText = "PLUGIN_AUTH_TOKEN"
tokenBox.ClearTextOnFocus = false
tokenBox.Text = ""
tokenBox.TextXAlignment = Enum.TextXAlignment.Left
tokenBox.Parent = frame

makeLabel("PortLabel", "API port", UDim2.fromOffset(12, 78), UDim2.new(1, -24, 0, 22))
local portBox = Instance.new("TextBox")
portBox.Name = "Port"
portBox.Position = UDim2.fromOffset(12, 102)
portBox.Size = UDim2.fromOffset(110, 30)
portBox.Text = "8787"
portBox.ClearTextOnFocus = false
portBox.Parent = frame

local status =
	makeLabel("Status", "Not connected", UDim2.fromOffset(12, 140), UDim2.new(1, -24, 0, 42))
local syncButton = Instance.new("TextButton")
syncButton.Name = "ConnectAndSync"
syncButton.Text = "Fetch approved action for review"
syncButton.Position = UDim2.fromOffset(12, 184)
syncButton.Size = UDim2.new(1, -24, 0, 34)
syncButton.Parent = frame

local reviewScroll = Instance.new("ScrollingFrame")
reviewScroll.Name = "ActionReviewScroll"
reviewScroll.Position = UDim2.fromOffset(12, 228)
reviewScroll.Size = UDim2.new(1, -24, 0, 170)
reviewScroll.CanvasSize = UDim2.new(0, 0, 0, 0)
reviewScroll.AutomaticCanvasSize = Enum.AutomaticSize.Y
reviewScroll.ScrollBarThickness = 8
reviewScroll.BackgroundColor3 = Color3.fromRGB(25, 27, 32)
reviewScroll.Parent = frame

local review = Instance.new("TextLabel")
review.Name = "ActionReview"
review.Text = "No action is awaiting review."
review.Position = UDim2.fromOffset(4, 4)
review.Size = UDim2.new(1, -12, 0, 0)
review.AutomaticSize = Enum.AutomaticSize.Y
review.BackgroundTransparency = 1
review.TextColor3 = Color3.fromRGB(235, 238, 245)
review.TextXAlignment = Enum.TextXAlignment.Left
review.TextYAlignment = Enum.TextYAlignment.Top
review.TextWrapped = true
review.Font = Enum.Font.Code
review.TextSize = 13
review.Parent = reviewScroll

local applyButton = Instance.new("TextButton")
applyButton.Name = "ApplyReviewedAction"
applyButton.Text = "Apply this action to Workspace"
applyButton.Position = UDim2.fromOffset(12, 406)
applyButton.Size = UDim2.new(0.5, -18, 0, 34)
applyButton.Visible = false
applyButton.Parent = frame

local rejectButton = Instance.new("TextButton")
rejectButton.Name = "RejectReviewedAction"
rejectButton.Text = "Reject"
rejectButton.Position = UDim2.new(0.5, 6, 0, 406)
rejectButton.Size = UDim2.new(0.5, -18, 0, 34)
rejectButton.Visible = false
rejectButton.Parent = frame

makeLabel(
	"Notice",
	"Only approved, script-free Workspace edits are supported. Each action is undoable.",
	UDim2.fromOffset(12, 448),
	UDim2.new(1, -24, 0, 30)
)

local function messageId()
	return "m-" .. HttpService:GenerateGUID(false)
end

local function request(body)
	local port = tonumber(portBox.Text)
	if not port or port % 1 ~= 0 or port < 1024 or port > 65535 then
		error("API port must be a whole number from 1024 to 65535")
	end
	local encodedBody = HttpService:JSONEncode(body)
	if body.type == "work.poll" then
		-- Roblox may encode an empty Luau table as a JSON array. The protocol
		-- requires an empty object for work.poll, so replace only this known field.
		encodedBody = string.gsub(encodedBody, '"payload":%[%]', '"payload":{}', 1)
	end
	return HttpService:RequestAsync({
		Url = API_URL_PREFIX .. tostring(port) .. "/v1/messages",
		Method = "POST",
		Headers = {
			["Content-Type"] = "application/json; charset=utf-8",
			["Authorization"] = "Bearer " .. activeToken,
		},
		Body = encodedBody,
	})
end

local function envelope(kind, sessionId, payload)
	local result = {
		protocol_version = { major = 1, minor = 0 },
		kind = "request",
		type = kind,
		message_id = messageId(),
		payload = payload,
	}
	if sessionId then
		result.session_id = sessionId
	end
	return result
end

local function readProperties(instance)
	if not (instance:IsA("BasePart")) then
		return nil
	end
	local color = instance.Color
	local size = instance.Size
	local position = instance.Position
	local orientation = instance.Orientation
	local properties = {
		Anchored = instance.Anchored,
		CanCollide = instance.CanCollide,
		Transparency = instance.Transparency,
		Color = { r = color.R, g = color.G, b = color.B },
	}
	if
		size.X >= 0.05
		and size.Y >= 0.05
		and size.Z >= 0.05
		and size.X <= 2048
		and size.Y <= 2048
		and size.Z <= 2048
	then
		properties.Size = { x = size.X, y = size.Y, z = size.Z }
	end
	if
		math.abs(position.X) <= 100000
		and math.abs(position.Y) <= 100000
		and math.abs(position.Z) <= 100000
	then
		properties.Position = { x = position.X, y = position.Y, z = position.Z }
	end
	if
		math.abs(orientation.X) <= 360
		and math.abs(orientation.Y) <= 360
		and math.abs(orientation.Z) <= 360
	then
		properties.Orientation = { x = orientation.X, y = orientation.Y, z = orientation.Z }
	end
	local material = instance.Material.Name
	local allowedMaterials = {
		Plastic = true,
		SmoothPlastic = true,
		Wood = true,
		WoodPlanks = true,
		Metal = true,
		Concrete = true,
		Brick = true,
		Glass = true,
		Neon = true,
		Grass = true,
		Sand = true,
		Fabric = true,
	}
	if allowedMaterials[material] then
		properties.Material = { enum = "Material", item = material }
	end
	return properties
end

local function collectSnapshot(reason, afterActionId)
	local roots = {}
	local frontier = {}
	local entries = {}
	for _, name in ipairs(ROOT_NAMES) do
		local service = game:FindService(name)
		if service then
			table.insert(roots, name)
			table.insert(entries, { path = { name }, class_name = service.ClassName })
			table.insert(frontier, { instance = service, path = { name }, depth = 1 })
		end
	end

	local completeDepth = 1
	local truncated = false
	while #frontier > 0 do
		local nextFrontier = {}
		local levelEntries = {}
		local level = frontier[1].depth + 1
		if level > MAX_DEPTH then
			truncated = true
			break
		end
		local entryLimitReached = false
		for _, parent in ipairs(frontier) do
			local namesAtThisLevel = {}
			for _, child in ipairs(parent.instance:GetChildren()) do
				if #entries + #levelEntries >= MAX_ENTRIES then
					entryLimitReached = true
					break
				end
				if child.Name == "" or #child.Name > 100 or namesAtThisLevel[child.Name] then
					return {
						snapshot_id = messageId(),
						reason = reason,
						roots = roots,
						after_action_id = afterActionId,
						complete_depth = completeDepth,
						truncated = true,
						entries = entries,
					}
				end
				namesAtThisLevel[child.Name] = true
				local path = table.clone(parent.path)
				table.insert(path, child.Name)
				local entry = { path = path, class_name = child.ClassName }
				local properties = readProperties(child)
				if properties then
					entry.properties = properties
				end
				table.insert(levelEntries, entry)
				table.insert(nextFrontier, { instance = child, path = path, depth = level })
			end
			if entryLimitReached then
				break
			end
		end
		if entryLimitReached then
			truncated = true
			break
		end
		local candidateEntries = table.clone(entries)
		for _, entry in ipairs(levelEntries) do
			table.insert(candidateEntries, entry)
		end
		local candidate = {
			snapshot_id = messageId(),
			reason = reason,
			roots = roots,
			complete_depth = level,
			truncated = false,
			entries = candidateEntries,
		}
		if #HttpService:JSONEncode(candidate) > MAX_BODY_BYTES then
			truncated = true
			break
		end
		entries = candidateEntries
		completeDepth = level
		frontier = nextFrontier
	end

	return {
		snapshot_id = messageId(),
		reason = reason,
		after_action_id = afterActionId,
		roots = roots,
		complete_depth = completeDepth,
		truncated = truncated,
		entries = entries,
	}
end

local function sendSnapshot(sessionId)
	local response = request(envelope("project.state", sessionId, collectSnapshot("session_start")))
	if not response.Success then
		error(string.format("API rejected snapshot (HTTP %d)", response.StatusCode))
	end
	local decoded = decodeProtocolResponse(response.Body)
	if decoded.status ~= "ok" then
		local payload = type(decoded.payload) == "table" and decoded.payload or {}
		local issue = tostring(payload.code or "unknown")
		local detail = type(payload.message) == "string"
				and string.sub(string.gsub(payload.message, "[^%w%p ]", "?"), 1, 80)
			or ""
		error("API rejected the place snapshot (" .. issue .. "): " .. detail)
	end
end

local function sendAfterActionSnapshot(sessionId, actionId)
	local payload = collectSnapshot("after_action", actionId)
	local response = request(envelope("project.state", sessionId, payload))
	if not response.Success then
		error(
			string.format("Could not send the after-action snapshot (HTTP %d)", response.StatusCode)
		)
	end
	local decoded = decodeProtocolResponse(response.Body)
	if decoded.status ~= "ok" then
		local issue = type(decoded.payload) == "table" and decoded.payload.code or "unknown"
		error("API rejected the after-action snapshot (" .. tostring(issue) .. ")")
	end
end

local function readbackMatches(target, operation)
	local value = operation.value
	local property = operation.property
	if property == "Anchored" or property == "CanCollide" then
		return target[property] == value
	elseif property == "Transparency" then
		return math.abs(target.Transparency - value) <= 0.0001
	elseif property == "Size" then
		local actual = target.Size
		return math.abs(actual.X - value.x) <= 0.002
			and math.abs(actual.Y - value.y) <= 0.002
			and math.abs(actual.Z - value.z) <= 0.002
	elseif property == "Position" then
		local actual = target.Position
		return math.abs(actual.X - value.x) <= 0.002
			and math.abs(actual.Y - value.y) <= 0.002
			and math.abs(actual.Z - value.z) <= 0.002
	elseif property == "Orientation" then
		local actual = target.Orientation
		return math.abs(actual.X - value.x) <= 0.002
			and math.abs(actual.Y - value.y) <= 0.002
			and math.abs(actual.Z - value.z) <= 0.002
	elseif property == "Color" then
		local actual = target.Color
		-- Studio's BasePart.Color readback quantizes channels to 8-bit values.
		-- Match that measured representation exactly; do not accept arbitrary
		-- color drift with a broad tolerance.
		local function channelMatches(actualChannel, requestedChannel)
			local expectedChannel = math.floor(requestedChannel * 255 + 0.000001) / 255
			return math.abs(actualChannel - expectedChannel) <= 0.00001
		end
		return channelMatches(actual.R, value.r)
			and channelMatches(actual.G, value.g)
			and channelMatches(actual.B, value.b)
	elseif property == "Material" then
		return target.Material.Name == value.item
	end
	return false
end

local function isFiniteNumber(value)
	return type(value) == "number" and value == value and math.abs(value) < math.huge
end

local function hasExactKeys(value, expected)
	if type(value) ~= "table" then
		return false
	end
	local expectedSet = {}
	for _, key in ipairs(expected) do
		expectedSet[key] = true
		if value[key] == nil then
			return false
		end
	end
	for key in pairs(value) do
		if not expectedSet[key] then
			return false
		end
	end
	return true
end

local function validText(value, maximum)
	return type(value) == "string" and #value >= 1 and #value <= maximum
end

local function validArray(value, minimum, maximum)
	if type(value) ~= "table" then
		return false
	end
	local length = #value
	if length < minimum or length > maximum then
		return false
	end
	local count = 0
	for key in pairs(value) do
		if type(key) ~= "number" or key % 1 ~= 0 or key < 1 or key > length then
			return false
		end
		count += 1
	end
	return count == length
end

local function validPath(path)
	if not validArray(path, 1, 16) then
		return false
	end
	for _, segment in ipairs(path) do
		if not validText(segment, 100) then
			return false
		end
	end
	return path[1] == "Workspace"
end

local function pathCoveredByScope(path, scope)
	for _, entry in ipairs(scope) do
		local base = entry.path
		if #base <= #path then
			local matches = true
			for index, segment in ipairs(base) do
				if path[index] ~= segment then
					matches = false
					break
				end
			end
			if matches and (entry.extent == "subtree" or #base == #path) then
				return true
			end
		end
	end
	return false
end

local function validatePropertyValue(property, value)
	if property == "Anchored" or property == "CanCollide" then
		return type(value) == "boolean"
	elseif property == "Transparency" then
		return isFiniteNumber(value) and value >= 0 and value <= 1
	elseif property == "Size" or property == "Position" or property == "Orientation" then
		if not hasExactKeys(value, { "x", "y", "z" }) then
			return false
		end
		for _, axis in ipairs({ "x", "y", "z" }) do
			if not isFiniteNumber(value[axis]) then
				return false
			end
			if property == "Size" and (value[axis] < 0.05 or value[axis] > 2048) then
				return false
			elseif property == "Position" and math.abs(value[axis]) > 100000 then
				return false
			elseif property == "Orientation" and math.abs(value[axis]) > 360 then
				return false
			end
		end
		return true
	elseif property == "Color" then
		if not hasExactKeys(value, { "r", "g", "b" }) then
			return false
		end
		for _, channel in ipairs({ "r", "g", "b" }) do
			if not isFiniteNumber(value[channel]) or value[channel] < 0 or value[channel] > 1 then
				return false
			end
		end
		return true
	elseif property == "Material" then
		local materials = {
			Plastic = true,
			SmoothPlastic = true,
			Wood = true,
			WoodPlanks = true,
			Metal = true,
			Concrete = true,
			Brick = true,
			Glass = true,
			Neon = true,
			Grass = true,
			Sand = true,
			Fabric = true,
		}
		return hasExactKeys(value, { "enum", "item" })
			and value.enum == "Material"
			and type(value.item) == "string"
			and materials[value.item] == true
	end
	return false
end

local function validateEditAction(action)
	if
		not hasExactKeys(action, { "type", "action_id", "declared_scope", "operations" })
		or action.type ~= "edit.action"
		or not validText(action.action_id, 64)
	then
		return false, "Action envelope is malformed."
	end
	local scope = action.declared_scope
	local operations = action.operations
	if not validArray(scope, 1, 32) or not validArray(operations, 1, 100) then
		return false, "Action exceeds the local scope or operation limits."
	end
	for _, entry in ipairs(scope) do
		if
			not hasExactKeys(entry, { "path", "extent" })
			or not validPath(entry.path)
			or (entry.extent ~= "self" and entry.extent ~= "subtree")
		then
			return false, "Action scope is malformed."
		end
	end
	local operationIds = {}
	for _, operation in ipairs(operations) do
		if
			type(operation) ~= "table"
			or not validText(operation.op_id, 64)
			or operationIds[operation.op_id]
		then
			return false, "Action operation identifiers are malformed or duplicated."
		end
		operationIds[operation.op_id] = true
		if operation.op == "create_instance" then
			if
				not hasExactKeys(operation, { "op", "op_id", "parent", "name", "class_name" })
				or not hasExactKeys(operation.parent, { "path", "expect_class" })
				or not validPath(operation.parent.path)
				or not validText(operation.name, 100)
				or (
					operation.class_name ~= "Folder"
					and operation.class_name ~= "Model"
					and operation.class_name ~= "Part"
					and operation.class_name ~= "WedgePart"
				)
			then
				return false, "Action contains an unsupported or malformed creation."
			end
			if
				operation.parent.expect_class ~= "Workspace"
				and operation.parent.expect_class ~= "Folder"
				and operation.parent.expect_class ~= "Model"
			then
				return false, "Action creation parent is outside the safe subset."
			end
			local createdPath = table.clone(operation.parent.path)
			table.insert(createdPath, operation.name)
			if not pathCoveredByScope(createdPath, scope) then
				return false, "Action creation is outside its declared scope."
			end
		elseif operation.op == "set_property" then
			if
				not hasExactKeys(operation, { "op", "op_id", "target", "property", "value" })
				or not hasExactKeys(operation.target, { "path", "expect_class" })
				or not validPath(operation.target.path)
				or (operation.target.expect_class ~= "Part" and operation.target.expect_class ~= "WedgePart")
				or not pathCoveredByScope(operation.target.path, scope)
				or not validatePropertyValue(operation.property, operation.value)
			then
				return false,
					"Action contains a malformed, out-of-scope, or unsupported property change."
			end
		else
			return false, "Action contains an unsupported operation; no changes were applied."
		end
	end
	return true, nil
end

local function displayUntrusted(value)
	local escaped = {}
	for _, codepoint in utf8.codes(value) do
		if codepoint >= 0x20 and codepoint <= 0x7E and codepoint ~= 0x22 and codepoint ~= 0x5C then
			table.insert(escaped, string.char(codepoint))
		elseif codepoint == 0x22 then
			table.insert(escaped, '\\"')
		elseif codepoint == 0x5C then
			table.insert(escaped, "\\\\")
		else
			table.insert(escaped, string.format("\\u{%X}", codepoint))
		end
	end
	return '"' .. table.concat(escaped) .. '"'
end

local function displayPath(path)
	local segments = {}
	for _, segment in ipairs(path) do
		table.insert(segments, displayUntrusted(segment))
	end
	return table.concat(segments, " / ")
end

local function connectAndFetchAction()
	if #tokenBox.Text < 32 then
		error("Enter the local API token (at least 32 characters)")
	end
	activeToken = tokenBox.Text
	local hello = {
		protocol_version = { major = 1, minor = 0 },
		kind = "request",
		type = "session.hello",
		message_id = messageId(),
		payload = {
			client = { name = "RGA Studio Plugin", version = "0.1.0" },
			supported = { { major = 1, max_minor = 0 } },
		},
	}
	local response = request(hello)
	if not response.Success then
		error(string.format("API rejected handshake (HTTP %d)", response.StatusCode))
	end
	local decoded = decodeProtocolResponse(response.Body)
	if decoded.status ~= "ok" or type(decoded.session_id) ~= "string" then
		error("API handshake failed; check the local API and token")
	end
	sendSnapshot(decoded.session_id)
	local pollResponse = request(envelope("work.poll", decoded.session_id, {}))
	if not pollResponse.Success then
		error(string.format("Work poll failed (HTTP %d)", pollResponse.StatusCode))
	end
	local poll = decodeProtocolResponse(pollResponse.Body)
	if poll.status ~= "ok" then
		error("API did not return a work response")
	end
	local work = poll.payload.work
	if work == nil then
		status.Text = "Connected and synced. No approved action is waiting."
		return false
	end
	if work.type == "playtest.request" then
		local report = {
			playtest_id = work.playtest_id,
			outcome = "failed_to_start",
			duration_ms = 0,
			output = {
				{
					t_ms = 0,
					level = "warn",
					text = "Playtests are disabled in this plugin version.",
				},
			},
			output_truncated = false,
		}
		local resultResponse = request(envelope("playtest.report", decoded.session_id, report))
		if not resultResponse.Success then
			error("The API did not accept the blocked playtest report")
		end
		if decodeProtocolResponse(resultResponse.Body).status ~= "ok" then
			error("The API did not accept the blocked playtest report")
		end
		status.Text = "Received a playtest request; it was not run and was reported as blocked."
		return false
	end
	if work.type ~= "edit.action" then
		error("The API returned an unsupported work type; no changes were applied")
	end
	local actionValid, actionProblem = validateEditAction(work)
	if not actionValid then
		error("The API returned an invalid action: " .. actionProblem)
	end
	pendingAction = { session_id = decoded.session_id, work = work }
	local lines = {
		"API-approved action " .. displayUntrusted(work.action_id),
	}
	for _, entry in ipairs(work.declared_scope) do
		table.insert(lines, "Scope (" .. entry.extent .. "): " .. displayPath(entry.path))
	end
	for index, operation in ipairs(work.operations) do
		if operation.op == "create_instance" then
			table.insert(
				lines,
				string.format(
					"%d. Create %s %q under %s",
					index,
					operation.class_name,
					displayUntrusted(operation.name),
					displayPath(operation.parent.path)
				)
			)
		else
			table.insert(
				lines,
				string.format(
					"%d. Set %s at %s to %s",
					index,
					operation.property,
					displayPath(operation.target.path),
					HttpService:JSONEncode(operation.value)
				)
			)
		end
	end
	review.Text = table.concat(lines, "\n")
	review.TextYAlignment = Enum.TextYAlignment.Top
	applyButton.Visible = true
	rejectButton.Visible = true
	status.Text = "Review the action. Studio will recheck every path before applying it."
	return true
end

local function resolvePath(path)
	local instance = game:FindService(path[1])
	if not instance then
		return nil, "service is missing: " .. tostring(path[1])
	end
	for index = 2, #path do
		local matches = {}
		for _, child in ipairs(instance:GetChildren()) do
			if child.Name == path[index] then
				table.insert(matches, child)
			end
		end
		if #matches == 0 then
			return nil, "path is missing at segment " .. tostring(index)
		end
		if #matches ~= 1 then
			return nil, "path is ambiguous at segment " .. tostring(index)
		end
		instance = matches[1]
	end
	return instance
end

local function pathKey(path)
	return HttpService:JSONEncode(path)
end

local function preflight(action)
	local createdClasses = {}
	local createdChildren = {}
	for index, operation in ipairs(action.operations) do
		if operation.op == "create_instance" then
			local parentPath = operation.parent.path
			local parentClass = createdClasses[pathKey(parentPath)]
			if parentClass == nil then
				local parent, problem = resolvePath(parentPath)
				if not parent then
					return index, problem
				end
				parentClass = parent.ClassName
			end
			if parentClass ~= operation.parent.expect_class then
				return index, "parent class changed since planning"
			end
			if
				parentClass ~= "Workspace"
				and parentClass ~= "Folder"
				and parentClass ~= "Model"
			then
				return index, "parent class is outside the safe creation subset"
			end
			local parentKey = pathKey(parentPath)
			createdChildren[parentKey] = createdChildren[parentKey] or {}
			if createdChildren[parentKey][operation.name] then
				return index, "two operations create the same child name"
			end
			if createdClasses[parentKey] == nil then
				local parent, problem = resolvePath(parentPath)
				if not parent then
					return index, problem
				end
				for _, sibling in ipairs(parent:GetChildren()) do
					if sibling.Name == operation.name then
						return index, "a child with this name already exists"
					end
				end
			end
			createdChildren[parentKey][operation.name] = true
			local createdPath = table.clone(parentPath)
			table.insert(createdPath, operation.name)
			createdClasses[pathKey(createdPath)] = operation.class_name
		else
			local path = operation.target.path
			local targetClass = createdClasses[pathKey(path)]
			if targetClass == nil then
				local target, problem = resolvePath(path)
				if not target then
					return index, problem
				end
				targetClass = target.ClassName
			end
			if targetClass ~= operation.target.expect_class then
				return index, "target class changed since planning"
			end
			if targetClass ~= "Part" and targetClass ~= "WedgePart" then
				return index, "target is outside the safe property subset"
			end
		end
	end
	return nil, nil
end

local function applyProperty(target, operation)
	local value = operation.value
	if operation.property == "Anchored" or operation.property == "CanCollide" then
		target[operation.property] = value
	elseif operation.property == "Transparency" then
		target.Transparency = value
	elseif operation.property == "Size" then
		target.Size = Vector3.new(value.x, value.y, value.z)
	elseif operation.property == "Position" then
		target.Position = Vector3.new(value.x, value.y, value.z)
	elseif operation.property == "Orientation" then
		target.Orientation = Vector3.new(value.x, value.y, value.z)
	elseif operation.property == "Color" then
		target.Color = Color3.new(value.r, value.g, value.b)
	elseif operation.property == "Material" and value.enum == "Material" then
		local material = Enum.Material[value.item]
		if not material then
			error("material enum item is unavailable")
		end
		target.Material = material
	else
		error("property is not supported by the local Studio policy")
	end
end

local function skippedOperations(operations, fromIndex)
	local result = {}
	for index = fromIndex, #operations do
		table.insert(result, { op_id = operations[index].op_id, status = "skipped" })
	end
	return result
end

local function rejectedResult(action, index, reason)
	local operations = {}
	local failed = action.operations[index]
	table.insert(operations, {
		op_id = failed.op_id,
		status = "failed",
		error = { code = "preflight_rejected", message = string.sub(tostring(reason), 1, 250) },
	})
	for _, operation in ipairs(skippedOperations(action.operations, index + 1)) do
		table.insert(operations, operation)
	end
	return { action_id = action.action_id, outcome = "rejected", operations = operations }
end

local function applyAction(action)
	local preflightOk, failedIndex, problem = pcall(preflight, action)
	if not preflightOk then
		return rejectedResult(action, 1, failedIndex),
			"Action rejected before any changes: local preflight could not complete."
	end
	if failedIndex then
		return rejectedResult(action, failedIndex, problem),
			"Action rejected before any changes: " .. tostring(problem)
	end
	local recordingOk, recording = pcall(function()
		return ChangeHistoryService:TryBeginRecording(
			"RGA_" .. action.action_id,
			"Apply reviewed Roblox Game Architect changes"
		)
	end)
	if not recordingOk or not recording then
		return rejectedResult(action, 1, "Studio could not start an undo recording"),
			"Studio could not start an undo recording; nothing was applied."
	end

	local operations = {}
	for index, operation in ipairs(action.operations) do
		local ok, applyIssue = pcall(function()
			if operation.op == "create_instance" then
				local parent = resolvePath(operation.parent.path)
				if not parent or parent.ClassName ~= operation.parent.expect_class then
					error("parent changed during apply")
				end
				for _, sibling in ipairs(parent:GetChildren()) do
					if sibling.Name == operation.name then
						error("a child with this name appeared during apply")
					end
				end
				local created = Instance.new(operation.class_name)
				created.Name = operation.name
				if created:IsA("BasePart") then
					created.Anchored = true
				end
				created.Parent = parent
				if
					created.Parent ~= parent
					or created.ClassName ~= operation.class_name
					or (created:IsA("BasePart") and not created.Anchored)
				then
					error("created instance did not match the reviewed action")
				end
			else
				local target = resolvePath(operation.target.path)
				if not target or target.ClassName ~= operation.target.expect_class then
					error("target changed during apply")
				end
				applyProperty(target, operation)
				if not readbackMatches(target, operation) then
					if operation.property == "Color" then
						local actual = target.Color
						local value = operation.value
						error(
							string.format(
								"Color readback mismatch (requested %.6f, %.6f, %.6f; got %.6f, %.6f, %.6f)",
								value.r,
								value.g,
								value.b,
								actual.R,
								actual.G,
								actual.B
							)
						)
					end
					error("property readback did not match the approved value")
				end
			end
		end)
		if not ok then
			local issueText = tostring(applyIssue)
			local diagnosticStart = string.find(issueText, "Color readback mismatch", 1, true)
			if diagnosticStart then
				issueText = string.sub(issueText, diagnosticStart)
			end
			local issue = string.sub(issueText, 1, 200)
			local uncertainOperations = {}
			for previousIndex = 1, index - 1 do
				table.insert(uncertainOperations, {
					op_id = action.operations[previousIndex].op_id,
					status = "applied",
				})
			end
			table.insert(uncertainOperations, {
				op_id = operation.op_id,
				status = "unknown",
			})
			for _, skipped in ipairs(skippedOperations(action.operations, index + 1)) do
				table.insert(uncertainOperations, skipped)
			end
			pcall(function()
				ChangeHistoryService:FinishRecording(
					recording,
					Enum.FinishRecordingOperation.Commit
				)
			end)
			return {
				action_id = action.action_id,
				outcome = "indeterminate",
				operations = uncertainOperations,
			},
				"Apply stopped with an uncertain operation. The API will lock further delivery. "
					.. issue
		end
	end

	local finishOk = pcall(function()
		ChangeHistoryService:FinishRecording(recording, Enum.FinishRecordingOperation.Commit)
	end)
	for _, operation in ipairs(action.operations) do
		table.insert(operations, { op_id = operation.op_id, status = "applied" })
	end
	local notice = finishOk and "Changes applied and recorded for Undo."
		or "Changes applied; Studio did not confirm the Undo recording."
	return { action_id = action.action_id, outcome = "applied", operations = operations }, notice
end

local function sendActionResult(result, action, sessionId)
	local response = request(envelope("edit.result", sessionId, result))
	if not response.Success then
		error(string.format("API result request failed (HTTP %d)", response.StatusCode))
	end
	local decoded = decodeProtocolResponse(response.Body)
	if decoded.status ~= "ok" then
		error("API did not accept the edit result; do not retry this action")
	end
	sendAfterActionSnapshot(sessionId, action.action_id)
end

local function finishPending(reject)
	if not pendingAction or executionUncertain then
		return
	end
	local pending = pendingAction
	local action = pending.work
	pendingAction = nil
	applyButton.Visible = false
	rejectButton.Visible = false
	applyButton.Active = false
	rejectButton.Active = false
	local result
	if reject then
		result = rejectedResult(action, 1, "Human reviewer rejected this action")
		status.Text = "Reporting the rejection..."
	else
		local notice
		result, notice = applyAction(action)
		status.Text = notice
		if result.outcome == "indeterminate" then
			executionUncertain = true
			syncButton.Active = false
		end
	end
	local ok, issue = pcall(sendActionResult, result, action, pending.session_id)
	if not ok then
		executionUncertain = true
		syncButton.Active = false
		status.Text =
			"Result or snapshot was not confirmed. Do not reapply; restart Studio and inspect the API lock."
		review.Text = tostring(issue)
	else
		if result.outcome == "indeterminate" then
			review.Text = status.Text
		else
			review.Text = "Action result and fresh snapshot sent."
		end
		if reject then
			status.Text = "Action rejected; nothing was changed."
		end
		syncButton.Active = true
	end
	activeToken = ""
	applyButton.Active = true
	rejectButton.Active = true
end

applyButton.Activated:Connect(function()
	finishPending(false)
end)

rejectButton.Activated:Connect(function()
	finishPending(true)
end)

syncButton.Activated:Connect(function()
	if pendingAction or executionUncertain then
		return
	end
	syncButton.Active = false
	status.Text = "Connecting, syncing, and checking for approved work..."
	local ok, hasPending = pcall(connectAndFetchAction)
	if not ok then
		local issue = tostring(hasPending)
		local apiIssue = string.match(issue, "API rejected[^\n]*")
		status.Text = "Connection failed: " .. (apiIssue or issue):sub(-110)
		review.Text = "Connection details:\n" .. issue
		activeToken = ""
	elseif not hasPending then
		activeToken = ""
	end
	tokenBox.Text = ""
	if ok and hasPending then
		syncButton.Active = false
	elseif not executionUncertain then
		syncButton.Active = true
	end
end)

toggleButton.Click:Connect(function()
	widget.Enabled = not widget.Enabled
end)

plugin.Unloading:Connect(function()
	tokenBox.Text = ""
	activeToken = ""
	widget:Destroy()
end)
