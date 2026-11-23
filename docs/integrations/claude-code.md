# Give Claude Code the RGA skills and Blender tools

Roblox Game Architect equips Claude Code with domain skills and remote Blender
authoring. Roblox Studio work uses the native Studio MCP connection the user
already configured. This setup does not add a second Roblox MCP connection,
replace or proxy the native one, install Blender, or start an RGA service on the
user's computer.

## Configure remote Blender MCP

Obtain an HTTPS `/mcp` URL and a distinct bearer token from the RGA Blender
service operator. Store the token in Claude Code's sensitive plugin
configuration or a secret manager. Do not commit credentials or paste them
into skills.

For a manual `.mcp.json` configuration, add only the Blender entry to the
configuration Claude Code already uses; leave the native Studio entry intact:

```json
{
  "mcpServers": {
    "rga-blender": {
      "type": "http",
      "url": "https://<BLENDER_DOMAIN>/mcp",
      "headers": {
        "Authorization": "Bearer ${RGA_BLENDER_MCP_TOKEN}"
      }
    }
  }
}
```

Use project scope only when teammates should share the Blender endpoint; use
user scope for a personal host. Project-scoped servers require trust and
approval in an interactive Claude Code session. Verify the Blender tools with
`claude mcp list` and `/mcp`. This service credential is independent of the
model provider credential.

## Install the skill plugin

The repository's Claude Code plugin packages nine RGA skills and configures the
single Blender MCP endpoint. It does not configure a Roblox endpoint. Add the
marketplace and start an interactive session:

```sh
claude plugin marketplace add cesarsegura-eng/roblox-game-architect
claude
```

Then install the plugin in the Claude Code session:

```text
/plugin install rga-game-architect@roblox-game-architect-tools
```

The interactive install asks for the Blender host name and bearer token. Enter
the host only, such as `blender.example.com`; the plugin fixes the connection
to `https://<host>/mcp`. This prevents the bearer token from being configured
for a plaintext HTTP URL. If the
plugin was installed with `claude plugin install`, run
`/plugin configure rga-game-architect@roblox-game-architect-tools` in a session
to enter them. For checkout development, run
`claude --plugin-dir apps/claude-code-plugin`, then
`/plugin configure rga-game-architect`. Loading with `--plugin-dir` alone does
not open the configuration dialog.

Verify the Blender tools in `/mcp`, and confirm the user's existing native
Roblox Studio MCP connection remains present and unchanged. Use that native
connection for direct Roblox work within its tool descriptions, approval rules,
and test-place safeguards. Do not install this project's optional Studio
compatibility plugin to get Studio access. Roblox's Studio MCP targets open
Studio sessions and identifies them with `studio_id`; before making changes,
inspect the connected instances and select the intended place. See the
[official Studio MCP guide](https://create.roblox.com/docs/studio/mcp) for its
current setup and tool contract.

## Portable skills

The skills are also text files under `skills/`; install them into the agent's
skills directory if the plugin is not being used. The Claude plugin already
packages the nine guides locally, so they do not depend on an RGA Roblox MCP
resource endpoint. The guides cover game planning, UI/UX, biomes and playable
spaces, bounded Roblox Terrain and visual/audio effects through the existing
native Studio MCP, Blender scene authoring, Roblox blockouts, and character
modeling and animation.

Use the remote Blender MCP for bounded scene authoring. Use the native Studio
MCP for direct Roblox operations when available. A generated recipe, GLB, or
place file is not evidence that the open Studio place was changed, tested, or
made production-ready; report only actions supported by tool results.

If the Blender service operator sets `BLENDER_MCP_PUBLIC_ORIGIN`, a recipe
receipt includes a signed download link for the generated GLB that expires in
15 minutes. Download only that model file into a folder the user has approved
for Studio MCP uploads. After review and explicit approval, use the existing
Studio MCP `open_cloud_invoke` asset upload flow; do not add another Roblox MCP
endpoint. Roblox currently limits Open Cloud asset uploads to 20 MB per file.
The `open_cloud_invoke` path also requires the selected Studio place to belong
to a published experience with the required per-game asset permissions; an
unpublished local `.rbxlx` cannot grant them. Use only a dedicated test
experience for this handoff. If one is unavailable, keep the verified GLB as a
local artifact and leave upload, moderation, and import pending.
Keep the signed URL out of logs and do not use the path for larger GLBs. See
Roblox's [Studio Open Cloud guide](https://create.roblox.com/docs/studio/mcp-open-cloud)
and [asset usage guide](https://create.roblox.com/docs/cloud/guides/usage-assets).

For Blender deployment, see the [remote Blender guide](blender-remote-mcp.md)
and [service architecture](remote-application-architecture.md). The
[agent-neutral skill guide](agent-skills.md) covers other compatible agents.

## Official Claude Code references

- [Connect Claude Code to tools via MCP](https://code.claude.com/docs/en/mcp)
- [Claude Code skills](https://code.claude.com/docs/en/skills)
- [Claude Code plugins](https://code.claude.com/docs/en/plugins)
- [Claude Code plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
