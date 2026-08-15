# Open Night v0.6.3

This release is built over v0.6.2.1 and the complete v0.6.1 polished-map game.

## Web Railway auto-detection

- The Pygbag/web client reads `config/public_servers.csv` and automatically uses `wss://open-night-production.up.railway.app`.
- Opening the locally served webpage no longer makes the game assume `ws://localhost:8765` while a public endpoint is configured.
- A full or host-only `?server=` query remains the highest-priority override.
- Page-host port `8765` remains the fallback when no public endpoint is enabled.
- Public-server configuration loading is browser-safe; the desktop-only `websockets` import is lazy and excluded from browser startup.
- `server_directory.py` is now included in the clean Pygbag staging tree and checked by the web-build audit.
- Browser players receive randomized synthetic account numbers and display names instead of sharing one fixed account, allowing simultaneous web sessions.
- The connection notice identifies the Open Night internet server while Railway is being contacted.

## Preserved fixes

- Desktop Railway server probing, online-only display, automatic selection, LAN fallback, and Direct Connect remain unchanged.
- The corrected deployment helper continues to use `call railway.cmd` and remains open on every completion or failure path.
- All v0.6.1 map, art, traversal, traffic, Map Viewer, portable-map, and crash-visibility gates remain active.
