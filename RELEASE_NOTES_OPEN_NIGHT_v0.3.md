# OPEN NIGHT launcher branch v0.2

- Bundled map generator updated from v0.2 to v0.4 approved-layout portable.
- Generator default changed to night with `night_callback` lighting and authored street lamps enabled.
- Added `config/generator_defaults.csv`; `auto_export_map=true` refreshes the default portable `.map` after a full cosmetic build.
- Generator menu retains explicit named `.map` export.
- Added `server.py --map-file PATH`.
- Server control UI adds Portable `.map` field + Browse button.
- Portable maps are validated, loaded into the authoritative simulation, fingerprinted, compressed with their texture/catalog assets, and distributed over WebSocket only to clients missing that hash.
- Desktop and web network handshakes advertise locally cached map hashes.
- Clients install map packages in persistent shared-data cache and SHA-256 verify before use.
- Portable client renderer resolves downloaded material/prop assets and applies the map's default night/local-light layer.
- Movement preview remains included and uses the authoritative game character pack.
