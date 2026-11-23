# Server gameplay system patterns

These patterns guide implementation and review. Adapt them to the game's actual
player count and requirements; they are not a guarantee of release readiness.

## Remote request contract

For every client-to-server remote, write down:

| Contract field | Review question |
| --- | --- |
| Intent | What action is the client requesting? |
| Authority | Which server-owned state proves the action is allowed? |
| Shape | Which exact argument types, fields, lengths, and ranges are accepted? |
| Context | Is the player alive, in range, eligible, and in the correct game phase? |
| Abuse budget | What is the per-player rate and worst-case work/memory per request? |
| Idempotency | What prevents retries or duplicate touches from awarding/spending twice? |
| Result | What state is committed, and how does the client learn the result? |

Avoid generic remotes such as `DoAction(actionName, arbitraryData)`. Prefer a
small number of typed, feature-specific requests and a single server validation
path for each state change. Do not echo client claims back as accepted outcomes.

## Profile ownership and persistence

Treat persistence as a server system with an explicit owner, lifecycle, failure
states, and recovery policy. DataStore calls are network operations: do not put
them on a per-frame, per-touch, or other high-frequency gameplay path.

### Profile lifecycle

1. Define a bounded schema with a `schemaVersion`, stable `UserId` key, typed
   defaults, field limits, and migrations from every version still in use.
   Validate and normalize loaded data before any gameplay system reads it.
2. On join, load through one profile service and mark the player `Loading`.
   Gameplay mutations remain unavailable until the profile is `Ready`. If load
   or migration fails, mark it `Unavailable`, communicate that state, and use a
   documented deny-entry or non-persistent fallback mode. Never let fallback
   defaults become an eligible save over data that could not be read.
3. Keep the authoritative session copy in server memory. Other server systems
   make bounded, validated mutations through that owner; they do not write the
   same player key independently. Replicate only the fields a client needs.
4. Save dirty state on a staggered periodic interval, on `PlayerRemoving`, and
   during `BindToClose`; save at critical checkpoints such as purchase
   fulfillment. Shutdown saves must have a bounded completion policy. Do not
   report a write as durable until the API confirms success.
5. Make load, save, release, and cleanup idempotent. A player leaving during a
   load must not create a late profile, and concurrent shutdown/removal paths
   must not save or release the same session inconsistently.

Use one or a small fixed number of deterministic keys per player. For updates
that depend on the stored value or can race across servers, use `UpdateAsync`;
its transform can be called again and must be deterministic, bounded, and free
of yielding or external side effects. A transform returning `nil` cancels the
write. Keep callbacks limited to inspecting and transforming the supplied
value. `UpdateAsync` consumes read and write budget, so minimize calls, batch
related changes, and inspect request budgets when designing save cadence.

### Concurrency, retries, and failure handling

If a player's data can be loaded by more than one live server, implement
session ownership in the same atomic key update as the data. Specify lock
acquisition, refresh/heartbeat, release, timeout, and crash recovery; refresh
the lock before expiry and never let an expired or foreign session write an
older snapshot. For a small experience where overlapping sessions are
explicitly prevented by another verified design, document and test that
assumption instead of adding a partial lock. Do not present a naive
last-write-wins save as safe against duplicated inventory or lost progress.

Wrap each request in `pcall`. Retry only transient failures with capped
exponential backoff and random jitter, with bounded attempts and total wait.
Keep requests ordered per key so a delayed retry cannot overwrite newer state.
Treat a failed response as an ambiguous outcome when a write may have reached
the backend; design the operation to be idempotent and reconcile by reading or
retrying the same logical update, not by blindly replaying a reward. Avoid
retrying invalid requests. Do not start every player's autosave on the same
server tick, and keep calls within Roblox's current read/write budgets.

### Test and operational gates

Test the persistence adapter with a fake store before connecting it to Roblox.
Then use a separately published test experience or isolated data store and
scope. Never enable Studio API access against production data: Studio accesses
the same data stores as the live experience. Exercise a new profile, current
and older schema, migration failure, corrupt values, unavailable service,
throttling, ambiguous writes, ordered retries, two servers attempting one
profile, disconnect during load/save, server shutdown with multiple dirty
profiles, and recovery after a crashed lock owner. Verify data in the test
experience and preserve logs/place version as evidence. A successful mock or
single-server Studio run does not validate live persistence or concurrency.

Before production, document key layout and limits, migration/rollback, data
retention and deletion, monitoring, operator recovery, and how purchases are
granted idempotently with receipt history saved before acknowledging them.
Roblox's sample player-data implementation is reference material, not a
drop-in production library; review its caveats and load-test any adopted design.

## Round state machine

Represent each round with one server-owned phase and generation ID. Centralize
transitions, reject events from a previous generation after reset, and make
resolution atomic so two players touching a finish simultaneously cannot grant
the same round outcome twice. Specify join/leave, empty/full server, timeout,
respawn, and shutdown behavior. Publish presentation events only after the
server commits the corresponding state.

## Required test matrix

- One client: normal start, full loop, loss, win, reset, respawn, shutdown.
- Multiple clients: simultaneous actions, shared pickups, late join, leave
  during a round, reward race, and server-wide notifications.
- Security: wrong type/shape, oversized payload, non-finite numbers, invalid
  ownership, impossible distance, wrong phase, spam, duplicate delivery.
- Data: no record, current version, old version, corrupt value, throttling,
  ambiguous write result, migration failure, shutdown with queued saves.
- Devices: target resolutions, touch/controller input where supported, join
  time, frame/memory budget, reconnect and network delay.

Mark tests as automated engine, manual Studio, service integration, or human
review. Never describe an unrun row as passed.

## Official Creator Hub references

- [Security and cheat mitigation](https://create.roblox.com/docs/scripting/security/security-tactics)
- [Securing the client-server boundary](https://create.roblox.com/docs/scripting/security/client-server-boundary)
- [Remote events and callbacks](https://create.roblox.com/docs/scripting/events/remote)
- [Data stores](https://create.roblox.com/docs/cloud-services/data-stores)
- [Data store best practices](https://create.roblox.com/docs/cloud-services/data-stores/best-practices)
- [Player data and purchasing systems](https://create.roblox.com/docs/cloud-services/data-stores/player-data-purchasing)
- [Data store error codes and limits](https://create.roblox.com/docs/cloud-services/data-stores/error-codes-and-limits)
- [Studio testing modes](https://create.roblox.com/docs/studio/testing-modes)
