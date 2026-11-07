# Rainforest Treasure Hunt

A reviewed Scene Recipe v3 example for building a jungle path with three touch collectibles and global Roblox Lighting/Atmosphere. Select the fixed `treasure_hunt` mode when compiling it; that mode adds a neutral start pad over the path and the repository-owned server script. The source recipe contains data only and no Luau.

Build a complete, script-reviewed Roblox place artifact with the repository-pinned Rojo version. The CLI refuses to overwrite an existing artifact unless you pass `--overwrite`:

```powershell
uv run python tools/build_roblox_place.py examples/worlds/rainforest-treasure-hunt/scene-recipe.json dist/rainforest-treasure-hunt.rbxlx --gameplay-mode treasure_hunt
```

This is a low-poly blockout recipe, not a finished visual asset or proof of a live Roblox playtest. On 2026-11-06, a 20,371-byte Rojo 7.7.1 build opened in Roblox Studio; a local one-player Play test spawned a character on the generated start pad with zero runtime errors and warnings. After that inspection, the builder was updated to set collectible `CanTouch` explicitly and rebuilt the current 20,515-byte artifact. That rebuilt file has not yet been reopened in Studio. Collecting every coin, completing the round, multiplayer behavior, mesh quality, and a live disposable-place test remain unverified. Review and exercise those before treating it as production-ready.
