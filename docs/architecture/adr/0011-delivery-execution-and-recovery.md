# ADR-0011: Delivery, execution, idempotency and recovery

- **Status:** Proposed
- **Date:** 2026-11-01
- **Revised:** 2026-11-07

The decisions below were reviewed and approved by the project owner. The status
stays *Proposed* until the text itself has been reviewed; it becomes *Accepted*
then.

The revision of 2026-11-02 integrates five decisions that the owner approved
explicitly, marked **[Owner decision]** in the text: the premise on the identity of
the executor (section 1), the durable commit of an accepted result before `ok`
(section 3), the human attestation that releases the locks T1 to T3 (section 7), the
attestation plus recorded review that releases T4 (section 7), and the credential as
the unit of the lock in v1 (section 7). Everything else that the review of this
record raised is **not decided** and is listed under *Pending decisions*.
Integrating these decisions does not accept the record.

## Decisions taken on 2026-11-07

The project owner asked for the project to be finished and delegated the remaining
choices. This revision adopts, as **decided**, the choices that `packages/api`
already implements and tests, and says what each one costs. None of them adds a
field or an error code to the wire, so the protocol schemas are frozen by them.

| Question | Decision |
|---|---|
| Which results are "the same" (section 5), `edit.result` | Same `outcome` and, **position by position**, the same `op_id`, `status`, `path` and error `code`. **The order of the operations is significant**: a permutation is a different result, hence a conflict. The envelope, `replayed` and the text of an error are not compared |
| Which results are "the same", `playtest.report` | Same `outcome`, `duration_ms`, `output_truncated` and output lines `(t_ms, level, text)`. **[Plugin]** A plugin that resends a report sends the **stored** one unchanged and never measures again: a re-measured report is a conflict and engages T4 |
| What the retry digest covers (section 6) | The **bytes of the request body**. A retry must be byte-identical, `sent_at` and key order included. No canonical number form is needed, so the strict JSON profile is untouched |
| A held `message_id` returns with different content | Answered `invalid_message`. `message_id_reuse` is **not added** |
| Result stored but not acknowledged; partial state | The accepted result and its idempotency entry live in **one state document committed by one SQLite transaction** ([ADR-0016](0016-sqlite-lifecycle-store.md)), so a state with only one of them stored does not exist. A crash after the commit is resolved by a resend under a new `message_id`, compared as above |
| `replayed` | Recorded in the event history for every accepted result, duplicates included. It is never compared and **never releases a lock**: a declaration of provenance is not an identity (section 1). `playtest.report` has no such field, and none is added |
| The current snapshot (section 7) | The last snapshot accepted in the current session, by arrival order. Its causal relation to the uncertain work is **asserted by the plugin and not verified by the API**. A snapshot of an older state is recorded `snapshot_superseded`; a repeated `snapshot_id` with different content is recorded `snapshot_conflict` and the first is kept. Neither engages the lock. No field is added |
| `unknown_work` | Recorded as an event. It does **not** engage the lock |
| What one attestation covers | One attestation releases the **whole lock of the credential**, whatever triggers hold it. A T4 lock also needs a recorded review, a non-empty free-text note about both results. The attestation records actor, warning text and review. The first result stays authoritative |
| After a plugin restart, a stored terminal result | The plugin **may** resend it with a new `message_id`; for an `edit.result` it should set `replayed: true`. The API compares it as above and never executes anything again |
| An `unknown` operation | Carries no `error`. Why it is undetermined belongs to the event history |
| Session inactivity limit | 900 s, longer than the longest playtest (600 s) plus a margin |

**Still open, and why.** The value of the descendant-scan bound L, the limits of the
replay cache, ledger and history, the expiry of work items, and several projects
per credential or Team Create need either a calibration against Studio or a
product decision that has no user yet. **No plugin has ever been exercised against
a live Studio session**, so every **[Plugin]** obligation and every **[Assumption]**
here is unverified. For that reason, and only that reason, the record keeps the
status `Proposed`.

## How to read the claims

- **[Protocol]** — a property of the schemas and the validation procedure.
- **[Plugin]** — a behaviour the Studio plugin must implement. The schemas cannot
  enforce it.
- **[API]** — a policy or behaviour of the API service or of `packages/sandbox`.
- **[Consumer]** — a decision for whatever displays or consumes the data.
- **[Assumption]** — something believed about Roblox Studio from its
  documentation and **not yet exercised in Studio**. It is not a confirmed fact.
