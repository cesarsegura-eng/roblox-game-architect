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
    if class == "Part" then obj.Touched = signal() end
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
local packageRoot = child(workspace, "Folder", "Roblox Game Architect")
local map = child(packageRoot, "Model", "Treasure Test")
local collectiblesFolder = child(map, "Folder", "Collectible")
local first = child(collectiblesFolder, "Part", "First")
local second = child(collectiblesFolder, "Part", "Second")
local delayed = {}
local function avatar(name)
    local player = node("Player")
    player.Name = name
    local character = {player = player}
    local hit = {FindFirstAncestorOfClass = function() return character end}
    return player, hit
end

local alice, aliceHit = avatar("Alice")
local bob, bobHit = avatar("Bob")
local players = {
    children = {},
    PlayerAdded = signal(),
    PlayerRemoving = signal(),
    GetPlayers = function() return {alice, bob} end,
    GetPlayerFromCharacter = function(_, foundCharacter)
        return foundCharacter.player
    end,
}
alice.Parent = players
bob.Parent = players
local services = {Players = players, Workspace = workspace}
local game = {GetService = function(_, name) return assert(services[name]) end}
run(game, {new = node}, {delay = function(_, callback) table.insert(delayed, callback) end})

local aliceStats = alice.leaderstats
local bobStats = bob.leaderstats
first.Touched:fire(aliceHit)
first.Touched:fire(aliceHit)
assert(aliceStats.Treasures.Value == 1 and aliceStats.Victories.Value == 0)
assert(bobStats.Treasures.Value == 0 and bobStats.Victories.Value == 0)

second.Touched:fire(bobHit)
first.Touched:fire(bobHit)
assert(bobStats.Treasures.Value == 0 and bobStats.Victories.Value == 1)
assert(aliceStats.Treasures.Value == 1 and aliceStats.Victories.Value == 0,
    "Bob's round must not reset Alice's progress")

second.Touched:fire(aliceHit)
assert(aliceStats.Treasures.Value == 0 and aliceStats.Victories.Value == 1)
assert(#delayed == 2, "Each completed player round must have one short debounce")
first.Touched:fire(aliceHit)
second.Touched:fire(aliceHit)
assert(aliceStats.Victories.Value == 1,
    "Touch callbacks during the reset must not start another round")
delayed[2]()
second.Touched:fire(aliceHit)
first.Touched:fire(aliceHit)
assert(aliceStats.Treasures.Value == 0 and aliceStats.Victories.Value == 2,
    "Alice must be able to complete a second round")
assert(bobStats.Treasures.Value == 0 and bobStats.Victories.Value == 1,
    "Alice's second round must not affect Bob")
print("Passed independent two-player progress, two rounds, duplicate touches, and reset debounce")
