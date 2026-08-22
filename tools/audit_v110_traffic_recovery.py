#!/usr/bin/env python3
from __future__ import annotations

"""Sustained v1.1 GridWorld traffic deadlock/collision audit.

The visual full-stack capture previously exercised roughly ten seconds, which is
long enough to catch immediate route mistakes but not queue/junction deadlocks.
This harness runs a denser 75-second simulation, ignores the first five seconds
as warm-up, and rejects persistent stationary cars, road-boundary violations, or
vehicle-body overlaps.
"""

import json
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import v100_runtime_refinement
import v100_safe_layout
v100_safe_layout.install(v100_runtime_refinement)
v100_runtime_refinement.install()
import v100_scale_normalization
v100_scale_normalization.install()

import server
import v100_client
import v110_grid_population
import v110_pedestrian_flow
import v110_vehicle_proportions
import v110_traffic_recovery

v110_pedestrian_flow.install(v110_grid_population)
v110_vehicle_proportions.install(server)

OUT = ROOT / "assets" / "grid_v100" / "V110_TRAFFIC_RECOVERY_AUDIT.json"
TRAFFIC_COUNT = 28
DT = 1.0 / 60.0
SIM_SECONDS = 75.0
WARMUP_SECONDS = 5.0
MAX_STATIONARY_SECONDS = 5.0
MIN_DISTANCE_AFTER_WARMUP_PX = 550.0
CHECK_EVERY_TICKS = 12


def _overlaps() -> list[list[str]]:
    cars = list(server.traffic_vehicles)
    pairs: list[list[str]] = []
    for index, car in enumerate(cars):
        for other in cars[index + 1:]:
            if server._oriented_boxes_overlap(
                car.x, car.y, car.angle, car.collision_length, car.collision_width,
                other.x, other.y, other.angle, other.collision_length, other.collision_width,
            ):
                pairs.append([car.vehicle_id, other.vehicle_id])
    return pairs


def _audit_bounded_collision_recovery() -> dict:
    car = SimpleNamespace(
        x=0.0, y=0.0, angle=0.0, speed=90.0, speed_factor=1.0,
        wait_age=4.0, stuck_time=3.0, last_progress_x=0.0, last_progress_y=0.0,
    )
    route = {"speed_limit": 120.0}
    v110_traffic_recovery._apply_recovery_pose(server, car, route, -12.0, 0.0, math.pi)
    max_delta = v110_traffic_recovery.MAX_RECOVERY_HEADING_CHANGE_RADIANS
    if abs(float(car.angle)) > max_delta + 1e-9:
        raise RuntimeError(f"collision recovery snapped heading: {car.angle!r}")
    if not (
        v110_traffic_recovery.RECOVERY_INCH_SPEED_MIN
        <= float(car.speed)
        <= v110_traffic_recovery.RECOVERY_INCH_SPEED_MAX
    ):
        raise RuntimeError(f"collision recovery did not use inching speed: {car.speed!r}")
    return {
        "max_heading_change_degrees": round(math.degrees(max_delta), 3),
        "observed_heading_change_degrees": round(abs(math.degrees(float(car.angle))), 3),
        "recovery_speed_px_s": round(float(car.speed), 3),
    }


def _audit_player_collision_deflection() -> dict:
    old = 1.25
    samples = [
        server._player_collision_deflection_angle(old, offset, direction)
        for offset in (0.04, -0.04, 0.16, -0.30, 4.0)
        for direction in (-1.0, 1.0)
    ]
    maximum = max(abs((angle - old + math.pi) % (2.0 * math.pi) - math.pi) for angle in samples)
    if maximum > math.radians(4.0) + 1e-9:
        raise RuntimeError(f"player collision deflection can spin: {math.degrees(maximum):.3f} degrees")
    return {"max_heading_change_degrees": round(math.degrees(maximum), 3), "cooldown_seconds": 0.25}


