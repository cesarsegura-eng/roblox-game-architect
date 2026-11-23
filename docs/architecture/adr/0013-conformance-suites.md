# ADR-0013: Conformance suites as the shared contract

- **Status:** Proposed
- **Date:** 2026-11-01
- **Amends:** [ADR-0009](0009-luau-validation-subset-and-strict-json.md) — decision
  5, "the vectors are the conformance suite". That decision named three kinds of
  vector in one directory. This record replaces the layout with six suites, gives
  each a contract, and states who consumes it. Its statement that each invalid
  vector has exactly one defect is **kept** for the `schema` suite and generalised
  to "one primary defect" for the others.

The decisions below were reviewed and approved by the project owner. The status
stays *Proposed* until the text itself has been reviewed; it becomes *Accepted*
then.

## How to read the claims

- **[Protocol]** — a property of the schemas and the validation procedure.
- **[Plugin]** — a behaviour the Studio plugin must implement. The schemas cannot
  enforce it.
- **[API]** — a policy or behaviour of the API service or of `packages/sandbox`.
- **[Consumer]** — a decision for whatever displays or consumes the data.
- **[Assumption]** — something believed about Roblox Studio from its
  documentation and **not yet exercised in Studio**. It is not a confirmed fact.
- **[Pending]** — an open decision.

## Context

[ADR-0006](0006-protocol-single-source-of-truth.md) makes the schemas the single
source of truth, requires both sides to validate, and says a protocol change is its
own pull request. [ADR-0009](0009-luau-validation-subset-and-strict-json.md) added
the idea that makes "both sides validate" testable: a set of vectors, a plain data
file per case, that every implementation must answer the same way. Today they live in
`examples/v1/` as `valid/`, `invalid/` and `parse/`, with an `index.json`, and a
single Python implementation runs them.

An independent audit (findings M-6 and M-7) found what that leaves out:

- The rules of [ADR-0008](0008-edit-action-flat-operations.md) for scope and ordering
  exist only as Python in `packages/protocol/tests/`. They have no portable vectors,
  although ADR-0008 says `packages/sandbox` will implement them "against shared
  vectors".
- The decisions of [ADR-0010](0010-script-execution-reach-and-action-semantics.md),
  [ADR-0011](0011-delivery-execution-and-recovery.md) and
  [ADR-0012](0012-untrusted-text-and-unicode-rendering.md) add behaviour — logical
  identity, state machines, verification when an operation is applied, a renderer —
  that has to be specified in a form more than one language can run.
- The parse vectors miss the inputs most likely to make a second parser disagree
  with the first, and a JSON file cannot hold some of them at all, such as bytes that
  are not UTF-8.

**What exists today.** The Python reference runs the schema and parse vectors and a
set of hand-written semantic cases. No Luau code, no API, no `sandbox`, no plugin and
no web application exists. No consumer other than the Python reference has ever run
a vector.

## Problem

1. How are the suites organised so that each kind of behaviour has a contract that
   is precise and implementation-independent?
2. Which implementations are expected to consume which suite?
3. How are vectors identified and versioned so that they can be relied on over
   years?
4. How are vectors written so that expectations come from the specification and not
   from whatever an implementation happens to do?

## Decision

### 1. What a suite is

A **suite** is a directory of vector files that exercises one contract, plus a
meta-schema for those files, and a short README that states the contract and lists
which consumers run it today. Vectors are data and contain no code. **Expected results
are authored from the specification and reviewed. They are never recorded from the
output of an implementation**, so no implementation can validate itself.

### 2. Location

**[Pending]** The suites will live under `packages/protocol/conformance/v1/`. That
replaces `examples/v1/`: "examples" understates the normative role, and moving
before the tag `protocol-v1.0` is cheap, whereas afterwards every link and every
consumer would have to follow. **This record moves nothing.** Until the
implementation pull request, the existing vectors stay where they are.

### 3. The six suites

| Suite | Contract it fixes | Input | Expectation |
|---|---|---|---|
| `json-profile` | The strict JSON profile ([ADR-0009](0009-luau-validation-subset-and-strict-json.md), [ADR-0012](0012-untrusted-text-and-unicode-rendering.md)) | `text`, or `bytes_hex` | Accept or reject. The reason code is informational. |
| `schema` | Validation of a whole message against the schemas | a message | Valid, or the stage and the instance path of the failure. `keyword` and `inner` are informational. |
| `semantics` | Scope and ordering rules R1–R6 and the code-effect labels R5 | an action | The list of violations — operation index and code — and the labels per operation. |
| `preflight` | What the plugin checks and reports for an action against a tree, including changes made while the action runs | a tree, an action, optional interleaved edits | Per-operation status and error code, the outcome, and the resulting tree. |
| `lifecycle` | The state machines, the lock and the records of ADR-0011 | a trace of events | After each step, the states, the kind of response and the history appended. |
| `text-safety` | The renderer of ADR-0012 | code points | The rendered code points and flags. |

`json-profile` and `schema` are the successors of today's `parse/` and of
`valid/` plus `invalid/`.

### 4. Rules common to every vector