- **[Pending]** — an open decision.
- **[Owner decision]** — a decision approved explicitly by the project owner in the
  revision of 2026-11-02. It does not make the record *Accepted*.

## Context

[ADR-0007](0007-plugin-initiated-http-transport.md) fixed the channel: every
exchange is started by the plugin, and work the API wants applied waits in a queue
until the plugin's long-poll collects it. Delivery over that channel is **at least
once**: a response can be lost after the API has sent it, and a request can be
repeated.

`docs/protocol/README.md` described a recovery model: a ledger kept by the plugin,
a table of what the plugin does on a repeated delivery, and the statement that the
API treats any action it delivered and never saw resolved as `indeterminate` after a
new `session.hello`. An independent audit (findings M-1, M-2 and M-3) found that
model incomplete:

- A row of the plugin's table (an action `in_progress` after a crash) can only be
  reached if the ledger survives a restart, and the ledger was defined as living in
  memory.
- Nothing said that the API must not deliver again an action it had marked
  `indeterminate`, which is the only thing that stops a plugin with an empty ledger
  from applying it twice.
- Nothing said what the API does with a duplicate, a contradictory or a late
  result, or whether a retried request reuses its `message_id`.
- Playtests had no lifecycle at all.
- The model assumed that ending a session stops whatever the plugin was doing.

The last point is the most important and is not true. Studio executes plugin code
locally. **An invalidated session says nothing about whether the executor has
stopped.** Closing an HTTP connection, expiring a session, superseding it with a
new `hello`, or restarting the API does not stop an operation that Studio is
already running.

## Problem

1. What is the precise lifecycle of a unit of work, and which states permit
   delivery again?
2. How is a retried request made harmless, and what does the API do with results
   that are duplicated, contradictory or late?
3. How is a new session prevented from starting to modify the project while an
   operation of an earlier session may still be running?
4. What may the plugin check, and when, given that the user can edit the place after
   the pre-flight and that some Studio calls yield?
5. How is an operation whose effect cannot be determined reported?
6. How do playtests fit the same model?

The governing rule is that **a unit of work whose outcome is uncertain is never run
again automatically.**

## Decision

### 1. Premises

- **[API]** The API observes HTTP messages, nothing else. It cannot stop, pause or
  inspect an operation that Studio is executing.
- **[Owner decision]** The API has **no identity of an executor**. What it observes
  is the credential in the transport, a `session_id` that it issued itself, and the
  content of a message. The protocol as it stands cannot identify the Studio process
  that sends a message, so the API cannot link a message to a process, to a Studio
  instance or to a place: the credential is a token that any process holding it can
  use, `session.hello` carries only the name and version of the client, and no
  message carries an identifier of a place or project. Executor identity and fencing
  are left to a future architectural decision (see *Alternatives considered*).
  Everything in section 7 rests on this premise.
- **[Assumption]** Plugin code runs on one cooperative thread: code between yields
  is not interleaved with user edits or with other plugin code. This is what makes a
  check followed by a mutation, with no yield between them, safe against the user.
  It has not been exercised in Studio.
- "Work item" means an `edit.action` or a `playtest.request`. They share one
  lifecycle.

Five facts are kept apart, because treating them as one is what made the earlier
model unsafe:

| Fact | What it is | What it does not imply |
|---|---|---|
| **Session invalidated** | The API decided a session is no longer valid: it expired, a new `hello` superseded it, or the API restarted. | That the executor stopped, or that it never received the item. |
| **Executor stopped** | Knowledge about the plugin process. Values: *unknown* (the default after an invalidation, and it stays so whatever message arrives), *declared by a human* (an attestation, section 7). No message establishes it, because the API cannot tell which process sent a result (section 1). | That no other executor exists. |
| **Outcome unknown** | Knowledge about the *result* of a work item (section 4). | Whether the executor is still active. |
| **Credential locked** | The API delivers no new work items under that credential (section 7). | That anything was lost. |
| **Credential recovered and enabled** | The lock was released and a fresh snapshot of the current session has arrived. | That the place is in the state anyone expected. |

### 2. Rules P1–P5 (delivery) and RD1–RD5 (recovery)

**P1 — [Plugin]** The plugin has **one active work item at a time**, an action or a
playtest. It sends `work.poll` only when it is idle: no item in flight and no result
awaiting acknowledgement.

**P2 — [Plugin]** At most one `work.poll` is in flight.

