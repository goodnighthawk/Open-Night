# Gunner alpha v1 — v4.0 character replacement pack

This is a current-renderer-compatible replacement for the contents of
`assets/characters/grunge_topdown`. It is now installed in this workspace.
Restart the game client to load the replaced artwork.

## Contents

- Three new outfit designs: navy tactical, burgundy street, olive/tan utility.
- Three interchangeable heads, with body skin colors baked into each outfit.
- Eight required poses per outfit: idle, walk_left, walk_right, run_left,
  run_right, jump, crouch, prone (24 unique generated body poses).
- Eight retained hats from the existing game pack, registered to the new heads.
- 80 compatibility layer PNGs, each 160x128 RGBA, and a matching 1280x1280 master.
- Three full-resolution RGBA source sheets and a registration/alias manifest.
- Prior equipment concept sheets for reference; these still have baked
  checkerboard backgrounds and are NOT runtime weapon layers.

The game has eight persistent head/outfit IDs. IDs 01/04/07 use tactical art,
02/05/08 use street art, and 03/06 use utility art. These are compatibility
aliases, not eight unique generated outfits. Optional hats remain independent.

## Current animation behavior

Walking uses left/idle/right/idle at eight pose changes per second. Running
alternates left/right at ten changes per second. Jump, crouch and prone each
use one static pose. Double jump reuses jump with extra client scale and lift.
The renderer rotates north-facing art for heading. NPCs, interiors and bicycle
riders reuse this same character system.

The current action renderer ignores action, phase and weapon_id and returns
idle art. This pack does not claim implemented gun, knife, grenade, reload,
firing, crawling or swimming animation cycles. Enabling those requires a
separate gameplay/renderer change and corresponding action frames.

## Install in the next update

Back up the current grunge_topdown pack. Replace its matching master, heads,
bodies and hats together with this pack's files. Keep the folder name
grunge_topdown and existing hat/head/body IDs. The master overrides individual
PNGs in the current renderer, so replacing only the individual files will not
activate the new artwork. Restart the client or clear character-art caches.

The zip has a grunge_topdown/ root ready for the next update's asset import.
The activation replaced the 80 live layer PNGs and the matching clean master.
Catalog, renderer and saved-character data were unchanged. Previous live art
is recoverable from the backup named in ACTIVATION.md.

## Validation and alpha limits

validation.json records dimensional, alpha, master/layer agreement and current
renderer smoke checks. The preview exercises 2,112 combinations/states/headings,
with previews of all 24 unique body poses and all nine head/outfit combinations.
Animation GIF: art_review/modular_gunner_2026-09-05/alpha_movement_preview.gif.

This alpha follows the current renderer's short gait cycles and per-frame
height normalization; it is not a newly authored smooth multi-frame animation
system. Jump/crouch heads consequently appear larger than in the elongated
prone pose, as the renderer rescales the entire frame to a fixed height.
Head selection does not recolor exposed hands/arms to match skin tone.

Art generated with the built-in image tool using the three approved equipment
variation sheets as costume references, followed by alpha-background extraction
and a utility gait correction. Exact main prompt is in
art_review/modular_gunner_2026-09-05/LOCOMOTION_PROMPT.txt. Packaging uses the
game's existing fringe sanitation, crops at blank gutters and registers layers.

Rebuild with tools/build_gunner_alpha_pack.py using this folder's source/*.png
as the three inputs. Validate and regenerate previews/zip with
tools/preview_gunner_alpha_pack.py.
