# Rainforest Treasure Hunt

A reviewed Scene Recipe v3 example for building a jungle path with three touch collectibles and global Roblox Lighting/Atmosphere. Select the fixed `treasure_hunt` mode when compiling it; that mode adds a neutral start pad over the path and the repository-owned server script. The source recipe contains data only and no Luau.

Build a complete, script-reviewed Roblox place artifact with the repository-pinned Rojo version. The CLI refuses to overwrite an existing artifact unless you pass `--overwrite`:

```powershell
uv run python tools/build_roblox_place.py examples/worlds/rainforest-treasure-hunt/scene-recipe.json dist/rainforest-treasure-hunt.rbxlx --gameplay-mode treasure_hunt
uv run python tools/check_rainforest_treasure_hunt.py dist/rainforest-treasure-hunt.rbxlx --recipe examples/worlds/rainforest-treasure-hunt/scene-recipe.json
```

This is a low-poly blockout recipe, not a finished visual asset or proof of a live Roblox playtest. On 2026-11-07, the 28,266-byte artifact `dist/rainforest-treasure-continued.rbxlx` opened in Studio and passed the server-side Play Solo driver. Output confirmed three pickups, duplicate-contact idempotency, the reset debounce, and two completed rounds (`RGA_TREASURE_ROUND_PASS 1 0 1`, `RGA_TREASURE_ROUND_PASS 2 0 2`, `RGA_TREASURE_TWO_ROUNDS_PASS`). The driver teleports the player into each pickup, so it verifies engine touch handling but not manual walking/navigation, multiplayer, persistence, or live-server behavior. SHA-256: `05F3BDACE227E12324AA07C4D6BEB8362A2D5E9982F1F4230BEF72AEB26FF93F`. Mesh quality and a live disposable-place test remain unverified; review and exercise those before treating it as production-ready.
