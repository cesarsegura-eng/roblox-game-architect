# ADR-0004: Generated projects live outside the repository

- **Status:** Accepted
- **Date:** 2026-11-01

## Context

An early `projects/` directory sat at the repository root, apparently intended
to hold the game projects the agent generates. That puts runtime-generated
artefacts inside the versioned source tree.

In most projects that is merely untidy. Here it is worse, for a specific reason:
this system generates code autonomously. If generated output lives in the source
tree, the distinction between "what a human wrote" and "what the model wrote"
disappears from the repository — and that distinction is exactly what you need
in order to audit the system, review a contribution, or investigate an incident.

Secondary costs: generated projects include Roblox place files, which are binary
and multi-megabyte, do not diff, and bloat history permanently.

## Decision

Generated projects are written to a data directory **outside version control**,
configured by `DATA_DIR` in `.env` and defaulting to `./data`. `/data/` is in
`.gitignore`.

The repository keeps `examples/` instead: a small set of hand-curated,
version-controlled example projects that serve as reproducible fixtures for the
agent evaluation suite.

Roblox binaries (`*.rbxl`, `*.rbxlx`, `*.rbxm`, `*.rbxmx`) are gitignored
repository-wide. Plugin source is Luau text managed by Rojo, never a committed
place file.

## Consequences

**Easier:**

- `git log` and `git diff` stay meaningful: everything in history was written by
  a human or reviewed by one.
- Repository size stays small and clone times stay short.
- `examples/` gives the evaluation suite stable inputs, which is what makes
  engine changes reviewable.

**Harder:**

- Generated work is not backed up or versioned by default. A user who wants
  history for a generated game has to arrange it themselves — plausibly a
  per-project git repository inside `DATA_DIR`, which is left undecided.
- The data directory is one more thing to configure, document and handle the
  absence of.
- Anyone sharing a generated project must do it deliberately rather than by
  pushing a commit.

**Given up:** the convenience of generated output showing up in the repository
for free.

## Alternatives considered

- **Keep `projects/` versioned.** Rejected for the auditability reason above,
  plus binary bloat.
- **Version generated projects in a separate repository per game.** Not
  rejected, deferred: it is a reasonable option for the "I want history for my
  generated game" case, but it is a feature decision, not a layout decision,
  and nothing depends on it yet.
- **A database rather than the filesystem.** Deferred. Generated Roblox projects
  are files that Rojo and Studio expect on disk; a database would mean exporting
  to disk anyway. Revisit for hosted multi-user deployment.
