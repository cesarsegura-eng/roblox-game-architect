# apps/web — optional local operator application

The current web surface is a small, dependency-free operator panel served by
`packages/api`, currently intended for local development and single-operator
review. It is optional: an existing agent can use the remote MCP services
directly and the end user's computer does not need this panel or API process.
It generates structured game plans, world scene recipes for
Blender, and constrained Studio map blockouts from briefs, shows lifecycle
status, lists queued work for review, submits script-free actions, and requires
a separate approval confirmation.
It reports whether the remote Blender and Roblox MCP endpoints are configured.
The operator can run a separate read-only check that confirms each endpoint
exposes the project's fixed MCP tool; the result is timestamped and does not
build a scene or run a Roblox task.

**Status: local operator surface and remote place-file build flow implemented.** Game plans are descriptive
JSON handoffs; they do not write code or change Studio. This is not the planned
agent workspace: there is no live plan stream or playtest view, and model traces
include per-run totals and per-call provider, model, token usage, and cost
without storing prompts or generated content. It displays the shared session spend, reservations,
cap, and remainder. Game-plan, recipe, Studio blockout, and scoped Luau preview
generation have first-call maximum-cost quotes plus a session hard cap. It uses browser-native HTML, CSS,
and JavaScript so the local API adds no framework dependency.

## Intended responsibilities

- **Implemented:** quote game-plan, recipe, Studio blockout, and bounded Luau source preview first calls, then
  generate a validated plan or scene recipe from a brief under the configured
  spend limit; download the plan JSON or scene recipe for reuse; show API
  session/lock and spend state, queued work, and the newest 100 lifecycle and
  model-generation audit events grouped into scene-workflow timelines by their
  shared workflow ID;
  display each queued action's complete JSON; queue an action; separately
  approve its ID; generate and queue a bounded Studio blockout with the same
  brief, or convert a reviewed scene recipe into up to 14 oriented Studio
  proxy Parts without another model call, prioritizing navigation and building
  roles when the 14-Part cap applies; either route queues work for review
  and never approves or applies it, with the scene run UUID carried as a shared
  workflow ID across remote Blender, Roblox validation, and Studio queue audit
  events for traceability and retry recovery;
  preview scoped Luau only after the exact static scene-blockout policy passes,
  without queueing, executing, or delivering that source to Studio;
  check configured remote MCP endpoints for reachability and
  their fixed tool contract; optionally apply a reviewed Blender recipe or
  build and download a bounded `.rbxlx` through configured remote MCP servers,
  with script-free, Obby Course, Treasure Hunt, and bounded data-rule modes;
  when the separately configured test-place publisher is available, inspect
  that exact download in Studio and approve a second, digest-bound publication
  action to the pinned disposable test place. Production publishing stays off.
  Game Plan v2 reports a bounded first-build mode, validated data-only rules for
  `rule_game`, and included/deferred system sets. "Set up map build" carries
  those rules into the world-brief handoff and later remote build request; the
  fixed interpreter receives data, never model-authored Luau. Scene-role checks
  validate whether the generated recipe supports each trigger. The
  Studio blockout checks required feature
  labels and basic elongated route geometry before it is queued.
  The plan view can also request a separate release-readiness report with nine
  explicit, evidence-oriented gates; all start pending, and owners must decide
  whether persistence, commerce, and multiplayer apply. It never certifies a
  Roblox runtime, policy review, or release.
- **Remaining:** general model-authored gameplay remains gated on the broader
  source-policy and disposable-execution controls. Game Plan rules configure
  only the fixed actions supported by `rule_game`.

## Boundaries

- It talks only to `packages/api` over HTTP. It never talks to an LLM provider
  and never holds a provider key.
- It enforces nothing. Approval gates, spend caps and validation all live
  server-side, so a different front end cannot bypass them. The UI presents
  those controls; it is not where they live.

## Local use

Set `OPERATOR_AUTH_TOKEN` to a separate 32–512 character printable ASCII secret,
then start the API. To enable recipe generation, also set a supported real LLM
provider and its spend cap; the operator route shares the API process's bounded
world-generation budget. Open the exact `http://127.0.0.1:<port>/` URL printed
by the server. The panel keeps the token in memory for the open tab and sends it
only to same-origin loopback endpoints. The API requires the exact loopback
Host and same-origin Origin, serves a restrictive Content Security Policy, and
has no CORS policy. Leave the operator token unset to disable all operator
endpoints.

The panel never receives an LLM key or the Studio plugin token. A generation
click sends only the brief; the provider key remains in the API process. API
validation still rejects scripts, deletion, reparenting, and playtests. Approval
does not apply an edit by itself: the Studio plugin presents the action and asks
for a separate local Apply/Reject decision. Recipe downloads can be imported
through the Blender extension; they are not automatically inserted into a
local Blender or Studio project. A configured remote Blender MCP import is a
separate explicit review and confirmation step. If the reply is uncertain, the
panel keeps that recipe's request ID so retrying in the same tab recovers the
same remote artifact without building it twice.
