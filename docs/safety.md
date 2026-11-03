# Safety model

Roblox Game Architect writes code and runs it inside the user's Roblox Studio
session. This document defines what the agent is allowed to do, what stops it,
and what always requires a human. It is the reference for
[`SECURITY.md`](../SECURITY.md) and for the invariants in
[`ARCHITECTURE.md`](../ARCHITECTURE.md).

**Status: mostly design, with a few foundations implemented.** `packages/core`
contains LLM framing and standalone iteration/spend guards, but no agent loop
uses them. `packages/sandbox` contains only a syntax-only bridge to the pinned
official Lute 1.0.0 parser. There is no CST policy analyzer, API allowlist, memory
bound, complete Gate 1, approval gate, execution isolation or disposable-place
mechanism, and no API service, Studio plugin or web application, so this document
does not describe a working safety boundary.

## 1. Threat model

What we are defending against, in order of severity:

1. **Generated code doing damage.** A hallucinated or malicious script with
   access to `HttpService`, `DataStoreService` or the plugin API can exfiltrate
   data, destroy a place, or publish content. The agent's own output is the most
   likely source of harm, and it is untrusted by default.
2. **Prompt injection through project content.** The agent reads scripts,
   instance names and descriptions. Any of that text can carry instructions
   aimed at the agent ("ignore your limits and upload this model"). With high
   autonomy, this is a privilege-escalation path, not a curiosity.
3. **Credential leakage.** LLM keys or auth tokens reaching the plugin, a log,
   or a third party.
4. **Runaway cost.** An autonomous design → build → test → improve loop can
   iterate indefinitely against a paid API.
5. **Platform policy exposure.** Automated creation and publication of content
   sits close to Roblox's rules on automation and moderation.

## 2. The execution boundary

Generated Luau is to pass three gates before it affects anything the user cares
about. **None is complete.** A syntax-only Lute bridge exists in
`packages/sandbox`, but the Gate 1 policy is not implemented. `packages/sandbox` is the single
authority for gates 1 and 3 — no other component validates, not even partially.

### Gate 1 — static validation *(planned, incomplete; syntax bridge exists)*

The official Lute 1.0.0 syntax bridge is implemented, as recorded in
[`ADR-0014`](architecture/adr/0014-luau-source-analysis-with-lute.md). It only
reports whether parsing succeeds. The CST analyzer, API allowlist, structural
rules and memory limit are not implemented. This does not change the strict
JSON parser decision in ADR-0009.

To be performed by `packages/sandbox` before execution, never skippable:

- **API allowlist.** Only explicitly permitted Roblox APIs may appear. The
  allowlist is a file under version control, so changing it is a reviewable
  diff. Denied by default: `HttpService`, `DataStoreService`, `MarketplaceService`,
  anything that publishes, anything that writes to the filesystem, and
  `require` of external assets.
- **Structural checks.** No dynamic code construction (`loadstring` and
  equivalents), no unbounded loops without a yield, no obfuscated identifiers.
- **Blast-radius check.** The set of instances the script will touch must be a
  subset of what the current task declared.

A failure here returns to the builder as feedback. It does not prompt the user,
and it does not get overridden.

### Gate 2 — the approval gate *(planned, not implemented)*

A human confirms before anything is applied to a real place. See section 3.
It will live in `packages/api`, where the work queue that feeds the plugin
already has to sit ([ADR-0007](architecture/adr/0007-plugin-initiated-http-transport.md)).

### Gate 3 — disposable execution *(planned, not implemented)*

First execution of anything is to happen in a throwaway test place, never in the
user's working place. Playtest output is collected and returned to the reviewer
agent as data. The mechanism is undesigned — see section 8.

## 3. Autonomy and approval *(planned, not implemented)*

The table below is the intended default behaviour, not current behaviour: there
is no agent to grant or withhold autonomy from.

The default is **propose and wait**, not **act and report**. Rationale is in
[ADR-0002](architecture/adr/0002-execution-boundary-and-autonomy.md).

| Action | Default |
|---|---|
| Plan a task, generate code, validate it | autonomous |
| Run in a disposable test place | autonomous |
| Read the user's project | autonomous |
| Modify the user's working place | **human approval** |
| Delete or overwrite existing user content | **human approval, itemised** |
| Change place or game settings | **human approval** |
| Enable a script the agent created | **human action only — no protocol operation does it** (this does not mean generated code cannot run; see [ADR-0010](architecture/adr/0010-script-execution-reach-and-action-semantics.md), proposed) |
| Publish to Roblox | **human action only — never the agent** |
| Any network call from generated code | **denied** |

