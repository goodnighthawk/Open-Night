# v2.2 architecture — fixed-flow AI core

`traffic_starts.csv`, `bicycle_starts.csv`, and `npc_starts.csv` are executable authored start plans. `server._fixed_start_plan()` is the only resolver used by moving cars, AI bicycles, and pedestrians. It preserves CSV order and never chooses among routes or generates starting positions. Invalid route IDs or fractions are validation/startup errors.

Runtime AI reacts locally (signals, following, collision reservation, yielding, deterministic stall recovery) but does not plan routes. Traffic-density weighting remains an offline map-authoring operation expressed by the count and order of fixed rows.

## v1.4 art-iteration architecture

The server still owns simple gameplay geometry. The client resolves a separate art layer from `building_visuals.csv`, `street_props.csv`, approved textures and the unified street mesh. This is deliberate: art can change rapidly without rewriting collision, traffic or persistence.

`ART_REVIEW.bat` loads Map 001 directly with the Pygame dummy video driver and renders fixed camera views without networking or MySQL. `ART_REVIEW_WATCH.bat` watches art/map files and refreshes those PNGs automatically. Approved target images live under `assets/art_review_targets/`.

`mapfiles/art_rules.py` defines machine-checkable placement rules. The normal map validator now fails on art-rule errors such as trees on asphalt, sidewalk furniture on motorway-only links, signals deep inside lanes, crosswalk blockage, or spawns in buildings/water. `ART_RULE_AUDIT.bat` also exports the audit as CSV.

Building collision remains the rectangle from `buildings.csv`. `building_visuals.csv` maps that rectangle's ID to a 2.5D visual profile (family, apparent height, roof style/inset, penthouse count and shadow scale). Facade extrusion is visual only.

## v1.3 render architecture
The gameplay/collision map remains simple and server-authoritative. v1.3 adds a richer **visual layer** on top of the same footprints: 2.5D roof extrusions, rooftop modules, and a bespoke GWB overlay. This keeps iteration fast while making the map look closer to the approved art target.

# v1.2 architecture

`map_001_gwb_corridor` is the sole authoritative playable world. The server and client load the same CSV map object through `mapfiles/loader.py`. No runtime GIS conversion exists.

Map layers: roads + road points, buildings, water/green polygons, authored street props, traffic routes/signals, pedestrian routes, bicycle lanes/routes, parked vehicles/bicycles, landmarks/interiors/spawns. `roads.csv` owns explicit asphalt width, lanes, sidewalk width, curb width and building setback.

The camera keeps authoritative world coordinates unrotated. Gameplay is composed into an oversized logical surface, rotated as one scene for middle-mouse camera rotation, then cropped/scaled to the display. Mouse aiming and camera-relative WASD are inverse-transformed back into world coordinates. The M-map remains north-up.

Persistent assets/config are separate from versioned code in `PythonMMO_SharedData`. The curated map stays release-authoritative to prevent an old shared map cache from silently replacing it.

Camera invariant: whenever rotation is non-zero (or the middle button is actively dragging), the render pivot is the local player rather than the look-ahead camera center. The north-up view can still use bounded mouse look-ahead.

Character pipeline: `character_catalog.py` loads the approved pack's CSV registrations without importing Pygame; `character_art.py` performs cached Pygame frame loading/composition. Network packets carry normalized appearance IDs rather than filenames. `database.py` persists those IDs in additive MySQL columns so old accounts can be migrated without dropping cash/inventory. The launcher and server NPC generator consume the same dual-camera option catalog.


## v2.0 deterministic AI routes
Moving traffic, cyclists and pedestrians use fixed CSV start tables. Runtime randomness is not used to select an AI route or starting position. Historical traffic density is an offline authoring input that changes fixed slot counts, not a per-tick routing probability. See `TRAFFIC_SYSTEM.md`.

## v2.4.4 compact spatial partition contract

Map 001 is 24×8 1024px chunks (192 total, exactly 2× the original 16×6 area). Chunks remain the render/collision/debug/network-interest unit. Eight-by-four chunk groups form six logical server regions arranged 3×2.

The current server is still one process, but snapshot construction indexes players/vehicles/NPCs/bicycles/signals into chunk buckets once per snapshot. Each recipient reads only its configured nearby chunk window. Chunked maps send metadata-only welcome records; static world geometry is resolved from packaged local mapfiles.

This separates three scales:

- **32px logical cell** — collision/navigation broad phase
- **1024px chunk** — renderer/cache/debug/network-interest unit
- **8×4 chunks per region** — future authoritative worker ownership/handoff unit

On-foot WASD is camera-relative in v2.4.4. Vehicle input is not camera transformed.

## v2.5 runtime art and run state

The OBJ/MTL importer rasterizes selected user-created Unity geometry into Pygame-native RGBA sprites. Runtime code never loads OBJ, FBX, Unity `.meta`, or editor assets. `assets/open_source_import/catalog.csv` is the conversion ledger; the authoritative vehicle manifest points at copied runtime sprites.

Double-tap detection is client-side input intent, while speed remains server-authoritative. The client sends the existing `boost` field for either a held double-tap run or legacy Shift sprint. The server applies the configured 3.0 multiplier and publishes a `run` pose; every client then selects the faster eight-frame character cadence and dust effect.
