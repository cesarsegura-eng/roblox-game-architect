-- Trusted syntax bridge for packages/sandbox/parser.py.
-- The source file is data: this script parses it and never loads or executes it.

local filesystem = require("@std/fs")
local process = require("@std/process")
local json = require("@std/json")
local parser = require("@std/syntax/parser")
local query = require("@std/syntax/query")

local MAX_ITEMS = 512
local MAX_NAME_LENGTH = 256
local MAX_AST_NODES = 4096
local MAX_AST_DEPTH = 128

local function emptySummary()
	return {
		globals = {},
		access_chains = {},
		calls = {},
		bracket_index_count = 0,
		unresolved_call_count = 0,
		loop_kinds = {},
	}
end

local function addBounded(set, value)
	if type(value) ~= "string" or value == "" or #value > MAX_NAME_LENGTH then
		error("unsupported CST name")
	end
	set[value] = true
	local count = 0
	for _ in set do
		count += 1
		if count > MAX_ITEMS then
			error("CST summary limit exceeded")
		end
	end
end

local function asSortedArray(set)
	local values = {}
	for value in set do
		table.insert(values, value)
	end
	table.sort(values)
	return values
end

local function tokenText(token)
	if type(token) ~= "table" or type(token.text) ~= "string" then
		error("unsupported CST token")
	end
	return token.text
end

local function unwrapNode(node)
	if type(node) ~= "table" then
		error("unsupported CST node wrapper")
	end
	if node.kind == nil and type(node.node) == "table" then
		return node.node
	end
	return node
end

local function simpleStringLiteral(expression)
	local value = tokenText(expression.token)
	if expression.quoteStyle == "single" then
		return "'" .. value .. "'"
	elseif expression.quoteStyle == "double" then
		return "\"" .. value .. "\""
	end
	-- Keep nonstandard/long strings visible to the policy so its simple-literal
	-- allowlist rejects them without making the syntax bridge fail closed early.
	return "[[" .. value .. "]]"
end

local function bindingId(binding)
	if type(binding) ~= "table" or binding.kind ~= "local" or type(binding.location) ~= "table" then
		error("unsupported CST local binding")
	end
	local location = binding.location
	for _, field in { "beginLine", "beginColumn", "endLine", "endColumn" } do
		if type(location[field]) ~= "number" or location[field] < 1 then
			error("unsupported CST source location")
		end
	end
	return string.format(
		"%d:%d:%d:%d",
		location.beginLine,
		location.beginColumn,
		location.endLine,
		location.endColumn
	)
end

local function serializeProgram(root)
	local nodeCount = 0
	local serializeExpression
	local serializeStatement

	local function enterNode(node, depth)
		if type(node) ~= "table" or depth > MAX_AST_DEPTH then
			error("CST program depth limit exceeded")
		end
		nodeCount += 1
		if nodeCount > MAX_AST_NODES then
			error("CST program node limit exceeded")
		end
	end

	local function serializeBinding(binding)
		binding = unwrapNode(binding)
		return {
			id = bindingId(binding),
			name = tokenText(binding.name),
		}
	end

	local function serializeExpressions(expressions, depth)
		local values = {}
		for _, expression in expressions do
			table.insert(values, serializeExpression(unwrapNode(expression), depth + 1))
		end
		return values
	end

	serializeExpression = function(expression, depth)
		enterNode(expression, depth)
		local tag = expression.tag
		if expression.kind ~= "expr" then
			return { kind = "unsupported", tag = tostring(tag) }
		end
		if tag == "global" then
			return { kind = "global", name = tokenText(expression.name) }
		elseif tag == "local" then
			return {
				kind = "local",
				binding = bindingId(expression["local"]),
				name = tokenText(expression.token),
			}
		elseif tag == "string" then
			return { kind = "string", raw = simpleStringLiteral(expression) }
		elseif tag == "number" or tag == "integer" then
			return { kind = "number", raw = tokenText(expression.token) }
		elseif tag == "boolean" then
			return { kind = "boolean", value = expression.value }
		elseif tag == "nil" then
			return { kind = "nil" }
		elseif tag == "indexname" then
			local accessor = tokenText(expression.accessor)
			if accessor ~= "." and accessor ~= ":" then
				error("unsupported CST accessor")
			end
			return {
				kind = "indexname",
				base = serializeExpression(expression.expression, depth + 1),
				accessor = accessor,
				name = tokenText(expression.index),
			}
		elseif tag == "index" then
			return {
				kind = "index",
				base = serializeExpression(expression.expression, depth + 1),
				index = serializeExpression(expression.index, depth + 1),
			}
		elseif tag == "call" then
			return {
				kind = "call",
				func = serializeExpression(expression.func, depth + 1),
				arguments = serializeExpressions(expression.arguments, depth + 1),
			}
		elseif tag == "binary" then
			return {
				kind = "binary",
				operator = tokenText(expression.operator),
				left = serializeExpression(expression.lhsOperand, depth + 1),
				right = serializeExpression(expression.rhsOperand, depth + 1),
			}
		elseif tag == "unary" then
			return {
				kind = "unary",
				operator = tokenText(expression.operator),
				operand = serializeExpression(expression.operand, depth + 1),
			}
		elseif tag == "group" then
			return {
				kind = "group",
				expression = serializeExpression(expression.expression, depth + 1),
			}
		end
		return { kind = "unsupported", tag = tostring(tag) }
	end

	serializeStatement = function(statement, depth)
		statement = unwrapNode(statement)
		enterNode(statement, depth)
		if statement.kind ~= "stat" then
			return { kind = "unsupported", tag = tostring(statement.tag) }
		end
		local tag = statement.tag
		if tag == "block" then
			local statements = {}
			for _, child in statement.statements do
				table.insert(statements, serializeStatement(child, depth + 1))
			end
			return { kind = "block", statements = statements }
		elseif tag == "local" or tag == "const" then
			local variables = {}
			for _, variable in statement.variables do
				table.insert(variables, serializeBinding(variable))
			end
			return {
				kind = tag,
				variables = variables,
				values = serializeExpressions(statement.values, depth + 1),
			}
		elseif tag == "assign" then
			return {
				kind = "assign",
				targets = serializeExpressions(statement.variables, depth + 1),
				values = serializeExpressions(statement.values, depth + 1),
			}
		elseif tag == "expression" then
			return {
				kind = "expression",
				expression = serializeExpression(statement.expression, depth + 1),
			}
		end
		return { kind = "unsupported", tag = tostring(tag) }
	end

	return serializeStatement(root, 1)
