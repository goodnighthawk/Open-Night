from __future__ import annotations

import asyncio
import csv
import json
import time
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
PUBLIC_SERVERS_PATH = ROOT / "config" / "public_servers.csv"
TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def load_public_servers(path: Path = PUBLIC_SERVERS_PATH) -> list[dict]:
    """Load enabled, valid WebSocket endpoints from the public server CSV."""
    if not path.is_file():
        return []

    servers: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            enabled = str(row.get("enabled", "true")).strip().lower()
            if enabled not in TRUE_VALUES:
                continue
            uri = str(row.get("uri", "")).strip().rstrip("/")
            parsed = urlsplit(uri)
            if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
                continue
            external_port = parsed.port or (443 if parsed.scheme == "wss" else 80)
            servers.append({
                "uri": uri,
                "configured_name": str(row.get("name", "Open Night Internet Server")).strip()
                or "Open Night Internet Server",
                "host": parsed.hostname,
                "port": int(external_port),
                "scope": "INTERNET",
            })
    return servers


def choose_browser_server_uri(
    raw_server: str,
    page_scheme: str,
    page_host: str,
    public_servers: list[dict] | None = None,
) -> str:
    """Choose a Pygbag WebSocket target without desktop-only dependencies.

    An explicit ``?server=`` value always wins. Otherwise the first enabled
    configured public server is used, with the old page-host localhost behavior
    retained only as a fallback when no public endpoint is configured.
    """
    scheme = "wss" if str(page_scheme).strip().lower() == "wss" else "ws"
    override = str(raw_server).strip()
    if override:
        if override.lower().startswith(("ws://", "wss://")):
            return override
        return f"{scheme}://{override}"

    configured = load_public_servers() if public_servers is None else public_servers
    for server in configured:
        uri = str(server.get("uri", "")).strip()
        if uri.lower().startswith(("ws://", "wss://")):
            return uri

    host = str(page_host).strip() or "127.0.0.1"
    return f"{scheme}://{host}:8765"


async def probe_public_server(server: dict, timeout: float = 3.0) -> dict | None:
    """Return launcher metadata only when a configured WebSocket is reachable."""
    uri = str(server["uri"])
    try:
        # Imported lazily so the configuration/selection half of this module is
        # safe inside Pygbag, where browser-native WebSocket is used instead.
        from websockets.asyncio.client import connect

        async with connect(
            uri,
            open_timeout=timeout,
            close_timeout=0.25,
            ping_interval=None,
        ) as websocket:
            await websocket.send(json.dumps({"type": "probe"}, separators=(",", ":")))
            raw = await asyncio.wait_for(websocket.recv(), timeout=timeout)
        data = json.loads(raw)
        if data.get("type") != "server_info" or data.get("protocol") != "PYMMO_DISCOVER_V1":
            return None
        return {
            "uri": uri,
            "name": str(data.get("name") or server.get("configured_name") or "Open Night Internet Server"),
            "players": int(data.get("players", 0)),
            "max_players": int(data.get("max_players", 0)),
            "version": str(data.get("version", "dev")),
            "map_id": str(data.get("map_id", "map_001_gwb_corridor")),
            "map_name": str(data.get("map_name", "Open Night")),
            "game_mode_id": str(data.get("game_mode_id", "glorious_car_hijacker")),
            "game_mode_name": str(data.get("game_mode_name", "Glorious Car Hijacker")),
            "host": str(server["host"]),
            # Railway terminates TLS on 443. Never append the container's
            # internal $PORT value to the public WebSocket address.
            "port": int(server["port"]),
            "scope": "INTERNET",
            "last_seen": time.monotonic(),
        }
    except Exception:
        return None


async def probe_public_servers(servers: list[dict], timeout: float = 3.0) -> list[dict]:
    if not servers:
        return []
    results = await asyncio.gather(
        *(probe_public_server(server, timeout=timeout) for server in servers),
        return_exceptions=False,
    )
    return [server for server in results if server is not None]
