# The backend ↔ plugin contract

`packages/protocol` owns every message that crosses the Python/Luau boundary.
This document is the specification of version **1.0** of that contract. The
schemas in [`packages/protocol/schemas/v1/`](../../packages/protocol/schemas/v1/)
are authoritative; where this text and a schema disagree, the schema wins and
this text has a bug.

Rationale: [ADR-0006](../architecture/adr/0006-protocol-single-source-of-truth.md)
(why a package), [ADR-0007](../architecture/adr/0007-plugin-initiated-http-transport.md)
(transport), [ADR-0008](../architecture/adr/0008-edit-action-flat-operations.md)
(the shape of edits) and [ADR-0009](../architecture/adr/0009-luau-validation-subset-and-strict-json.md)
(how both sides validate).

## Status

| | State |
|---|---|
| Schemas v1.0 (20 files) | written |
| Vectors (52 valid, 148 invalid, 42 parse) | written |
| Python reference checks (`packages/protocol/tests/`) | written; pass locally |
| CI | **not verified**: the workflows have not run on this change |
| Studio plugin validation | strict parser and closed-subset envelope/payload validator pass all shared parse and valid/invalid schema vectors under Lute; installed Roblox Studio runtime validation remains |
| `approval.request`, `run.log` (API → web) | deferred; adding a message type is compatible |
| [ADR-0011](../architecture/adr/0011-delivery-execution-and-recovery.md) | proposed; its wire changes and API lifecycle, durable lock, result records and recovery attestation are implemented and exercised by API tests; Studio runtime recovery still needs validation |
| [ADR-0010](../architecture/adr/0010-script-execution-reach-and-action-semantics.md), [ADR-0012](../architecture/adr/0012-untrusted-text-and-unicode-rendering.md), [ADR-0013](../architecture/adr/0013-conformance-suites.md) | **proposed; not applied** to the schemas, vectors, reference checks or the sections named below |

**What is applied and what is not.** ADR-0011's changes to the wire are **applied**:
`unknown_action` is now `unknown_work`, `result_conflict` exists, `indeterminate`
means *at least one* operation is `unknown` with the applied ones before it and the
skipped ones after, and the section *Idempotency and recovery* below describes
that model. API state machines, the lock, durable records and recovery
attestation are implemented; Studio runtime recovery still needs validation.

ADR-0010 (script execution reach and action semantics), ADR-0012 (untrusted text and
Unicode rendering) and ADR-0013 (conformance suites) call for changes to the schemas,
the vectors, the reference checks and this document that have **not** been made.
Until they are applied, the schemas as written remain the contract of the wire, and
where the sections *Scripts*, *Untrusted content* and *Conformance* below differ from
those records, the records state the intended decision and this text is the one to be
corrected.

Every record from ADR-0010 to ADR-0014 is **`Proposed`**: nothing in them is
approved, and the decisions each one leaves open are listed in its own *Pending
decisions*.

## Why a package and not a folder

The plugin and the API are written in different languages, released on different
cadences, and updated by different means — the API updates when the user pulls,
the plugin updates when the user installs it into Studio. Two independently
drifting definitions of the same message is the most expensive failure mode this
project has. So the contract gets a single owner, a version, and a schema that
both sides validate against.

## Rules

1. **Schemas are the source of truth.** Not the Python types, not the Luau
   tables. Both are derived from or validated against the schema.
2. **Every message carries a protocol version.** The plugin may be older than
   the API. Version negotiation is explicit (see *Handshake*).
3. **Additive changes only within a major version.** New optional fields are
   fine. Removing a field, renaming one, or narrowing a type is a major bump.
   See *Compatibility* for what "additive" means mechanically.
4. **Both sides validate.** The API validates what the plugin sends; the plugin
   validates what the API sends. A malformed message is rejected and logged, not
   coerced.
5. **No transport assumptions in the schema.** The channel is plugin-initiated
   HTTP with long-polling ([ADR-0007](../architecture/adr/0007-plugin-initiated-http-transport.md)),
   but the message shapes must not depend on that.
