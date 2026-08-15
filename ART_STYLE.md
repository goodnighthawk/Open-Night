# Art Direction — v1.2

The approved Fort Lee / GWB top-down scene is the exterior visual target for v1.2. Target-derived surface tiles and approved props are used directly by the renderer so the playable map converges on the same dense illustrated city language rather than a flat traced-map look.

## Rendering rules

- Environment atlas access is centralized in `environment_art.py`.
- Static map art is rendered into streamed 1024 px chunks and cached for performance.
- Collision, traffic routes and gameplay positions are loaded from the authoritative Map 001 CSV files and do not depend on texture pixels.
- Authored static street furniture is loaded from `street_props.csv`; dynamic layers are traffic, cyclists, pedestrians, players and UI.
- Map 001 uses a consistent Fort Lee / GWB / Washington Heights urban roof, street and vegetation language across the whole corridor.

## Production note

The current supplied art is prototype/reference material. Replace it with original or properly licensed production art before public/commercial distribution. The asset API and centralized atlas rectangles are designed to make that replacement low-risk.

## Exterior scale

The exterior scale now prioritizes believable person-to-car proportions. A normal sedan should read as roughly two pedestrian sprite-heights long on screen, with buses/trucks substantially larger. Player/NPC sprites stay compact so roads and vehicles no longer feel miniature.

Interiors intentionally switch projection: exteriors remain top-down, while building rooms use a fixed 2:1 isometric grid. The interior target is the readability of classic social-room pixel games: low cutaway walls, strong outlines, simple furniture silhouettes, visible door/window anchors, and grid-snapped object placement. Do not copy proprietary room assets; keep the projection/layout language while replacing prototype art with original/licensed production sprites.

## Approved character art
The uploaded `master_dual_camera` dual-camera sprite family is the v2.5 revision-3 master character system. Top-down gameplay and isometric interiors must use the same registered paper-doll identity. Player characters, pedestrians and cyclist riders draw from the same catalog so NPCs no longer use a visually unrelated procedural style. Known complete outfits prefer their fluid movement sheets; custom mixes retain the same art family through registered body/clothing/accessory layers.

## v1.4 convergence rule
The approved target is a hard visual acceptance reference. Literal reference-map accuracy is subordinate to clean playable streets and the approved composition. Use `ART_REVIEW.bat`/`ART_REVIEW_WATCH.bat` to compare the same camera views after every meaningful art edit. Building collision and building appearance are intentionally separate; tune `building_visuals.csv` and approved facade/roof textures before changing gameplay geometry.
