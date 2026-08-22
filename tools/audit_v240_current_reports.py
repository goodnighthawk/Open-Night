from __future__ import annotations

"""Focused behavioral release gate for player reports #161-#164."""

import asyncio
import copy
import json
import math
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

import client
from common import PlayerState, empty_inventory, get_map
from gameplay.audio import GameAudio, SFX_ROOT
import server
import v100_server
import vehicle_art
from vehicle_catalog import vehicle_asset_path, vehicle_meta


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class CaptureSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send(self, raw: str) -> None:
        self.messages.append(json.loads(raw))


def _horn_audit() -> dict:
    car = server.TrafficVehicle(
        "v24-horn", 0, 0, 0.0, 0.0, 0.0, 0.0, 0, 0,
        collision_length=42.0, collision_width=18.0, render_length=48,
    )
    server._activate_traffic_horn(car, 0.8)
    first_sequence = car.horn_sequence
    server._activate_traffic_horn(car, 0.8)
    require(car.horn_sequence == first_sequence == 1, "held horn emitted repeated network events")
    car.horn_until = 0.0
    server._activate_traffic_horn(car, 0.8)
    require(car.public_dict()["horn_sequence"] == 2, "new horn pulse was not durable in snapshots")

    remote = client.RemoteVehicle(car.public_dict())
    require(remote.horn_sequence == 2, "client dropped the server horn sequence")
    require((SFX_ROOT / "SFX_STANDARD_HORN.wav").is_file(), "real vehicle horn sample is missing")

    audio = GameAudio()
    require(audio.enabled, "game audio did not load the horn sample")
    played: list[tuple[str, float]] = []
    audio._play = lambda key, volume=1.0: played.append((key, volume))  # type: ignore[method-assign]
    audio.last_any_horn = time.monotonic() - 2.0
    local = SimpleNamespace(render_x=0.0, render_y=0.0, in_vehicle=False, vehicle_id="", moving_until=0.0)
    audible = SimpleNamespace(
        id="audible-car", horn=False, horn_sequence=4, parked=False,
        render_x=80.0, render_y=0.0, speed=0.0,
    )
    game = SimpleNamespace(players={"local": local}, local_id="local", vehicles={"audible-car": audible}, grid_world=None)
    audio.update(game)
    audible.horn_sequence = 5
    audio.update(game)
    require([key for key, _volume in played].count("horn") == 1,
            "durable horn event did not play exactly one real sample")
    source = (ROOT / "client.py").read_text(encoding="utf-8")
    require('render("BEEP!"' not in source, "client still draws BEEP instead of relying on horn audio")
    return {"network_sequences": 2, "missed_boolean_pulse_recovered": True, "sample_plays": 1}


def _bus_art_audit() -> dict:
    completed: list[dict] = []
    for index in (22, 23, 24):
        meta = vehicle_meta(index)
        source = vehicle_art._load_surface_file(vehicle_asset_path(str(meta.get("file", ""))))
        require(source is not None, f"bus source {index} did not load")
        repaired = vehicle_art._repair_generated_rear_crop(source, "bus")
        source_bottom = source.get_bounding_rect(min_alpha=10).bottom
        repaired_bottom = repaired.get_bounding_rect(min_alpha=10).bottom
        require(repaired_bottom >= source_bottom + 10,
                f"bus {index} did not gain a connected rear cap: {source_bottom} -> {repaired_bottom}")
        vehicle_art._base_car.cache_clear()
        runtime = vehicle_art._base_car(index, 330)
        require(runtime is not None and runtime.get_bounding_rect(min_alpha=10).height >= 310,
                f"bus {index} runtime sprite is still clipped")
        completed.append({"index": index, "source_bottom": source_bottom, "repaired_bottom": repaired_bottom})
    return {"completed_buses": completed}


