-- Developer-only: run in the SERVER command bar during Play Solo on a fresh
-- rainforest rule_game artifact built from gameplay-rules.json.
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
	local collectibleFolder = map:WaitForChild("Collectible")
	local collectible = collectibleFolder:FindFirstChildWhichIsA("BasePart")
	assert(collectible and collectible.CanTouch, "A touchable speed boost collectible is required")
	local character = assert(player.Character, "Character missing")
	local humanoid = character:WaitForChild("Humanoid")
	local originalSpeed = humanoid.WalkSpeed
	character:PivotTo(collectible.CFrame + Vector3.new(0, 2, 0))

	local boosted = false
	local deadline = os.clock() + 5
	repeat
		task.wait(0.1)
		boosted = humanoid.WalkSpeed > originalSpeed
	until boosted or os.clock() >= deadline
	assert(boosted, "Touching the collectible did not increase WalkSpeed")
	assert(humanoid.WalkSpeed <= 32, "Speed boost exceeded the fixed speed ceiling")
	print("RGA_SPEED_BOOST_APPLIED", originalSpeed, humanoid.WalkSpeed)

	local duration = 12
	local restoreDeadline = os.clock() + duration + 3
	repeat
		task.wait(0.1)
	until humanoid.WalkSpeed == originalSpeed or os.clock() >= restoreDeadline
	assert(humanoid.WalkSpeed == originalSpeed, "Speed boost did not restore the original speed")
	print("RGA_SPEED_BOOST_RESTORED", humanoid.WalkSpeed)
end)
