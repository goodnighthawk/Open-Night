# OPEN NIGHT — map scale branch v0.7.0

Double-click **`START_OPEN_NIGHT.bat`**. The launcher remains open while each subsystem runs in its own process.

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

- `RUN_MAP_GENERATOR.bat`
- `RUN_CHARACTER_PREVIEW.bat`
- `LOCAL_QA.bat`

## Internet play

The desktop client probes `wss://open-night-production.up.railway.app` in the background. A valid game-protocol response adds the server to the top of `AVAILABLE SERVERS` and selects it automatically. Offline or invalid endpoints are not shown. The endpoint is editable in `config\public_servers.csv`.

The web client reads the same CSV and uses the Railway endpoint by default. If the CSV has no enabled public endpoint, it falls back to the page host on port `8765`. Appending `?server=192.168.1.5:8765` or a complete WebSocket URI to the webpage URL overrides automatic selection.

## Multiplayer controls

- Friends: Esc > Friends, then add/remove an online name. Friends alone appear on the compact minimap.
- Local chat: press Enter, type, and press Enter again. Nearby outdoor players—or everyone in the same interior—see a speech bubble.
- Whisper: `/w FriendName message`; the name must already be on your Friends list.
- Passenger: press T beside a slow player-driven car. The driver controls it; press T again to leave once it is slow enough.
- Player sale: stand near another player with a package and press E. The buyer presses E nearby to accept the $40 offer.
- NPC sale: stand near a pedestrian with a package and press E. The obsolete fixed customer point no longer buys packages.
- Interior: press E at a doorway. Room movement and all occupants are server-authoritative and visible to one another.
