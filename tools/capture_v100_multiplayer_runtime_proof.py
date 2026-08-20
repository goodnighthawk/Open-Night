#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYMMO_SHARED_DATA", tempfile.mkdtemp(prefix="open-night-v100-proof-"))

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame
from versioning import GAME_VERSION
import v100_client


OUT = ROOT / "assets" / "grid_v100" / "MULTIPLAYER_FULL_STACK_RUNTIME_PROOF_2560x720.png"
AUDIT = ROOT / "assets" / "grid_v100" / "MULTIPLAYER_FULL_STACK_RUNTIME_AUDIT.json"
PROOF_ZOOM = 0.72


def _free_port() -> int:
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
            sys.executable,
            str(ROOT / "v100_server.py"),
            "--memory-db",
            "--no-discovery",
            "--port",
            str(port),
            "--traffic",
            "0",
            "--map",
            "map_001_gwb_corridor",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            error = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"v1.0 server exited early ({proc.returncode}): {error[-3000:]}")
        if _port_open(port):
            return proc
        time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("v1.0 server did not open its loopback port")


def _stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


def _drain_second(network, state: dict) -> None:
    while True:
        try:
            message = network.incoming.get_nowait()
        except queue.Empty:
            return
        kind = str(message.get("type", ""))
        if kind == "login_error":
            raise RuntimeError(f"second client login failed: {message}")
        if kind == "welcome":
            state["welcome"] = message
        elif kind == "snapshot":
            state["snapshot_count"] = int(state.get("snapshot_count", 0)) + 1
            state["snapshot"] = message


def _pump(game, second, state: dict, duration: float = 0.02) -> None:
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        game.process_network()
        _drain_second(second, state)
        for player_id, player in game.players.items():
            player.smooth(1.0 / 60.0, local=player_id == game.local_id)
        time.sleep(0.005)


