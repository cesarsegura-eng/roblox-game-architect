# ADR-0018: Remote Roblox map authoring boundary

- **Status:** Accepted
- **Date:** 2026-11-05
- **Deciders:** project owner

## Context

The project should use a separately hosted MCP service for external authoring
tools where a server API supports the operation; users should not need Blender
or a Roblox-specific authoring executable installed merely to generate a map.
The remote Roblox service builds complete `.rbxlx` artifacts and can validate
bounded recipes against a disposable place. It does not provide incremental
editing of an existing place; the optional local Studio plugin is a compatibility
route, not a product prerequisite.

Roblox documents two possible server-side write paths:

- [Place Publishing](https://create.roblox.com/docs/cloud/guides/usage-place-publishing)
  uploads a complete `.rbxl` or `.rbxlx` file to a selected place as a published
  version. It requires an API key with `universe-places:write`. This replaces
  the place DataModel with the submitted file; it is not an incremental Part
  editing API. Roblox also documents that this path does not update several
  instance types, including `EditableMesh`, `PartOperation`, and
  `SurfaceAppearance`.
- [Engine Instances](https://create.roblox.com/docs/cloud/guides/instance) is a
  Beta API, but the documented current limit permits reading/updating
  `Script`, `LocalScript`, and `ModuleScript` instances only, with
  collaborative editing enabled. It cannot create the Part hierarchies needed
  for map authoring.

The built-in Roblox Studio MCP is a local `stdio` process attached to an open
Studio session. It is not a remotely hosted server. Luau Execution is server
hosted but runs code with DataModel access, so it remains restricted to the
repository-owned fixed validation harness from ADR-0015.

## Decision

1. **Keep remote Blender MCP as the normal 3D authoring route.** It creates
   reviewable GLB artifacts on a separate server and needs no local Blender.
2. **Do not treat Roblox Studio MCP or Luau Execution as remote map editors.**
   The former is local `stdio`; the latter is code execution and remains fixed-
   harness validation only.
3. **Remote Roblox authoring generates a complete data-only place file first.**
   `rga_build_place` compiles a validated Scene Recipe with pinned Rojo 7.7.1,
   returns a script-free `.rbxlx` and SHA-256 digest, and never uploads it. This
   file is a separate complete place, not a merge into an existing experience.
4. **Place Publishing is an explicit, separately approved operation.** It
   must be a fixed MCP tool with a server-configured universe and place,
   production-ID deny lists, a server-only `universe-places:write` key, a
   reviewable digest of the exact place file, durable idempotency, and an
   operator action bound to that digest. A successful upload publishes a new
   place version and can affect players; a generic agent request is not
   sufficient approval.
5. **Keep the local Studio plugin as an optional compatibility route.** It
   remains useful for reviewing and applying bounded changes to an already open
   place, but it is not a dependency of the remote Blender workflow.
6. **Keep production publishing disabled.** The fixed remote publisher may
   target only the server-pinned disposable test place, after the user reviews
   the exact artifact digest and fixed destination and explicitly approves the
   operation. Opening the artifact in Studio is optional additional review and
   is not a dependency of the remote agent workflow. Keep even the test-place
   deployment gate closed until the target's isolation and restoration path
   are verified. A fake transport or XML-only test does not establish that
   Roblox accepts the file or that the final DataModel is correct.

## Consequences

- The remote Roblox MCP has fixed place-build and validation tools. A separate
  opt-in fixed publisher can update only the pinned disposable test place after
  a digest-bound operator approval; production targets remain impossible.
  Deployment still needs a separately hosted service, Rojo, and operator
  credentials; those are not supplied by this repository.
- Remote Blender MCP returns GLB without requiring Blender on the user's PC.
  Remote Roblox place build returns RBXLX without requiring Studio on the user's
  PC. The product workflow uses separately hosted MCP services; local Studio
  inspection and the plugin remain optional compatibility paths.
- The publisher uses a separate `universe-places:write` credential and approval
  secret; neither is shared with the disposable validation key.
- Production publishing is not enabled by this ADR; it requires a later design
  with explicit publishing scope, review, staging, and verified rollback.

## Acceptance evidence and remaining runtime verification

- [x] A bounded Rojo serializer emits a data-only place file with no scripts,
  source, or caller-selected class names; focused tests cover mapping and bounds.
- [ ] Roblox Studio opens a generated artifact and confirms the final DataModel.
- [x] The remote build has no place target or publishing credential, enforces
  bounded input/output, and returns a digest that the API client verifies.
- [x] The optional test-place publisher has a fixed server-side destination,
  separate publishing credentials, a digest/target-bound short-lived approval,
  a durable idempotency ledger, and an operator route that accepts only an
  artifact created and retained by the API. Fake-transport tests confirm the
  signed request and recovery/no-resubmit behavior.
- [ ] A staging import and rollback are exercised against a real test
  experience before the remote publisher is deployed; production publishing
  remains disabled.

## References

- [Roblox Place Publishing guide](https://create.roblox.com/docs/cloud/guides/usage-place-publishing)
- [Roblox Engine Instances guide](https://create.roblox.com/docs/cloud/guides/instance)
- [Roblox Studio MCP guide](https://create.roblox.com/docs/studio/mcp)
- [ADR-0015](0015-disposable-world-validation.md)
