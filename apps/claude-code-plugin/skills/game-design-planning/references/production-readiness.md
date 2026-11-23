# Roblox production and release readiness

Use this checklist when a brief asks for a production-ready game, a public
release, live operations, monetization, or saved progress. Tailor it to the
actual game and target audience. Mark inapplicable areas with a reason; do not
turn this checklist into boilerplate milestones for a prototype.

## Plan the release boundary

- Name the intended client platforms, device tiers, regions, languages, player
  audience, concurrency range, and release channel (private test, early test, or
  public release). Record the assumptions that affect design and test scope.
- Separate what a player can do in the first playable slice from launch-only
  requirements. Convert each launch requirement into an owner, a test method,
  and observable evidence. Keep the current Game Plan's `included_systems` and
  `deferred_systems` partition exact.
- Treat publishing permissions, content maturity answers, asset rights, and
  platform review as human-owned release gates. Automation can prepare evidence
  but cannot certify policy compliance or approve a public release.
- For generated 3D assets, retain structural validation receipts for meshes,
  textures, rigs, and animations, then inspect representative imports in Roblox
  Studio for rendering and intended use. Structural checks cannot certify
  topology, visual quality, animation quality, or successful runtime rendering.
  Record both the automated preflight and the human Studio review.

## Server authority and abuse cases

- Keep currency, rewards, inventory, purchases, health, match outcomes, and
  progression decisions authoritative on the server. The client can request an
  action or render feedback; it cannot decide the result.
- For every client-triggerable RemoteEvent, RemoteFunction, ProximityPrompt,
  ClickDetector, or DragDetector, define server checks for type and structure,
  size, value range, permission, player state, distance, timing, and rate limits
  as relevant. Assume client-set prompt properties and client-side cooldowns
  can be bypassed.
- Bound remote payload size and work per request. Never accept arbitrary paths,
  asset IDs, code, instance references, or resource names as authority to load,
  require, delete, award, or mutate server state.
- Include abuse cases in the test plan: replayed requests, duplicate touches,
  NaN/infinite values, malformed or oversized tables/strings, spam, respawn or
  disconnect during a transaction, and attempts to act out of range or while
  dead. Select only cases the feature actually exposes.

## Persistence, commerce, and recovery

- If progress persists, define a versioned data schema, stable user-ID keys,
  default and corrupt-data behavior, migration and rollback steps, and the
  acceptable loss window. Keep client input out of trusted saved data.
- Budget data-store calls. Load into server memory, save at planned checkpoints
  and on lifecycle events, use `UpdateAsync` when changes depend on existing
  state or multiple servers can write, and apply bounded retries with backoff
  and jitter for transient failures. Serialize requests per key so stale retries
  cannot overwrite newer data.
- For trades, purchases, rewards, and grants, define idempotency and duplicate
  processing behavior. Use Roblox's current server-side receipt API and test
  incomplete, retried, and repeated receipt delivery before launch.
- Use a separate test experience and data scope for migrations, reset/rollback,
  and failure injection. Never validate persistence by writing test records to
  live player data.
- If monetization or policy-gated features exist, check current Creator Hub
  requirements for eligible users and regions, use server-side receipts and
  policy checks, and test the ineligible or unavailable path. Make pricing,
  reward odds, and player-facing terms clear for the intended audience.

## Playability, performance, and operations

- Test full sessions with multiple players, reconnects, low-latency and
  high-latency conditions, empty and full servers, late joiners, and relevant
  edge cases. Record which scenarios were automated and which were manual.
- Test the actual target device classes, aspect ratios, input methods, and
  network conditions. Define experience-specific frame-time, memory, join-time,
  and server-cost budgets before optimization, then profile a representative
  assembled place. Source-level object counts are not performance evidence.
- Check the first session from install/join to exit: onboarding, controls,
  objective clarity, accessibility, readable feedback, recovery after failure,
  and whether the experience works without relying on color or audio alone.
- For social, chat, user-generated content, trading, or creator tools, plan
  abuse prevention, reporting and moderation boundaries, and safe defaults.
- Define telemetry needed to detect broken progression, failed purchases,
  elevated errors, poor performance, and drop-off. Avoid collecting unnecessary
  personal data; document retention and access for any data the game stores.
- Prepare a release candidate, a human-reviewed content and asset inventory,
  rollback path, incident owner, and post-release monitoring window. Test the
  rollback path before public launch.

## Report evidence precisely

In the plan, make each applicable release check specific enough to reproduce:

`feature or risk → test setup → action → expected result → evidence → owner`.

Distinguish schema and static checks, deterministic template simulation, Roblox
engine tests, Studio manual playtests, multi-device/network testing, platform
policy review, and public-release approval. A pass at one level does not imply
the next. If the required live service, test experience, device, permission, or
human reviewer is unavailable, record the gate as pending and continue with
independent work.

## Authoritative references

Use the current Creator Hub pages linked from
`references/research-sources.md` for security, data stores, performance,
content maturity, publishing, and monetization. Policies, API limits, and
publishing eligibility can change; check them again against the target game and
account before a release.
