from __future__ import annotations

"""Focused behavioral release gate for player reports #150-#160."""

import asyncio
import copy
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

pygame.init()
pygame.display.set_mode((1, 1))

import character_art
import client
from common import PlayerState, empty_inventory, get_map
import grid_client_entry
import server
import v100_server
from vehicle_art import _base_car


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class CaptureSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send(self, raw: str) -> None:
        self.messages.append(json.loads(raw))


def _car(vehicle_id: str, x: float, y: float, *, controlled_by: str = "", speed: float = 0.0) -> server.TrafficVehicle:
    return server.TrafficVehicle(
        vehicle_id=vehicle_id, route_index=-1, next_waypoint=0,
        x=x, y=y, angle=0.0, speed=speed, color_index=0, sprite_index=0,
        controlled_by=controlled_by, npc_driver=not bool(controlled_by), parked=not bool(speed),
        collision_length=142.0, collision_width=62.0, render_length=142,
    )


async def _passenger_audit(world) -> dict:
    x, y = world.choose_spawn("ground", server.PLAYER_RADIUS)
    driver = _car("v23-driver-car", x + 22.0, y, controlled_by="driver", speed=0.0)
    player = PlayerState("v23-passenger", "Passenger", x, y)
    session = server.ClientSession(CaptureSocket(), player, "15550000230", empty_inventory())
    server.traffic_vehicles[:] = [driver]
    await server.process_passenger_action(session)
    require(session.passenger_vehicle_id == driver.vehicle_id, "E passenger action did not board")
    require(player.vehicle_role == "passenger" and player.player_id in driver.passenger_ids,
            "passenger role/occupancy was not authoritative")
    driver_player = PlayerState("driver", "Driver", driver.x, driver.y)
    driver_session = server.ClientSession(CaptureSocket(), driver_player, "15550000231", empty_inventory())
    driver_session.driving_vehicle_id = driver.vehicle_id
    await server.handle_message(driver_session, json.dumps({
        "type": "input", "sequence": 0,
        "x": 0.0, "y": 0.0, "aim": 0.0, "handbrake": True,
    }))
    require(driver_session.handbrake, "Space handbrake input was not accepted for the authoritative driver")
    source = (ROOT / "client.py").read_text(encoding="utf-8")
    require('"type": "passenger_action"' in source and '[{key}]' in source,
            "client E passenger action or prompt is missing")
    return {
        "boarded_with_e_action": True, "handbrake_input_authoritative": True,
        "capacity": driver.public_dict()["passenger_capacity"],
    }


def _vehicle_motion_audit(world) -> dict:
    old_world, old_grid = server.GRID_WORLD, server.GRID_RUNTIME_ACTIVE
    try:
        server.GRID_WORLD = world
        server.GRID_RUNTIME_ACTIVE = True
        road = next(
            world.cell_center(gx, gy)
            for gy in range(world.height) for gx in range(world.width)
            if world.collision_at("ground", *world.cell_center(gx, gy)) == "road"
            and all(world.collision_at("ground", world.cell_center(gx, gy)[0] + dx, world.cell_center(gx, gy)[1] + dy) == "road"
                    for dx, dy in ((-90, 0), (90, 0), (0, -90), (0, 90)))
        )
        mover = _car("v23-mover", road[0], road[1], controlled_by="player", speed=90.0)
        blocker = _car("v23-blocker", road[0] + 80.0, road[1], speed=0.0)
        blocker.parked = False
        server.traffic_vehicles[:] = [mover, blocker]
        before = (blocker.x, blocker.y)
        require(server._push_blocking_vehicles(mover, road[0] + 28.0, road[1], 0.0, 24.0),
                "player car could not displace a blocking traffic car")
        require((blocker.x, blocker.y) != before, "blocking traffic car was not moved")

        player_x, player_y = mover.x, mover.y
        displaced = server._displace_point_from_car(player_x, player_y, server.PLAYER_RADIUS, mover)
        require(displaced is not None and math.hypot(displaced[0] - player_x, displaced[1] - player_y) > 10.0,
                "overlapped player was not given a legal displacement pose")

        handbrake_car = _car("v23-handbrake", road[0], road[1], speed=200.0)
        server._apply_player_handbrake(handbrake_car, 0.10)
        require(0.0 <= handbrake_car.speed <= 125.0 and handbrake_car.brake_lights,
                f"Space handbrake deceleration failed: {handbrake_car.speed}")
        server_source = (ROOT / "server.py").read_text(encoding="utf-8")
        bicycle_branch = server_source[server_source.index("if session.riding_bicycle_id:"):server_source.index("if session.driving_vehicle_id:")]
        driver_branch = server_source[server_source.index("if session.driving_vehicle_id:", server_source.index("async def simulation_loop")):server_source.index("speed_abs = abs(car.speed)")]
        require("_apply_player_handbrake" not in bicycle_branch,
                "car handbrake was accidentally connected to bicycle physics")
        require("if session.handbrake:" in driver_branch and "_apply_player_handbrake(car, dt)" in driver_branch,
                "authoritative driver physics does not apply the handbrake")
        return {
            "traffic_car_displaced_px": round(math.hypot(blocker.x - before[0], blocker.y - before[1]), 2),
            "player_escape_distance_px": round(math.hypot(displaced[0] - player_x, displaced[1] - player_y), 2),
            "handbrake_speed_after_100ms": round(handbrake_car.speed, 2),
        }
    finally:
        server.GRID_WORLD, server.GRID_RUNTIME_ACTIVE = old_world, old_grid