- **Stable identifier.** Each vector has an `id` in kebab-case, unique in its suite,
  that names the behaviour and carries no number. An identifier is never reused.
  A vector that must be retired is withdrawn and keeps its identifier recorded as
  withdrawn. Changing what a vector expects is a new vector with a new identifier,
  not an edit, unless the change corrects an error in the specification.
- **Version metadata.** Each vector records the protocol version in which it first
  applies (`since`, as `MAJOR.MINOR`). Each suite records its own version. Adding
  vectors raises the suite's minor version; changing an expectation raises the major
  version. The manifest lists the suites, their versions and the version of any
  shared data they use.
- **A description, and tags.** The description says why the vector exists.
- **One primary defect.** An invalid vector isolates one root cause. When one cause
  necessarily produces several diagnostics — a deleted parent makes both the parent
  and the path beneath it stale — the expectation lists all of them and the
  description says which is the primary one. The `schema` suite keeps the stricter
  rule of ADR-0009: exactly one error.
- **Inputs a JSON file cannot hold.** Binary input is written as `bytes_hex`,
  lowercase and of even length, so that invalid UTF-8 — overlong forms, values above
  U+10FFFF, five-byte forms, UTF-16, an encoded surrogate — is representable. Text
  for `text-safety` is written as an array of code points, so that no file contains
  an invisible or ambiguous character. Large inputs are described by a `generate`
  recipe, as today.
- **Files.** ASCII, LF, a trailing newline, and no secret, credential or real
  project content.
- **Meta-schemas.** Each suite has a JSON Schema for its vector files, written in the
  closed subset of ADR-0009, under `meta/`. The Python tests validate every vector
  file against it. A consumer in another language does not need to.
- **Machine-readable index.** Runtimes that cannot list a directory load the
  vectors from the manifest.

Field names in this record are working names; the meta-schemas fix them.

### 5. What each suite must cover

**`json-profile`.** The cases the audit found missing: whitespace that is not JSON
(vertical tab, form feed, no-break space, U+2028); invalid escapes (`\x`, `\'`, short
or non-hexadecimal `\u`, capital `\U`); malformed numbers (`1e`, `1e+`, `-`, `--1`,
`0.`, `-.5`, `00`, `-01`); misspelt literals; comments; two documents; control
characters other than a line feed inside a string; U+0000 literal and escaped
(ADR-0012); **invalid UTF-8 as `bytes_hex`**; a byte-order mark; the negative integer
bound as accepted; and nesting depth reached with **objects** as well as with arrays,
at 12 (accepted) and 13 (rejected). Duplicates include keys that are equal only after
their escapes are decoded and one written in different case of the hexadecimal digits.

**`schema`.** The present contract: stage (`dispatch`, `envelope`, `payload`), the
instance path, one error, and — for a `oneOf` — the branch intended.

**`semantics`.** Comparison of paths **by segment, not by string** (`Map` against
`Map2`); `self` against `subtree` for creating, setting, deleting and moving;
reparent followed by the old path, an old descendant, and a double move; cycles by the
current location and by the old one; references to objects created earlier in the
action; scope exceeded by each kind of effect; and, for ADR-0010, **logical identity**:
a write repeated through a move, repeated source edits, create-then-delete, and the
cases that are explicitly permitted. It also carries the R5 labels.

**`preflight`.** The fixture is a tree: instance names, classes, children, and the
enabled state of scripts, including siblings with the same name. It covers
`ambiguous_target`, `name_conflict`, `class_mismatch`, `state_mismatch` for both
assertions, a cycle in the real tree, a move with descendants, and a subtree larger
than the scan limit L. The suite also carries **interleaved modifications**: an
external edit applied before operation *k*, or during the *n*-th invocation of the
callback of a simulated `UpdateSourceAsync`, whose double must be able to cancel,
reject and re-invoke the callback, and to fail after an invocation with each of the
read-back results of ADR-0011. These express the premise that verification is made
when an operation is applied. They do not establish that Studio behaves this way
**[Assumption]**.

**`lifecycle`.** A trace is an ordered list of events — approval, a poll with a
`message_id` and a session, a result, a `hello`, the end of a session by expiry,
supersession or API restart, a plugin restart, a human attestation, a snapshot, a
cancellation — and, after each, the expected execution state, outcome knowledge, lock
state, kind and code of the response, whether it is a replay, and the history events
appended. The API half and the plugin half are separate parts of the same vector.
Required traces include: delivered and not received; retry with the same and with a
new `message_id`; received; executing; plugin restart during execution; result lost;
duplicate result; contradictory result; late result from a new session; each trigger
T1–T4 of the lock and its release by a result and by an attestation; approved items
returning to `queued`; and the playtest equivalents. Every trace must show that an
item of unknown outcome is not delivered again.

**`text-safety`.** The renderer of ADR-0012: each escaped family; bidirectional
controls; tag characters; variation selectors; the marks rule at the start, after a
space, after an escaped code point and in a run longer than four; unassigned code
points; and a set of distinct inputs that must render distinctly — including text that
literally contains `\u{202E}` and a backslash — which is the vector form of
injectivity. A separate, non-blocking group holds the advisory warnings, which are
not part of the contract.

