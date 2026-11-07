---
name: character-modeling-animation
description: Design readable stylized characters, anatomy-aware proportions, deformation-friendly topology, rigs, and movement for Roblox.
---

# Character modeling and movement

Use this skill for humanoid, creature, NPC, or avatar modeling and animation.
Combine it with `blender-scene-authoring` for Blender work. Read
`references/character-art.md` before producing a rig or Roblox avatar asset.

## Modeling and anatomy

- Start from the character's function, personality, movement, camera distance,
  and gameplay role. Choose proportions intentionally; no single body ratio is
  universal or appropriate to every style, age, culture, or creature.
- Establish a clear silhouette and primary masses (head, torso, pelvis, limbs)
  before anatomy detail. Make forms readable from front, side, back, and gameplay
  distance. Keep joints and limb lengths consistent with the intended rig.
- Where realistic anatomy matters, research the relevant body type, age, and
  motion; do not infer an individual from stereotypes. Stylization can simplify
  anatomy, but shoulder, elbow, wrist, hip, knee, and ankle relationships still
  need to support the planned poses.
- Place topology to support deformation: loops around bending joints, sufficient
  edge flow through shoulders and hips, controlled volume at elbows/knees, and
  clean normals. Test deformation instead of judging a neutral pose alone.

## Rigging and motion

- Select the target Roblox rig standard before naming or parenting bones. Use
  Roblox's required hierarchy, axis, pose, and geometry rules for a platform
  avatar; a custom NPC rig can differ if it is not expected to use that system.
- Build a small set of story poses and contact poses first. Check balance, center
  of mass, foot/hand contact, arcs, timing, spacing, and silhouette through the
  full range of movement.
- Skin weights should blend across joints without collapsing or stretching
  unpredictably. Inspect extreme poses, mirrored motion, and transitions.
- Motion should convey weight and intent. Use anticipation, clear action,
  follow-through, and recovery where they improve readability; do not apply them
  mechanically to every motion.
- Design motion as a readable cycle or action with contact, compression, travel,
  and recovery phases. Inspect timing and spacing at gameplay distance, then
  test on the target rig; keyframe easing is part of the motion design, not a
  cleanup-only step.
- Blender's viewport and a successful export cannot establish Roblox
  compatibility. Use a connected Roblox-side acceptance or import workflow for
  the intended rig when one exists; otherwise report the compatibility check as
  unverified and hand the artifact to an authorized service operator for
  optional Studio inspection. Do not require Studio on the end user's PC.
- Choose the deliverable type explicitly: a generic NPC rig, a custom skinned
  character, and an R15 avatar have different hierarchy, pose, geometry, and
  import requirements. Do not label a generic blockout as a valid avatar.
- For avatar or character uploads, use official Avatar Setup and character
  specifications as acceptance references. Successful GLB/FBX export alone
  does not establish avatar readiness. If the connected remote services cannot
  test the imported rig and clips on the intended character type, state that
  limitation and leave inspection in the user's Studio as a handoff step.
- Consult Roblox's [character pipeline](https://create.roblox.com/docs/characters),
  [rigging and skinning guide](https://create.roblox.com/docs/art/modeling/rigging),
  and [character body specifications](https://create.roblox.com/docs/art/modeling/specifications)
  for current platform requirements.

Do not claim anatomy accuracy or production-ready rigging from a primitive
blockout. State what was modeled, what was rigged, and what still needs artist
review.

## Available Blender tool

Use the remote Blender MCP service as the default Blender execution tool. The
agent's skillpacks provide design guidance, while the separate MCP host runs
Blender 5.2.3 and returns a GLB from a validated recipe. Do not require a
Blender installation on the user's computer. The optional RGA Blender
extension can create a stylized humanoid blockout with a
hierarchical skeleton and loop-compatible walk, run, jump, or idle action. Its ellipsoid body
parts are rigidly weighted to bones for readable pose and export checks. This
is a generic NPC rig, not a Roblox R15 avatar or a deformation-ready anatomy
mesh. Adapt proportions, replace the rigid body parts with a continuous mesh,
and retarget to the required Roblox rig before using it as an avatar animation.
The destination experience must enable looping for cycle-based clips.