def _world_population_audit(config: dict, world) -> dict:
    parking = config.get("parking_spots", [])
    parked = [car for car in server.traffic_vehicles if car.parked]
    require(len(parking) >= 12 and len(parked) >= 4, "usable parking population is missing")
    require(sum(not row.get("occupied") for row in parking) >= 8, "parking population left no chill-out bays")
    payload = server.network_map_payload(config)
    require(len(payload.get("parking_spots", [])) == len(parking), "parking bays were dropped from network map")

    signals = config.get("traffic_signals", [])
    require(len(signals) >= 48, "GridWorld traffic-light fixtures were not generated")
    source = (ROOT / "grid_client_entry.py").read_text(encoding="utf-8")
    wrapper = source[source.index("def _draw_world_grid_exclusive"):source.index("def _with_grid_player_scale")]
    require("_ORIGINAL_DRAW_WORLD(game)" in wrapper and "grid_renderer.draw_view" not in wrapper,
            "grid entry still bypasses dynamic traffic-light drawing")

    jobs = config.get("job_locations", [])
    require(len(jobs) == 20, f"expected 20 job markers, found {len(jobs)}")
    require(source.count("for job in game._job_locations()") >= 2,
            "M map or minimap still uses the legacy single job pair")

    phones = [row for row in world.objects if row.get("lighting_kind") == "public_phone"]
    require(len(phones) == 16 and all(row.get("emits_light") for row in phones),
            "pavement phones do not all carry registered light pools")
    require(all(world.collision_at("ground", *world.cell_center(int(row["gx"]), int(row["gy"]))) == "sidewalk" for row in phones),
            "a public phone is not anchored to pavement")

    # v2.8 supersedes the earlier four-times scale after report #190 showed
    # that it covered the entire pavement cell. Keep the prop substantial while
    # reserving visible and collision clearance around its authored cell.
    planters = [
        row for row in world.objects
        if row.get("scale_policy") == "sidewalk_fit_tree_planter_scale_1_5x_v28"
    ]
    require(planters and all(
        100 <= int(row["width_px"]) < int(world.cell_px)
        and 90 <= int(row["height_px"]) < int(world.cell_px)
        for row in planters
    ), "reported wooden shrub planter does not fit inside one pavement cell")
    require(all(25.0 <= float(row.get("collision_radius_px", 0.0)) <= 40.0 for row in planters),
            "reported wooden shrub planter collision does not preserve sidewalk clearance")
    require(all(row.get("placement_policy") == "single_pavement_cell_clearance_v28" for row in planters),
            "reported wooden shrub planter is missing the v2.8 clearance policy")
    return {
        "parking_spots": len(parking), "parked_cars": len(parked),
        "empty_parking_spots": sum(not row.get("occupied") for row in parking),
        "traffic_signals": len(signals), "job_markers": len(jobs),
        "public_phones_with_lights": len(phones), "sidewalk_fit_tree_planters": len(planters),
    }


