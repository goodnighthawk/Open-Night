# Open Night v0.8.0

Pass 18 is now the release-authoritative map instead of a generator-only preview.

## Default and only map

- The sole playable world is the Fort Lee → George Washington Bridge → Washington Heights corridor.
- The reviewed day/night composition is packaged as chunked runtime art; collision and navigation are generated from the same authored pass.
- Static clients and servers require exact `0.8.0` compatibility, and the map build ID is `open_night_v0_8_0_pass18_default_only`.

## Map and artwork

- 38 terrain-aware roads, 157 segments, 96 angled segments and 23 T-junctions replace the old overly regular/wide network.
- 242 crossings snap to their final road centerline and tangent. Zebra bars are parallel to lane lines and the crossing spans curb-to-curb.
- The Hudson continues through the full composition; only the authored GWB enters its water band.
- Filtered reference water and green polygons remain authoritative without consuming excessive developable land.
- 95 late-pass building sprites use Fort Lee, Washington Heights and compact-lot atlases. Scale audits enforce the 0.72–1.12 band.
- Each building exposes ground, upper and roof metadata plus an exterior stairwell record. Three old-church/parish landmark variants remain in the building assignment.

## Playability

- Two ramps connect ground level to the elevated GWB deck.
- Ten enterable locations are rebound to current building frontages.
- Fixed traffic, bicycle and pedestrian routes use the promoted streets and remain deterministic.
- The compiled A1–P12 grid and portable `.map` package are regenerated from v0.8.0 CSVs.