**P3 — retries are idempotent.** **[Plugin]** A retry of a request is the same
request: the same `message_id` and the same content. **[API]** The API answers a
repeated `message_id` of the same session with the **stored response, verbatim**,
including that response's own `message_id`, `correlation_id` and `session_id`. For
`session.hello` there is no session yet, so the key is the `message_id` alone, for a
bounded window. The cache is bounded; when an entry has been evicted, the repeated
request is processed again, which is safe because a result is idempotent by content
(section 5), a repeated poll is a new poll, and a repeated `hello` merely opens
another session.

**P4 — [API]** The session is the boundary of uncertainty. When a session ends, by
expiry, supersession or an API restart, every work item that was delivered in it and
is unresolved becomes **outcome unknown** (inferred). A new session never inherits
the confidence of the one before it.

**P5 — [API]** At most one session is active per credential. A new `hello`
invalidates the previous session. This does not stop the previous executor, and it
does not release the lock (section 7).

**RD1 — [API]** Redelivery is allowed only from `delivered`, only within the session
in which the item was delivered, and only in answer to a `work.poll` with a **new**
`message_id`. By P1, such a poll proves that the plugin is idle and holds no result,
so it did not receive the item. The redelivery has the same work id and identical
content.

**RD2 — [API]** A work item whose outcome is unknown is **never executed again
automatically**. The only way to try again is a **new** item with a new id, planned
against a fresh snapshot. An approval does not carry over.

**RD3 — [API]** When a work item becomes outcome-unknown, every approved item that
has not been delivered returns to `queued`, with the reason `stale_base`, and needs a
new approval. It was planned against a state that may no longer exist.

**RD4 — [Plugin]** A `session_start` snapshot is captured **only while the plugin is
idle**. If an item is being applied when a session starts, the plugin finishes it,
reports it, and then sends the snapshot.

**RD5 — [API]** A result for a work id that is not in a state that accepts it
(unknown, `queued`, `approved`, `cancelled`) is answered with the protocol error
`unknown_work`.

### 3. Delivery and the write-ahead record

**[API]** The API **persists** the state `delivered` *before* the response that
carries the item leaves. If it cannot persist, it does not respond. Without this, a
crash between sending and recording would restart the API with an item still
`approved`, and it would be delivered again to a plugin that already holds it.

**[Owner decision]** The same rule applies in the other direction. The API
**durably commits the accepted result and its idempotency record before it emits
`ok`**. If it cannot commit, it does not answer `ok`.

**What `ok` guarantees, exactly:** that at the moment it was emitted the accepted
result and its idempotency record were both durable. It guarantees nothing more, and
nothing about a result for which no `ok` was received. A result durable without its
idempotency record would leave a repetition with the same `message_id` to be
processed again while P3 promises the stored response, which is why `ok` waits for
both.

This record does **not** say that the two are one atomic, all-or-nothing write.
A state with only one of them stored cannot exist (see *Decisions taken on 2026-11-07*).

The rule is of the form *durable before emitting*, like the one above for
`delivered`. It is **not** a transaction that includes the network, and no
implementation can offer one: a response can always be lost after the storage.

*Consequences.*

- An `ok` means the result and its idempotency record are durable. The absence of an
  `ok` says nothing about whether the result was recorded.
- **A crash after the result is durably stored and before the acknowledgement** is
  possible, and the rule does not prevent it. The result is recorded, and the plugin
  sees a transport failure or an error answer and knows nothing about the record. The
  plugin **may resend the same content with a new `message_id`**. That is a new
  request, so the replay cache of P3 does not decide it. The API compares it with the
  result already recorded:
  - for an `edit.result`, by the comparison of section 5 (order significant): the
    same, it is a duplicate, answered `ok` with nothing changed; different, it is a
    conflict;
  - for a `playtest.report`, by the report projection of section 5: the same, a
    duplicate; different, a conflict.

  Whatever the classification, the work is not executed again (RD2): a result is a
  report, not an action.
- The opposite order, acknowledging before committing, would let a crash discard a
  result that the plugin believes settled.

**Decided 2026-11-07:** the result and its idempotency entry are committed together,
so a partial state does not arise; whether the replay cache keeps error responses is
left to the implementation, which stores the response it sent.

The storage engine decision is recorded in
[ADR-0016](0016-sqlite-lifecycle-store.md). The pending result-acknowledgement,
replay-cache, and recovery semantics in this proposed record remain unresolved.
A start-up that finds items `delivered` applies P4 and the lock (section 7).

### 4. Three separate records

The earlier model kept one status. It is replaced by three records that are not
interchangeable.

