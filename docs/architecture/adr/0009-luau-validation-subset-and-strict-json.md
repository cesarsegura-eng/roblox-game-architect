# ADR-0009: Both sides validate: a closed schema subset and a strict JSON profile

- **Status:** Accepted
- **Date:** 2026-11-01
- **Amended by:** [ADR-0012](0012-untrusted-text-and-unicode-rendering.md) and
  [ADR-0013](0013-conformance-suites.md) (both proposed; they take effect when they
  are accepted). ADR-0012 adds a rule to the strict JSON profile of decision 3:
  U+0000 is not accepted in any string. ADR-0013 replaces the layout of the vectors
  in decision 5 with six suites, each with a contract, and keeps the rule that a
  `schema` vector has exactly one defect. The body below is left as written, because
  an accepted ADR is a record, not a document to edit.

## Context

[ADR-0006](0006-protocol-single-source-of-truth.md) requires that both sides
validate and recorded the risk that made this hard: Luau has no mature JSON Schema
validator, so the plugin-side validation "will likely need either generated
validators or a hand-written subset". `ARCHITECTURE.md` named it as one of the two
decisions to settle before the contract could be written. Without an answer, "both
sides validate" is not real.

Two facts decide the shape of the answer.

**Validation is not only schema validation.** A validator can only judge what the
parser gave it, and the parsers disagree. Checked on 2026-11-01:

- Python's `json` accepts `NaN`, `Infinity` and `1e999` (which becomes infinity),
  keeps the last of two duplicate keys, accepts a lone surrogate escape, and turns
  `null` into `None`.
- `HttpService:JSONDecode` is documented to produce a table and little else. It is
  silent on duplicate keys, `null` and non-finite values. Luau tables cannot hold
  `nil`, so a `null` cannot survive the decode: `{"work": null}` and `{}` become
  the same value.
- `rxi/json.lua`, a typical pure-Lua decoder, overwrites duplicate keys, maps
  `null` to `nil`, and parses numbers with `tonumber`, which accepts forms JSON
  does not.

A message can therefore be valid to one side and a different message, or an
invalid one, to the other. That is the cross-language bug this package exists to
prevent, and it appears before any schema is consulted.

**No Luau code can be written and tested in this phase.** There is no Luau runtime
in the development environment, and the plugin is out of scope.

## Decision

**1. The schemas use a closed subset of JSON Schema** (Draft 2020-12): `type`
(a single name, never `null`), `enum` and `const` (strings and integers only),
`properties`, `required`, `additionalProperties: false`, `items`, `minItems`,
`maxItems`, `minLength`, `maxLength`, `minimum`, `maximum`, `oneOf`, a
`$ref` to a file of the set or to one of its `$defs` (alone in its schema), and the annotations `x-untrusted` and
`x-since`. No `pattern` and no `format`, because Luau has no regular expressions;
identifiers are length-bounded strings. Every object is closed, every string,
array and number is bounded, every `oneOf` branch is told apart by a differing
`const`, and there are no cycles.

**2. Tests enforce the subset.** They walk every schema file and every subschema —
what a `$ref` points at is a file in the set and is audited like any other — and
fail on a keyword outside the list, an open object, an unbounded value, an
orphaned file, an unused definition, a cycle, or a property named like a prompt, a
provider or a secret. They also prove the audit has teeth by feeding it
deliberately bad schemas.

**3. Both sides parse under one strict JSON profile**, specified in
[`docs/protocol/README.md`](../../protocol/README.md): UTF-8 without a BOM, a
top-level object, at most 1 MiB, nesting at most 12, no duplicate keys (compared
after decoding escapes), no `null`, no non-finite number, integer literals within
2^53, no lone surrogate. A message that fails the profile never reaches schema
validation. String lengths count code points.

**4. The Luau side will use a single-pass parser written for the profile**, not
`HttpService:JSONDecode`. **It is not implemented in this phase.** It belongs to
the plugin stage, and until it exists Luau conformance is *specified, not
verified*. This ADR commits to its design; it does not claim it works.

**5. The vectors are the conformance suite.** `examples/v1/` holds valid, invalid
and parse vectors. Every implementation must agree with each on validity, on the
stage of the failure (`parse`, `dispatch`, `envelope`, `payload`) and on the
instance path of it. A failure inside a `oneOf` is reported at the `oneOf`'s own
path, which keeps the contract implementable without reproducing any one library's
error ranking. Each invalid vector has exactly one defect, and, for a `oneOf`, names
the branch it meant so the Python tests can prove it fails for that reason.

**6. Validation is two-stage and dispatched by name.** A small envelope is checked
first, and the payload schema is then found from `type`, `kind` and `status`
(`messages/<type>.<kind>.json`). The alternative, one schema using `allOf` and
`if/then` to pick the payload, would need keywords outside the subset.

**7. The `session.hello` framing is frozen at 1.0** and its payloads never change.
A hello must always be answerable, because it is how an old plugin finds out it is
too old. This is recorded in `docs/protocol/README.md` with the rest of the
version rules (`x-since`, sender gating).

## Consequences

**Easier:**

- The Luau validator is a small, finite job: a dozen keywords, no regular
  expressions, no reference resolution beyond a file lookup.
- Python and Luau cannot disagree about *what the message is*, only about whether
  an implementation is correct — and the vectors say which.
- "Both sides validate" has a definition that can be tested.

**Harder:**

- A bespoke Luau parser is code to write, test and maintain, and its performance
  has not been measured. A parser in Luau can be slow; the 1 MiB cap bounds the
  damage, and a long parse blocks the plugin's main thread.
- Surrogate pairs have to be combined into UTF-8 by hand, and number grammar has to
  be checked before `tonumber`, which is more permissive than JSON.
- The subset is a ceiling: a useful schema feature outside it (`pattern`,
  `allOf`) is unavailable, and enums and bounds cannot be widened inside a major
  version.
- Two parsers (Python and Luau) plus the API's own must be kept in agreement, by
  vectors and nothing else.
- Until the Luau runner exists, the strongest claim available is that the Python
  side passes the vectors and the Luau side is specified.

**Given up:** `HttpService:JSONDecode` for protocol messages, regular-expression
validation of identifiers, and the convenience of a general-purpose JSON Schema
library on the plugin side.

## Alternatives considered

- **A lexical pre-scan for duplicate keys, then `JSONDecode`.** Less code on paper,
  but the scanner must tokenise strings, escapes and structure to know which
  object a key belongs to and what it decodes to — most of a parser — and then
  `JSONDecode` reads the same text a second time and may interpret it differently.
  Two readers of one text is a parser differential, and it still cannot see `null`.
  Rejected.
- **A fork of `rxi/json.lua`.** MIT-licensed and small, but four places need
  patching (duplicates, `null`, number grammar, depth) and there is no depth limit;
  the result is no cheaper than a parser written for the profile and leaves a fork
  to carry. Used as a reference for structure only.
- **Validators generated from the schemas.** Stronger on paper, and it adds a build
  step to the plugin. The subset keeps the validator small enough that generation
  is not needed; it remains an option if the subset grows.
- **Validate only the envelope in the plugin.** Rejected: it abandons ADR-0006's
  rule that both sides validate.
- **An IDL with code generation.** Already rejected by ADR-0006, and still poor on
  Luau.