6. **A schema change is a reviewable diff of its own.** Protocol changes do not
   ride along inside feature PRs.

## Message types

Five message types travel in envelopes. Two more — `edit.action` and
`playtest.request` — are *work items*: the API cannot call the plugin, so they
arrive inside the response to `work.poll`.

| Type | Direction | Envelope | Purpose |
|---|---|---|---|
| `session.hello` | plugin → API | request, response | open a session, negotiate the version |
| `work.poll` | plugin → API | request, response | the long-poll; the response carries at most one work item |
| `project.state` | plugin → API | request, response | a bounded snapshot of the open place |
| `edit.result` | plugin → API | request, response | what actually happened to an `edit.action` |
| `playtest.report` | plugin → API | request, response | output of a playtest |
| `edit.action` | API → plugin | work item | one validated, approved change to apply |
| `playtest.request` | API → plugin | work item | run a test, with what to collect |

Every plugin request gets a response from the API. The API never sends a
request, so the plugin never sends a response, and an invalid response is
discarded locally as a transport failure.

## The envelope

| Field | Where | Meaning |
|---|---|---|
| `protocol_version` | every message | `{major, minor}`; after the handshake, the negotiated version |
| `kind` | every message | `request` or `response` |
| `type` | every message but an untyped error | one of the five envelope types |
| `message_id` | every message | the sender's identifier for this message (1–64 characters, opaque) |
| `correlation_id` | responses | the `message_id` of the request being answered |
| `session_id` | every message after the handshake | assigned by the API in the `session.hello` response |
| `status` | responses | `ok` or `error` |
| `sent_at` | optional | Unix milliseconds; informational, clocks are not trusted |
| `payload` | every message | an object, validated against the schema its type, kind and status select |

`correlation_id` pairs a response with its request. It is *not* the link between
an `edit.action` and its `edit.result`: that is `action_id`, because the action
arrived inside a `work.poll` response and the result is a new request.

There is **no `null` anywhere in the protocol**. Luau tables cannot hold `nil`,
so a JSON `null` would silently delete its key. "Absent" is how a value is
absent: a `work.poll` response without `work` means *no work yet*, which is not
an error and not a failure.

## Validating a message

The same procedure on both sides. Each stage that fails ends the procedure.

1. **Size.** More than 1,048,576 bytes → reject, before decoding anything.
2. **Parse** under the strict JSON profile below. Failure → stage `parse`.
3. **Dispatch.** `kind` must be `request` or `response`, else the culprit is
   `/kind`. A response without a `type` is an untyped error (`envelope.error.json`).
   Otherwise `type` must be one of the five (`version.json`), else the culprit is
   `/type`. `session.hello` uses `envelope.hello.<kind>.json`; every other type
   uses `envelope.<kind>.json`. Failure → stage `dispatch`.
4. **Envelope.** Validate against the selected envelope schema. Failure → stage `envelope`.
5. **Payload.** A request is validated against `messages/<type>.request.json`; a
   response with `status: ok` against `messages/<type>.response.json`; a response
   with `status: error` against `error.protocol.json`. Failure → stage `payload`.

The envelope leaves `payload` opaque so that no `oneOf` is needed to choose a
payload schema: the dispatch table is the file names.

### How a failure maps to a protocol error

| Failure | `ProtocolError` code |
|---|---|
| parse, `/kind`, envelope, payload | `invalid_message` |
| dispatch at `/type` | `unknown_type` (answered with an untyped error) |
| `protocol_version` differing from the negotiated one | `unsupported_version` |
| unknown or expired `session_id` | `session_expired` |
| missing or invalid credential | `unauthorized` |
| a result for a work id not in a state that accepts one | `unknown_work` |
| a result different from the one already recorded | `result_conflict` |
| anything else on the API's side | `internal` |

## The strict JSON profile

Standard parsers disagree on inputs that matter here. Python's `json` accepts
`NaN`, `Infinity` and `1e999`, keeps the last of two duplicate keys, and accepts
lone surrogate escapes. Roblox's `HttpService:JSONDecode` is undocumented on all
of these and, because Luau tables cannot hold `nil`, cannot represent `null`.
So both sides parse under one profile, and a message that does not satisfy it
never reaches schema validation.

