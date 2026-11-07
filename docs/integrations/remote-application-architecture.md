# Remote application architecture

Roblox Game Architect connects to external tools through server-side adapters
where the target application supports it. The user's computer does not need to
install any content-authoring application or extension for the product
workflow, or host an MCP service. The user equips an existing agent with the
project's skills and connects its MCP client to separately hosted services; the
agent plans, invokes tools, and reports reviewable results. The optional RGA
operator surface supports development and review. Local Studio plugins and
Blender extensions remain optional compatibility, development, or inspection
paths and must not become prerequisites for remote workflows.

## Blender

The standard Blender path is a remote MCP service on a separate server. That
server owns Blender 5.2.3, validates the data-only scene recipe, renders it in
a bounded worker process, and returns a GLB artifact by ID. The API connects to
the service over authenticated HTTPS. The optional local Blender extension is
for users who want to author assets on their own machine; it is not a runtime
dependency. The operator panel can check that the service is reachable and
exposes the fixed recipe tool without building a scene. See the
[deployment guide](blender-remote-mcp.md).

The agent's dedicated `blender-scene-authoring`, `world-environments`, and
`character-modeling-animation` skillpacks provide design guidance. They shape
the validated recipe; they do not install or operate Blender on the user's
computer. The separate MCP service is the execution tool: it accepts the
bounded recipe, runs the trusted Blender worker, and returns an artifact. The
same split applies to research references: curated, attributable sources inform
the skillpacks, while the MCP contract provides the capability to build the
result.

## Roblox

The operator can convert a validated Blender scene recipe into up to 14
oriented Roblox Part proxies, subject to the protocol's 100-operation cap. The
conversion preserves object names, roles, rotation, material colors, and
approximate bounds, swaps Blender Z-up to Roblox Y-up, and drops geometry
outside the strict blockout bounds. If more than 14 objects fit,
it prioritizes paths, entries, landmarks, terrain, and building forms, preserving
source order within each role. Mesh detail becomes bounding boxes; the result is
a layout proxy, not an imported GLB. The action enters the
ordinary unapproved queue and needs API approval before it enters an
agent-visible action queue. Applying proxy edits through this compatibility
path still requires a local Studio session; remote builds and test-place
publishing use the Roblox MCP service instead. Out-of-bounds objects, lights,
and character rigs are reported as omitted; use the remote Blender GLB workflow
for the full scene and character geometry.

Roblox has two separate integration surfaces:

- The official [Roblox Studio MCP server](https://create.roblox.com/docs/studio/mcp)
  is built into Studio, runs locally over stdio, and targets the user's open
  Studio session. The current RGA Studio plugin likewise applies explicitly
  reviewed, script-free actions in Studio. This route requires Studio on the
  machine that owns the working place; it is not a remotely hosted Studio MCP
  server.
- [Open Cloud Luau Execution](https://create.roblox.com/docs/cloud/reference/features/luau-execution)
  is Roblox's hosted route for headless tasks against a place and optional
  pinned version. It runs Luau with engine access, so it is not safe to expose
  as an arbitrary-code MCP tool. The RGA remote adapter accepts only bounded
  recipe data, submits a repository-controlled harness, requires a separately
  provisioned disposable test place and pinned version, and keeps the Open
  Cloud API key on the server. It does not proxy arbitrary scripts or silently
  switch to a live place.

The repository includes a remote Roblox MCP adapter at
[`apps/roblox_mcp_server`](../../apps/roblox_mcp_server/README.md). Alongside
the disposable-place validator, its `rga_build_place` tool compiles a reviewed
Scene Recipe with Rojo 7.7.1 into a `.rbxlx` artifact. The default is
script-free. Explicit Treasure Hunt and Obby Course modes add only their
respective fixed gameplay Script after validating recipe roles and route
requirements. `rule_game` accepts only a bounded `gameplay_rules` array for
touch score, healing, nonlethal hazard damage, elimination, and threshold-based
wins, then adds one fixed interpreter Script. The model cannot supply Luau. The API checks
the receipt and file digest; the operator
panel downloads it, while a direct agent receives the build artifact through
its MCP result. It creates a complete separate place file and does not merge
into an existing DataModel. The remote service still needs deployment and credentials;
live Open Cloud validation remains unverified against a disposable place. The
operator can check both fixed MCP contracts without building a scene or
submitting a Roblox task. See
[ADR-0015](../architecture/adr/0015-disposable-world-validation.md) and
[ADR-0018](../architecture/adr/0018-remote-roblox-map-authoring.md).

For direct use by an existing agent, the Roblox MCP host can also fetch a
UUID-addressed GLB from one fixed Blender MCP host. A read-only prepare tool
returns its digest and short-lived approval details; a separate confirmed tool
creates the Roblox Model asset, after which the same Roblox MCP can include an
approved asset ID in a script-free place build. GLB bytes move between the two
trusted servers and do not pass through the user's agent or computer. The asset
write requires explicit configuration, a two-step approval, and a scoped Open
Cloud asset key; real moderation and in-engine import remain unverified. See
the [remote Roblox MCP setup](../../apps/roblox_mcp_server/README.md#optional-reviewed-model-asset-upload).

Roblox's server-side Place Publishing API accepts a whole `.rbxlx` file and
replaces the published place version rather than merging map Parts into an
existing DataModel. The optional publisher is limited to one configured
disposable test place, requires an exact digest-bound approval, and has a
separate direct-agent prepare/confirm flow. Production publishing remains
disabled. Live Open Cloud writes and rollback still require isolated runtime
evidence. See [ADR-0018](../architecture/adr/0018-remote-roblox-map-authoring.md).

## Integration rule

An MCP endpoint is a transport, not a security boundary. Every adapter must
expose only the project's fixed, validated operations, keep third-party keys on
the server that needs them, bound inputs and outputs, and record a result that
can be reviewed. Do not expose a generic code-execution tool just because the
target application has an MCP server.
