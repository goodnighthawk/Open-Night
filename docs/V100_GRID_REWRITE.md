# Open Night v1.0 grid-authoritative rewrite

## Decision

Open Night v1.0 will no longer treat the existing vector/CSV road-and-building scaffold as the production map authority. The new city-block art pack is built around a 256 px module, so v1.0 will use a **256 px authoritative world grid**.

The current 16384 x 12288 world therefore becomes a **64 x 48 cell map**.

The old vector map remains in the repository only as migration/reference data until the new grid reaches feature parity. New art/runtime work must target the grid.

## Authority

Each grid cell is authoritative for both rendering and gameplay semantics. Tiles are not decorative overlays on top of unrelated collision geometry.

A cell can define:

- base surface tile
- structure/building tile
- decal/road-marking tile
- prop tile/object
- collision class
- traversal layer
- transition/entrance semantics
- optional multi-cell sprite ownership

The runtime derives collision and traversal from the same tile catalog used to render the cell.

## Base grid

- cell size: 256 px
- width: 64 cells
- height: 48 cells
- world width: 16384 px
- world height: 12288 px
- origin: top-left
- coordinates: integer (gx, gy) cell coordinates plus optional local offsets inside a cell

## Tile families

The uploaded `city_block` pack is the primary source and should be imported directly rather than reduced to 64 px material crops.

Primary families:

- road/pavement/curb modules
- small pavement modules
- road markings
- road wear overlays
- five building-floor module families
- premade multi-cell buildings
- roof decorations / HVAC / ducts / pipes / water tanks / helipad

PBR packs may be used only as secondary texture support where a direct city-block tile does not exist.

## Multi-cell buildings

Premade buildings are exact or near-exact multiples of the 256 px grid and should be placed as anchored grid objects. Example: a 1792 x 2048 sprite occupies 7 x 8 cells. Its entire occupied footprint receives building collision/ownership from the same object record.

## Layers

The same grid coordinate system is shared by:

1. hell
2. underground
3. ground
4. first_floor
5. second_floor
6. roof
7. clouds
8. hud_space

A layer may have different tile occupancy, but it must not introduce a second projection or detached coordinate system.

## Migration rule

The existing vector/CSV map may be sampled once to help seed broad geography, but after grid conversion it must not override or silently correct grid cells. Any mismatch is resolved by editing the grid.

## Immediate implementation sequence

1. Introduce the grid data model and tile catalog.
2. Import a curated core of the supplied 256 px tiles directly into the repository.
3. Build a real Ground grid with those tiles and grid-derived collision.
4. Switch the runtime renderer/collision queries to the grid map.
5. Produce a new runtime screen capture proving the supplied assets are actually visible.
6. Only then resume Underground / First Floor / remaining layer production on the same grid system.
