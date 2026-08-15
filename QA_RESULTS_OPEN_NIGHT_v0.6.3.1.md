# Open Night v0.6.3.1 — release QA

## Crash regression

- Registered fluid-sheet audit: PASS — 80 sheets and 4,320 frame-direction cells fit their declared PNG grids.
- Bundled release-pack selection: PASS — normal startup resolves to the character pack inside the current game folder.
- Out-of-range frame/direction regression: PASS — deliberately invalid `999,999` indices are wrapped before `Surface.subsurface` is called.
- Python compile smoke: PASS.

## Preserved v0.6.3 behavior

- Public Railway discovery and real protocol probe: PASS.
- Desktop internet-first selection, browser Railway default, query override, and localhost fallback: PASS.
- Clean Pygbag staging: PASS — 657 files, required client/config files present.
- Railway deployment batch control flow: PASS.

## Preserved v0.6.1 game

- Current map validation: PASS — 292 roads, 55 crossings, 41 traffic routes, 33 bicycle lanes, 0 art warnings.
- Building/road hard exclusion: PASS — 868 buildings, 0 overlaps.
- Deterministic traffic, bicycle, and pedestrian starts: PASS.
- Multi-level traversal and Map Viewer parity: PASS.
- Portable-map package/transfer: PASS.
- Real local server handshake and 10/10 interior gates: PASS.
- Full 16-step `LOCAL_QA.bat` suite: PASS.
