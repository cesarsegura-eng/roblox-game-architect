# Roblox UI, input, and accessibility references

Use these official Creator Hub pages as the source of truth for APIs and current
platform behavior. Recheck them when implementing engine features because APIs
and platform requirements can change.

- [User interface](https://create.roblox.com/docs/building-and-visuals/ui):
  screen and in-world GUI types, object hierarchy, layout structures, size and
  appearance modifiers.
- [Implement designs in Studio](https://create.roblox.com/docs/tutorials/curriculums/user-interface-design/implement-designs-in-studio):
  `StarterGui`, Device Emulator, Controller Emulator, and screen/aspect-ratio
  review.
- [Adaptive design guidelines](https://create.roblox.com/docs/production/publishing/adaptive-design):
  responsive sizing, input fluidity, focusable controls, safe areas, and player
  preferences.
- [Input](https://create.roblox.com/docs/input): cross-platform actions and
  `UserInputService.PreferredInput` behavior.
- [Accessibility guidelines](https://create.roblox.com/docs/production/publishing/accessibility):
  text size, contrast, `GuiService.PreferredTextSize`,
  `GuiService.PreferredTransparency`, and reduced motion.
- [Localization](https://create.roblox.com/docs/production/localization):
  source languages, automatic and manual translations, localization settings,
  and `AutoLocalize`.
- [Security and cheat mitigation](https://create.roblox.com/docs/scripting/security/security-tactics):
  server authority and validation for UI-triggered remote requests.

## Review matrix

| Area | Evidence to collect |
|---|---|
| Layout | Small phone portrait, phone landscape, tablet, desktop, and ultrawide screenshots or observations |
| Inputs | Touch, keyboard/mouse, and gamepad operation for every essential flow |
| Focus | Visible initial selection, full navigation path, close/back behavior, and restored focus |
| Legibility | Normal and enlarged preferred text size, contrast, transparency preference, and localization expansion |
| States | First join, loading, success, failure/retry, empty inventory, respawn, and late join as applicable |
| Authority | Server rejects forged, repeated, out-of-range, stale, or unauthorized UI requests |

The matrix is a checklist, not a certification. Record untested devices and
flows as unknown; do not infer that coverage from a desktop Play Solo session.
