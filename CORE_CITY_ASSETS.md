# Core City Art Assets

v1.5.1 establishes `assets/core_city_pack/` as a carry-forward asset family. New game versions should copy this directory intact unless an asset is explicitly superseded.

Included source/reference atlas:
- `2.5D City Texture Pack Atlas.png` — approved-derived 2.5D building material and city-detail source covering facade families, roof surfaces, windows/doors, parapets, rooftop equipment, fire escapes, awnings, planters and utilities.

Runtime-ready approved tiles remain under `assets/environment/approved/`, street furniture under `assets/street_props/`, and the approved player/NPC pack under `assets/characters/master_dual_camera/`.

The composite source atlas is preserved as a source/reference asset; runtime tiles should be cleanly extracted/derived into the approved runtime directories rather than sampling UI labels or borders from the composite sheet.

v2.5 also includes a user-created CityVoxelPack building converted to clean top-down and isometric PNGs under `assets/open_source_import/city/`. Large 2.5D roofs may use the isometric version as a depth-correct rooftop tower. The movement tester uses either camera-matched version as a world object.
