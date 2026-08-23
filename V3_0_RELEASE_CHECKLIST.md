# Open Night v3.0 release checklist

v3.0 promotes the approved empty HUD shell into the canonical main client while carrying the verified v2.8 gameplay and report history forward.

## HUD 3.0 authority

- [x] Wire HUD 3.0 through the supported `v100_client.py` launcher path.
- [x] Preserve the strict center opening and render the player in the center of the screen.
- [x] Provide open and closed states with non-overlapping navigation, equipment, magazine, inventory, hotbar, resources, chat, and minimap regions.
- [x] Use a square lower-right minimap and place active chat in the bottom gap between the hotbar and minimap.
- [x] Provide 20 square equipment/pocket sockets, 10 circular ring sockets, 13 hotbar slots, and a 10-by-6 empty inventory grid.
- [x] Preserve the 10-round magazine, hold-R reload, and individual-round top-up interaction contracts.
- [x] Route Resume, Options, Radio Stations, Controls, Friends, Messages, and Quit to the existing client pages/actions.

## Release gate

- [x] Pass the headless HUD 3.0 runtime audit at 1280 by 720.
- [x] Pass the canonical main-release and carried v2.8 regression audits.
- [x] Keep `VERSION.txt`, wire version, server identity, launchers, and Railway patch identity aligned at v3.0.
- [x] Add HUD 3.0 compilation and runtime verification to the main GitHub Actions release gate.
