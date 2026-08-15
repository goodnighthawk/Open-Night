from __future__ import annotations

import asyncio
import json
import math
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mapfiles.loader import load_map_folder

MAP_DIR = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"
PORTABLE = ROOT / "dev_tools" / "map_generator" / "exports" / "Map_001_GWB.map"


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.15)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def start_server(port: int, portable: bool = False) -> subprocess.Popen:
    cmd = [
        sys.executable, str(ROOT / "server.py"), "--memory-db", "--no-discovery",
        "--port", str(port), "--traffic", "0",
    ]
    if portable:
        cmd += ["--map-file", str(PORTABLE)]
    else:
        cmd += ["--map", "map_001_gwb_corridor"]
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 18.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            err = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"server exited early ({proc.returncode}): {err[-2000:]}")
        if port_open(port):
            return proc
        time.sleep(0.1)
    proc.terminate()
    raise RuntimeError(f"server did not open port {port}")


async def hello_probe(port: int, portable: bool = False) -> tuple[list[str], dict]:
    try:
        from websockets.asyncio.client import connect
    except Exception:
        from websockets import connect
    uri = f"ws://127.0.0.1:{port}"
    types: list[str] = []
    welcome = None
    async with connect(uri, ping_interval=None, max_size=8 * 1024 * 1024) as ws:
        await ws.send(json.dumps({
            "type": "hello", "name": "Pass38", "phone": f"+1555000{port}",
            "client_version": "0.8.0",
            "map_cache_hashes": [],
        }))
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            msg = json.loads(raw)
            kind = str(msg.get("type", ""))
            types.append(kind)
            if kind == "welcome":
                welcome = msg
                break
            if kind in {"fatal", "error", "login_error"}:
                raise RuntimeError(str(msg))
    if welcome is None:
        raise RuntimeError(f"no welcome; messages={types}")
    if portable:
        for required in ("map_transfer_begin", "map_transfer_end", "welcome"):
            if required not in types:
                raise RuntimeError(f"portable transfer missing {required}: {types}")
    return types, welcome


def point_rect_distance(px: float, py: float, rect: list[float]) -> float:
    x, y, w, h = map(float, rect)
    dx = max(x - px, 0.0, px - (x + w))
    dy = max(y - py, 0.0, py - (y + h))
    return math.hypot(dx, dy)


def interior_gate(m: dict) -> None:
    interiors = m.get("interiors", []) or []
    buildings = m.get("buildings", []) or []
    if len(interiors) != 10:
        raise RuntimeError(f"expected 10 enterable locations, found {len(interiors)}")
    worst = 0.0
    for room in interiors:
        p = room.get("entry", [0, 0])
        x, y = float(p[0]), float(p[1])
        d = min(point_rect_distance(x, y, b) for b in buildings)
        worst = max(worst, d)
        if d > 28.0:
            raise RuntimeError(f"interior {room.get('id')} entry is {d:.1f}px from nearest building frontage")
    print(f"interior gate: 10/10 entries near building frontages (worst {worst:.1f}px)")


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=2)


def main() -> int:
    m = load_map_folder(MAP_DIR)
    interior_gate(m)

    p1 = start_server(8876, portable=False)
    try:
        types, welcome = asyncio.run(hello_probe(8876, portable=False))
        player = welcome.get("player", {})
        netmap = welcome.get("map", {})
        if int(player.get("level", -99)) != 0:
            raise RuntimeError(f"default server spawn did not publish Level 0: {player}")
        if int(netmap.get("chunk_cols", 0)) != 16 or int(netmap.get("chunk_rows", 0)) != 12:
            raise RuntimeError(f"server did not load polished 16x12 default map: {netmap}")
        print(f"default server handshake: PASS messages={types} level={player.get('level')} map={netmap.get('chunk_cols')}x{netmap.get('chunk_rows')}")
    finally:
        stop(p1)

    p2 = start_server(8877, portable=True)
    try:
        types, welcome = asyncio.run(hello_probe(8877, portable=True))
        player = welcome.get("player", {})
        netmap = welcome.get("map", {})
        if int(player.get("level", -99)) != 0:
            raise RuntimeError("portable server welcome lost player level")
        if str(netmap.get("map_payload_mode", "")) != "portable_map_v1":
            raise RuntimeError(f"portable server payload mode wrong: {netmap.get('map_payload_mode')}")
        chunks = sum(1 for t in types if t == "map_transfer_chunk")
        print(f"portable server transfer: PASS chunks={chunks} mode={netmap.get('map_payload_mode')}")
    finally:
        stop(p2)

    print("PASS 38 PLAYABILITY SMOKE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
