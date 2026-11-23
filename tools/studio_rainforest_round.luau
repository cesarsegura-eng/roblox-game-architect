-- Developer-only: run in the SERVER command bar of a fresh Play Solo session.
-- Never insert this test driver into a delivered or published game.
-- Teleporting exercises engine contacts; it does not test navigability.
task.spawn(function()
    local runService = game:GetService("RunService")
    assert(runService:IsStudio() and runService:IsRunning() and runService:IsServer(),
        "Use the server command bar during Studio Play Solo")
    local players = game:GetService("Players"):GetPlayers()
    assert(#players == 1, "This driver requires exactly one test player")
    local player = players[1]
    local map = workspace["Roblox Game Architect"]["Rainforest Canopy Obby"]
    local coins = map.Collectible:GetChildren()
    table.sort(coins, function(a, b) return a.Name < b.Name end)
    assert(#coins == 3, "Expected the reference three-coin map")
    local goal = map.Landmark:GetChildren()[1]
    local stats = player:WaitForChild("leaderstats")
    assert(stats.Points.Value == 0 and stats.Wins.Value == 0, "Start a fresh test session")
    local function touch(part)
        local character = assert(player.Character, "Character missing")
        local root = character:WaitForChild("HumanoidRootPart")
        root.AssemblyLinearVelocity = Vector3.zero
        root.AssemblyAngularVelocity = Vector3.zero
        character:PivotTo(CFrame.new(part.Position + Vector3.new(0, 12, 0)))
        task.wait(0.2)
        character:PivotTo(CFrame.new(part.Position + Vector3.new(0, 2, 0)))
        task.wait(1)
    end
    touch(goal)
    assert(stats.Wins.Value == 0, "Early goal incorrectly awarded a win")
    for round = 1, 2 do
        for index, coin in ipairs(coins) do
            touch(coin)
            assert(stats.Points.Value == index, "Coin score mismatch")
            touch(coin)
            assert(stats.Points.Value == index, "Repeated coin awarded points twice")
        end
        touch(goal)
        assert(stats.Wins.Value == round and stats.Points.Value == 0, "Round did not reset")
        local hud = player.PlayerGui:FindFirstChild("RGA Objective")
        assert(hud and string.find(hud.Progress.Text, "Wins: " .. round, 1, true),
            "HUD does not reflect the server win count")
        print("RGA_ENGINE_ROUND_PASS", round, stats.Points.Value, stats.Wins.Value)
    end
    print("RGA_ENGINE_TWO_ROUNDS_PASS")
    local previousCharacter = player.Character
    local humanoid = previousCharacter:FindFirstChildOfClass("Humanoid")
    touch(map.Hazard:GetChildren()[1])
    assert(humanoid.Health == 0, "Hazard did not eliminate the player")
    local deadline = os.clock() + 15
    while os.clock() < deadline do
        local character = player.Character
        local nextHumanoid = character and character:FindFirstChildOfClass("Humanoid")
        if character ~= previousCharacter and nextHumanoid and nextHumanoid.Health > 0 then
            task.wait(1)
            local hud = player.PlayerGui:FindFirstChild("RGA Objective")
            assert(hud and string.find(hud.Progress.Text, "Wins: 2", 1, true),
                "HUD was lost during respawn")
            assert(stats.Points.Value == 0 and stats.Wins.Value == 2,
                "Respawn changed round stats")
            print("RGA_ENGINE_HAZARD_RESPAWN_PASS")
            return
        end
        task.wait(0.2)
    end
    error("Character did not respawn within the test deadline")
end)
