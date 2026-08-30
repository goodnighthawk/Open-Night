# Open Night — Working State

Read this file before starting a development session. Update it whenever a v4.0 pass is checkpointed so GitHub remains the source of truth.

## Current checkpoint

- Release under development: **Open Night v4.0**
- Working branch: `v4.0`
- Integration base: released `main` v3.0 checkpoint (`68a5abce`)
- Playable world: `map_001_gwb_corridor` only
- Default game mode: **Glorious Car Hijacker** (`glorious_car_hijacker`)
- Map corridor: Fort Lee / GWB approaches / George Washington Bridge / Washington Heights
- Current public version marker remains **3.0** until the v4.0 release gate passes.

## v4.0 objective

Open Night v4.0 should make the existing multiplayer build finally look and feel like Open Night. The procedural/generated GWB corridor is the only normal playable map. The release should favor a consistent approved visual language over bespoke perfection for every building.

Full player housing is post-v4.0. v4.0 establishes the foundation by distributing blank residential houses through the city and spawning players inside a provisional first-floor home instead of outdoors.

## Release blockers

1. **Map cutover** — `map_001_gwb_corridor` is the sole normal playable world. Implemented in architecture; re-verify in v4 runtime.
2. **Visual consistency** — roads, buildings, roofs, sidewalks, crossings, lighting, and major props use the approved Open Night language. Partial; requires runtime visual pass.
3. **Indoor spawn** — 14 private first-floor apartments use collision-free online assignment and first-frame interior delivery. Overflow players spawn outside an apartment; exits/re-entry still require runtime proof.
4. **Multiplayer regression** — movement, player visibility, reconnect/version handling, and server synchronization. v3 baseline exists; v4 regression required.
5. **Core systems regression** — vehicles, friends/SMS, HUD, and minimap. v3 baseline exists; v4 regression required.
6. **Runtime/art verification** — actual playable runtime must match the approved map/art direction; preview-only improvements do not count. Pending.
7. **Release/deployment** — align version 4.0, packaged/local build, Railway deployment, and updater. Pending.
8. **Game-mode authority** — discovery, welcome packets, server manager, Railway, and HUD now identify the default ruleset as Glorious Car Hijacker. Additional modes can be added through the central registry without branching the server entry path.
9. **64-player networking** — v4.0 uses one WebSocket per client for simpler hosting, firewall, and reconnect behavior. The server and launcher default to an atomically enforced 64-session limit. The authoritative player/player-vehicle loop and sequenced client input stream run at 60 Hz; stale/out-of-order inputs are discarded and acknowledged. A compact 60 Hz message carries quantized nearby player/player-controlled-vehicle movement while rich ambient snapshots remain 20 Hz and ambient simulation remains 30 Hz. The client now predicts local on-foot walking/sprinting immediately, rewinds to acknowledged authoritative positions, and replays unacknowledged input through the shared collision path; vehicle prediction remains deferred until the pedestrian behavior is runtime-tuned. F8 reports same-WebSocket application ping, exact encoded bandwidth/message rates, and a rolling 10-second percentage of movement updates that were skipped or arrived late. Dynamic replication uses dedicated 3072 px network zones with a fixed current-plus-eight-neighbors subscription, independent of 1024 px rendering chunks. The 2026-08-30 city-wide proof held 64/64 bots across 16 traversed zones with 59.93 Hz mean/57.03 Hz p05 authority, 2.598 ms peak average work against a 16.667 ms budget, and zero movement gaps, overruns, or bot errors.

## Housing-spawn implementation direction

- Reuse the existing interior system rather than create a second coordinate system for v4.0.
- Author a distributed `blank_house` interior pool against existing building footprints.
- Select a preferred apartment deterministically from the account key, then walk the pool until an unoccupied first floor is found.
- Assign at most one connected player to each authored floor. Current housing capacity is 14 while the connection limit remains higher.
- When capacity is exhausted, spawn the overflow player outdoors at a stable random-looking apartment entrance and expose the overflow count as planning data for v5.0.
- Do not generate, append, or mutate housing geometry in v4.0. Additional housing generation belongs exclusively to the v5.0 map/release project.
- Keep current outdoor `login_spawn` points as recovery/fallback locations if no valid house is available.
- Login should send authoritative interior state immediately so the first playable frame is inside the house.
- Present the assignment as `1st Floor - <username>'s Apartment`; floor remains a separate field for later multi-floor/unit expansion.
- Treat residency as private directory data: self and mutually accepted friends can see it globally; one-sided requests reveal nothing, while strangers receive the listing only beside that building's buzzer.
- Keep v4.0 friend saves device-local. Mutual access exists only while both online clients report each other's saved username; account-backed requests/persistence are deferred.
- Do not expand this pass into furnishing/customization/ownership; those belong after v4.0.
- The 2026-08-30 real-protocol housing audit connected 15 simultaneous clients, assigned 14 distinct first floors, placed player 15 outside an authored buzzer, and passed label/privacy plus exit/re-entry checks.

## Current next pass

1. Visually inspect the red `population/housing capacity` HUD and private buzzer directory in a live client.
2. Retain overflow metrics for v5.0 planning without adding a v4.0 generation trigger.
3. Runtime-tune on-foot prediction/reconciliation, then decide whether v4.0 also needs vehicle prediction.
4. Complete the runtime visual-consistency pass and full multiplayer proof before changing `VERSION.txt` to 4.0.

## Existing development commands

- Play locally: `QUICK_LOCAL_TEST.bat`
- Fast noninteractive checks: `TEST_FAST.bat`
- Full verification and render: `BUILD_RELEASE.bat`
- Build preview: `BUILD_PREVIEW.bat`
- Isolated 64-player city-wide proof: `RUN_V4_CITY_LOAD_TEST.bat`
- Isolated 14-apartment + one-overflow proof: `RUN_V4_HOUSING_TEST.bat`
- Deploy server: `DEPLOY_OPEN_NIGHT_SERVER.bat`

## Scope discipline

- One bounded subsystem or visual problem per pass.
- Runtime behavior outranks Map Lab/preview-only improvements.
- Do not maintain a second playable legacy map.
- Do not change the release version merely to mark work in progress.
- Preserve the released v3.0 baseline on `main`; v4.0 work stays on `v4.0` until gates pass.
