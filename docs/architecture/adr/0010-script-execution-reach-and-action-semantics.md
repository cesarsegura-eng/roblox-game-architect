# ADR-0010: Script execution reach and action semantics

- **Status:** Proposed
- **Date:** 2026-11-01
- **Amends:** [ADR-0008](0008-edit-action-flat-operations.md) — three things in it.
  The statements that "v1 has no activation" and that "generated scripts do not
  run in a v1 playtest until the user enables them" overstate what the protocol
  can guarantee. Its single `set_script_source` operation is split in two. And its
  ordering rules R1–R4 gain R5 and R6. Everything else in ADR-0008 stands.

The decisions below were reviewed and approved by the project owner. The status
stays *Proposed* until the text itself has been reviewed; it becomes *Accepted*
then.

## How to read the claims

Every claim in this record carries one of these tags, because a recommendation
that reads like a guarantee is the failure this record exists to correct.

- **[Protocol]** — a property of the schemas and the validation procedure.
- **[Plugin]** — a behaviour the Studio plugin must implement. The schemas cannot
  enforce it.
- **[API]** — a policy or behaviour of the API service or of `packages/sandbox`.
- **[Consumer]** — a decision for whatever displays or consumes the data.
- **[Assumption]** — something believed about Roblox Studio from its
  documentation and **not yet exercised in Studio**. It is not a confirmed fact.
- **[Pending]** — an open decision.

## Context

[ADR-0008](0008-edit-action-flat-operations.md) gave `edit.action` five primitive
operations and stated that no operation enables a script and that v1 has no
activation. Its consequences section drew from that the conclusion that generated
scripts do not run in a v1 playtest until the user enables them. The specification
in `docs/protocol/README.md` repeated both.

An independent audit of the implementation (finding H-1) showed that the
conclusion does not follow from the schemas as written:

- `set_script_source` can replace the source of **any** `Script`, `LocalScript` or
  `ModuleScript`, including one that is already enabled.
- `reparent` accepts any existing instance, so it can move an enabled script, or a
  folder that contains one, from one container to another.
- A `ModuleScript` has no run flag at all; it runs when something requires it, and
  the protocol cannot know what does.
- A playtest runs the place in which it is started, so it runs whatever is enabled
  there. **[Assumption]**

The Roblox documentation, as read during the audit, says a `Script` runs once its
`Enabled` property is true and it is a descendant of `Workspace` or
`ServerScriptService`, that `LocalScript` inherits from `Script`, and that a script
whose `RunContext` is not `Legacy` runs under a wider set of containers.
**[Assumption]** None of this has been exercised in Studio.

The precise statement is therefore narrower than the one ADR-0008 made: the
protocol offers no operation that *enables* a script. It does not follow that
agent-authored code cannot execute.

## Problem

1. What can the protocol actually guarantee about creating, modifying and moving
   scripts and about running playtests, and what can it not?
2. How is a script created by the agent distinguished from one that was already
   there, given that the protocol keeps no durable record of provenance?
3. What default policy is safe and still lets the product do useful work?
4. How does an approval summary learn, from the action alone, which operations
   introduce or change code?
5. How are contradictory operations inside one action detected deterministically,
   including after an instance has been moved to another path?

## Decision

### 1. What the protocol guarantees, and what it does not

**Guarantees G1–G5.** Each row names the layer that provides it. Only G1 and G5
are properties of the schemas alone; G2 is a requirement on the plugin, and G3 and
G4 need the protocol to carry an assertion and the plugin to verify it.

