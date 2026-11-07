-- Run the shipped rule script with deterministic Roblox event doubles under Lute.
local rules = {}
local connections = 0
local function signal()
    return { Connect = function(self, callback)
        assert(not self.callback, "Duplicate handler")
        self.callback = callback
        connections += 1
    end }
end
local function part()
    return { CanTouch = true, IsA = function(_, name) return name == "BasePart" end,
        Touched = signal() }
end
local function folder(parts)
    return { GetChildren = function() return parts end,
        IsA = function(_, name) return name == "Folder" end }
end
local pickupA, pickupB, hazard, finish = part(), part(), part(), part()
local folders = {
    Collectible = folder({pickupA, pickupB}), Hazard = folder({hazard}), Landmark = folder({finish}),
}
local spawnPoint = {}
local map = {}
function map:FindFirstChild(name) return folders[name] end
function map:WaitForChild(name)
    if name == "RGA Spawn" then
        return { FindFirstChildWhichIsA = function() return spawnPoint end }
    end
    assert(name == "RGA Gameplay Rules")
    return { Value = "" }
end
local player = {PlayerGui = {}}
function player:FindFirstChild(name) return self[name] end
function player:WaitForChild(name) return self[name] end
local task = {spawn = function(fn, ...) fn(...) end}
local UDim2 = {fromScale = function(x, y) return {x, y} end,
    new = function(...) return {...} end}
local Color3 = {fromRGB = function(r, g, b) return {r, g, b} end}
local humanoid = { Health = 100, MaxHealth = 100 }
function humanoid:TakeDamage(amount) self.Health -= amount end
local character = { FindFirstChildOfClass = function() return humanoid end }
local hit = { FindFirstAncestorOfClass = function() return character end }
local services = {
    Players = {
        PlayerAdded = signal(), PlayerRemoving = signal(),
        GetPlayers = function() return {player} end,
        GetPlayerFromCharacter = function(_, model) return if model == character then player else nil end,
    },
    Workspace = { WaitForChild = function()
        return { FindFirstChildWhichIsA = function() return map end }
    end },
    HttpService = { JSONDecode = function() return rules end },
}
local game = { GetService = function(_, name) return services[name] end }
local Instance = { new = function()
    return setmetatable({Value = 0}, { __newindex = function(self, key, value)
        rawset(self, key, value)
        if key == "Parent" then value[self.Name] = self end
    end })
end }
local function runTemplate()
    -- INSERT TRUSTED TEMPLATE
end

local score = { trigger_role = "collectible", action = "award_points", amount = 3 }
local damage = { trigger_role = "hazard", action = "damage", amount = 85 }
local eliminate = { trigger_role = "hazard", action = "eliminate" }
local win = { trigger_role = "landmark", action = "award_win", minimum_points = 6 }
for _, invalid in {
    {score, {trigger_role = "landmark", action = "award_win", minimum_points = 7}},
    {score, damage, eliminate, win},
    {score, score},
    {score, {trigger_role = "landmark", action = "execute"}},
} do
    rules = invalid
    assert(not pcall(runTemplate), "Invalid rule set accepted")
    assert(connections == 0 and player.leaderstats == nil, "Rejected game left active handlers")
end
rules = {win, score, damage}
runTemplate()
hazard.Touched.callback(hit)
assert(humanoid.Health == 15)
hazard.Touched.callback(hit)
assert(humanoid.Health == 15)
pickupA.Touched.callback(hit)
pickupA.Touched.callback(hit)
finish.Touched.callback(hit)
assert(player.leaderstats.Points.Value == 3 and player.leaderstats.Wins.Value == 0)
pickupB.Touched.callback(hit)
finish.Touched.callback(hit)
assert(player.leaderstats.Points.Value == 0 and player.leaderstats.Wins.Value == 1)
hazard.Touched.callback(hit)
assert(humanoid.Health == 1)
pickupA.Touched.callback(hit)
assert(player.leaderstats.Points.Value == 3)
