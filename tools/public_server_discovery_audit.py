from __future__ import annotations

import asyncio
import csv
import json
import sys
import tempfile
from pathlib import Path

from websockets.asyncio.server import serve

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server_directory import PUBLIC_SERVERS_PATH, choose_browser_server_uri, load_public_servers, probe_public_servers


async def protocol_server(websocket) -> None:
    request = json.loads(await websocket.recv())
    if request.get("type") != "probe":
        return
    await websocket.send(json.dumps({
        "protocol": "PYMMO_DISCOVER_V1",
        "type": "server_info",
        "name": "Open Night Internet Test",
        "players": 2,
        "max_players": 30,
        "version": "2.5",
        "map_id": "map_001_gwb_corridor",
        "map_name": "Open Night Test Map",
        "port": 8080,
    }))


async def audit_probe() -> None:
    async with serve(protocol_server, "127.0.0.1", 0) as websocket_server:
        port = int(websocket_server.sockets[0].getsockname()[1])
        with tempfile.TemporaryDirectory(prefix="open_night_server_directory_") as temp_dir:
            config = Path(temp_dir) / "public_servers.csv"
            with config.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("enabled", "name", "uri"))
                writer.writerow(("true", "Local protocol test", f"ws://127.0.0.1:{port}"))
                writer.writerow(("false", "Disabled", "wss://disabled.invalid"))
                writer.writerow(("true", "Invalid", "https://not-a-websocket.invalid"))
            configured = load_public_servers(config)
            if len(configured) != 1:
                raise AssertionError(f"Expected one valid enabled endpoint, got {configured!r}")
            results = await probe_public_servers(configured, timeout=1.0)
            if len(results) != 1:
                raise AssertionError(f"Protocol probe did not detect the server: {results!r}")
            result = results[0]
            assert result["uri"] == f"ws://127.0.0.1:{port}"
            assert result["scope"] == "INTERNET"
            assert result["name"] == "Open Night Internet Test"
            assert result["players"] == 2 and result["max_players"] == 30
            assert result["port"] == port


def main() -> int:
    production = load_public_servers(PUBLIC_SERVERS_PATH)
    expected = "wss://open-night-production.up.railway.app"
    if [item["uri"] for item in production] != [expected]:
        raise SystemExit(f"Production Railway endpoint is missing or invalid: {production!r}")
    if choose_browser_server_uri("", "ws", "127.0.0.1", production) != expected:
        raise SystemExit("Browser default did not choose the configured Railway endpoint")
    if choose_browser_server_uri("wss://override.example/game", "ws", "127.0.0.1", production) != "wss://override.example/game":
        raise SystemExit("Full ?server= browser override did not win")
    if choose_browser_server_uri("192.168.1.5:9000", "ws", "127.0.0.1", production) != "ws://192.168.1.5:9000":
        raise SystemExit("Host-only ?server= browser override did not inherit page scheme")
    if choose_browser_server_uri("", "ws", "localhost", []) != "ws://localhost:8765":
        raise SystemExit("Browser localhost fallback is incorrect")
    asyncio.run(audit_probe())
    print("PUBLIC SERVER DISCOVERY AUDIT: PASS")
    print("Desktop protocol probe plus browser Railway default, override, and localhost fallback passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
