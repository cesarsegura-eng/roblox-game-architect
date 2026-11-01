# Security Policy

## Why this file matters more than usual here

Roblox Game Architect generates code and executes it. That makes a class of bugs
in this project a security issue rather than a defect: a validation gap in the
codegen path, a prompt injection that escalates the agent's reach, or a leak of
an LLM key through the Studio plugin.

Please read this before filing a public issue.

## Reporting a vulnerability

**Do not open a public issue.** Use GitHub's private reporting:

> Repository -> **Security** -> **Report a vulnerability**

If that menu is not there, private vulnerability reporting has not been enabled
on the repository — please open a public issue saying only *"I have a security
report, how should I send it?"*, with no details, and a maintainer will reply
with a contact address.

**Maintainer note:** enable Settings -> Code security -> Private vulnerability
reporting. Until that is done, the link above 404s and this policy has no
working channel. A dedicated contact alias should replace the fallback above.

Please include: what you did, what happened, what you expected, and the smallest
reproduction you have. A proof of concept against your own test place is ideal.

## In scope

- Generated Luau escaping the validation or execution boundary. That boundary is
  `packages/sandbox` and only `packages/sandbox`; if you find a path where
  `packages/core` or the plugin decides on its own that code is safe to run,
  that is itself the finding.
- Prompt injection through project content — script text, instance names,
  descriptions — that changes the agent's behaviour or privileges.
- Any path that sends an LLM API key, auth token or user credential to the
  Studio plugin, to a log, or to a third party.
- Privilege problems in the Studio plugin: acting without the approval the
  safety model requires.
- Bypassing the iteration or spend limits.
- Dependency or supply-chain issues in what this repository ships.

## Out of scope

- Vulnerabilities in Roblox Studio or the Roblox platform. Report those to Roblox.
- Vulnerabilities in third-party LLM providers. Report those to the provider.
- Findings that require the user to deliberately disable the safety model
  described in [`docs/safety.md`](docs/safety.md).
- Missing hardening in code that does not exist yet. The project is pre-alpha;
  an unimplemented package is not a vulnerability.

## Response

This is a volunteer-maintained project, so no commercial SLA is offered. The
intent is to acknowledge a report within 7 days and agree a disclosure timeline
with you from there. Credit is given unless you prefer otherwise.

## Supported versions

Pre-alpha: only `main` is supported. There are no released versions yet.
