# Conformance vectors

Every implementation of the protocol — the Python reference in `../../tests/`, the
future API parser, the future Luau parser and validator — must give each vector the
result it declares. **Only the Python reference has been run against them.**

`index.json` lists every vector by group, so a runtime that cannot list a directory
can still load them all.

| Group | What it tests |
|---|---|
| `valid/` | a message that must be accepted |
| `invalid/` | a message that must be rejected by schema validation, with **exactly one defect** |
| `parse/` | the strict JSON profile alone (`docs/protocol/README.md`); nothing past parsing is checked |

## A vector

```json
{
  "description": "why this vector exists",
  "message": { },
  "generate": [ ],
  "expect": { }
}
```

- `message` is the message as a JSON value; or
- `message_raw` is the message as **text**, for inputs that are not representable as
  a value (a duplicate key, `NaN`, a lone surrogate). A vector has one of the two.
  The file is pure ASCII, so any runtime can read it.
- `generate` (optional, with `message`) expands a large message from a small file.
  Apply the steps in order; `at` is a JSON Pointer to an existing location:
  - `{"at": p, "repeat": item, "count": n}` sets that location to an array of `n`
    copies of `item`;
  - `{"at": p, "fill": s, "length": n}` sets it to `s` repeated `n` times.
  Then serialise the result compactly and treat that text as the message.

## What `expect` says

Valid: `{"valid": true}`. Parse: `{"valid": true, "stage": "parse"}`, or `{"valid":
false, "stage": "parse", "reason": r}`.

Invalid:

| Field | Meaning | Part of the contract? |
|---|---|---|
| `stage` | `dispatch`, `envelope` or `payload` | **yes** |
| `path` | JSON Pointer to the instance that fails; `""` is the message itself, payload paths start `/payload` | **yes** |
| `keyword` | the JSON Schema keyword that failed | no, Python only |
| `inner` | for a `oneOf`: the branch the author meant and the error inside it | no, Python only |

The stages are the ones in `docs/protocol/README.md`: parse, dispatch, envelope,
payload. A failure **inside a `oneOf`** is reported at the `oneOf`'s own path — for
a work item `/payload/work`, for an operation that operation — and its `keyword` is
`oneOf`. `inner` then says which branch was meant (`schema`, `instance`, `path`,
`keyword`), or `unknown_discriminator` when no branch claims the value; the Python
tests check that the message really fails for that reason. A `parse` failure's
`reason` is informational: the contract is the stage.

A message that fails one stage is not checked by the next, so each invalid vector
has one defect and cannot pass or fail by accident.

## Limits that need a generated vector

The vectors at a limit and one past it are the `boundary-*` vectors in `valid/` and
their `*-101`, `*-2001`, `*-100001` and similar partners in `invalid/`. The
message-size limit is `parse/oversize-message.json`. Not stored, because a JSON
file cannot carry them: invalid UTF-8 bytes, and a message of exactly 1,048,576
bytes. The Python tests cover those directly; any other implementation has to
cover them in its own tests.
