# ADR-0015: Isolated world validation and Luau execution

- **Status:** Proposed
- **Date:** 2026-11-05
- **Deciders:** project owner
- **Supersedes:** none

## Context

The fixed-recipe Open Cloud adapter and harness are implemented, but Gate 3 is
not operationally verified. The Studio plugin applies a narrow, script-free
action subset to the open place. Neither it nor the adapter runs generated game
Luau, and the API rejects playtest work until isolated-runtime evidence is
recorded and the supported harness scope is verified against Roblox.

Roblox now documents two relevant facilities:

- [Open Cloud Luau Execution](https://create.roblox.com/docs/cloud/reference/features/luau-execution)
  runs a submitted script with access to the target place's DataModel, accepts a
  place version, and returns task state, results, and logs. Tasks can run for up
  to five minutes. The script can also call engine APIs such as
  `AssetService:SavePlaceAsync()`.
- [StudioTestService](https://create.roblox.com/docs/reference/engine/classes/StudioTestService)
  can drive play and multiplayer tests from a Studio plugin. It operates on the
  Studio test session spawned from the currently open place.

Neither facility is an isolation boundary by itself. Selecting a version does
not prove that the place contains no scripts, secrets, or live integrations;
Studio's play session is derived from the open place. A generated script must
therefore not be submitted to either facility under this ADR.

## Decision

1. **World-map validation may use Open Cloud only against a separately provisioned
   test universe and place.** The API must require explicit test universe, place,
   and pinned place-version configuration. It must fail closed when any value is
   absent, malformed, or equal to a configured production target.
2. **Only a repository-controlled Luau harness may be executed.** The generated
   scene recipe is strict, bounded JSON data consumed by that harness. Recipe
   fields must never be interpolated into executable Luau source.
3. **The test place must be provisioned and reviewed as disposable.** It must
   contain no user game scripts, production secrets, live data stores, or external
   integrations. The harness must not call `SavePlaceAsync`, publish, or perform
   network requests. Each test begins from a pinned place version. Before relying
   on the service, verify that task execution cannot persist DataModel changes;
   do not assume timeout or task completion rolls them back.
4. **Execution is version-scoped, bounded, and observable.** Pin the place version,
   set the shortest useful task timeout, poll only the returned task path, bound
   and validate logs/results, and record task identity and outcome in the local
   audit history. Treat task output as untrusted data.
5. **Generated Luau remains blocked.** Enabling generated source execution needs
   a separate ADR covering a complete source policy, service capabilities,
   network denial, data-store isolation, and approval bound to the reviewed
   source digest. A restricted test universe alone does not make arbitrary code
   safe.
6. **StudioTestService is an optional local validation route, not Gate 3.** It may
   be offered for a user-initiated test of a place they explicitly opened. It
   cannot be described as disposable unless the plugin can establish and verify
   an isolated source place before starting the test.

## Consequences

- The next safe playtest increment is deterministic validation of generated
  geometry and navigation using the fixed harness, not execution of model-written
  game scripts.
- A live implementation requires the owner to provision a dedicated Roblox test
  universe, an empty test place, and an Open Cloud key scoped to that universe
  and only the required execution/log permissions. The API must keep that key
  server-side.
- The current `playtest.request` path remains disabled. The fixed map-validation
  MCP tool is a separate operation and requires explicit test-target
  configuration, a pinned version, production-ID guards, an API key on the
  remote server, and live evidence that execution leaves production and the
  pinned place version unchanged.
- The existing Studio plugin can continue to apply reviewed declarative edits;
  that workflow is separate from remote test-place validation.

## Acceptance criteria for implementation

- Unit tests reject production/missing/malformed target configuration and prove
  that the submitted Luau source is constant for all recipe inputs.
- Contract tests cover create, poll, timeout, failed task, malformed output,
  bounded logs, and retry without resubmitting a different task body.
- A disposable Roblox test universe is exercised with a pinned empty-place
  version; execution is proven not to persist changes, and its original version
  and production place remain unchanged.
- CI verifies the fixed harness against representative biome, interior/exterior,
  and navigation fixtures. Runtime playability claims require Roblox-engine
  evidence and remain separate from structural tests.

## Implementation status

`apps/roblox_mcp_server` exposes only `rga_validate_map`. Its Open Cloud client
uploads recipe JSON as binary input, submits only the checked-in harness to the
pinned place version, bounds polling and receipts, and stores request IDs so an
uncertain task is never resubmitted. The operator API and UI can request this
validation after recipe review. Automated transport tests use a fake Cloud
backend. No Roblox universe, Open Cloud key, task result, persistence proof, or
live engine validation is configured in this repository environment; the
integration is implemented but not verified for operational use.

## References

- [Open Cloud Luau Execution](https://create.roblox.com/docs/cloud/reference/features/luau-execution)
- [Open Cloud permission scopes](https://create.roblox.com/docs/cloud/reference/scopes)
- [StudioTestService](https://create.roblox.com/docs/reference/engine/classes/StudioTestService)
- [Studio testing modes](https://create.roblox.com/docs/studio/testing-modes)
