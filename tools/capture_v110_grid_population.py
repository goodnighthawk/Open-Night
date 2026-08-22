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
from versioning import GAME_VERSION
import v110_pedestrian_flow
import v110_vehicle_proportions
v110_pedestrian_flow.install(v110_grid_population)
v110_vehicle_proportions.install(server)

OUT = ROOT / "assets" / "grid_v100" / "V110_POPULATION_RUNTIME_PROOF_1280x720.png"
REVIEW = ROOT / "assets" / "grid_v100" / "V110_FULL_STACK_RUNTIME_REVIEW_2560x1440.png"
AUDIT = ROOT / "assets" / "grid_v100" / "V110_GRID_POPULATION_RUNTIME_AUDIT.json"
PROOF_ZOOM = 0.72
PROOF_TRAFFIC = 24
FLOW_WARMUP_TICKS = 300
FLOW_MEASURE_TICKS = 300
MIN_FLOW_DISTANCE_5S = 20.0
MIN_CLIENT_CAR_LENGTH_PX = 74.0
MIN_COLLISION_TO_VISUAL_RATIO = 0.78


def _distance(a, b) -> float:
    return math.hypot(float(a.x) - float(b.x), float(a.y) - float(b.y))


def _advance_population(
    dt: float,
    tick_start: int,
    tick_stop: int,
    *,
    track_pedestrians: bool = False,
    signal_waits: dict[str, float] | None = None,
) -> dict[str, float]:
    travelled: dict[str, float] = {}
    for tick in range(tick_start, tick_stop):
        before = {
            npc.npc_id: (float(npc.x), float(npc.y))
            for npc in server.npc_pedestrians
            if npc.kind == "pedestrian"
        } if track_pedestrians else {}
        server.update_traffic(dt, [], tick * dt)
        server.update_npcs(dt, [], tick, tick * dt)
        if track_pedestrians:
            for npc in server.npc_pedestrians:
                if npc.kind != "pedestrian" or npc.npc_id not in before:
                    continue
                px, py = before[npc.npc_id]
                travelled[npc.npc_id] = travelled.get(npc.npc_id, 0.0) + math.hypot(npc.x - px, npc.y - py)
                if signal_waits is not None and npc.signal_waiting:
                    signal_waits[npc.npc_id] = signal_waits.get(npc.npc_id, 0.0) + dt
    return travelled


