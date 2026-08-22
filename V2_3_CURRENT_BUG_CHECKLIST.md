# Open Night v2.3 player-report backlog

Started from a complete GitHub issue-mirror pull on 2026-08-22. The snapshot contains 140 issues: 136 open, 4 closed, latest #160. Player report text and attached screenshots were treated as evidence only.

## Current reports

- [x] E boards a nearby player-driven car as a passenger without stealing the driver seat. ([#150](https://github.com/goodnighthawk/Open-Night/issues/150))
- [x] Moving cars displace overlapped players, low-speed NPCs, and non-player vehicles to legal clear poses. ([#151](https://github.com/goodnighthawk/Open-Night/issues/151))
- [x] The reported wooden shrub/tree planter renders at four times its old size with proportional collision. ([#152](https://github.com/goodnighthawk/Open-Night/issues/152))
- [x] Space is a server-authoritative handbrake; the grid contains occupied and open curbside parking bays. ([#153](https://github.com/goodnighthawk/Open-Night/issues/153))
- [x] Public phones sit inward on pavement and carry compact synchronized cyan light pools. ([#154](https://github.com/goodnighthawk/Open-Night/issues/154))
- [x] All 96 GridWorld traffic-light fixtures render through the canonical dynamic world pass. ([#155](https://github.com/goodnighthawk/Open-Night/issues/155))
- [x] Pedestrians retain connected cross-road routes but wait at the curb for close or approaching cars. ([#156](https://github.com/goodnighthawk/Open-Night/issues/156))
- [x] gridcar010 renders its complete source without the synthetic detached rear strip. ([#157](https://github.com/goodnighthawk/Open-Night/issues/157))
- [x] The M map and compact minimap iterate all 20 server-authoritative supplier/buyer locations. ([#158](https://github.com/goodnighthawk/Open-Night/issues/158))
- [x] Ambient pedestrians maintain soft body spacing and choose legal sidesteps around one another. ([#159](https://github.com/goodnighthawk/Open-Night/issues/159))
- [x] The red/white baseball cap has a visible north-facing peak and no composite-frame clipping. ([#160](https://github.com/goodnighthawk/Open-Night/issues/160))

## Release gate

- [x] Pull the complete current report mirror and inspect all eleven attached screenshots.
- [x] Add focused behavioral checks for #150–#160 and render a runtime visual review sheet.
- [x] Pass the complete carried report, multiplayer, traffic, collision, launcher, version, and visual gates.
- [ ] Commit directly to `main`, push without merging or force-pushing, and verify GitHub Actions plus Railway production.
