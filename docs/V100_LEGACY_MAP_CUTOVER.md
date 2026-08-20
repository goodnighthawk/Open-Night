# Open Night v1.0 legacy-map cutover

## Authority contract

Open Night v1.0 uses the tile/grid world as the single playable map authority.
Legacy map data may remain in the repository only as migration/reference metadata
or as a source of non-geometric labels such as established place names.

The following gameplay/runtime behavior should be preserved while being rebound to
GridWorld coordinates and records:

- multiplayer player movement and collision
- vehicles, bicycles, NPCs and traffic scheduling
- inventory, supplier/buyer interactions and persistence
- friends, SMS/chat, bug reporting and minimap player markers
- camera, zoom, rotation, jumping/crouching/prone controls
- interiors and future level transitions
- location/place-name labels where still useful

The following legacy map authority is retired for the v1.0 playable world:

- vector road/building/water geometry rendering
- vector/elevated road overlays on Ground
- legacy geometry collision and spawn selection when GridWorld is active
- legacy road/building geometry in the minimap and M world map
- legacy map geometry validation as a prerequisite for grid-authoritative startup

## Migration rule

A v1.0 feature is complete only when its coordinates and collision/route queries are
registered to GridWorld or to explicit grid-associated objects. Rendering pixels are
never collision authority.

Place names may be copied from legacy metadata, but their geometry must not be.
