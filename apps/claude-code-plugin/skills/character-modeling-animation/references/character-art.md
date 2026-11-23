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
templates/mannequins where possible. Validate imports through the user's
existing native Studio MCP when its tools support the checks, or through a
Roblox-side acceptance service already available to the agent. Do not require a
new Roblox MCP connection or local RGA plugin. If no suitable import validator
is available, report the import and animation checks as unverified.

## Useful pose checks

- neutral standing, crouch, reach overhead, reach forward, arms crossed;
- deep elbow and knee bend, shoulder raise, hip flexion, wrist turn;
- foot plant and toe-off, hand contact, turn, jump/fall/landing if relevant;
- inspect volume, silhouette, intersections, and weight shifts in each pose.

## Stylized anatomy and deformation workflow

Treat anatomy as a support for silhouette, pose readability, and the intended
art direction. Agree on a target body scale and reference sheet before adding
surface detail. Block the head, ribcage, pelvis, and major limb masses first;
check front, side, and three-quarter silhouettes at gameplay camera distance.
Use deliberate proportion changes consistently (for example, a larger head or
hands) instead of mixing realistic and exaggerated scales accidentally. Keep
joint locations plausible enough for the chosen action: shoulder, elbow, wrist,
hip, knee, and ankle should not be hidden inside rigid costume masses.

After the blockout, establish edge flow around shoulders, elbows, hips, and
knees so the mesh can bend without collapsing. Test weight paint with extreme
but relevant poses before detailing: raise and cross the arms, bend elbows and
knees, flex the hips, twist the torso, and reach overhead. Inspect the inside
and outside of each bend for pinching, gaps, volume loss, and intersections.
Separate hard-surface accessories from deforming body areas where practical;
attach them to the appropriate rigid joint instead of painting broad blended
weights across a moving seam.

## Motion planning

Define the action and contact points before keyframing. For a walk or run, block
the contact, passing, opposite contact, and opposite passing poses, then check
foot placement, leg compression, pelvis travel, torso counter-rotation, and
opposing arm swing. For a jump, include anticipation, takeoff, airborne shape,
landing compression, and recovery. For interaction, identify the planted foot,
reach target, and hand contact so the character does not visibly slide through
the action. Refine timing and easing only after the poses read clearly in
silhouette. Review the loop seam, motion at normal gameplay speed, and motion
with the expected camera and control response.

These are animation blocking checks, not a claim that the current Scene Recipe
exports production rigs or custom motion curves. Its named generic character
actions are fixed blockouts. A production character needs a dedicated remote
authoring/validation path and a Roblox-side import test before it is called
ready.

The Blender Armature Modifier supports deformation through vertex groups or bone
envelopes. For production control, carefully weighted vertex groups are usually
more predictable than relying on envelopes alone. Clean unused groups and inspect
all deformations after rig changes.

## Sources

See `references/research-sources.md` for current Blender, Roblox, and
animation/rigging references.