def main() -> None:
    bounded_recovery = _audit_bounded_collision_recovery()
    player_deflection = _audit_player_collision_deflection()
    game_client = v100_client.game_client
    game_client.NetworkClient.start = lambda self: None
    v100_client.install_v100_client()
    game = game_client.Game("ws://v110-traffic-audit.invalid:8765", "5550000111", "TrafficAudit")
    if game.grid_world is None:
        raise RuntimeError("traffic audit requires normalized GridWorld")

    server.ACTIVE_MAP = game.map_config
    server.ACTIVE_MAP_ID = str(game.map_config.get("id", server.ACTIVE_MAP_ID))
    server.GRID_WORLD = game.grid_world
    server.GRID_RUNTIME_ACTIVE = True
    server.TRAFFIC_COUNT = TRAFFIC_COUNT
    population = v110_grid_population.prepare_and_initialize(server, server.ACTIVE_MAP, server.GRID_WORLD)
    cars = list(server.traffic_vehicles)
    if len(cars) < 12:
        raise RuntimeError(f"traffic audit expected at least 12 safe cars, got {len(cars)}")

    stationary = {car.vehicle_id: 0.0 for car in cars}
    max_stationary = {car.vehicle_id: 0.0 for car in cars}
    signal_wait = {car.vehicle_id: 0.0 for car in cars}
    max_signal_wait = {car.vehicle_id: 0.0 for car in cars}
    distance_after_warmup = {car.vehicle_id: 0.0 for car in cars}
    blocked_seen: set[str] = set()
    overlap_seen: set[tuple[str, str]] = set()
    ticks = int(round(SIM_SECONDS / DT))
    warmup_ticks = int(round(WARMUP_SECONDS / DT))

    for tick in range(ticks):
        before = {car.vehicle_id: (float(car.x), float(car.y)) for car in server.traffic_vehicles}
        server.update_traffic(DT, [], tick * DT)
        for car in server.traffic_vehicles:
            old = before.get(car.vehicle_id, (car.x, car.y))
            moved = math.hypot(float(car.x) - old[0], float(car.y) - old[1])
            if tick >= warmup_ticks:
                distance_after_warmup[car.vehicle_id] = distance_after_warmup.get(car.vehicle_id, 0.0) + moved
                if moved < 0.15 and bool(getattr(car, "red_light_waiting", False)):
                    stationary[car.vehicle_id] = 0.0
                    signal_wait[car.vehicle_id] = signal_wait.get(car.vehicle_id, 0.0) + DT
                elif moved < 0.15:
                    stationary[car.vehicle_id] = stationary.get(car.vehicle_id, 0.0) + DT
                    signal_wait[car.vehicle_id] = 0.0
                else:
                    stationary[car.vehicle_id] = 0.0
                    signal_wait[car.vehicle_id] = 0.0
                max_stationary[car.vehicle_id] = max(
                    max_stationary.get(car.vehicle_id, 0.0),
                    stationary[car.vehicle_id],
                )
                max_signal_wait[car.vehicle_id] = max(
                    max_signal_wait.get(car.vehicle_id, 0.0),
                    signal_wait[car.vehicle_id],
                )

        if tick % CHECK_EVERY_TICKS == 0:
            for car in server.traffic_vehicles:
                if v110_grid_population._grid_vehicle_blocked(
                    game.grid_world, car, car.x, car.y, car.angle
                ):
                    blocked_seen.add(str(car.vehicle_id))
            for a, b in _overlaps():
                overlap_seen.add(tuple(sorted((a, b))))

    stalled = sorted(
        car_id for car_id, seconds in max_stationary.items()
        if seconds > MAX_STATIONARY_SECONDS
    )
    undertravel = sorted(
        car_id for car_id, distance in distance_after_warmup.items()
        if distance < MIN_DISTANCE_AFTER_WARMUP_PX
    )
    recovery = dict(getattr(server, "_v110_traffic_recovery_stats", {}) or {})
    route_offsets = sorted({
        round(abs(float(route.get("lane_offset", 0.0))), 3)
        for route in server.ACTIVE_MAP.get("traffic_routes", []) or []
    })
    result = {
        "proof": "v110_sustained_traffic_recovery",
        "simulation_seconds": SIM_SECONDS,
        "warmup_seconds": WARMUP_SECONDS,
        "traffic_requested": TRAFFIC_COUNT,
        "traffic_spawned": len(server.traffic_vehicles),
        "traffic_route_count": int(population.get("traffic_route_count", 0)),
        "lane_offsets_px": route_offsets,
        "max_stationary_allowed_seconds": MAX_STATIONARY_SECONDS,
        "max_stationary_observed_seconds": round(max(max_stationary.values(), default=0.0), 3),
        "max_lawful_signal_wait_observed_seconds": round(max(max_signal_wait.values(), default=0.0), 3),
        "stalled_car_ids": stalled,
        "min_distance_required_px": MIN_DISTANCE_AFTER_WARMUP_PX,
        "min_distance_observed_px": round(min(distance_after_warmup.values(), default=0.0), 3),
        "undertravel_car_ids": undertravel,
        "blocked_car_ids": sorted(blocked_seen),
        "overlap_pairs": [list(pair) for pair in sorted(overlap_seen)],
        "recovery_stats": recovery,
        "bounded_collision_recovery": bounded_recovery,
        "bounded_player_collision_deflection": player_deflection,
        "grid_cell_px": int(game.grid_world.cell_px),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))

    if stalled:
        raise RuntimeError(f"cars remained stationary too long: {stalled[:8]}")
    if undertravel:
        raise RuntimeError(f"cars failed sustained route progress: {undertravel[:8]}")
    if blocked_seen:
        raise RuntimeError(f"cars left authoritative road collision: {sorted(blocked_seen)[:8]}")
    if overlap_seen:
        raise RuntimeError(f"vehicle bodies overlapped during sustained run: {sorted(overlap_seen)[:8]}")
    lane_width = game.grid_world.cell_px * 5.0 / 6.0
    expected_offsets = [lane_width * ratio for ratio in (0.5, 1.5, 2.5)]
    if len(route_offsets) != 3 or any(abs(actual - expected) > 0.01 for actual, expected in zip(route_offsets, expected_offsets)):
        raise RuntimeError(f"six-lane separation is not exact: offsets={route_offsets}, expected={expected_offsets}")


if __name__ == "__main__":
    main()
