# Open Night v0.8.1 — release QA

Validated 2026-08-15.

## Pass 19 map gates

- Sole packaged/runtime map: `map_001_gwb_corridor` — PASS.
- Frozen Pass 18 gameplay geometry: 38 roads, 242 crossings and 95 building
  footprints with zero road/curb/sidewalk/setback overlaps — PASS.
- Pass 19 building assignments: 95 placements / 40 approved styles — PASS.
- Maximum style share 6.3%; nearest exact-repeat share 2.1% — PASS.
- Worst reused-sprite scale spread 0.0964; three church variants — PASS.
- Baked composition: 32 day and 32 night v19 tiles — PASS.
- Runtime CSVs, generator mirror, portable map and asset hashes agree — PASS.

## Runtime and multiplayer gates

- Python compile, map loading, deterministic traffic and compiled-grid loading — PASS.
- Desktop and portable-map WebSocket handshakes and map transfer — PASS.
- Exact v0.8.1 client/server version gate — PASS.
- Friend map markers, persistent SMS/inbox and shared interiors — PASS.
- Shift-run, single/double jump, passenger seats and multi-level traversal — PASS.
- Water wading, vehicle boundaries/front-axle pivot and 30 mph NPC impact gate — PASS.
- Moderated `/bug` queue, human approval gate, clipboard controls and chat hint — PASS.
- Railway/MySQL deployment and clean Pygbag staging — PASS.

All 28 checks represented by `LOCAL_QA.bat` passed. The playability smoke test
exercised both the installed map and the portable-map transfer over real local
WebSockets.
