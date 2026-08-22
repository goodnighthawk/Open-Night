# Open Night v1.9

Player-report reconciliation release covering GitHub issues #102 through #111.
The release gate remained closed until every item in `CURRENT_BUG_CHECKLIST.md`
was implemented and verified.

- Stops live radio playback immediately when the player leaves a vehicle and
  keeps separate music and game-audio controls visible during normal gameplay.
- Adds rounded road-edge curbs and deterministic pavement variation.
- Corrects `gridcar002` orientation so its nose, headlights, and movement agree.
- Aligns street-lamp fixtures with their road-facing light pools.
- Removes exterior-connected black frames from building art while retaining
  legitimate rooftop detail.
- Reduces road-marking density and makes lane markings symmetric about each
  road center.
- Publishes visible synchronized traffic-light fixtures to clients, makes AI
  obey red phases, and prevents traffic recovery from pushing cars through red.
- Moves login locations onto safe interior sidewalks away from map edges.
- Makes fire escapes functional routes between Ground and roof levels in both
  directions.

Verification includes the ten-item focused checklist audit, a 75-second traffic
simulation with no blocked, stalled, or overlapping vehicles, runtime building
setback checks, launcher/update checks, radio checks, vehicle-fleet checks, and
visual review of the final map features.
