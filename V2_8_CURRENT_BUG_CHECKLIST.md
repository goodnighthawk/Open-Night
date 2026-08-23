# Open Night v2.8 release checklist

v2.8 carries the complete verified report history through GitHub issue #197 and restores the George Washington Bridge and Hudson River at the center of the authoritative map.

## Current reports

- [x] [#185](https://github.com/goodnighthawk/Open-Night/issues/185): clear the mass car/NPC stalls by reducing population pressure and retaining traffic/pedestrian recovery.
- [x] [#186](https://github.com/goodnighthawk/Open-Night/issues/186): correct the nose direction for the reported parked yellow vehicle sprite.
- [x] [#187](https://github.com/goodnighthawk/Open-Night/issues/187): place suppliers on accessible building rooftops.
- [x] [#188](https://github.com/goodnighthawk/Open-Night/issues/188): halve moving traffic from 56 to 28 and ambient pedestrians from 216 to 108.
- [x] [#189](https://github.com/goodnighthawk/Open-Night/issues/189): keep exactly three one-to-one dog/walker pairs, with reciprocal IDs, a visible leash, and the dog leading.
- [x] [#190](https://github.com/goodnighthawk/Open-Night/issues/190): resize the wood/shrub planter to fit one pavement cell with walkable clearance.
- [x] [#191](https://github.com/goodnighthawk/Open-Night/issues/191): place every buyer and supplier on a distinct accessible rooftop and keep all ambient NPCs at ground level.
- [x] [#192](https://github.com/goodnighthawk/Open-Night/issues/192): let E board a nearby occupied AI- or player-driven vehicle as a passenger.
- [x] [#193](https://github.com/goodnighthawk/Open-Night/issues/193): show rooftop players and NPCs from Ground; show a crisp playable roof over a strongly blurred, unreadable city backdrop from Roof.
- [x] [#194](https://github.com/goodnighthawk/Open-Night/issues/194): distribute each five-cone closure evenly across the full road instead of overlapping cones at one curb cell.
- [x] [#195](https://github.com/goodnighthawk/Open-Night/issues/195): remove the loose street-edge awning that appeared as a random tarp in the road.
- [x] [#196](https://github.com/goodnighthawk/Open-Night/issues/196): add full-surface patrols for every legal sidewalk component and remove displaced white divider bars.
- [x] [#197](https://github.com/goodnighthawk/Open-Night/issues/197): add a continuous Hudson River channel under the visible nine-piece George Washington Bridge.

## Requested map restoration and carried authority

- [x] Restore all nine George Washington Bridge pieces over the central highway, within five cells of the map midpoint.
- [x] Preserve 30 enterable buildings and the matching 30-player capacity.
- [x] Preserve the recently approved pixel-car fleet, including prior orientation and rear-crop fixes.
- [x] Carry every earlier player-report audit and the v2.6 character-art archive checks forward.

## Release gate

- [x] Pull and safely snapshot 177 GitHub reports (173 open), through issue #197.
- [x] Run focused simulations for population counts, clustering, traffic overlap, rooftop roles, dog pairs, passenger boarding, vehicle orientation, planter clearance, and bridge placement.
- [x] Render and inspect a v2.8 visual proof sheet from the runtime assets.
- [x] Advance launcher, client, server, public-discovery, and Railway patch authority together to v2.8.
- [x] Commit directly to `main`, push without merging or force-pushing, and verify GitHub Actions plus Railway production.
