# Open Night v2.8 release checklist

v2.8 carries the complete verified report history through GitHub issue #192 and restores the George Washington Bridge at the center of the authoritative map.

## Current reports

- [x] [#185](https://github.com/goodnighthawk/Open-Night/issues/185): clear the mass car/NPC stalls by reducing population pressure and retaining traffic/pedestrian recovery.
- [x] [#186](https://github.com/goodnighthawk/Open-Night/issues/186): correct the nose direction for the reported parked yellow vehicle sprite.
- [x] [#187](https://github.com/goodnighthawk/Open-Night/issues/187): place suppliers on accessible building rooftops.
- [x] [#188](https://github.com/goodnighthawk/Open-Night/issues/188): halve moving traffic from 56 to 28 and ambient pedestrians from 216 to 108.
- [x] [#189](https://github.com/goodnighthawk/Open-Night/issues/189): keep exactly three one-to-one dog/walker pairs, with reciprocal IDs, a visible leash, and the dog leading.
- [x] [#190](https://github.com/goodnighthawk/Open-Night/issues/190): resize the wood/shrub planter to fit one pavement cell with walkable clearance.
- [x] [#191](https://github.com/goodnighthawk/Open-Night/issues/191): place every buyer and supplier on a distinct accessible rooftop and keep all ambient NPCs at ground level.
- [x] [#192](https://github.com/goodnighthawk/Open-Night/issues/192): let E board a nearby occupied AI- or player-driven vehicle as a passenger.

## Requested map restoration and carried authority

- [x] Restore all nine George Washington Bridge pieces over the central highway, within five cells of the map midpoint.
- [x] Preserve 30 enterable buildings and the matching 30-player capacity.
- [x] Preserve the recently approved pixel-car fleet, including prior orientation and rear-crop fixes.
- [x] Carry every earlier player-report audit and the v2.6 character-art archive checks forward.

## Release gate

- [x] Pull and safely snapshot 172 GitHub reports (168 open), through issue #192.
- [x] Run focused simulations for population counts, clustering, traffic overlap, rooftop roles, dog pairs, passenger boarding, vehicle orientation, planter clearance, and bridge placement.
- [x] Render and inspect a v2.8 visual proof sheet from the runtime assets.
- [x] Advance launcher, client, server, public-discovery, and Railway patch authority together to v2.8.
- [ ] Commit directly to `main`, push without merging or force-pushing, and verify GitHub Actions plus Railway production.
