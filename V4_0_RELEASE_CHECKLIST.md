# Open Night v4.0 release checklist

v4.0 is the procedural-city cutover release: the existing GWB corridor becomes the sole normal playable world with a consistent Open Night visual identity and a first-floor blank-house spawn foundation.

## 1. Map authority

- [x] Keep `map_001_gwb_corridor` as the only normal playable map exposed by `common.py`.
- [ ] Verify desktop and Railway clients both load the same authoritative map build.
- [ ] Confirm no normal launcher path can silently fall back to an obsolete playable map.

## 2. Blank-house first-floor spawn

- [x] Author a distributed pool of blank houses across Fort Lee and Washington Heights.
- [x] Add stable pseudo-random account-to-house selection with occupied-house avoidance.
- [ ] Integrate the selector into server login.
- [ ] Start the player in the assigned room on the first playable frame.
- [ ] Preserve outdoor login spawns as a safe recovery fallback only.
- [ ] Verify exit places the player at the correct exterior entrance and re-entry works.
- [ ] Verify two or more simultaneous players are distributed across houses when free houses exist.

## 3. Visual consistency

- [ ] Verify runtime roads, sidewalks, crossings, water/green areas, building art, roofs, street lamps, and major props against the approved Open Night direction.
- [ ] Remove conspicuous legacy-map or placeholder visuals from the normal playable view.
- [ ] Confirm building sprite scale remains consistent and fire escapes/street props do not violate collision/readability.
- [ ] Improve only the highest-impact standout buildings before release; defer broad bespoke-building work.

## 4. Multiplayer regression

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
- [ ] Run `TEST_FAST.bat`.
- [ ] Run `BUILD_RELEASE.bat` and retain the verification result.

## 7. Release/deployment

- [ ] Change version markers from 3.0 to 4.0 only after the functional gates above pass.
- [ ] Align `VERSION.txt`, wire/server identity, launcher identity, Railway patch identity, and packaged client version.
- [ ] Deploy the v4.0 server to Railway and verify health/login.
- [ ] Verify the normal update workflow installs the matching v4.0 client.
- [ ] Merge/promote only after the release proof is complete.
