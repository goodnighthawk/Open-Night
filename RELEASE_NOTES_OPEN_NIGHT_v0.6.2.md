# Open Night v0.6.2

This release is built directly on Open Night v0.6.1 and retains its polished screenshot-derived 16x12 default map, compact correctly oriented zebra crossings, building/road hard-exclusion gates, multi-level traversal, Map Viewer, portable map delivery, and Quick Local Test crash visibility.

## Internet server auto-detection

- Added the live Railway endpoint to `config/public_servers.csv`.
- The desktop server browser probes configured internet endpoints in a background thread using the real `PYMMO_DISCOVER_V1` WebSocket protocol.
- The Railway server appears only after a valid response, including its live name, map, player count, capacity, and server version.
- Reachable internet servers sort first and are selected automatically; the player only needs to click `JOIN`.
- The launcher displays `INTERNET: CHECKING`, `ONLINE`, or `OFFLINE`.
- LAN discovery, same-machine detection, and manual Direct Connect remain intact.
- Public probing never appends Railway's internal port to the `wss://` address.

## Railway packaging

- Added `railway.toml`, `.railwayignore`, `RAILWAY_SETUP.md`, and `DEPLOY_OPEN_NIGHT_SERVER.bat`.
- The update helper links a newly extracted folder to the existing `open-night` Railway project before deployment, preventing an accidental second project.

## QA

- Added a repeatable public-server discovery audit covering CSV filtering, a real WebSocket probe, protocol validation, metadata, and the production Railway address.