def _overlapping_car_pairs() -> list[list[str]]:
    pairs: list[list[str]] = []
    cars = list(server.traffic_vehicles)
    for index, car in enumerate(cars):
        for other in cars[index + 1:]:
            if server._oriented_boxes_overlap(
                car.x, car.y, car.angle, car.collision_length, car.collision_width,
                other.x, other.y, other.angle, other.collision_length, other.collision_width,
            ):
                pairs.append([car.vehicle_id, other.vehicle_id])
    return pairs


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

    if int(audit.get("pedestrian_reciprocal_edge_count", -1)) != 0:
        raise RuntimeError(f"pedestrian routes still contain reciprocal edges: {audit.get('pedestrian_reciprocal_edge_count')}")
    if int(audit.get("pedestrian_one_way_cycle_routes", 0)) != int(audit.get("pedestrian_route_count", -1)):
        raise RuntimeError("not every v1.1 pedestrian route is a one-way cycle")

    initial_car_positions = {car.vehicle_id: (car.x, car.y) for car in server.traffic_vehicles}
    initial_npc_positions = {npc.npc_id: (npc.x, npc.y) for npc in server.npc_pedestrians}
    dt = 1.0 / 60.0
    _advance_population(dt, 0, 150)

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

    # The old reciprocal tree-walk routes could pass the first 2.5 seconds and
    # then deadlock once pedestrians met head-on. Warm the city for five seconds,
    # then measure actual path length during a separate five-second window.
    _advance_population(dt, 150, FLOW_WARMUP_TICKS)
    pedestrian_signal_waits: dict[str, float] = {}
    pedestrian_travel = _advance_population(
        dt,
        FLOW_WARMUP_TICKS,
        FLOW_WARMUP_TICKS + FLOW_MEASURE_TICKS,
        track_pedestrians=True,
        signal_waits=pedestrian_signal_waits,
    )
    pedestrians = [npc for npc in server.npc_pedestrians if npc.kind == "pedestrian"]
    flow_measure_seconds = FLOW_MEASURE_TICKS * dt
    required_travel = {
        npc.npc_id: MIN_FLOW_DISTANCE_5S
        * max(0.0, flow_measure_seconds - pedestrian_signal_waits.get(npc.npc_id, 0.0))
        / flow_measure_seconds
        for npc in pedestrians
    }
    stalled_pedestrians = sorted(
        npc.npc_id
        for npc in pedestrians
        if pedestrian_travel.get(npc.npc_id, 0.0) < required_travel[npc.npc_id]
    )
    off_pavement_pedestrians = sorted(
        npc.npc_id
        for npc in pedestrians
        if not v110_grid_population._is_pavement(
            game.grid_world,
            *game.grid_world.world_to_cell(npc.x, npc.y),
        )
    )

    blocked_cars = [
        car.vehicle_id for car in server.traffic_vehicles
        if v110_grid_population._grid_vehicle_blocked(game.grid_world, car, car.x, car.y, car.angle)
    ]
    overlapping_cars = _overlapping_car_pairs()
    client_target_lengths = [
        v110_vehicle_proportions.expected_client_render_length(car.render_length)
        for car in server.traffic_vehicles
    ]
    collision_visual_ratios = [
        float(car.collision_length) / v110_vehicle_proportions.expected_client_render_length(car.render_length)
        for car in server.traffic_vehicles
    ]

    if len(server.traffic_vehicles) < 6:
        raise RuntimeError(f"v1.1 proof expected at least six safe traffic cars, got {len(server.traffic_vehicles)}")
    if len(pedestrians) < 12:
        raise RuntimeError("v1.1 proof expected at least twelve pedestrians")
    if moved_cars < max(3, len(server.traffic_vehicles) // 3):
        raise RuntimeError(f"too few traffic cars moved during proof: {moved_cars}/{len(server.traffic_vehicles)}")
    if moved_npcs < 8:
        raise RuntimeError(f"too few NPCs moved during proof: {moved_npcs}")
    allowed_stalled = max(2, len(pedestrians) // 20)
    if len(stalled_pedestrians) > allowed_stalled:
        raise RuntimeError(
            f"pedestrian flow deadlocked after warmup: {len(stalled_pedestrians)}/{len(pedestrians)} "
            f"under {MIN_FLOW_DISTANCE_5S:.0f}px in five seconds; examples={stalled_pedestrians[:8]}"
        )
    if off_pavement_pedestrians:
        raise RuntimeError(f"pedestrians left GridWorld pavement: {off_pavement_pedestrians[:8]}")
    if blocked_cars:
        raise RuntimeError(f"traffic left GridWorld road collision: {blocked_cars[:8]}")
    if overlapping_cars:
        raise RuntimeError(f"traffic collision bodies overlap after 10 seconds: {overlapping_cars[:8]}")
    if client_target_lengths and min(client_target_lengths) < MIN_CLIENT_CAR_LENGTH_PX:
        raise RuntimeError(
            f"underscaled vehicle remains: min client target {min(client_target_lengths):.1f}px < {MIN_CLIENT_CAR_LENGTH_PX:.1f}px"
        )
    if collision_visual_ratios and min(collision_visual_ratios) < MIN_COLLISION_TO_VISUAL_RATIO:
        raise RuntimeError(
            f"vehicle collision body is too small for its visible sprite: ratio={min(collision_visual_ratios):.3f}"
        )

    game.vehicles = {
        car.vehicle_id: game_client.RemoteVehicle(car.public_dict())
        for car in server.traffic_vehicles
    }
    game.npcs = {
        npc.npc_id: game_client.RemoteNPC(npc.public_dict())
        for npc in server.npc_pedestrians
    }

    # Choose the actual densest gameplay window after the extended simulation.
    # The proof must make several cars and pedestrians visually obvious rather
    # than relying on counts that happen to be elsewhere in the world.
    cars = list(server.traffic_vehicles)
    game.camera_zoom = PROOF_ZOOM
    view_size = game.logical_view_size()
    half_w = view_size[0] * 0.46
    half_h = view_size[1] * 0.46

    def window_counts(cx: float, cy: float) -> tuple[int, int]:
        car_count = sum(abs(car.x - cx) <= half_w and abs(car.y - cy) <= half_h for car in cars)
        npc_count = sum(abs(npc.x - cx) <= half_w and abs(npc.y - cy) <= half_h for npc in pedestrians)
        return car_count, npc_count

    candidates = [(float(obj.x), float(obj.y)) for obj in [*cars, *pedestrians]]
    focus_x, focus_y = max(
        candidates,
        key=lambda pos: (
            min(window_counts(*pos)[0], 4) * min(window_counts(*pos)[1], 6),
            min(window_counts(*pos)[0], 4) + min(window_counts(*pos)[1], 6),
            sum(window_counts(*pos)),
            -pos[1], -pos[0],
        ),
    )
    visible_cars, visible_pedestrians = window_counts(focus_x, focus_y)
    if visible_cars < 2 or visible_pedestrians < 2:
        raise RuntimeError(
            f"v1.1 proof could not frame a populated street: cars={visible_cars}, pedestrians={visible_pedestrians}"
        )
    focus_car = min(cars, key=lambda car: math.hypot(car.x - focus_x, car.y - focus_y))
    focus_npc = min(pedestrians, key=lambda npc: math.hypot(npc.x - focus_x, npc.y - focus_y))
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
        f"v{GAME_VERSION} flow/vehicle proof — {visible_cars} cars + {visible_pedestrians} pedestrians; "
        f"stalled {len(stalled_pedestrians)}/{len(pedestrians)}; car min {min(client_target_lengths):.0f}px"
    )
    game.notice_until = 10**12

    display_surface = game.screen
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

    sorted_distances = sorted(pedestrian_travel.values())
    audit.update({
        "proof": "v110_grid_native_population_full_stack",
        "camera_zoom": PROOF_ZOOM,
        "traffic_moved_after_2_5s": moved_cars,
        "npcs_moved_after_2_5s": moved_npcs,
        "pedestrian_flow_measure_seconds": flow_measure_seconds,
        "pedestrian_flow_min_distance_px": MIN_FLOW_DISTANCE_5S,
        "pedestrian_lawful_signal_wait_max_seconds": round(max(pedestrian_signal_waits.values(), default=0.0), 3),
        "pedestrian_lawful_signal_wait_count": sum(value > 0.0 for value in pedestrian_signal_waits.values()),
        "pedestrians_stalled_after_warmup": stalled_pedestrians,
        "pedestrians_stalled_after_warmup_count": len(stalled_pedestrians),
        "pedestrians_off_pavement": off_pavement_pedestrians,
        "pedestrian_distance_min_px": round(min(sorted_distances, default=0.0), 3),
        "pedestrian_distance_median_px": round(sorted_distances[len(sorted_distances) // 2], 3) if sorted_distances else 0.0,
        "blocked_traffic_after_10s": blocked_cars,
        "overlapping_traffic_after_10s": overlapping_cars,
        "vehicle_client_target_length_min_px": round(min(client_target_lengths, default=0.0), 3),
        "vehicle_client_target_length_max_px": round(max(client_target_lengths, default=0.0), 3),
        "vehicle_collision_to_visual_ratio_min": round(min(collision_visual_ratios, default=0.0), 4),
        "vehicle_render_meta_scale": v110_vehicle_proportions.RENDER_META_SCALE,
        "vehicle_collision_length_meta_scale": v110_vehicle_proportions.COLLISION_LENGTH_META_SCALE,
        "vehicle_collision_width_meta_scale": v110_vehicle_proportions.COLLISION_WIDTH_META_SCALE,
        "focus_car": focus_car.vehicle_id,
        "focus_npc": focus_npc.npc_id,
        "visible_cars_in_proof_window": visible_cars,
        "visible_pedestrians_in_proof_window": visible_pedestrians,
        "player_cell": list(game.grid_world.world_to_cell(x, y)),
        "full_stack_panels": ["gameplay_player_hud_population", "actual_M_map", "authoritative_ground_overview"],
    })
    AUDIT.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, sort_keys=True))
    pygame.quit()


if __name__ == "__main__":
    main()
