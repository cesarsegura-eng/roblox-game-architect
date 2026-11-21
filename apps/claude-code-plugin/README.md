# Claude Code plugin

This optional plugin packages the nine RGA skills and configures the
separately hosted Blender MCP service. Roblox Studio work uses Claude Code's
already configured native Studio MCP. The plugin does not add a Roblox MCP
connection, bundle executables, install Blender, or start a local service.

## Configure

The plugin asks for the remote Blender MCP hostname and bearer token when
you install or enable it through Claude Code's interactive `/plugin` interface.
Enter only the hostname (for example, `blender.example.com`); the plugin fixes
the URL scheme to HTTPS and the route to `/mcp`, so the bearer token is never
sent to a plaintext HTTP endpoint.
The token is declared as sensitive user configuration, so Claude Code stores it
in its secure credential store. Obtain the endpoint and token from the RGA
Blender service operator. The plugin leaves the native Roblox Studio MCP
configuration untouched. Do not put credentials in project files.

Read [Privacy](PRIVACY.md) before connecting. The notice explains what is sent
to the configured Blender MCP host.

The project skills are synchronized from `packages/core/skillpacks/` with:

```sh
python tools/package_agent_skills.py
python tools/package_agent_skills.py --check
```

## Install from the project marketplace

Once this marketplace manifest is available from GitHub, add it to Claude Code
and install the plugin inside an interactive session:

```sh
claude plugin marketplace add cesarsegura-eng/roblox-game-architect
claude
```

Then run this in the Claude Code session:

```text
/plugin install rga-game-architect@roblox-game-architect-tools
```

The interactive install asks for the Blender hostname and credential. If you
installed the plugin with `claude plugin install`, run
`/plugin configure rga-game-architect@roblox-game-architect-tools` in a session
to enter them. Verify the RGA Blender tools in `/mcp`; leave the native Studio
server entry unchanged.

## Try the plugin from this checkout

From the repository root, run:

```sh
claude --plugin-dir apps/claude-code-plugin
```

In the resulting session, run `/plugin configure rga-game-architect` to enter
the Blender hostname and credential. Loading with `--plugin-dir` does not open
the configuration dialog automatically. Use the existing native Studio MCP
for Roblox work; do not delete, rename, proxy, or route it through RGA.

Plugin skills are namespaced under `/rga-game-architect:`. Start with the
coordinator skill, then load the dedicated planning, environment, Blender,
map-blockout, or character skill as needed. The Claude plugin packages the
guides locally as skill files; no Roblox MCP server is needed to read them.

Follow the native Studio tools' own target restrictions and approval flow.
Review generated assets before import, and do not claim an edit or playtest
succeeded without evidence from the corresponding Studio tool result.

## Validate before release

With Claude Code installed, validate both manifests using its official CLI:

```sh
claude plugin validate apps/claude-code-plugin --strict
claude plugin validate . --strict
```

These commands check the plugin and marketplace structure. They do not prove
that a hosted Blender endpoint is reachable or that a live MCP session works;
verify those separately with a service URL and credential from the operator.
See Claude Code's [plugin validation guide](https://code.claude.com/docs/en/plugins/create#test-and-debug)
and [marketplace validation guide](https://code.claude.com/docs/en/plugin-marketplaces#validate-and-test).
