# World-design evaluation fixtures

These eight reviewed evaluation cases use seven Scene Recipe v3 files as
deterministic responses for the offline `FakeProvider` evaluation mode. They
exercise schema parsing, the normal generation loop, skill selection, and the
structural rubric for environment architecture across rainforest, temperate
forest, alpine settlement, arid courtyard, tidal wetland, tropical stilt
housing, and a generic walk/run/jump blockout. Each fixture also carries a
biome-specific global-lighting, Atmosphere, and cloud profile for the Roblox
place builder. The rainforest collect-and-win case reuses the reviewed gameplay
recipe and checks minimum collectible, hazard, landmark, and connected-path
counts plus their spatial relationships.
The alpine inn uses three touching trail segments, and its rubric checks the
largest connected path group as well as individual path shape.

They are hand-authored test fixtures, not generated model output and not visual
or gameplay references. A fake-provider pass proves only that the fixed
contracts and rubric work. To evaluate model output, select a real configured
provider; the JSON report identifies that run as `provider_generation`.

Run one case or all cases from the repository root:

```powershell
uv run python tools/evaluate_worldbuilding.py --case coastal-wetland
uv run python tools/evaluate_worldbuilding.py
```
