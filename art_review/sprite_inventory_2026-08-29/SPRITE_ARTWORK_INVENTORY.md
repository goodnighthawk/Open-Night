# Open Night sprite artwork inventory

Scope: the current normal playable world, `map_001_gwb_corridor`, using the v4 grid renderer. This distinction matters because the older freeform map CSVs contain proposed street-detail rows that the current grid renderer does not consume.

## Priority list — unimplemented, easy additions first

These already have matching night artwork in `cosmetic_packs/nyc_gta2_callback/sprites/`. None appears as an object in the current ground or roof grid data.

| Priority | Addition | Current state | Smallest implementation |
|---:|---|---|---|
| 1 | Benches | Sprite ready; no grid catalog entry or placement | Register one object and author a few sidewalk positions |
| 2 | Mailboxes | Sprite ready; no grid catalog entry or placement | Register and place at curb-side sidewalk anchors |
| 3 | Dumpsters | Sprite ready; no grid catalog entry or placement | Register and place in service alleys/building edges |
| 4 | Traffic cones / bollards / barriers | Multiple sprites ready; no placement | Register decorative versions and place near repairs/curbs |
| 5 | Hydrants | Two night variants ready; current grid has none | Register and place visual-only hydrants; collision/breaking can follow separately |
| 6 | Parking, stop, speed, yield, bus and street signs | Full sign family ready; no grid placement | Register pole sprites and author corner/curb positions |
| 7 | Bus shelters | Day/night art ready; no grid placement | Register and place beside existing transit-stop data |
| 8 | Phone boxes / newspaper boxes | Art ready; no grid placement | Register as decorative sidewalk props |
| 9 | Tree and shrub variants | Several day/night variants ready; current grid view uses very limited greenery | Register variants and place only in verified sidewalk/park cells |
| 10 | Chain fence / service fence | Art ready; no grid placement | Add edge-aligned decorative segments near lots and waterfront service areas |

Recommended first art pass: benches, mailboxes, dumpsters, cones, and hydrants. They are small, visually legible, reuse existing assets, and immediately reduce empty sidewalks without changing map geometry.

## Implemented now

| Family | Evidence in current map/runtime | Artwork state |
|---|---:|---|
| Street lamps | 45 placed lamp records | Implemented with synchronized light emitters |
| Road center markings | 116 yellow center-line records plus active white markings | Implemented |
| Crosswalk art | 384 crossing-piece records | Implemented |
| Curb drains | 31 placed records | Implemented |
| Manholes | 4 placed records | Visuals implemented; underground transition is still marked future work |
| Road wear | 29 crack, pothole, oil and puddle decals | Implemented |
| Facade awnings | 25 colored awning records | Implemented |
| Rooftop dressing | 161 non-placeholder roof objects across HVAC, pipes, ducts, tanks, windows and roof effects | Implemented |
| Buildings | 25 enterable runtime buildings | Implemented as modular tile families |
| Characters | Shared top-down player/NPC/cyclist art family | Implemented and animated |
| Vehicles | Player and traffic vehicle sheets | Implemented and animated |
| Bridge landmarks | GWB tower, truss and pier assets are installed by runtime refinement | Implemented, but worth a later composition pass |

## Implemented behavior, but artwork is still a placeholder

| Gap | Current evidence | Needed artwork/work |
|---|---:|---|
| Street doors | 25 `placeholder_street_door` records | Original door family, wall-edge anchors, open/closed states |
| Exterior fire escapes | 25 `placeholder_fire_escape` records | Original cardinal variants and clean building attachment |
| Roof hatches | 25 `placeholder_roof_hatch` records | Closed/open frames and roof-level interaction anchor |

These three are the best “with some work” art task because the gameplay records already exist. Replacing the placeholder images preserves the current transition architecture.

## Requires art plus integration work

1. Dynamic traffic signals: replace procedural/dynamic drawing with a stateful sprite set while keeping server-synchronized red/amber/green state.
2. Destructible hydrants: use the existing hydrant artwork, then connect grid collision, broken state, and the existing water-burst effect.
3. Bus shelters and bus signs: art exists, but transit-stop alignment and pedestrian clearance need an authored placement pass.
4. Vegetation expansion: art exists, but placement must respect roads, crosswalks, doors, and sightlines.
5. GWB composition: current tower/truss/pier sprites exist, but a full bridge silhouette pass needs scale and overlap review.
6. Manhole/subway access: the four manholes already carry a future-transition marker, but the entry animation, lower level, and transition states are not implemented.

## Missing artwork — concept directions

The concept sheet explores eight original additions:

1. Apartment entrance
2. Storefront entrance
3. Exterior fire escape
4. Roof hatch
5. Subway stair entrance
6. Service/storm-drain access
7. Garbage and litter cluster
8. Stray dog (the current ambient dog is procedurally drawn)

The concept sheet is not runtime-ready. It still needs transparent-cell cleanup, per-object slicing, cardinal variants where required, scale normalization, and interaction frames.

## Sheets

- `01_currently_implemented_examples.png` — representative current map/runtime art
- `02_easy_unimplemented_examples.png` — matching existing art that can be added quickly
- `03_missing_art_concepts.png` — new concept directions for genuine artwork gaps
- `missing_art_concept_source.png` — unframed generated source

## Concept-generation note

Mode: built-in image generation, using `cosmetic_packs/nyc_gta2_callback/sprite_atlas_night.png` as the style reference.

Prompt: create a clean 4-by-2 concept sprite sheet containing a street-level apartment door, storefront door, exterior metal fire escape, rooftop hatch, subway stair entrance, storm-drain service access, tied garbage-bag cluster, and a small urban stray dog; match the reference's top-down/slight 2.5D pixel-art language, grungy NYC night palette, cool shadows, and restrained amber accents; isolate every sprite with generous padding; no labels, UI, borders, or watermark.

## Production caution

`ART_STYLE.md` marks current supplied artwork as prototype/reference material. Before public or commercial release, every retained source-pack/cosmetic asset still needs an original-art or license verification pass.
