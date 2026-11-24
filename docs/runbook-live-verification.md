# Runbook: from "written" to "verified"

The repository contains working prototypes, but is not yet an end-to-end
production game builder. Some gaps need implementation (especially general
gameplay execution and production gates); others need external infrastructure
that this checkout cannot supply: a Roblox test universe, hosted servers, and
scoped keys. This page records the external verification work and its evidence.
Passing these checks does not by itself complete the remaining implementation
roadmap.

Nothing here publishes to production. A step that writes to Roblox targets only
a dedicated test universe and place.

## 0. Prerequisites

- [x] Local developer toolchain installed under ignored `.tools/` with pinned
      Lute 1.0.0, Rojo 7.7.1, selene 0.32.0, and StyLua 2.6.0. This is only for
      validating this checkout; end-user workflows do not require these local
      executables or a locally installed Blender.
- [x] Selene 0.32.0 uses the checked-in Roblox standard library in
      `roblox.yml` (`775,923` bytes; SHA-256
      `107d8b0208909a331ddd54e33401e945467535782db43b0127c54b36a1fa225a`).
      The library was generated from Selene's official Roblox API source, then
      pinned in `selene.toml`; lint passed offline with zero errors, warnings,
      or parse errors across the Studio plugin and fixed gameplay drivers.
      Regenerate only as an intentional engine-baseline update and review the
      library diff.
- [x] StyLua authored-source check passed; generated `Protocol/Schemas.lua` is
      checked byte-for-byte against the protocol contract instead.
- [x] Rojo 7.7.1 built `dist/rga-studio-plugin.rbxmx`; the output contains the
      required plugin RunContext token.
- [x] `uv lock --check --offline` passed with uv 0.13.6 (`Resolved 17 packages
      in 40ms`); the lockfile matches the current project metadata.
- [x] `uv sync --locked --extra dev` passed in a fresh `.tmp/clean-venv` on
      Python 3.11.9, installing the project and 16 locked dependencies.
- [x] The latest full suite passed locally: `1,654 passed` with no skips,
      loopback access enabled, and the pinned Lute binary ahead of the
      working-directory-sensitive Rokit shims on `PATH`. Hosted CI still needs
      a green run on this tree.
