# v4.0 character replacement contract

Inspected VERSION.txt (4.0), character_art.py, character_catalog.py,
client.py draw_player, bicycle_art.py, and current character audits.

| Requested behavior | Current renderer behavior | Required body art |
| --- | --- | --- |
| Idle | Static | idle |
| Walk | 8 pose changes/second: left, idle, right, idle | walk_left, walk_right, idle |
| Run | 10 pose changes/second: left, right | run_left, run_right |
| Jump | Static pose with client lift and 1.35x default scale | jump |
| Double jump | Same art, extra client lift and 1.50x default scale | jump reused |
| Crouch | Static squat | crouch |
| Prone | Static belly-down pose | prone |
| Cycling | Existing bicycle renderer overlays idle/walking character | idle/walk reused |
| Interior occupants and NPCs | Same character renderer | idle/walk reused |
| Direction | Rotate north-facing composite toward heading | No extra direction rows |
| Gun/knife/grenade actions | build_action_surface currently discards action, phase, weapon_id | Equipment review art only; future integration |

The current renderer does not have separate crawl, climb, swim, landing,
death, firing, recoil, grenade-throw, knife-swing or reload animation cycles.
No such cycles are claimed by the replacement pack.

## Existing persistence and art schema

Eight hats, eight head IDs, eight outfit/body IDs. A body is one coordinated
torso/arms/hands/legs/boots selection. Each has eight 160x128 RGBA layer cells.
Hat `none` is supported. Runtime crops alpha and scales the assembled body to
31 pixels tall at scale 1 (minimum display scale still applies in the client).
It uses a 224x224 composition canvas and state-specific head offsets.

The clean master, if present, overrides individual part PNGs. Replacement
compatibility requires both to agree. Expected master is 1280x1280, 8 columns
by 10 rows: hats, heads, idle, walk_left, walk_right, run_left, run_right,
jump, crouch, prone. Reuse existing hats as retained assets.

Alpha art has three unique outfits/heads. Compatibility IDs 01/04/07 map to
tactical, 02/05/08 to street, and 03/06 to utility. These are aliases, not eight
unique newly generated costumes. Head and body can be mixed independently.

The pack will be staged separately from the current live pack for review,
with a preview that calls the existing renderer against the staged assets.
