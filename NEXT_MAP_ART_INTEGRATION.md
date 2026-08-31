# Next Map Artwork Integration

This is a content/generator pass for the map after v4.0. It does not change the
current release marker.

## Integrated artwork

- `assets/generated_v4_buildings/`: 65 modular 256px building tiles across five
  themes. The shared morphology grammar generates rectangles, L-shapes, stepped
  sides, recessed edges, and enclosed courtyards.
- `assets/generated_v4_art/` and `assets/generated_v4_rooftops/`: catalog
  overrides for transitions, street dressing, HVAC, roof finishes, and tanks.
- `assets/generated_v4_surfaces/`: coordinated 256px pavement, curb, asphalt,
  marking-overlay, sand, shoreline, and animated-water tiles.
- `assets/generated_v4_transitions/`: tightly cropped approved entrance, buzzer,
  roof-access, elevator, compact ladder, and six-state traffic-signal sprites.
  Only the four masters listed by `generated_transition_objects.json` are used.

Original `city_block` and free-asset source packs remain unchanged. Runtime
replacement happens through companion catalogs in `assets/grid_v100/`.

## Generator/runtime rules

- Ground collision and Roof walkability use the same exact generated footprint.
- Shared building edges are byte-identical after modular assembly.
- Doors and fire escapes are placed on walkable exterior sidewalk cells; hatches
  remain on their building's walkable Roof footprint.
- Generated street props are collision-neutral and relocate deterministically to
  clear pavement when a new footprint occupies their preferred cell.
- Road markings remain transparent objects. Crossings receive deterministic curb
  ramps; road, turn, T-junction, and intersection topology is classified from
  cardinal neighbors.
- Shorelines use cardinal and diagonal neighbors to select straight, outside-
  corner, and inside-corner tiles.
- Sand remains walkable. Water uses `wade` collision: pedestrians move at 55%
  speed while vehicles remain restricted to `road` cells.
- Transition art, collision, and interaction zones are separate records. Doors,
  buzzers, elevators, roof access, and ladders publish independent prompts and
  targets; inactive triggers never block movement.
- Traffic signals resolve six catalog IDs from a server-published state while
  retaining the original boolean light state for older clients. Every state uses
  one canvas, mast-base pivot, render scale, and zero collision footprint.
- One west-district test area serializes an entrance and buzzer, elevator, roof
  access, ladder route, and four-fixture intersection that cycles all six states.

## Rebuild and verification

Run the surface builder with the bundled workspace Python (Pillow is required),
then run the two audits with the project Python:

```powershell
& 'C:\Users\Pepperoni\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' tools\build_next_map_surface_pack.py
& 'C:\Users\Pepperoni\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' tools\build_next_map_transition_pack.py
python tools\next_map_generated_art_audit.py
python tools\next_map_surface_audit.py
python tools\next_map_transition_audit.py
python tools\render_next_map_transition_preview.py
```

The audits render the full map and close-ups under
`artifacts/next_map_generated_art/` and verify catalog loading, dimensions,
seams, morphology, access, collision, road connectivity, shoreline grammar,
transparent cropping, pivots, all six signal states, transition hooks,
serialization, compatibility, and the shared desktop/server grid loader.
