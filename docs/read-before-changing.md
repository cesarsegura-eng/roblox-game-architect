# Read before changing the code

> **⚠️ Read the entry for a file before you edit it.**
>
> Some of what looks arbitrary here is load-bearing. Each entry says what the
> code looks like, why it is that way, and what breaks if it changes. If an entry
> does not convince you, change the code — but change it knowing what the entry
> was protecting, and update the entry in the same pull request.

## What this file is, and is not

It is **not** a second ADR index. `docs/architecture/adr/README.md` owns the
architectural decisions and their status. This file owns the smaller kind: an
implementation detail that reads like a preference, is not one, and that a
reasonable person would otherwise "clean up" on a quiet afternoon.

It is also not a changelog. `CHANGELOG.md` says what changed; this says why a
line is shaped the way it is and what it would cost to reshape it.

**Simpler is welcome.** Every entry names the property that must survive, not the
code. If you can keep the property with less code, do it.

## How risky is this file to change?

| Tier | What it means |
|---|---|
| **Critical** | A careless change silently breaks a safety property or the wire contract. Read the entry; expect to need a test and possibly an ADR. |
| **Minor** | A careless change breaks a build or a developer's day, loudly. Read the entry; a test is usually enough. |
| **Optional** | Convenience. Change freely; nothing depends on the exact shape. |

| File | Tier | What it is load-bearing for |
|---|---|---|
| `packages/protocol/schemas/v1/**` | **Critical** | the wire contract. The tag `protocol-v1.0` exists, so a closed `enum` or a bound can no longer be widened inside major 1 |
| `packages/sandbox/parser.py` | **Critical** | the bounded, untrusted-source parser: process limits, version pin, and the rule that Lute's diagnostics never surface |
| `packages/core/roblox_place.py` | **Critical** | what may appear in a generated place, and the untrusted-text boundary on build failures |
| `packages/api/service.py` | **Critical** | the ADR-0011 lifecycle, including three choices the record leaves open and this code had to make |
| `apps/blender_mcp_server/server.py` | **Critical** | artifact validation and publication |
| `apps/blender_mcp_server/Dockerfile` | **Minor** | the only place the Blender archive's integrity is checked |
| `.github/workflows/ci.yml` | **Minor** | the toolchain the jobs actually get |
| `.gitleaks.toml` | **Critical** | whether a real credential in a test file is still reported |
| `tools/dev-env.sh` | **Minor** | a local toolchain that matches the pins |
| `tools/`, `examples/` otherwise | **Optional** | convenience and fixtures |

---

## Entries

Each entry: what it looks like · why · what breaks · how it was established.

### The protocol's closed enums cannot be widened any more

**Critical** — `packages/protocol/schemas/v1/`

`packages/protocol/schemas/v1/error.protocol.json` and the other closed lists look like ordinary enums. They
are frozen inside major version 1, because `docs/protocol/README.md` makes
widening a closed `enum` a major bump and the tag `protocol-v1.0` now exists.

Renaming `unknown_action` to `unknown_work` and adding `result_conflict` was
only admissible because that tag did not exist yet. **The same change today is a
major version.** If a code is missing, the answer is a new major or a different
message, not one more member.

### An `unknown` operation carries no reason, on purpose

**Critical** — `packages/protocol/schemas/v1/messages/edit.result.request.json`

The schema ties `error` to the status `failed`, so an operation whose effect
could not be determined cannot say why. That looks like an oversight. It is
recorded in ADR-0011 section 9 as **[Pending]**: the reason belongs in the event
history, not in the result, and changing it is a schema change before a tag that
already exists. Do not "fix" it by loosening the schema.

### Lute's output never reaches a caller

**Critical** — `packages/sandbox/parser.py`

`analyze` deliberately drops Lute's syntax diagnostics: they quote the source,
and source is untrusted (invariant I3, ADR-0012). The one exception is the
`--version` call, which reads no project source, so its exit code is safe to
report — that is why the unavailability message can name `ROKIT_ROOT` and an
exit code and nothing else.

**If you add a diagnostic**, ask first whether the text can contain a fragment of
the analysed source. If it can, it stays inside the process.

### A failed place build carries the tool's output beside the message

**Critical** — `packages/core/roblox_place.py`, `tools/build_roblox_place.py`

`RobloxPlaceBuildError` takes `tool_output` as a keyword and keeps it **out of**
the message. The MCP server answers with `str(exc)`, so it keeps relaying a fixed
template and never the tool's text; `tools/build_roblox_place.py` prints the
output because a developer at a terminal needs it.