- [x] Run CI on the branch so the jobs that had never run anywhere do run:
      Windows sandbox limits, the Blender container and the Roblox container.
      **Proof:** [run 12](https://github.com/cesarsegura-eng/roblox-game-architect/actions/runs/45229635041) on commit `3a9aef7`, every job green, including
      the Blender Compose build and smoke and the fixed-template place build.
      The branch went to the project's own **public** repository rather than a
      private one, after a scan found no `.env`, no credential pattern in the
      diff, and `.gitleaks.toml` reporting clean.
- [ ] Before publishing the Claude Code marketplace entry, confirm the public
      `privacyPolicyUrl` in `apps/claude-code-plugin/.claude-plugin/plugin.json`
      resolves to the exact `PRIVACY.md` from the published revision and that the
      remote Blender MCP operator's privacy and retention terms are linked where
      users configure the service. **Proof:** reviewable public URLs and a tested
      plugin install from the published marketplace revision.

### What is blocked, and on what

Checked on 2026-11-23 against `main` (`849cfec`). Each of these is waiting on a
resource this checkout cannot supply, not on code:

| Leg of the vertical slice | Blocked on | How it was checked |
|---|---|---|
| A real-provider run end to end | an API key. `ANTHROPIC_API_KEY`, `LLM_API_KEY`, `LLM_PROVIDER` and `LLM_MODEL_ID` are all unset and there is no `.env` | read the process environment; the key itself was never used |
| A hosted MCP deployment | a host. `docker` is not installed on this machine, so only CI builds and smoke-tests the images | `docker --version` not found |
| Roblox Studio behaviour | a running Studio. No instance is connected | the Studio tool lists zero instances |

What does run here, and did on that commit: the nine offline FakeProvider cases
at $0 spend, and a place build producing the rainforest `rule_game` artifact.

### Reproducing the local checks

Rokit's shims fail from some shells (`The system cannot find the path specified (os
error 3)`) unless `ROKIT_ROOT` points at the toolchain directory. Either set it, or
put the real binaries first on `PATH`. From the repository root in Git Bash:

`. tools/dev-env.sh` does the same thing from the pins in `aftman.toml` and
checks each reported version. The explicit form is kept here because it shows
what the script does:

```sh
T="$PWD/.tools/rokit-root/tool-storage"
export PATH="$T/rojo-rbx/rojo/7.7.1:$T/luau-lang/lute/1.0.0:$T/kampfkarren/selene/0.32.0:$T/johnnymorganz/stylua/2.6.0:$PATH"
lute --version && rojo --version && selene --version && stylua --version
python -m pytest -q
python -m ruff check . && python -m ruff format --check .
python tools/package_agent_skills.py --check
python tools/package_reference_scenes.py --check
python tools/package_luau_protocol_schemas.py --check
claude plugin validate apps/claude-code-plugin && claude plugin validate .
git diff --check
```

If a test that needs Rojo fails with `KeyError: 'structuredContent'`, first check
that `rojo --version` runs in that shell. The Selene, StyLua, wheel and
fixed-template place commands are those of `.github/workflows/ci.yml`.

The pinned-Lute CI job also builds the rainforest `.rbxlx` in the fixed
`rule_game`, Obby, and Treasure Hunt modes. It verifies the rule-game round,
the ordered Obby route, and the Treasure Hunt artifact's triggers and spawn
before running the repository-owned gameplay simulations. These checks cover
serialized artifacts and fixed template logic; they do not replace an engine
playtest in Studio or a disposable live test place.

## 1. Optional local Studio plugin workflow (needs Studio and the local API)

The source plugin is split across `Main.plugin.lua` and protocol modules under
`apps/studio-plugin/src/Protocol/`. Build the installable model from the project
manifest with `rojo build apps/studio-plugin/default.project.json --output
dist/rga-studio-plugin.rbxmx`; install that model through Roblox Studio. The
remote agent workflow does not require this optional operator plugin.

- [ ] Install the built `.rbxmx` model through Studio's Plugins management UI and
      restart Studio if needed (`apps/studio-plugin/README.md`). Do not copy only
      `Main.plugin.lua`; it depends on the packaged protocol modules.
- [ ] Run the local API (`python -m api.cli serve`), queue
      `tools/examples/create-platform.json`, approve it, fetch it in the plugin and
      click Apply. **Proof:** the part exists, Ctrl+Z removes it, and
      `python -m api.cli status` shows the item `closed` with knowledge `known`.
- [ ] Close Studio mid-apply. **Proof:** the lock engages and only
      `python -m api.cli attest` releases it.

This is the evidence that lets ADR-0011 move from `Proposed` to `Accepted`.

## 2. Optional RGA artifact services (needs a Linux host and DNS)

Follow `apps/remote/deploy/README.md`.

- [ ] For hosted Blender authoring, set `BLENDER_MCP_URL` and
      `BLENDER_MCP_BEARER_TOKEN`, then
      `python tools/smoke_remote_blender_mcp.py`. **Proof:** it returns a GLB,
      verifies the receipt digest and Roblox asset preflight, and validates the
      optional 512x512 PNG preview returned in the same MCP call.
- [ ] Only when deploying the separate RGA Roblox artifact service, set
      `ROBLOX_MCP_URL` and `ROBLOX_MCP_BEARER_TOKEN`, then
      `python tools/smoke_remote_roblox_mcp.py`. **Proof:** it returns a `.rbxlx`
      with its digest.
- [ ] For the artifact route, open the returned `.rbxlx` in Roblox Studio or
      inspect it through the user's existing native Studio MCP. **Proof:** the
      map loads; verify gameplay separately with an engine playtest.

These checks validate the optional RGA hosted artifact services. The Claude
Code workflow configures remote Blender authoring and uses the user's existing
native Roblox Studio MCP; it does not add the RGA Roblox endpoint. Neither
workflow installs Blender, an RGA MCP server, or a local RGA API on the user's
computer.

On 2026-11-08, a live loopback MCP client/server run with local Blender 5.2.0
negotiated the tool, requested and validated a PNG preview, downloaded the GLB
with bearer authentication, and matched its SHA-256 to the receipt. The
36-object Mistral Coast recipe produced a 276,466-byte preview and a
102,888-byte GLB (`abe994ff917dc2dac6dced432447c53aff2b74573b5e64d35086b3fe1e831c3b`).
This checks the real local HTTP and Blender worker path; the deployed Blender
5.2.3 container and hosted DNS/TLS endpoint remain unverified.

A fresh current-checkout loopback smoke on 2026-11-08 used a temporary bearer
token and bound the service only to `127.0.0.1`. Blender 5.2.0 built 70
objects and returned a 277,838-byte preview; the GLB contained 66 meshes, 2
skins, and 2 animations. The smoke downloaded the artifact, matched SHA-256
`ff0c74e4b5289d52bf0fae9e1ced27df8f8e5f9f5cb50bfbe3664418520b0784`, and
passed the Roblox GLB preflight and unsupported-light-extension check. The
temporary local service was stopped. This strengthens local service evidence;
it does not verify the hosted Blender 5.2.3 container or public DNS/TLS.

### Remote Blender artifact to the native Studio MCP

Before the upload checklist, open a place belonging to a dedicated published
test experience and confirm its identity in the native Studio MCP. Open Cloud
permissions are granted per published game; a local unpublished `.rbxlx` can be
engine-tested but cannot authorize an Open Cloud asset upload. If no dedicated
published test experience is available, leave upload, moderation, and import
pending. Do not substitute a production experience.

- [ ] Set `BLENDER_MCP_PUBLIC_ORIGIN` to the public HTTPS origin used by the
      Blender MCP client, then rebuild and deploy the service.
- [ ] From Claude Code, build a small GLB below Roblox's current 20 MB Open
      Cloud asset-upload limit. Confirm the receipt's signed URL uses the
      configured Blender host and expires within 15 minutes; do not record the
      URL in access logs.
- [ ] Download the model file directly into a folder already approved by the
      native Studio MCP. Compare the file's SHA-256 to the receipt's
      `artifact_sha256`, then present the recipe and verified digest for review.
- [ ] After explicit approval, upload through the native `open_cloud_invoke`
      tool, wait for Roblox moderation approval, then insert the asset into the
      disposable test place through that same Studio MCP. **Proof:** asset ID,
      completed moderation result, and a saved test place containing the
      expected MeshParts. Do not publish the place.

This verifies the model handoff and import path only; it does not establish
that the generated game is production-ready.

## 3. A real model (needs `ANTHROPIC_API_KEY` and a spend limit)

- [ ] Set `LLM_PROVIDER=anthropic`, `LLM_MODEL_ID=claude-sonnet-5-5` and a small
      `AGENT_MAX_USD_PER_SESSION`.
- [ ] `python tools/evaluate_worldbuilding.py`. **Proof:** the structural rubric
      results and the recorded spend, which must not exceed the limit.

## 4. Release-gate report (local and read-only)

After creating a Game Plan, the operator panel's **Review release gates** button
or `POST /v1/operator/release-readiness` with `{"plan": <Game Plan v2>}` returns
a nine-gate JSON checklist. Every gate starts `pending`; persistence, commerce,
and multiplayer applicability must be decided by an owner. This confirms the
plan can be translated into explicit evidence requests. Download the report to
maintain it alongside separately recorded verification results. The endpoint
does not store evidence, prove any gate, inspect a Roblox place, or certify a
public release.

To collect local proof files with integrity metadata, package a still-pending
report and explicit evidence paths from the repository root:

```sh
python tools/package_release_evidence.py \
  dist/release-readiness.json dist/release-evidence.zip \
  --evidence server_authority_and_abuse=dist/server-abuse-results.json \
  --evidence device_playability_and_performance=dist/studio-playtest-notes.md
