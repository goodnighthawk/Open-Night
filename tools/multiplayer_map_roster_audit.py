from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from versioning import GAME_VERSION
PORT = 8878


def _port_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.15)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def _start_server() -> subprocess.Popen:
    proc = subprocess.Popen(
        [
<<<<<<< Updated upstream
            sys.executable, str(ROOT / "server.py"), "--memory-db", "--no-discovery",
            "--port", str(PORT), "--traffic", "0", "--map", "map_001_gwb_corridor",
=======
            sys.executable, str(ROOT / "v100_server.py"), "--memory-db", "--no-discovery",
            "--port", str(port), "--traffic", "0", "--map", "map_001_gwb_corridor",
>>>>>>> Stashed changes
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 18.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            error = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"server exited early ({proc.returncode}): {error[-2000:]}")
        if _port_open():
            return proc
        time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("multiplayer roster audit server did not start")


async def _recv_kind(ws, kind: str, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        if message.get("type") == kind:
            return message
        if message.get("type") in {"fatal", "error", "login_error"}:
            raise RuntimeError(str(message))
    raise RuntimeError(f"timed out waiting for {kind}")


async def _exercise_two_clients() -> None:
    try:
        from websockets.asyncio.client import connect
    except Exception:
        from websockets import connect

    uri = f"ws://127.0.0.1:{PORT}"
    async with connect(uri, ping_interval=None) as outdated:
        await outdated.send(json.dumps({
            "type": "hello", "name": "OldClient", "phone": "15556660000",
            "client_version": "0.0.0",
        }))
        rejected = await _recv_kind(outdated, "login_error")
        assert rejected.get("required_version") == GAME_VERSION
    async with connect(uri, ping_interval=None) as first, connect(uri, ping_interval=None) as second:
        await first.send(json.dumps({
            "type": "hello", "name": "MapFriendA", "phone": "15556660001",
            "client_version": GAME_VERSION,
        }))
        welcome_a = await _recv_kind(first, "welcome")
        await second.send(json.dumps({
            "type": "hello", "name": "MapFriendB", "phone": "15556660002",
            "client_version": GAME_VERSION,
        }))
        welcome_b = await _recv_kind(second, "welcome")
        expected = {str(welcome_a["id"]), str(welcome_b["id"])}

        async def roster(ws) -> dict:
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                snapshot = await _recv_kind(ws, "snapshot", timeout=3.0)
                rows = snapshot.get("map_players")
                if isinstance(rows, list) and expected <= {str(row.get("id", "")) for row in rows if isinstance(row, dict)}:
                    return snapshot
            raise RuntimeError("global two-player map roster was not delivered")

        snapshot_a, snapshot_b = await asyncio.gather(roster(first), roster(second))
        for snapshot in (snapshot_a, snapshot_b):
            rows = snapshot["map_players"]
            for row in rows:
                if str(row.get("id", "")) in expected:
                    for key in ("name", "x", "y", "level"):
                        if key not in row:
                            raise RuntimeError(f"map marker missing {key}: {row}")

        await first.send(json.dumps({"type": "sms_send", "target": "MapFriendB", "text": "network inbox"}))
        sent, received = await asyncio.gather(
            _recv_kind(first, "sms_sent"),
            _recv_kind(second, "sms_received"),
        )
        assert sent.get("text") == received.get("text") == "network inbox"


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


def main() -> int:
    server_source = (ROOT / "server.py").read_text(encoding="utf-8")
    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    assert 'payload["map_players"] = map_players' in server_source
    assert "client version mismatch" in server_source
    assert "for pid, marker in self.map_players.items()" in client_source
    assert "green: friends" in client_source

    proc = _start_server()
    try:
        asyncio.run(_exercise_two_clients())
    finally:
        _stop(proc)

    print("MULTIPLAYER WORLD-MAP ROSTER AUDIT: PASS")
    print("  old client rejected; matching clients received stable markers and live persisted SMS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
