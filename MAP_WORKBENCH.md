# Open Night Map Workbench

`MAP_WORKBENCH.bat` opens the current map without starting the game client,
server, networking, NPCs, or gameplay simulation.

## What works now

- `Y` shows population debug markers. Hover a visible marker to see its entity
  ID, kind, role, floor, and coordinates in **Under cursor**.
- `1` / `2` show the new first- and second-floor shells. Their playable masks
  match the rooftop footprints exactly. In the game, entrance/stair triggers
  connect Ground → 1st Floor → 2nd Floor → Roof and back.
- `U` shows a connected pipe network between manholes, including junctions and
  paired climb-down/climb-up triggers. It is independent of the street layout.
- Rooftops retain a clear view of the streets and river outside the building.
- The GWB approaches remain open through the shoreline curb; larger towers,
  trusses along both sides, and continuous physical deck barriers frame the bridge.
- The two overlapping Manhattan avenues are removed and Broadway is cardinal.
  Shore piers meet the shoreline consistently and leave the bridge approaches clear.

- The current Fort Lee / Hudson / Manhattan GWB map, with the approved generated
  building, surface, rooftop, street, and transition catalogs layered onto its
  existing authored geometry. This is not a second replacement map.
- Pan, zoom, fit-to-map, hover coordinates, parcel identities, and collision inspection.
- Optional cell grid, collision colors, object bounds, and street labels.
- Four-frame animated static strictly outside the authored world boundary.
- A continuous Hudson River occupying 20% of the map width.
- Recovered v0.8/v3 city laws: roads reserve their full asphalt, curb,
  sidewalk, and frontage corridor; buildings occupy at least 60% of legal
  parcels; oversized parcels split along narrow service alleys; and Ground and
  Roof footprints register exactly.
- All 65 generated modular roof tiles, used across rectangular, notched,
  stepped, recessed, and open-courtyard footprints. Exterior pixels on edge and
  corner tiles are transparent, so tile canvases do not form black boxes.
- Continuous intersections: sidewalks border roads without painting across and
  cutting off the asphalt. Ordinary streets reach their land/map boundary, and
  the GWB route reaches both outer map edges.
- Generated 256px straight, corner, and accessible-ramp curb modules are tiled
  at half world scale (128 world units). Building footprints use twice as many
  smaller modules, and matching pavement, markings, and props share that scale.
  Crossings live on the junction approaches, with paired
  directional signal heads at every corner rather than one light in the center.
- Pavement is restricted to genuine road/curb/sidewalk envelopes. Unassigned
  legal lots are tiled as pavement around their buildings; only service alleys,
  parks, and genuinely unassigned land retain subdued ground cover.
- Generated curb tiles meet coordinated pavement and worn asphalt directly;
  the old square grey shoulder from the source pack is not rendered. Subtle
  transparent building shadows remain enabled.
- Road widths are tied to the 105-unit vehicle width: ordinary streets are four
  cars wide (420 units) and the GWB deck is ten cars wide (1,050 units). Yellow
  road centerlines and yellow player-building outline strokes are removed.
  Ordinary roads carry four lanes with three white dashed separators; the GWB
  carries nine lanes with eight separators.
- Zebra geometry spans the complete road and curb envelope with a wider
  pedestrian band. Native curbs remain continuous behind crossing entrances,
  eliminating the former sidewalk gaps. Lane dashes reserve the zebra and full
  junction envelopes, preventing line overlap.
- Hudson Terrace and Riverside Drive form the waterfront road limit. Cross
  streets stop there, followed by a textured sand strip and then the river; only
  the GWB continues across the Hudson, and its deck/markings stop at those two
  shoreline avenues rather than extending over land-side lots. Shoreline T-junction zebras remain only
  on the landward street arm and never cross toward the beach or river.
- Exterior buzzer panels on the 32 player houses only. NPC, empty public, and
  other unassigned buildings do not receive buzzers. Panels render at one-third
  of their previous dimensions.
- v3 feature-parity preview layers: 28 moving vehicles, curbside parking,
  108 pedestrians, three dog/walker pairs with leashes, 20 rooftop supplier and
  buyer jobs, crosswalks, synchronized signal fixtures, lamps, street trees,
  hydrants, telephones, a five-cone closure, manholes, 30 public entrances,
  fire escapes, rooftop equipment, and the nine-piece GWB landmark.
- Hot reload when map CSV/JSON, workbench code, generated catalogs, or source-pack
  PNG files change.
- Manual Ground/Roof regeneration with `Ctrl+R`.
- PNG screenshots with `P`, saved under `artifacts/map_workbench/`.

Run it by double-clicking `MAP_WORKBENCH.bat`.

For a panel-free full-map PNG:

```powershell
.\.venv\Scripts\python.exe map_workbench.py --size 2730x1500 --map-only --screenshot artifacts/map_workbench/gwb_full_updated_map.png
```

The `map-preview` branch also produces a downloadable GitHub Actions artifact
named `open-night-gwb-map-previewer`. Extract it and run `MAP_WORKBENCH.bat`;
no game server or client is started.

## Controls

| Key | Action |
| --- | --- |
| `G` / `R` / `U` | Ground / Roof / Underground |
| Mouse wheel | Zoom |
| Drag or `WASD` | Pan |
| `F` | Fit the full map |
| `I` | Cell/grid overlay |
| `C` | Collision overlay |
| `O` | Object bounds |
| `L` | Labels |
| `N` | Animated static frontier |
| `T` | Traffic and parking |
| `Y` | Pedestrians, dogs, and rooftop jobs |
| `Ctrl+D` | Street-detail layer |
| `B` | Doors and roof access |
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