```

The tool stores the original pending report, a deterministic manifest, and the
selected files in a ZIP. The manifest records workspace-relative paths,
byte lengths, media types, and SHA-256 digests. It rejects paths outside the
workspace, symlinks, empty files, altered/verified reports, and oversized
inputs; it never overwrites an existing output. The package is an evidence
inventory, not a gate verifier: every gate stays pending and the content must
be reviewed independently. Nothing is uploaded or sent by this command.

Verify the resulting inventory from the repository root:

```sh
python tools/verify_release_evidence.py dist/release-evidence.zip \
  --sha256 YOUR_TRUSTED_ARCHIVE_SHA256
```

A successful check confirms the supplied SHA-256 matches the entire ZIP and
that the report is canonical and all archive paths, sizes, and file hashes
match the manifest. Obtain the expected archive hash through a trusted channel;
without `--sha256`, the command checks only internal consistency, since the ZIP
is not digitally signed. It reads the ZIP without extracting it and leaves all
nine gates pending; an owner must still inspect the evidence and validate its
claims.

## 5. Local unpublished Studio place (no published universe required)

The repo can produce a local, unpublished place file for engine checks. This
does not need Open Cloud credentials, a published test universe, the optional
RGA Studio plugin, or another Roblox MCP connection. The file is separate from
any currently open or published place and can be discarded after review.

Build and run the deterministic artifact check:

```sh
python tools/build_roblox_place.py \
  examples/worlds/rainforest-checkpoint-obby/scene-recipe.json \
  dist/rga-disposable-obby-test.rbxlx --gameplay-mode obby
