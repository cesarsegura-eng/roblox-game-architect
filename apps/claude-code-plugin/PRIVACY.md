# Privacy and data handling

Last updated: 2026-11-07

The Roblox Game Architect Claude Code plugin contains local skill instructions
and configuration for one separately operated RGA Blender MCP endpoint. It
does not configure or operate a Roblox MCP endpoint. Roblox Studio access stays
in the user's existing native Studio MCP configuration, outside this plugin.

## Data sent to the Blender MCP service

When Claude Code invokes an RGA Blender tool, the tool arguments and any
referenced scene recipe or generated artifact needed for that operation are
sent to the HTTPS endpoint configured by the user. The endpoint receives its
configured bearer token. The plugin does not automatically send every
conversation to RGA; data is transmitted when a configured RGA Blender tool is
called. Claude Code and the model provider may process conversation content
under their own terms and privacy practices.

## Credentials and service operators

The Blender endpoint URL and bearer token are user-supplied plugin
configuration. Use only an endpoint operated by a provider you trust. Its
operator controls hosting, access logs, retention, backups, subprocessors, and
incident response. This repository does not establish those practices.
Review the operator's privacy terms before connecting. Do not send personal,
confidential, or otherwise sensitive information unless the operator is
authorized to receive it.

The native Roblox Studio MCP has its own configuration, operator, permissions,
and privacy terms. This plugin neither changes those settings nor routes Studio
data through the RGA Blender service.
