"""Fixed, reviewed Roblox gameplay templates selected through bounded data.

Model output never supplies Luau. Each template is project-owned source with a
small parameter surface validated against the scene recipe before serialization.
"""

from __future__ import annotations

from collections import Counter
from itertools import pairwise

from .spatial import PATH_SEGMENT_MAX_GAP, bounds_distance, object_bounds
from .worldbuilding import SceneRecipe, WorldbuildingError, _validate_requested_world_roles

GAMEPLAY_MODES = frozenset({"blockout", "obby", "treasure_hunt", "rule_game"})


class GameplayTemplateError(ValueError):
    """A requested built-in gameplay template cannot be applied to this scene."""


def validate_gameplay_mode(mode: object, recipe: SceneRecipe, gameplay_rules: object = None) -> str:
    if not isinstance(mode, str) or mode not in GAMEPLAY_MODES:
        raise GameplayTemplateError(
            "gameplay_mode must be blockout, obby, treasure_hunt, or rule_game"
        )
    if mode == "rule_game":
        if gameplay_rules is None:
            raise GameplayTemplateError("rule_game requires data-only gameplay_rules")
        validate_gameplay_rules(gameplay_rules, recipe)
        return mode
    if gameplay_rules is not None:
        raise GameplayTemplateError("gameplay_rules are accepted only in rule_game mode")
    if mode == "treasure_hunt":
        count = sum(item.role == "collectible" for item in recipe.objects)
        if not 1 <= count <= 100:
            raise GameplayTemplateError(
                "treasure_hunt requires 1 to 100 scene objects with the collectible role"
            )
        try:
            _validate_requested_world_roles(recipe, {"path", "collectible"})
        except WorldbuildingError as exc:
            raise GameplayTemplateError(str(exc)) from exc
    elif mode == "obby":
        count = sum(item.role == "path" for item in recipe.objects)
        if count < 2:
            raise GameplayTemplateError(
                "obby requires at least two scene objects with the path role"
            )
        try:
            _validate_requested_world_roles(recipe, {"path"})
        except WorldbuildingError as exc:
            raise GameplayTemplateError(str(exc)) from exc
        paths = [item for item in recipe.objects if item.role == "path"]
        for first, second in pairwise(paths):
            gap = bounds_distance(object_bounds(first), object_bounds(second))
            if gap > PATH_SEGMENT_MAX_GAP:
                raise GameplayTemplateError(
                    f"obby route order is disconnected between {first.name!r} and "
                    f"{second.name!r} ({gap:.1f} Blender units; maximum "
                    f"{PATH_SEGMENT_MAX_GAP:g})"
                )
    return mode


def gameplay_script(mode: str) -> tuple[str, str] | None:
    """Return the trusted server Script name/source for a fixed playable mode."""
    if mode == "treasure_hunt":
        return "RGA Treasure Hunt", treasure_hunt_source()
    if mode == "obby":
        return "RGA Obby Course", obby_course_source()
    if mode == "rule_game":
        return "RGA Data Rules", rule_game_source()
    return None


