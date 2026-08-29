# Open Night Map Workbench

`MAP_WORKBENCH.bat` opens the current map without starting the game client,
server, networking, NPCs, or gameplay simulation.

## What works now

- Real `city_block` Ground and Roof rendering from the current GridWorld data.
- The approved v4 Fort Lee / Hudson / Manhattan layout plan.
- Pan, zoom, fit-to-map, hover coordinates, tile IDs, and collision inspection.
- Optional cell grid, collision colors, object bounds, and street labels.
- Four-frame animated static outside the authored world boundary.
- Hot reload when map CSV/JSON, renderer code, or `city_block` PNG files change.
- Manual Ground/Roof regeneration with `Ctrl+R`.
- PNG screenshots with `P`, saved under `artifacts/map_workbench/`.

Run it by double-clicking `MAP_WORKBENCH.bat`.

## Controls

| Key | Action |
| --- | --- |
| `1` / `2` | City Block runtime / v4 layout |
| `G` / `R` | Ground / Roof |
| Mouse wheel | Zoom |
| Drag or `WASD` | Pan |
| `F` | Fit the full map |
| `I` | Cell/grid overlay |
| `C` | Collision overlay |
| `O` | Object bounds |
| `L` | Labels |
| `N` | Animated static frontier |
| `F5` | Reload files |
| `H` | Toggle automatic reload |
| `Ctrl+R` | Regenerate Ground and Roof from `city_block` |
| `P` | Save screenshot |

## Editor expansion design

The next phase should store the map as deterministic chunks rather than resize
one giant tile matrix in place. Each saved map owns a generation seed, an active
chunk rectangle, generation-rule version, and a list of manually locked chunks.

Player capacity maps to an approved active-area target. Expansion is an explicit
server-authorized operation: select frontier chunks, generate roads/parcels and
`city_block` buildings from the saved seed, run connectivity/collision checks,
then commit the new chunk set atomically. Existing authored chunks never change
unless an editor deliberately unlocks them.

Clients receive only the active/revealed chunk manifest. Anything beyond that
manifest renders the same short static loop already previewed by the workbench.
This makes the boundary visually intentional while preventing clients from
seeing incomplete generation or disagreeing about newly generated terrain.
