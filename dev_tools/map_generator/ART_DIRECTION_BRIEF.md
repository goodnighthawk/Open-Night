# Art-direction brief — current Open Night target

## Primary visual target

Approved Fort Lee / George Washington Bridge / Washington Heights gameplay art:
- dense authored NYC blocks
- warm brick / stone / concrete building families
- substantial roof HVAC, parapets, water towers and facade rhythm
- deep blue Hudson water
- dark clean asphalt
- pale, highly legible sidewalks and curbs
- bold crosswalks / arrows / intersection hierarchy
- rich green + autumn vegetation
- strict orthographic GTA2-style outdoor projection; 2.5D building depth only, with runtime-owned directional shadows
- bespoke GWB steel, towers, cables, gantries and approach infrastructure

## GTA2 callback target

Use GTA2 qualitatively for:
- top-down gameplay readability
- strong street/sidewalk/object silhouettes
- urban grit and repeated environmental dressing
- district identity
- loops, service alleys, cut-throughs and memorable route choices
- strong local night lighting and contrast
- active vehicle/street composition

Do **not** copy GTA2 map geometry, textures, UI or copyrighted artwork. Do not use pixel-difference/image registration as an acceptance metric.

User-supplied interactive-map layout reference:
`https://mapgenie.io/grand-theft-auto-2`

## Architecture

The style is a replaceable cosmetic layer over stable game semantics. Geometry/collision/networking remains authoritative. Lighting is independently replaceable again on top of the cosmetics.
