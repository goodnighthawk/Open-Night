# Open Night v2.8

Population stability, rooftop jobs, passenger interaction, and central-map restoration.

- Restores the nine-piece George Washington Bridge landmark over the highway at the center of the map.
- Halves moving traffic from 56 to 28 cars and ambient pedestrians from 216 to 108, while retaining the deadlock and pedestrian recovery systems.
- Moves all 20 suppliers and buyers onto distinct accessible building rooftops. Ambient pedestrians and dogs remain at ground level, and interactions/rendering now respect map level.
- Keeps exactly three one-to-one dog/walker pairs with reciprocal pairing, a leash, and the dog leading its walker.
- Corrects the reported backwards parked yellow vehicle sprite while preserving the approved pixel-car fleet and earlier repairs.
- Resizes shrub planters to fit within one pavement cell with clearance around their collision footprint.
- Allows E to board a nearby occupied AI- or player-driven vehicle as a passenger; the existing T action remains available for taking control.
- Carries every prior report fix, 30-building/30-player capacity authority, character-art archive, launcher updater, and radio feature forward.

Release verification covers the complete issue snapshot through #192, sustained traffic/pedestrian simulation, rooftop accessibility and role isolation, dog pairing, passenger boarding, map-center bridge placement, vehicle orientation, planter clearance, all carried release suites, GitHub Actions, and Railway production.