def _pedestrian_audit(world) -> dict:
    edge = next(
        (gx, gy, dx, dy)
        for gy in range(1, world.height - 1) for gx in range(1, world.width - 1)
        if world.collision_at("ground", *world.cell_center(gx, gy)) == "sidewalk"
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        if world.collision_at("ground", *world.cell_center(gx + dx, gy + dy)) == "road"
    )
    gx, gy, dx, dy = edge
    x, y = world.cell_center(gx, gy)
    nx, ny = world.cell_center(gx + dx, gy + dy)
    car = _car("v23-crossing-car", nx - dx * 45.0, ny - dy * 45.0, speed=60.0)
    car.angle = math.atan2(dy, dx)
    server.traffic_vehicles[:] = [car]
    require(not server._pedestrian_vehicle_allows_entry(world, x, y, nx, ny),
            "pedestrian entered road in front of nearby car")
    car.x += 2000.0
    car.y += 2000.0
    require(server._pedestrian_vehicle_allows_entry(world, x, y, nx, ny),
            "pedestrian was unable to cross a clear road")

    first = server.NPCPedestrian("v23-ped-a", 0, 1, x, y, 60.0, 0.0, {}, last_progress_x=x, last_progress_y=y)
    second = server.NPCPedestrian("v23-ped-b", 0, 1, x + 5.0, y, 60.0, 0.0, {}, last_progress_x=x + 5.0, last_progress_y=y)
    server.npc_pedestrians[:] = [first, second]
    server.traffic_vehicles.clear()
    resolved = server._resolve_npc_personal_space(world, 26.0)
    distance = math.hypot(first.x - second.x, first.y - second.y)
    require(resolved >= 1 and distance >= 22.0, f"pedestrian separation failed: {distance}")
    return {"near_car_entry_blocked": True, "clear_crossing_allowed": True, "personal_space_px": round(distance, 2)}


def _art_audit() -> dict:
    # gridcar010 is generated index 25. The complete source must no longer pass
    # through the synthetic rear-cap repair that created the detached strip.
    import vehicle_art
    original = vehicle_art._repair_generated_rear_crop
    vehicle_art._base_car.cache_clear()
    vehicle_art._repair_generated_rear_crop = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("unexpected repair"))
    try:
        truck = _base_car(25, 300)
    finally:
        vehicle_art._repair_generated_rear_crop = original
        vehicle_art._base_car.cache_clear()
    require(truck is not None and truck.get_bounding_rect(min_alpha=10).height >= 280,
            "gridcar010 complete sprite did not render")

    cap_source = character_art._load_part("hats/hat_07.png")
    source_rect = cap_source.get_bounding_rect(min_alpha=10)
    cap = character_art._north_facing_baseball_cap(cap_source)
    cap_rect = cap.get_bounding_rect(min_alpha=10)
    require(cap_rect.top < source_rect.top, "baseball-cap peak does not extend north")
    frame = character_art._composed_frame("hat_07", "head_01", "body_01", "idle")
    require(frame.get_bounding_rect(min_alpha=10).top > 0, "corrected cap clips outside the composite canvas")
    return {
        "gridcar010_runtime_height": truck.get_height(),
        "cap_peak_north_extension_px": source_rect.top - cap_rect.top,
    }


def main() -> int:
    world = v100_server.load_ground_grid()
    config = copy.deepcopy(get_map())
    old_map, old_world = server.ACTIVE_MAP, server.GRID_WORLD
    old_traffic, old_npcs = list(server.traffic_vehicles), list(server.npc_pedestrians)
    try:
        server.ACTIVE_MAP = config
        server.GRID_WORLD = world
        errors = v100_server.validate_active_authority(config)
        require(not errors, f"GridWorld population failed: {errors}")
        population = _world_population_audit(config, world)
        passenger = asyncio.run(_passenger_audit(world))
        vehicle_motion = _vehicle_motion_audit(world)
        pedestrians = _pedestrian_audit(world)
        art = _art_audit()
    finally:
        server.ACTIVE_MAP, server.GRID_WORLD = old_map, old_world
        server.traffic_vehicles[:] = old_traffic
        server.npc_pedestrians[:] = old_npcs
    results = {
        "reports": "#150-#160", "passenger": passenger,
        "vehicles": vehicle_motion, "population": population,
        "pedestrians": pedestrians, "art": art,
        "release_status": "ready_for_v2.3_release_gate",
    }
    print("V2.3 CURRENT REPORTS AUDIT: PASS")
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