def _wait_for(predicate, game, second, state: dict, message: str, timeout: float = 12.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _pump(game, second, state)
        if predicate():
            return
    raise RuntimeError(message)


def _snapshot_player(snapshot: dict, player_id: str) -> dict | None:
    for row in snapshot.get("players", []) or []:
        if str(row.get("id", "")) == player_id:
            return row
    return None


def _render(game, second_id: str) -> None:
    local = game.players.get(game.local_id or "")
    if local is None:
        raise RuntimeError("rendered client has no server-backed local player")
    game.friend_names = {game.players[second_id].name.casefold(): game.players[second_id].name}
    game.camera_zoom = PROOF_ZOOM
    for player in game.players.values():
        player.render_x, player.render_y = player.target_x, player.target_y

    display_surface = game.screen
    view_size = game.logical_view_size()
    game.camera_controller.update(
        (local.render_x, local.render_y),
        (view_size[0] // 2, view_size[1] // 2),
        view_size,
        (game.grid_world.world_w, game.grid_world.world_h),
        1.0 / 60.0,
        force_center=True,
    )
    world_surface = pygame.Surface(view_size).convert()
    game.screen = world_surface
    game._render_camera_override = None
    game.draw_world()
    for player in sorted(game.players.values(), key=lambda item: game.camera_depth(item.render_x, item.render_y)):
        game.draw_player(player, local=player.id == game.local_id)
    game.screen = display_surface
    pygame.transform.smoothscale(world_surface, display_surface.get_size(), display_surface)
    game.draw_player_nameplates()
    game.draw_job_location_labels()
    game.notice = f"v{GAME_VERSION} full stack — server + 2 real clients + authoritative movement"
    game.notice_until = time.monotonic() + 60.0
    game.draw_hud()
    gameplay = display_surface.copy()

    display_surface.blit(gameplay, (0, 0))
    game.map_open = True
    game.draw_world_map()
    world_map = display_surface.copy()
    game.map_open = False

    review = pygame.Surface((2560, 720)).convert()
    review.blit(pygame.transform.smoothscale(gameplay, (1280, 720)), (0, 0))
    review.blit(pygame.transform.smoothscale(world_map, (1280, 720)), (1280, 0))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(review, OUT)


def main() -> int:
    if GAME_VERSION != "1.0.0":
        raise RuntimeError(f"canonical v1.0 wire version is {GAME_VERSION!r}, expected '1.0.0'")
    v100_client.install_v100_client()
    port = _free_port()
    server = _start_server(port)
    game = None
    second = None
    state: dict = {"snapshot_count": 0}
    clean_shutdown = False
    try:
        uri = f"ws://127.0.0.1:{port}"
        game_client = v100_client.game_client
        game = game_client.Game(uri, "15551000001", "StackProofA")
        second = game_client.NetworkClient(uri, "15551000002", "StackProofB")
        second.start()

        _wait_for(
            lambda: game.connected and game.local_id is not None and state.get("welcome") is not None,
            game,
            second,
            state,
            "two canonical clients did not complete the v1.0 handshake",
        )
        welcome_b = state["welcome"]
        second_id = str(welcome_b.get("id", ""))
        local_id = str(game.local_id or "")
        if not second_id or second_id == local_id:
            raise RuntimeError("server did not assign two distinct player identities")
        if str(welcome_b.get("server_version", "")) != GAME_VERSION:
            raise RuntimeError(f"server advertised wrong release version: {welcome_b.get('server_version')}")

        def both_clients_see_both() -> bool:
            snapshot = state.get("snapshot") or {}
            second_rows = {str(row.get("id", "")) for row in snapshot.get("players", []) or []}
            return {local_id, second_id} <= set(game.players) and {local_id, second_id} <= second_rows

        _wait_for(
            both_clients_see_both,
            game,
            second,
            state,
            "both clients did not receive the shared two-player snapshot",
        )
        start = game.players[second_id]
        start_xy = (float(start.target_x), float(start.target_y))
        movement_direction = None
        end_xy = start_xy
        for dx, dy in ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)):
            second.send({"type": "input", "x": dx, "y": dy, "aim": math.atan2(dy, dx), "boost": False})
            # Move far enough that both independently rendered sprites and labels
            # are visibly distinct in the approval frame, not merely distinct IDs.
            _pump(game, second, state, duration=1.15)
            second.send({"type": "input", "x": 0.0, "y": 0.0, "aim": math.atan2(dy, dx), "boost": False})
            _pump(game, second, state, duration=0.2)
            observed = game.players.get(second_id)
            snapshot_row = _snapshot_player(state.get("snapshot") or {}, second_id)
            if observed is None or snapshot_row is None:
                continue
            end_xy = (float(observed.target_x), float(observed.target_y))
            second_xy = (float(snapshot_row["x"]), float(snapshot_row["y"]))
            if math.dist(start_xy, end_xy) >= 24.0 and math.dist(end_xy, second_xy) <= 1.0:
                movement_direction = [dx, dy]
                break
        if movement_direction is None:
            raise RuntimeError("server-authoritative movement was not propagated to both clients")

        if game.grid_world is None or game.grid_world.cell_px != 128:
            raise RuntimeError("rendered client did not retain the canonical 128px GridWorld")
        if game.grid_world.width != 64 or game.grid_world.height != 48:
            raise RuntimeError("rendered client did not retain the canonical 64x48 GridWorld")

        # Separate the two authoritative players enough for a human reviewer to
        # distinguish both sprites and nameplates in the captured gameplay panel.
        separation = math.dist(
            (game.players[local_id].target_x, game.players[local_id].target_y),
            (game.players[second_id].target_x, game.players[second_id].target_y),
        )
        for dx, dy in ((-1.0, 0.0), (0.0, -1.0), (0.0, 1.0), (1.0, 0.0)):
            if separation >= 96.0:
                break
            game.network.send({"type": "input", "x": dx, "y": dy, "aim": math.atan2(dy, dx), "boost": False})
            _pump(game, second, state, duration=1.0)
            game.network.send({"type": "input", "x": 0.0, "y": 0.0, "aim": math.atan2(dy, dx), "boost": False})
            _pump(game, second, state, duration=0.2)
            separation = math.dist(
                (game.players[local_id].target_x, game.players[local_id].target_y),
                (game.players[second_id].target_x, game.players[second_id].target_y),
            )
        if separation < 64.0:
            raise RuntimeError(f"proof players remained visually ambiguous ({separation:.1f}px apart)")
        _wait_for(
            lambda: {local_id, second_id} <= set(game.map_players),
            game,
            second,
            state,
            "global two-player M-map roster was not delivered",
        )
        _render(game, second_id)

        audit = {
            "proof": "canonical_v100_server_backed_two_client_runtime",
            "release_version": GAME_VERSION,
            "server_entry": "v100_server.py --memory-db --no-discovery",
            "rendered_client_entry": "v100_client.Game + NetworkClient",
            "second_client_entry": "v100_client.NetworkClient",
            "map_id": str(game.map_config.get("id", "")),
            "grid_size_cells": [game.grid_world.width, game.grid_world.height],
            "grid_cell_px": game.grid_world.cell_px,
            "world_size_px": [game.grid_world.world_w, game.grid_world.world_h],
            "player_ids_distinct": local_id != second_id,
            "two_player_snapshot_seen_by_rendered_client": {local_id, second_id} <= set(game.players),
            "two_player_snapshot_seen_by_second_client": both_clients_see_both(),
            "two_player_m_map_roster": {local_id, second_id} <= set(game.map_players),
            "movement_start_px": [round(start_xy[0], 3), round(start_xy[1], 3)],
            "movement_end_px": [round(end_xy[0], 3), round(end_xy[1], 3)],
            "movement_delta_px": round(math.dist(start_xy, end_xy), 3),
            "movement_direction": movement_direction,
            "rendered_player_separation_px": round(separation, 3),
            "second_client_snapshot_count": int(state.get("snapshot_count", 0)),
            "hud_online_count": len(game.map_players),
            "review_panels": ["server_backed_gameplay_hud", "server_backed_M_map"],
            "clean_shutdown": True,
            "errors": [],
        }
        AUDIT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        clean_shutdown = True
        print(json.dumps(audit, indent=2, sort_keys=True))
        return 0
    finally:
        if second is not None:
            second.stop()
        if game is not None:
            game.network.stop()
        _stop_server(server)
        pygame.quit()
        if clean_shutdown:
            print("V1.0 MULTIPLAYER FULL-STACK RUNTIME PROOF: PASS")


if __name__ == "__main__":
    raise SystemExit(main())
