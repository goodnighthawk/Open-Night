# V4 Rooftop Replacement Pack

## Release-map read

The map's street-level treatment is now comparatively rich. The rooftop layer remains visibly tied to the original `city_block` pack: repeated, clean pastel slabs with limited surface weathering. The best high-impact replacement is the existing procedural roof-prop catalog, not the map geometry.

## First import pack (priority order)

1. `rooflayer_blue_roof`, `rooflayer_green_roof`, `rooflayer_grey_roof`, `rooflayer_orange_roof` — four weathered roof-surface modules. These appear in the mixed-service and low-profile roof archetypes.
2. `rooflayer_aircon`, `rooflayer_aircon_large` — compact and large HVAC clusters. These appear across the mechanical, waterworks and mixed-service archetypes.
3. `rooflayer_water_brown`, `rooflayer_water_green`, `rooflayer_water_red` — three top-down water-tank variants. These are the thematic centerpiece of waterworks roofs.

That is nine replacement PNGs and covers the dominant repeated `city_block` roof accents. Pipes, small vents, white service boxes and roof-edge masses should remain unchanged for the first pass; they add useful visual scale and can form a second pack once the new roof language is approved.

## Import contract

- All artwork must be strict 80–90 degree top-down, isolated on transparency, and use the dark, dirty nighttime palette of the v4 concept art.
- Each replacement keeps the current runtime draw size, so no map placement or collision changes are needed.
- The source `city_block` pack remains untouched. The generated catalog overrides only the listed `rooflayer_*` IDs.
- The machine-readable asset list and exact briefs live in `assets/grid_v100/generated_rooftop_art_manifest.json`.

## Second pack, after review

Replace `rooflayer_white_box*`, `rooflayer_pipe*`, `rooflayer_duct_02` and the roof-edge masses with matching top-down vents, conduits and penthouse service units.
