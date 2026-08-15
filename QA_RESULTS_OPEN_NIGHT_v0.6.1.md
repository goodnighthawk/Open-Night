# Open Night v0.6.1 — release QA

## Default map

- Screenshot-derived `map_001_gwb_corridor` is the sole packaged playable map and server default.
- Map size: 16x12 chunks / 192 chunks.
- 292 roads, 55 compact zebra crossings, 868 buildings, 41 deterministic traffic routes, 33 bicycle lanes.
- Building/road hard exclusion: PASS — 0 asphalt overlaps and 0 road/curb/sidewalk/setback overlaps.
- Art-rule audit: PASS — 0 errors / 0 warnings.
- Zebra rule: bars are parallel to the nearest road/lane tangent; crossing depth is capped at 30 px.

## Runtime and map delivery

- Multi-level audit: PASS — walkable levels 0 and 1, 2 connectors, 1 elevated road deck.
- Launcher integration: PASS — 7 actions including Map Viewer.
- Portable `.map` audit: PASS — 39 semantic tables + 11 cosmetic tables.
- Real server default-map handshake: PASS.
- Portable-map transfer: PASS — 16 chunks followed by `portable_map_v1` welcome.
- Interior gate: PASS — 10/10 enterable locations near building frontages.

## Determinism and scale

- Spatial-interest audit: PASS — 16x12 chunks, 6 logical regions, radius-2 interest <= 25 chunk buckets.
- Deterministic traffic audit: PASS — 194 car starts, 66 bicycle starts, 24 pedestrian starts; no runtime RNG in audited route/start selection.
- Asset + movement audits: PASS — approved asset pack and dedicated 3x wide-gait sheets remain wired.

## Legacy cleanup

- Legacy GIS/Overpass source directories, setup scripts, settings, download dependencies and stale map-expansion/reprofile helpers are absent.
- Reference screenshots + explicit trace CSVs are the only map-source workflow.

## Quick Local Test failure visibility

- `QUICK_LOCAL_TEST.bat` now reports its failing exit code and pauses on failure.
- Unexpected Quick Local Test Python exceptions print a full traceback.
- Windows SERVER and CLIENT child consoles stay open on Python failure and display the child exit code, so a crash cannot silently close before its error is read.

Interactive Windows rendering still needs normal user-side visual confirmation through `QUICK_LOCAL_TEST.bat` / desktop client.
