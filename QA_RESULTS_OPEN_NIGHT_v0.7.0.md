# Open Night v0.7.0 — release QA

All 21 `LOCAL_QA.bat` stages passed on 2026-08-14.

## Map iteration gates

- 289/289 roads at least 2× baseline width: PASS.
- 568 explicit sidewalk sides; 100% eligible ordinary-road coverage: PASS.
- 19 edge continuation tunnels on the world perimeter: PASS.
- 506 buildings with zero asphalt or full-corridor overlaps: PASS.
- 55 compact, road-aligned crossings; zero art-rule errors: PASS.
- 27 retained bicycle routes with zero exposed-water samples: PASS.
- Compact 0.72× top-down bicycle rendering contract: PASS.
- Full bicycle/map and car–bicycle body collision integration: PASS.

## Preserved release gates

- Python compile, imported assets and 4,320 character frame-direction cells: PASS.
- Two-client world-map roster, shared interiors, friends, chat and trading: PASS.
- Passenger seats, rotated vehicle collision and NPC run-over lifecycle: PASS.
- Deterministic traffic/bicycle/pedestrian starts: PASS.
- Multi-level traversal and automatic jump visibility: PASS.
- Desktop/browser Railway auto-detection and deployment batch control flow: PASS.
- Clean Pygbag staging and portable map packaging/transfer: PASS.
- Real local server handshake and portable-server transfer: PASS.
