# map_generator v0.4 qualitative art-direction review

This audit intentionally performs **no pixel-difference or image-registration scoring**. The supplied GTA2 screenshots and approved NYC/GWB images are art-direction references, not images the semantic map is expected to line up with.

## Current structural checks

- **PASS — Cosmetic archetype budget:** 100 (target <= 100). Hard cap preserves a small reusable art vocabulary.
- **PASS — Gameplay buildings with cosmetic skin:** 506 (target 506 expected). Every building should be skinnable without altering footprint/collision.
- **PASS — Cosmetic families used:** 20 (target 12+). Enough recurring families to create district identity without asset sprawl.
- **REVIEW — 3D sign anchors:** 19 (target 20–120). Vertical road infrastructure should be visible but not clutter every road.
- **PASS — Bespoke landmark anchors:** 6 (target 4+). GWB and waterfront landmarks should not fall back to generic road/building art.
- **PASS — Bridge cable definitions:** 4 (target 2+). Suspension-cable visuals are independent cosmetic geometry over the semantic bridge deck.
- **PASS — Independent light emitters:** 369 (target 80–450). Night mood should come from local light pools, not a single dark filter.
- **PASS — Cosmetic building massing volumes:** 556 (target >= 506). Large semantic footprints should break into richer visual masses without changing collision.
- **PASS — Authored layout overlays:** 65 (target 20+). Alleys/lightwells/cut-through cues provide memorable top-down layout structure without copying another map.
- **PASS — Cosmetic street dressing:** 1725 (target 150+). Dense reusable dressing improves urban richness without increasing the 100-object archetype budget.
- **PASS — Walkable-road sidewalk presence:** 100.0% (target 100% except motorways). Every non-motorway road should provide a pedestrian edge so road-walking is rarely necessary.
- **PASS — Readable wide sidewalk coverage:** 94.4% (target >= 70%). Most ordinary streets should retain a strong bright sidewalk/curb band; narrow trunk sidewalks may be intentionally slimmer.
- **INFO — Major-road count:** 77 (target informational). Road hierarchy is reviewed structurally, never by pixel registration.
- **INFO — Placed street props:** 371 (target informational). Dense recurring props support the gritty callback atmosphere.

## Visual review priorities for the next human/ChatGPT pass

1. Does the street scene read immediately at gameplay zoom: dark asphalt, light sidewalks/curbs, bold crossings and clean silhouettes?
2. Do buildings form convincing urban walls rather than isolated semantic rectangles?
3. Does each district feel authored through recurring facade/roof/prop families without exceeding the object budget?
4. At night, are there distinct warm/cool local light pools, darker unlit areas, readable vehicles/props, and stronger sign/storefront presence?
5. Are bridge/highway approaches given bespoke vertical infrastructure: gantries, signs, barriers and lights?
6. Are waterfront/industrial edges dense with retaining walls, railings, docks, fences and utility clutter rather than empty land?
7. Are roads adjusted for gameplay readability where literal reference tracing hurts the composition?
8. Does the layout create memorable loops, cut-throughs, landmark approaches and district identity without copying GTA2 geometry?

## Architecture contract

- Gameplay type, collision and networking remain authoritative and style-neutral.
- `cosmetic_instances.csv` maps stable game object IDs to reusable cosmetic archetypes.
- `road_sign_anchors.csv` is a derived 2.5D cosmetic structure layer.
- `landmark_anchors.csv` and `bridge_cables.csv` provide replaceable GWB/lighthouse visual treatment.
- `building_massing.csv`, `layout_overlays.csv` and `street_dressing.csv` are cosmetic layout layers over stable gameplay geometry.
- `light_emitters.csv` is independent from geometry and can be replaced by another lighting pack.
- The callback pack contains exactly 100 master environment archetypes; day/night assets are states of those same objects, not extra object types.
