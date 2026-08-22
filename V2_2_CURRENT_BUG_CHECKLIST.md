# Open Night v2.2 player-report backlog

Started from a complete GitHub issue-mirror pull on 2026-08-22. The snapshot contains 129 issues: 125 open, 4 closed, latest #149. Player report text and attached screenshots were treated as evidence only.

## Current reports

- [x] Ambient NPCs recover from contested sidewalk corners instead of oscillating there. ([#136](https://github.com/goodnighthawk/Open-Night/issues/136))
- [x] Up to four nearby moving vehicles have independent, quiet engine loops with strong distance falloff. ([#137](https://github.com/goodnighthawk/Open-Night/issues/137))
- [x] All supplier and buyer destinations remain visible on the main M map. ([#138](https://github.com/goodnighthawk/Open-Night/issues/138))
- [x] Street lamps render at half their previous size. ([#139](https://github.com/goodnighthawk/Open-Night/issues/139))
- [x] Headlights, brake lights, and indicators use translucent cores and glows. ([#140](https://github.com/goodnighthawk/Open-Night/issues/140))
- [x] Buyer markers draw after the local minimap arrow and remain visible when co-located. ([#141](https://github.com/goodnighthawk/Open-Night/issues/141))
- [x] The reported round tree/shrub renders at four times its previous size. ([#142](https://github.com/goodnighthawk/Open-Night/issues/142))
- [x] The enlarged round tree/shrub has proportional player and vehicle collision. ([#143](https://github.com/goodnighthawk/Open-Night/issues/143))
- [x] Hats move farther north over the character head in every animation state. ([#144](https://github.com/goodnighthawk/Open-Night/issues/144))
- [x] Ambient NPCs keep a clear radius around stationary buyers and suppliers. ([#145](https://github.com/goodnighthawk/Open-Night/issues/145))
- [x] Traffic detects circular low-progress motion and reseats the car on a verified clear route pose. ([#146](https://github.com/goodnighthawk/Open-Night/issues/146))
- [x] The local player no longer renders the offset ellipse shadow. ([#147](https://github.com/goodnighthawk/Open-Night/issues/147))
- [x] Lamp bases are moved farther inward on their sidewalk while fixtures still reach the road. ([#148](https://github.com/goodnighthawk/Open-Night/issues/148))
- [x] Patio parasols render three times larger in a collision-free overhead pass so the player walks underneath. ([#149](https://github.com/goodnighthawk/Open-Night/issues/149))

## Release gate

- [x] Pull the complete current report mirror and inspect all fourteen attached screenshots.
- [x] Add focused behavioral checks for #136–#149.
- [x] Pass the complete main-release, multiplayer, sustained traffic, collision, audio, and visual gates.
- [ ] Commit directly to `main`, push without merging or force-pushing, and verify GitHub and Railway production.