| # | Statement | Layer |
|---|---|---|
| G1 | No operation sets `Enabled`, `Disabled` or `RunContext`, and no operation enables a script. | **[Protocol]**. Holds in the schemas as written: the `set_property` allowlist excludes all three. |
| G2 | Every `Script` and `LocalScript` created by `create_instance` is created disabled **before** it is parented into the DataModel. The plugin reads the state back; if it cannot confirm that the script is disabled it fails the operation with `operation_failed` and destroys the instance. | **[Plugin]** behaviour. Not enforceable by a schema. **[Assumption]**: the semantics of `Enabled` and `Disabled`. The documentation describes `Enabled` as not replicated and not saved and `Disabled` as the saved property, so the plugin checks both views. |
| G3 | A source edit to a `Script` or `LocalScript` carries the required assertion `expect_enabled`, and is applied only if the script's enabled state equals it when the edit is applied. | **[Protocol]** requires the assertion; the **[Plugin]** verifies it (verification timing is in [ADR-0011](0011-delivery-execution-and-recovery.md)). |
| G4 | A `reparent` carries the required assertion `contains_scripts`, and is applied only if it equals the real state of the subtree: true if the target itself or any descendant, at any depth, is an instance of class `Script`, `LocalScript` or `ModuleScript`. | **[Protocol]** requires the assertion; the **[Plugin]** verifies it. |
| G5 | Every `playtest.request` states in `place` whether it runs in the `working` place or a `disposable` one. | **[Protocol]**. |

G3, G4 and G5 describe schema changes that have **not** been made. See *What
changes and what does not exist yet*.

**What the protocol does not guarantee.** These are stated so that no document
needs to imply the opposite.

1. Agent-authored code may execute. It can do so when a policy permits editing a
   script that is enabled; when a `ModuleScript` is required by code that runs;
   when a script, or a subtree containing one, is moved into a container where it
   runs **[Assumption]**; when a human enables a script; and in any playtest.
2. A script created disabled is not a script that will never run. It means only
   that no protocol operation can enable it.
3. A playtest in the `working` place has no isolation from the rest of the place.
4. A `ModuleScript` is not inert. Its execution reach is unknown.
5. Moving a script, or a subtree that contains one, into or out of a particular
   service neither isolates it nor reliably activates it. Which containers run
   scripts, and the effect of `RunContext`, are **[Assumption]**s.
6. `declared_scope` is lexical (section 10). It is not a statement about behaviour.
7. The protocol keeps no durable record of who created a script.
8. None of this is enforced yet. `packages/sandbox` contains only a syntax-only
   Lute bridge ([ADR-0014](0014-luau-source-analysis-with-lute.md)), which enforces
   none of it, and the plugin does not exist; the reference checks live only in
   `packages/protocol/tests/`. (When this record was written, `packages/sandbox`
   did not exist.)

### 2. Script, LocalScript and ModuleScript are separate operations

**[Protocol]** `set_script_source` is split in two.

- **`set_script_source`** targets `Script` and `LocalScript`. It carries the
  required boolean `expect_enabled`.
- **`set_module_source`** targets `ModuleScript` only. It carries no
  `expect_enabled`, because a `ModuleScript` has no enabled state.

They are separate operations rather than one operation with an optional flag so
that a validator can tell them apart by the `op` discriminator, which is how the
closed schema subset of [ADR-0009](0009-luau-validation-subset-and-strict-json.md)
keeps a `oneOf` decidable, and so that the flag cannot be present where it means
nothing or absent where it is required.

### 3. Agent-created and pre-existing scripts

There is no durable provenance in v1. The distinction is made from what the
protocol can see:

- **Created in this action** — the script's path is created by an earlier
  `create_instance` of the same action. This is known statically.
- **Observed** — any other script: one that was already in the place or was created
  by an earlier action. Its state is known only from a `project.state` snapshot
  (`script_state`, see below) and is asserted by the sender through
  `expect_enabled`.

Policy keys on observable state — the enabled flag, the class and the service —
not on origin. After a human enables an agent-created script, it is an *observed
enabled* script and is treated as such.

### 4. The two preconditions

`expect_enabled` and `contains_scripts` are assertions by the sender that the
plugin checks against the real state. They are the same kind of thing as
`expect_class` (ADR-0008): they put no policy in the plugin; they let the plugin
refuse to apply an edit whose premise is false.

