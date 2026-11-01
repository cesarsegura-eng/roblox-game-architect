# packages/sandbox — the execution boundary

Static validation of generated Luau, and controlled execution in a disposable
place. This is the security boundary of the whole system.

**Status: not implemented.** The full design, including the gaps, is in
[`docs/safety.md`](../../docs/safety.md).

## Why this is a package and not a module

A boundary nobody can point at is a boundary nobody reviews. Giving it a name in
the file tree makes it a thing a contributor can find, audit and reason about
([ADR-0002](../../docs/architecture/adr/0002-execution-boundary-and-autonomy.md)).

## This package is the only validator

No other component decides whether generated code may run. `packages/core`
produces code and asks here for a verdict; it implements no checks of its own.
A boundary with two owners has none.

## Gate 1 — static validation *(planned, not implemented)*

Will run before any execution. Not skippable, not overridable by the user.

- **API allowlist**, kept as a version-controlled file so changing it is a
  reviewable diff. Denied by default: `HttpService`, `DataStoreService`,
  `MarketplaceService`, anything that publishes, anything that writes to the
  filesystem, and `require` of external assets.
- **Structural checks**: no dynamic code construction (`loadstring` and
  equivalents), no unbounded loops without a yield, no obfuscated identifiers.
- **Blast-radius check**: the instances the script will touch must be a subset
  of what the task declared.

A failure returns to the builder as feedback. It never prompts the user for an
override — the user is not well placed to judge generated Luau, and a warning
that can be clicked through is not a control.

## Gate 3 — disposable execution *(planned, not implemented)*

First execution of anything is to happen in a throwaway test place, never the
user's working place. Playtest output is collected and handed back to the reviewer
agent as data.

(Gate 2, human approval, lives in `packages/api`.)

## Known gaps

Carried here from `docs/safety.md` so they are visible at the boundary itself:

- The API allowlist does not exist yet.
- Luau static validation has no implementation; the parser choice is open.
- "Disposable test place" has no mechanism — how the plugin creates and tears
  one down is undesigned.