def validate_gameplay_rules(value: object, recipe: SceneRecipe) -> list[dict[str, object]]:
    """Validate the closed touch-rule DSL; rules contain no executable text."""
    if not isinstance(value, list) or not 1 <= len(value) <= 16:
        raise GameplayTemplateError("gameplay_rules must contain between 1 and 16 rules")
    role_counts = Counter(item.role for item in recipe.objects)
    if not role_counts["path"]:
        raise GameplayTemplateError("rule_game requires a path object for the player spawn")
    available_points = 0
    win_threshold = 0
    normalized: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for rule in value:
        if not isinstance(rule, dict) or not isinstance(rule.get("trigger_role"), str):
            raise GameplayTemplateError("each gameplay rule needs a supported trigger_role")
        role = rule["trigger_role"]
        if role not in {"collectible", "hazard", "prop", "landmark"}:
            raise GameplayTemplateError("gameplay rule trigger_role is not touch-interactive")
        if role not in role_counts:
            raise GameplayTemplateError(f"gameplay rule role {role!r} is missing from the recipe")
        action = rule.get("action")
        if action == "award_points":
            if set(rule) != {"trigger_role", "action", "amount"}:
                raise GameplayTemplateError("award_points rule requires only an amount field")
            amount = rule["amount"]
            if type(amount) is not int or not 1 <= amount <= 1000:
                raise GameplayTemplateError("award_points amount must be an integer from 1 to 1000")
            available_points += role_counts[role] * amount
        elif action == "heal":
            if set(rule) != {"trigger_role", "action", "amount"}:
                raise GameplayTemplateError("heal rule requires only an amount field")
            amount = rule["amount"]
            if type(amount) is not int or not 1 <= amount <= 100:
                raise GameplayTemplateError("heal amount must be an integer from 1 to 100")
        elif action == "damage":
            if set(rule) != {"trigger_role", "action", "amount"} or role != "hazard":
                raise GameplayTemplateError("damage rules require hazard and an amount field")
            amount = rule["amount"]
            if type(amount) is not int or not 1 <= amount <= 100:
                raise GameplayTemplateError("damage amount must be an integer from 1 to 100")
        elif action == "eliminate":
            if set(rule) != {"trigger_role", "action"} or role != "hazard":
                raise GameplayTemplateError("eliminate rules require hazard and have no parameters")
            amount = None
        elif action == "speed_boost":
            if role not in {"collectible", "prop"} or set(rule) != {
                "trigger_role",
                "action",
                "amount",
                "duration_seconds",
            }:
                raise GameplayTemplateError(
                    "speed_boost requires a collectible or prop, amount and duration_seconds"
                )
            amount = rule["amount"]
            duration = rule["duration_seconds"]
            if type(amount) is not int or not 1 <= amount <= 16:
                raise GameplayTemplateError("speed_boost amount must be an integer from 1 to 16")
            if type(duration) is not int or not 1 <= duration <= 30:
                raise GameplayTemplateError(
                    "speed_boost duration_seconds must be an integer from 1 to 30"
                )
        elif action == "award_win":
            if set(rule) != {"trigger_role", "action", "minimum_points"} or role != "landmark":
                raise GameplayTemplateError("award_win rules require landmark and minimum_points")
            amount = rule["minimum_points"]
            if type(amount) is not int or not 1 <= amount <= 1000:
                raise GameplayTemplateError(
                    "award_win minimum_points must be an integer from 1 to 1000"
                )
            win_threshold = amount
        else:
            raise GameplayTemplateError("gameplay rule action is unsupported")
        key = (role, action)
        if key in seen:
            raise GameplayTemplateError("gameplay rules cannot repeat a trigger role and action")
        seen.add(key)
        normalized.append(
            {
                "trigger_role": role,
                "action": action,
                **(
                    {"amount": amount}
                    if action in {"award_points", "heal", "damage", "speed_boost"}
                    else {}
                ),
                **(
                    {"duration_seconds": rule["duration_seconds"]}
                    if action == "speed_boost"
                    else {}
                ),
                **({"minimum_points": amount} if action == "award_win" else {}),
            }
        )
    if {("hazard", "damage"), ("hazard", "eliminate")} <= seen:
        raise GameplayTemplateError("damage and eliminate rules cannot share the hazard role")
    if win_threshold and not available_points:
        raise GameplayTemplateError("award_win requires at least one award_points rule")
    if win_threshold > available_points:
        raise GameplayTemplateError(
            f"award_win requires {win_threshold} points but the recipe provides only "
            f"{available_points} per round"
        )
    return normalized