### 6. Who runs what

This is the **future** division of responsibility. Today only the Python reference
exists.

| Component | Suites it must run |
|---|---|
| Python reference (`packages/protocol/tests`) | all of them, as the executable specification |
| API (Python) | `json-profile` and `schema` for its parser and validator; its half of `lifecycle`; `text-safety` for logs and for model input |
| `packages/sandbox` | `semantics` |
| Plugin (Luau) | `json-profile`, `schema`, `preflight`, its half of `lifecycle`, and `text-safety` for its confirmation dialog |
| Web application | `text-safety`, and the advisory group |

The reference implementations remain test-only and are not importable by production
code. They validate the specification; they are not the specification.

### 7. Shared data

The Unicode table of [ADR-0012](0012-untrusted-text-and-unicode-rendering.md) is data
that the `text-safety` suite and every renderer share. It will live with the suites,
be listed in the manifest with its version, and be loaded — not copied — by the
consumers. It does not exist yet, and the Unicode version it needs is a pending
decision.

### 8. Process

- A protocol change that alters an expectation changes the vectors in the same pull
  request, and raises `since` or the suite's version as above (ADR-0006, rule 6).
- A vector for a rule is written **before** the component that implements the rule,
  so the first implementation is checked against something it did not produce.
- Each suite's README says which consumers run it today. A suite no consumer runs is
  marked as such. Nothing in this record claims that Luau, the API, `sandbox`, the
  plugin or the web application conforms.

## What changes, and what does not exist yet

**Nothing in this record is implemented, and no vector is created or moved by it.**
The existing `examples/v1/` vectors, the schemas and the tests are unchanged.
Creating the suites, the meta-schemas, the manifest, the shared table and the
consumers is the work this record prepares.

## Alternatives considered

- **Keep the single `examples/` directory and add kinds to it.** Rejected: contracts
  with different inputs and expectations mixed in one place cannot be validated by one
  meta-schema.
- **Generate the vectors in each language.** Rejected: the languages would drift apart
  and the generators would become the contract.
- **Keep the semantic rules as Python tests only.** Rejected: `sandbox` and the plugin
  could not check themselves against them, and the rules would be a prose description
  for everyone but Python.
- **Record expectations from an implementation's output.** Rejected: it makes the
  implementation its own judge.
- **Property-based testing instead of vectors.** Rejected as the only mechanism: it
  does not travel between languages. It remains useful inside one language, for
  example to check that the renderer is injective.
- **A single large manifest in place of per-vector files.** Rejected: review diffs are
  unreadable and one change touches everything.
- **Another file format.** Rejected: JSON is what the protocol already uses and is
  what Luau can read.

## Consequences

**Positive**

- Every behaviour decided in ADR-0010 to ADR-0012 has a place where a second
  implementation can be checked against it.
- `sandbox` and the plugin will be written against vectors that exist before them.
- The inputs that make parsers disagree are representable.
- Identifiers and versions let a vector be relied on, cited and withdrawn without
  ambiguity.
- The division of work between Python, Luau, the API, `sandbox`, the plugin and the web
  application is explicit.

**Negative and risks**

- A substantial body of vectors and meta-schemas to write and keep correct, much of it
  by hand because expectations may not be recorded from an implementation.
- Six suites to maintain, two of which — `preflight` and `lifecycle` — need a
  simulated Studio or a simulated state machine to be run at all.
- A suite with no consumer gives no assurance. Until Luau, the API, `sandbox` and the
  plugin exist, the strongest honest statement is that the Python reference passes the
  vectors that apply to it.
- The `preflight` vectors depend on **[Assumption]**s about Studio's behaviour. They
  specify what a conforming plugin does; they do not show that Studio permits it.
- Moving to `conformance/` breaks every link to `examples/v1/` unless the references
  are updated in the same change.
- A mistake in a hand-written expectation will be reproduced by every implementation
  that is checked against it; review of the vectors is the only defence.

## Pending decisions

- The timing of the move from `examples/v1/` to `conformance/v1/`.
- The field names, fixed when the meta-schemas are written.
- The Unicode version of the shared table, which blocks the `text-safety` suite.
- Whether the manifest carries checksums.

## Related ADRs

- [ADR-0006](0006-protocol-single-source-of-truth.md) — rule 1 (schemas are authoritative), rule 4 (both sides validate) and rule 6 (a protocol change is its own pull request) are what the suites make checkable. This record does not amend it.
- [ADR-0008](0008-edit-action-flat-operations.md) — the scope and ordering rules the `semantics` suite will carry.
- [ADR-0009](0009-luau-validation-subset-and-strict-json.md) — amended by this record: its vectors become the suites above.
- [ADR-0010](0010-script-execution-reach-and-action-semantics.md) — R5, R6 and the preconditions the `semantics` and `preflight` suites cover.
- [ADR-0011](0011-delivery-execution-and-recovery.md) — the behaviours the `lifecycle` and `preflight` suites specify.
- [ADR-0012](0012-untrusted-text-and-unicode-rendering.md) — the profile rule, the renderer and the shared table.
