# Runbook: from "written" to "verified"

What remains between the repository and a working product is almost entirely
evidence that needs something this repository cannot supply: a Roblox test
universe, hosted servers, a model key, Lute, and Roblox Studio. This page lists
those steps in order, what each needs, and the proof to keep. Every step is
independent of code changes; if one fails, the failure is the finding.

Nothing here publishes to production. A step that writes to Roblox targets only
a dedicated test universe and place.

## 0. Prerequisites

- [ ] `rokit install` (installs pinned Lute 1.0.0, Rojo 7.7.1, selene, StyLua).
- [ ] `uv sync --locked --extra dev`, then `uv run pytest`. With Lute available the
      14 skipped tests run; **proof:** the full-suite line with no Lute skips.
- [ ] Push the branch to a **private** GitHub repository so CI runs the jobs that
      have never run (Windows sandbox limits, Blender and Roblox containers).
      **Proof:** one green run on the pushed commit.

## 1. The plugin in Roblox Studio (needs only Studio)

The plugin is one file, `apps/studio-plugin/src/Main.plugin.lua`.

- [ ] Copy it into Studio's local plugins folder and restart Studio. If the toolbar
      button does not appear, build the model instead (`apps/studio-plugin/README.md`).
- [ ] Run the local API (`python -m api.cli serve`), queue
      `tools/examples/create-platform.json`, approve it, fetch it in the plugin and
      click Apply. **Proof:** the part exists, Ctrl+Z removes it, and
      `python -m api.cli status` shows the item `closed` with knowledge `known`.
- [ ] Close Studio mid-apply. **Proof:** the lock engages and only
      `python -m api.cli attest` releases it.

This is the evidence that lets ADR-0011 move from `Proposed` to `Accepted`.

## 2. Hosted MCP services (needs a Linux host and DNS)

Follow `apps/remote/deploy/README.md`.

- [ ] `BLENDER_MCP_URL` and `BLENDER_MCP_BEARER_TOKEN` set, then
      `python tools/smoke_remote_blender_mcp.py`. **Proof:** it returns a GLB.
- [ ] `ROBLOX_MCP_URL` and `ROBLOX_MCP_BEARER_TOKEN` set, then
      `python tools/smoke_remote_roblox_mcp.py`. **Proof:** it returns a `.rbxlx`
      with its digest.
- [ ] Open that `.rbxlx` in Studio. **Proof:** the map loads and plays.

## 3. A real model (needs `ANTHROPIC_API_KEY` and a spend limit)

- [ ] Set `LLM_PROVIDER=anthropic`, `LLM_MODEL_ID=claude-sonnet-5-5` and a small
      `AGENT_MAX_USD_PER_SESSION`.
- [ ] `python tools/evaluate_worldbuilding.py`. **Proof:** the structural rubric
      results and the recorded spend, which must not exceed the limit.

## 4. Open Cloud validation (needs a dedicated test universe)

The gates are the acceptance criteria of
`docs/architecture/adr/0015-disposable-world-validation.md`.

- [ ] Provision an empty test universe and place, and a key scoped only to that
      universe and to Luau execution.
- [ ] Run `rga_validate_map` against a pinned place version.
      **Proof:** after the task, the place version and the production place are
      unchanged (the ADR requires this before relying on it).

Do not enable test-place publication or model upload until this step has passed.

## 5. What stays blocked

Executing model-written gameplay Luau, playtests through `playtest.request`, and
production publishing remain disabled. They need a separate decision and a
broader source policy than the scoped blockout subset
(`docs/safety.md`, section 8).
