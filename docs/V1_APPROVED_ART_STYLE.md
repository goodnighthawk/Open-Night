# Open Night v1.0 — Approved Art Style

The user-supplied reference image approved on 2026-08-18 is the authoritative visual target for the v1.0 art-overlay release:

`assets/environment/approved/reference/V1_APPROVED_ART_DIRECTION.jpg`

This reference **supersedes the earlier dark/gritty promotional board for visual style, palette, material treatment and detail language**. Existing gameplay geometry, collision semantics, layer registration and continuous world-coordinate rules remain authoritative.

## Core visual language

- Clean, highly readable illustrated top-down city art with restrained 2.5D height cues.
- Crisp dark outlines and clearly separated shapes rather than painterly, photorealistic or heavily textured rendering.
- Cool blue-gray asphalt, pale blue-gray concrete/sidewalks, and deliberately varied but controlled rooftop/facade colors.
- Saturated accent colors for rooftop equipment, awnings, utility objects, vegetation, signs and interactive-looking details.
- Rooftops are visually busy and authored: HVAC fans, ducts, pipes, tanks, skylights, vents, parapets and utility boxes are major identity cues.
- Streets use simple, legible markings: dashed lane separators, directional arrows, stop text, zebra crossings, curb edges, drains, manholes and occasional cracks/puddles/wear.
- Vegetation uses compact, rounded, outlined forms with visible internal leaf/shrub detail; it must remain visually distinct from pavement and buildings.
- Strong readability at gameplay zoom takes priority over microtexture realism.
- Consistent world scale for people, cars, lanes, sidewalks, doors, props and buildings.
- Collision/function geometry remains authoritative. Art conforms to gameplay masks; art pixels never redefine collision.

## Projection and composition contract

- The entire playable world uses one continuous top-down / restrained-2.5D camera language indoors and outdoors.
- Entering a building must not switch to an isometric renderer or remap movement into an isometric grid.
- Building depth is communicated with roof edges, parapets, facade strips, shadows and equipment rather than perspective distortion that changes gameplay alignment.
- Camera rotation remains visual only; player/world movement stays world-relative.
- Floors remain registered to the same X/Y world coordinates as the building footprint below them.

## Ground layer authority

Ground is the primary visual benchmark and should follow the approved reference closely:

- Roads: flat cool blue-gray asphalt with subtle authored wear, not noisy photorealistic texture.
- Sidewalks: pale modular slabs/tiles with clear curb boundaries and occasional utility details.
- Crossings and markings: large, crisp and gameplay-readable.
- Buildings: colorful roof fields bounded by strong parapets and facade-edge strips.
- Roofs: dense HVAC/duct/pipe/tank/skylight decoration in the same illustrated vocabulary.
- Street furniture: lamps, hydrants, drains, barriers, bins and utility fixtures should use the same outlined sprite language.
- Green areas: saturated but controlled foliage with distinct outlined silhouettes.
- Decorative wear: cracks, puddles, drains and manholes are sparse authored accents rather than global grunge overlays.

## Night/day treatment

The reference controls **shape language, line work, color relationships, materials and density**, not only a time-of-day grade.

- Day variants may stay close to the supplied reference brightness.
- Night variants should darken and cool the scene while preserving the same clean illustrated assets, strong outlines and color separation.
- Night lighting may add pools of warm/cool light and emissive accents, but must not revert to the superseded gritty/photorealistic visual target.
- Ground/Night approval therefore means “this art direction under a readable night grade,” not a different art style.

## Layer identities under the new direction

1. Hell: same clean outlined top-down language, using hotter reds/oranges, lava/fire shapes, ruins and occult/industrial props while preserving traversal readability.
2. Underground: outlined tunnels, pipes, service corridors, subway/sewer infrastructure and maintenance rooms with a darker utility palette.
3. Ground: the supplied reference is the principal direct benchmark.
4. First Floor: accessible interiors use the same outline weight, simplified materials, object scale and top-down projection as Ground.
5. Second Floor: upper interiors continue the same visual grammar without projection changes.
6. Roof: dense illustrated rooftop utility vocabulary, directly informed by the reference image.
7. Clouds: simplified stylized atmospheric shapes; non-collisional and visually subordinate to gameplay.
8. HUD / Space: crisp, minimal UI language compatible with the illustrated world; it must not obscure gameplay.

## Uploaded asset-pack priority

The uploaded art packs remain the preferred production vocabulary where their license permits use:

- `city_block`: primary sprite/tile source for roads, curbs, crossings, rooftops, buildings and urban props; its visual language closely matches the approved reference.
- `RetroUrbanFree`: use selectively for source texture information, but simplify/recolor it to fit the illustrated reference rather than exposing raw photorealistic PBR appearance.
- `Free1`: use selectively for grass/rock source material, stylized to the same outlined illustrated language.
- `Free` / `Free2`: deferred primarily to interior materials.
- `GTAMaker`: reference-only until separately validated.

When a purchased/uploaded source conflicts with this reference image, **the approved reference image wins for visual treatment**, while authoritative map/collision geometry wins for placement and function.

## Acceptance rules

- Existing `MAP_ART_RULES.md` continues to control functional placement and geometry.
- The approved Fort Lee / GWB / Washington Heights geography remains the world scaffold; the reference image does not authorize replacing the map with its example street layout.
- Do not alter road widths, sidewalks, crossings, building footprints, water, vegetation masks or collision to make an asset fit.
- Scale/crop/recolor/compose assets inside authoritative masks instead.
- Do not copy proprietary third-party game assets. Runtime art must be user-created or appropriately licensed.
- Fixed-camera review screenshots should be compared against `V1_APPROVED_ART_DIRECTION.jpg` after meaningful Ground art changes.

## v1.0 release gate

A v1.0.0 final release requires runtime wiring of the eight-layer overlay system, representative production art for every layer, collision/function audits, layer-transition validation, performance validation, continuous indoor/outdoor projection validation, and a final fixed-camera visual review against the approved reference image.