This split is the whole point. Folding the output into the message would leak
recipe-derived names to a protocol client. Two tests in
`packages/core/tests/test_roblox_place.py` pin it, and they are the tests to keep
if you restructure the exception.

**Established by:** a CI failure that reported only `KeyError:
'structuredContent'` across three runs and said nothing about the cause.

### Rojo runs with its working directory in the build's temporary folder

**Critical** — `packages/core/roblox_place.py`

`subprocess.run(..., cwd=root)` is deliberate: the generated project and its
`server/` folder live in that temporary directory, and relative `$path` entries
resolve against it.

The consequence is that **a Rokit shim cannot be used as `rojo` here**. A shim
resolves its tool from a manifest in the working directory, and a temporary
directory has none: it answers `Failed to find tool 'rojo' in any project
manifest file`. The real binary has no such tie. This is why CI puts the pinned
binaries ahead of the shims and why `tools/dev-env.sh` does the same locally.

**Established by:** CI, where `rojo --version` passed at the job root and
`rojo build` failed inside the temporary directory. It does not reproduce on a
machine whose Rokit root has a global `rokit.toml` of its own listing the tools, which is
why it was invisible locally.

### The GLB is copied into the artifact directory, not renamed into it

**Critical** — `apps/blender_mcp_server/server.py`

The obvious code is `temporary_glb.replace(staging_path)`. It raises
`OSError: [Errno 18] Invalid cross-device link` in the container, where the job
directory is a tmpfs and the artifact store is a volume: a rename cannot cross a
filesystem.

It copies into the destination directory and then replaces **within** that
directory, so the publish is still atomic. `shutil.move` would also work and
would give that atomicity away, which is the property worth keeping.

**Established by:** the first CI run that ever started this container. It does
not reproduce locally, where everything is one filesystem.

### The Blender archive keeps its published name

**Minor** — `apps/blender_mcp_server/Dockerfile`

`sha256sum --check` reads each file name from the checksum line, so the download
is saved as `blender-<version>-linux-x64.tar.xz` and the build `cd`s to its
directory. Saving it as `blender.tar.xz` made the check unable to find its input:
the integrity check had never verified anything, which only became visible when
the download itself started failing.

`--status` is left off so the build log carries the `OK` line as evidence that
the hash was checked. Keep that.

The long retry is for a different problem: `download.blender.org` answers 403 to
a runner's address at times and allows it at others. If that keeps failing, the
answer is to stop fetching 400 MB on every run, not more retries.

### gitleaks allowlists values, never paths

**Critical** — `.gitleaks.toml`

The two entries are literal test fixtures, matched by their value. The tempting
simplification — allowlisting `**/tests/**` — would mean a real credential
committed to a test file is never reported. That is the failure mode this file
exists to avoid.

### `rokit install --no-trust-check` in CI

**Minor** — `.github/workflows/ci.yml`

Without it `rokit install` stops to ask whether each tool is trusted, and a
runner has nobody to answer: `The following tool has not been marked as trusted:
JohnnyMorganz/StyLua`. The flag is rokit's own, documented for CI.

### Toolchain-dependent tests skip, they do not fail

**Minor** — `packages/sandbox/tests/`, `packages/protocol/tests/`,
`apps/roblox_mcp_server/tests/test_knowledge.py`

`pytest.mark.skipif(shutil.which(...) is None)` is the house pattern: the plain
Python job has no Luau toolchain, and a dedicated job runs the same tests with
it. A test that fails when a tool is absent turns a documented environment
requirement into eighteen confusing failures.

The guard checks **presence, not runnability**. A broken shim on `PATH` still
satisfies it. That is a known hole; `tools/dev-env.sh` exists so you do not fall
into it.

### Three decisions in `packages/api/service.py` are marked PROVISIONAL

**Critical** — `packages/api/service.py`

ADR-0011 leaves them open, and a service has to do something: how two results
are compared, what the idempotency digest covers, and what is answered when a
`message_id` returns with different content. Each is marked `PROVISIONAL` at the
point where it is made.

**Implementing one did not decide it.** If you change one, you are not fixing a
bug — you are taking a decision the record reserves for the owner.

---

## Adding an entry

Add one when you write something a later reader would reasonably undo. Keep the
four parts: what it looks like, why, what breaks, and how you established it. If
you cannot say how you established it, say that instead of inventing a reason —
"assumed, not verified" is a useful entry too.
