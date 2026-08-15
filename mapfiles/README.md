# Mapfiles

Only `data/map_001_gwb_corridor` is playable in v1.2. Edit its CSVs directly. `loader.py` normalizes them for both client and server; `tools/validate_mapfiles.py` checks references, bounds and road/sidewalk gameplay scale.

## v1.4 approved-art authoring
- `building_visuals.csv` is client visual metadata keyed by `buildings.csv` ID. It changes apparent 2.5D height, roof material/inset, rooftop module count, art family and shadow scale without changing collision.
- `street_props.csv` is checked by `mapfiles/art_rules.py`; normal street furniture must sit on a valid sidewalk/furnishing envelope and stay clear of buildings/crosswalks.
- `crosswalks.csv` remains authoritative crossing geometry. Traffic signals do not generate zebra decals.
- `MAP_ART_RULES.md` in the release root is the authoritative reference-map-to-playable art guide.
- Run `ART_REVIEW_WATCH.bat` while editing these files for fixed-camera serverless visual feedback.