A message is a JSON text (RFC 8259) that is **UTF-8 without a byte order mark**
and whose top-level value is an object, with these additional rules:

| Rule | Reason code |
|---|---|
| at most 1,048,576 bytes | `size_exceeded` |
| valid UTF-8 | `invalid_utf8` |
| valid JSON grammar: no leading zeros, hex, `+`, `.5`, `1.`, trailing commas, single quotes, unquoted keys, raw control characters in strings, trailing content | `invalid_json` |
| the top-level value is an object | `not_object` |
| no duplicate key in any object, compared after decoding escapes (`"a"` and `"a"` collide) | `duplicate_key` |
| no `null` anywhere | `null_value` |
| no number that is not finite as an IEEE double (`NaN`, `Infinity` are not JSON; `1e999` is valid grammar and still rejected). `1e-999` underflows to 0 and is allowed | `non_finite` |
| an integer literal (no `.`, no exponent) has an absolute value of at most 2^53 | `integer_out_of_range` |
| no lone surrogate in a key or a string (a valid `😀` pair is fine) | `lone_surrogate` |
| container nesting depth at most 12 (the top-level object is depth 1) | `depth_exceeded` |

`1.0` and `1` are the same number: Luau cannot tell them apart, so a validator
may not either. String lengths are counted in Unicode code points, not bytes
(Luau: `utf8.len`).

The reference implementation is `packages/protocol/tests/protocol_strict_json.py`
and is **test-only**. The API will need a parser of its own; the Luau parser is
described in ADR-0009 and does not exist yet.

## Handshake

`session.hello` is the only message sent before a `session_id` exists.

**Request.** Framing is `protocol_version: {1, 0}`, exactly, with no `session_id`.
Payload: `client: {name, version}` and `supported`, between 1 and 8
`{major, max_minor}` entries.

**Negotiation.** The API picks the highest major both sides support. The
negotiated minor is the lower of the plugin's `max_minor` and the API's for that
major.

**Accepted.** The response is `status: ok`, carries the new `session_id` in its
envelope (that is the only way to learn it) and `payload: {negotiated: {major,
minor}, server: {version}}`. Framing is again `{1, 0}`.

**No common major.** `status: error`, `unsupported_version`, **no** `session_id`,
and `details.supported` listing what the API supports. Credential failures are
answered the same way with `unauthorized`.

**The hello is frozen.** Both of its envelopes and both of its payloads are
immutable: the framing version is the constant `1.0` forever, and no field is
ever added to them. Information that should be exchanged at connect time in a
later version goes in a later message, after the session exists. A hello in this
framing must always be answerable, whatever majors exist.

**From the accepted response on**, every message in both directions carries the
`session_id` and the negotiated `protocol_version`. The session is a correlation
context, **not a credential**.

**Credentials** travel in the transport (an HTTP header carrying
`PLUGIN_AUTH_TOKEN`), on *every* request, never in a message. That keeps secrets
out of anything the protocol logs and keeps the schemas free of transport
detail ([ADR-0005](../architecture/adr/0005-credentials-and-thin-plugin.md)).

**A session can end at any time** (the API restarts, it expires). The next
request is answered `session_expired`, and the plugin sends `session.hello`
again. There is no goodbye message.

## Work delivery

The plugin polls only when idle: it has no action in flight. A `work.poll`
response carries zero or one work item. Zero is `status: ok` with no `work`.

## `edit.action`

A work item: `action_id`, `declared_scope` (1–32 entries), `operations` (1–100).
Decision and reasoning: [ADR-0008](../architecture/adr/0008-edit-action-flat-operations.md).

### Addressing

Every instance is an absolute **path**: an array of 1–16 segments, each 1–100
characters, starting at a DataModel service. Never a string with separators —
instance names can contain any character. Every *existing* instance is addressed
as `{path, expect_class}`, where `expect_class` is the exact `ClassName`
(equality, not `IsA`).