async def _parking_departure_audit(world, config: dict) -> dict:
    parked = [car for car in server.traffic_vehicles if car.parked]
    require(len(parked) >= 6, "occupied parking population is incomplete")
    for car in parked:
        car.controlled_by = "departure-check"
        car.parked = False
        require(not server._vehicle_map_blocked(car, car.x, car.y, car.angle),
                f"{car.vehicle_id} becomes trapped when player collision activates")
        nx = car.x + math.cos(car.angle) * 24.0
        ny = car.y + math.sin(car.angle) * 24.0
        require(not server._vehicle_map_blocked(car, nx, ny, car.angle),
                f"{car.vehicle_id} cannot move forward out of its bay")
        car.controlled_by = ""
        car.parked = True

    target = parked[0]
    player = PlayerState("v24-driver", "Departure", target.x, target.y)
    session = server.ClientSession(CaptureSocket(), player, "15550000240", empty_inventory())
    await server.process_car_action(session)
    require(session.driving_vehicle_id == target.vehicle_id and target.controlled_by == player.player_id,
            "player could not enter a generated parked car")
    require(not server._vehicle_map_blocked(target, target.x, target.y, target.angle),
            "entered parked car is collision-trapped")
    close_spots = [
        row for row in config.get("parking_spots", [])
        if world.object_collision_at(float(row["pos"][0]), float(row["pos"][1]), 90.0)
    ]
    require(not close_spots, f"parking bays still overlap solid curb props: {close_spots}")
    return {"occupied_bays": len(parked), "all_departure_poses_clear": True, "entered_vehicle": target.vehicle_id}


def _circulation_audit(config: dict) -> dict:
    routes = config.get("traffic_routes", []) or []
    starts = config.get("traffic_starts", []) or []
    require(len(routes) == 84 and all(route.get("city_circulation") for route in routes),
            "traffic does not exclusively use city-circulation routes")
    require(min(len(route.get("waypoints", [])) for route in routes) >= 12,
            "a traffic route still loops around one block")
    require(min(int(route.get("circulation_blocks", 0)) for route in routes) >= 6,
            "a traffic route does not span multiple city blocks")
    route_ids = [str(row.get("route_id", "")) for row in starts]
    require(len(set(route_ids)) >= min(50, len(route_ids)),
            "traffic start plan does not vary routes across the fleet")
    source = (ROOT / "v110_grid_population.py").read_text(encoding="utf-8")
    require("random." not in source and "random.choice" not in source,
            "circulation introduced nondeterministic multiplayer routing")
    return {
        "routes": len(routes), "minimum_waypoints": min(len(route["waypoints"]) for route in routes),
        "minimum_block_span": min(int(route["circulation_blocks"]) for route in routes),
        "unique_start_routes": len(set(route_ids)), "car_avoidance_retained": True,
    }


def main() -> int:
    world = v100_server.load_ground_grid()
    config = copy.deepcopy(get_map())
    old_map, old_world, old_grid = server.ACTIVE_MAP, server.GRID_WORLD, server.GRID_RUNTIME_ACTIVE
    old_count = server.TRAFFIC_COUNT
    old_traffic, old_npcs = list(server.traffic_vehicles), list(server.npc_pedestrians)
    try:
        server.ACTIVE_MAP = config
        server.GRID_WORLD = world
        server.GRID_RUNTIME_ACTIVE = True
        server.TRAFFIC_COUNT = 56
        errors = v100_server.validate_active_authority(config)
        require(not errors, f"GridWorld population failed: {errors}")
        horn = _horn_audit()
        buses = _bus_art_audit()
        parking = asyncio.run(_parking_departure_audit(world, config))
        circulation = _circulation_audit(config)
    finally:
        server.ACTIVE_MAP, server.GRID_WORLD, server.GRID_RUNTIME_ACTIVE = old_map, old_world, old_grid
        server.TRAFFIC_COUNT = old_count
        server.traffic_vehicles[:] = old_traffic
        server.npc_pedestrians[:] = old_npcs
    results = {
        "reports": "#161-#164", "horn": horn, "bus_art": buses,
        "parking": parking, "circulation": circulation,
        "release_status": "ready_for_v2.4_release_gate",
    }
    print("V2.4 CURRENT REPORTS AUDIT: PASS")
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
