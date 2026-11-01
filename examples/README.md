# examples/

Hand-curated, version-controlled example projects.

**Status: empty.** Examples get added alongside the first vertical slice.

## What belongs here

Small, readable, reproducible Roblox project definitions used as:

- **fixtures for the evaluation suite** — fixed inputs, so a change to a prompt
  or an agent can be shown to improve or regress behaviour,
- **integration-test inputs**,
- **documentation** of what the agent is expected to handle.

## What does not belong here

Projects the agent generated. Those are written to `DATA_DIR` (default `./data`,
gitignored) and never committed
([ADR-0004](../docs/architecture/adr/0004-generated-project-storage.md)). Keeping
generated output out of the source tree is what preserves the distinction
between what a human wrote and what the model wrote — which is exactly what you
need in order to audit the system.

## Rules

- Luau text and JSON only. No `.rbxl`, `.rbxlx`, `.rbxm` or `.rbxmx` — they are
  binary, they do not diff, and `.gitignore` blocks them.
- Small enough to read in one sitting. An example nobody reads is dead weight.
- Each example gets a README saying what it exercises and what good output
  looks like.