python tools/check_rainforest_obby.py dist/rga-disposable-obby-test.rbxlx
```

Open `dist/rga-disposable-obby-test.rbxlx` in Roblox Studio. With the user's
existing native Studio MCP, call `list_roblox_studios`, select this local file
by its `studio_id` and place identity, then test it in Play Solo or a local
Server & Clients session. Use two clients for the multiplayer driver. Inspect
the route using the native MCP's `character_navigation` or `user_keyboard_input`
tools if available; read their live schemas first. Walk each consecutive leg
with an actual player character and capture server output and viewport evidence.
For sustained keyboard-controlled traversal, use `user_keyboard_input` with an
ordered key-down, wait, and key-up sequence when that live schema supports it;
a short key-press tap by itself is not traversal evidence. `character_navigation`
can check an agent-controlled route, but record it as assisted navigation rather
than manual player control.
If only `PathfindingService` or teleport-based drivers are available, record
those as connectivity or gameplay-logic checks and leave manual route traversal
pending. Stop without saving or publishing. Do not use the RGA Roblox MCP or
optional Studio plugin for this direct Studio test.

The deterministic checker only verifies the fixed Luau template against mocked
services. Engine evidence requires the actual Studio run and observed output;
this local file does not satisfy the separate Open Cloud test-universe gate.

On 2026-11-08, the local rainforest Obby artifact with SHA-256
`07278b2bc43de5324add2dda0ec5d26e00c54045cd8a33e009af96b6346cbd76` passed
one-player Play Solo in Studio 0.746.0.7461269. The server driver logged
`RGA_OBBY_NAVIGATION_PASS 4`, `RGA_OBBY_SEQUENCE_FINISH_PASS 1 1`, and
`RGA_OBBY_HAZARD_RESPAWN_PASS`. The driver accepts initial `Stage` 0 or 1
because the character may touch the first spawn checkpoint before the driver
runs. The session stopped without saving or publishing. The teleport-based
checks do not verify walking, multiplayer, or a live server.

## 6. Open Cloud validation (needs a dedicated test universe)

The gates are the acceptance criteria of
`docs/architecture/adr/0015-disposable-world-validation.md`.

- [ ] Provision an empty test universe and place, and a key scoped only to that
      universe and to Luau execution.
- [ ] Run `rga_validate_map` against a pinned place version.
      **Proof:** after the task, the place version and the production place are
      unchanged (the ADR requires this before relying on it).

Do not enable test-place publication or model upload until this step has passed.

## 7. What stays blocked

General model-written gameplay execution through RGA, playtests through
`playtest.request`, and production publishing remain disabled. They need a
broader source policy than the scoped blockout subset and independent runtime
gates (`docs/safety.md`, section 8). The user's native Studio MCP is a separate
direct authoring tool and may expose script editing or execution in an open
place; those actions are outside RGA's policy and are not isolated validation.

### Native Terrain authoring smoke (needs a disposable local place)

The `roblox-terrain-authoring` skill includes a deterministic heightfield
template. Its pinned-Lute simulation checks dimensions, array shape, the
route's center material, repeatable output, bounds rejection, and refusal to
write into an occupied region. This is not Roblox-engine evidence. To verify
the real native path:

- [ ] Open a new, unpublished local place or a separate disposable copy in
      Roblox Studio. Keep the user's working or published place out of scope.
- [ ] Through the existing Studio MCP, call `list_roblox_studios`, confirm the
      exact local place and edit state, then use that `studio_id` for the rest
      of the calls. Do not register another Roblox MCP endpoint for this test.
- [ ] Review the terrain bounds and code in
      `skills/roblox-terrain-authoring/references/terrain-recipes.md`; call
      Roblox's current Terrain API documentation with native `http_get`, then
      run the reviewed script through the native `execute_luau` tool.
- [ ] Confirm `RGA_TERRAIN_HEIGHTFIELD_PASS 48 24 48 55296`, inspect the patch
      with `screen_capture`, and navigate the generated trail with the native
      playtest tools. Record path readability, collisions, slopes, and any
      terrain or script errors.
- [ ] On a second empty test region, verify that an oversized configuration is
      rejected before writing. On an occupied region, verify the helper refuses
      to write; do not clear the test region to force a pass.
- [ ] Stop playtest and retain or discard the unpublished local artifact as
      the reviewer directs. Do not publish it.

**Proof:** selected Studio ID and local place identity, exact output marker,
viewport evidence, successful route navigation, and observed rejection results.
Do not claim Terrain MCP authoring is engine-verified until this evidence is
recorded.

### Existing local engine evidence

On 2026-11-07, the generated rainforest `rule_game` artifact passed a one-player
Roblox Studio Play Solo check on Studio `0.746.0.7461269`. Server Output
confirmed two rounds, duplicate-contact idempotency, rejection of an early goal,
hazard elimination, and respawn. The test driver teleported the character to
trigger parts, so this does not establish walking-route playability. It also
does not cover multiplayer, persistence, a disposable cloud test place, hosted
MCP services, or production behavior. See the evidence and artifact digest in
[`examples/worlds/rainforest-checkpoint-obby/README.md`](../examples/worlds/rainforest-checkpoint-obby/README.md).

On 2026-11-07, the corrected rainforest Obby artifact was opened in Studio and
run in a fresh one-player Play Solo session. The developer-only server command
bar driver `tools/studio_rainforest_obby.luau` passed with Output markers
`RGA_OBBY_NAVIGATION_PASS 4`, `RGA_OBBY_SEQUENCE_FINISH_PASS 1 1`, and
`RGA_OBBY_HAZARD_RESPAWN_PASS`. Roblox `PathfindingService` returned a
successful waypoint path for all four consecutive checkpoint legs with a
2-stud radius, 5-stud height, jump-capable agent. Engine touch checks covered
early and skipped checkpoint rejection, duplicate touches, ordered progression,
a single win, start respawn selection, hazard elimination, and respawn. The
driver teleports the player, so manual walking/control playability, multiplayer,
persistence, live-server behavior, hosted MCP services, and production behavior
remain unverified. Play Solo was stopped without saving or publishing the
artifact. See the evidence and digest in
[`examples/worlds/rainforest-checkpoint-obby/README.md`](../examples/worlds/rainforest-checkpoint-obby/README.md).

On 2026-11-08, a fresh Play Solo recheck loaded the same local artifact
(`dist/codex-review-rainforest-obby.rbxlx`, SHA-256
`07278b2bc43de5324add2dda0ec5d26e00c54045cd8a33e009af96b6346cbd76`). The
avatar spawned at the start, but one forward-key tap did not produce movement;
Studio retained focus in its command editor. No command was executed. The test
was stopped without saving or publishing. Manual navigation remains unverified.

The two-client driver `tools/studio_rainforest_obby_multiplayer.luau` is ready
for a fresh local **Server & Clients** session with exactly two clients. Its
engine run remains pending: the attempted session exposed a Server window but
no clients, so no multiplayer pass is claimed. The driver is linted in CI and
checks isolated progression/wins plus hazard respawns once the required clients
are present.

The repository-owned Obby server template also passed its deterministic Lute
simulation on 2026-11-07:
`python tools/check_rainforest_obby.py dist/rainforest-checkpoint-obby.rbxlx
--lute .tools/lute-1.0.0/lute.exe`. It verified ordered checkpoint progression,
rejection of early and skipped checkpoints, duplicate contacts, one-time finish
awards and reset, hazard handling, and independent progress for two players.
This exercises the fixed Luau template with mocked Roblox services; it does
not establish Roblox engine physics, actual respawn, network timing, or route
walkability. Those still require the Studio engine driver.

On 2026-11-07, the generated rainforest Treasure Hunt artifact passed a fresh
one-player Roblox Studio Play Solo server-driver run. Output confirmed all
three collectibles, duplicate-contact idempotency, the one-second round reset
debounce, and two consecutive victories with `RGA_TREASURE_ROUND_PASS 1 0 1`,
`RGA_TREASURE_ROUND_PASS 2 0 2`, and `RGA_TREASURE_TWO_ROUNDS_PASS`. The test
driver initially expected the raw pickup count after the final coin; it was
corrected to expect the implemented reset and victory award. The fixed game
template required no change. The driver teleports the character, so this
checks engine touch handling, not manual navigation, multiplayer, persistence,
or production-server behavior. See the artifact and digest in
[`examples/worlds/rainforest-treasure-hunt/README.md`](../examples/worlds/rainforest-treasure-hunt/README.md).

The `rule_game` template now includes a timed speed boost on rainforest
collectibles. Its deterministic simulation verifies the speed cap and timer
refresh/restore. To verify Roblox engine touch behavior, build a fresh local
artifact with:

```powershell
python tools/build_roblox_place.py `
  examples/worlds/rainforest-checkpoint-obby/scene-recipe.json `
  dist/rainforest-speed-boost.rbxlx `
  --gameplay-mode rule_game `
  --gameplay-rules examples/worlds/rainforest-checkpoint-obby/gameplay-rules.json
