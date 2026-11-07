# Character art and Roblox movement reference

## Asset-type gates

Before modeling, decide whether the deliverable is an environment character/NPC,
a Roblox standard R15 body, an advanced R15 body, an accessory, or a generic
rigged mesh. These are different targets. Roblox avatar bodies have strict part
names, hierarchy, axes, poses, triangle budgets, attachments, and bounds. Check
the current Creator Hub specification rather than applying one target's rules
to every character.

For standard R15 avatar bodies, Creator Hub describes 15 body mesh objects,
required joint hierarchy, positive-Z facing and positive-Y standing orientation,
and I-, A-, or T-pose export guidance. The advanced rig permits additional
named joints for spine, clavicles, fingers, toes, and head. Use official
templates/mannequins where possible. Validate imports through a connected
Roblox-side acceptance workflow; Studio is an optional operator inspection path,
not an end-user computer requirement. If no remote rig validator is available,
report the import and animation checks as unverified.

## Useful pose checks

- neutral standing, crouch, reach overhead, reach forward, arms crossed;
- deep elbow and knee bend, shoulder raise, hip flexion, wrist turn;
- foot plant and toe-off, hand contact, turn, jump/fall/landing if relevant;
- inspect volume, silhouette, intersections, and weight shifts in each pose.

The Blender Armature Modifier supports deformation through vertex groups or bone
envelopes. For production control, carefully weighted vertex groups are usually
more predictable than relying on envelopes alone. Clean unused groups and inspect
all deformations after rig changes.

## Sources

See `docs/art-direction/research-sources.md` for current Blender, Roblox, and
animation/rigging references.
