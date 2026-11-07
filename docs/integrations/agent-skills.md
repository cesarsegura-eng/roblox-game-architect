# Give any existing agent the RGA skills

Roblox Game Architect is built to add capabilities to the agent a user already
uses. The user needs Roblox Studio, where the game is made, and nothing else:
the product does not require Blender, an RGA extension, or an RGA server on
their computer. Domain instructions are
plain `SKILL.md` files, and authoring tools are separate, authenticated MCP
services hosted remotely.

## Read the guides through MCP

On the authenticated Roblox endpoint, call `resources/list` and read
`rga://skills/roblox-game-architect` first. Pick the domain guides from the
returned list as needed. The server also serves the JSON contracts at
`rga://schemas/game-plan-v2` and `rga://schemas/scene-recipe-v3`. An agent
with MCP resource support can read all eight resources directly over HTTPS.

## Optional portable knowledge pack

The `skills/` directory contains six portable skills: one coordinator and five
domain guides for game planning, environments, Blender authoring, Roblox map
blockouts, and character modeling and motion. Each skill uses the common
`SKILL.md` frontmatter format; references remain inside that skill's folder.
Agents that support skills can load the directory directly. To hand the pack to
another compatible agent, create a deterministic archive:

```sh
python tools/package_agent_skills.py
python tools/package_agent_skills.py --check
python tools/package_agent_skills.py --archive /path/to/rga-agent-skills.zip
```

Extract the archive into the agent's configured skills directory, preserving
the six folder names. This installs instruction files only. It does not install
applications, execute project code, or start a local server. The canonical
skill source for all six guides is `packages/core/skillpacks/`.

## Connect remote tools

Configure the agent's MCP client to connect to the separately hosted RGA
Blender and Roblox Streamable HTTP services. MCP clients use different
configuration formats, so follow the agent vendor's instructions for adding an
HTTP MCP endpoint and its authorization header. Use distinct operator-issued
tokens, keep them in the client's secret store or environment, and never put
them in the skill pack or project files. Keep per-call approval prompts enabled
for persistent Roblox asset creation or test-place publishing.

After connecting, confirm the agent can discover `rga_apply_scene_recipe` on
the Blender service and `rga_build_place` / `rga_validate_map` on the Roblox
service. Optional tools appear only when the remote operator configured them.
The Roblox service can fetch a Blender artifact directly from the fixed Blender
host; the generated GLB does not need to pass through the user's computer or
agent context. A downloadable place artifact does not mean a live place was
changed or that gameplay was playtested.

See the [remote service architecture](remote-application-architecture.md),
[Blender deployment guide](blender-remote-mcp.md), and
[Codex-specific connection example](roblox-game-architect-codex.md) for the
service side and a client-specific example.
