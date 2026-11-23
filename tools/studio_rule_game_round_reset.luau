-- Developer-only: run in the SERVER command bar during Play Solo on a fresh
-- rule_game artifact whose Landmark awards one point and awards a win at one.
-- Never add this test driver to a delivered or published place.
task.spawn(function()
	local RunService = game:GetService("RunService")
	assert(
		RunService:IsStudio() and RunService:IsRunning() and RunService:IsServer(),
		"Use the server command bar during Studio Play Solo"
	)
	local Players = game:GetService("Players")
	local players = Players:GetPlayers()
	assert(#players == 1, "This driver requires exactly one test player")
	local player = players[1]
	local map = workspace["Roblox Game Architect"]["Rainforest Canopy Obby"]
	local landmarkFolder = map:WaitForChild("Landmark")
	local landmark = landmarkFolder:FindFirstChildWhichIsA("BasePart")
	assert(landmark and landmark.CanTouch, "A touchable scoring landmark is required")
	local spawnFolder = map:WaitForChild("RGA Spawn")
	local spawnPoint = spawnFolder:FindFirstChildWhichIsA("SpawnLocation")
	assert(spawnPoint, "A player spawn is required")

	local function moveTo(part)
		local character = assert(player.Character, "Character missing")
		character:PivotTo(part.CFrame + Vector3.new(0, part.Size.Y / 2 + 4, 0))
	end

	local function winsValue()
		local leaderstats = player:FindFirstChild("leaderstats")
		return leaderstats and leaderstats:FindFirstChild("Wins")
	end

	local function waitForWins(expected)
		local deadline = os.clock() + 5
		local wins
		repeat
			task.wait(0.1)
			wins = winsValue()
		until (wins and wins.Value >= expected) or os.clock() >= deadline
		assert(wins and wins.Value == expected, "Expected exactly " .. expected .. " wins")
	end

	moveTo(spawnPoint)
	task.wait(0.25)
	moveTo(landmark)
	waitForWins(1)
	local wins = assert(winsValue(), "Wins stat is missing")
	local points = player.leaderstats:FindFirstChild("Points")
	assert(points and points.Value == 0, "Winning did not reset points")

	moveTo(spawnPoint)
	task.wait(0.1)
	moveTo(landmark)
	task.wait(0.35)
	assert(wins.Value == 1, "Duplicate landmark contact awarded another win")
	assert(points.Value == 0, "Touch scoring was not paused during round reset")

	task.wait(0.7)
	moveTo(spawnPoint)
	task.wait(0.1)
	moveTo(landmark)
	waitForWins(2)
	assert(points.Value == 0, "Second win did not reset points")
	print("RGA_RULE_ROUND_RESET_ENGINE_PASS", wins.Value, points.Value)
end)
