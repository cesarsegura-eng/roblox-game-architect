-- Run beside the verified Obby template written by check_rainforest_obby.py.
local run = require("./server")

local function signal()
    local listeners = {}
    return {
        Connect = function(_, callback)
            table.insert(listeners, callback)
        end,
        fire = function(_, ...)
            for _, callback in listeners do
                callback(...)
            end
        end,
    }
end

local function node(class)
    local children = {}
    local object = {
        children = children,
        GetChildren = function()
            return children
        end,
        IsA = function(_, wanted)
            return class == wanted
                or ((class == "Part" or class == "SpawnLocation") and wanted == "BasePart")
        end,
        FindFirstChild = function(self, name)
            return self[name]
        end,
        WaitForChild = function(self, name)
            return assert(self[name], name)
        end,
        FindFirstChildWhichIsA = function(_, wanted)
            for _, child in children do
                if child:IsA(wanted) then
                    return child
                end
            end
        end,
        FindFirstChildOfClass = function(_, wanted)
            for _, child in children do
                if child.class == wanted then
                    return child
                end
            end
        end,
    }
    object.class = class
    if class == "SpawnLocation" then
        object.Touched = signal()
        object.CFrame = setmetatable({name = "checkpoint"}, {
            __add = function(cframe, offset)
                return {cframe = cframe, offset = offset}
            end,
        })
    elseif class == "IntValue" then
        object.Value = 0
    elseif class == "Humanoid" then
        object.Health = 100
    end
    return setmetatable(object, {
        __newindex = function(self, key, value)
            rawset(self, key, value)
            if key == "Parent" and value then
                value[self.Name] = self
                table.insert(value.children, self)
            end
        end,
    })
end

local function child(parent, class, name)
    local object = node(class)
    object.Name = name
    object.Parent = parent
    return object
end

local workspace = node("Workspace")
local map = child(child(workspace, "Folder", "Roblox Game Architect"), "Model", "Rainforest Canopy Obby")
local checkpoints = child(map, "Folder", "RGA Checkpoints")
local route = {}
for index = 1, 5 do
    route[index] = child(checkpoints, "SpawnLocation", string.format("%03d Checkpoint", index))
end
local hazards = child(map, "Folder", "Hazard")
local lava = child(hazards, "Part", "Lava")
lava.Touched = signal()

local function player(name)
    local result = node("Player")
    result.Name = name
    result.CharacterAdded = signal()
    local character = child(workspace, "Model", name .. "Character")
    local humanoid = child(character, "Humanoid", "Humanoid")
    character.PivotTo = function(_, pivot)
        character.lastPivot = pivot
    end
    local hit = {
        FindFirstAncestorOfClass = function(_, wanted)
            if wanted == "Model" then
                return character
            end
        end,
    }
    character.Parent = workspace
    return result, hit, humanoid, character
end

local alice, aliceHit, aliceHumanoid, aliceCharacter = player("Alice")
local bob, bobHit, bobHumanoid, bobCharacter = player("Bob")
local characterOwners = {[aliceCharacter] = alice, [bobCharacter] = bob}
local players = {
    PlayerAdded = signal(),
    PlayerRemoving = signal(),
    GetPlayers = function()
        return {alice}
    end,
    GetPlayerFromCharacter = function(_, character)
        return characterOwners[character]
    end,
}
local services = {Players = players, Workspace = workspace}
local game = {GetService = function(_, name)
    return assert(services[name], name)
end}
run(game, {new = node}, {new = function(x, y, z)
    return {x = x, y = y, z = z}
end})
players.PlayerAdded:fire(bob)
assert(alice.RespawnLocation == route[1] and bob.RespawnLocation == route[1])
local aliceStats = alice.leaderstats
local bobStats = bob.leaderstats

route[3].Touched:fire(aliceHit)
assert(aliceStats.Stage.Value == 0, "An early checkpoint advanced the stage")
route[1].Touched:fire(aliceHit)
route[1].Touched:fire(aliceHit)
assert(aliceStats.Stage.Value == 1 and alice.RespawnLocation == route[1])
route[3].Touched:fire(aliceHit)
assert(aliceStats.Stage.Value == 1, "A skipped checkpoint advanced the stage")
route[2].Touched:fire(aliceHit)
route[2].Touched:fire(aliceHit)
assert(aliceStats.Stage.Value == 2 and alice.RespawnLocation == route[2])

for index = 3, #route do
    route[index].Touched:fire(aliceHit)
    assert(aliceStats.Stage.Value == (index == #route and 0 or index))
end
assert(aliceStats.Wins.Value == 1 and alice.RespawnLocation == route[1])
route[5].Touched:fire(aliceHit)
assert(aliceStats.Wins.Value == 1, "A repeated finish awarded another win")
assert(aliceCharacter.lastPivot ~= nil, "The finish did not return the character to start")
print("RGA_OBBY_ORDER_FINISH_PASS")

-- Starting the next run clears its completion latch; players keep independent progress.
route[1].Touched:fire(aliceHit)
route[2].Touched:fire(bobHit)
assert(aliceStats.Stage.Value == 1 and bobStats.Stage.Value == 0)
lava.Touched:fire(aliceHit)
lava.Touched:fire(bobHit)
assert(aliceHumanoid.Health == 0 and bobHumanoid.Health == 0)
assert(aliceStats.Stage.Value == 1 and bobStats.Stage.Value == 0)
print("RGA_OBBY_HAZARD_ISOLATION_PASS")

-- Both independent routes can finish and increment wins independently.
aliceHumanoid.Health = 100
bobHumanoid.Health = 100
for index = 2, #route do
    route[index].Touched:fire(aliceHit)
end
for index = 1, #route do
    route[index].Touched:fire(bobHit)
end
assert(aliceStats.Wins.Value == 2 and bobStats.Wins.Value == 1)
assert(aliceStats.Stage.Value == 0 and bobStats.Stage.Value == 0)
assert(alice.RespawnLocation == route[1] and bob.RespawnLocation == route[1])
print("RGA_OBBY_MULTIPLAYER_PROGRESS_PASS")
