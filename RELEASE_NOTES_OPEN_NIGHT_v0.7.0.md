# Open Night v0.7.0

This is the next map-scale iteration over v0.6.4 and retains the complete multiplayer, Railway, social, interior, passenger, trade and NPC run-over feature set.

## Roads and map edge

- All 289 generated drivable roads are at least 2× their stored baseline asphalt width.
- Ordinary roads keep explicit left and right sidewalks.
- 506 buildings were regenerated outside the complete asphalt, curb, furnishing, sidewalk, frontage and setback envelope.
- Nineteen deduplicated perimeter exits continue into strict-top-down tunnel mouths instead of visibly stopping at the map edge.
- The collision boundary remains closed behind each tunnel; portals imply travel beyond the current loaded world but do not unload or teleport players.

## Bicycles and cars

- Bicycle body/shadow art is compact 0.72× and remains strict 90° top-down.
- Six traced bicycle loops that crossed exposed water are rejected by the compiler; all 27 retained loops are water-safe. Bridge-deck routes remain legal.
- Runtime bicycle collision samples the complete rotated body against world bounds, water and buildings.
- Bicycles can use ordinary road space and do not hard-block one another.
- AI and player cars reserve against complete rotated bicycle bodies; cars and bicycles cannot occupy the same space.
- Bicycle starts and parked bicycles are validated or deterministically rescued before spawning.

## Deployment

Run `DEPLOY_OPEN_NIGHT_SERVER.bat` and select the existing `open-night` Railway project/service if linking is requested. Do not create a second project. The public address remains `wss://open-night-production.up.railway.app`.
