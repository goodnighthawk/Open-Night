# Open Night v1.0.0 — Playable GridWorld baseline

Approved playable baseline from branch `v1.0-art-overlay` and PR #38.

## Runtime baseline
- GridWorld is the authoritative Ground/Roof map for client and server.
- Normalized world scale: 128 px per grid cell, 64 x 48 cells, 8192 x 6144 world units.
- Canonical desktop client: `v100_client.py` via `RUN_CLIENT.bat` / `START_OPEN_NIGHT.bat`.
- Canonical server: `v100_server.py` via `RUN_SERVER.bat`.
- Main `M` map, minimap, player HUD, collision, building/roof registration, exterior fire escapes, and synchronized street lamps are included in the verified runtime proof.

## Verification baseline
Commit `209cfb58aa70b29b2db373cf89bf4bb380bc0c9d` passed Grid Cutover, Grid Runtime Proof, and Ground Art checks before this version marker was added.

## Next phase
Gameplay changes should now be driven by reproduced `/bug` reports. Existing reports from older builds must be re-checked against v1.0 before implementation; new reports should include this v1.0.0 build identity.
