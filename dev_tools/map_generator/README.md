# Open Night standalone Map + Sprite Generator v0.5.1

Double-click `MAP_GENERATOR.bat`.

The primary workflow imports one composite reference screenshot or separate roads / traffic / terrain / transit / biking screenshots, then traces/compiles them into deterministic semantic CSVs. Option **B** rebuilds the 100-object environment sprite pack, semantic-to-cosmetic bindings, authored-layout dressing, independent lighting/sign layers, night previews and the qualitative audit.

## Art direction

The **approved NYC / Fort Lee / GWB / Washington Heights art target** controls the daytime palette, building massing, road/sidewalk hierarchy, bridge treatment, vegetation, roof detail and 2.5D depth.

The GTA2 callback is treated as an overall **top-down design-language** reference: strong silhouettes, high street readability, gritty/active urban dressing, distinctive districts, local pools of night light, compact loops, cut-throughs and memorable landmark approaches. It is not used for literal image matching or map-geometry copying.

User-supplied layout reference:
`https://mapgenie.io/grand-theft-auto-2`

`config/layout_design.csv` exposes the qualitative layout priorities. `working_cosmetics/layout_design_contract.csv` records the generated contract.

## Cosmetic architecture

Gameplay semantics remain separate from appearance:

- `mapfiles/data/...` = authoritative map/collision/network IDs
- `working_cosmetics/cosmetic_instances.csv` = semantic object -> cosmetic archetype
- `building_massing.csv` = cosmetic sub-volumes inside semantic building footprints
- `layout_overlays.csv` = cosmetic alleys/lightwells/cut-through cues
- `street_dressing.csv` = zero-collision visual dressing
- `road_sign_anchors.csv` / `landmark_anchors.csv` = 2.5D structures
- `light_emitters.csv` = independent lighting/effects layer

A different cosmetic pack can replace these layers without renaming the underlying road/building/object types.

## Portable map export

Choose option **C** in `MAP_GENERATOR.bat` or run `map_generator.py export-map`.

Default output:

```text
exports/
  Map_001_GWB.map
  Map_001_GWB_assets/
    textures/
      objects/       # individual day/night object PNGs; edit directly
      materials/     # asphalt, sidewalk, curb, water, grass, roofs, etc.
    signs/
    lighting/
    atlases/
    catalogs/
    manifest.csv
```

Move the `.map` and its sibling `_assets` folder together. All paths stored in the map are relative. The `.map` itself is plain UTF-8 JSON with a custom extension, making it inspectable, moddable and version-control friendly.

## 100-object budget

There are exactly **100 unique reusable environment archetypes**. Cosmetic placements, building sub-volumes, lighting emitters and layout overlays do not consume additional archetype slots. Vehicles, players and equipment remain separate asset systems.