| Record | Values | Rules |
|---|---|---|
| **Execution state** | `queued`, `approved`, `delivered`, `closed`, `cancelled` | `queued → approved` by human approval. `approved → delivered` on a poll, after the write-ahead record. `delivered → delivered` on a redelivery (RD1), counting deliveries. `delivered → closed` on a result, or when the session ends (P4). `queued` and `approved` can become `cancelled`. An approved item returns to `queued` (RD3). **`closed` and `cancelled` are final: a closed item is never delivered again and never reopened.** |
| **Outcome knowledge** | `none`, `unknown`, `known` | Only moves forward: `none → unknown → known`, or `none → known`. `unknown` is set by inference (P4) or by an `indeterminate` result. `known` is set only by a result with outcome `applied`, `rejected` or `partial`, and is then immutable. |
| **Event history** | an append-only log | Every event is recorded with its time, session, `message_id` and kind: delivery *n*, session ended, lock engaged or released, result received (flagged `late` when it arrives while the knowledge is `unknown`), duplicate, conflict, snapshot, evidence annotation, attestation, review of the two results of a conflict (T4). |

The history is the source of truth for audit. The other two are projections of it.
An outcome that is `known` and an item that is `closed` do not rewrite anything that
was recorded before.

### 5. Results: duplicate, contradictory, late

**Same result. [Decided 2026-11-07]** Two results for one work id are the same when they have the same
outcome and, operation by operation, the same `op_id`, `status`, `path` and error
`code`; the operations are paired by position in the array only as a working
convention. **The order is significant**: two results whose operations are a
permutation of each other are different. The `replayed` flag, the `message_id`, the
`sent_at` and the text of an error message are not compared. For a `playtest.report`
the compared fields are `outcome`, `duration_ms`, `output_truncated` and the output
lines `(t_ms, level, text)`.

| Situation | **[API]** handling |
|---|---|
| First result for a work id that is `delivered` | Record it; knowledge becomes `known` (or `unknown` if it reports `indeterminate`); the item is `closed`. |
| A result equal to the one already recorded | Answer `ok`. Nothing changes. |
| A result different from the one already recorded | **The first result wins.** Answer with `result_conflict`. Record the conflict. Engage the lock (T4). |
| A result arriving after the knowledge was inferred `unknown` | A **late result**. Accepted if the credential is the same and the work id exists. Recorded with `late`. Knowledge becomes `known` (or stays `unknown` if the result is itself `indeterminate`). The item stays `closed`; **nothing is executed again.** It does **not** release a lock (section 7). |
| A result after an `indeterminate` result was already recorded, different from it | A conflict. The `indeterminate` result was the first result. |

**Identifiers of a late result from a new session.** The work id is the same, because
it is the key of the domain and does not depend on a session. `session_id` is that of
the **current** session; the history keeps the session of the delivery as well.
`message_id` is new: the idempotent retry of P3 holds only within a session, and
across sessions the repetition is resolved by content. The response's
`correlation_id` is that request's `message_id`, as always. The result does not need
to say in which session the item was delivered: the API knows it from its history.

**Late result against earlier evidence.** The API may have recorded an annotation
derived from snapshots (`corroborated_applied` or `inconclusive`;
`docs/protocol/README.md`). A late result **prevails as knowledge**, because it is a
report on the operations whereas a snapshot only supports an inference. It is still a
message of unverified origin (section 1). The annotation is **not deleted**: it
stays in the history, an `evidence_contradicted` event is appended, the item is
flagged for human review, and nothing else happens automatically.

A snapshot never turns an unknown outcome into `applied` or `rejected`. Only a
result can.

### 6. Identifiers in each scenario

| Scenario | Execution | Knowledge | Identifiers |
|---|---|---|---|
| Delivered, response lost | `delivered` | `none` | Retry with the same `message_id`: the stored response, verbatim. Poll with a new `message_id`: redelivery *n+1*, same work id, a new `correlation_id`. |
| Received | `delivered` | `none` | No traffic. The plugin is preflighting. |
| Executing | `delivered` | `none` | No traffic: P1 forbids polling. If the API expires the session meanwhile, the result goes in a new session (late). |
| Plugin restarted mid-execution | `closed` once the session ends | `unknown` (inferred) | Work id unchanged. `session_id` and `message_id` are new. No redelivery. |
| Result lost | `delivered` or `closed` | `none` or `known` | Resent with the same `message_id`: if the API has it, the stored acknowledgement. |
| Result recorded, acknowledgement lost | `closed` | `known`, or `unknown` if the recorded result is `indeterminate` | Resent with a new `message_id` and the same content. Compared with the recorded one by the projection of section 5: if it is a duplicate it is answered `ok` with nothing changed. Nothing is executed again. Knowledge does not change, and a lock that the result engaged stays until a human attests (section 7) |
| Duplicate result | `closed` | `known`, or `unknown` if the recorded result is `indeterminate` | Same work id; acknowledged without change. |
| Contradictory result | `closed` | `known`, or `unknown` if the first result is `indeterminate` | `result_conflict`; first result stays. |
| Late result | `closed` | `unknown → known`, or stays `unknown` if the late result is `indeterminate` | New session, new `message_id`, same work id. |

