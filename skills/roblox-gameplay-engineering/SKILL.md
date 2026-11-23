---
name: roblox-gameplay-engineering
description: Design, author, secure, and validate Roblox gameplay systems through the user's existing Roblox Studio tools.
---

# Roblox gameplay engineering

Use this skill when a request requires custom Luau gameplay, server/client
architecture, player data, multiplayer, rounds, progression, or live-service
behavior. The product equips the agent with engineering guidance; it does not
install a second Roblox integration. For Claude Code, use the user's existing
native Studio MCP and leave its ownership and configuration intact. Do not
route gameplay edits through the optional RGA Roblox service: that service
accepts fixed schemas and does not execute caller-provided source.

## Establish the target and acceptance criteria

1. Read the current Game Plan, its included and deferred systems, and the
   production-readiness checklist. Identify player actions, authoritative
   outcomes, device/input targets, data lifetime, player count, abuse cases,
   and observable pass conditions before writing scripts.
2. Discover the existing Studio MCP tools. Select the intended open instance by
   its `studio_id`; verify place identity and inspect scripts and hierarchy
   before editing. Use only operations documented by the connected MCP.
   When its `skill` tool is available, retrieve current Roblox debugging,
   playtest, or server-scripting guidance for the feature; use `http_get` to
   check engine APIs that may have changed. Verify each connected tool's live
   schema instead of assuming every documented operation is available.
3. Make changes in an isolated test place or test copy. If no safe target exists,
   keep the implementation as a reviewable plan or patch until the owner
   supplies one. A native Studio MCP tool call is not a sandbox.
4. Turn each feature into a short contract: who may request it, which server
   state changes, valid inputs, rate and resource limits, failure behavior,
   client feedback, and automated or manual evidence.

## Build from a server-authoritative design

- Keep decisions and secrets on the server: currency, inventory, health,
  damage, rewards, checkpoints, purchases, win conditions, and saved progress.
  Clients send intent and display replicated results; they do not send a claimed
  result for the server to accept.
- Keep server logic in `ServerScriptService` or `ServerStorage`. Put only
  required remotes and non-secret shared modules in replicated containers.
  Keep LocalScripts focused on input, camera, animation presentation, and UI.
- Give each stateful system a small service boundary and explicit state
  transitions. Do not let a UI script become the source of game state or make
  unrelated scripts mutate the same profile independently.
- Choose `RemoteEvent` for asynchronous requests and notifications. Use
  `RemoteFunction` only when the request must synchronously return a bounded
  result; do not yield for DataStore or other slow work inside a remote callback.
- Validate every client request on the server: exact value types and shapes,
  string/table size, numeric finiteness and range, permission, current character
  and game state, server-measured distance, cooldown, and per-player rate limit
  as applicable. Reject unknown fields and unknown action names. Bound work per
  call; make repeated touches and retries idempotent where rewards or spending
  are involved.
- Treat `Touched`, prompts, client-reported positions, and client cooldowns as
  requests that still require server checks. Use server-owned state to determine
  whether a reward or transition is valid.

## Implement the data and multiplayer lifecycle

- For a round-based game, use a server-owned state machine (for example
  `Waiting`, `Intermission`, `Active`, `Resolving`). Define legal transitions,
  timeouts, disconnect behavior, late-join policy, reset behavior, and exactly
  when rewards are granted. Ensure one player cannot resolve the same round
  twice.
- For inventories, quests, abilities, shops, and progression, define one
  server-side owner for each state and explicit request/response contracts.
  Validate ownership, availability, distance, price, cooldowns, and game phase
  before mutation. Keep client UI updates as consequences of committed state.
- If progress persists, use a versioned schema and stable user ID key. Define
  defaults, corrupt-data behavior, migrations, session ownership, shutdown
  handling, and recovery before implementing writes. Use `UpdateAsync` when an
  update depends on current data or may race across servers. Wrap requests in
  `pcall`, serialize writes per key, and use bounded retries with exponential
  backoff and jitter for transient errors. Never replace unreadable data with a
  blank profile or treat a failed write as proof that the backend did not write.
- Keep purchases and grants server-authoritative. Make receipt processing
  idempotent, persist fulfillment state, handle retries, and verify current
  eligibility/policy for the requested purchase before enabling commerce.
- If a system is explicitly deferred, keep it out of the playable slice and
  describe the limitation. Do not imply that session-only wins are saved.

## Validate the implementation in Studio

1. Inspect server and client code separately. Check that state-changing paths
   have server validation, bounded remotes, cleanup for departing players, and
   predictable recovery from invalid or unavailable services.
2. Run the requested test copy with separate server and client simulations.
   Exercise the normal path, duplicate requests, malformed inputs, spam,
   out-of-range requests, deaths/respawns, player joins and leaves, late joins,
   simultaneous rewards, and round reset. Use Studio's multi-client mode for
   multiplayer behavior; Play Solo does not prove multiplayer correctness.
3. When the game saves data, use a separate test experience or isolated data
   scope. Test failed reads/writes, migration, duplicate receipt delivery,
   concurrent servers, and recovery without touching production player data.
4. Test target device and input profiles, complete sessions, performance, and
   UI states. Keep server output, test setup, place version, and reproducible
   results with the review.
5. Report code edits, tests, and unresolved production gates separately. A
   passing static check is not an engine test; a Studio test is not a
   multi-device release test. Obtain the required human review before public
   publishing.

Read `references/server-systems.md` for implementation patterns and official
Creator Hub sources. Use `game-design-planning` for production scope,
`roblox-studio-map-blockouts` for safe map work, and the Game Architect skill
for the end-to-end workflow.
