# Project status

The detailed state of each roadmap stage. The README carries the short table.
Three states are used strictly: **written** means the implementation or design
exists in the repository; **verified** means the stated check has passed;
**planned** means it does not exist. A written remote adapter is not described
as live until its external service and runtime evidence are available.

| Stage | Scope | State |
| 0 | Architecture decisions, safety model | written (documents only) |
| 1 | Repository hygiene, CI, governance | written; CI workflows cover lint, formatting, Python tests, Luau checks, Windows sandbox limits, Blender container runtime smoke, and Roblox build/validation container build plus authenticated fake-MCP smoke; the Roblox standard library is checked in and pinned for offline Selene lint; a Roblox container smoke decodes valid PNG/JPEG model assets and rejects a structurally valid but undecodable JPEG; on 2026-11-08, `uv build --wheel --offline` built a 318,864-byte wheel whose 36-resource audit covers every core skillpack and schema and includes the release-evidence integrity verifier; [the latest green run on `main`](https://github.com/cesarsegura-eng/roblox-game-architect/actions/runs/41348016243) used commit `03d254f`, predates the current checkout `a4d83dc`, and did not run the new container jobs, so this tree remains unverified in hosted CI |
| 2 | `packages/protocol` — first versioned schema | written; on 2026-11-08 the current checkout passed the full local suite with repository-pinned Lute 1.0.0 available (`1,648 passed`, no skips); the integrated Luau strict parser and schema validator passed all 42 parse vectors, exact-size/invalid-UTF-8 cases, and 200 valid/invalid schema vectors; hosted CI and the installed Studio runtime remain unverified on this uncommitted tree |
| 3 | `packages/core` — LLM foundation and run guards | in progress; fake and Anthropic providers, trusted/untrusted framing, budget-enforced Game Plan v2 with a validated first-slice mode and bounded data-only gameplay rules, dedicated native-Studio gameplay-engineering and cross-platform UI/UX skills, world-design and builder loops, and a sandbox Luau validator for scoped scene blockouts exist; the read-only source preview is wired to the operator, while general gameplay remains outside policy; production briefs carry an evidence-oriented checklist in the trusted planning prompt, and the operator can create a separate machine-readable nine-gate release report; all gates remain pending until owners provide evidence and human review, so this report does not implement or verify the listed release systems |
| 4 | First vertical slice: generate → validate → run → report | in progress; API has script-free declarative actions, Blender recipes can become reviewed Studio proxy Parts, core can generate and retry through an injected validator, Studio supports review and a narrow undoable Workspace action subset, and a fixed-harness remote Roblox map-validation path exists; Obby builds reject checkpoint sequences that skip or disconnect consecutive route segments, and the rainforest example checkpoints serialize from start to finish; on 2026-11-07, fresh local builds of the `rule_game`, Obby, and Treasure Hunt rainforest places passed their fixed Lute checkers (rule scoring, temporary speed boost expiration, route sequencing, hazards, multiplayer simulation, collection, rounds, and reset debounce); these are deterministic template simulations, not a new Roblox Studio run; a fresh current-checkout rebuild on 2026-11-08 generated 19 recipe objects in each mode; fixed checkers passed two rule-game rounds with speed-boost expiry, duplicate-touch handling, hazards, and independent player scores; Obby order/finish, hazard isolation, and multiplayer progress; and Treasure Hunt independent two-player progress, two rounds, duplicate touches, and reset debounce; these are deterministic artifact simulations, not an engine playtest; the rule-game HUD now uses scale-based width, safe-area inset, wrapped text, and automatic height, verified in the deterministic round fixture; the one-player Play Solo speed-boost driver is included in CI's Selene/StyLua checks, while its engine run remains pending; CI contains the same artifact gates, though the hosted run on this tree remains pending; one-player Studio Play Solo server-driver checks on Studio 0.746.0.7461269 confirmed rule-game scoring/rounds/hazards/HUD and the current Obby template's ordered checkpoints, win/reset, hazard elimination, and respawn; in Roblox Studio, `PathfindingService` returned waypoints for all four consecutive Obby legs with the fixed 2-stud radius/5-stud height agent; server Output showed `RGA_OBBY_NAVIGATION_PASS 4`, `RGA_OBBY_SEQUENCE_FINISH_PASS 1 1`, and `RGA_OBBY_HAZARD_RESPAWN_PASS`; a fresh one-player Studio Play Solo server-driver run on 2026-11-07 verified Treasure Hunt three-pickup collection, duplicate-contact idempotency, reset debounce, and two wins in the 28,266-byte artifact (`RGA_TREASURE_ROUND_PASS 1 0 1`, `RGA_TREASURE_ROUND_PASS 2 0 2`, `RGA_TREASURE_TWO_ROUNDS_PASS`); this teleport-based driver does not establish manual navigation; multiplayer engine behavior and external Open Cloud runtime/persistence remain unverified, and arbitrary generated source remains blocked |
| 5 | 3D authoring and Studio clients | in progress; Rojo 7.7.1 built the optional RGA Studio plugin model with bundled protocol modules and the expected Plugin RunContext; this verifies packaging only, not installation or live Studio behavior; remote Blender MCP builds reviewed GLB artifacts without local Blender; on 2026-11-08, the local MCP service smoke with Blender 5.2.0 generated 70 objects, exported 66 meshes, 2 skins, and 2 animations, verified the artifact download against the receipt SHA-256, and passed the Roblox GLB preflight; that run exposed `KHR_lights_punctual` in the service export, so the worker now omits this unsupported asset extension while recipe lighting remains in the separate place artifact; the MCP smoke explicitly rejects the extension; the generic rigid NPC blockout now offers balanced, heroic, slender, and round body-proportion presets without changing its skeleton; the Blender 5.2.0 extension smoke on 2026-11-08 verified heroic, round, and slender proportions plus all three animation clips in a GLB round-trip; a Blender 5.2.0 extension smoke on 2026-11-08 generated 69 importable meshes and two silhouette presets and passed the then-current structural preflight; the current Pillow 13.0.0 image-decoding preflight passed the local asset smoke for valid PNG/JPEG and a malformed JPEG; a fresh Blender 5.2.0 end-to-end extension smoke on 2026-11-08 exported a textured scene with 70 recipe objects, re-imported 86 meshes including three character silhouettes, and passed the current full-decode preflight; an earlier full-suite run passed 1,627 tests with pinned Lute 1.0.0 and no skips; the local artifact store now enforces 2 GiB and 4,096-file caps, recovers orphaned GLBs, and denies downloads after seven days; the deployed Blender 5.2.3 container remains unverified; before persistent writes, the Roblox asset uploader checks each imported GLTF primitive against the 20,000-triangle ceiling, embedded geometry ranges, dense and sparse accessor values for positions, indices, skin weights/joints and animation data, 60,000-vertex mesh and 100,000-element animation accessor caps, a 1,000,000-element global validation-work cap, bounded metadata collection sizes, a 256-image ceiling and 64-million aggregate texture-pixel budget, bounded node transforms and valid acyclic scene hierarchies, finite values, four-influence skin limits, MAT4 inverse-bind matrices checked against joints, affine matrix rows, and bounded morph target accessors, mesh/node weights, morph animation output shapes, and general animation channels/times/output shapes, embedded PNG/JPEG dimensions against 4096 pixels, PNG chunk checksums, JPEG frame/scan/end-marker structure, and full Pillow pixel decoding of every unique embedded image source; the Blender 5.2.0 extension smoke removed its source image, re-imported a JPEG-textured GLB, verified decoded 16x8 pixels, and passed the then-current structural Roblox asset preflight on 2026-11-08; it does not certify topology, texture or animation quality, successful moderation, or runtime rendering; the API can transfer a reviewed GLB to a separately configured Roblox MCP asset tool using digest-bound approval, and an opt-in, bounded cloud-inspection plus Rojo import prototype can include approved Model MeshParts in a script-free blockout; live asset loading, serialization, and rendering remain unverified; the authenticated Roblox MCP fake-validator smoke passes locally through the fixed build and Rojo artifact path, but Docker deployment remains unverified; digest-bound publication supports direct-agent prepare/confirm to only the configured disposable test place; live Open Cloud writes, rollback, and persistence remain unverified, and production publishing stays disabled; fixed Obby, Treasure Hunt, and data-driven rule modes include only repository-owned server scripts; on 2026-11-08, the 32,747-byte rainforest Obby artifact (`07278b2bc43de5324add2dda0ec5d26e00c54045cd8a33e009af96b6346cbd76`) passed a fresh one-player Studio 0.746.0.7461269 Play Solo engine-driver run: server output reported `RGA_OBBY_NAVIGATION_PASS 4`, `RGA_OBBY_SEQUENCE_FINISH_PASS 1 1`, and `RGA_OBBY_HAZARD_RESPAWN_PASS`; the driver now accepts `Stage` 0 or 1 at start because the spawned avatar may touch the first SpawnLocation before the check; the run verifies route PathfindingService connectivity, ordered and duplicate checkpoint handling, one win, hazard death, and respawn, but its teleport-based checks do not verify manual navigation, multiplayer engine behavior, or live-server behavior; Blender MCP protocol and signed artifact download tests pass locally, but external hosted URLs/tokens, native terrain generation, Studio asset upload, moderation, and final Roblox rendering remain unverified here; production map publishing remains disabled in [ADR-0018](architecture/adr/0018-remote-roblox-map-authoring.md) |
| 6 | Web application | in progress; local operator UI quotes game-plan, recipe, Studio blockout, and scoped code-preview calls before generation, displays shared spend, checks remote MCP contracts, reviews and downloads Blender GLB and Roblox place artifacts, carries Game Plan v2 data-only gameplay rules and trigger-role requirements through recipe generation into the fixed server interpreter, offers script-free, Obby Course, Treasure Hunt, and bounded data-driven rule modes behind separate review and confirmation, groups correlated Blender/Roblox workflows, and approves script-free actions; it can generate and export a strict nine-gate release-readiness report from a validated plan, including generated-mesh/texture/rig/animation validation receipts and Roblox import/render review; the report remains pending and external evidence and human approval are still required; arbitrary source preview is not run or sent to Roblox |
| 7 | Agent evaluation suite with fixed cases | in progress; on 2026-11-08, a fresh run of `tools/evaluate_worldbuilding.py` passed all nine reviewed offline FakeProvider cases at $0 spend, including connected rainforest Obby and collect-and-win routes, plus a volcanic cave entrance-to-interior transition; the rubric checks required collectible/hazard/landmark counts, each collectible's route proximity and distribution across distinct segments, recipe-order continuity for Obby routes, hazard/landmark placement, house transitions and room layout, connected paths, elongated route geometry, lighting coverage, biome settings, character motions, and requested character silhouette presets; this is structural fixture coverage, not visual quality or in-Studio playability; live provider comparisons and Studio playability grading remain |
| 8 | Existing-agent delivery: domain skills + remote MCP tools | in progress; nine portable `SKILL.md` guides package game-planning, server gameplay engineering, UI/UX, biome and environment-effects authoring, native Studio Terrain, Blender, map-blockout, and character knowledge for compatible agents, with a reproducible ZIP export; the terrain skill uses the user's existing Studio MCP and a bounded deterministic Luau heightfield template, simulated with pinned Lute; real Studio terrain behavior remains unverified; [ADR-0020](architecture/adr/0020-native-studio-mcp-and-existing-agent.md) defines Claude Code's native Studio MCP as the direct Roblox connection, while the Claude plugin and marketplace configure only the separately hosted Blender MCP; the standalone RGA Roblox service remains optional for agent environments where an operator has already exposed it; Claude Code 2.1.317 passed its official strict validator on both the plugin and marketplace manifests, and the plugin includes a privacy notice whose canonical GitHub URL resolves only after the current branch changes are published; the optional unified remote Compose stack builds Blender and Roblox MCP services behind one TLS reverse proxy without exposing backend container ports; Blender GLBs can transfer between fixed MCP hosts, and a 15-minute signed artifact link supports Claude's existing native Studio Open Cloud upload path when its public origin is configured; the artifact receipt digest is checked by both the operator API and browser before download; local signed-link and protocol tests pass, but live hosted connection, native terrain engine behavior, native upload, moderation, engine import, final Roblox rendering, public privacy notice, and marketplace publication remain unverified |

## 2026-11-08 incremental Blender evidence

The Blender MCP recipe tool now optionally returns a non-persisted, fixed-camera
512x512 PNG preview in the same response as its GLB receipt. The existing API
client can request the image and validates its type, dimensions, and size. A
live local loopback client/server smoke with Blender 5.2.0 negotiated MCP,
rendered the 36-object Mistral Coast recipe, returned a 276,466-byte preview,
downloaded the 102,888-byte GLB, and matched its receipt SHA-256
(`abe994ff917dc2dac6dced432447c53aff2b74573b5e64d35086b3fe1e831c3b`). The 44
focused client and server tests also passed. This preview is a Blender
composition aid, not a Roblox engine render. The hosted Blender 5.2.3 container
smoke still needs to run in CI.

A fresh current-checkout loopback MCP smoke on 2026-11-08 used an ephemeral
bearer token and bound the service only to `127.0.0.1`. Blender 5.2.0 built
the current 70-object recipe, returned a 277,838-byte PNG preview, and produced
a GLB with 66 meshes, 2 skins, and 2 animations. The client downloaded the
artifact, matched SHA-256
`ff0c74e4b5289d52bf0fae9e1ced27df8f8e5f9f5cb50bfbe3664418520b0784`, and
passed the Roblox GLB preflight, including the unsupported-light-extension
check. The local service process was stopped after the smoke. This verifies
the current local MCP and Blender worker path; it does not verify the hosted
Blender 5.2.3 deployment or public DNS/TLS endpoint.

## 2026-11-08 expanded world evaluation and cave authoring

The reviewed offline world-generation suite now has nine cases and includes a
volcanic cave crossing. Its rubric checks exterior, entry, open-threshold, and
separate interior roles; adjacency to an interior landmark; two connected
ordered route segments; and a point light near the chamber. All nine
FakeProvider cases passed at $0 spend, and the focused worldbuilding/evaluation
tests passed. This remains structural evidence, not a human visual or Roblox
playability review. The cave recipe also exported and reimported in Blender
5.2.0 with 66 imported meshes across the scene and character smoke assets, then
built a 14-Part script-free `.rbxlx` through the pinned Rojo path. The current
local place SHA-256 is
`3cbaba413e1244c1b64094b6b7371a447b1e8ffeb263eddd92c0ee530b97d063`; it has
not yet been opened or playtested in Studio.

## 2026-11-08 desert courtyard house artifact

The Desert Courtyard Home v3 recipe passed strict recipe validation with 10
scene objects and two recipe lights. Rojo built a separate, unpublished,
script-free blockout at `dist/rga-review-desert-courtyard-house.rbxlx` (15,403
bytes; SHA-256
`922c701fadf3520cf86b681229a0327c24c1b7c6738459c5d8956bb22f381945`). An
independent XML inspection found the 10 authored Part models plus the builder's
spawn part, one local light, Lighting, Atmosphere, Clouds, and no Scripts,
LocalScripts, or ModuleScripts. The example README now contains the build
command. This confirms serialization of the interior/exterior roles and
environment profile; the blockout has not been opened for visual, collision, or
manual navigation review in Studio.

## 2026-11-08 Roblox Studio engine evidence

The local unpublished rainforest Obby (`dist/codex-review-rainforest-obby.rbxlx`;
SHA-256 `07278b2bc43de5324add2dda0ec5d26e00c54045cd8a33e009af96b6346cbd76`)
was run in Roblox Studio 0.746.0.7461269 Play Solo. The server driver passed
route connectivity for all four checkpoint legs, ordered and duplicate checkpoint
handling, one finish win, hazard elimination, and respawn. Studio Output recorded
`RGA_OBBY_NAVIGATION_PASS 4`, `RGA_OBBY_SEQUENCE_FINISH_PASS 1 1`, and
`RGA_OBBY_HAZARD_RESPAWN_PASS`. The driver precondition now accepts `Stage` 0 or
1 because spawning on the first `SpawnLocation` can activate it before the test
starts. The session stopped without saving or publishing. Teleport checks do not
verify manual controls, multiplayer engine behavior, or a live server.

A separate UI-only Play Solo check reopened that same 32,747-byte artifact and
showed the avatar on the starting platform. No command-bar script was run. The
Windows UI control used for this check rejected held-key input; repeated key
presses and a jump did not establish sustained movement or route traversal, so
manual playability remains unverified. Repeat the check through the user's
existing native Studio MCP using its live `user_keyboard_input` schema and an
ordered key-down, wait, and key-up sequence. A fresh Play Solo recheck on
2026-11-08 confirmed the artifact still has SHA-256
`07278b2bc43de5324add2dda0ec5d26e00c54045cd8a33e009af96b6346cbd76`; the
avatar loaded at the start, but a single forward-key input produced no visible
movement while Studio retained focus in the command editor. Play Solo was
stopped without running the pasted test driver, saving, or publishing. Manual
playability remains unverified.

## 2026-11-08 Blender authoring smoke

Ran `tools/smoke_blender_extension.py` in the installed Blender 5.2.0 LTS
against the curated Mistral Coast recipe. The real extension built 87 recipe
objects, created three 48-part character blockouts with heroic, slender, and
round silhouettes, exported and reimported the JPEG-textured GLB, and passed
the exact Roblox upload preflight after verifying the decoded texture. Blender
reported `RGA_BLENDER_SMOKE_OK` with 86 imported meshes. This validates the
local development extension and interchange path; end users still use the
separately hosted Blender MCP, and this run does not establish visual quality
or Studio import/rendering.

## 2026-11-08 current Blender-to-GLB preflight

After the vertex-attribute validator update, a fresh Blender 5.2.0 LTS run of
`tools/smoke_blender_extension.py` rebuilt the Mistral Coast recipe and three
silhouette/animation rigs, exported and reimported the textured artifact with
86 meshes, and reported `RGA_BLENDER_SMOKE_OK`. The exact current Roblox asset
preflight accepted `dist/rga-turn-smoke-current.glb` (381,164 bytes; SHA-256
`0155ababc51cfaee4e32e0eb1864bad9d90afbcaa33282c7a08a6c283eceef4c`). This
verifies the local Blender extension and GLB structural/image preflight; it
does not verify the hosted Blender MCP, a native Studio import, Roblox
moderation, rendered appearance, or in-game animation quality.

## 2026-11-08 agent workflow packaging

The coordinator skill now carries the validated Game Plan's world brief,
playable-slice mode, included/deferred systems, limitations, and acceptance
checks into each agent tool call. The local operator panel is explicitly an
optional compatibility path, not a prerequisite. The canonical skill and both
agent-facing copies passed the synchronization check; the Claude plugin
workflow invariant passed all 18 focused tests. The coordinator also directs
agents to use ordered key-down/wait/key-up actions for sustained Studio
movement tests when the connected MCP schema provides them. The asset handoff
now requires a published dedicated test experience for per-game Open Cloud
permissions; an unpublished local place remains usable for engine checks but
cannot authorize uploads. The reproducible skill archive now embeds the
authoritative research-source index in the planning, environment, and character
skills, so portable installs resolve their cited source guide. Blender authoring
now receives the same source index alongside its recipe schema. The archive was
rebuilt as `dist/rga-agent-skills.zip` (94,195 bytes; SHA-256
`221d945fe9d77a0c128982fb6d8e6513398470f3d8778905443ab5a65dfa1a85`).

## 2026-11-08 production-scope detection

The nine-gate release report now recognizes English and Spanish descriptions of
session-only progression. A generic mention of progression no longer claims
that persistence is in scope when the plan explicitly says data is not saved;
the gate stays pending and asks an owner to resolve scope. A separate explicit
save/persistence requirement still marks the gate likely in scope. Focused
release-readiness coverage passed, and the full local suite passed `1,627 tests`
with loopback access enabled and pinned Lute 1.0.0. These checks validate plan
classification, not the game's actual data behavior or production readiness.

## 2026-11-08 GLB vertex-attribute preflight

The Roblox asset preflight now validates standard and custom vertex-attribute
semantics, accessor references and counts, supported component/normalization
pairs, structural set indices, and finite attribute data; it rejects normalized
float `POSITION` accessors. The asset test module passed 69 focused cases and
lint and format checks passed. An earlier restricted run could not execute a
loopback server test; a subsequent full run passed all 1,627 tests with access
to the suite's own 127.0.0.1 servers. A scan of
36 retained Blender GLBs found 30 accepted by the current preflight; six older
exports were rejected for declaring `KHR_lights_punctual`, which the uploader
intentionally does not inspect. This covers interchange structure, not visual
quality or Roblox import and rendering.

## 2026-11-08 current gameplay-template rebuilds

Rebuilt the rainforest recipe with each current gameplay mode and ran its fixed
Lute 1.0.0 simulator. The 35,735-byte `rule_game` artifact passed scoring,
boost expiry, duplicate-touch handling, hazards, two rounds, and independent
player scores (SHA-256
`bc123e1c9e01417f121ba1f59ed21091b5342f9c1abe9e2a5a30f8c9f6a26acd`). The
32,747-byte `obby` artifact passed ordered route/finish, hazard isolation, and
independent multiplayer progress (SHA-256
`07278b2bc43de5324add2dda0ec5d26e00c54045cd8a33e009af96b6346cbd76`). The
28,266-byte `treasure_hunt` artifact passed independent two-player progress,
two rounds, duplicate touches, and reset debounce (SHA-256
`05f3bdace227e12324aa07c4d6beb8362a2d5e9982f1f4230bef72aeb26ff93f`). These
are deterministic fixed-template simulations, not Roblox engine or manual
playability tests.

## 2026-11-08 local release evidence packaging

Added `core.release_evidence` and
`tools/package_release_evidence.py` to gather explicitly selected workspace
files beside a still-pending release-readiness report. The reproducible ZIP
contains the report, a manifest whose shape is covered by the checked-in
schema, and the requested artifacts;
each item is tied to one of the nine gates with its workspace-relative source
path, media type, byte length, and SHA-256. Paths must stay in the workspace,
symlinks and empty files are rejected, inputs are bounded, and the CLI never
overwrites an output. Readiness remains `not_ready` and all gate statuses remain
`pending`; this is a hash-bound integrity inventory, not a review of evidence
claims or release certification. Twenty-three focused readiness/evidence and CLI tests passed,
including a symlink-rejection branch driven through a mocked `Path.is_symlink`
signal. A real CLI smoke
generated and reopened a ZIP without transmitting data. External owner review
and runtime proof remain required.

## 2026-11-08 release evidence integrity verification

Added `verify_release_evidence_bundle` and
`tools/verify_release_evidence.py` to verify a previously created evidence ZIP
without extracting it. The verifier bounds compressed and expanded sizes,
rejects duplicate or unlisted archive entries and non-pending reports, and
checks canonical JSON, archive structure, and each evidence file's byte length
and SHA-256 against the manifest. An optional expected archive SHA-256 can bind
the check to bytes obtained through a trusted channel; without it, the check is
internal consistency only because the bundle is not signed. A successful check
leaves every gate pending and does not assert that a file's claims are true.
Focused tests cover intact bundles, tampered payloads, extra archive entries,
and trusted-digest mismatch; live owner review and production evidence remain
required.

## 2026-11-08 Blender cutaway review

The remote Blender MCP now accepts `preview_mode: "cutaway"` with
`include_preview: true`. It temporarily hides recipe objects with role `roof`
for the inspection render and restores them before GLB export. The API client,
tool schema, canonical authoring skill, portable skill copy, and Claude plugin
skill document this option. Blender 5.2.0 ran the real worker against the
Desert Courtyard Home recipe: the 512x512 preview exposed the room and courtyard,
and the 16,968-byte GLB retained all ten named meshes including `Deep shade
roof canopy`. Removed the deprecated `World.use_nodes` assignment after
confirming the Blender 5.2 worker still renders through the existing world node
tree. This is local worker evidence; the hosted Blender 5.2.3 MCP and
Roblox Studio visual import remain unverified. A new live loopback smoke now
starts the actual HTTP MCP service, requests the cutaway via the API client,
downloads the GLB and verifies its receipt SHA-256, passes the Roblox asset
preflight, confirms the roof is present in the export, and checks that cutaway
and isometric PNGs differ; it passed with 12 objects, a 289,107-byte cutaway
PNG, and a 16,968-byte GLB (`98c6e24e4a52542a9b3aa180405d9535c8e5f085c4729baa841a8c82265befcf`). The service binds only to `127.0.0.1`, uses an
ephemeral token and temporary artifact store, and shuts down after the run. The
MCP-focused tests passed 45 cases, and the latest full local suite passed
`1,642` tests with pinned Lute 1.0.0 and no skips. Loopback access was enabled.
Ruff lint/format and
`git diff --check` passed. The
reproducible portable skills ZIP was rebuilt at `dist/rga-agent-skills.zip`
(94,349 bytes; SHA-256
`050260f86b944c16f75f3e9faeffa1abf79620301dfba73baa8514741668f2e5`).

The script-free house place `dist/rga-review-desert-courtyard-house.rbxlx`
opened in Roblox Studio for a local load check. Studio showed a Lighting
Technology Migration prompt; it was dismissed without migration. The default
viewport framed the roof canopy and did not expose the interior, so the cutaway
image is the available interior review evidence. The temporary Studio session
was later closed with **Don't Save**; the on-disk file remains 15,403 bytes with
SHA-256 `922c701fadf3520cf86b681229a0327c24c1b7c6738459c5d8956bb22f381945`.
This confirms that Studio can load the local place file, not that the place is
manually playable or production-ready.

The 2026-11-08 CI follow-up now runs the cutaway MCP smoke inside the same
Blender 5.2.3 container image used by the deployment job, and copies only its
recipe and test runner into that image. Focused deployment and release-evidence
tests pass (`18 passed`), Ruff passes, and `git diff --check` is clean. Docker is
not installed in this workspace, so the container job itself still needs a
hosted CI run; this local check does not claim a container or hosted-service
pass.

## 2026-11-08 rule-game round-reset idempotency

Hardened the fixed `rule_game` interpreter against duplicate wins when a
landmark both awards points and satisfies the win threshold. After a win, all
nonlethal touch effects pause for one second while per-player round state is
reset; configured lethal hazards remain active. The deterministic Lute
simulation reproduces repeated landmark contacts during that window and checks
that a later round can start. The artifact-level round fixture now advances its
mock timers, including the one-second reset debounce and twelve-second speed
boost, and models players as parented to Players; it no longer starts round two
while the server correctly has scoring paused. Fresh current-checkout builds
of rule_game, Obby, and Treasure Hunt passed their Lute fixed-template
checkers (rule_game SHA-256
`8840d37de727fdb453acfff067e1c078781cbc93202d74d181f4e2e9ef732a0a`, Obby
`07278b2bc43de5324add2dda0ec5d26e00c54045cd8a33e009af96b6346cbd76`, Treasure
Hunt `05f3bdace227e12324aa07c4d6beb8362a2d5e9982f1f4230bef72aeb26ff93f`). The
focused gameplay/place checks passed 28 cases; a full rerun passed `1,648`
tests with loopback access and pinned Lute 1.0.0 enabled. Full Ruff lint,
format check, portable skill sync check, Selene, StyLua, protocol-schema
packaging, and `git diff --check` passed; Rojo 7.7.1 built the 91,306-byte
Studio plugin model with its expected server RunContext. A fresh local Blender
5.2.0 cutaway MCP smoke also passed with 12 objects, a 289,107-byte preview,
and a 16,968-byte GLB whose SHA-256 is
`98c6e24e4a52542a9b3aa180405d9535c8e5f085c4729baa841a8c82265befcf`. This is
fixed-template and local-service evidence only; it does not add custom
model-written Luau or replace Studio engine and multiplayer testing.

## 2026-11-08 verification pass, request timeouts and a digest guard

Re-verified the uncommitted tree on top of `a4d83dc` (branch
`protocol/v1-and-adr-0011-wire-changes`) with the pinned Lute 1.0.0, Rojo 7.7.1,
Selene 0.32.0 and StyLua 2.6.0 binaries on `PATH`. The full local suite passed
`1,654` tests with no skips (`python -m pytest -q`, about 65 s, loopback enabled).
The same checks as the hosted CI's Python and Luau jobs passed: `uv lock --check
--offline`, the skill, reference-scene and Luau-protocol-schema sync checks, Ruff
lint and format, Selene (0 warnings, 0 parse errors) and StyLua on the authored
Luau, `git diff --check`, `claude plugin validate` on the plugin and on the
marketplace (Claude Code 2.1.317), a wheel build audited by
`tools/check_wheel_resources.py` (318,864 bytes, 93 members) and Rojo's 91,306-byte
plugin model with its Plugin RunContext token. Fresh `rule_game`, Obby and
Treasure Hunt places built to the digests recorded above and passed their Lute
checkers, and `tools/evaluate_worldbuilding.py` passed all nine offline FakeProvider
cases at $0. None of this is hosted CI, Studio, or a live service.

Defects found and fixed in this pass:

- The remote Blender and Roblox MCP servers set no socket timeout. Each admits only
  a few simultaneous requests (8 and 2), so a client that connected and sent nothing,
  or declared a body and stalled, could occupy every slot indefinitely. Both handlers
  now time out stalled reads after 30 s and answer an unfinished body as a bad request;
  `tests/test_remote_server_timeouts.py` drives a silent and a stalled connection
  against both servers, and was confirmed to fail on the old behaviour.
- The bundled `Caddyfile` now bounds header (10 s) and body (120 s) time and header
  size, and has no write timeout so long builds are not cut. The Roblox MCP README had
  claimed "proxy rate limits" the stock proxy does not provide; it and the deploy guide
  now say so. The new Caddy options were not validated locally, because this
  environment has no Docker or Caddy: the CI job that runs `caddy validate` is the
  check, and it has not run.
- The Treasure Hunt artifact digest recorded in this page was three characters short;
  it now matches the fresh build, and `tests/test_doc_digests.py` rejects any quoted
  digest that is not 64 hex characters.

Environment note: with Rokit's shims first on `PATH` and `ROKIT_ROOT` unset, `rojo`,
`selene` and `stylua` fail with "The system cannot find the path specified (os error
3)", and the one test that needs Rojo then fails
(`test_agent_corrects_recipe_and_unwinnable_plan_before_building`). That is an
environment fault, not a code failure; see the runbook for the commands.

Native Studio: `list_roblox_studios` reported one instance without a place name and
`get_studio_state` answered "Place is not open", so no Studio step was run and nothing
was edited, saved or published.
