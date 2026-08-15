# OPEN NIGHT — v0.8.1

Double-click **`START_OPEN_NIGHT.bat`**. The launcher remains open while each subsystem runs in its own process.

GitHub clones on `main` automatically check `origin/main` first and apply only safe fast-forward updates. Offline play and ZIP copies still work; local tracked edits cause the updater to skip rather than overwrite anything.

Extracted friend copies use `UPDATE_FRIEND_BUILD.bat`: choose GitHub download, import a ZIP, or drag a ZIP onto the batch file. It preserves `config\friends.csv`, `.venv`, and local logs.

## Launcher

1. **MAP GENERATOR** — bundled v0.5.1 screenshot-reference front end on the approved-layout portable generator. Open Night defaults to **night**, `night_callback` lighting and authored street lamps.
2. **QUICK TEST** — supervised memory-server/WebSocket/client smoke path.
3. **START SERVER** — authoritative server control panel with portable `.map` selection.
4. **DESKTOP CLIENT** — native Pygame client; automatically detects the configured Railway internet server when it is online, with LAN and Direct Connect fallbacks.
5. **WEB CLIENT** — Pygbag browser client; automatically uses the configured Railway WSS server while retaining a `?server=` override.
6. **MOVEMENT PREVIEW** — character movement/action sandbox using the same authoritative character pack as the game.
7. **MAP VIEWER** — opens portable `.map` files directly, including dynamic per-level filtering.

## New map-source workflow

Open Night map generation is entirely reference-image based. The generator accepts either:

- one composite street-map screenshot, or
- separate **roads / traffic / terrain / transit / biking** screenshots.

Use **Reference Map Trace Studio** to click explicit vectors over those images. The resulting CSV traces are compiled deterministically into a staging semantic map. Installing that staging map creates a backup first. The downstream cosmetic, street-lamp, night-render and portable-map systems are unchanged.

The former GIS/Overpass migration path has been removed after the screenshot-derived default map passed structural, multi-level, server, and portable-map acceptance tests.

## v0.7.0 map iteration

- Generated drivable asphalt is at least 2× its former baseline width.
- Ordinary roads keep explicit sidewalks on both sides; buildings regenerate outside the full frontage envelope.
- Outward-facing perimeter roads continue into visible tunnel portals while the world boundary stays closed.
- Compact strict-top-down bicycles use water-safe generated routes, can use road space, and do not hard-block other bicycles.
- Rotated car and bicycle body boundaries prevent cars from sharing physical space with bicycles.

## v0.7.1 feedback and facing update