- If an assertion does not hold, the operation fails with the operation error
  `state_mismatch`. Nothing is changed by that operation.
- A sender that is wrong about a script's state therefore gets a refusal, never a
  silent live-code change.
- How and when the plugin verifies them, including that the check is repeated when
  the edit is applied, is decided in
  [ADR-0011](0011-delivery-execution-and-recovery.md).
- A planner learns a script's enabled state from `script_state` on `project.state`
  entries. That field is an **observation**: it does not make `Enabled` writable.

### 5. Approval policy

**[API]** The following is the intended default policy. It is **not yet applied**:
it is to be enforced by the API and `packages/sandbox`, whose policy checks do not
exist yet (the package has only a syntax-only Lute bridge,
[ADR-0014](0014-luau-source-analysis-with-lute.md)). It can be changed without
changing the wire format. Loosening it changes approval *granularity*; it never
loosens gate 1 of [ADR-0002](0002-execution-boundary-and-autonomy.md), the static
validation of source, which applies to every source that enters through either
operation.

| Operation | Condition | Default |
|---|---|---|
| `create_instance` of `Script` or `LocalScript` | inside the declared scope | Allowed. Created disabled (G2). Approval shows the source set for it. |
| `create_instance` of `ModuleScript` | inside the declared scope | Allowed. Labelled *execution reach unknown*. Approval shows the source. |
| `set_script_source` | script created in this action, `expect_enabled: false` | Allowed, standard approval. |
| `set_script_source` | observed script, `expect_enabled: false` | Allowed, standard approval. |
| `set_script_source` | observed script, `expect_enabled: true` (a live code change) | **Denied by default.** Allowed only with an itemised approval for that script. |
| `set_module_source` | module created in this action | Allowed, standard approval. |
| `set_module_source` | observed module | Itemised approval, because its reach is unknown. |
| `reparent` | `contains_scripts: false` | An ordinary modification. |
| `reparent` | `contains_scripts: true`, source and destination in the same service | Approval, with the scripts called out. |
| `reparent` | `contains_scripts: true`, different services | **Denied by default.** Itemised approval if enabled. |
| `delete_instance` of a script | | An ordinary deletion; itemised approval as in `docs/safety.md`. |
| Playtest, `place: working` | | Human approval for each run. |
| Playtest, `place: disposable` | | See section 6. |

"Same service" means the same first path segment.

### 6. Playtests

**[Protocol]** `playtest.request` carries the required field `place`, whose values
are `working` and `disposable`. `playtest.report` gains the outcome `unsupported`,
meaning that the plugin cannot honour the request.

- **`working`** is the place the user has open. A playtest there runs everything
  that is enabled in it, every module that running code requires, and every change
  the agent has already applied. **[API]** Each run requires human approval. The
  protocol provides no isolation.
- **`disposable`** is a copy built for the test. **Playtests in a disposable place
  are not supported in v1.** The mechanism is undesigned (`docs/safety.md`, known
  gaps). **[Plugin]** A v1 plugin answers a `disposable` request with outcome
  `unsupported`; **[API]** treats that as "not run".
- A user who starts Play in Studio by hand is outside what the protocol can
  control.

Direction, not a decision **[Pending]**: the intended way for generated code to run
without touching the working place is to enable scripts only inside a disposable
copy. That needs a design of its own for how the copy is built and how scripts are
enabled in it. Whether Studio makes it feasible is an **[Assumption]**. Activating
a script in the working place remains a human action.

### 7. Modules

A `ModuleScript` has no run flag. It runs when something requires it, and the
protocol cannot know what requires it: a require may name a path, may resolve a
name at run time, or may come from code that is not in scope. Therefore the
protocol and this record make **no** claim that a module is inert, that a newly
created module has no requirers, or that moving a module into a particular service
isolates it. The policy labels modules *execution reach unknown* and approves them
accordingly.

### 8. R5: deterministic classification of code effects

