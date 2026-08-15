# map_generator v0.2

- Removed literal pixel-difference/profile-ranking workflow.
- Added semantic-map / cosmetic-pack / lighting-layer separation.
- Added exactly 100 reusable original environment archetypes with day/night sprite states and atlases.
- Added deterministic cosmetic assignment to stable map object IDs.
- Added derived 2.5D road sign/gantry anchors without changing road semantics.
- Added independent local lighting emitter layer.
- Added day/night Fort Lee, GWB and Washington Heights previews.
- Added a fast non-geographic Style Lab for rapid art-direction iteration.
- Added qualitative structural audit and review prompts rather than image-registration scores.
- Added `gta2_callback_v2` geometry profile separately from cosmetics; no literal 3x lane multiplication.
- Export now copies semantic map, cosmetic pack and generated cosmetic layers independently.