def rule_game_source() -> str:
    """Return the fixed server interpreter with runtime role, field, and range checks."""
    return """local Players = game:GetService("Players")
local Workspace = game:GetService("Workspace")
local HttpService = game:GetService("HttpService")

local packageRoot = Workspace:WaitForChild("Roblox Game Architect")
local map = packageRoot:FindFirstChildWhichIsA("Model")
assert(map, "Generated map model is missing")
local spawnFolder = map:WaitForChild("RGA Spawn")
local spawnPoint = spawnFolder:FindFirstChildWhichIsA("SpawnLocation")
assert(spawnPoint, "Rule Game requires a spawn point")
local encodedRules = map:WaitForChild("RGA Gameplay Rules")
local rules = HttpService:JSONDecode(encodedRules.Value)
assert(type(rules) == "table" and #rules >= 1 and #rules <= 16, "Invalid gameplay rules")
local pointsByPlayer = {}
local consumedByPlayer = {}
local roundReadyByPlayer = {}
local actionsByRole = {}
local partsByRole = {}
local speedBoosts = {}
local availablePoints = 0
local winThreshold = 0
local hudByPlayer = {}

local function updateHud(player)
    local label = hudByPlayer[player]
    local stats = player:FindFirstChild("leaderstats")
    if not label or not stats then return end
    local objective = if winThreshold > 0
        then string.format("Earn %d points, then touch a landmark to win.", winThreshold)
        else "Explore the map and interact with its objects."
    label.Text = string.format("%s\\nPoints: %d  |  Wins: %d\\nProgress lasts for this session.",
        objective, pointsByPlayer[player] or 0, stats.Wins.Value)
end

local function createHud(player)
    local playerGui = player:WaitForChild("PlayerGui", 10)
    if not playerGui or pointsByPlayer[player] == nil then return end
    local gui = Instance.new("ScreenGui")
    gui.Name = "RGA Objective"
    gui.ResetOnSpawn = false
    gui.IgnoreGuiInset = false
    gui.DisplayOrder = 10
    gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
    local label = Instance.new("TextLabel")
    label.Name = "Progress"
    label.Position = UDim2.new(0.04, 0, 0.02, 0)
    label.Size = UDim2.new(0.92, 0, 0, 0)
    label.AutomaticSize = Enum.AutomaticSize.Y
    label.BackgroundColor3 = Color3.fromRGB(20, 28, 36)
    label.BackgroundTransparency = 0.08
    label.TextColor3 = Color3.fromRGB(255, 255, 255)
    label.TextSize = 18
    label.TextWrapped = true
    label.TextScaled = false
    label.TextXAlignment = Enum.TextXAlignment.Left
    label.TextYAlignment = Enum.TextYAlignment.Center
    label.Parent = gui
    hudByPlayer[player] = label
    updateHud(player)
    gui.Parent = playerGui
end

local function addPlayer(player)
    if pointsByPlayer[player] ~= nil then
        return
    end
    pointsByPlayer[player] = 0
    consumedByPlayer[player] = {}
    roundReadyByPlayer[player] = true
    player.RespawnLocation = spawnPoint
    local leaderstats = Instance.new("Folder")
    leaderstats.Name = "leaderstats"
    leaderstats.Parent = player
    local points = Instance.new("IntValue")
    points.Name = "Points"
    points.Parent = leaderstats
    local wins = Instance.new("IntValue")
    wins.Name = "Wins"
    wins.Parent = leaderstats
    task.spawn(createHud, player)
end

local function playerFromHit(hit)
    local character = hit:FindFirstAncestorOfClass("Model")
    local player = character and Players:GetPlayerFromCharacter(character)
    local humanoid = character and character:FindFirstChildOfClass("Humanoid")
    if player and humanoid and humanoid.Health > 0 then
        return player, humanoid
    end
    return nil, nil
end

for _, rule in ipairs(rules) do
    assert(type(rule) == "table", "Invalid gameplay rule")
    local role = rule.trigger_role
    local action = rule.action
    assert(
        role == "collectible" or role == "hazard" or role == "prop" or role == "landmark",
        "Invalid gameplay trigger role"
    )
    local validAction = action == "award_points" or action == "heal"
        or (action == "damage" and role == "hazard")
        or (action == "award_win" and role == "landmark")
        or (action == "eliminate" and role == "hazard")
        or (action == "speed_boost" and (role == "collectible" or role == "prop"))
    assert(validAction, "Invalid gameplay rule action")
    local fieldCount = 0
    for key in pairs(rule) do
        local allowedField = key == "trigger_role" or key == "action"
            or ((action == "award_points" or action == "heal" or action == "damage")
                and key == "amount")
            or (action == "speed_boost" and (key == "amount" or key == "duration_seconds"))
            or (action == "award_win" and key == "minimum_points")
        assert(allowedField, "Unexpected gameplay rule field")
        fieldCount += 1
    end
    local expectedFieldCount = if action == "eliminate" then 2
        elseif action == "speed_boost" then 4 else 3
    assert(fieldCount == expectedFieldCount, "Invalid gameplay rule fields")
    if action == "award_points" then
        assert(
            type(rule.amount) == "number" and rule.amount % 1 == 0
                and rule.amount >= 1 and rule.amount <= 1000,
            "Invalid score amount"
        )
    elseif action == "heal" then
        assert(
            type(rule.amount) == "number" and rule.amount % 1 == 0
                and rule.amount >= 1 and rule.amount <= 100,
            "Invalid heal amount"
        )
    elseif action == "damage" then
        assert(
            type(rule.amount) == "number" and rule.amount % 1 == 0
                and rule.amount >= 1 and rule.amount <= 100,
            "Invalid damage amount"
        )
    elseif action == "speed_boost" then
        assert(
            type(rule.amount) == "number" and rule.amount % 1 == 0
                and rule.amount >= 1 and rule.amount <= 16
                and type(rule.duration_seconds) == "number"
                and rule.duration_seconds % 1 == 0
                and rule.duration_seconds >= 1 and rule.duration_seconds <= 30,
            "Invalid speed boost"
        )
    elseif action == "award_win" then
        assert(
            type(rule.minimum_points) == "number" and rule.minimum_points % 1 == 0
                and rule.minimum_points >= 1 and rule.minimum_points <= 1000,
            "Invalid win threshold"
        )
    end
    if not actionsByRole[role] then
        local folderName = role:sub(1, 1):upper() .. role:sub(2)
        local folder = map:FindFirstChild(folderName)
        assert(folder and folder:IsA("Folder"), "Gameplay rule role folder is missing")
        local parts = folder:GetChildren()
        assert(#parts > 0, "Gameplay rule role is empty")
        for _, part in ipairs(parts) do
            assert(part:IsA("BasePart") and part.CanTouch, "Gameplay part cannot be touched")
        end
        partsByRole[role] = parts
        actionsByRole[role] = {}
    end
    local actions = actionsByRole[role]
    assert(not actions[action], "Duplicate gameplay rule")
    actions[action] = rule
    assert(not (actions.damage and actions.eliminate), "Conflicting hazard rules")
    if action == "award_points" then
        availablePoints += #partsByRole[role] * rule.amount
    elseif action == "award_win" then
        winThreshold = rule.minimum_points
    end
end
assert(winThreshold <= availablePoints, "Win threshold exceeds available points per round")

Players.PlayerAdded:Connect(addPlayer)
Players.PlayerRemoving:Connect(function(player)
    pointsByPlayer[player] = nil
    consumedByPlayer[player] = nil
    roundReadyByPlayer[player] = nil
    hudByPlayer[player] = nil
end)
for _, player in Players:GetPlayers() do
    addPlayer(player)
end

for role, parts in pairs(partsByRole) do
    local actions = actionsByRole[role]
    for _, part in ipairs(parts) do
        part.Touched:Connect(function(hit)
            local player, humanoid = playerFromHit(hit)
            local consumed = player and consumedByPlayer[player]
            if not consumed then
                return
            end
            if not roundReadyByPlayer[player] then
                if actions.eliminate then
                    humanoid.Health = 0
                end
                return
            end
            local leaderstats = player.leaderstats
            if not consumed[part] then
                consumed[part] = true
                if actions.award_points then
                    pointsByPlayer[player] += actions.award_points.amount
                    leaderstats.Points.Value = pointsByPlayer[player]
                end
                if actions.damage then
                    local amount = actions.damage.amount
                    humanoid:TakeDamage(math.min(amount, math.max(0, humanoid.Health - 1)))
                end
                if actions.heal then
                    local healed = humanoid.Health + actions.heal.amount
                    humanoid.Health = math.min(humanoid.MaxHealth, healed)
                end
                if actions.speed_boost then
                    local state = speedBoosts[humanoid]
                    if not state then
                        state = { original = humanoid.WalkSpeed, token = 0 }
                        speedBoosts[humanoid] = state
                    end
                    state.token += 1
                    local token = state.token
                    humanoid.WalkSpeed = math.min(
                        32, humanoid.WalkSpeed + actions.speed_boost.amount
                    )
                    task.delay(actions.speed_boost.duration_seconds, function()
                        if speedBoosts[humanoid] == state and state.token == token then
                            if humanoid.Parent then
                                humanoid.WalkSpeed = state.original
                            end
                            speedBoosts[humanoid] = nil
                        end
                    end)
                end
            end
            if actions.award_win and pointsByPlayer[player] >= winThreshold then
                leaderstats.Wins.Value += 1
                pointsByPlayer[player] = 0
                leaderstats.Points.Value = 0
                consumedByPlayer[player] = {}
                roundReadyByPlayer[player] = false
                task.delay(1, function()
                    if player.Parent and roundReadyByPlayer[player] == false then
                        roundReadyByPlayer[player] = true
                    end
                end)
            end
            if actions.eliminate then
                humanoid.Health = 0
            end
            updateHud(player)
        end)
    end
end
"""


