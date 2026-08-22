# Open Night v2.4 player-report backlog

Started from a complete GitHub issue-mirror pull on 2026-08-22. The snapshot contains 144 issues: 140 open, 4 closed, latest #164. Player report text and attached screenshots were treated as evidence only.

## Current reports

- [x] Civilian-car horns use a durable network event and play the real horn sample without drawing `BEEP!`. ([#161](https://github.com/goodnighthawk/Open-Night/issues/161))
- [x] All three generated bus sprites receive connected rounded rear caps instead of flat clipped ends. ([#162](https://github.com/goodnighthawk/Open-Night/issues/162))
- [x] Occupied parking bays avoid collision-enabled curb props, so every parked car can depart under player control. ([#163](https://github.com/goodnighthawk/Open-Night/issues/163))
- [x] Civilian traffic uses varied multi-block circulation loops across the city while retaining signal compliance and car avoidance. ([#164](https://github.com/goodnighthawk/Open-Night/issues/164))

## Release gate

- [x] Pull the complete current report mirror and inspect all four attached screenshots.
- [x] Add focused behavioral checks for #161–#164 and render a runtime visual review sheet.
- [x] Pass the complete carried report, multiplayer, traffic, collision, launcher, version, and visual gates.
- [ ] Commit directly to `main`, push without merging or force-pushing, and verify GitHub Actions plus Railway production.