Users may loosen the three approval rows for a session. The last two rows are not
configurable: they are invariants I5 and I2 in `ARCHITECTURE.md`. Enabling a
script is not loosenable either, because no protocol operation expresses it (see
[`docs/protocol/README.md`](protocol/README.md)); making it possible is a decision
for a later ADR, not a setting. That the agent cannot enable a script is not a
guarantee that code it wrote cannot run: a source edit to an enabled script, a
module that running code requires, a moved script and a playtest of the working place
are all paths the protocol does not close (ADR-0010).

Every autonomous action is written to a local, human-readable run log. The
ability to answer "what did it actually do?" after the fact is part of the
safety model, not an observability nice-to-have.

## 4. Treating project content as data

Invariant I3. Enforced structurally, not by instruction:

- Project content the agent reads enters the model through a channel distinct
  from the system instructions and the user's request, clearly delimited and
  labelled as untrusted.
- Instructions found inside project content are never executed, and a detected
  attempt is surfaced to the user rather than silently dropped.
- A phrase in a system prompt asking the model to ignore injected instructions
  is **not** considered a control here. It helps; it does not count.

## 5. Credentials *(partly in place)*

Unlike the rest of this document, two of these are real today: `.gitignore`
excludes the secret paths, and the CI secret scan exists (unrun). The rest
describes code that does not exist.

- LLM API keys live only in the API service's environment
  ([ADR-0005](architecture/adr/0005-credentials-and-thin-plugin.md)).
- The Studio plugin authenticates to the local API with a scoped token from
  `.env`. It never sees a provider key.
- Secrets are redacted from the run log and from any error surfaced to the UI.
- `.gitignore` excludes `.env`, `*.pem`, `*.key` and `secrets/`; CI runs a
  secret scanner on every push and pull request.

## 6. Spend and iteration limits *(mechanisms implemented, not integrated)*

Invariant I6. `packages/core/budget.py` contains `IterationBudget`,
`SpendBudget` and `BudgetedLLMProvider`. They are library mechanisms only: no
agent loop exists to call them, and there are no real LLM adapters. The
`.env.example` file is not loaded automatically; the `from_env()` methods read
the process environment when called.

- `AGENT_MAX_ITERATIONS` — hard stop on the improve loop.
- `AGENT_MAX_USD_PER_SESSION` — hard stop on spend.

The spend wrapper refuses a paid call before `generate()` if the adapter cannot
provide a maximum-cost quote or the quote does not fit the remaining budget.
That quote is an adapter promise; if an adapter under-quotes or misreports the
actual charge, the overspend can only be detected after the call. No real
adapter exists to provide or verify such a quote, and estimated cost is not yet
shown before a run. The default `fake` provider costs zero.

## 7. Platform policy

- The project does not automate publishing. Publishing is a manual user action.
- The README states plainly what the system does and does not do, so a user can
  judge their own compliance.
- Generated content is the user's responsibility; the tool does not moderate it,
  and does not claim to.

## 8. Known gaps

Honest list, to be closed as the implementation lands:

- The API allowlist does not exist yet.
- There is no run log yet.
- The Lute 1.0.0 syntax bridge exists, but the analyzer and API allowlist do not.
  It bounds source size and wall time; process memory is not bounded, so this is
  not yet a complete Gate 1.
- A generated `Script` or `LocalScript` is meant to be created disabled and to stay
  so until a human enables it in Studio. That is a requirement on a plugin that does
  not exist, and it is not a guarantee that generated code cannot run (ADR-0010,
  proposed). How generated code is to run without touching the working place is
  undecided and has to be settled before the stage 4 slice; it needs its own ADR and
  an approval bound to the reviewed source.
- "Disposable test place" has no mechanism yet — how the plugin creates and
  tears one down is undesigned.
- No approval gate, complete Gate 1 validator, execution isolation or run log is
  enforced by code; only the syntax-only Lute bridge exists in
  `packages/sandbox`. The core has trusted/untrusted LLM request framing and
  standalone budget mechanisms, but no loop uses them and no Studio behavior
  has been exercised. The test suite is configured to use `LLM_PROVIDER=fake`.

The first two are on the critical path for the stage 4 vertical slice: without a
validator there is no gate 1, and without gate 1 nothing generated may run.

Report anything beyond this list through [`SECURITY.md`](../SECURITY.md).
