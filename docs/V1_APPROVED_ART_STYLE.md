# Open Night v1.0 — Approved Art Style

The v1.0 promotional eight-layer reference board generated and approved on 2026-08-17 is the authoritative visual target for the v1.0 art-overlay release.

## Core visual language

- Dark, richly detailed nighttime city presentation.
- Strict readable top-down / 2.5D game composition; perspective cues must never compromise gameplay alignment.
- **The entire playable world uses one continuous 2.5D camera/art language, indoors and outdoors. Interiors are not isometric and must not switch projection when a player enters a building.**
- Gritty realistic urban surfaces translated into cohesive game art rather than photorealism.
- Warm windows, sodium/amber practical lights, cool moon/sky ambience and restrained neon accents.
- Dense authored environmental detail: roof furniture, utilities, alleys, storefront cues, street furniture, vegetation and landmark-specific structure.
- Strong separation of asphalt, sidewalk, building, vegetation, water, interiors and vertical layers at gameplay zoom.
- Consistent world scale for people, cars, lanes, sidewalks, doors, props and buildings.
- Collision/function geometry remains authoritative. Art conforms to gameplay masks; art pixels never redefine collision.

## Layer identities

1. Hell: fiery underworld, ruins, bridges, lava/fire illumination and demonic/occult architectural cues; readable traversal remains collision locked.
2. Underground: tunnels, sewers, subway/service infrastructure, pipes, maintenance rooms and hidden facilities; low warm utility lighting against cool darkness, rendered in the same 2.5D world projection as ground level.
3. Ground: dense nighttime city streets, parks, alleys, shorelines, storefronts and landmark composition; this is the principal exterior visual benchmark.
4. First Floor: accessible interiors such as shops, homes, offices and public spaces, rendered as 2.5D cutaway/open-roof spaces in exactly the same world projection, camera rotation behavior and scale as the exterior. Walls, doors, furniture and room boundaries gain height/depth cues but never an isometric grid/projection.
5. Second Floor: upper interiors including apartments, offices and clubs, again using the same continuous 2.5D world projection as ground and first floor. Vertical transition changes the active floor/art layer, not the camera projection.
6. Roof: dark rooftops with access points, signs, antennas, HVAC, tanks, utilities, parapets and landmark silhouettes in the same 2.5D projection.
7. Clouds: atmospheric cloud layer with moon, stars, weather/sky cues and city glow; never authoritative for collision.
8. HUD / Space: minimal dark interface framing with crisp readable status, inventory, time/weather and map information; space/sky backdrop may extend the upper atmospheric presentation without obscuring gameplay.

## Interior 2.5D contract

- Entering a building must not rotate, skew, snap or remap the movement grid into an isometric coordinate system.
- Player movement remains world-relative and continuous across exterior/interior boundaries.
- Camera rotation remains a visual camera operation and behaves identically indoors and outdoors.
- Interior walls use 2.5D height/facade cues and may hide/cut away/fade where needed for visibility.
- Floors remain registered to the same X/Y world coordinates as the building footprint below them.
- Stairs and level transitions change Z/layer while preserving X/Y continuity wherever the authored geometry requires it.
- Furniture, doors, counters, rooms and interior props use the same world scale and collision registration as exterior props.
- Interior overlay generation must derive from room/wall/door/collision masks, just like exterior art derives from roads/sidewalks/buildings.
- No separate isometric interior renderer, isometric movement rule, or isometric-only asset requirement is permitted for v1.0.

## Acceptance rules

- The approved board controls palette, lighting hierarchy, density, material language and layer mood, except that any isometric-looking interior presentation in earlier concept material is superseded by the continuous-2.5D interior rule above.
- Existing MAP_ART_RULES.md continues to control functional placement and geometry.
- The approved Fort Lee/GWB/Washington Heights geography remains the world scaffold; the board does not authorize replacing the map with its illustrative island layout.
- Reference-board text/checklists are visual presentation material, not automatically implemented feature claims.
- Do not copy proprietary third-party game assets. Runtime art must be original, user-created, or appropriately licensed.
- Fixed-camera art-review screenshots should be compared against this target after meaningful art changes.

## v1.0 release gate

A v1.0.0 final release requires runtime wiring of the eight-layer overlay system, representative production art for every layer, collision/function audits, layer-transition validation, performance validation, **continuous 2.5D indoor/outdoor projection validation**, and a final fixed-camera visual review against this approved target.