**`expect_class` detects drift; it does not prove identity.** If the user
deletes an instance and another of the same class takes the same path, the check
passes. A path is not an identity. What limits the damage is the pre-flight
refusing ambiguous paths, the declared scope, the approval gate and the local
confirmation — none of which is a guarantee.

### Operations

| `op` | Fields | Notes |
|---|---|---|
| `create_instance` | `parent`, `name`, `class_name` | never carries source; `class_name` ∈ Folder, Model, Part, WedgePart, Script, ModuleScript, LocalScript |
| `set_property` | `target`, `property`, `value` | only the allowlist below |
| `set_script_source` | `target`, `source` (≤ 100,000 characters) | `target` class ∈ Script, LocalScript, ModuleScript; replaces the whole source |
| `reparent` | `target`, `new_parent` | |
| `delete_instance` | `target` | |

There is no rename, no property named `Name` or `Parent`, and no operation that
enables a script.

### The `set_property` allowlist

The allowlist **is** the `set_property_*` definitions in
`messages/edit.action.json`; nothing else states it. `packages/sandbox` may
restrict it further and may never loosen it. A property is allowed on `Part` and
`WedgePart` (compared by exact `ClassName`).

| Property | Value | Bounds |
|---|---|---|
| `Anchored`, `CanCollide` | boolean | |
| `Transparency` | number | 0 to 1 |
| `Size` | `{x, y, z}` | each 0.05 to 2048 |
| `Position` | `{x, y, z}` | each −100000 to 100000 |
| `Orientation` | `{x, y, z}` | each −360 to 360 degrees (Roblox Y-X-Z order) |
| `Color` | `{r, g, b}` | each 0 to 1 (`Color3.new`; no 0–255 form, no HDR) |
| `Material` | `{enum: "Material", item}` | `item` ∈ Plastic, SmoothPlastic, Wood, WoodPlanks, Metal, Concrete, Brick, Glass, Neon, Grass, Sand, Fabric |

The `Size` bounds are **conservative protocol bounds, not Roblox's**: Roblox
documents 0.001 to 2048 per dimension (and simulates anything below 0.05 as
0.05); the 0.05 minimum here is deliberately stricter. The `Position` cap is a
protocol cap with no Roblox basis. Property names, classes and enum items were
checked against the Roblox creator documentation on 2026-11-01. Excluded on
purpose: anything that loads content (`MeshId`, `TextureID`, `SoundId`),
instance references, `CFrame`, attributes, tags, and every script property
(`Enabled`, `Disabled`, `RunContext`).

An `EnumItem` is the enum's name plus the item's *name*, never its number. The
enum name is a constant per property.

### Scope and ordering

`declared_scope` is a list of `{path, extent}`, `extent` ∈ `self`, `subtree`.
Each operation's *effects* are computed from the action alone, in one in-order
pass, without the state of the place:

| Operation | Effect that must be covered |
|---|---|
| `create_instance` | the new path (`parent + [name]`), extent `self`; the parent is not "touched" |
| `set_property`, `set_script_source` | the target, `self` |
| `delete_instance` | the target, `subtree` |
| `reparent` | the source and the destination (`new_parent + [last segment of target]`), both `subtree` |

An effect `(p, extent)` is covered when some entry's path is a prefix of `p` and
either the entry is `subtree`, or the entry's path equals `p` and both extents
are `self`. Ordering rules, also decidable from the message alone:

- **R1 No forward references.** A path created by the action cannot have been
  named by an earlier operation while it was still live.
- **R2 No stale paths.** After `delete_instance` or `reparent` of X, no later
  operation may name X or anything beneath it. The new path of a moved instance
  is usable.
- **R3 No duplicates.** Two creations of one path, a creation onto a move's
  destination, or recreating a deleted path in the same action are rejected.
- **R4 Reparent.** The target has at least two segments; the new parent is neither
  the target, nor beneath it, nor its current parent.

