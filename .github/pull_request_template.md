## What this changes

<!-- One paragraph. What is different after this PR, and why. -->

## Related issue

<!-- Closes #NNN. Large changes should have had an issue first (CONTRIBUTING.md). -->

## How it was verified

<!-- What you actually ran, and what it said. "Tests pass" without the command
     is not verification. If something is untested, say so here rather than
     leaving a reviewer to find out. -->

## Checklist

- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] `pytest` passes with `LLM_PROVIDER=fake` (no API key needed)
- [ ] Luau changes pass `selene` and `stylua --check`
- [ ] One concern per PR — no mixed refactor-plus-feature
- [ ] Tests added or updated, next to the code they test
- [ ] Docs updated if behaviour changed (`README.md`, `ARCHITECTURE.md`, package README)
- [ ] `CHANGELOG.md` updated under `[Unreleased]`

## Safety invariants

Confirm none of these is weakened by this PR (see
[`ARCHITECTURE.md`](../ARCHITECTURE.md) and [`docs/safety.md`](../docs/safety.md)):

- [ ] `packages/core` still imports no web framework
- [ ] Generated code is still statically validated before it runs
- [ ] Project content is still treated as data, never as instructions
- [ ] No API key, token or credential reaches the Studio plugin or a log
- [ ] Publishing to Roblox remains a human action
- [ ] Iteration and spend caps remain enforced in `packages/core`

If this PR intentionally changes one of them, it needs an ADR that supersedes
the relevant decision. Link it here.

## Architecture decisions

- [ ] This PR does not contradict an accepted ADR, **or** it adds a new ADR
      superseding one. Link: <!-- docs/architecture/adr/NNNN-*.md -->

## AI assistance

- [ ] Parts of this change were model-generated

Fine either way, and expected in this project — but say so, because generated
code tends to fail in different places than hand-written code, and reviewers
read it differently. You remain the author of record.
