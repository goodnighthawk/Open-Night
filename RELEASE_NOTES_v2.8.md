# Open Night v2.8

Population stability, rooftop jobs, passenger interaction, and central-map restoration.

- Restores the nine-piece George Washington Bridge landmark over the highway and a continuous Hudson River channel at the center of the map.
- Halves moving traffic from 56 to 28 cars and ambient pedestrians from 216 to 108, while retaining the deadlock and pedestrian recovery systems.
- Moves all 20 suppliers and buyers onto distinct accessible building rooftops. Ambient pedestrians and dogs remain at ground level, and interactions/rendering now respect map level.
- Keeps exactly three one-to-one dog/walker pairs with reciprocal pairing, a leash, and the dog leading its walker.
- Corrects the reported backwards parked yellow vehicle sprite while preserving the approved pixel-car fleet and earlier repairs.
- Resizes shrub planters to fit within one pavement cell with clearance around their collision footprint.
- Allows E to board a nearby occupied AI- or player-driven vehicle as a passenger; the existing T action remains available for taking control.
- Makes rooftop players and NPCs visible from Ground, while Roof view replaces readable street detail with a strongly blurred surrounding-city backdrop.
- Places each five-cone closure evenly across its road, removes the reported loose road awning and displaced white divider bars, and adds patrol coverage for every legal sidewalk cell.
- Carries every prior report fix, 30-building/30-player capacity authority, character-art archive, launcher updater, and radio feature forward.

Release verification covers the complete issue snapshot through #197, sustained traffic/pedestrian simulation, full sidewalk coverage, level-aware visibility, rooftop blur, cone spacing, road-art cleanup, rooftop accessibility and role isolation, dog pairing, passenger boarding, the map-center bridge/Hudson placement, vehicle orientation, planter clearance, all carried release suites, GitHub Actions, and Railway production.
