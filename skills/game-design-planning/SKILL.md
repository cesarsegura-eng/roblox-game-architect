---
name: game-design-planning
description: Turn a Roblox game brief into a scoped, testable plan that can feed safe world and Studio blockout workflows.
---

# Game design planning

Use this skill to turn a broad game idea into a small, reviewable plan. Clarify
the player promise, audience, core loop, map needs, feature dependencies, and a
first playable milestone. Prefer one coherent experience over a long feature
wish list.
Follow the `game-plan-v2` reference for the exact included/deferred system
partition and supported fixed or data-rule build modes.

## Planning method

- Describe what a player does, why they repeat it, what changes over time, and
  what makes one session satisfying. Keep the core loop to observable actions.
- Define systems by purpose and dependency. Separate features that can be
  represented as a script-free world blockout from features that require later
  gameplay code, assets, moderation, persistence, or platform services.
- Design the first map around the loop: spawn, orientation, route, objective,
  recovery, and return. Use the `world-environments` and
  `roblox-studio-map-blockouts` skills for spatial and Studio constraints.
- Organize milestones so a small playable slice comes before content volume,
  economy depth, live operations, or polish. Each milestone needs an observable
  completion condition.
- In Game Plan v2, choose `playable_slice.gameplay_mode` only from the available
  supported modes: `blockout`, `obby`, `treasure_hunt`, or `rule_game`. Map each system exactly
  once to `included_systems` or `deferred_systems`, consistent with its
  implementation stage. State template limits plainly; do not describe a
  blockout as a playable game or promise custom generated gameplay.
- Include `playable_slice.gameplay_rules`: an empty array unless the mode is
  `rule_game`; for that mode, return only the bounded actions and numeric fields
  listed in the `game-plan-v2` reference. Tie each rule to a world role the
  Scene Recipe can create, and never put Luau or free-form parameters there.
- State how the plan can be checked: route readability, objective completion,
  retry behavior, device performance, and accessibility should be concrete.
- Keep estimates qualitative unless the brief provides team, schedule, budget,
  and production assumptions. Do not invent a promise of delivery time.

## Tool and safety boundaries

- Return only the requested JSON plan. Do not include Luau, Python, commands,
  uploaded assets, publishing steps, or instructions to bypass review.
- Planning does not create a place, change Studio, run code, or guarantee that a
  proposed system is implemented. Label code-dependent work as `later`.
- The `world_brief` is a handoff to the validated Scene Recipe generator. It
  should describe geography, route, landmarks, architecture, and playable
  interior/exterior transitions without asking for scripts.
- If the selected slice is `obby`, the world brief must request at least two
  ordered traversal segments. If it is `treasure_hunt`, it must place
  collectibles along a connected route. The place builder validates those
  required recipe roles before emitting the trusted template.
- Do not promise features that need network services, persistent data,
  moderation, payments, or external assets as part of the current blockout.
