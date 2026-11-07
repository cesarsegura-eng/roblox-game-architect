-- Run next to the verified server template written by check_rainforest_round.py.
local run = require("./server")

local function signal()
    local listeners = {}
    return {
        Connect = function(_, callback) table.insert(listeners, callback) end,
        fire = function(_, ...) for _, callback in listeners do callback(...) end end,
    }
end

local function node(class)
    local children = {}
    local obj = {
        children = children,
        GetChildren = function() return children end,
        IsA = function(_, wanted)
            return class == wanted or (class == "Part" and wanted == "BasePart")
        end,
        FindFirstChild = function(self, name) return self[name] end,
        WaitForChild = function(self, name) return assert(self[name], name) end,
        FindFirstChildWhichIsA = function(_, wanted)
            for _, item in children do
                if item:IsA(wanted) then return item end
            end
        end,
    }
    if class == "Part" then obj.CanTouch = true; obj.Touched = signal() end
    if class == "IntValue" then obj.Value = 0 end
    return setmetatable(obj, {
        __newindex = function(self, key, value)
            rawset(self, key, value)
            if key == "Parent" then
                value[self.Name] = self
                table.insert(value.children, self)
            end
        end,
    })
end

local function child(parent, class, name)
    local item = node(class)
    item.Name = name
    item.Parent = parent
    return item
end

local workspace = node("Workspace")
local map = child(child(workspace, "Folder", "Roblox Game Architect"), "Model", "Rainforest Canopy Obby")
local spawn = child(child(map, "Folder", "RGA Spawn"), "SpawnLocation", "Player Spawn")
local coins = child(map, "Folder", "Collectible")
for i = 1, 3 do child(coins, "Part", tostring(i)) end
local goal = child(child(map, "Folder", "Landmark"), "Part", "Summit")
local hazard = child(child(map, "Folder", "Hazard"), "Part", "Lava")
local rulesValue = child(map, "StringValue", "RGA Gameplay Rules")
rulesValue.Value = "verified rainforest rules"

local function avatar()
    local player = node("Player")
    child(player, "PlayerGui", "PlayerGui")
    local humanoid = {Health = 100, MaxHealth = 100}
    local character = {player = player, FindFirstChildOfClass = function(_, name)
        if name == "Humanoid" then return humanoid end
    end}
    return player, {FindFirstAncestorOfClass = function() return character end}, humanoid
end

local alice, aHit = avatar()
local bob, bHit, bHumanoid = avatar()
local players = {
    PlayerAdded = signal(), PlayerRemoving = signal(),
    GetPlayers = function() return {alice} end,
    GetPlayerFromCharacter = function(_, character) return character.player end,
}
local services = {Players = players, Workspace = workspace, HttpService = {
    JSONDecode = function(_, encoded)
        assert(encoded == rulesValue.Value)
        return require("./rules")
    end,
}}
run({GetService = function(_, name) return assert(services[name]) end}, {new = node},
    {spawn = function(fn, ...) fn(...) end},
    {fromScale = function(x, y) return {x, y} end,
        new = function(...) return {...} end},
    {fromRGB = function(r, g, b) return {r, g, b} end})
players.PlayerAdded:fire(bob)
assert(alice.RespawnLocation == spawn and bob.RespawnLocation == spawn)
local aliceHud = alice.PlayerGui["RGA Objective"]
assert(aliceHud.ResetOnSpawn == false)
assert(string.find(aliceHud.Progress.Text, "Earn 3 points", 1, true))
goal.Touched:fire(aHit)
assert(alice.leaderstats.Wins.Value == 0)
coins.children[1].Touched:fire(bHit)
hazard.Touched:fire(bHit)
assert(bHumanoid.Health == 0)
coins.children[2].Touched:fire(bHit)
assert(bob.leaderstats.Points.Value == 1)
for round = 1, 2 do
    for i, coin in coins.children do
        coin.Touched:fire(aHit)
        coin.Touched:fire(aHit)
        assert(alice.leaderstats.Points.Value == i)
        assert(string.find(aliceHud.Progress.Text, "Points: " .. i, 1, true))
    end
    goal.Touched:fire(aHit)
    goal.Touched:fire(aHit)
    assert(alice.leaderstats.Points.Value == 0 and alice.leaderstats.Wins.Value == round)
    assert(string.find(aliceHud.Progress.Text, "Wins: " .. round, 1, true))
    assert(string.find(aliceHud.Progress.Text, "Points: 0", 1, true))
    assert(bob.leaderstats.Points.Value == 1 and bob.leaderstats.Wins.Value == 0)
end
print("Passed two rounds, duplicate touches, early goal, hazard, and independent player scores")
