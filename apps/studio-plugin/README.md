# apps/studio-plugin — the Studio client

The plugin opens a protocol session, submits a bounded place snapshot, and can
fetch one API-approved edit at a time. It shows the complete operation list in a
scrollable review panel and waits for a separate local **Apply** click. The
current execution subset creates `Folder`, `Model`, `Part`, and `WedgePart`
instances under `Workspace` (parts start anchored), then changes allowlisted properties on parts. Each
apply is recorded with Studio's `ChangeHistoryService` so the user can undo it.

It rejects script creation/source edits, deletion, reparenting, and playtests.
The matching API policy blocks those work items before approval or delivery.
The operator can derive an unapproved Studio proxy blockout from a validated
Blender scene recipe. It preserves object rotation and converts meshes and
curved primitives to oriented bounding boxes; each action stays within the
protocol's 100-operation limit. Those Parts remain ordinary declarative work
and receive the same review and local Apply gates.
The sandbox has a separate, restricted CST policy for generated scene-blockout
source, but the plugin accepts only declarative actions and does not apply or run
that source. Playtests need a disposable execution boundary.

## Optional local Studio client

This plugin is a separate optional compatibility route for projects that use
RGA's local operator API. It is not required for the agent-first product or its
remote Blender and Roblox MCP services. It also is not required to use Roblox
Studio's own native MCP: leave that user-owned connection configured as-is and
use it directly for supported work in the open place. RGA does not proxy or
recreate the native Studio connection. Remote RGA map validation remains a
fixed server-side tool and does not edit the user's open place.

## Install in Studio

The plugin package contains the main script, strict JSON parser, complete
protocol subset validator, and generated schema registry under `src/Protocol/`.
Install the prebuilt `.rbxmx` through
**Plugins → Manage Plugins → Install from File**. The user needs only Roblox
Studio; Rojo and rokit are needed only to build the package from source.
Earlier live smokes exercised plugin load, loopback handshake, snapshot, polling,
action review, and a bounded apply on disposable places (details below). The
current Rojo build in this checkout has not yet been installed and rechecked in
Studio; confirm its toolbar button and rerun the smoke before treating this
package build as runtime-verified.

The local API that the plugin talks to is a separate process (Python); it is
needed only for this optional compatibility route, not to open a generated place
file in Studio.

## Build the installable model (contributors)

To produce an installable model instead, install the pinned tools with
`rokit install`, then build:

```bash
rojo build apps/studio-plugin/default.project.json --output dist/rga-studio-plugin.rbxmx
```

In Roblox Studio, use **Plugins → Manage Plugins → Install from File** and
select the generated `.rbxmx`. The built plugin file is a local artifact; do not
commit it. Open the **Roblox Game Architect** toolbar widget, enter the
`PLUGIN_AUTH_TOKEN` from the local API process, and select **Fetch approved
action for review**. The port field defaults to `8787`; change it to match the
API's `API_PORT` if needed. The client always uses the loopback host
`127.0.0.1`. Studio may ask you to grant the plugin permission to contact the
local host. Roblox documents that Studio plugins can communicate with
`localhost` and `127.0.0.1` through `HttpService` ([HTTP service
documentation](https://create.roblox.com/docs/cloud-services/http-service)).

Queue and approve actions from the API operator process before fetching them.
Review the full action in Studio, then apply or reject it. The plugin holds the
token only in memory while it fetches and reports the action; it clears the
entry field after fetching and clears its in-memory copy after the result is
settled. The token is visible while entered. The LLM provider key never belongs
in this plugin.

## Snapshot and apply bounds

The initial snapshot walks a fixed set of common services breadth-first. It
includes at most 2,000 entries, stops at depth 16, and keeps the encoded request
below 800 KB. It records only the property allowlist from the protocol. If a
name is empty, duplicated among siblings, or outside the protocol's bounds, or
if entry/byte/depth limits are reached, the snapshot is marked truncated and
`complete_depth` stays at the deepest fully represented level. Script source is
never read.

Before applying an action, the plugin checks every reference and name conflict
against the live place, then repeats the relevant path, class, and collision
checks immediately before each change. The application loop does not yield.
Before showing the review controls, it also validates the received action's
closed field shapes, operation and scope bounds, unique operation IDs, supported
classes, property values, and declared-scope coverage. Unsupported operations
fail closed in the plugin even if a malformed server response reaches Studio.
Project-supplied names and path segments in the review panel are quoted and
escaped to printable ASCII, so control and bidirectional formatting characters
cannot imitate extra review lines or reorder their text.
If an operation throws after changes begin, the result is `indeterminate`, the
plugin stops the action, and the API lock prevents more work until human
recovery. A lost result or snapshot response also disables further apply from
that plugin session; do not click Apply again.

## Remaining Studio gates

- Connect the restricted Luau scene-blockout policy to a source review flow if
  source delivery is enabled. The current plugin remains declarative-only.
- The operator panel now groups generation, Blender, Roblox validation, and
  Studio queue events into workflow timelines, including per-call model usage
  traces. Live agent reasoning and playtest streaming remain unavailable until
  those stages produce bounded, reviewable runtime events.
- Keep script execution and playtests disabled until an isolated place/run
  boundary and recovery behavior can be exercised in Studio.
- Live smokes on the installed Roblox Studio build verified plugin load,
  loopback API handshake, bounded snapshot upload, poll, and action review on
  fresh disposable places. An apply smoke created a Part and applied its size
  and position, then stopped at Color readback: for requested RGB
  `(0.1, 0.8, 0.4)`, Studio returned `(0.098039, 0.8, 0.4)`. The plugin reported
  requested and actual channels, marked the action indeterminate, and engaged
  the API lock as designed. The readback value is exactly `25/255`; the plugin
  now checks the measured 8-bit channel representation with a strict `0.00001`
  comparison instead of the previous exact-float comparison. A second fresh
  disposable-place smoke applied `(0.234, 0.567, 0.891)` and verified a closed
  `applied` result plus the after-action snapshot in the API audit. All five
  operations (create, size, position, color, orientation) completed. This
  confirms the floor-to-8-bit readback rule for these measured values, not every
  color or Studio release. Roblox documents `BasePart.Color` as a Color3
  property and says BrickColor derives its closest match
  ([BasePart reference](https://create.roblox.com/docs/reference/engine/classes/BasePart)).
  Verify the supported Studio version matrix as well; the Rojo build alone
  checks packaging only.

The project does not publish places. Publishing is always a manual human action.

## Toolchain

| Tool | Purpose |
|---|---|
| Rojo | Build the plugin model from Luau source |
| selene | Luau linting |
| StyLua | Luau formatting (tabs, per `.editorconfig`) |
| TestEZ | Luau unit tests, under `tests/` when added |

Versions are pinned in [`aftman.toml`](../../aftman.toml) (read by Rokit). Never
commit `.rbxl`, `.rbxlx`, `.rbxm` or `.rbxmx` place/model files; generated files
belong in the ignored `dist/` directory. CI lints and formats the Luau source,
then builds the pinned Rojo project and checks that it produces a non-empty
`.rbxmx` with `RunContext=Plugin`; this verifies packaging metadata, while the
Studio runtime smoke verifies that the local plugin appears and opens.
