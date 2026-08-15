# Open Night v0.8.1

This build combines the accepted Pass 19 Fort Lee / GWB / Washington Heights
map with the multiplayer reliability work completed after v0.8.0.

## Pass 19 map

- Pass 18 road, sidewalk, crossing, water, footprint, and collision geometry is
  intentionally frozen.
- Pass 19 assigns 95 building placements across 40 approved top-down styles.
- The most-used atlas cell covers 6.3% of buildings, exact nearest-neighbour
  repeats cover 2.1%, and repeated-sprite scale spread is at most 0.0964.
- Three church/parish variants prevent repeated landmark silhouettes.
- Runtime and generator CSVs, `composition_tiles_v19.zip`, and the portable
  `Map_001_GWB.map` are promoted and hash-checked together.
- Decorative yellow center lines remain disabled.

## Integrated multiplayer improvements

- Friends remain visible on the world map and minimap; persistent `/sms`
  messages support Tab completion and the F2 inbox.
- Clients and servers reject mismatched release versions before login.
- Players wade slowly while cars and bicycles remain water-blocked.
- Player cars use a front-axle pivot and NPC run-over blood requires 30 mph.
- Ctrl+A/C/X/V works in game text fields and chat shows the `/bug` reminder.
- `/bug` screenshots and text enter the moderated Railway queue and require
  explicit human approval before export.

## Compatibility

The client and server version is 0.8.1. Deploy Railway and update every friend
client together; the strict compatibility gate intentionally rejects older
builds.

## Verification

`tools/building_art_convergence_audit.py --strict` enforces the Pass 19 art
limits. `tools/pass19_map_audit.py` verifies the promoted composition, mirrored
semantic tables, portable-map assets and release version.
