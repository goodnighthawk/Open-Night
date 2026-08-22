# Open Night — v0.8.1

## Start

1. In a GitHub clone, click **Fetch/Pull origin** in GitHub Desktop.
2. Run **`START_OPEN_NIGHT.bat`**.
3. Use the Open Night launcher for updating, quick test, server, or the desktop client.

When this folder is a GitHub clone on the `main` branch, the launcher checks GitHub before setup and applies only a safe fast-forward update. It continues normally when offline, when Git is unavailable, or when local tracked edits would be affected. Set `OPEN_NIGHT_SKIP_UPDATE=1` to disable the check. Friends using extracted ZIP copies can run `UPDATE_FRIEND_BUILD.bat` to download GitHub `main` or import a ZIP without deleting their local environment, logs, or Friends list.

The default playable world is now the accepted screenshot-derived full-region map. Night with authored street lamps is the default visual mode; the outdoor projection remains strict GTA2-style top-down while the 10 enterable rooms/stores retain the isometric interior system.

The desktop client now automatically probes `wss://open-night-production.up.railway.app`. When the server is online it appears first in `AVAILABLE SERVERS`, is selected automatically, and can be joined without entering an address. LAN discovery and Direct Connect remain available.

The web client uses the same configured Railway endpoint automatically. Opening the local Pygbag page at `http://127.0.0.1:8000` now connects to the internet server instead of assuming a local game server. An explicit `?server=host:port` query remains available for development overrides.

The local browser build pins the known-working Pygbag 0.9.2 runtime. `RUN_WEB_CLIENT.bat` automatically corrects an existing 0.9.3 install, whose browser loader can stall on a solid grey page, and builds under a stable versioned package name to avoid stale-package confusion.

v0.6.4 makes the Railway world substantially more social: all online players reach the world map, friends appear on the minimap, Enter opens nearby speech-bubble chat, `/w FriendName message` whispers, cars support passengers with persistent occupant names, and building interiors now show and synchronize every player in the same room.

v0.7.0 is the next map iteration. Every generated drivable road now has at least **2×** its former asphalt width. Ordinary streets retain left/right sidewalks, nearby buildings are regenerated against the complete road/curb/furnishing/sidewalk/frontage envelope, and outward-facing perimeter roads terminate in 19 visible continuation tunnels rather than abrupt dead ends. The world boundary remains solid behind the portals.

v0.7.1 adds an in-game next-version feedback path. Type `/bug description` in chat to capture the current frame and append structured context to `feedback/next_version/next_version_feedback.csv`. The screenshot is stored beside it under `feedback/next_version/screenshots/`, ready to review and deliberately commit through GitHub Desktop. F10 area reports mirror into the same folder. Mouse-driven head tracking has been removed; a character's head now follows the body heading while bounded mouse camera look-ahead remains available.

v0.7.2 integrates the movement-preview controls into the authoritative multiplayer game. Hold Shift with WASD to run at **3x** speed. Space jumps forward; pressing Space again performs a larger double jump and lands prone. C crouches, X toggles prone/standing, and the one-second stand transition is synchronized for nearby players. The accepted pass-17 Fort Lee/GWB/Washington Heights map remains the default, and Railway persistence resets once per patch ID while this development policy is active.

v0.7.3 replaces direct Git feedback writes with a moderated Railway queue. `/bug description`, `/mapfeedback description`, and F10 captures keep a private local backup and upload bounded report data plus a PNG to MySQL as `pending`. Reports are rate-limited, account identifiers are salted, and player text is treated as untrusted evidence. Only a token-authenticated human using `REVIEW_BUG_REPORTS.bat` can approve a report and export it into `feedback/approved/` for ChatGPT or another development agent.

v0.7.4 stabilizes friend multiplayer. Saved friends remain highlighted on the M map and compact minimap, `/sms FriendName message` supports Tab completion, and F2 opens a Railway-backed inbox that receives online or offline messages. Clients and servers must report the exact same release version before login. Pedestrians can wade slowly in water while vehicles remain blocked, player cars rotate around a front-axle pivot, and NPC run-over blood requires an impact of at least 30 mph.

v0.7.5 adds clipboard editing to launcher fields, chat, SMS composition, and the F10 report note. Use Ctrl+A, Ctrl+C, Ctrl+X, and Ctrl+V. Opening chat now shows `/bug describe what went wrong` on its own highlighted line above the entry box, including the screenshot and human-approval behavior.

v0.8.0 establishes the accepted Pass 18 full-region composition as the default map: clear top-down roads, sidewalks, crossings, authored lighting, and baked day/night tiles share one semantic geometry contract.

