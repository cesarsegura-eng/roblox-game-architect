---
name: roblox-ui-ux
description: Design, implement, and verify responsive, accessible Roblox interfaces and player-facing flows.
---

# Roblox UI and player experience

Use this skill when a game needs a HUD, menu, onboarding, settings, inventory,
shop, interaction prompt, or other player-facing interface. It complements
`game-design-planning` and `roblox-gameplay-engineering`; it does not replace
them.

## Work through the existing Studio connection

- Discover and use the user's existing native Roblox Studio MCP for direct place
  inspection and edits. Never install a second Studio connection or route these
  edits through the optional RGA Roblox artifact service.
- When the native MCP exposes `skill`, retrieve its relevant UI, input, or device
  simulation guidance. Use `http_get` to confirm current engine APIs and inspect
  the connected tool schemas before using input simulation or editing tools.
- Inspect the current place hierarchy, scripts, UI conventions, and available
  tools before changing it. Preserve unrelated work and make focused edits.
- Keep interface layout and presentation on the client. Keep currency, purchase
  receipts, rewards, inventory ownership, progression, and other state changes
  authoritative on the server. Treat every remote payload as untrusted; validate
  identity, range, current state, rate, and retry behavior on the server.
- Never put secrets or trusted reward logic in a LocalScript. A hidden button,
  disabled control, or client-side check is not authorization.
- Do not claim that a UI was edited, executed, or tested unless Studio tool
  results or observed runtime evidence confirm it.

## Design the flow before building it

1. Map the player journey: first spawn, primary objective, feedback for an
   action, pause/settings, recovery after death or reconnect, and exit/return.
2. Define the smallest useful UI for the playable slice. Tie every panel and
   status to a player question or action. Avoid decorative HUD clutter.
3. List the UI states, transitions, empty/loading/error cases, and the data each
   state displays. Mark which values are server-owned and which are presentation
   only.
4. Establish hierarchy, spacing, type scale, color/contrast, icon use, and input
   hints as a small reusable system before duplicating components.
5. Build with `ScreenGui` for screen UI or `SurfaceGui`/`BillboardGui` for
   world-attached UI. Use layout objects and constraints rather than hard-coded
   pixel positions wherever possible.

## Cross-device and accessibility requirements

- Adapt to viewport size and orientation. Test small phones, tablets, desktop,
  and ultrawide layouts using Studio's Device Emulator; keep important controls
  clear of Roblox's top bar, thumbstick, and safe-area overlays.
- Support mouse/keyboard, touch, and gamepad for every essential action. Prefer
  Roblox's Input Action System for shared actions. Use `UserInputService.PreferredInput`
  to switch concise control hints and input-specific layouts when appropriate.
- Make gamepad focus visible and complete: set predictable selection order,
  ensure a usable focus path through menus, and verify that opening/closing a
  panel restores focus to a meaningful control.
- Use legible text, strong text/background contrast, clear hierarchy, and
  touch targets with enough size and spacing. Do not encode state by color
  alone; pair color with text, shape, or iconography.
- Respect `GuiService.PreferredTextSize` and `GuiService.PreferredTransparency`.
  Avoid `TextScaled` when it prevents the preferred text-size setting from
  working. Prefer automatic sizing and wrapping with sensible layout limits.
- Use localization-ready text. Avoid baking text into images, leave room for
  translation expansion, and set `AutoLocalize` deliberately for names or text
  that should not be translated.
- Avoid flashing and unnecessary motion. Honor reduced-motion preferences for
  optional animation; never make motion the only way to understand a state.
- Do not make sound the only channel for essential information such as a hazard,
  an objective change or a result. Pair it with a visible cue, and give any spoken
  or voiced line readable text, so a player who cannot hear it loses nothing.

## Implementation and review

- Keep UI components and state transitions small. Disconnect event connections,
  cancel delayed work, and remove temporary objects when a panel or character
  lifecycle ends.
- Give buttons visible hover, focus, pressed, disabled, and pending states.
  Prevent duplicate submissions while a request is in flight and show a useful
  failure/retry state without claiming a server action succeeded prematurely.
- Use server acknowledgements as the source for rewards, purchases, and saved
  state. Make retryable requests idempotent. Show optimistic presentation only
  when it can be reconciled safely with the authoritative response.
- Do not fabricate shop products, prices, purchase results, saved settings, or
  player data. Commerce must follow the dedicated production gate and current
  Roblox platform rules.
- Verify the interface in Studio with Device Emulator and Controller Emulator,
  then test the live flow for first-time player, empty/loading/error states,
  respawn, late join where relevant, input switching, and enlarged text.
- Report each device, input method, UI flow, and failure case exercised. Studio
  screenshots or a successful call alone do not prove accessibility, broad
  device coverage, or production readiness.

For current engine APIs and platform guidance, use the official references in
`references/ui-systems.md`.
