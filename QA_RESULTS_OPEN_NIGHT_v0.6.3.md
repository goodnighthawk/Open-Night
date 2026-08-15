# Open Night v0.6.3 — release QA

## v0.6.1 preservation

- v0.6.1 polished screenshot-derived 16x12 default map retained.
- 292 roads, 55 compact zebra crossings, 868 buildings, 41 deterministic traffic routes, and 33 bicycle lanes retained.
- Building/road hard exclusion, zebra orientation/depth, multi-level traversal, Map Viewer, portable-map delivery, deterministic traffic, and Quick Local Test failure visibility remain in the release QA suite.

## Internet discovery

- Public-server CSV validation: PASS.
- Real WebSocket `PYMMO_DISCOVER_V1` probe: PASS.
- Live server metadata mapping and external-port handling: PASS.
- Production address configuration (`wss://open-night-production.up.railway.app`): PASS.
- Background-only probe integration, online-only display, internet-first selection, LAN fallback, and Direct Connect fallback: source/compile audit PASS.

## Web-client selection

- Browser-safe server configuration import without desktop `websockets`: PASS.
- Default browser selection resolves to the configured Railway `wss://` endpoint: PASS.
- Full and host-only `?server=` overrides: PASS.
- Page-host port `8765` fallback with no enabled public endpoint: PASS.
- Clean Pygbag staging includes `server_directory.py` and `config/public_servers.csv`: PASS.
- Random synthetic browser account generation replaces the single shared prototype login: source/compile audit PASS.

## Packaging

- Railway configuration and update helper included.
- Railway batch control-flow audit: PASS — all `railway.cmd` invocations use `call`, and the unified exit-code pause is present.
- Python compile smoke: PASS.
- Full automated v0.6.3 suite: PASS, including 0 map art warnings, 0 building/road overlaps, deterministic starts, multi-level parity, portable-map transfer, 10/10 interior gates, and a real local server handshake.
