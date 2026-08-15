from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from versioning import GAME_VERSION
HOST = "127.0.0.1"
PORT = 8765
URI = f"ws://{HOST}:{PORT}"


def port_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((HOST, PORT)) == 0


async def websocket_probe(timeout: float = 1.5) -> tuple[bool, str]:
    try:
        from websockets.asyncio.client import connect
    except Exception:
        from websockets import connect
    try:
        async with asyncio.timeout(timeout):
            async with connect(URI, ping_interval=None) as ws:
                await ws.send(json.dumps({
                    "type": "hello", "name": "QuickProbe", "phone": "+15550000023",
                    "client_version": GAME_VERSION,
                }))
                while True:
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    kind = str(msg.get("type", ""))
                    if kind == "welcome":
                        return True, f"welcome from server v{msg.get('server_version', '?')} / {msg.get('map', {}).get('id', 'map')}"
                    if kind in {"fatal", "error"}:
                        return False, str(msg.get("text") or msg)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def new_console_flags() -> int:
    return int(getattr(subprocess, "CREATE_NEW_CONSOLE", 0)) if sys.platform.startswith("win") else 0


def launch_visible(cmd: list[str], *, label: str) -> subprocess.Popen:
    """Launch a child so Windows keeps its console open if Python exits with an error."""
    if sys.platform.startswith("win"):
        command = subprocess.list2cmdline(cmd)
        # /v:on lets us report the *child* exit code inside the failure block.
        wrapped = (
            f'{command} || ('
            f'set "ERR=!ERRORLEVEL!" & echo. & '
            f'echo [ERROR] {label} exited with code !ERR! & '
            f'echo The console is being kept open so the traceback can be read. & '
            f'pause & exit /b !ERR!)'
        )
        return subprocess.Popen(
            ["cmd.exe", "/d", "/v:on", "/c", wrapped],
            cwd=ROOT,
            creationflags=new_console_flags(),
        )
    return subprocess.Popen(cmd, cwd=ROOT)


def main() -> int:
    python = sys.executable
    if port_open():
        print(f"[ERROR] Port {PORT} is already in use.")
        print("Quick Local Test will not guess whether that process is the correct server.")
        print("Close the old server window, then run QUICK_LOCAL_TEST.bat again.")
        return 2

    server_cmd = [
        python, str(ROOT / "server.py"), "--memory-db", "--no-discovery",
        "--port", str(PORT), "--map", "map_001_gwb_corridor", "--traffic", "8",
    ]
    print("[1/3] Starting memory-DB server...")
    server = launch_visible(server_cmd, label="SERVER")

    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if port_open():
            break
        if server.poll() is not None:
            print(f"[ERROR] Server launcher exited early with code {server.returncode}.")
            print("The SERVER console should contain the Python traceback/error details.")
            return 3
        time.sleep(0.15)
    else:
        print(f"[ERROR] Server did not open port {PORT} within 15 seconds.")
        print("If the server crashed, its SERVER console has been kept open so you can read the traceback.")
        return 4

    print("[2/3] Verifying real WebSocket hello/welcome...")
    ok, detail = asyncio.run(websocket_probe())
    if not ok:
        print(f"[ERROR] TCP port opened, but the game protocol probe failed: {detail}")
        return 5
    print(f"[OK] {detail}")

    print("[3/3] Launching desktop client...")
    client_cmd = [python, str(ROOT / "client.py"), "--server", URI]
    launch_visible(client_cmd, label="CLIENT")
    print("[OK] Client launched only after server readiness was proven.")
    print("If the client crashes, its console will stay open and show the Python traceback.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        print("\n[FATAL] QUICK LOCAL TEST crashed unexpectedly.")
        print(f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        raise SystemExit(99)
