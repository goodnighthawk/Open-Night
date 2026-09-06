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
from common import get_map
from housing_spawn import house_login_state
from versioning import GAME_VERSION


def _available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.15)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _start_server(port: int) -> subprocess.Popen:
    proc = subprocess.Popen(
        [
            sys.executable, str(ROOT / "v100_server.py"), "--memory-db", "--no-discovery",
            "--port", str(port), "--traffic", "0", "--map", "map_001_gwb_corridor",
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
        if _port_open(port):
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


async def _recv_matching(ws, predicate, description: str, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=remaining))
        if message.get("type") in {"fatal", "error", "login_error"}:
            raise RuntimeError(str(message))
        if predicate(message):
            return message
    raise RuntimeError(f"timed out waiting for {description}")


def _nearby_account_pair() -> tuple[str, str]:
    """Pick deterministic accounts whose assigned apartment doors are nearby."""
    map_config = get_map()
    first_phone = "15556660001"
    first = house_login_state(map_config, first_phone, set())
    if first is None:
        raise RuntimeError("first roster-audit apartment was unavailable")
    for suffix in range(2, 200):
        second_phone = f"1555666{suffix:04d}"
        second = house_login_state(map_config, second_phone, {first[0]})
        if second is not None and math.hypot(first[1] - second[1], first[2] - second[2]) < 2800.0:
            return first_phone, second_phone
    raise RuntimeError("could not find two nearby deterministic apartment assignments")


async def _exercise_two_clients(port: int) -> None:
    try:
        from websockets.asyncio.client import connect
    except Exception:
        from websockets import connect

    uri = f"ws://127.0.0.1:{port}"
    first_phone, second_phone = _nearby_account_pair()
    async with connect(uri, ping_interval=None) as outdated:
        await outdated.send(json.dumps({
            "type": "hello", "name": "OldClient", "phone": "15556660000",
            "client_version": "0.0.0",
        }))
        rejected = await _recv_kind(outdated, "login_error")
        assert rejected.get("required_version") == GAME_VERSION
    async with connect(uri, ping_interval=None) as first, connect(uri, ping_interval=None) as second:
        await first.send(json.dumps({
            "type": "hello", "name": "MapFriendA", "phone": first_phone,
            "client_version": GAME_VERSION,
        }))
        welcome_a = await _recv_kind(first, "welcome")
        await second.send(json.dumps({
            "type": "hello", "name": "MapFriendB", "phone": second_phone,
            "client_version": GAME_VERSION,
        }))
        welcome_b = await _recv_kind(second, "welcome")
        expected = {str(welcome_a["id"]), str(welcome_b["id"])}
        apartment_a = str(welcome_a["account"]["apartment"]["interior_id"])
        apartment_b = str(welcome_b["account"]["apartment"]["interior_id"])
        assert apartment_a and apartment_b and apartment_a != apartment_b

        async def roster(ws) -> dict:
            deadline = time.monotonic() + 8.0
            while time.monotonic() < deadline:
                snapshot = await _recv_kind(ws, "snapshot", timeout=3.0)
                rows = snapshot.get("map_players")
                if isinstance(rows, list) and expected <= {str(row.get("id", "")) for row in rows if isinstance(row, dict)}:
                    return snapshot
            raise RuntimeError("global two-player map roster was not delivered")

        snapshot_a, snapshot_b = await asyncio.gather(roster(first), roster(second))
        for snapshot, own_id, own_apartment, other_id in (
            (snapshot_a, str(welcome_a["id"]), apartment_a, str(welcome_b["id"])),
            (snapshot_b, str(welcome_b["id"]), apartment_b, str(welcome_a["id"])),
        ):
            rows = snapshot["map_players"]
            for row in rows:
                if str(row.get("id", "")) in expected:
                    for key in ("name", "x", "y", "level"):
                        if key not in row:
                            raise RuntimeError(f"map marker missing {key}: {row}")
            markers = {str(row["id"]): row for row in rows if str(row.get("id", "")) in expected}
            assert markers[own_id].get("interior_id") == own_apartment
            assert not markers[other_id].get("interior_id"), "stranger apartment ID leaked through map roster"
            detailed_ids = {str(row.get("id", "")) for row in snapshot.get("players", [])}
            assert own_id in detailed_ids and other_id not in detailed_ids

        # Once both players exit their separate apartments, nearby movement and
        # rich snapshots must expose both outdoor avatars to both clients.
        await asyncio.gather(
            first.send(json.dumps({"type": "interior_exit"})),
            second.send(json.dumps({"type": "interior_exit"})),
        )
        await asyncio.gather(_recv_kind(first, "interior_state"), _recv_kind(second, "interior_state"))

        def outdoor_pair(message: dict) -> bool:
            if message.get("type") != "snapshot":
                return False
            detailed = {str(row.get("id", "")) for row in message.get("players", [])}
            markers = {
                str(row.get("id", "")): row for row in message.get("map_players", [])
                if isinstance(row, dict)
            }
            return expected <= detailed and expected <= set(markers) and all(
                not markers[player_id].get("interior_id") for player_id in expected
            )

        await asyncio.gather(
            _recv_matching(first, outdoor_pair, "first outdoor two-player snapshot", 10.0),
            _recv_matching(second, outdoor_pair, "second outdoor two-player snapshot", 10.0),
        )

        def movement_pair(message: dict) -> bool:
            return message.get("type") == "movement" and expected <= {
                str(row[0]) for row in message.get("p", [])
                if isinstance(row, (list, tuple)) and row
            }

        await asyncio.gather(
            _recv_matching(first, movement_pair, "first two-player movement stream"),
            _recv_matching(second, movement_pair, "second two-player movement stream"),
        )

        await first.send(json.dumps({"type": "sms_send", "target": "MapFriendB", "text": "network inbox"}))
        sent, received = await asyncio.gather(
            _recv_kind(first, "sms_sent"),
            _recv_kind(second, "sms_received"),
        )
        assert sent.get("text") == received.get("text") == "network inbox"

        # Disconnect removes the live marker but keeps the process-lifetime
        # apartment reservation. Reconnect always begins inside that same floor.
        await first.close()
        await _recv_matching(
            second,
            lambda message: message.get("type") == "snapshot"
            and int(message.get("server_population", 0)) == 1
            and all(str(row.get("id", "")) != str(welcome_a["id"])
                    for row in message.get("map_players", []) if isinstance(row, dict)),
            "disconnected player removal",
            10.0,
        )
        async with connect(uri, ping_interval=None) as returning:
            await returning.send(json.dumps({
                "type": "hello", "name": "MapFriendA", "phone": first_phone,
                "client_version": GAME_VERSION,
            }))
            reconnect_welcome = await _recv_kind(returning, "welcome")
            reconnect_apartment = reconnect_welcome["account"]["apartment"]
            assert reconnect_apartment["interior_id"] == apartment_a
            assert reconnect_welcome["player"]["interior_id"] == apartment_a
            reconnect_state = await _recv_kind(returning, "interior_state")
            assert reconnect_state.get("active") is True
            assert reconnect_state.get("interior_id") == apartment_a

            returning_id = str(reconnect_welcome["id"])
            separated = await _recv_matching(
                second,
                lambda message: message.get("type") == "snapshot"
                and any(str(row.get("id", "")) == returning_id
                        and not row.get("interior_id")
                        for row in message.get("map_players", []) if isinstance(row, dict))
                and all(str(row.get("id", "")) != returning_id
                        for row in message.get("players", []) if isinstance(row, dict)),
                "reconnected indoor player redaction",
                10.0,
            )
            assert int(separated.get("server_population", 0)) == 2


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

    port = _available_local_port()
    proc = _start_server(port)
    try:
        asyncio.run(_exercise_two_clients(port))
    finally:
        _stop(proc)

    print("MULTIPLAYER WORLD-MAP ROSTER AUDIT: PASS")
    print("  version rejection + indoor privacy + outdoor visibility + reconnect reservation + SMS verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
