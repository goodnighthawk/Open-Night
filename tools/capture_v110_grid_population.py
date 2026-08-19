#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame
import v100_runtime_refinement
import v100_safe_layout
v100_safe_layout.install(v100_runtime_refinement)
v100_runtime_refinement.install()
import v100_scale_normalization
v100_scale_normalization.install()

import server
import v100_client
import v110_grid_population

OUT = ROOT / "assets" / "grid_v100" / "V110_POPULATION_RUNTIME_PROOF_1280x720.png"
REVIEW = ROOT / "assets" / "grid_v100" / "V110_FULL_STACK_RUNTIME_REVIEW_2560x1440.png"
AUDIT = ROOT / "assets" / "grid_v100" / "V110_GRID_POPULATION_RUNTIME_AUDIT.json"
PROOF_ZOOM = 0.72
PROOF_TRAFFIC = 24


def _distance(a, b) -> float:
    return math.hypot(float(a.x) - float(b.x), float(a.y) - float(b.y))


def main() -> None:
    game_client = v100_client.game_client
    game_client.NetworkClient.start = lambda self: None
    v100_client.install_v100_client()
    game = game_client.Game("ws://v110-runtime-proof.invalid:8765", "5550000110", "V110Proof")
    if game.grid_world is None or game.grid_renderer is None:
        raise RuntimeError("v1.1 population proof requires the canonical GridWorld client")

    server.ACTIVE_MAP = game.map_config
    server.ACTIVE_MAP_ID = str(game.map_config.get("id", server.ACTIVE_MAP_ID))
    server.GRID_WORLD = game.grid_world
    server.GRID_RUNTIME_ACTIVE = True
    server.TRAFFIC_COUNT = PROOF_TRAFFIC
    audit = v110_grid_population.prepare_and_initialize(server, server.ACTIVE_MAP, server.GRID_WORLD)

    initial_car_positions = {car.vehicle_id: (car.x, car.y) for car in server.traffic_vehicles}
    initial_npc_positions = {npc.npc_id: (npc.x, npc.y) for npc in server.npc_pedestrians}
    dt = 1.0 / 60.0
    for tick in range(150):
        server.update_traffic(dt, [], tick * dt)
        server.update_npcs(dt, [], tick)

    moved_cars = sum(
        math.hypot(car.x - initial_car_positions[car.vehicle_id][0], car.y - initial_car_positions[car.vehicle_id][1]) > 8.0
        for car in server.traffic_vehicles
        if car.vehicle_id in initial_car_positions
    )
    moved_npcs = sum(
        math.hypot(npc.x - initial_npc_positions[npc.npc_id][0], npc.y - initial_npc_positions[npc.npc_id][1]) > 4.0
        for npc in server.npc_pedestrians
        if npc.npc_id in initial_npc_positions
    )
    blocked_cars = [
        car.vehicle_id for car in server.traffic_vehicles
        if v110_grid_population._grid_vehicle_blocked(game.grid_world, car, car.x, car.y, car.angle)
    ]
    if len(server.traffic_vehicles) < 6:
        raise RuntimeError(f"v1.1 proof expected at least six safe traffic cars, got {len(server.traffic_vehicles)}")
    if sum(1 for npc in server.npc_pedestrians if npc.kind == "pedestrian") < 12:
        raise RuntimeError("v1.1 proof expected at least twelve pedestrians")
    if moved_cars < max(3, len(server.traffic_vehicles) // 3):
        raise RuntimeError(f"too few traffic cars moved during proof: {moved_cars}/{len(server.traffic_vehicles)}")
    if moved_npcs < 8:
        raise RuntimeError(f"too few NPCs moved during proof: {moved_npcs}")
    if blocked_cars:
        raise RuntimeError(f"traffic left GridWorld road collision: {blocked_cars[:8]}")

    game.vehicles = {
        car.vehicle_id: game_client.RemoteVehicle(car.public_dict())
        for car in server.traffic_vehicles
    }
    game.npcs = {
        npc.npc_id: game_client.RemoteNPC(npc.public_dict())
        for npc in server.npc_pedestrians
    }

    # Frame the densest useful road/sidewalk pair so the proof necessarily shows
    # both systems rather than choosing an arbitrary login spawn far from traffic.
    cars = list(server.traffic_vehicles)
    pedestrians = [npc for npc in server.npc_pedestrians if npc.kind == "pedestrian"]
    pair = min(((_distance(car, npc), car, npc) for car in cars for npc in pedestrians), key=lambda row: row[0])
    _, focus_car, focus_npc = pair
    focus_x = (focus_car.x + focus_npc.x) * 0.5
    focus_y = (focus_car.y + focus_npc.y) * 0.5
    x, y = game.grid_world.nearest_walkable("ground", focus_x, focus_y, game_client.PLAYER_RADIUS)
    local = game_client.RemotePlayer({
        "id": "v110-proof-local", "name": "V110Proof", "x": x, "y": y,
        "aim": -math.pi / 2.0, "cash": 420, "packages": 2,
        "level": 0, "pose": "idle", "appearance": None,
    })
    game.local_id = local.id
    game.players = {local.id: local}
    game.map_players = {local.id: {"id": local.id, "name": local.name, "x": x, "y": y, "level": 0}}
    game.notice = (
        f"v1.1 GridWorld population proof — {len(game.vehicles)} traffic cars • "
        f"{len(game.npcs)} ambient NPCs"
    )
    game.notice_until = 10**12
    game.camera_zoom = PROOF_ZOOM

    display_surface = game.screen
    view_size = game.logical_view_size()
    game.camera_controller.update(
        (x, y), (view_size[0] // 2, view_size[1] // 2), view_size,
        (game.grid_world.world_w, game.grid_world.world_h), dt, force_center=True,
    )
    world_surface = pygame.Surface(view_size).convert()
    game.screen = world_surface
    game._render_camera_override = None
    game.draw_world()

    drawables = []
    drawables.extend((game.camera_depth(car.render_x, car.render_y), "car", car) for car in game.vehicles.values())
    drawables.extend((game.camera_depth(npc.render_x, npc.render_y), "npc", npc) for npc in game.npcs.values())
    drawables.append((game.camera_depth(local.render_x, local.render_y), "player", local))
    for _, kind, obj in sorted(drawables, key=lambda row: row[0]):
        if kind == "car":
            game.draw_vehicle(obj)
        elif kind == "npc":
            game.draw_npc(obj)
        else:
            game.draw_player(obj, True)

    game.screen = display_surface
    pygame.transform.smoothscale(world_surface, display_surface.get_size(), display_surface)
    game.draw_player_nameplates()
    game.draw_job_location_labels()
    game.draw_hud()
    pop_label = game.tiny_font.render(
        f"GRID POPULATION  cars {len(game.vehicles)}  npcs {len(game.npcs)}  zoom {PROOF_ZOOM:.2f}x",
        True, game_client.MUTED_TEXT,
    )
    game.screen.blit(pop_label, (game.screen.get_width() - pop_label.get_width() - 18, 48))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    gameplay_frame = game.screen.copy()
    pygame.image.save(gameplay_frame, OUT)

    game.screen.blit(gameplay_frame, (0, 0))
    game.map_open = True
    game.draw_world_map()
    mmap_frame = game.screen.copy()
    game.map_open = False

    raw_overview = pygame.Surface((2560, 1440)).convert()
    game.grid_renderer.draw_overview(raw_overview, "ground")
    review = pygame.Surface((2560, 1440)).convert()
    review.fill((12, 12, 14))
    review.blit(pygame.transform.smoothscale(gameplay_frame, (1280, 720)), (0, 0))
    review.blit(pygame.transform.smoothscale(mmap_frame, (1280, 720)), (1280, 0))
    review.blit(pygame.transform.smoothscale(raw_overview, (2560, 720)), (0, 720))
    pygame.image.save(review, REVIEW)

    audit.update({
        "proof": "v110_grid_native_population_full_stack",
        "camera_zoom": PROOF_ZOOM,
        "traffic_moved_after_2_5s": moved_cars,
        "npcs_moved_after_2_5s": moved_npcs,
        "blocked_traffic_after_2_5s": blocked_cars,
        "focus_car": focus_car.vehicle_id,
        "focus_npc": focus_npc.npc_id,
        "player_cell": list(game.grid_world.world_to_cell(x, y)),
        "full_stack_panels": ["gameplay_player_hud_population", "actual_M_map", "authoritative_ground_overview"],
    })
    AUDIT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, sort_keys=True))
    pygame.quit()


if __name__ == "__main__":
    main()
