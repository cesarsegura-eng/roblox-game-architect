# Give an existing agent RGA knowledge and tools

Roblox Game Architect is designed to equip an agent the user already has with
domain skills and remote authoring tools. The end user's computer does not need
Blender, Roblox Studio, either application extension, this repository, or an
RGA MCP process installed. Run MCP services on separately hosted servers and
connect the agent to their HTTPS endpoints. The API/operator web application
is an optional orchestration and review surface; it is not the only intended
way for an agent to use the fixed MCP tools.

The repository's five domain skillpacks and one coordinator skill are published
as six portable Codex skills under `skills/`. Keep
`packages/core/skillpacks/` as the canonical source for all six guides;
`python tools/package_agent_skills.py` refreshes those portable copies, and
`python tools/package_agent_skills.py --check` verifies they have not drifted.
The Roblox MCP also serves the guides through `resources/list` and
`resources/read`. Start at `rga://skills/roblox-game-architect`. To load the
pack into an agent, add or copy the skill folders to that agent's skill
directory; this installs instructions only, not Blender, Studio, or a local
MCP process.

## Connect Codex to the hosted MCP services

First deploy the remote services and obtain their HTTPS MCP URLs and unique
bearer tokens from the service operator. Do not put tokens in this repository,
the skill files, screenshots, or chat. Codex desktop, CLI, and IDE extension
share their MCP configuration. In Codex desktop, open **Settings → MCP servers
→ Add server**, choose **Streamable HTTP**, enter each URL and credential, then
restart and confirm both servers appear under `/mcp`.

For a Codex `config.toml`, the equivalent server entries are:

```toml
[mcp_servers.rga_blender]
url = "https://<blender-host>/mcp"
bearer_token_env_var = "RGA_BLENDER_MCP_TOKEN"
default_tools_approval_mode = "prompt"

[mcp_servers.rga_roblox]
url = "https://<roblox-host>/mcp"
bearer_token_env_var = "RGA_ROBLOX_MCP_TOKEN"
default_tools_approval_mode = "prompt"
```

Keep `default_tools_approval_mode = "prompt"` for the Roblox server: its
digest-bound model-upload tool creates a persistent Roblox asset. Do not change
the upload tools to automatic approval for unattended agent runs.

Set the two environment variables in the environment used to launch the Codex
client. Use distinct tokens. The Roblox service exposes `rga_build_place` and
`rga_validate_map` when configured; persistent model-upload and test-place
publishing tools are hidden unless separately enabled on the server. Keep tool
approval prompting enabled. Never copy the example hostnames or put placeholder
values in the actual Codex configuration.

After connecting, ask the agent to list the RGA tools before making a scene.
Start with a script-free place build and inspect the returned artifact. For a
Blender mesh, `rga_apply_scene_recipe` returns an artifact ID. If the Roblox
service has its fixed Blender source and asset-upload settings enabled, call
`rga_prepare_blender_model_upload` with that ID, show the recipe and digest, and
wait for the user's explicit approval before calling
`rga_upload_prepared_blender_model` with its exact confirmation phrase. Then
pass the moderation-approved asset ID to `rga_build_place`. The GLB bytes travel
directly between the two MCP hosts; they do not pass through the user's agent or
computer. If these optional tools are absent, only the script-free recipe
blockout, fixed Obby Course and Treasure Hunt templates, and bounded `rule_game`
touch rules remain available through direct MCP without model-asset upload.

A build does not update a live place. Use a configured disposable Roblox test
place only for validation. When direct test-place publishing is configured,
the agent may call `rga_prepare_test_place_publication` with the exact build
request ID and digest. Show the returned build summary, digest, fixed target,
expiry, and phrase; wait for explicit user approval; then call
`rga_publish_prepared_test_place` with those exact values. Keep the MCP
client's per-call approval prompt enabled. Never use the compatibility
`rga_publish_reviewed_place` operation from an agent. This path is limited to
the isolated test place; production publishing remains disabled.

See the official [Codex MCP connection guide](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
for the current desktop setup, shared configuration, Streamable HTTP, and
`bearer_token_env_var` behavior. This repository's service deployment steps
and required credentials are documented in the
[remote Blender guide](blender-remote-mcp.md) and
[`apps/roblox_mcp_server/README.md`](../../apps/roblox_mcp_server/README.md).
