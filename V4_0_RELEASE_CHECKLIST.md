# Open Night v4.0 release checklist

v4.0 is the procedural-city cutover release: the existing GWB corridor becomes the sole normal playable world with a consistent Open Night visual identity and a first-floor blank-house spawn foundation.

## 0. Game-mode authority

- [x] Name the existing/default ruleset **Glorious Car Hijacker**.
- [x] Publish a stable `glorious_car_hijacker` identifier through discovery and login.
- [x] Route local server management and Railway through the same explicit game-mode selection.
- [ ] Verify the game-mode name appears correctly in the launcher and live HUD.

## 1. Map authority

- [x] Keep `map_001_gwb_corridor` as the only normal playable map exposed by `common.py`.
- [ ] Verify desktop and Railway clients both load the same authoritative map build.
- [ ] Confirm no normal launcher path can silently fall back to an obsolete playable map.

## 2. Blank-house first-floor spawn

- [x] Author a distributed pool of blank houses across Fort Lee and Washington Heights.
- [x] Add stable pseudo-random preferred-apartment selection with occupied-floor avoidance.
- [x] Integrate atomic login assignment with one connected player per first floor.
- [x] Start the player in the assigned room on the first playable frame.
- [ ] Preserve outdoor login spawns as a safe recovery fallback only.
- [ ] Verify exit places the player at the correct exterior entrance and re-entry works.
- [x] Spawn player 15+ outdoors at a stable random-looking apartment entrance when all 14 floors are occupied.
- [x] Publish population, housing capacity, and overflow metrics for future controlled map expansion.
- [x] Defer all generated/additional housing to v5.0; v4.0 never mutates the playable map from population data.
- [ ] Verify 14 simultaneous players receive distinct floors and player 15 sees the outdoor overflow flow.
- [x] Present the assignment as `1st Floor - <username>'s Apartment` with a separate numeric floor field.
- [x] Enforce self/mutually-accepted-friend/nearby-buzzer visibility for apartment residency listings; one-sided requests reveal nothing.
- [x] Keep v4.0 friend saves device-local; reciprocal online saves define mutual acceptance for this release.
- [ ] Runtime-check buzzer panels, authorized directory labels, and hidden distant-stranger listings.
- [ ] Runtime-check the red top-right population/capacity counter (for example `15/14`).

## 3. Visual consistency

- [ ] Verify runtime roads, sidewalks, crossings, water/green areas, building art, roofs, street lamps, and major props against the approved Open Night direction.
- [ ] Remove conspicuous legacy-map or placeholder visuals from the normal playable view.
- [ ] Confirm building sprite scale remains consistent and fire escapes/street props do not violate collision/readability.
- [ ] Improve only the highest-impact standout buildings before release; defer broad bespoke-building work.

## 4. Multiplayer regression

- [x] Set the server and local launcher default capacity to 64 sessions and enforce it atomically during login.
- [x] Configure the authoritative player/player-vehicle simulation and client input stream for 60 Hz.
- [x] Keep movement and reliable gameplay events on one WebSocket for v4.0 deployment simplicity.
- [x] Sequence movement inputs, discard stale/out-of-order packets, and acknowledge the latest processed sequence.
- [x] Configure representative stress bots to send sequenced input at 60 Hz.
- [x] Add compact 60 Hz quantized movement messages for nearby players and player-controlled cars/bicycles.
- [x] Keep entity spawning/rich state and ambient entities on the existing 20 Hz snapshot path.
- [x] Keep ambient traffic, bicycles, and pedestrian movement on a separate 30 Hz tier.
- [x] Separate 3072 px dynamic network zones from 1024 px rendering chunks.
- [x] Restrict normal dynamic interest to exactly the current network zone plus eight adjacent zones (3x3).
- [x] Publish current/subscribed network-zone data in snapshots and the F8 panel.
- [x] Publish measured server tick rate/work/budget metrics and expose the initial F8 performance panel.
- [ ] Add application ping, loss, bandwidth, and packet-rate instrumentation to complete the F8 contract.
- [ ] Add local client prediction and reconciliation using the processed-input acknowledgements.
- [ ] Prove stable 60 Hz authoritative ticks under a representative automated 64-client city load.
- [ ] Movement and remote-player visibility pass with at least two clients.
- [ ] Disconnect/reconnect and strict client/server version handling pass.
- [ ] Server snapshots and map-player markers remain coherent while players are indoors/outdoors.

## 5. Core-system regression

- [ ] Vehicles: enter/exit, driving, passengers, traffic interaction, and map collision pass.
- [ ] Friends/SMS: saved friends, autocomplete, send/receive/history pass.
- [ ] HUD 3.0: center opening, inventory/hotbar/resources/chat/pause navigation pass.
- [ ] Minimap/world map: local player, friends, other players, and relevant markers pass.

## 6. Runtime/art proof

- [ ] Capture an actual playable v4.0 runtime view, not only Map Lab or generated preview output.
- [ ] Compare the runtime capture against the approved city-art direction and fix the largest remaining mismatch.
- [x] Run `TEST_FAST.bat`.
- [ ] Run `BUILD_RELEASE.bat` and retain the verification result.

## 7. Release/deployment

- [ ] Change version markers from 3.0 to 4.0 only after the functional gates above pass.
- [ ] Align `VERSION.txt`, wire/server identity, launcher identity, Railway patch identity, and packaged client version.
- [ ] Deploy the v4.0 server to Railway and verify health/login.
- [ ] Verify the normal update workflow installs the matching v4.0 client.
- [ ] Merge/promote only after the release proof is complete.
