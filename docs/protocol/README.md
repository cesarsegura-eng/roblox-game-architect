# The backend ↔ plugin contract

`packages/protocol` owns every message that crosses the Python/Luau boundary.
This document states the rules that package follows. The schemas themselves are
not written yet — this is the agreement they will be written against.

Rationale: [ADR-0006](../architecture/adr/0006-protocol-single-source-of-truth.md).

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
   the API. Version negotiation happens on connect and is explicit.
3. **Additive changes only within a major version.** New optional fields are
   fine. Removing a field, renaming one, or narrowing a type is a major bump.
4. **Both sides validate.** The API validates what the plugin sends; the plugin
   validates what the API sends. A malformed message is rejected and logged, not
   coerced.
5. **No transport assumptions in the schema.** The channel is plugin-initiated
   HTTP with long-polling ([ADR-0007](../architecture/adr/0007-plugin-initiated-http-transport.md)),
   but the message shapes must not depend on that, so a later move to short
   polling changes nothing here.
6. **A schema change is a reviewable diff of its own.** Protocol changes do not
   ride along inside feature PRs.

## Message families

The contract is expected to cover these, named here so the boundary is visible
before it is built:

| Family | Direction | Purpose |
|---|---|---|
| `session` | plugin → API | handshake, protocol version negotiation, auth |
| `work.poll` | plugin → API | the long-poll that collects queued work |
| `project.state` | plugin → API | what currently exists in the open place |
| `edit.action` | API → plugin | one validated, approved change to apply |
| `edit.result` | plugin → API | what actually happened, including failures |
| `playtest.request` | API → plugin | run a test, with what to collect |
| `playtest.report` | plugin → API | output, errors, timings, observations |
| `approval.request` | API → web | what the agent wants to do and why |
| `run.log` | API → web | the audit trail described in `docs/safety.md` |

## Layout

```
packages/protocol/
├── README.md
└── schemas/
    └── v1/            not created yet — stage 2 on the roadmap
```

## Open questions

- Whether `edit.action` is a flat list of primitive operations or a tree
  mirroring the instance hierarchy. This affects how precisely the blast-radius
  check in `docs/safety.md` can be expressed, so it is a safety-relevant
  decision, not only an ergonomic one. **Settle this before writing v1.**
- How the Luau side validates incoming messages: generated validators, or a
  hand-written subset. Recorded as the known risk in ADR-0006.

Transport is no longer open. It is plugin-initiated HTTP with long-polling
(ADR-0007). Because every exchange begins with a plugin request, `session` is
the plugin asking to connect, and work the agent wants applied waits in a queue
on the API side until the plugin's long-poll picks it up — which is also where
the human approval gate of ADR-0002 naturally sits.
