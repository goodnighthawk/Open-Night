# v0.4 — approved NYC cosmetics + authored-layout design pass

- Rebuilt map previews around the approved NYC/GWB target palette and 2.5D hierarchy: deep blue water, dark clean asphalt, pale tiled sidewalks/curbs, warm brick/stone facades, richer roof equipment, autumn/green vegetation, stronger shadows and more vertical street infrastructure.
- Kept the GTA2 callback as an overall design-language reference for top-down readability, contrast, night lighting, dense urban clutter and memorable navigation rather than literal image or map copying.
- Added a deterministic **authored-layout dressing pass** informed by the user-supplied GTA2 interactive-map reference. It generates service-cut-through cues, roof/lightwell courtyards, richer building massing, district-specific street dressing and a layout-design contract while preserving the authoritative gameplay/collision map.
- Added `working_cosmetics/building_massing.csv`: large semantic building footprints may render as multiple adjacent cosmetic volumes without changing collision.
- Added `working_cosmetics/layout_overlays.csv`: cosmetic alleys/lightwells/cut-through cues.
- Added `working_cosmetics/street_dressing.csv`: >1,000 deterministic reusable prop/tree placements drawn from the same 100 archetypes.
- Added `working_cosmetics/layout_design_contract.csv` and `config/layout_design.csv` for editable layout-design priorities.
- Preview renderer now tiles editable surface textures for land, asphalt, sidewalk, curb, water, grass and roofs instead of relying on flat colors.
- Preview views support a scale field so larger bridge/approach compositions can be reviewed without regenerating the map.
- Building sprites have deeper 2.5D facades and stronger roof/facade contrast.
- Portable export remains a plain `.map` JSON file plus sibling editable `_assets` folder. All texture references are relative paths.
- Exactly 100 unique environment archetypes remain the hard master-object budget; massing and dressing create many instances without asset sprawl.
