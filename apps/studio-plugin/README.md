# apps/studio-plugin — the thin client

A Roblox Studio plugin that applies approved changes, runs playtests and reports
results back to the local API service.

**Status: not implemented.** Stage 5 on the [roadmap](../../README.md#roadmap).

## What it does — and what it must never do

This is the most privileged component in the system. A Studio plugin with HTTP
and script permissions can do very nearly anything in the user's session, and it
is the component the user will scrutinise least. So it is deliberately the one
with the least logic in it.

**It does:**

- report the state of the open place,
- apply validated, approved edits it is handed,
- run playtests and report output, errors and timings,
- confirm destructive actions in its own UI, at the moment of change.

**It must never:**

- hold an LLM API key, a prompt, or any agent decision logic
  ([ADR-0005](../../docs/architecture/adr/0005-credentials-and-thin-plugin.md)),
- publish to Roblox (invariant I5 — publishing is a human action, always),
- apply an edit that has not passed validation and approval.

It authenticates to the local API with `PLUGIN_AUTH_TOKEN` from `.env`, scoped to
the three operations above.

## Toolchain

| Tool | Purpose |
|---|---|
| Rojo | sync Luau source into Studio |
| selene | linting |
| StyLua | formatting (tabs, per `.editorconfig`) |
| TestEZ | Luau unit tests, in `tests/` |

Versions are pinned in [`aftman.toml`](../../aftman.toml) at the repository
root. Install them with `aftman install`.

## Layout

```
src/     Luau source — nothing here yet
tests/   TestEZ specs — nothing here yet
```

`default.project.json` will define the Rojo mapping once there is source to map.

## A note on place files

Never commit a `.rbxl`, `.rbxlx`, `.rbxm` or `.rbxmx`. They are binary,
multi-megabyte, and do not diff. `.gitignore` blocks them repository-wide
([ADR-0004](../../docs/architecture/adr/0004-generated-project-storage.md)). The
plugin is Luau text managed by Rojo; the place file is a local build artefact.
