-- Developer-only: run in the SERVER command bar of a fresh Play Solo session.
-- Never insert this test driver into a delivered or published game.
-- Teleporting exercises engine contacts; it does not test navigability.
task.spawn(function()
	local runService = game:GetService("RunService")
	assert(
		runService:IsStudio() and runService:IsRunning() and runService:IsServer(),
		"Use the server command bar during Studio Play Solo"
	)
	local players = game:GetService("Players"):GetPlayers()
	assert(#players == 1, "This driver requires exactly one test player")
	local player = players[1]
	local map = workspace["Roblox Game Architect"]["Rainforest Canopy Obby"]
	local collectibles = map.Collectible:GetChildren()
	table.sort(collectibles, function(left, right)
		return left.Name < right.Name
	end)
	assert(#collectibles == 3, "Expected the reference three-collectible map")
	assert(
		game:GetService("ServerScriptService"):FindFirstChild("RGA Treasure Hunt"),
		"Treasure Hunt server script is missing"
	)
	local stats = player:WaitForChild("leaderstats")
	local treasures = stats:WaitForChild("Treasures")
	local victories = stats:WaitForChild("Victories")
	assert(treasures.Value == 0 and victories.Value == 0, "Start a fresh test session")

	local function touch(part, expectedTreasures, expectedVictories)
		local character = assert(player.Character, "Character missing")
		local root = character:WaitForChild("HumanoidRootPart")
		assert(root:IsA("BasePart"), "HumanoidRootPart is not a BasePart")
		root.AssemblyLinearVelocity = Vector3.zero
		root.AssemblyAngularVelocity = Vector3.zero
		character:PivotTo(part.CFrame + Vector3.new(0, 12, 0))
		task.wait(0.2)
		-- Place the root inside the thin trigger. A +2 stud offset leaves the
		-- R15 collision parts above these low profile coins in Studio.
		character:PivotTo(part.CFrame)
		local minimumContactWait = os.clock() + 0.15
		local deadline = os.clock() + 4
		repeat
			task.wait(0.1)
		until (
				(treasures.Value == expectedTreasures and victories.Value == expectedVictories)
				and os.clock() >= minimumContactWait
			) or os.clock() >= deadline
		assert(
			treasures.Value == expectedTreasures and victories.Value == expectedVictories,
			"Treasure touch did not produce the expected player stats"
		)
	end

	local function touchDuringDebounce(part)
		local character = assert(player.Character, "Character missing")
		local root = character:WaitForChild("HumanoidRootPart")
		assert(root:IsA("BasePart"), "HumanoidRootPart is not a BasePart")
		root.AssemblyLinearVelocity = Vector3.zero
		root.AssemblyAngularVelocity = Vector3.zero
		character:PivotTo(part.CFrame + Vector3.new(0, 12, 0))
		task.wait(0.2)
		character:PivotTo(part.CFrame)
		task.wait(0.2)
		assert(
			treasures.Value == 0 and victories.Value == 1,
			"A touch during the round reset scored prematurely"
		)
	end

	for round = 1, 2 do
		for index, collectible in ipairs(collectibles) do
			print(
				"RGA_TREASURE_TOUCH_BEGIN",
				round,
				index,
				collectible.Name,
				treasures.Value,
				victories.Value
			)
			local expectedTreasures = index == #collectibles and 0 or index
			local expectedVictories = round - 1 + (index == #collectibles and 1 or 0)
			touch(collectible, expectedTreasures, expectedVictories)
			touch(collectible, expectedTreasures, expectedVictories)
			print("RGA_TREASURE_TOUCH_PASS", round, index, treasures.Value, victories.Value)
		end
		assert(
			treasures.Value == 0 and victories.Value == round,
			"A completed set must reset progress and award one victory"
		)
		print("RGA_TREASURE_ROUND_PASS", round, treasures.Value, victories.Value)
		if round == 1 then
			touchDuringDebounce(collectibles[1])
			task.wait(1.1)
		end
	end
	print("RGA_TREASURE_TWO_ROUNDS_PASS")
end)
