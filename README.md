# Open Night — v0.7.1

## Start

1. Extract the ZIP fully.
2. Run **`START_OPEN_NIGHT.bat`**.
3. Use the Open Night launcher for map generation, map viewing, quick test, server, desktop client, web client, or movement preview.

When this folder is a GitHub clone on the `main` branch, the launcher checks GitHub before setup and applies only a safe fast-forward update. It continues normally when offline, when Git is unavailable, or when local tracked edits would be affected. Set `OPEN_NIGHT_SKIP_UPDATE=1` to disable the check. ZIP copies continue to launch without auto-update.

The default playable world is now the accepted screenshot-derived full-region map. Night with authored street lamps is the default visual mode; the outdoor projection remains strict GTA2-style top-down while the 10 enterable rooms/stores retain the isometric interior system.

The desktop client now automatically probes `wss://open-night-production.up.railway.app`. When the server is online it appears first in `AVAILABLE SERVERS`, is selected automatically, and can be joined without entering an address. LAN discovery and Direct Connect remain available.

The web client uses the same configured Railway endpoint automatically. Opening the local Pygbag page at `http://127.0.0.1:8000` now connects to the internet server instead of assuming a local game server. An explicit `?server=host:port` query remains available for development overrides.

v0.6.4 makes the Railway world substantially more social: all online players reach the world map, friends appear on the minimap, Enter opens nearby speech-bubble chat, `/w FriendName message` whispers, cars support passengers with persistent occupant names, and building interiors now show and synchronize every player in the same room.

v0.7.0 is the next map iteration. Every generated drivable road now has at least **2×** its former asphalt width. Ordinary streets retain left/right sidewalks, nearby buildings are regenerated against the complete road/curb/furnishing/sidewalk/frontage envelope, and outward-facing perimeter roads terminate in 19 visible continuation tunnels rather than abrupt dead ends. The world boundary remains solid behind the portals.

v0.7.1 adds an in-game next-version feedback path. Type `/bug description` in chat to capture the current frame and append structured context to `feedback/next_version/next_version_feedback.csv`. The screenshot is stored beside it under `feedback/next_version/screenshots/`, ready to review and deliberately commit through GitHub Desktop. F10 area reports mirror into the same folder. Mouse-driven head tracking has been removed; a character's head now follows the body heading while bounded mouse camera look-ahead remains available.

Bicycles now use compact **0.72×**, strict top-down body art. The map compiler rejects bicycle loops that touch exposed water, while bridge-deck cycling remains valid. Bicycles may share the road surface and do not hard-block one another; cars and bicycles use full rotated body boundaries and cannot occupy the same space.

Movement transitions now trigger an automatic jump that renders at 1.35× scale with a small lift. Vehicle/world and car-to-car contacts use rotated body boundaries. Moving vehicles can run over NPC pedestrians, leaving a temporary stylized red stain before a replacement NPC respawns on the route. Point-based selling is removed: sell directly to nearby NPCs, or make a player offer that the buyer accepts with E.

`LOCAL_QA.bat` runs 22 repeatable asset, map-scale, bicycle-water, multiplayer, social, feedback-capture, collision, traffic, multi-level, launcher, internet-discovery and portable-map checks. `tools\pass38_playability_smoke.py` adds a real local server + portable-map protocol gate.

## v2.5 changes

- Five user-created `Arcade_Car_Physics` OBJ vehicles are converted into clean top-down Pygame sprites and added to the authoritative vehicle manifest. Low-density traffic deterministically includes them.
- The user-created `CityVoxelPack` building is converted into top-down and isometric runtime views. The isometric form appears as a depth-correct rooftop module in the game; both views are available to the movement tester.
- White-puff source art is converted into an eight-frame sprint-dust atlas.
- The current dual-camera modular character pack replaces the older bundled player pack. It supports eight headings, modular outfits/accessories, fluid walk/idle rows, and strict 90-degree top-down rendering.
- Double-tap W, A, S, or D to run at **3×** speed. The second-tapped key must remain held; release, crouch, jump, vehicle entry, or stopped movement cancels the run. Shift remains the legacy sprint/vehicle-boost control.
- Remote clients receive the `run` pose and select dedicated eight-frame `run_wide_8` art at the faster cadence. Its peak frames use substantially greater leg separation while the normal walk is unchanged; sprint dust remains synchronized with the run.
- Desktop and web clients use the same source, manifest, character pack, and generated runtime art.

`USER_ASSET_IMPORT.md` describes the source-to-runtime conversion. The package intentionally contains only runtime-ready derivatives and the reproducible importer—not the full Unity project or redundant legacy sprites.

## Map and camera

Map 001 is a 16×12 grid of 1024px chunks (192 chunks, preserving the prior total area while fitting the globally orthogonalized reference extent). The screenshot-derived world is release-authoritative. Geometry is authored from the five bundled reference-image layers and explicit trace CSVs; no live map service is queried.

On-foot WASD is camera-relative. Vehicle throttle/steering remains vehicle-relative. Space jumps, C crouches, T enters/drives/rides/exits vehicles, E interacts/trades/enters rooms, Enter chats, `/bug description` captures feedback, the mouse provides bounded camera look-ahead, middle-mouse rotates the camera, and the mouse wheel zooms. Esc opens the scrollable Settings and Friends pages.

## Useful launchers

- `START_OPEN_NIGHT.bat` — Open Night development launcher
- `UPDATE_OPEN_NIGHT.bat` — safe GitHub `main` fast-forward used automatically by the launcher
- `RUN_MAP_GENERATOR.bat` — screenshot-reference map generator
- `QUICK_LOCAL_TEST.bat` — memory server + desktop client
- `RUN_CLIENT.bat` — desktop client
- `RUN_SERVER.bat` — server
- `RUN_WEB_CLIENT.bat` — browser client
- `RUN_CHARACTER_PREVIEW.bat` — movement/sprite tester
- `RUN_MAP_VIEWER.bat` — portable `.map` viewer with dynamic level filtering
- `DEPLOY_OPEN_NIGHT_SERVER.bat` — update the existing Railway internet service
- `LOCAL_QA.bat` — non-destructive validation suite

The obsolete GIS/Overpass importer, settings, scripts and dependencies have been removed from this branch.
