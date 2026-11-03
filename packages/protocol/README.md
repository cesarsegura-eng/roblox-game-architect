# packages/protocol — the contract

Versioned JSON Schema definitions for every message crossing the Python/Luau
boundary. The single source of truth for the backend ↔ plugin contract.

**Status: version 1.0 written, verified locally in Python only.** The schemas, the
vectors and the reference checks exist and their tests pass. The CI workflows have
not run on them. **Nothing in Luau exists:** the plugin-side parser and validator
are specified (ADR-0009) and not written, so Luau conformance is *specified, not
verified*.

The specification is [`docs/protocol/README.md`](../../docs/protocol/README.md).
The reasoning is in
[ADR-0006](../../docs/architecture/adr/0006-protocol-single-source-of-truth.md)
(why a package),
[ADR-0007](../../docs/architecture/adr/0007-plugin-initiated-http-transport.md)
(transport),
[ADR-0008](../../docs/architecture/adr/0008-edit-action-flat-operations.md) (the
shape of edits) and
[ADR-0009](../../docs/architecture/adr/0009-luau-validation-subset-and-strict-json.md)
(how both sides validate).

## In short

- Schemas are authoritative; Python types and Luau tables are derived from or
  validated against them, never the reverse.
- Every message carries a protocol version, negotiated by `session.hello`. An old
  plugin talking to a new API is the normal case, not an edge case.
- Additive changes only within a major version.
- Both sides validate, under one strict JSON profile (no duplicate keys, no
  `null`, no non-finite numbers).
- No transport assumptions in the schemas.
- The `set_property` allowlist is the schema; there is no other list.
- A schema change is its own pull request.

## Layout

```
schemas/v1/       the contract (20 schema files + version.json)
examples/v1/      conformance vectors: valid/, invalid/, parse/, index.json
tests/            what verifies it (Python only)
```

`examples/v1/README.md` states the vector format.

## Running the tests

From the repository root, as CI does:

```
uv sync --locked --extra dev
uv run pytest packages/protocol
```

They need `jsonschema`, which is in the `dev` extra and nowhere else. Nothing in
`tests/` is importable by production code, on purpose.

- `test_schemas.py` — the schemas are valid Draft 2020-12; each stays inside the
  closed subset (and the audit is shown to reject bad schemas); the reference graph
  is sound; every limit is the documented one; the error code lists, the
  allowlist and the script rules are exactly as documented; and every vector gives
  its declared result, with exactly one defect.
- `test_strict_json.py` — the reference strict-JSON parser, including the inputs a
  JSON vector cannot carry (invalid UTF-8, the exact byte limit).
- `test_semantics.py` — the reference check of scope and ordering (ADR-0008), of
  results and of snapshots. It is an executable specification: `packages/sandbox`
  is the single authority and will implement these rules itself.

## Known risks

- **Luau conformance is unverified.** The parser and validator are the plugin
  stage's first task, and the vectors are what they must pass.
- A Luau JSON parser may be slow. The 1 MiB cap bounds it and it has not been
  measured.
- Closed `enum`s and bounds cannot be widened inside a major version, and the
  `session.hello` can never change.
- The comparison against released schemas that `x-since` relies on needs a tag
  (`protocol-v1.0`) that does not exist yet.
- No protocol operation enables a script, but that does not prevent agent-authored
  code from running in a playtest; ADR-0010 (proposed) states what is and is not
  guaranteed. ADR-0010 to ADR-0013 (proposed) describe changes to the schemas,
  vectors and tests that have not been made.