end

local function expressionChain(expression)
	if type(expression) ~= "table" then
		return nil
	end
	if expression.kind == "expr" and expression.tag == "global" then
		return tokenText(expression.name)
	end
	if expression.kind == "expr" and expression.tag == "indexname" then
		local prefix = expressionChain(expression.expression)
		if prefix == nil then
			return nil
		end
		local accessor = tokenText(expression.accessor)
		if accessor ~= "." and accessor ~= ":" then
			error("unsupported CST accessor")
		end
		return prefix .. accessor .. tokenText(expression.index)
	end
	return nil
end

local function collectSummary(tree)
	local globals, accesses, calls, loops = {}, {}, {}, {}
	local bracketIndexes, unresolvedCalls = 0, 0
	local nodes = query.findAllFromRoot(tree, function(node)
		if type(node) ~= "table" then
			error("unsupported CST node")
		end
		if node.kind == "expr" and node.tag == "global" then
			return { kind = "global", name = tokenText(node.name) }
		end
		if node.kind == "expr" and node.tag == "indexname" then
			local chain = expressionChain(node)
			if chain ~= nil then
				return { kind = "access", name = chain }
			end
		end
		if node.kind == "expr" and node.tag == "call" then
			local chain = expressionChain(node.func)
			if chain ~= nil then
				return { kind = "call", name = chain }
			end
			return { kind = "dynamic_call" }
		end
		if node.kind == "expr" and node.tag == "index" then
			return { kind = "dynamic_index" }
		end
		if node.kind == "stat" and (node.tag == "for" or node.tag == "forin" or node.tag == "while" or node.tag == "repeat") then
			return { kind = "loop", name = node.tag }
		end
		return nil
	end):mapToArray(function(item)
		return item
	end)

	for _, item in nodes do
		if type(item) ~= "table" or type(item.kind) ~= "string" then
			error("unsupported CST query result")
		end
		if item.kind == "global" then
			addBounded(globals, item.name)
		elseif item.kind == "access" then
			addBounded(accesses, item.name)
		elseif item.kind == "call" then
			addBounded(calls, item.name)
		elseif item.kind == "dynamic_index" then
			bracketIndexes += 1
		elseif item.kind == "dynamic_call" then
			unresolvedCalls += 1
		elseif item.kind == "loop" then
			loops[item.name] = true
		else
			error("unsupported CST query result")
		end
	end

	return {
		globals = asSortedArray(globals),
		access_chains = asSortedArray(accesses),
		calls = asSortedArray(calls),
		bracket_index_count = bracketIndexes,
		unresolved_call_count = unresolvedCalls,
		loop_kinds = asSortedArray(loops),
	}
end

local sourcePath = process.args[2]
if sourcePath == nil then
	process.exit(2)
end

local readOk, source = pcall(filesystem.readFileToString, sourcePath)
if not readOk or type(source) ~= "string" then
	process.exit(2)
end

local parseOk, tree = pcall(parser.parse, source)
if not parseOk then
	print(json.serialize({
		syntax_valid = false,
		summary = emptySummary(),
		program = { kind = "block", statements = {} },
	}))
	return
end

local summaryOk, summary = pcall(collectSummary, tree)
if not summaryOk then
	process.exit(2)
end
local programOk, program = pcall(serializeProgram, tree.root)
if not programOk then
	process.exit(2)
end
print(json.serialize({ syntax_valid = true, summary = summary, program = program }))
