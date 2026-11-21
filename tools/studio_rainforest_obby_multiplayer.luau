-- Developer-only: run in the SERVER command bar of a fresh two-player Studio session.
-- Never insert this test driver into a delivered or published game.
-- Character teleports exercise engine contacts; they do not test manual controls.
task.spawn(function()
	local RunService = game:GetService("RunService")
	assert(
		RunService:IsStudio() and RunService:IsRunning() and RunService:IsServer(),
		"Use the server command bar during a Studio multiplayer test"
	)
	local Players = game:GetService("Players")
	local players = Players:GetPlayers()
	table.sort(players, function(left, right)
		return left.UserId < right.UserId
	end)
	assert(#players == 2, "This driver requires exactly two test players")
	local map = workspace["Roblox Game Architect"]["Rainforest Canopy Obby"]
	local checkpoints = map:WaitForChild("RGA Checkpoints"):GetChildren()
	table.sort(checkpoints, function(left, right)
		return left.Name < right.Name
	end)
	assert(#checkpoints == 5, "Expected five ordered rainforest checkpoints")
	local firstPlayer, secondPlayer = players[1], players[2]
	local firstStats = firstPlayer:WaitForChild("leaderstats")
	local secondStats = secondPlayer:WaitForChild("leaderstats")
	assert(
		firstStats.Wins.Value == 0 and secondStats.Wins.Value == 0,
		"Start a fresh multiplayer test session"
	)

	local function touch(player, part, succeeds, description, mustRemainUnchanged)
		local character = assert(player.Character, "Character missing")
		local root = character:WaitForChild("HumanoidRootPart")
		assert(root:IsA("BasePart"), "HumanoidRootPart is not a BasePart")
		root.AssemblyLinearVelocity = Vector3.zero
		root.AssemblyAngularVelocity = Vector3.zero
		character:PivotTo(part.CFrame + Vector3.new(0, 8, 0))
		task.wait(0.25)
		character:PivotTo(part.CFrame + Vector3.new(0, 2, 0))
		if mustRemainUnchanged then
			task.wait(0.8)
		else
			local deadline = os.clock() + 4
			repeat
				task.wait(0.1)
			until succeeds() or os.clock() >= deadline
		end
		assert(succeeds(), description)
	end

	for _, player in players do
		touch(player, checkpoints[1], function()
			return player.leaderstats.Stage.Value == 1
		end, "Start checkpoint did not initialize player progress")
	end
	touch(firstPlayer, checkpoints[2], function()
		return firstStats.Stage.Value == 2
	end, "First player did not advance to checkpoint two")
	assert(secondStats.Stage.Value == 1, "First player's progress changed the second player")
	touch(secondPlayer, checkpoints[3], function()
		return secondStats.Stage.Value == 1
	end, "Second player's skipped checkpoint advanced progress", true)
	touch(secondPlayer, checkpoints[2], function()
		return secondStats.Stage.Value == 2
	end, "Second player did not advance independently")
	assert(firstStats.Stage.Value == 2, "Second player's progress changed the first player")

	for index = 3, #checkpoints do
		touch(firstPlayer, checkpoints[index], function()
			return index == #checkpoints and firstStats.Wins.Value == 1
				or index < #checkpoints and firstStats.Stage.Value == index
		end, "First player's route did not finish in order")
	end
	assert(
		firstStats.Wins.Value == 1 and secondStats.Wins.Value == 0,
		"First player's win was not isolated"
	)
	assert(secondStats.Stage.Value == 2, "First player's finish changed the second player's stage")
	local firstStageAfterFinish = firstStats.Stage.Value
	touch(firstPlayer, checkpoints[#checkpoints], function()
		return firstStats.Wins.Value == 1 and firstStats.Stage.Value == firstStageAfterFinish
	end, "Repeated finish changed the first player's state", true)

	for index = 3, #checkpoints do
		touch(secondPlayer, checkpoints[index], function()
			return index == #checkpoints and secondStats.Wins.Value == 1
				or index < #checkpoints and secondStats.Stage.Value == index
		end, "Second player's route did not finish in order")
	end
	assert(
		firstStats.Wins.Value == 1 and secondStats.Wins.Value == 1,
		"Players did not earn independent wins"
	)
	print("RGA_OBBY_MULTIPLAYER_PROGRESS_PASS", firstStats.Wins.Value, secondStats.Wins.Value)

	local hazard = map:WaitForChild("Hazard"):FindFirstChildWhichIsA("BasePart")
	assert(hazard, "Expected an authored hazard part")
	local function checkHazardRespawn(player, stats)
		local oldCharacter = assert(player.Character, "Character missing")
		local humanoid = assert(oldCharacter:FindFirstChildOfClass("Humanoid"), "Humanoid missing")
		local oldStage, oldWins = stats.Stage.Value, stats.Wins.Value
		touch(player, hazard, function()
			return humanoid.Health <= 0
		end, "Hazard did not eliminate player " .. player.Name)
		local deadline = os.clock() + 15
		while os.clock() < deadline do
			local character = player.Character
			local nextHumanoid = character and character:FindFirstChildOfClass("Humanoid")
			if character ~= oldCharacter and nextHumanoid and nextHumanoid.Health > 0 then
				assert(
					stats.Stage.Value == oldStage and stats.Wins.Value == oldWins,
					"Hazard respawn changed player stats"
				)
				assert(
					player.RespawnLocation == checkpoints[1],
					"Hazard respawn did not use the start"
				)
				return
			end
			task.wait(0.2)
		end
		error("Player " .. player.Name .. " did not respawn within the test deadline")
	end

	checkHazardRespawn(firstPlayer, firstStats)
	checkHazardRespawn(secondPlayer, secondStats)
	assert(
		firstStats.Wins.Value == 1 and secondStats.Wins.Value == 1,
		"Hazard respawn changed a player's win count"
	)
	print("RGA_OBBY_MULTIPLAYER_RESPAWN_PASS")
end)