### 7. The lock

**[Owner decision]** In v1 the lock applies **per credential**. It is engaged when:

- **T1** a session ends while a work item is `delivered`;
- **T2** the API starts and finds `delivered` items persisted;
- **T3** a result with outcome `indeterminate` is received;
- **T4** a `result_conflict` occurs, which suggests two executors.

While locked, the API delivers no work item of any kind, and approved items return to
`queued` (RD3). It keeps accepting results and snapshots.

**[Owner decision] The unit of the lock is the credential.** No message carries an
identifier of a place or project, so the credential is the only unit the API can key
a lock by.

*Consequences.*

- **The lock can stop the work of several places that share a credential.** An
  uncertain item in one place blocks delivery for every place associated with that
  credential, including places that were not involved.
- The API cannot tell which place an uncertain item belonged to, so neither it nor
  the person who attests can narrow the lock to the affected place.
- An attestation releases the lock for the whole credential, and so the person
  declaring that the executor has stopped is declaring it for every place under it.
- P5 allows one active session per credential, so this record does not address how
  two Studio instances under one credential coexist.
- A finer unit would need an identifier of a place or project on the wire, which
  cannot go in the frozen `session.hello` and which this record does not propose.

**[Owner decision] Releasing the lock requires a human attestation.** Time is not
evidence, and neither is any message, because the API has no identity of an executor
(section 1).

**What a result does and does not do.** A result, of any outcome and including
`indeterminate`, is evidence about the **operations**: it updates the outcome
knowledge (section 4) and is recorded. It does **not** release a lock by itself, and
it does not show that the previous executor stopped acting or that no other executor
exists. The API cannot tell which process sent it: a process other than the one that
received the item may send a result, for example one that a persisted ledger holds
(section 8). The same is true of a snapshot and of a new `session.hello`.

| Lock | Released by |
|---|---|
| **T1, T2, T3** | A **human attestation** that the executor has stopped. A result may arrive before or after it, and is evidence about the operations only |
| **T4** | A **human attestation** and a **recorded review of both incompatible results**. The review does not change which result is authoritative: the first result recorded **remains authoritative** (section 5) |

The attestation is a **declaration**, not a technical guarantee. The API records who
declared it, when, and the text of the warning shown; for T4 it also records the
review of the two results. The API has no means of checking that no Studio instance
is still applying the item. A mistaken or false attestation can lead to two
executors modifying the same place at once. Apply-time verification (section 8)
limits what such an overlap can do; it does not remove the risk.

Making a different result authoritative after a review is **not** decided by this
record; it would need a further decision.

**Decided 2026-11-07:** one attestation releases the whole lock of the credential,
whatever triggers hold it. A T4 lock also needs a recorded review, a non-empty note
about both results, kept in the event history. `unknown_work` and a conflicting
snapshot are recorded and do not engage the lock.

After the lock is released, the credential is **recovered and enabled** only when a
fresh snapshot of the current session arrives (`session_start` or `after_action`,
captured while idle, RD4). Planning resumes from that snapshot, not from inference.

**Decided 2026-11-07:** the current snapshot is the last one accepted in the current
session; an older one is recorded as superseded; what a snapshot shows about the
state after the uncertain work is asserted by the plugin and not verified. The rule
stands that a snapshot never turns an unknown outcome into `applied` or `rejected`
(section 5).

### 8. What the plugin checks, and when

**[Plugin]** The plugin applies one item at a time and writes an in-memory ledger
entry for it. Persisting the ledger across a restart is an optional plugin choice and
is outside the protocol. If a persisted ledger shows an item that was being applied
when the plugin stopped, the plugin **does not apply it again**: it reports
`indeterminate` with every operation `unknown`.

