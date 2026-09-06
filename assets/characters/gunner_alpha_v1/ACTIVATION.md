# Alpha activation

Installed 81 files into assets/characters/grunge_topdown: the clean master,
eight hats, eight heads and 64 body-state files. Each installed file was
SHA-256 compared against its staged source.

Previous live folder backup:
art_review/modular_gunner_2026-09-05/backups/grunge_topdown_before_alpha_767da8a845d74287a865d083a9e88152.zip

Checks passed against the installed live pack:
- tools/character_sheet_bounds_audit.py
- tools/player_revision_audit.py
- tools/audit_grunge_characters.py

Live render contact sheet: work/grunge_character_movement_preview.png.
Restart any open client to discard its cached old sprites.

To restore the previous art, close the client and restore the grunge_topdown
folder from the backup ZIP over assets/characters/grunge_topdown, then restart.
The activation did not modify character catalog IDs, renderer code, or saved
character records. Equipment action rendering remains the documented gap.
