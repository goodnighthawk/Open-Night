# Outfit and equipment variation review

Three requested visual variants: navy tactical clothing, burgundy street
clothing, and olive/tan utility clothing. Each sheet is intended to share the
same sixteen-cell order. These are pose and costume proposals; they are not
complete equipment-specific animation loops or registered modular exports.

## Equipment scope found in the project

The active HUD in `hud_v3.py` prepares fist, knife, pistol, and grenade icons.
The earlier pack's `weapon_catalog.csv` also lists eleven prepared overlays,
`weapon_00` through `weapon_10`. They are legacy art references, not proof that
all eleven have implemented gameplay. The current `character_art.py` discards
the weapon ID in `build_action_surface`.

No named equipment types were inferred from empty hotbar or inventory slots.
The legacy catalog has no descriptive weapon names. Keep its IDs until names
and gameplay roles are established. Visual interpretations of those sprites
are not authoritative item definitions.

## Intended sheet layout

| Row | Column 1 | Column 2 | Column 3 | Column 4 |
| --- | --- | --- | --- | --- |
| 1 | Unarmed walk A | Unarmed walk B | Knife ready | Grenade ready |
| 2 | weapon_00 | weapon_01 | weapon_02 | weapon_03 |
| 3 | weapon_04 | weapon_05 | weapon_06 | weapon_07 |
| 4 | weapon_08 | weapon_09 | weapon_10 | Unarmed idle |

Every pose must face north, including the centered two-hand gun grip. Hands
and muzzle belong on the north side of the head; feet extend south. Do not
reuse the inverted grip in prototype v1. Hold silhouettes should distinguish
the blade, grenade, small firearms, long equipment, and baton-like equipment.

After visual approval, separate head, outfit, and equipment using preserved
frame coordinates and sockets. Author matched walk/action frames for each
grip family, then review playback. Generated review sheets need alpha and
registration inspection before use in game. No renderer changes are included
in this art-generation pass.

## Generated output review

- `tactical_equipment_v2.png`: navy tactical outfit; north-pointing equipment.
- `street_equipment_v2.png`: burgundy outfit; strongest centered two-hand grips.
- `utility_equipment_v2.png`: olive and tan workwear; north-pointing equipment.

All three contain sixteen poses but retain baked checkerboard backgrounds.
The tactical and utility sheets use one-hand holds for some larger equipment;
these require supported grip corrections. Equipment silhouettes are generated
interpretations, particularly the curved weapon_07 and broad weapon_09, not
faithful replacements for every catalog sprite. The street sheet is the best
reference for correcting supported north-facing aim in the next art pass.
Walking phase differences also need playback review; these are not seamless
walk cycles. Head and outfit remain assembled in these review outputs.
