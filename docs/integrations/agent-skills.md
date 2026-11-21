# Give any existing agent the RGA skills

Roblox Game Architect adds domain skills and remote tools to the agent a user
already runs. The product does not require Blender, an RGA extension, or an RGA
server on the user's computer. Roblox Studio is used to inspect, edit, and play
returned places; remote builds do not require Studio. Domain instructions are
plain `SKILL.md` files, and authoring tools are separate, authenticated MCP
services hosted remotely.

The RGA build service can return a complete `.rbxlx` without a local Studio
installation. When the user's agent already has Roblox Studio's native MCP,
that connection is the direct path to the open place for user-requested
creation, edits, inspection, and playtesting, within its documented tools and
safeguards. Preserve it; portable skills do not install, replace, or proxy it.
RGA's remote Roblox MCP remains a separate service for validated recipe
artifacts and its configured fixed-harness checks. It does not control Studio
or create another Studio connection.

## Read the guides through MCP

If an agent environment already has the separate RGA Roblox MCP service
configured, call `resources/list` and read
`rga://skills/roblox-game-architect` first. The service also serves JSON
contracts at `rga://schemas/game-plan-v2` and
`rga://schemas/scene-recipe-v3`. This is optional: portable skill files include
the guides, and the Claude Code plugin does not add a Roblox MCP connection just
to read them.

## Optional portable knowledge pack

The `skills/` directory contains nine portable skills: one coordinator and eight
domain guides for game planning, server gameplay engineering, UI/UX,
environments, native Roblox Terrain, Blender authoring, Roblox map blockouts,
and character modeling and motion. Each skill uses the common `SKILL.md`
frontmatter format. The deterministic archive bundles referenced schemas and
the authoritative research-source index with the planning, environment,
Blender, and character skills, so those guides remain usable outside the source
checkout. When researching a real region, agents should use their available web
search tools for local sources, cite the design claims, and label details they
cannot verify. Agents that support skills can load the directory directly. To
hand the pack to another compatible agent, create a deterministic archive:

```sh
python tools/package_agent_skills.py
python tools/package_agent_skills.py --check
python tools/package_agent_skills.py --archive /path/to/rga-agent-skills.zip
```

Extract the archive into the agent's configured skills directory, preserving
the nine folder names. This installs instruction files only. It does not install
applications, execute project code, or start a local server. The canonical
skill source for all nine guides is `packages/core/skillpacks/`.

## Connect remote tools

Configure the agent's MCP client for the separately hosted RGA Blender
Streamable HTTP service. For Claude Code, keep the existing native Roblox
Studio MCP connection and do not add an RGA Roblox endpoint. Other agent
environments may use the separate RGA Roblox artifact service if their operator
has already configured it and the agent needs its fixed-build tools. Follow
the agent vendor's setup instructions and store operator-issued tokens in a
secret manager, never in the skill pack or project files. Persistent Roblox
operations must follow the approval flow of the tool that performs them.

After connecting Blender, confirm the agent can discover
`rga_apply_scene_recipe`. Other compatible agent deployments can optionally
use `rga_build_place` / `rga_validate_map` when their operator already exposes
the separate RGA Roblox service; these tools build separate artifacts and do
not control Studio. A downloadable place artifact does not mean the open Studio
place changed or gameplay was playtested.

The `roblox-terrain-authoring` skill uses the user's existing native Studio MCP
and Roblox's `Terrain` API for bounded voxel authoring. It does not add another
Roblox endpoint; use a disposable copy or an explicitly reviewed region before
running edits in the open place.

See the [remote service architecture](remote-application-architecture.md),
[Blender deployment guide](blender-remote-mcp.md), and
[Claude Code connection guide](claude-code.md),
[Codex-specific connection example](roblox-game-architect-codex.md), and the
remote deployment guide for setup and client-specific examples.