**Decided 2026-11-07:** after a restart, a ledger entry that holds a **terminal
outcome** may be resent under a new `message_id` (an `edit.result` should carry
`replayed: true`; a `playtest.report` has no marker). The API never executes anything
again because of it. What else a plugin may persist across a restart is left to the
plugin.

- **Write-ahead marker.** Before the first mutation of an action the plugin records
  that it is applying it.
- **Pre-flight is advisory.** It runs against a virtual tree, mutates nothing, and
  fails fast. It is not the check that decides.
- **Verification at apply time is authoritative.** Immediately before **each**
  operation the plugin checks, in one synchronous block with no yield between the
  check and the mutation: that the target exists, that its path is not ambiguous,
  that its class equals `expect_class`, that a creation does not collide, and the
  assertions `expect_enabled` and `contains_scripts` of
  [ADR-0010](0010-script-execution-reach-and-action-semantics.md). The user can edit
  the place after the pre-flight, and earlier operations of the same action change
  it too.
- **No yielding between operations**, except where an operation yields inherently.
  **[Assumption]** The cooperative-thread premise of section 1.
- **`contains_scripts`.** The scan of the subtree is synchronous and bounded by a
  limit **L** on the number of descendants visited, an implementation constant that
  must be documented. With the assertion `true` the scan may stop at the first script
  it finds; with `false` it must visit the whole subtree. If the subtree exceeds L the
  operation fails with `operation_failed` and the planner has to split the move. The
  value of L is **[Pending]**: it is a calibration, and Studio's behaviour under a
  long synchronous scan has not been measured.

**Source edits through `ScriptEditorService:UpdateSourceAsync`.** The documentation
states that the callback may not yield, that returning `nil` cancels the update, that
the call yields until it is applied or cancelled, and that the editor may reject an
update made from stale content, in which case the callback is invoked again.
**[Assumption]** These behaviours are documented and have not been exercised.

- **[Plugin]** The callback re-checks, on **every** invocation, that the target still
  exists, that its class is as expected and that `expect_enabled` still holds, and
  cancels by returning `nil` if not. Otherwise it returns the complete new source —
  the same string every time, ignoring the old content.
- This record does **not** claim that `UpdateSourceAsync` is atomic with respect to
  concurrent external modifications. The callback is the last verification point the
  documentation offers for that update. A change made by the user after the callback
  returns, while the call is still yielding, is not excluded.

| What happens | Reported status of the operation |
|---|---|
| The callback cancelled and the call returned | `failed`, with `state_mismatch`. Nothing changed. |
| The last invocation returned the source and the call returned | `applied` |
| The call raised before the callback ran at all | `failed`, with `operation_failed` |
| The call raised after the callback ran at least once | Read back the edit-time source. Equal to the intended source → `applied`. Equal to the original source, captured in the first invocation → `failed`. Neither → **`unknown`**. |

Which Studio call reads back the edit-time source, and how it behaves, is an
**[Assumption]**.

### 9. Outcomes and `unknown` operations

An operation whose effect cannot be determined is reported with status `unknown`.
The operations before it are `applied` and the ones after it are `skipped`. The
outcomes are:

| Outcome | Meaning |
|---|---|
| `applied` | Every operation applied. |
| `rejected` | Nothing was changed. The first operation failed, at pre-flight or when applied; the rest are `skipped`. |
| `partial` | At least one operation applied, then one `failed` (known not to have been applied); the rest are `skipped`. No rollback is promised: Studio has no transactions. |
| `indeterminate` | **At least one operation is `unknown`.** Earlier ones are `applied`; later ones `skipped`. When a plugin reports after a restart and knows nothing, every operation is `unknown`. |

Two consequences follow from the outcomes above and from section 8, where an action
stops at its first failure:

- **`failed` and `unknown` never share a result.** A failure known not to have been
  applied yields `rejected` or `partial`; an operation whose effect cannot be
  determined yields `indeterminate`.
- **An `unknown` operation carries no `error`.** The schema ties `error` to the
  status `failed`, so why an operation is undetermined is not expressible in the
  message; it belongs to the event history (section 4). Accepted on 2026-11-07.

This **replaces** the earlier meaning of `indeterminate`, in which every operation
had to be `unknown`. The schema is unchanged: the status `unknown` already exists.
**Applied:** the test-only reference check and `docs/protocol/README.md` now encode
this rule, and a vector of the mixed form exists beside the all-`unknown` one.

### 10. Playtests

A playtest is a work item and follows the same states, with the same rules P1–P5 and
RD1–RD5.

