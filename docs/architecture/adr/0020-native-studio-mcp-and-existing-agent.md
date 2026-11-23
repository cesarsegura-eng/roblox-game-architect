# ADR-0020: Use the user's native Roblox Studio MCP

- **Status:** Accepted
- **Date:** 2026-11-07
- **Deciders:** project owner

## Context

The project equips an agent the user already runs with Roblox skills and
authoring tools. Claude Code already has a native Roblox Studio MCP connection
that operates on the user's open Studio session. Adding an RGA Roblox MCP entry
to the Claude plugin creates a second Roblox integration and duplicates part
of the user's existing workflow. The user also requires that Blender and other
authoring applications run through remote services rather than requiring local
installation.

The repository's RGA Roblox MCP is a separate server-side artifact builder and
fixed validator. It does not control the user's open Studio session. It can
remain useful to other compatible agent deployments, but it is not needed to
connect Claude Code to Roblox Studio.

## Decision

1. The Claude Code plugin packages the RGA domain skills and configures only the
   separately hosted Blender MCP service. It does not register `rga-roblox` or
   ask for a Roblox MCP URL or token.
2. For direct Roblox creation, editing, inspection, and playtesting, the agent
   uses the user's existing native Studio MCP when its documented tools support
   the requested action. It leaves that connection's configuration and
   ownership untouched and does not proxy it through RGA.
3. The RGA Roblox MCP remains an optional, separate artifact-building and
   fixed-validation service. Use it only in an agent environment where an
   operator has already exposed it; the Claude plugin and its setup guide do not
   instruct users to add it.
4. The local RGA Studio plugin remains an optional compatibility path for the
   local operator API. It is not a prerequisite for the native Studio MCP or
   the remote Blender workflow.
5. Native Studio tools are not assumed to be an execution sandbox. Follow their
   tool contracts, user approvals, target restrictions, and test-copy rules;
   report a change or playtest only when the tool result provides evidence.

## Consequences

- Claude Code users configure one remote authoring endpoint for Blender and
  preserve their existing Roblox Studio MCP connection.
- The portable skills remain agent-neutral. They distinguish direct operations
  in the native Studio session from RGA's separate remote place artifacts.
- A Roblox Studio connection is needed only for work performed in Studio. A
  remote RGA artifact can still be generated without installing Studio or
  Blender on the user's computer.
- Live validation remains dependent on an available Studio MCP or a separately
  configured disposable-place validator. This decision does not certify either
  integration or make arbitrary generated Luau safe.

## References

- [Claude Code integration guide](../../integrations/claude-code.md)
- [Agent-neutral skills guide](../../integrations/agent-skills.md)
- [Remote application architecture](../../integrations/remote-application-architecture.md)
- [Roblox Studio MCP documentation](https://create.roblox.com/docs/studio/mcp)