- Type `/bug description` in local chat to capture the current game frame and structured map/player context.
- GitHub-ready reports are saved under `feedback\next_version\` as CSV plus PNG; use GitHub Desktop to commit and push reports you want reviewed.
- F10 area reports also mirror into that feedback folder while retaining their persistent shared-data copy.
- Player heads now use the same heading as their bodies. Mouse movement controls bounded camera look-ahead only.

## v0.7.2 unified movement and map build

- Hold Shift with WASD to run at 3x speed in the preview, desktop client, and web client.
- Space performs a forward jump; pressing it twice performs a visibly larger double jump and lands prone.
- C crouches and X toggles prone/standing. The authoritative server replicates run, jump, double-jump, crouch, prone, and stand transitions to nearby players.
- Map Viewer opens the accepted pass-17 Fort Lee/GWB/Washington Heights map by default.
- Railway persistence resets once when the configured patch ID changes, avoiding stale development-state bugs between patches.

## v0.7.3 moderated bug reports

- `/bug`, `/mapfeedback`, and F10 reports keep a local recovery copy and upload to the Railway MySQL queue as `pending`.
- Report text is untrusted, screenshot size/type is bounded, account IDs are salted, and each player is rate-limited.
- `REVIEW_BUG_REPORTS.bat` requires the secret Railway moderator token and exact typed confirmation before approve/reject.
- Only approved reports are exported to `feedback\approved\` for GitHub and ChatGPT; no player submission can automatically become implementation work.

## v0.7.4 multiplayer reliability

- Friends remain highlighted on both M and the compact minimap even when their full avatar is outside the nearby-interest stream.
- `/sms FriendName message` stores online/offline messages in Railway MySQL; Tab completes saved names and F2 opens the inbox.
- The server rejects missing or mismatched client versions with an update instruction before account login.
- On-foot players wade through water at 28% walking speed; cars and bicycles remain water-blocked.
- Player cars steer around a front-axle pivot. NPC blood/respawn triggers only at 30 mph or faster.

## v0.7.5 text editing and bug reminder

- Ctrl+A, Ctrl+C, Ctrl+X, and Ctrl+V work in launcher fields, live chat/SMS composition, and the F10 report note.
- Desktop uses the operating-system clipboard; the browser build uses the browser clipboard API with an in-game fallback.
- Chat displays `/bug describe what went wrong` on a dedicated highlighted line above the entry box, explaining that it captures a screenshot for the human-approval queue.

## v0.8.0 accepted composition

- Pass 18 freezes the accepted full-region road, sidewalk, crossing, water, building-footprint, collision, and baked-composition geometry.
- Outdoor rendering remains orthographic top-down and the baked map supplies matching day and night tiles.
- Decorative yellow center lines remain disabled.

## v0.8.1 Pass 19 building-art convergence

- Pass 19 preserves Pass 18 gameplay geometry and changes building presentation only.
- 95 building placements use 40 approved top-down styles; no style exceeds 6.3% of placements.
- Exact nearest-neighbour repeats are limited to 2.1%, and reused sprite scales stay within a 0.10 spread.
- Three church/parish variants prevent landmark repetition.
- Runtime CSVs, the generator mirror, `composition_tiles_v19.zip`, and `Map_001_GWB.map` are rebuilt and hash-checked together.

## Portable `.map` workflow

The generator defaults remain:

- `default_preview_mode=night`
- `default_lighting_profile=night_callback`
- `street_lamps_enabled=true`
- `auto_export_map=true`
- `map_export_name=Map_001_GWB`

The portable format keeps the `.map` as readable JSON and editable PNG/CSV assets in a sibling `<name>_assets` directory. A server loading a `.map` validates it, loads its semantic data, and distributes a compressed package only to clients that do not already advertise the matching SHA-256 hash. Clients cache verified maps under:

`Documents\PythonMMO_SharedData\maps\client_cache\<map-hash>\`

## Character-source rule

The game and movement preview use `assets/characters/master_dual_camera` from the current release folder, so an older shared-data pack cannot silently override cyclist/player sheets. Modders can deliberately select a complete external pack with `PYMMO_CHARACTER_PACK`.

## Direct shortcuts

- `UPDATE_OPEN_NIGHT.bat`
- `UPDATE_FRIEND_BUILD.bat`
- `RUN_MAP_GENERATOR.bat`
- `RUN_CHARACTER_PREVIEW.bat`
- `LOCAL_QA.bat`
- `REVIEW_BUG_REPORTS.bat`

## Internet play

The desktop client probes `wss://open-night-production.up.railway.app` in the background. A valid game-protocol response adds the server to the top of `AVAILABLE SERVERS` and selects it automatically. Offline or invalid endpoints are not shown. The endpoint is editable in `config\public_servers.csv`.

The web client reads the same CSV and uses the Railway endpoint by default. If the CSV has no enabled public endpoint, it falls back to the page host on port `8765`. Appending `?server=192.168.1.5:8765` or a complete WebSocket URI to the webpage URL overrides automatic selection.

`RUN_WEB_CLIENT.bat` pins and, when necessary, installs Pygbag 0.9.2 because the 0.9.3 browser loader can stop at a plain grey page. The tab/package title should read **Open Night v0.8.1** after the corrected build starts.

## Multiplayer controls

- Friends: Esc > Friends, then add/remove an online name. Friends alone appear on the compact minimap.
- Local chat: press Enter, type, and press Enter again. Nearby outdoor players—or everyone in the same interior—see a speech bubble.
- Whisper: `/w FriendName message`; the name must already be on your Friends list.
- SMS: `/sms FriendName message`; press Tab to complete a saved friend and F2 to read the persistent inbox.
- Bug feedback: `/bug describe what went wrong`; a local backup is kept and the Railway copy waits for human approval.
- Text editing: Ctrl+A selects the current entry; Ctrl+C copies, Ctrl+X cuts, and Ctrl+V pastes.
- Passenger: press T beside a slow player-driven car. The driver controls it; press T again to leave once it is slow enough.
- Player sale: stand near another player with a package and press E. The buyer presses E nearby to accept the $40 offer.
- NPC sale: stand near a pedestrian with a package and press E. The obsolete fixed customer point no longer buys packages.
- Interior: press E at a doorway. Room movement and all occupants are server-authoritative and visible to one another.
