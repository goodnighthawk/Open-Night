# Open Night v0.8.0 — release QA

Validated 2026-08-15.

## Promoted-map gates

- Sole packaged/runtime map: `map_001_gwb_corridor` — PASS.
- 38 roads / 157 segments / 96 angled segments / 23 T-junctions — PASS.
- 242 road-tangent, compact zebra crossings; zero map or art-rule errors — PASS.
- 95 buildings; zero asphalt, curb, sidewalk or setback overlaps — PASS.
- 285 building layer rows and 95 exterior stairwell rows — PASS.
- Continuous Hudson exclusion; zero non-bridge road/building violations — PASS.
- Two water-safe bicycle loops; compact 0.72× bicycle contract — PASS.
- Packaged day/night previews differ from the approved masters by mean RGB 0.0058 / 0.0023 after preview resampling — PASS.

## Runtime gates

- Python compile, map loading and current compiled-grid fingerprint — PASS.
- Spatial interest: 16×12 chunks, six server regions, 25-chunk maximum player window — PASS.
- Ground / GWB deck / roof levels and two bridge ramps — PASS.
- Nine traffic, four bicycle and four pedestrian fixed start slots; deterministic selection — PASS.
- Ten interior entries bound within 18 px of current collision frontages — PASS.
- Desktop static-map and portable-map server handshakes — PASS.
- Portable package: 43 map tables, verified manifest and baked composition archive — PASS.
- Exact v0.8.0 client/server login contract — PASS.

The clean release worktree passed all 24 checks in `LOCAL_QA.bat`. The container did not have Pygame installed, so the visual preview gate used the dependency-free archive/chunk contract path; the actual server and portable transfer were exercised over WebSockets. The approved-master comparison was performed during promotion, and committed preview images remain available as the stable release-clone comparison targets.
