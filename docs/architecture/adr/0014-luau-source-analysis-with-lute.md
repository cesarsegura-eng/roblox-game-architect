# ADR-0014: Official Lute parser for Luau source analysis

- **Status:** Proposed
- **Date:** 2026-11-02

The project owner approved using the official Lute parser at an exactly pinned
version. This record remains Proposed until its wording is reviewed.

## Context

Gate 1 in [`docs/safety.md`](../../safety.md) must inspect generated Luau
structurally before any execution. Text matching cannot reliably distinguish
code from comments or strings, and a hand-written partial parser would create a
second, incomplete Luau grammar to secure and maintain.

This is a parser for **Luau source code** used by `packages/sandbox`. It is
separate from the strict JSON parser for protocol messages specified by
[ADR-0009](0009-luau-validation-subset-and-strict-json.md); that decision is not
changed here.

The official Lute documentation exposes a parser that returns a concrete syntax
tree (CST), while warning that the syntax APIs may evolve across major versions.
The project therefore needs an exact tool pin and conformance checks before any
version change.

## Decision

1. `packages/sandbox` will use the official Lute parser API
   `@std/syntax/parser` to parse source and inspect its CST. The repository pins
   the stable Lute release `1.0.0` in `aftman.toml`; it does not follow a nightly
   or floating version. Install the pinned toolchain with `rokit install`.
2. Lute runs only a trusted, version-controlled checker. Generated source is
   supplied to that checker as data to parse; it is never run, compiled to an
   executable, or loaded as a module by Lute. Lute is a parser dependency, not an
   execution sandbox for Roblox code.
3. A missing or mismatched Lute executable, a parser error, or an analyzer error
   fails validation closed. The sandbox implementation bounds source size, CPU
   time, output and memory. Linux uses an address-space limit before `exec`;
   Windows assigns the suspended child to a memory-limited Job Object before
   resuming its primary thread. Unsupported platforms fail closed. The Lute
   process itself does not provide the isolation boundary.
4. Any Lute version change is explicit. Before updating the pin, the sandbox
   conformance corpus must pass against the candidate version, including syntax
   failures and AST/CST cases used by every security rule.
5. This ADR chooses the source parser only. It does not define the API allowlist,
   structural policy, Roblox execution mechanism, or disposable-place lifecycle.
   A syntax-only bridge is implemented, but it is not Gate 1 and cannot authorize
   execution.

## Consequences

**Easier:**

- The analyzer can reason over Luau syntax without maintaining a second grammar.
- A fixed parser version makes changes to syntax handling deliberate and
  reviewable.

**Harder:**

- Contributors and CI need the native Lute executable installed for sandbox
  validation. The exact release must be available for each supported platform.
- The CST API can evolve. The version pin limits surprise changes but does not
  remove the cost of reviewing and testing upgrades.
- Parsing is still exposed to untrusted source. Resource limits and OS-level
  privileges are part of the checker boundary and must be implemented before it
  is treated as a security gate.

**Given up:**

- A dependency-free parser maintained entirely in this repository.
- Following Lute nightlies for new syntax without a reviewed pin update.

## Alternatives considered

- **A hand-written Luau subset parser.** Rejected because it would need to reject
  unsupported valid syntax while correctly handling lexical contexts, nesting,
  comments and strings; an incomplete parser risks missing dangerous constructs.
- **The Luau compiler's internal C++ parser directly.** Rejected for this slice
  because it would require a native integration or a separately maintained
  build, while Lute provides an official packaged parser and CST traversal API.
- **Use Lute only as a syntax checker and do policy checks with text scans.**
  Rejected because security rules need syntax-aware traversal; a successful
  syntax check alone does not enforce an API allowlist or structural policy.
- **Defer parsing until after the agent loop.** Rejected because generated code
  must not execute before Gate 1 exists.

## References

- [Lute syntax parser API](https://lute.luau.org/std/syntax/parser.html)
- [Lute CST visitor API](https://lute.luau.org/std/syntax/visitor/)
- [Lute releases](https://github.com/luau-lang/lute/releases)
