# ADR-0007: Plugin-initiated HTTP, with long-polling for results

- **Status:** Accepted
- **Date:** 2026-11-01
- **Amends:** ADR-0006 (the transport example in its rule 5)

## Context

ADR-0006 left the transport open and described the choice as "long-poll vs
WebSocket". `ARCHITECTURE.md` and `docs/protocol/README.md` repeated it, and the
protocol document went further, assessing WebSocket as "better for streaming a
long run".

That choice does not exist. Luau in Roblox exposes no WebSocket client, in game
code or in a plugin, and a Studio plugin cannot listen for inbound connections:
it has outbound HTTP and nothing else. Leaving the question open invited a
contributor to design against a transport that cannot be built.

It is worth being precise about what ADR-0006 got right and wrong. Its rule — the
schemas make no transport assumptions — is correct and stands. Only the
parenthetical example was wrong.

## Decision

**All traffic is HTTP, always initiated by the plugin.** The API service never
calls the plugin.

- **Plugin → API** is a direct request: place state, edit results, playtest
  reports.
- **API → plugin** is a response to a plugin request. Work the agent wants
  applied waits in a queue on the API side until the plugin asks for it.
- **Long-polling** is how the plugin waits: it issues a request that the API
  holds open until there is work or a timeout elapses, then reissues it. This
  keeps latency low without the plugin busy-polling.

The protocol schemas stay transport-agnostic, as ADR-0006 rule 5 requires. This
decision constrains the channel, not the message shapes.

Timeout and retry values are implementation detail and are deliberately not
fixed here; they belong with the first working client.

## Consequences

**Easier:**

- The design matches what the platform actually offers, so the first plugin
  implementation has no dead end waiting for it.
- A queue on the API side is a natural place to hold work pending the human
  approval gate of ADR-0002 — approval and delivery become the same mechanism
  rather than two.
- Plugin-initiated-only means the API needs no inbound reachability to the
  user's machine, which keeps the local setup simple.

**Harder:**

- Long-polling ties up a connection and a server-side handler per connected
  plugin. Fine for a local single-user service; it is a known limit if hosting
  ever becomes multi-user.
- Streaming a long run to the plugin is clumsier than it would be over a
  persistent socket. The web application does not have this restriction, so
  rich streaming belongs there, and the plugin receives discrete units of work.
- Request timeouts become part of the protocol's behaviour, so the plugin needs
  to tell "no work yet" apart from "the service is gone".

**Given up:** server-push to the plugin, which was never available.

## Alternatives considered

- **WebSocket.** Not available in Luau. This is the error being corrected.
- **Short polling on a fixed interval.** Simpler, and a reasonable fallback if
  long-polling proves awkward through Studio's HTTP layer, at the cost of
  latency or wasted requests. Long-polling first, this in reserve.
- **A local file as the channel.** Rejected: a plugin's filesystem access is
  restricted and would need user permission for an operation the plugin should
  not need at all.
