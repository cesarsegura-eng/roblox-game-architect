# Optional local Blender scene authoring extension

This extension is not required for the normal remote MCP workflow. The remote
service runs Blender 5.2.3 on its own server and returns reviewed GLB artifacts;
see [`docs/integrations/blender-remote-mcp.md`](../../docs/integrations/blender-remote-mcp.md).
Install Blender locally only if you want to author or import recipes directly
on your own machine.

This is a Blender extension for importing validated scene recipes from
`packages/core/worldbuilding.py` and exporting reviewed selections as GLB files
for Roblox Studio.

## Current workflow

1. Install Blender 4.2 or newer and configure the operator environment for
   `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, and the supported
   `LLM_MODEL_ID` (`claude-sonnet-5-5`). Keep the key out of Blender.
2. For direct generation from Blender, start `python -m api.cli serve` from the
   repository root after setting `PLUGIN_AUTH_TOKEN` and `BLENDER_AUTH_TOKEN`
   to separate, long random secrets.
   Keep `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, `LLM_MODEL_ID`, and the
   spend cap in the API process environment. The server binds to loopback on
   `API_PORT` (default `8787`).
3. In Blender 5.2, open **Preferences → Get Extensions → Install from Disk** and
   select the extension ZIP. Build it from the repository root with
   `uv run python tools/package_blender_extension.py` (or pass a different
   `.zip` output path). The current package version is 0.4.0.
4. Enable the extension. In its preferences, enter the matching Blender
   service token and API port. Open the 3D View sidebar and select the **RGA** tab.
5. Choose **Generate World in Blender**, enter a brief, and review the generated
   collection. This calls only the authenticated local API and imports a
   validated recipe; it never receives the provider key. You can also choose
   **Import Scene Recipe** to import a saved v1/v2 JSON file.
6. To create a character blockout, choose a Walk, Run, Jump, or Idle rig
   blockout in the RGA panel. Inspect the action in Blender's
   timeline, select the character objects and rig, then export them as GLB.
7. Choose **Export Selection as GLB**, then review and import the file through
   Roblox Studio's Importer. The exporter includes skinning and animation data.

Recipe files contain data only. The extension accepts v1 primitive recipes and
v2 recipes with allowlisted primitives or bounded low-poly vertices/faces,
transforms, simple materials, basic lights, and up to eight generic rigged
character blockouts with WALK, RUN, JUMP, or IDLE actions. It never executes generated
Python or contacts external hosts. The optional generation button sends only a
brief and the local service token to `127.0.0.1`; it never receives the provider
key. The add-on validates the whole recipe before modifying the Blender scene.
Exports refuse to overwrite an existing file and never upload or publish assets.

The character generator builds a generic NPC skeleton and rigidly weighted
stylized parts, with loop-compatible idle, walk, run, and jump action presets. The jump cycle
animates root-bone height through takeoff, airborne pose, and landing. It is a blockout for
proportion, motion, and export iteration; it is not a Roblox R15 avatar rig or a
production deformation mesh. Roblox Studio's Importer supports glTF rigging,
skinning, and animation data. To publish an animation for standard avatars,
retarget it to an R15 rig and follow Studio's Animation Editor workflow.

The current authoring contract is
[`packages/core/schemas/scene-recipe-v3.schema.json`](../../packages/core/schemas/scene-recipe-v3.schema.json).
The add-on still accepts the older v1 and v2 geometry recipes. V3 adds validated
Roblox global-environment settings; these are consumed by the Roblox place
builder and are not encoded in GLB exports.
The core parser and Blender's dependency-free validator mirror that contract;
update both validators and the schema together when the recipe version changes.

## Verify the installed Blender integration

Run the Blender-side smoke check with a real Blender executable. It imports the
recipe into a separate generated collection, creates the walk rig, exports a
GLB, and inspects the GLB container for mesh, skin, and animation data:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" `
  --background --factory-startup --python tools/smoke_blender_extension.py -- `
  --recipe examples/worlds/mistral-coast-lookout-v2/scene-recipe.json `
  --output dist/rga-smoke.glb
```

The output path must be new; the add-on and smoke script refuse to overwrite an
existing GLB. CI is configured to run this smoke check with Blender 5.2.3 from
the same pinned image used by the remote MCP worker. The manifest declares
Blender 4.2 as its minimum, but other releases still need their own runtime
checks. The 0.4.0 extension and smoke recipe passed locally on Blender 5.2.0;
the pinned 5.2.3 container CI job has not yet run green on this checkout.

## Integration boundary

The core exposes `WorldDesignAgent` and three project skill packs. Character
entries are data-only (`name`, `motion`, `location`, `scale`) and use fixed
trusted geometry and animation presets; they do not carry Blender code. The operator
CLI can call Anthropic under the per-session spend cap; `fake` remains the
offline default. The Blender extension imports the resulting local JSON recipe.
The Blender extension can call the authenticated loopback API route directly or
import a saved local recipe file.

Roblox import settings and mesh rules change over time. Follow the current
[Blender/Studio guide](https://create.roblox.com/docs/art/blender),
[Importer guide](https://create.roblox.com/docs/studio/importer), and
[mesh specifications](https://create.roblox.com/docs/art/modeling/specifications).