| Situation | Handling |
|---|---|
| `playtest.request` delivered and not received | As for actions: redelivery on a poll with a new `message_id` within the session; the same `playtest_id`. |
| Plugin restarted while it ran a playtest | The item is `closed` with unknown knowledge (inferred). It is **not** run again automatically. Repeating it requires a new `playtest_id` and a new approval. |
| `playtest.report` lost | Resent with the same `message_id`; the stored acknowledgement is returned if the API has it. |
| A report repeated for the same `playtest_id`, classified as the same as the one recorded | **Depends on a pending decision**: how a `playtest.report` is compared is not decided (section 5, *Pending decisions*), so which reports count as the same is open. Once classified as the same: `ok`, no change. |
| A report for the same `playtest_id`, classified as different from the one recorded | **Depends on the same pending decision.** Once classified as a conflict: `result_conflict`; the first result stays; the lock engages (T4). |
| Report for a `playtest_id` not in a state that accepts it | `unknown_work`. |
| Report after the knowledge was inferred `unknown` | Accepted as late. A playtest has no repeated-execution hazard, so accepting it is always safe. |

Whatever the classification, an accepted report never causes the playtest to be run
again (RD2): a report is a result, not an action.

**[Plugin]** The plugin runs one playtest at a time and does not poll while it runs
(P1). **[API]** Its session-inactivity limit must exceed the longest playtest, which
is 600 seconds, plus a margin; otherwise the report arrives late, which is accepted.
Given a `playtest.request` with `place: disposable`, the plugin answers with a
`playtest.report` whose `outcome` is `unsupported`, which the API treats as "not run"
([ADR-0010](0010-script-execution-reach-and-action-semantics.md)). That is an
ordinary report: it is neither a protocol error nor a protocol response. The field
`place` and that outcome do not exist in the schemas yet; ADR-0010 lists both as
changes still to be applied.

## What changes, and what does not exist yet

**The changes this record makes to the wire are applied; nothing else in it is.**
This record remains `Proposed` only because no plugin has been exercised against
Studio; the choices that were `[Pending]` are settled in *Decisions taken on
2026-11-07*.

Applied, in one protocol change that lands before the tag `protocol-v1.0`:

- `error.protocol.json`: `unknown_action` renamed to `unknown_work`, and
  `result_conflict` added. Both are changes to a **closed `enum`**, which
  `docs/protocol/README.md` forbids inside a major version; they are admissible only
  because that tag does not exist yet.
- The reference checks, the vectors and `docs/protocol/README.md` updated for the new
  meaning of `indeterminate`, for `unknown_work` and `result_conflict`, and for the
  sections this record replaces (the ledger table and "`indeterminate` is final").

**Not implemented, and not schema:**

- The state machines, the lock and the three records are **[API]** and **[Plugin]**
  behaviour and have no schema. They are to be specified by the `lifecycle` suite of
  [ADR-0013](0013-conformance-suites.md), which does not exist.
- No plugin exists, so every **[Plugin]** obligation in this record is unexercised,
  and so is every **[Assumption]** about Studio.
- `message_id_reuse` is **not added**: a repeated `message_id` with different content
  is answered `invalid_message` (decided 2026-11-07).

Documentation corrected together with this record: `docs/protocol/README.md` carries
a note that this record supersedes the parts of it that differ.

## Alternatives considered

- **A deadline after which the plugin stops by itself.** Rejected: it helps only an
  executor that obeys it. A hung or orphaned executor is not covered, and it adds a
  field and an obligation.
- **An executor identifier, or fencing, in `hello` or in the snapshot.** **[Owner
  decision]** Left to a future architectural decision. An identifier alone would be a
  declaration like any other, and the hello is frozen; identity or fencing needs a
  point where it is *enforced*, and the API is not one: it can refuse to deliver, it
  cannot stop a process that already holds an item. Nothing in this record adds a
  field. Revisit if human attestation proves to be frequent.
- **Releasing the lock on a result, `indeterminate` included.** **[Owner decision]**
  Rejected: the API cannot link a result to the executor, so a result does not show
  that the previous executor stopped. A result is evidence about the operations
  (section 7).
- **Releasing the lock after a time.** Rejected: elapsed time proves nothing about an
  executor.
- **Refusing a second `hello`.** Rejected: it would shut out a plugin that restarted
  while the API still considers its old session alive.
- **Relying on the end of the HTTP connection.** Rejected: it does not stop a local
  operation.
