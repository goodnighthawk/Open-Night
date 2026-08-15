# Open Night map generator summary

## Current generator

Open Night uses the **v0.5 screenshot-reference generator** with the portable `.map` renderer/export pipeline. Night rendering with street lamps remains the default.

### Retained downstream systems
- separate semantic map geometry and cosmetic art layers
- approved Fort Lee / GWB / Washington Heights 2.5D visual rules
- deterministic traffic/start system
- building massing, street dressing, signs, landmarks and lighting
- portable `.map` export with server distribution and client SHA-256 cache
- character movement preview and desktop/web launch paths

## New primary source
The generator uses reference screenshots only. It accepts either one composite street-map screenshot or five aligned screenshots:

1. **roads** — centerlines, hierarchy, bridges and intersections
2. **traffic** — relative flow/density and priority corridors
3. **terrain** — water, parks, green areas and other land-cover cues
4. **transit** — rail/bus/ferry corridors and stations/stops
5. **biking** — bike lanes, protected paths and greenways

The screenshots are visual references only. The Trace Studio converts them into explicit CSV vector traces, and the deterministic compiler converts those traces into the existing semantic map format. Runtime gameplay never reads pixels or performs live map queries.

## GIS removal complete
The old GIS/Overpass importer, setup script, settings and dependencies were removed after the screenshot-derived default map passed the playability gate. Normal generation has one source contract: user-supplied reference screenshots → explicit trace CSVs. No live geographic service is queried.

## New pipeline
`street-map screenshot(s) -> Trace Studio -> five trace CSVs -> deterministic semantic-map staging -> cosmetics/night lighting -> portable .map -> server -> client cache`

Compilation is intentionally staged first. The generator does not overwrite the live working map until **Compile + INSTALL** is chosen, and it saves a backup before installation.
