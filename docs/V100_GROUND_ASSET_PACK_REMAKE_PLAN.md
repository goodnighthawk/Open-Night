# Open Night v1.0 Ground remake — uploaded asset packs now take priority

This document records the first asset-directed remake step for PR #38.

## Policy

The uploaded art packs supplied in this session are now the highest-priority visual source for the v1.0 Ground layer, above the previous procedural/debug-looking surface treatment.

This changes **how Ground is rendered**, not the authoritative gameplay geometry:

- road centerlines, widths and crossings remain driven by the map CSVs
- sidewalk envelopes remain driven by the map CSVs
- building footprints and layer registration remain driven by the map CSVs
- water, vegetation and other collision/function masks remain authoritative
- uploaded assets constrain the surface language, props and facade vocabulary used inside those masks

## Selected packs and intended use

### 1) `city_block`
Use as the principal **2D city-tile vocabulary** for:

- road and pavement tile motifs
- curb pieces
- zebra/crossing markings
- potholes, drains, cracks and manholes
- premade building/facade sprites
- rooftop decorations such as ducts, HVAC units, awnings and water tanks

Representative assets from the uploaded pack:

- `road_and_pavement_tileset/road_fill.png`
- `road_and_pavement_tileset/pavement_horizontal_repeating.png`
- `road_and_pavement_tileset/curb_left_edge.png`
- `road_markings/white_crossing_piece.png`
- `road_overlays/road_cracks.png`
- `road_overlays/man_hole.png`
- `premade_buildings/red_building_01.png`
- `premade_buildings/blue_building_01.png`
- `premade_buildings/dark_green_building_01.png`
- `roof_top_decorations/aircon_unit.png`
- `roof_top_decorations/red_water_but.png`

### 2) `RetroUrbanFree`
Use as the principal **surface-material source** for Ground:

- asphalt / asphalt road
- concrete / concrete slabs
- pavement variants
- rough pavement wear and edge variation

Representative basecolor sources:

- `AsphaltRoad/AsphaltRoad_05/AsphaltRoad_05_basecolor.png`
- `Asphalt/Asphalt_06/Asphalt_06_basecolor.png`
- `Concrete/Concrete_05/Concrete_05_basecolor.png`
- `ConcreteSlabs/ConcreteSlabs_02/ConcreteSlabs_02_basecolor.png`
- `CleanPavement/ConcretePavement_02/ConcretePavement_02_basecolor.png`
- `RoughPavement/RoughPavement_01/RoughPavement_01_basecolor.png`

### 3) `Free1`
Use as the principal **green-space and shoreline-support source** for:

- grass fill and variation
- rocky edge material for shoreline / embankment accents

Representative basecolor sources:

- `Grass/Grass_03/Grass_03_basecolor.png`
- `Grass/Grass_07/Grass_07_basecolor.png`
- `Rocky/Rocky_04/Rocky_04_basecolor.png`
- `Rocky/Rocky_07/Rocky_07_basecolor.png`

### 4) `Free` and `Free2`
These are held for later phases, primarily:

- interior floor materials
- wood surfaces and room treatment for first/second-floor layers

Ground may use them only sparingly where an exterior deck, boardwalk or wood-surface exception is explicitly needed.

### 5) `GTAMaker`
Treat only as a **reference project artifact** for now. It is not yet selected as a direct source of production runtime art.

## Immediate implementation order

1. Replace procedural road fill with `RetroUrbanFree` asphalt road/basecolor driven by the existing road masks.
2. Replace procedural sidewalk fill with `RetroUrbanFree` concrete / pavement basecolors driven by the existing sidewalk masks.
3. Use `city_block` curb, crossing and road-overlay motifs to restore readable curb edges, zebra crossings and street wear detail.
4. Use `city_block` premade building sprites and roof decorations as the first-pass building/roof vocabulary where scale and footprint fit the authoritative building masks.
5. Use `Free1` grass / rocky materials inside existing vegetation and shoreline masks.
6. Re-run the Ground/Night stitched preview and compare fixed-camera screenshots against the approved target.

## Acceptance intent

The goal of this remake step is **not** to replace the Open Night map with the asset pack's own layout. The goal is to make the authoritative Fort Lee / GWB / Washington Heights geometry render using a consistent purchased/uploaded art vocabulary rather than a loosely procedural placeholder look.
