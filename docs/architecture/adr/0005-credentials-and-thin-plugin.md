# ADR-0005: Credentials stay server-side; the plugin is a thin client

- **Status:** Accepted
- **Date:** 2026-11-01

## Context

The Studio plugin is the most privileged component in the system. A Roblox
plugin with HTTP and script permissions can do very nearly anything inside the
user's Studio session, and it is the component the user will scrutinise least —
it is installed once and then forgotten.

It is also the worst possible place to keep a secret. Plugin source is
distributed to the user's machine and is readable; there is no secure storage
and no server-side boundary.

Meanwhile there is a real pull in the other direction: having the plugin call
the LLM provider directly would remove a hop and simplify the first prototype.

## Decision

**The plugin holds no provider credentials, no prompts and no decision logic.**
It is a thin client that:

- reports the state of the open place,
- applies validated, approved edits it is handed,
- runs playtests and reports results.

LLM API keys live only in the API service's environment. The plugin
authenticates to the local API with a scoped token (`PLUGIN_AUTH_TOKEN`), and
that token's privileges are limited to the operations above.

Secrets are redacted from the run log and from any error text that reaches the
UI.

The plugin requests the minimum Studio permissions it needs, and every
destructive action is confirmed in its own UI as well as at the API-side
approval gate — the local confirmation is what the user actually sees at the
moment of change.

## Consequences

**Easier:**

- A leaked or decompiled plugin exposes a scoped local token, not a billable
  provider key.
- Prompt and agent logic changes ship by pulling the repository, with no plugin
  reinstall. Given how slowly plugins update in practice, this matters.
- The component with the most privilege has the least logic, so there is less in
  it to go wrong and less to review.

**Harder:**

- The API service must be running for the plugin to do anything. A user with
  Studio open and no service gets an inert plugin, and that needs clear error
  messaging.
- More moving parts in the local setup than a self-contained plugin would need.
- Every capability the plugin needs has to be expressed in the protocol first,
  which slows plugin development deliberately.

**Given up:** a standalone plugin that works with nothing else installed. That
is a genuine loss for adoption, accepted for the security reason.

## Alternatives considered

- **Plugin calls the LLM provider directly with the user's key.** Rejected: puts
  a billable credential in a readable, unprotectable location, and moves prompt
  logic into the slowest-updating component.
- **Plugin holds the decision logic, API is a thin proxy.** Rejected: maximises
  logic in the most privileged, least reviewed, hardest-to-update component.
- **Encrypt the key inside the plugin.** Rejected: the plugin must decrypt it to
  use it, so this is obfuscation, not protection.