Where a created or moved path is named again, `expect_class` must equal the class
it was created with (or the moved instance's class).

`packages/sandbox` is the **single authority** on these checks. The plugin does
not evaluate scope policy. The reference implementation in
`packages/protocol/tests/protocol_semantics.py` is an executable specification
only, and is not importable by production code.

### What the plugin does

One action at a time. First a **pre-flight that mutates nothing**, against a
virtual tree laid over the real one: every pre-existing target exists
(`target_not_found`, `parent_not_found`), no path is ambiguous (`ambiguous_target`
— Roblox permits siblings with the same name; the plugin never chooses one), every
class matches (`class_mismatch`), no creation collides (`name_conflict`), no move
makes a cycle (`invalid_reparent`). A reparent moves its node in the virtual tree
and the descendants follow, so later operations resolve against the new location.
If the pre-flight fails the outcome is `rejected` and nothing was mutated.

Then it applies the operations in order and stops at the first failure: `partial`,
the remaining operations `skipped`. **Studio has no transactions. No rollback is
promised.** Which operations need itemised local confirmation is derived from the
operation kind (deleting, or overwriting source), not from a flag in the message,
and is the plugin's concern ([ADR-0005](../architecture/adr/0005-credentials-and-thin-plugin.md)).

### Scripts

Creating a script and giving it source are separate operations, and no protocol
operation enables a script. That is **not** a guarantee that agent-authored code
cannot execute; see [ADR-0010](../architecture/adr/0010-script-execution-reach-and-action-semantics.md)
(proposed).

- The plugin creates every `Script` and `LocalScript` **disabled, before assigning
  its parent**: it makes the instance, disables it, reads the state back to
  confirm, and only then parents it. If it cannot confirm, the operation fails
  with `operation_failed` and the instance is destroyed. This matters because the
  Roblox documentation says a `Script` runs the moment it is enabled and is a
  descendant of `Workspace` or `ServerScriptService`, and `LocalScript` inherits
  from `Script`. `Enabled` is documented as not replicated and not saved, while
  `Disabled` is the saved property, so the plugin confirms both views.
- `ModuleScript` has no run flag; it runs only when something required it.
- Source is written with `ScriptEditorService:UpdateSourceAsync`, not by assigning
  `.Source`, which the documentation protects and discourages. The callback
  ignores the old content and returns the full new source, the same string every
  time, because the editor may call it again, and never returns `nil`, which would
  cancel.
- Activation is a human action in Studio. A future operation to activate a script
  would need its own ADR and an approval bound to the reviewed source.

**Consequence.** A script *created* by the agent starts disabled and runs only after
a human enables it. Agent-authored code can still execute: through a source edit to
a script that is already enabled, through a `ModuleScript` required by code that
runs, through a script moved into a container where it runs, or in a playtest of the
working place. The schemas as written do not prevent any of these. ADR-0010
(proposed) states the guarantees precisely and the preconditions it would add. How
generated code is to run without touching the working place has to be decided before
the stage 4 vertical slice.

These behaviours come from the documentation as of 2026-11-01 and have **not been
exercised in Studio**.

## `project.state`

The plugin sends a snapshot immediately after the `session.hello` response
(`reason: session_start`) and after every `edit.result` (`reason: after_action`,
with `after_action_id`). The API cannot request one.

| Field | Meaning |
|---|---|
| `snapshot_id` | identifier |
| `reason`, `after_action_id` | `after_action_id` present exactly when `reason` is `after_action` |
| `roots` | the services captured (≤ 16) |
| `entries` | up to 2000 `{path, class_name, properties?}`; `properties` holds the allowlisted properties with the same value shapes as `set_property` |
| `truncated` | whether instances were left out |
| `complete_depth` | the deepest depth (service = 1) at which *every* instance under `roots` is included |

The plugin walks level by level and stops at 2000 entries or at the byte budget,
leaving room for the envelope. Script source is not included.

**Reading absence.** A path missing from a snapshot is evidence that it did not
exist **only if** its first segment is in `roots` **and** either `truncated` is
false or its depth is at most `complete_depth`. Otherwise it is *unknown*, and
unknown is never evidence of absence. Presence is always evidence of existence.

**Freshness.** A snapshot is current until the API delivers a later action or the
session ends. The ordering is the API's own; the protocol cannot see changes the
user makes in Studio, and preflight plus `expect_class` are what catch those.

**What a snapshot permits.** Planning against it, and clearing the "synchronisation
pending" state after a session loss. It does not approve anything, widen a scope or
change the result of an action.

## Idempotency and recovery

Delivery is **at least once**. There is no exactly-once guarantee and none is
claimed. The model is [ADR-0011](../architecture/adr/0011-delivery-execution-and-recovery.md)
(proposed); this section summarises it, and where the two differ that record is the
one to follow.

The governing rule: **a unit of work whose outcome is uncertain is never run again
automatically.** A "work item" is an `edit.action` or a `playtest.request`; both
follow one lifecycle.

**What the API cannot do.** It observes HTTP messages, a credential and a
`session_id` it issued itself. It cannot stop, pause or inspect an operation Studio
is executing, and it **cannot tell which process sent a message**: no message
carries an identity of a process, a Studio instance or a place. So an invalidated
session says nothing about whether the executor stopped.

**Three records, not one status.** Execution state (`queued`, `approved`,
`delivered`, `closed`, `cancelled`, the last two final); outcome knowledge (`none`,
`unknown`, `known`, forward only); and an append-only event history, which is the
source of truth for audit.

**Delivery.**

- **The API is the authority.** It assigns each work id; the id and its content never
  change. It **persists `delivered` before the response carrying the item leaves**,
  and it **durably commits an accepted result and its idempotency record before it
  emits `ok`**.
- **One active work item at a time.** The plugin polls only when idle: no item in
  flight and no result awaiting acknowledgement.
- **Redelivery** is allowed only from `delivered`, only inside the session that
  delivered it, and only in answer to a poll with a **new** `message_id` — which, by
  the rule above, proves the plugin never received it.
- **A retry is the same request**: the same `message_id` and the same content,
  answered from a bounded replay cache with the stored response verbatim. The cache
  is bounded, so idempotency is bounded: outside retention a repeat is processed
  again, and for a result that is safe because a repeat is resolved by content.
- **An item of unknown outcome is never delivered again.** Trying again means a
  **new** item with a new id, planned against a fresh snapshot; an approval does not
  carry over, and approved items that were planned against a lost state return to
  `queued`.

**Results.** The first result for a work id is recorded and closes the item. A
result classified as the same as the one recorded is answered `ok` with nothing
changed; one classified as different is answered `result_conflict`, **the first
result stays authoritative**, and the lock engages. A result that arrives after the
outcome was inferred `unknown` is a **late result**: accepted, recorded as late, and
**nothing is executed again**. How two results are compared is a **pending decision**
in ADR-0011, including whether the order of the operations is significant; until it
is settled, which results count as the same is open.

**The lock.** In v1 it applies **per credential**, and it is engaged when a session
ends with an item `delivered`, when the API restarts and finds `delivered` items,
when a result with outcome `indeterminate` arrives, and on a `result_conflict`.
While locked the API delivers no work item and keeps accepting results and
snapshots. **Releasing it requires a human attestation** that the executor has
stopped — time is not evidence, and neither is any message, because no message shows
which process sent it. For a conflict the attestation is accompanied by a recorded
review of both results. An attestation is a **declaration, not a guarantee**: a
mistaken one can leave two executors modifying one place, and apply-time
verification limits what that can do without removing the risk. After release,
planning resumes only once a fresh snapshot of the current session has arrived.

**Limits, stated plainly.** A Studio restart loses an in-memory ledger; persisting
it is an optional plugin choice outside the protocol, and a persisted ledger can be
re-sent by a process that observed none of it. An unsaved place may lose its edits
and a recovered place may differ from any ledger; there is no stable identifier for
an unpublished place. There is no expiry on work items in v1, so a long approval
wait lets the place drift.

**A snapshot never turns an unknown outcome into `applied` or `rejected`.** Only a
result can. The API may annotate an item `corroborated_applied` as informational
evidence — never `rejected`, because the absence of effects proves nothing — and only
when all of these hold: every operation has discriminating evidence, the evidence is
consistent, the relevant paths are covered (above), a baseline exists (the last
current snapshot before delivery), and the snapshot comes from a session after the
delivery. Otherwise the annotation is `inconclusive`.

| Operation | What corroborates it |
|---|---|
| `create_instance` | absent from the baseline, present now with the same class |
| `set_property` | the baseline value differed from the target and now equals it, compared with a tolerance (Roblox stores `float32`) |
| `delete_instance` | present in the baseline, absent now |
| `reparent` | the source is gone and the destination exists with the same class |
| `set_script_source` | nothing: v1 snapshots do not carry source |

A user who makes the same edit by hand confounds all of this, so corroboration is
an indication, not proof.

## Errors

Two schemas, two closed lists. Messages come from fixed templates: never
exception text, stack traces, secrets, paths of the file system, or project
content copied verbatim. `details` is closed and holds no free-form data. The
schemas bound size and shape; they cannot prove that a message is free of a
secret — that is the redaction of the API ([ADR-0005](../architecture/adr/0005-credentials-and-thin-plugin.md)).

**`ProtocolError`** — the payload of any response with `status: error`:
`{code, message (≤ 256), retryable, details?: {supported (≤ 8), retry_after_ms}}`.

| Code | Meaning |
|---|---|
| `invalid_message` | the message failed parsing, dispatch, envelope or payload validation |
| `unknown_type` | the type is not one this version knows (untyped response) |
| `unsupported_version` | no common major, or a version different from the negotiated one |
| `unauthorized` | the credential is missing or invalid |
| `session_expired` | the session is unknown or has ended; send `session.hello` again |
| `unknown_work` | a result names a work item the API does not have, or one whose state does not accept a result |
| `result_conflict` | a different result is already recorded for that work item; the first one stays authoritative |
| `internal` | a failure on the API's side |

**`OperationError`** — inside `edit.result.operations[].error`:
`{code, message (≤ 256), details?: {path}}`.

| Code | Meaning |
|---|---|
| `target_not_found` | an existing target is not there |
| `parent_not_found` | the parent of a creation or the new parent of a move is not there |
| `ambiguous_target` | more than one sibling matches a segment; the plugin never chooses |
| `class_mismatch` | the instance's `ClassName` is not `expect_class` |
| `name_conflict` | a sibling with that name already exists |
| `invalid_reparent` | a cycle, a no-op or a service |
| `property_unavailable` | the property or enum item does not exist in this Studio, or is not writable |
| `operation_failed` | anything else; the template message never carries Studio's raw error |

## Untrusted content

The text of the project and of playtests is **data and never instructions**
(invariant I3). The schemas mark exactly two fields `x-untrusted: true` so a
consumer can route them through the labelled, delimited channel
([`docs/safety.md`](../safety.md)): every path segment (instance names) and every
playtest output line. Playtest output may be produced by the model's own code, so
it is adversarial by construction.

The marker and the length limits **do not remove the risk of prompt injection**.
They tell a consumer which text to distrust and bound how much of it there is; the
text still reaches the model. Defence is the job of `packages/core` and
`packages/sandbox`, not of this protocol. By the same token, a schema-valid message
is not an approved or safe one: nothing in the protocol is evidence of approval,
which is why there is no `approved` flag.

## Compatibility

Within a major version a change must be additive. The mechanics:

- `x-since: "MAJOR.MINOR"` is a protocol annotation, **not** a JSON Schema keyword.
  Validators ignore it. It may sit only on a `oneOf` branch (a new operation, a new
  allowlisted property), on an **optional** property, or at the root of a message
  schema. Absent means 1.0.
- A property introduced after 1.0 can never be `required`.
- A sender whose negotiated minor is *N* never emits an element annotated with an
  `x-since` above *N*; an older receiver would reject it, being closed.
- Within a major version, **a closed `enum` or a numeric bound cannot be widened**,
  because values cannot be annotated. Widening is a new major, or a new property or
  branch.
- Tests enforce the annotation's format, placement and the `required` rule, and
  that none exceeds `version.json`. At 1.0 nothing is annotated.
- **Not yet in place:** the comparison against the released schemas. It needs a
  baseline, i.e. a tag `protocol-v1.0`, which does not exist. After tagging, any
  change under `schemas/v1/` must pass that comparison.

## Limits

All explicit, all enforced by the schemas or the profile, all locked by tests.

| Limit | Value |
|---|---|
| Message size | 1,048,576 bytes |
| JSON nesting | 12 (the deepest v1 message is 7) |
| Integer literal | ±2^53 |
| Identifier | 1–64 characters |
| Path | 1–16 segments of 1–100 characters |
| `class_name` | ≤ 64 characters |
| Operations per action | 1–100 |
| Scope entries | 1–32 |
| Script source | ≤ 100,000 characters |
| Snapshot entries | ≤ 2000 |
| Snapshot roots | ≤ 16 |
| `complete_depth` | 0–16 |
| Playtest output lines | ≤ 1000 of ≤ 1000 characters |
| Playtest duration limit | 1–600 s |
| Error message | 1–256 characters |
| `supported` versions | ≤ 8 |

The 1 MiB cap is a protocol cap. No documented platform limit on request bodies
was found, and the cap has to be tried against Studio when the first plugin exists.
Several limits can be reached together (a hundred maximum-size scripts do not fit
in 1 MiB); the byte cap decides, and the sender splits the work.

## Conformance

`packages/protocol/examples/v1/` holds the vectors; its
[README](../../packages/protocol/examples/v1/README.md) states their format. They
are the conformance suite for **every** implementation: the Python reference, the
API parser, and the Luau parser and bounded schema validator.

An implementation must agree with each vector on validity, on the stage of the
failure and on the instance path of it. A failure inside a `oneOf` is reported at
the `oneOf`'s own path, so a defect in a work item is reported at `/payload/work`
and one in an operation at that operation. `keyword` and `inner` are extra
precision for the Python tests and are not part of the contract.

Verified in Python: the schemas are Draft 2020-12; each stays inside the subset;
every limit is the documented one; every valid vector validates; every invalid
vector fails at its declared stage and path, with exactly one defect, and — for a
`oneOf` — against the branch it names. The integrated Luau strict parser matches
the shared parse vectors plus explicit byte-profile cases, and the bounded schema
validator matches all shared valid/invalid schema vectors under Lute 1.0.0.

## Layout

```
packages/protocol/
├── README.md
├── schemas/v1/
│   ├── version.json                    the version and the message types
│   ├── common.json                     shared definitions
│   ├── envelope.{request,response,error}.json
│   ├── envelope.hello.{request,response}.json
│   ├── error.{protocol,operation}.json
│   └── messages/<type>.{request,response}.json, edit.action.json, playtest.request.json
├── examples/v1/{valid,invalid,parse}/  vectors, and index.json
└── tests/                              test_schemas, test_strict_json, test_semantics + helpers
```

## Known limitations

- Full Luau protocol semantics remain unverified. Lute covers parsing and the
  bounded schema subset, not operation-specific semantic checks such as
  revision ordering, snapshot reconciliation, lifecycle recovery, or parity of
  diagnostic details. The installed Studio runtime is also unverified (ADR-0009).
- Agent-authored code can execute in a playtest by paths the schemas do not prevent
  (ADR-0010, proposed); the guarantees are narrower than earlier versions of this
  document stated.
- Truncated snapshots on large places will often leave a reconciliation
  inconclusive. A scoped snapshot request would fix that and is compatible, but is
  not in v1.
- Failures inside a `oneOf` are localised only to the `oneOf`, which limits the
  precision of an error report.
- Closed `enum`s and bounds cannot be widened inside a major version.
- The hello cannot be changed, ever.
- The release comparison for `x-since` does not exist until the first tag.
- `approval.request` and `run.log` (API → web) are not specified.