**[API]** R5 is a pure function of the action. For each operation it yields a set of
labels, possibly empty. It decides nothing by itself; it feeds the approval summary
and the policy of section 5.

| Label | Given by |
|---|---|
| `new_code` | `create_instance` whose `class_name` is `Script`, `LocalScript` or `ModuleScript` |
| `dormant_edit` | `set_script_source` with `expect_enabled: false` |
| `live_code_change` | `set_script_source` with `expect_enabled: true` |
| `module_change` | `set_module_source` |
| `code_move` | `reparent` with `contains_scripts: true` |
| `reach_change` | a `code_move` whose target and `new_parent` start at different services |

An operation may carry two labels; a cross-service `code_move` carries `code_move`
and `reach_change`. R5 depends on the asserted booleans. They are verified by the
plugin when the operation is applied (G3, G4), so a false assertion fails the
operation instead of changing what runs. A `reparent` with `contains_scripts: false`
carries no label.

### 9. R6: logical identity and repeated writes

**Within one action, an instance keeps a logical identity (LID) even when a
`reparent` changes its path.** The LID is internal to the checker and to
`packages/sandbox`. It never appears on the wire; the wire keeps addressing by path.

The assignment is a pure function of the ordered operations and uses a single piece
of state, a table from current path to LID:

1. A path named for the first time that is not in the table and not beneath a
   stale prefix (R2) receives a new LID. It stands for an instance that existed
   before the action, known only by that path at that moment.
2. `create_instance` gives the new path a new LID and marks it created by this
   action.
3. `reparent` of T to a new location D rebinds T's LID to the destination path.
   Every table entry whose path begins with T is rewritten to begin with the new
   location, so descendants named earlier are carried along. T becomes a stale
   prefix.
4. `delete_instance` removes T's LID and every entry beneath T, and T becomes a
   stale prefix.

Because of step 3, naming the new path after a move resolves to the same LID as the
old path did.

Rules on LIDs, all **[API]**:

| Situation | Result |
|---|---|
| The same (LID, property) is written twice by `set_property` | `conflicting_write` |
| The same LID receives two source edits, by either source operation | `conflicting_write` |
| A LID created in this action is deleted in this action | `create_then_delete` |
| A write reaches an instance through its **old** path after a move or delete | `stale_target` (R2), unchanged |

Explicitly permitted, so as not to restrict for its own sake: writing through the
new path after a move, moving an instance more than once, writing and then moving,
and writing and then deleting.

`conflicting_write` and `create_then_delete` extend the closed list of action
violation codes of the reference checks (which today holds `duplicate_op_id`,
`scope_violation`, `forward_reference`, `stale_target`, `duplicate_target`,
`invalid_reparent` and `created_class_mismatch`). They are semantic codes. They are
not wire error codes and appear in no schema.

### 10. The declared scope is lexical

`declared_scope` is compared with paths, segment by segment. It says nothing about
behaviour. A `ModuleScript` edited inside the scope may be required by scripts
outside it; changing a property of a part inside the scope may affect parts joined
to it outside; none of that is visible to the check. ADR-0008 never claimed
otherwise, but a reader of the scope rules could assume it.

## What changes, and what does not exist yet

**Nothing in this record is implemented.** The schemas, vectors and tests in the
repository describe the state before it. The following changes belong to one
protocol pull request that must land **before** the tag `protocol-v1.0`, because
after the tag they are a major version:

- `edit.action.json`: split `set_script_source` / `set_module_source`; add
  `expect_enabled`; add `contains_scripts` to `reparent`.
- `error.operation.json`: add the code `state_mismatch`.
- `project.state.request.json`: an optional `script_state` object on entries of
  class `Script` and `LocalScript`, carrying the observed enabled state.
- `playtest.request.json`: the required field `place`.
- `playtest.report.request.json`: the outcome `unsupported`.
- The reference checks, vectors and documentation updated to match.