v0.8.1 installs Pass 19 over that frozen gameplay geometry. Its building-art convergence assigns 95 placements across 40 approved top-down styles, limits any one atlas cell to 6.3% of the map, holds nearest-neighbour exact repeats to 2.1%, and keeps repeated-sprite scale spread below 0.10. The runtime map, generator mirror, baked `composition_tiles_v19.zip`, and portable `.map` are synchronized. Decorative yellow center lines remain disabled.

Bicycles now use compact **0.72×**, strict top-down body art. The map compiler rejects bicycle loops that touch exposed water, while bridge-deck cycling remains valid. Bicycles may share the road surface and do not hard-block one another; cars and bicycles use full rotated body boundaries and cannot occupy the same space.

Movement transitions now trigger an automatic jump that renders at 1.35× scale with a small lift. Vehicle/world and car-to-car contacts use rotated body boundaries. Moving vehicles can run over NPC pedestrians, leaving a temporary stylized red stain before a replacement NPC respawns on the route. Point-based selling is removed: sell directly to nearby NPCs, or make a player offer that the buyer accepts with E.

`LOCAL_QA.bat` runs 28 repeatable asset, map-scale, bicycle-water, multiplayer, movement, social/SMS, version, moderated-feedback, collision, traffic, multi-level, launcher, internet-discovery, Pass 19 art and portable-map checks. `tools\pass38_playability_smoke.py` adds a real local server + portable-map protocol gate.

## v2.5 changes

- Five user-created `Arcade_Car_Physics` OBJ vehicles are converted into clean top-down Pygame sprites and added to the authoritative vehicle manifest. Low-density traffic deterministically includes them.
- The user-created `CityVoxelPack` building is converted into top-down and isometric runtime views. The isometric form appears as a depth-correct rooftop module in the game; both views are available to the movement tester.
- White-puff source art is converted into an eight-frame sprint-dust atlas.
- The current dual-camera modular character pack replaces the older bundled player pack. It supports eight headings, modular outfits/accessories, fluid walk/idle rows, and strict 90-degree top-down rendering.
- Hold Shift with W, A, S, or D to run at **3x** speed. Release Shift, crouch, jump, enter a vehicle, or stop moving to cancel the run.
- Remote clients receive the `run` pose and select dedicated eight-frame `run_wide_8` art at the faster cadence. Its peak frames use substantially greater leg separation while the normal walk is unchanged; sprint dust remains synchronized with the run.
- Desktop and web clients use the same source, manifest, character pack, and generated runtime art.

`USER_ASSET_IMPORT.md` describes the source-to-runtime conversion. The package intentionally contains only runtime-ready derivatives and the reproducible importer—not the full Unity project or redundant legacy sprites.

## Map and camera

Map 001 is a 16×12 grid of 1024px chunks (192 chunks, preserving the prior total area while fitting the globally orthogonalized reference extent). The screenshot-derived world is release-authoritative. Geometry is authored from the five bundled reference-image layers and explicit trace CSVs; no live map service is queried.

On-foot WASD is camera-relative. Vehicle throttle/steering remains vehicle-relative. Space jumps, C crouches, T enters/drives/rides/exits vehicles, E interacts/trades/enters rooms, Enter chats, `/sms FriendName message` sends persistent friend SMS, F2 opens Messages, `/bug description` submits a pending human-review report, Ctrl+A/C/X/V edits text, middle-mouse rotates the camera, and the mouse wheel zooms. Esc opens the scrollable Settings and Friends pages.

## Useful launchers

- `START_OPEN_NIGHT.bat` — Open Night development launcher
- `UPDATE_OPEN_NIGHT.bat` — safe GitHub `main` fast-forward used automatically by the launcher
- `UPDATE_FRIEND_BUILD.bat` — update an extracted friend copy from GitHub or a shared ZIP
- `QUICK_LOCAL_TEST.bat` — memory server + desktop client
- `RUN_CLIENT.bat` — desktop client
- `RUN_SERVER.bat` — server
- `RUN_WEB_CLIENT.bat` — browser client
- `RUN_CHARACTER_PREVIEW.bat` — movement/sprite tester
- `RUN_MAP_VIEWER.bat` — portable `.map` viewer with dynamic level filtering
- `DEPLOY_OPEN_NIGHT_SERVER.bat` — update the existing Railway internet service
- `REVIEW_BUG_REPORTS.bat` — inspect, approve/reject, and export Railway reports
- `LOCAL_QA.bat` — non-destructive validation suite

The obsolete GIS/Overpass importer, settings, scripts and dependencies have been removed from this branch.
