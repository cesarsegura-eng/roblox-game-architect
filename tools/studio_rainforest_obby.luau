-- Developer-only: run in the SERVER command bar of a fresh Play Solo session.
-- Never insert this test driver into a delivered or published game.
-- PathfindingService checks route geometry; teleports do not test manual controls.
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
	local checkpoints = map:WaitForChild("RGA Checkpoints"):GetChildren()
	table.sort(checkpoints, function(left, right)
		return left.Name < right.Name
	end)
	assert(#checkpoints == 5, "Expected five ordered rainforest checkpoints")
	local stats = player:WaitForChild("leaderstats")
	local initialStage = stats.Stage.Value
	assert(
		(initialStage == 0 or initialStage == 1) and stats.Wins.Value == 0,
		"Start a fresh test session at the first checkpoint"
	)

	local function touch(part, succeeds, description, mustRemainUnchanged)
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

	touch(checkpoints[3], function()
		return stats.Stage.Value == initialStage
	end, "Out-of-order checkpoint advanced the stage", true)
	touch(checkpoints[1], function()
		return stats.Stage.Value == 1
	end, "First checkpoint did not start the route")
	touch(checkpoints[1], function()
		return stats.Stage.Value == 1
	end, "Duplicate checkpoint touch changed the stage", true)
	touch(checkpoints[3], function()
		return stats.Stage.Value == 1
	end, "Skipped checkpoint advanced the stage", true)
	touch(checkpoints[2], function()
		return stats.Stage.Value == 2
	end, "Second checkpoint did not advance the route")
	touch(checkpoints[2], function()
		return stats.Stage.Value == 2
	end, "Duplicate checkpoint touch changed the stage", true)
	for index = 3, #checkpoints do
		local expected = index
		if index == #checkpoints then
			touch(checkpoints[index], function()
				return stats.Wins.Value == 1
			end, "Final checkpoint did not award exactly one win")
		else
			touch(checkpoints[index], function()
				return stats.Stage.Value == expected
			end, "Ordered checkpoint did not advance the stage")
		end
	end
	local pathfinding = game:GetService("PathfindingService")
	for index = 2, #checkpoints do
		local path = pathfinding:CreatePath({
			AgentRadius = 2,
			AgentHeight = 5,
			AgentCanJump = true,
		})
		local ok = pcall(function()
			path:ComputeAsync(
				checkpoints[index - 1].Position + Vector3.new(0, 3, 0),
				checkpoints[index].Position + Vector3.new(0, 3, 0)
			)
		end)
		assert(
			ok and path.Status == Enum.PathStatus.Success and #path:GetWaypoints() > 0,
			string.format(
				"Roblox PathfindingService could not connect checkpoints %d and %d",
				index - 1,
				index
			)
		)
	end
	print("RGA_OBBY_NAVIGATION_PASS", #checkpoints - 1)
	assert(player.RespawnLocation == checkpoints[1], "Finish did not set the start respawn")
	assert(stats.Wins.Value == 1, "Finish awarded an incorrect win count")
	print("RGA_OBBY_SEQUENCE_FINISH_PASS", stats.Stage.Value, stats.Wins.Value)
	local stageAfterFinish = stats.Stage.Value
	touch(checkpoints[#checkpoints], function()
		return stats.Wins.Value == 1 and stats.Stage.Value == stageAfterFinish
	end, "Repeated finish changed route progress or awarded another win", true)

	local previousCharacter = player.Character
	local humanoid = assert(previousCharacter:FindFirstChildOfClass("Humanoid"), "Humanoid missing")
	local hazardFolder = map:WaitForChild("Hazard")
	local hazard = hazardFolder:FindFirstChildWhichIsA("BasePart")
	assert(hazard, "Expected an authored hazard part")
	local oldCharacter = previousCharacter
	touch(hazard, function()
		return humanoid.Health <= 0
	end, "Hazard did not eliminate the player")
	local deadline = os.clock() + 15
	while os.clock() < deadline do
		local character = player.Character
		local nextHumanoid = character and character:FindFirstChildOfClass("Humanoid")
		if character ~= oldCharacter and nextHumanoid and nextHumanoid.Health > 0 then
			assert(player.RespawnLocation == checkpoints[1], "Hazard respawn did not use the start")
			assert(stats.Wins.Value == 1, "Hazard respawn changed the win count")
			print("RGA_OBBY_HAZARD_RESPAWN_PASS")
			return
		end
		task.wait(0.2)
	end
	error("Character did not respawn within the test deadline")
end)