def treasure_hunt_source() -> str:
    """Return fixed server-side logic; no model or user text is interpolated."""
    return """local Players = game:GetService("Players")
local Workspace = game:GetService("Workspace")

local packageRoot = Workspace:WaitForChild("Roblox Game Architect")
local map = packageRoot:FindFirstChildWhichIsA("Model")
assert(map, "Generated map model is missing")
local collectibleFolder = map:WaitForChild("Collectible")
local collectibles = collectibleFolder:GetChildren()
local targetCount = #collectibles
assert(targetCount > 0, "Treasure Hunt needs at least one collectible")
local playerCollections = {}
local roundReadyByPlayer = {}

local function addPlayer(player)
    if playerCollections[player] ~= nil then
        return
    end
    playerCollections[player] = {}
    roundReadyByPlayer[player] = true
    local leaderstats = Instance.new("Folder")
    leaderstats.Name = "leaderstats"
    leaderstats.Parent = player

    local treasures = Instance.new("IntValue")
    treasures.Name = "Treasures"
    treasures.Parent = leaderstats

    local victories = Instance.new("IntValue")
    victories.Name = "Victories"
    victories.Parent = leaderstats
end

Players.PlayerAdded:Connect(addPlayer)
Players.PlayerRemoving:Connect(function(player)
    playerCollections[player] = nil
    roundReadyByPlayer[player] = nil
end)
for _, player in Players:GetPlayers() do
    addPlayer(player)
end

for _, collectible in collectibles do
    if collectible:IsA("BasePart") then
        collectible.Touched:Connect(function(hit)
            local character = hit:FindFirstAncestorOfClass("Model")
            local player = character and Players:GetPlayerFromCharacter(character)
            local leaderstats = player and player:FindFirstChild("leaderstats")
            local treasures = leaderstats and leaderstats:FindFirstChild("Treasures")
            local victories = leaderstats and leaderstats:FindFirstChild("Victories")
            local collected = player and playerCollections[player]
            if not treasures or not victories or not collected or collected[collectible]
                or not roundReadyByPlayer[player] then
                return
            end

            collected[collectible] = true
            treasures.Value += 1
            if treasures.Value >= targetCount then
                victories.Value += 1
                treasures.Value = 0
                playerCollections[player] = {}
                roundReadyByPlayer[player] = false
                task.delay(1, function()
                    if player.Parent and roundReadyByPlayer[player] ~= nil then
                        roundReadyByPlayer[player] = true
                    end
                end)
            end
        end)
    end
end

local hazardFolder = map:FindFirstChild("Hazard")
if hazardFolder then
    for _, hazard in hazardFolder:GetChildren() do
        if hazard:IsA("BasePart") then
            hazard.Touched:Connect(function(hit)
                local character = hit:FindFirstAncestorOfClass("Model")
                local humanoid = character and character:FindFirstChildOfClass("Humanoid")
                if humanoid and humanoid.Health > 0 then
                    humanoid.Health = 0
                end
            end)
        end
    end
end
"""


