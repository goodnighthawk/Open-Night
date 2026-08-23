# Open Night v2.5

Map-capacity and player-report reconciliation release covering the GitHub backlog through issue #184.

- Restores the George Washington Bridge art over the center highway.
- Adds two enterable infill buildings to empty urban blocks with a three-player-width curb setback.
- Gives every building a wall-bound functional first-floor entrance.
- Reduces public-server capacity from 128 to the authoritative count of 30 enterable buildings; future map changes update the slot limit from the same runtime count.
- Groups traffic cones into three recognizable road closures, moves public telephones inward, and renders lamps and enlarged wall-attached canopies overhead so players and pedestrians pass below them.
- Adds clear-before-entry intersection reservations, inside-junction priority, and sustained overlap/orbit regression checks for civilian traffic.
- Corrects the runtime orientation of `gridcar005` and `gridcar015` while retaining the recently added pixel-car fleet.
- Completes the three generated vehicle exports reported with clipped/missing rear bodywork.
- Speeds up player steering when the active indicator matches the turn direction.
- Keeps pedestrian routes outside building/rooftop footprints, reserves rooftops to buyer/supplier job NPCs, disperses dense visible clusters, and pairs dogs with ahead-of-walker pavement movement plus visible bounded leashes.
- Integrates the selected Arcade Car Physics, CityVoxelPack, white-puff, and character-motion source assets into both game clients and the standalone movement tester.
- Retains the five added top-down vehicle sprites, camera-matched voxel-building art, eight-frame sprint dust, and the modular eight-direction dual-camera character pack.
- Keeps the fluid character frame-count fix, server-authoritative 3× directional running, remote run pose, faster run cadence, and dedicated wide-gait sheets with their modular-outfit fallback.
- Preserves Shift sprint/vehicle boost compatibility while continuing to exclude redundant legacy sprites and original Unity/editor content.

Release verification covers reports #165–#184, every carried report suite, sustained and isolated traffic behavior, building/interior capacity authority, multiplayer handshakes, launcher/version authority, and runtime visual review.
