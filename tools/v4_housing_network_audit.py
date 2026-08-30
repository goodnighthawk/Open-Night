from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import socket
import subprocess
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common import get_map
from housing_spawn import blank_house_interiors
from portable_paths import ensure_shared_layout
from versioning import GAME_VERSION
from websockets.asyncio.client import connect


def available_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def wait_for_server(port: int, process: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"housing audit server exited with code {process.returncode}")
        try:
            async with connect(
                f"ws://127.0.0.1:{port}", open_timeout=1.0, close_timeout=0.2
            ):
                return
        except Exception:
            await asyncio.sleep(0.1)
    raise TimeoutError("housing audit server did not open its WebSocket port")


async def receive_matching(ws, predicate, description: str, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(0.05, deadline - time.monotonic())
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        try:
            message = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if message.get("type") == "login_error":
            raise RuntimeError(str(message))
        if predicate(message):
            return message
    raise TimeoutError(f"timed out waiting for {description}")


async def receive_kind(ws, kind: str, timeout: float = 8.0) -> dict:
    return await receive_matching(
        ws, lambda message: message.get("type") == kind, kind, timeout
    )


def directory_names(snapshot: dict) -> set[str]:
    rows = snapshot.get("apartment_directory", [])
    return {
        str(row.get("resident_name", ""))
        for row in rows
        if isinstance(row, dict) and str(row.get("resident_name", ""))
    }


async def exercise_housing(uri: str) -> dict:
    names = [f"Housing{i:02d}" for i in range(1, 16)]
    welcomes: list[dict] = []
    sockets = []
    assigned: dict[str, str] = {}

    async with AsyncExitStack() as stack:
        for index, name in enumerate(names, start=1):
            ws = await stack.enter_async_context(
                connect(uri, ping_interval=None, open_timeout=8, close_timeout=0.2)
            )
            sockets.append(ws)
            await ws.send(json.dumps({
                "type": "hello",
                "name": name,
                "phone": f"556{index:07d}",
                "client_version": GAME_VERSION,
            }))
            welcome = await receive_kind(ws, "welcome")
            welcomes.append(welcome)
            assert int(welcome["housing_capacity"]) == 14
            assert int(welcome["server_population"]) == index
            player = welcome.get("player", {})
            apartment = welcome.get("account", {}).get("apartment")
            if index <= 14:
                assert isinstance(apartment, dict), f"player {index} did not receive an apartment"
                interior_id = str(apartment.get("interior_id", ""))
                assert interior_id and interior_id not in assigned
                assert str(player.get("interior_id", "")) == interior_id
                assert int(apartment.get("floor", 0)) == 1
                assert apartment.get("label") == f"1st Floor - {name}'s Apartment"
                assigned[interior_id] = name
                state = await receive_kind(ws, "interior_state")
                assert state.get("active") is True and state.get("interior_id") == interior_id
            else:
                assert apartment is None
                assert not str(player.get("interior_id", ""))
                assert int(welcome.get("housing_overflow", 0)) == 1

        assert len(assigned) == 14
        overflow_ws = sockets[14]
        overflow_welcome = welcomes[14]
        overflow_notice = await receive_matching(
            overflow_ws,
            lambda message: message.get("type") == "notice" and "Housing is full" in str(message.get("text", "")),
            "housing-full overflow notice",
        )
        assert "15/14" in str(overflow_notice.get("text", ""))

        houses = blank_house_interiors(get_map())
        overflow_player = overflow_welcome["player"]
        overflow_x = float(overflow_player["x"])
        overflow_y = float(overflow_player["y"])
        overflow_house = next(
            house for house in houses
            if math.hypot(float(house["entry"][0]) - overflow_x, float(house["entry"][1]) - overflow_y) < 0.01
        )
        buzzer_resident = assigned[str(overflow_house["id"])]

        population_snapshot = await receive_matching(
            overflow_ws,
            lambda message: message.get("type") == "snapshot"
            and int(message.get("server_population", 0)) == 15
            and int(message.get("housing_overflow", 0)) == 1,
            "15/14 population snapshot",
        )
        assert int(population_snapshot["housing_capacity"]) == 14

        self_snapshot = await receive_matching(
            sockets[0],
            lambda message: message.get("type") == "snapshot" and names[0] in directory_names(message),
            "resident self directory",
        )
        self_rows = [
            row for row in self_snapshot["apartment_directory"]
            if row.get("resident_name") == names[0]
        ]
        assert self_rows[0]["label"] == f"1st Floor - {names[0]}'s Apartment"

        # One-sided local friend saves must reveal nothing.
        await sockets[2].send(json.dumps({"type": "friend_sync", "names": [names[0]]}))
        one_sided = await receive_matching(
            sockets[2],
            lambda message: message.get("type") == "snapshot" and "apartment_directory" in message,
            "one-sided friend directory",
            timeout=10.0,
        )
        assert names[0] not in directory_names(one_sided)
        assert names[0] not in set(one_sided.get("mutual_friends", []))

        # Reciprocal online saves establish a mutual friendship for v4.0.
        await sockets[0].send(json.dumps({"type": "friend_sync", "names": [names[1]]}))
        await sockets[1].send(json.dumps({"type": "friend_sync", "names": [names[0]]}))
        mutual = await receive_matching(
            sockets[0],
            lambda message: message.get("type") == "snapshot"
            and names[1] in directory_names(message)
            and names[1] in set(message.get("mutual_friends", [])),
            "mutual-friend directory",
            timeout=10.0,
        )
        assert {names[0], names[1]} <= directory_names(mutual)

        # The overflow player has no friend relationship but stands exactly at a
        # randomly selected apartment buzzer, so only that local listing appears.
        buzzer = await receive_matching(
            overflow_ws,
            lambda message: message.get("type") == "snapshot"
            and buzzer_resident in directory_names(message),
            "buzzer-local directory",
            timeout=10.0,
        )
        assert buzzer_resident in directory_names(buzzer)
        distant_resident = next(name for name in assigned.values() if name != buzzer_resident)
        assert distant_resident not in directory_names(buzzer)

        # Exit and re-enter the assigned room through the authoritative doorway.
        first_id = str(welcomes[0]["account"]["apartment"]["interior_id"])
        await sockets[0].send(json.dumps({"type": "interior_exit"}))
        exited = await receive_matching(
            sockets[0],
            lambda message: message.get("type") == "interior_state" and not message.get("active"),
            "apartment exit",
        )
        assert exited.get("interior_id") == ""
        first_player_id = str(welcomes[0]["id"])
        exterior_snapshot = await receive_matching(
            sockets[0],
            lambda message: message.get("type") == "snapshot" and any(
                str(row.get("id", "")) == first_player_id
                and not str(row.get("interior_id", ""))
                for row in message.get("players", []) if isinstance(row, dict)
            ),
            "apartment exterior position",
        )
        exterior_row = next(
            row for row in exterior_snapshot["players"]
            if str(row.get("id", "")) == first_player_id
        )
        assert math.hypot(
            float(exterior_row["x"]) - float(welcomes[0]["player"]["x"]),
            float(exterior_row["y"]) - float(welcomes[0]["player"]["y"]),
        ) < 0.01
        await sockets[0].send(json.dumps({"type": "interior_enter", "interior_id": first_id}))
        reentered = await receive_matching(
            sockets[0],
            lambda message: message.get("type") == "interior_state" and message.get("active"),
            "apartment re-entry",
        )
        assert reentered.get("interior_id") == first_id

        return {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "connected_players": 15,
            "distinct_apartments": len(assigned),
            "housing_capacity": 14,
            "overflow_players": 1,
            "overflow_house": str(overflow_house["id"]),
            "self_directory": "PASS",
            "one_sided_privacy": "PASS",
            "mutual_friend_directory": "PASS",
            "buzzer_directory": "PASS",
            "exit_reentry": "PASS",
            "result": "PASS",
        }


async def run_audit() -> int:
    port = available_local_port()
    shared = ensure_shared_layout()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = shared["stress_results"] / f"v4_housing_{stamp}.csv"
    server_log = shared["stress_results"] / f"v4_housing_server_{stamp}.log"
    command = [
        sys.executable, "-u", str(ROOT / "server.py"),
        "--host", "127.0.0.1", "--port", str(port),
        "--name", "Open Night v4 Housing Audit",
        "--max-players", "64", "--traffic", "0",
        "--memory-db", "--no-discovery",
    ]
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    print(f"Starting isolated housing server on ws://127.0.0.1:{port}")
    with server_log.open("w", encoding="utf-8") as log_handle:
        process = subprocess.Popen(
            command, cwd=ROOT, env=environment,
            stdout=log_handle, stderr=subprocess.STDOUT, text=True,
        )
        try:
            await wait_for_server(port, process)
            result = await exercise_housing(f"ws://127.0.0.1:{port}")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    await asyncio.to_thread(process.wait, 5.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    await asyncio.to_thread(process.wait, 5.0)

    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result))
        writer.writeheader()
        writer.writerow(result)
    print("V4 HOUSING NETWORK AUDIT: PASS")
    print("  14 private first floors + player 15 overflow + privacy/buzzer + exit/re-entry verified")
    print(f"Report: {report_path}")
    print(f"Server log: {server_log}")
    return 0


def main() -> int:
    argparse.ArgumentParser(
        description="Run the isolated Open Night v4 15-player housing network audit"
    ).parse_args()
    return asyncio.run(run_audit())


if __name__ == "__main__":
    raise SystemExit(main())