def obby_course_source() -> str:
    """Return fixed server-side checkpoint and completion logic."""
    return """local Players = game:GetService("Players")
local Workspace = game:GetService("Workspace")

local packageRoot = Workspace:WaitForChild("Roblox Game Architect")
local map = packageRoot:FindFirstChildWhichIsA("Model")
assert(map, "Generated map model is missing")
local checkpointFolder = map:WaitForChild("RGA Checkpoints")
local checkpoints = checkpointFolder:GetChildren()
table.sort(checkpoints, function(left, right)
    return left.Name < right.Name
end)
assert(#checkpoints >= 2, "Obby needs at least two route checkpoints")

local playerStages = {}
local completed = {}

local function addPlayer(player)
    if playerStages[player] ~= nil then
        return
    end
    playerStages[player] = 0
    completed[player] = false
    player.RespawnLocation = checkpoints[1]
    local leaderstats = Instance.new("Folder")
    leaderstats.Name = "leaderstats"
    leaderstats.Parent = player

    local stage = Instance.new("IntValue")
    stage.Name = "Stage"
    stage.Parent = leaderstats

    local wins = Instance.new("IntValue")
    wins.Name = "Wins"
    wins.Parent = leaderstats

    player.CharacterAdded:Connect(function()
        if not player.RespawnLocation then
            player.RespawnLocation = checkpoints[1]
        end
    end)
end

Players.PlayerAdded:Connect(addPlayer)
Players.PlayerRemoving:Connect(function(player)
    playerStages[player] = nil
    completed[player] = nil
end)
for _, player in Players:GetPlayers() do
    addPlayer(player)
end

for index, checkpoint in ipairs(checkpoints) do
    if checkpoint:IsA("SpawnLocation") then
        checkpoint.Touched:Connect(function(hit)
            local character = hit:FindFirstAncestorOfClass("Model")
            local player = character and Players:GetPlayerFromCharacter(character)
            local currentStage = player and playerStages[player]
            local leaderstats = player and player:FindFirstChild("leaderstats")
            local stageValue = leaderstats and leaderstats:FindFirstChild("Stage")
            local wins = leaderstats and leaderstats:FindFirstChild("Wins")
            if not stageValue or not wins or currentStage == nil then
                return
            end
            if index <= currentStage or index > currentStage + 1 then
                return
            end

            playerStages[player] = index
            stageValue.Value = index
            player.RespawnLocation = checkpoint
            if index == 1 then
                completed[player] = false
            elseif index == #checkpoints and not completed[player] then
                wins.Value += 1
                completed[player] = true
                playerStages[player] = 0
                stageValue.Value = 0
                player.RespawnLocation = checkpoints[1]
                if character and character.Parent then
                    character:PivotTo(checkpoints[1].CFrame + Vector3.new(0, 4, 0))
                end
            end
        end)
    end
end

local hazardFolder = map:FindFirstChild("Hazard")
if hazardFolder then
    for _, hazard in hazardFolder:GetChildren() do
        if hazard:IsA("BasePart") then
            hazard.Touched:Connect(function(hit)
                local character = hit:FindFirstAncestorOfClass("Model")
                local humanoid = character and character:FindFirstChildOfClass("Humanoid")
                if humanoid and humanoid.Health > 0 then
                    humanoid.Health = 0
                end
            end)
        end
    end
end
"""
