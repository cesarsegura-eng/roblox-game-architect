# Game Plan v2 contract guide

The portable JSON Schema is next to this guide at
`game-plan-v2.schema.json`. The RGA planner API also supplies its trusted copy
with each generation call. This guide explains the gameplay handoff fields for
agents that use the portable skill without the RGA planner API.

## `systems`

Give each system a unique `name`, a concise `purpose`, and an
`implementation_stage` of `blockout` or `later`. `blockout` means it is
represented by the first world build or one of the fixed server templates; it
does not authorize model-authored code. `later` systems are not part of the
current place artifact.

## `playable_slice`

- `gameplay_mode` is exactly one of `blockout`, `obby`, `treasure_hunt`, or
  `rule_game`.
- `gameplay_rules` is an empty array for every mode except `rule_game`. For
  `rule_game`, provide 1-16 rules using only `award_points` (amount 1-1000),
  `heal` (amount 1-100), `damage` (hazard role, amount 1-100), `eliminate`
  (hazard role, no parameters), `speed_boost` (collectible or prop role,
  `amount` 1-16 and `duration_seconds` 1-30), or `award_win` (landmark role,
  `minimum_points` 1-1000). A win threshold requires at least one
  `award_points` rule. A trigger-role/action pair may occur only once. These
  rules contain data only; they cannot contain source text.
- `included_systems` lists each first-slice system name whose stage is
  `blockout`.
- `deferred_systems` lists each system name whose stage is `later`.
- Together, those arrays must partition every system exactly once.
- `limitations` states what the selected build does not include. For fixed
  modes, identify the absence of custom UI, saved progress, or any other feature
  the template does not implement. Optional `hazard` role parts are lethal on
  touch in Obby and Treasure Hunt; do not imply other hazard behaviors.

Use `obby` only for a sequential traversal loop and request at least two
connected `path` segments in `world_brief`. Use `treasure_hunt` only when the
loop is to collect every placed pickup; request 1-100 route-adjacent
`collectible` objects. The build service validates those recipe requirements.
Use `blockout` if the requested loop needs mechanics outside those fixed
templates. `rule_game` passes its bounded `gameplay_rules` array to
`rga_build_place`: touch-triggered `award_points` or `heal` rules on
`collectible`, `hazard`, `prop`, and `landmark` roles; `speed_boost` on
`collectible` or `prop`; nonlethal `damage` or `eliminate` on `hazard`; and
`award_win` on `landmark` after reaching `minimum_points`. Each repeated rule
fires once per player per part until a win resets session points and collection
state for another round. A speed boost adds to the current WalkSpeed, caps it at
32, and restores its saved original value when the latest boost expires. Each
role must exist in the Scene Recipe. This is data interpreted by one fixed
server script, never model-authored Luau. Never call a generated model script a
supported build mode.