Documentation corrected together with this record, without changing any contract:
the sentences in `docs/protocol/README.md`, `docs/safety.md`, `ARCHITECTURE.md` and
`packages/protocol/README.md` that said generated scripts do not run in a v1
playtest now say what the protocol does and does not guarantee, and point here.

## Alternatives considered

- **Forbid every script operation in v1.** Rejected: game logic is code, and the
  product cannot build games without it.
- **Forbid `reparent` of scripts in the schema.** Rejected: the schema cannot see
  the contents of a moved folder. A verified assertion can.
- **Rely on dormancy by container.** Rejected: the documentation indicates that
  scripts with a `RunContext` other than `Legacy` run under more containers
  **[Assumption]**, so a container is not a reliable boundary.
- **Provenance tags on instances the agent creates.** Rejected for v1: it writes
  state into the user's place, the user can remove it, and the variable that matters
  is the enabled state, not the origin. It can be revisited.
- **An `enable_script` operation now.** Rejected here. It deserves its own record
  and an approval bound to the reviewed source. See the direction in section 6.
- **Block edits to enabled scripts in the schema.** Rejected: it would make it
  impossible to improve an existing game. The precondition plus the default-deny
  policy keeps the choice with the human.
- **One `set_script_source` with an optional `expect_enabled`.** Rejected: it
  breaks the discriminator rule and allows the flag where it means nothing.

## Consequences

**Positive**

- The documentation stops claiming something the architecture does not guarantee.
- A planner cannot change live code by mistake: a wrong assertion fails the
  operation.
- An approval summary can say, from the action alone, which operations introduce or
  change code.
- Contradictory actions, including ones that hide behind a move, are detected
  without a persistent identifier on the wire.
- The product keeps its useful default: dormant script work needs no special
  approval.

**Negative and risks**

- Six operations instead of five, and two new required assertions the planner must
  produce.
- A planner that does not know a script's state has to read it from a snapshot,
  and snapshots are bounded (2,000 entries).
- Live edits and cross-service code moves are denied by default, which is friction
  for users who want them.
- The default policy is not enforced by anything until the policy checks of
  `packages/sandbox` exist; today it has only a syntax-only Lute bridge.
- `contains_scripts` needs a subtree scan by the plugin; its bound is in ADR-0011.
- Every statement tagged **[Assumption]** may turn out wrong when exercised in
  Studio, and G2 in particular rests on it.
- Without a disposable place, generated code cannot be run both safely and
  autonomously. The vertical slice of stage 4 depends on a design that does not
  exist.

## Assumptions to validate in Roblox Studio

- A `Script` runs once enabled and a descendant of `Workspace` or
  `ServerScriptService`; the effect of `RunContext`; which containers run scripts.
- `Enabled` and `Disabled` are two views of one state, and disabling before
  parenting prevents any run.
- A `ModuleScript` runs only when required.
- Reading the enabled state and the source back from the plugin behaves as the
  documentation describes.

## Pending decisions

- How a disposable place is built and how scripts are enabled in it.
- Whether an `enable_script` operation exists, and with what approval.
- Whether durable provenance becomes necessary.
- Whether scripts deleted by `delete_instance` need a label of their own.

## Related ADRs

- [ADR-0002](0002-execution-boundary-and-autonomy.md) — the three gates and the autonomy matrix this policy sits inside.
- [ADR-0005](0005-credentials-and-thin-plugin.md) — why the plugin verifies assertions and carries no policy.
- [ADR-0006](0006-protocol-single-source-of-truth.md) — schemas are authoritative; a protocol change is its own pull request.
- [ADR-0008](0008-edit-action-flat-operations.md) — amended by this record.
- [ADR-0009](0009-luau-validation-subset-and-strict-json.md) — the closed subset the new operations must respect.
- [ADR-0011](0011-delivery-execution-and-recovery.md) — when the plugin verifies the assertions, and what an uncertain edit reports.
- [ADR-0013](0013-conformance-suites.md) — the suites that will carry the vectors for R5 and R6.
