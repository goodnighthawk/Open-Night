# Open Night v2.5 player-report backlog

Started from a complete GitHub issue-mirror pull on 2026-08-22 and refreshed before release. The snapshot contains 164 issues: 160 open, 4 closed, latest #184. Player report text and attached screenshots were treated as evidence only.

## Current reports

- [x] Every runtime building has a functional first-floor door placed on its wall boundary. ([#165](https://github.com/goodnighthawk/Open-Night/issues/165))
- [x] Traffic cones form three compact road-closure groups instead of appearing as unrelated single props. ([#166](https://github.com/goodnighthawk/Open-Night/issues/166))
- [x] Civilian cars cannot overlap or remain stuck together during sustained traffic simulation. ([#167](https://github.com/goodnighthawk/Open-Night/issues/167))
- [x] `gridcar005` uses its correct nose-up source orientation. ([#168](https://github.com/goodnighthawk/Open-Night/issues/168))
- [x] Street-lamp fixtures are non-blocking overhead art, so pedestrians walk below them without forming prop queues. ([#169](https://github.com/goodnighthawk/Open-Night/issues/169), [#170](https://github.com/goodnighthawk/Open-Night/issues/170))
- [x] Junction reservations stop new cars before an occupied intersection and prioritize cars already clearing it. ([#171](https://github.com/goodnighthawk/Open-Night/issues/171))
- [x] Two ordinary empty urban blocks contain enterable buildings set at least three player widths from the curb. ([#172](https://github.com/goodnighthawk/Open-Night/issues/172))
- [x] Public telephones sit deeper inside the pavement instead of on the curb edge. ([#173](https://github.com/goodnighthawk/Open-Night/issues/173))
- [x] A sustained isolated-car route test rejects tight orbiting/circular traffic behavior. ([#174](https://github.com/goodnighthawk/Open-Night/issues/174))
- [x] `gridcar015` uses its correct nose-up source orientation. ([#175](https://github.com/goodnighthawk/Open-Night/issues/175))
- [x] Canopies are three times larger, attached to the building wall, and rendered as walk-under overhead art. ([#176](https://github.com/goodnighthawk/Open-Night/issues/176))
- [x] The visibly truncated rear exports used by `gridcar035`, `gridcar032`, and `gridcar031` are completed before runtime scaling. ([#177](https://github.com/goodnighthawk/Open-Night/issues/177), [#178](https://github.com/goodnighthawk/Open-Night/issues/178), [#181](https://github.com/goodnighthawk/Open-Night/issues/181), [#184](https://github.com/goodnighthawk/Open-Night/issues/184))
- [x] Grid-native entrances replace random freestanding markers and teleport through the matching wall door to that building's first floor. ([#179](https://github.com/goodnighthawk/Open-Night/issues/179))
- [x] A matching left/right indicator increases player steering rate while an incorrect indicator does not. ([#180](https://github.com/goodnighthawk/Open-Night/issues/180))
- [x] Pedestrian routes exclude building/object footprints and the crowd watchdog prevents stuck visible clusters. ([#182](https://github.com/goodnighthawk/Open-Night/issues/182))
- [x] Dogs are paired with pedestrians, walk ahead on legal pavement, and render a visible bounded leash to their walker. ([#183](https://github.com/goodnighthawk/Open-Night/issues/183))
- [x] Ambient pedestrians and dogs cannot occupy building/rooftop footprints; only buyer and supplier job NPC roles are permitted there.

## Requested map/release changes

- [x] Restore the George Washington Bridge landmark over the center highway.
- [x] Derive server capacity from the final number of enterable buildings; v2.5 must advertise 30 slots for 30 buildings, not 128.

## Release gate

- [x] Pull and inspect the complete current report history and all evidence for #165–#184.
- [x] Pass focused v2.5 behavior checks, the isolated/sustained traffic simulations, and runtime visual review.
- [x] Pass every carried report, multiplayer, collision, launcher, version, and release audit.
- [ ] Commit directly to `main`, push without merging or force-pushing, and verify GitHub Actions plus Railway production.