- **A message acknowledging receipt of a work item.** Rejected: P1 makes a poll after
  a delivery equivalent to a negative acknowledgement, with no new message.
- **Delivering again actions of unknown outcome whose operations are idempotent.**
  Rejected: not all operations are idempotent, and it breaks the governing rule.
- **Rejecting late results.** Rejected: it discards the best evidence available and
  prevents no hazard, since nothing is executed.
- **Last result wins.** Rejected: it lets a faulty executor rewrite history.
- **A persistent ledger in the plugin as a requirement.** Rejected: places can be
  unsaved and unpublished, so the ledger and the place can diverge.
- **Expiry of work items.** Deferred: not needed to meet the governing rule.

## Consequences

**Positive**

- A work item of uncertain outcome cannot be run again by any automatic path.
- A retry cannot cause a second effect, and its response is reproducible.
- The distinction between a session, an executor, an unknown outcome and a lock
  removes the unsafe assumption that closing a session stops the work.
- The best evidence about the operations — a result — is kept even when it arrives
  late, and contradictions leave a trace.
- Playtests need no machine of their own.

**Negative and risks**

- Treating every undelivered-looking item of a lost session as outcome-unknown is
  conservative: a work item that was never received also locks the credential and
  forces replanning.
- Releasing **any** lock needs a human, including after a result of any outcome, and
  a human can be wrong. Every `indeterminate` report, and every lost session with an
  item in flight, costs a human step; how often that happens depends on Studio
  behaviour that has not been observed. The risk of two executors is reduced, not
  eliminated.
- The write-ahead record and the commit of accepted results need durable storage, and
  that engine is not chosen. If the API cannot commit, it does not answer `ok`, so a
  plugin may keep holding a result that it cannot settle.
- Because the lock is per credential, an uncertain item in one place stops work in
  every place under that credential until a person attests (section 7).
- An executor that is still running while a second one starts is limited only by
  verification at apply time, whose strength rests on the cooperative-thread
  **[Assumption]**.
- The user's edits at yield points, and collaborative editing, are not excluded.
- A scan bound L can make a legitimate large move fail and force the planner to
  split it.
- The replay cache, the ledger and the history need retention limits that are not
  decided here.
- Everything about the plugin side is unverified: there is no plugin, and no Luau
  implementation of any of this exists.

## Assumptions to validate in Roblox Studio

- Plugin code runs cooperatively on one thread, and a user edit cannot occur between
  two statements without a yield.
- `UpdateSourceAsync`: the callback cannot yield, returning `nil` cancels, the editor
  may reject and re-invoke, and the call yields until done.
- Which call reads back the edit-time source, and how it behaves.
- What happens to a running plugin thread when the plugin is reloaded or Studio is
  closed (whether a stale thread can keep running).
- The cost of a synchronous subtree scan, to calibrate L.
- `Enabled` and `Disabled` as two views of one state.

## Pending decisions

- The value of L, and the bounds of the replay cache, the ledger and the history.
  Both need a calibration against Studio.
- Expiry of work items.
- Executor identity and fencing, which need a mechanism of enforcement: a future
  architectural decision.
- A finer unit of the lock than the credential, which needs an identifier of a place
  or project on the wire; how several Studio instances under one credential coexist
  given P5; and the behaviour for Team Create.
- The user experience of the human attestation, which belongs to the web application.

The durable storage for the write-ahead record is SQLite
([ADR-0016](0016-sqlite-lifecycle-store.md)), the session inactivity limit is 900 s,
and the other choices that were open are settled in *Decisions taken on 2026-11-07*.

## Related ADRs

- [ADR-0002](0002-execution-boundary-and-autonomy.md) — the approval gate and the run log the history feeds.
- [ADR-0005](0005-credentials-and-thin-plugin.md) — the plugin is thin; what it verifies is mechanical.
- [ADR-0006](0006-protocol-single-source-of-truth.md) — schemas are authoritative for the wire; this record adds none beyond the error codes above.
- [ADR-0007](0007-plugin-initiated-http-transport.md) — the transport and the at-least-once delivery this record builds on.
- [ADR-0008](0008-edit-action-flat-operations.md) — its pre-flight is kept as an advisory step; the authoritative check is section 8 here.
- [ADR-0010](0010-script-execution-reach-and-action-semantics.md) — the assertions verified in section 8 and the `place` of playtests.
- [ADR-0013](0013-conformance-suites.md) — the `lifecycle` and `preflight` suites that will specify these behaviours as vectors.
