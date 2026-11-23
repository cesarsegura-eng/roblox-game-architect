# ADR-0008: `edit.action` is a flat list of primitive operations

- **Status:** Accepted
- **Date:** 2026-11-01
- **Amended by:** [ADR-0010](0010-script-execution-reach-and-action-semantics.md)
  (proposed; it takes effect when that record is accepted) — the statements below
  that there is no activation and that generated scripts do not run in a v1
  playtest until the user enables them overstate what the protocol guarantees; the
  single `set_script_source` operation is split in two; and the ordering rules gain
  R5 and R6. The body below is left as written, because an accepted ADR is a record,
  not a document to edit.

## Context

`ARCHITECTURE.md` marked the shape of `edit.action` as a decision on the critical
path, and said why: it determines how precisely the blast-radius check of
[ADR-0002](0002-execution-boundary-and-autonomy.md) can be expressed. That check
says the instances a change touches must be a subset of what the task declared.
Whatever shape the edit has, "what does this touch?" has to be answerable from the
message alone, in a package (`sandbox`) that has no Studio to ask.

Three further forces:

- The plugin is the most privileged component and must think the least
  ([ADR-0005](0005-credentials-and-thin-plugin.md)). It cannot be where the scope
  policy lives.
- The agent writes code, and code is the one thing a "set a property" operation
  must never become a way to smuggle in. A script that is created and runs before
  anyone has seen it defeats gate 2.
- Roblox allows several siblings with the same name, instances move, and the user
  keeps editing while an approval waits. A path is not an identity.

## Decision

**An edit is a flat, ordered list of primitive operations**, not a tree. Five
kinds: `create_instance`, `set_property`, `set_script_source`, `reparent`,
`delete_instance`. There is no rename, no operation that enables a script, and no
operation that sets `Name` or `Parent`.

**Addressing.** An instance is an absolute path (an array of segments, never a
string with separators). Every existing instance is addressed as `{path,
expect_class}`; `expect_class` is the exact `ClassName`, compared by equality. A
created instance has no separate identifier: its path is `parent + [name]`,
unique by construction because creation fails with `name_conflict` when a sibling
of that name exists.

**Scope.** An action carries `declared_scope`, entries of `{path, extent}`. Each
operation's effects are computed from the action alone, in one in-order pass.
Creating touches the new path (`self`); setting touches the target (`self`);
deleting touches the target (`subtree`); moving touches source and destination
(both `subtree`). An effect is covered by a `subtree` entry that is a prefix of
its path, or by a `self` entry equal to it. Deleting and moving require subtree
coverage on purpose: it is the conservative reading.

**Ordering rules**, all decidable without the state of the place: no forward
references (R1); no use of a path after it was deleted or moved (R2); no
duplicate creations, no recreating a deleted path (R3); a reparent has a target of
at least two segments and a new parent that is neither the target, beneath it, nor
its current parent, which also rules out cycles made of several moves (R4). A
created or moved path named again must carry the class it was created with.

**Who checks what.** `packages/sandbox` is the single authority on scope and
ordering. The plugin does not evaluate scope policy. It performs a pre-flight that
depends on the place and mutates nothing: existence, ambiguity, class, name
conflicts, cycles, on a virtual tree laid over the real one. A reference
implementation of the rules exists **only inside `packages/protocol/tests/`** as an
executable specification, so the rules are tested now without a second owner of
them existing in the source tree.

**The `set_property` allowlist lives in the schema.** `messages/edit.action.json`
has one `oneOf` branch per allowed property, each fixing the classes it applies to
(exact `ClassName`, `Part` and `WedgePart` in v1), the shape of its value and its
bounds. Both validators therefore enforce it, and the vectors cover it, with no
second source of truth. `sandbox` may restrict it further and may never loosen it.
Growing it later means adding a property or a branch, annotated `x-since`;
widening an existing property's enum or bounds is not a minor change.
`create_instance` and `set_script_source` take closed class lists in the same way.

**Scripts.** Creating a script and giving it source are separate operations;
`create_instance` has no `source`. The plugin creates every `Script` and
`LocalScript` **disabled, before assigning its parent**, confirms by reading the
state back, and otherwise fails the operation and destroys the instance. **v1 has
no activation**: the user enables a script in Studio. Source is written with
`ScriptEditorService:UpdateSourceAsync`.

## Consequences

**Easier:**

- The blast-radius check is a pure function of the message. It can be tested, and
  it can run in `sandbox` with no Studio.
- The plugin stays thin: it carries no policy, only mechanical checks that need the
  place.
- The allowlist is reviewable as a diff of one file, and the schema, not a
  convention, is what makes an unlisted property impossible to send.
- A created script cannot run before its source has been reviewed and approved.

**Harder:**

- A flat list is more verbose than a tree for large constructions, and the 100
  operations and 1 MiB limits make the sender split big builds into several actions.
- Conservative coverage will make `sandbox` reject some edits a human would call
  fine. Declaring scope is work the planner must do up front, as ADR-0002 already
  says.
- Rules R1–R4 forbid some natural sequences (touching a path again after moving
  it, replacing a path by deleting and recreating it in one action).
- Closed enums and bounds in a major version are permanent in practice. Choosing
  them wrongly costs a major bump, or a new property.
- **Generated scripts do not run in a v1 playtest until the user enables them.**
  The stage 4 vertical slice needs an answer, which will be its own ADR: an
  activation operation with an approval bound to the reviewed source.
- Destructive-looking operations carry no flag. The plugin derives them from the
  operation kind, which is one more rule it must implement correctly.

**Given up:** the compactness of a tree, a stable identity for instances, atomic
actions, and rollback. Studio has no transactions, and `partial` is a real outcome.

## Alternatives considered

- **A tree mirroring the instance hierarchy.** Compact, but the set of affected
  instances becomes implicit in the structure, so the blast-radius check has to
  interpret a tree instead of reading a list. Rejected: it makes the safety check
  harder to state and to test.
- **The allowlist as a data file owned by `sandbox`.** Keeps policy out of the
  protocol, but then the plugin would need to ship and trust a second artefact, a
  stale plugin would hold a stale list, and validity would split across two sources.
  Rejected; the single-source rule is worth the cost of a protocol PR per property.
- **Matching classes with `IsA`.** More flexible, but then the static check, which
  has no inheritance table, and the plugin could disagree. Exact `ClassName` is
  decidable from the message.
- **Generic, tagged property values.** More extensible, but it moves the type of a
  value from the schema into data, and the allowlist could not constrain it. The
  property fixes the type instead.
- **Identifiers for created instances.** A path is already unique by construction
  and a second naming scheme would be a second thing to keep consistent.
- **The plugin re-checking scope.** Defence in depth, but two implementations of
  the same rule in two languages is the drift this package exists to prevent, and
  ARCHITECTURE.md names `sandbox` as the single authority on validation.
- **Creating a script with its source in one operation, or an `enabled` flag.**
  Convenient, and exactly how an unreviewed script ends up running.
