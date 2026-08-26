# Open Night — Working State

Read this file before starting a development session. Update it whenever a v4.0 pass is checkpointed so GitHub remains the source of truth.

## Current checkpoint

- Release under development: **Open Night v4.0**
- Working branch: `v4.0`
- Integration base: released `main` v3.0 checkpoint (`68a5abce`)
- Playable world: `map_001_gwb_corridor` only
- Map corridor: Fort Lee / GWB approaches / George Washington Bridge / Washington Heights
- Current public version marker remains **3.0** until the v4.0 release gate passes.

## v4.0 objective

Open Night v4.0 should make the existing multiplayer build finally look and feel like Open Night. The procedural/generated GWB corridor is the only normal playable map. The release should favor a consistent approved visual language over bespoke perfection for every building.

Full player housing is post-v4.0. v4.0 establishes the foundation by distributing blank residential houses through the city and spawning players inside a provisional first-floor home instead of outdoors.

## Release blockers

1. **Map cutover** — `map_001_gwb_corridor` is the sole normal playable world. Implemented in architecture; re-verify in v4 runtime.
2. **Visual consistency** — roads, buildings, roofs, sidewalks, crossings, lighting, and major props use the approved Open Night language. Partial; requires runtime visual pass.
3. **Indoor spawn** — blank houses, valid first-floor spawn, exits/collision, and multi-player house distribution. In progress.
4. **Multiplayer regression** — movement, player visibility, reconnect/version handling, and server synchronization. v3 baseline exists; v4 regression required.
5. **Core systems regression** — vehicles, friends/SMS, HUD, and minimap. v3 baseline exists; v4 regression required.
6. **Runtime/art verification** — actual playable runtime must match the approved map/art direction; preview-only improvements do not count. Pending.
7. **Release/deployment** — align version 4.0, packaged/local build, Railway deployment, and updater. Pending.

## Housing-spawn implementation direction

- Reuse the existing interior system rather than create a second coordinate system for v4.0.
- Author a distributed `blank_house` interior pool against existing building footprints.
- Select a provisional home deterministically from the account key so returning players receive the same house until persistent housing is implemented.
- Prefer an unoccupied house among connected sessions, with stable fallback if all houses are occupied.
- Keep current outdoor `login_spawn` points as recovery/fallback locations if no valid house is available.
- Login should send authoritative interior state immediately so the first playable frame is inside the house.
- Do not expand this pass into furnishing/customization/ownership; those belong after v4.0.

## Current next pass

1. Add and validate the blank-house pool and deterministic selection helper.
2. Integrate house selection into `server.py` login creation and immediate `interior_state` delivery.
3. Verify the client enters the assigned room directly from the welcome/login flow.
4. Test exiting the house to the authored exterior door and re-entering it.
5. Run multiplayer/core-system regressions before changing `VERSION.txt` to 4.0.

## Existing development commands

- Play locally: `QUICK_LOCAL_TEST.bat`
- Fast noninteractive checks: `TEST_FAST.bat`
- Full verification and render: `BUILD_RELEASE.bat`
- Build preview: `BUILD_PREVIEW.bat`
- Deploy server: `DEPLOY_OPEN_NIGHT_SERVER.bat`

## Scope discipline

- One bounded subsystem or visual problem per pass.
- Runtime behavior outranks Map Lab/preview-only improvements.
- Do not maintain a second playable legacy map.
- Do not change the release version merely to mark work in progress.
- Preserve the released v3.0 baseline on `main`; v4.0 work stays on `v4.0` until gates pass.
