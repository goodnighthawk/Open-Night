# Current player-report checklist

Release gate: no version bump, deployment, tag, or release commit until every item below is checked and the linked audit evidence passes.

- [x] Radio stops immediately outside a vehicle. (GitHub #102, #109)
- [x] Music and game-audio mute controls remain visible and clickable during normal gameplay. (#109)
- [x] Curbs use rounded corner art and pavement has deterministic visual variation. (#103)
- [x] `gridcar002` artwork and headlights share the same forward direction. (#104)
- [x] Every street-lamp fixture and light pool use one transform and the pool reaches the road. (#105)
- [x] Exterior-connected black building frames are removed without erasing rooftop detail. (#106, #111)
- [x] Road markings are sparser and exactly symmetric about each road center. (#107)
- [x] Junctions publish visible synchronized traffic lights; AI stops on red and recovery never pushes it through red. (#108, #111)
- [x] Login spawns are walkable sidewalks at least three cells from every map edge. (#110)
- [x] Fire escapes provide a working stationary-jump route from Ground to roof and back. (#111)

Verification evidence: `tools/audit_current_bug_checklist.py` passes all ten checks; the sustained traffic audit passes 75 seconds with no blocked/stalled/overlapping cars; `tools/capture_current_bug_visual_qa.py` renders the final visual review board.
