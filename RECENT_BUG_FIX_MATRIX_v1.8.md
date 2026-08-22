# Recent bug reconciliation — Open Night v1.8

Scope: all 58 GitHub-mirrored database reports created from 2026-08-20 through
the v1.5 report session: #42–#100, excluding nonexistent #49.

| Reports | Final release contract | Verification |
|---|---|---|
| #42, #45, #47, #48, #51, #61, #63, #65, #68, #78, #91 | Full-size NPCs use connected multi-block pavement/zebra routes; crowds are mutually non-blocking, flee horns/cars, and escape roads. | `audit_v120_pedestrian_escape.py`, `audit_v120_signal_harmony.py` |
| #43, #55, #60, #73, #81, #98 | Exactly ten supplier/buyer pairs are distributed on pavement as real stationary authoritative NPCs and exposed to map UI. | `audit_recent_bug_history.py` |
| #44, #48 | Grid population enforces the existing 2x minimum NPC/player scale and vehicle manifest dimensions. | `audit_player_vehicle_fleet.py`, canonical client startup gate |
| #46, #54, #58, #99 | Building overlap/setback authority remains intact; connected dark perimeter frames are removed from modular and premade building art. | `audit_recent_bug_history.py`, `BUILDING_SETBACK_RUNTIME_AUDIT.json` |
| #50, #57, #71, #79, #92, #97 | Spatial reservation, bounded class-aware steering, gentle recovery, route reseating, and non-overlap watchdogs prevent spin/stall traffic jams. | `audit_v110_traffic_recovery.py` |
| #52, #53 | Player cars may cross markings and mount sidewalks; AI remains road-bound. Painted lines are visual, never collision authority. | `v110_grid_population._grid_vehicle_blocked` contract |
| #56, #70 | Controls are a dedicated pause-menu page and are absent from the default pause page. | `audit_recent_bug_history.py` |
| #57 | Traffic and pedestrian routes are loops; the route network continuously recirculates entities without dead-end population loss. | population and signal audits |
| #58 | Roof props are constrained to registered Roof-layer building cells and the building setback audit has zero overlaps. | `BUILDING_SETBACK_RUNTIME_AUDIT.json`, GridRenderer layer contract |
| #59, #67, #85, #88 | Every generated traffic approach carries phase metadata; pedestrians enter conflicting crossings only while vehicle traffic is red. | `audit_v120_signal_harmony.py` |
| #62, #64, #66, #75, #76, #89, #100 | Roads retain the latest six-lane width authority; 464 dividers now use repeating-line art, zebras remain crossings, and curb/pavement pieces use the large set. | `audit_v130_art_consolidation.py`, `audit_recent_bug_history.py` |
| #69, #77, #80, #90 | Lamp fixture/emitter records are shared, cool blue, and correctly oriented; traffic signals use compact over-road arms with state on the road-facing end. | `audit_recent_bug_history.py` |
| #72, #82, #83, #87, #93–#96 | Manifest sizing follows the newest report; generated crops retain safe alpha padding and no duplicate shadow; reported indices 5, 7, and 10 are verified by the shared nose-down-sheet to nose-up-runtime transform. | `audit_player_vehicle_fleet.py`, generated-alpha and heading-render audits, `audit_recent_bug_history.py` |
| #74 | The obsolete acceleration tire-screech loop is absent; collision/turn audio is throttled by the audio manager. | `audit_v120_audio.py` |
| #84 | Login selection rejects road cells and searches pavement/sidewalk candidates. | `GridWorld.circle_spawnable`, `audit_recent_bug_history.py` |
| #86 | Q/E indicators, H headlamps, brake lamps, and automatic AI turn indication are server-authoritative and rendered above vehicle sprites. | protocol compile and `audit_recent_bug_history.py` |

Conflicting historical requests are reconciled chronologically. In particular,
the older “roads half size” and “vehicles too large” reports are superseded by
later traffic-width and post-replacement vehicle-scale reports. This avoids
claiming two mutually exclusive presentations at the same time.
