# Open Night v0.6.4 — release QA

All 20 `LOCAL_QA.bat` stages passed on 2026-08-14.

## New regression gates

- Multiplayer global world-map roster with two simultaneous WebSocket clients: PASS.
- Shared interior entry/movement/exit state and same-room local chat: PASS.
- Friends/minimap filter, whisper routing and scroll-settings integration: PASS.
- Consent-based player package offer/accept/cash transfer: PASS.
- Driver/passenger board/exit/capacity/speed gates: PASS.
- Rotated vehicle-body separating-axis boundary tests: PASS.
- NPC run-over removal, blood-stain lifetime and delayed route replacement: PASS.
- Visible 1.35× automatic layer-jump integration: PASS.

## Preserved game and deployment gates

- Python runtime compile and 80-sheet/4,320-cell character bounds: PASS.
- Map validation: 292 roads, 55 crossings, 41 traffic routes, 33 bicycle lanes, 0 art warnings.
- Building/road exclusion: 868 buildings, 0 overlaps.
- Deterministic traffic, bicycle and pedestrian starts: PASS.
- Multi-level traversal and Map Viewer parity: PASS.
- Desktop and browser Railway auto-detection: PASS.
- Clean Pygbag staging: 658 files, required client/config files present.
- Railway batch control flow: PASS.
- Portable-map package/transfer: PASS.
- Real local server handshake, 10/10 interior gates and portable server transfer: PASS.