```

Open that disposable artifact in Studio, start a fresh Play Solo session, and
run [`tools/studio_rule_game_speed_boost.luau`](../tools/studio_rule_game_speed_boost.luau)
in the **server** command bar. A pass must show both
`RGA_SPEED_BOOST_APPLIED` and `RGA_SPEED_BOOST_RESTORED`. Do not run this driver
in a user's working place or publish the test artifact.

The fixed `rule_game` HUD is authored with viewport-relative width, top-bar safe
inset, wrapped text, and content-driven height. Its Lute fixture checks those
properties but does not emulate screen sizes. For engine review, open a fresh
disposable build of the same artifact in Studio and use Device Emulator to
inspect a small phone in portrait and landscape plus a desktop layout; use
Controller Emulator to check visible focus behavior. Record each layout and
input you actually inspected. The current template HUD has no interactive
buttons, so this check does not cover navigation through a full menu.

The fixed rule-game interpreter also pauses nonlethal touch effects for one
second after an `award_win` reset so repeated contacts on a scoring landmark
cannot award repeated wins. The local Lute simulation covers this edge case.
For an engine check, build a disposable rule-game artifact whose landmark has
both `award_points: 1` and `award_win: 1`, then run
[`tools/studio_rule_game_round_reset.luau`](../tools/studio_rule_game_round_reset.luau)
in the Play Solo **server** command bar. The pass marker is
`RGA_RULE_ROUND_RESET_ENGINE_PASS`. This driver teleports a single test avatar;
it verifies server touch/reset behavior only, not manual navigation or
multiplayer. Never put the driver into a delivered place.
