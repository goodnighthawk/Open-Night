# Open Night v1.0 — Approved Art Style

The v1.0 promotional eight-layer reference board generated and approved on 2026-08-17 is the authoritative visual target for the v1.0 art-overlay release.

## Core visual language

- Dark, richly detailed nighttime city presentation.
- Strict readable top-down / 2.5D game composition; perspective cues must never compromise gameplay alignment.
- Gritty realistic urban surfaces translated into cohesive game art rather than photorealism.
- Warm windows, sodium/amber practical lights, cool moon/sky ambience and restrained neon accents.
- Dense authored environmental detail: roof furniture, utilities, alleys, storefront cues, street furniture, vegetation and landmark-specific structure.
- Strong separation of asphalt, sidewalk, building, vegetation, water, interiors and vertical layers at gameplay zoom.
- Consistent world scale for people, cars, lanes, sidewalks, doors, props and buildings.
- Collision/function geometry remains authoritative. Art conforms to gameplay masks; art pixels never redefine collision.

## Layer identities

1. Hell: fiery underworld, ruins, bridges, lava/fire illumination and demonic/occult architectural cues; readable traversal remains collision locked.
2. Underground: tunnels, sewers, subway/service infrastructure, pipes, maintenance rooms and hidden facilities; low warm utility lighting against cool darkness.
3. Ground: dense nighttime city streets, parks, alleys, shorelines, storefronts and landmark composition; this is the principal exterior visual benchmark.
4. First Floor: accessible interiors such as shops, homes, offices and public spaces, using readable cutaway/isometric room language while preserving registered entrances and floor geometry.
5. Second Floor: upper interiors including apartments, offices and clubs; visually related to first floor but more private/vertical in character.
6. Roof: dark rooftops with access points, signs, antennas, HVAC, tanks, utilities, parapets and landmark silhouettes.
7. Clouds: atmospheric cloud layer with moon, stars, weather/sky cues and city glow; never authoritative for collision.
8. HUD / Space: minimal dark interface framing with crisp readable status, inventory, time/weather and map information; space/sky backdrop may extend the upper atmospheric presentation without obscuring gameplay.

## Acceptance rules

- The approved board controls palette, lighting hierarchy, density, material language and layer mood.
- Existing MAP_ART_RULES.md continues to control functional placement and geometry.
- The approved Fort Lee/GWB/Washington Heights geography remains the world scaffold; the board does not authorize replacing the map with its illustrative island layout.
- Reference-board text/checklists are visual presentation material, not automatically implemented feature claims.
- Do not copy proprietary third-party game assets. Runtime art must be original, user-created, or appropriately licensed.
- Fixed-camera art-review screenshots should be compared against this target after meaningful art changes.

## v1.0 release gate

A v1.0.0 final release requires runtime wiring of the eight-layer overlay system, representative production art for every layer, collision/function audits, layer-transition validation, performance validation, and a final fixed-camera visual review against this approved target.
