# Modular gunner character art

Requested reference: `topdown_gunner_reference.png` (user-provided).

## Customization

- Head: interchangeable head/hair identity.
- Outfit: one coordinated torso, arms, hands, legs, and boots selection.
- Optional hat remains compatible with the existing character system.

The user described outfit-level customization. Individually selectable shirts,
arms, and trousers are not assumed by this prototype.

## Reference pose mapping

Read the supplied reference left to right: upper row first, then lower row.
Prototype columns 1–4 follow the upper unarmed poses; columns 5–8 follow the
lower gun-equipped poses. This is a pose reference, not evidence of a complete
firing, reload, or eight-direction animation set.

Prototype rows: assembled character; outfit without head; head option A;
head option B. Generated imagery is a visual prototype and needs registration
and animation playback review before being treated as runtime-ready art.

## Production requirements

Use a fixed camera directly overhead. All frames share the same cell size,
body pivot, scale, lighting, and animation phase. Record the head socket for
every frame. Preserve blank canvas around extracted layers; independently
cropping each frame would destroy registration unless its offsets are stored.

Head and outfit choices must use the same pose index and frame clock. Review
all head/outfit combinations for gaps, overlaps, wobble, and clipped limbs.
Review walk and gun-walk loops at game scale, including the last-to-first
transition. Do not infer timing or loop order solely from sheet placement.

For production weapon swapping, separate the weapon into an equipment layer
and author matching hand sockets and grips. The first visual prototype keeps
the reference weapon with the gun-pose outfit to establish pose agreement.
Walking should advance from movement; standing aim should hold its pose.
Firing/recoil and reload animations require separately authored frames.

The current game catalog exposes hat/head/body slots in `character_catalog.py`.
The outfit concept maps to its body slot. This art review does not change the
game renderer, character catalog, or saved character data.

## First generated draft review

`modular_gunner_prototype_v1.png` is a concept sheet, not an importable atlas.
The camera and separated head/outfit idea are visible, but row spacing is not
uniform, corresponding body poses differ between assembled and outfit rows,
and weapon placement is inconsistent. The background is a baked checkerboard
in an RGB image rather than alpha transparency. Do not auto-slice this file
into production sprites or claim it reproduces the supplied movement exactly.

Generation mode: built-in image generation, with the supplied image as reference.
Prompt specification: an eight-column, four-row grungy top-down character atlas;
four unarmed reference poses then four gun reference poses; assembled character,
headless coordinated outfit, dark-haired head, and shaved head rows; consistent
registration, overhead camera, reference-like pixel-painted treatment, and
transparent background. The first draft did not satisfy all these constraints.
