from __future__ import annotations

"""Focused behavioral release gate for reports #165-#184 and v2.5 map capacity."""

import asyncio
from collections import Counter
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

from common import PlayerState, empty_inventory, get_map
from interior_layout import interior_floor_rect
import server
import v100_server
import v110_grid_population
import v110_pedestrian_connectivity
import v110_traffic_recovery
import vehicle_art


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class CaptureSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send(self, raw: str) -> None:
        self.messages.append(json.loads(raw))


def _overlap_pairs() -> list[tuple[str, str]]:
    cars = [car for car in server.traffic_vehicles if not car.parked]
    pairs = []
    for index, car in enumerate(cars):
        for other in cars[index + 1:]:
            if server._oriented_boxes_overlap(
                car.x, car.y, car.angle, car.collision_length, car.collision_width,
                other.x, other.y, other.angle, other.collision_length, other.collision_width,
            ):
                pairs.append(tuple(sorted((car.vehicle_id, other.vehicle_id))))
    return pairs


async def _building_and_capacity_audit(world, config: dict) -> dict:
    buildings = list((world.data.get("building_synthesis") or {}).get("buildings") or [])
    interiors = list(config.get("interiors", []) or [])
    doors = {
        str(item.get("building_id", "")): item
        for item in world.objects
        if bool(item.get("functional_entry"))
    }
    require(len(buildings) == len(interiors) == len(doors) == 30,
            "building, interior, door, and slot authorities diverged")
    require(server.MAX_PLAYERS == 30, "server did not derive 30 slots from 30 enterable buildings")
    require(config.get("runtime", {}).get("server_capacity_policy") == "one_slot_per_enterable_building_v25",
            "building-proportional capacity policy is missing")

    by_building = {str(row["building_id"]): row for row in buildings}
    for interior in interiors:
        building_id = str(interior.get("building_id", ""))
        require(building_id in by_building and building_id in doors,
                f"interior is not bound to one wall door: {building_id}")
        require(interior_floor_rect(config, str(interior["id"])) is not None,
                f"first-floor geometry is missing: {building_id}")
        ex, ey = map(float, interior["entry"])
        require(world.collision_at("ground", ex, ey) in {"walk", "sidewalk"},
                f"door interaction point is not pavement: {building_id}")
        door = doors[building_id]
        x0, y0, x1, y1 = map(int, by_building[building_id]["rect"])
        require(x0 <= int(door["gx"]) <= x1 and y0 <= int(door["gy"]) <= y1,
                f"door is not on the building wall cell: {building_id}")

    first = interiors[0]
    ex, ey = map(float, first["entry"])
    player = PlayerState("v25-door", "DoorAudit", ex, ey)
    socket = CaptureSocket()
    session = server.ClientSession(socket, player, "15550000250", empty_inventory())
    await server.process_interior_action(session, "enter", {"interior_id": first["id"]})
    require(player.interior_id == first["id"] and bool(socket.messages[-1].get("active")),
            "wall door did not enter the authoritative first floor")

    infill = [row for row in buildings if row.get("infill_policy")]
    require(len(infill) == 2, "two photographed empty urban blocks were not filled")
    require(all("three_player_width_setback" in str(row.get("infill_policy")) for row in infill),
            "infill buildings do not declare the three-player-width curb setback")
    return {
        "enterable_buildings": len(buildings),
        "functional_wall_doors": len(doors),
        "first_floor_entered": str(first["id"]),
        "infill_buildings": [str(row["building_id"]) for row in infill],
        "server_slots": server.MAX_PLAYERS,
    }


def _map_art_audit(world) -> dict:
    closures = Counter(
        str(item.get("road_closure_id", ""))
        for item in world.objects if item.get("street_item_kind") == "traffic_cone"
    )
    require(len(closures) == 3 and set(closures.values()) == {5},
            f"traffic cones are not three five-cone closures: {dict(closures)}")

    phones = [item for item in world.objects if item.get("street_item_kind") == "telephone_box"]
    require(len(phones) == 16 and all(item.get("placement_policy") == "deep_pavement_inset_public_phone_v25" for item in phones),
            "public phones are not using the deep pavement inset")
    for item in phones:
        center_x = float(item["offset_x_px"]) + float(item["width_px"]) * 0.5
        center_y = float(item["offset_y_px"]) + float(item["height_px"]) * 0.5
        require(max(abs(center_x - world.cell_px * 0.5), abs(center_y - world.cell_px * 0.5)) >= 50.0,
                "public phone remained at the curb-facing half-cell center")

    lamps = [item for item in world.objects if item.get("lighting_kind") == "sidewalk_lamp"]
    require(len(lamps) >= 80 and all(item.get("overhead") and item.get("decorative_only") for item in lamps),
            "street lamps are not exclusively walk-under overhead art")
    require(all(float(item.get("collision_radius_px", 0)) == 0.0 for item in lamps),
            "an overhead lamp still blocks pedestrians")

    canopies = [item for item in world.objects if item.get("silhouette_kind") == "facade_break"]
    require(canopies and all(item.get("overhead") for item in canopies), "canopies are not overhead")
    require(all(int(item.get("width_px", 0)) >= 330 and int(item.get("height_px", 0)) >= 130 for item in canopies),
            "a canopy is not approximately three times its former 112x44 size")
    require(all("wall_attached" in str(item.get("placement_policy", "")) for item in canopies),
            "a canopy is detached from its building wall")

    gwb = [item for item in world.objects if item.get("landmark_kind") == "george_washington_bridge"]
    require(len(gwb) == 9 and all(abs(int(item["gx"]) - world.width // 2) <= 5 for item in gwb),
            "George Washington Bridge is not restored at map center")
    return {
        "road_closures": dict(closures),
        "public_phones": len(phones),
        "overhead_lamps": len(lamps),
        "triple_scale_canopies": len(canopies),
        "gwb_pieces": len(gwb),
    }


def _sprite_orientation_audit() -> dict:
    expected = {
        "free-pixel-cars-link-in-comments-v0-fujphf59vg661.png#004",
        "free-pixel-cars-link-in-comments-v0-xs01xj2gvg661.webp#006",
    }
    require(all(vehicle_art.SOURCE_NOSE_CORRECTIONS.get(name) == "up" for name in expected),
            "gridcar005/gridcar015 nose corrections are incomplete")
    require(str(server._traffic_asset(4).get("source_name")) in expected,
            "gridcar005 no longer resolves to its corrected source cell")
    require(str(server._traffic_asset(14).get("source_name")) in expected,
            "gridcar015 no longer resolves to its corrected source cell")
    repaired = {
        str(server._traffic_asset(index).get("source_name"))
        for index in (30, 31, 34)
    }
    require(repaired == vehicle_art.REAR_CROP_REPAIR_SOURCES,
            f"reported clipped vehicle exports are not all repaired: {sorted(repaired)}")
    return {
        "gridcar005": "nose_up",
        "gridcar015": "nose_up",
        "closed_rear_crops": sorted(repaired),
    }


def _pedestrian_companion_audit(world) -> dict:
    routes = list(server.ACTIVE_MAP.get("npc_routes", []) or [])
    blocked_waypoints = []
    for route in routes:
        for point in server._route_points(route):
            gx, gy = world.world_to_cell(float(point[0]), float(point[1]))
            if v110_pedestrian_connectivity.is_building_cell(world, gx, gy):
                blocked_waypoints.append((str(route.get("id", "")), point))
    require(not blocked_waypoints,
            f"pedestrian routes still cross building/object footprints: {blocked_waypoints[:3]}")

    dt = 1.0 / 60.0
    for tick in range(int(12.0 / dt)):
        server.update_npcs(dt, [], tick, server_time=tick * dt)

    pedestrians = [npc for npc in server.npc_pedestrians if npc.kind == "pedestrian"]
    require(pedestrians, "pedestrian population is missing")
    inside = [
        npc.npc_id for npc in pedestrians
        if v110_pedestrian_connectivity.is_building_cell(world, *world.world_to_cell(npc.x, npc.y))
    ]
    require(not inside, f"pedestrians entered building/object footprints: {inside[:8]}")
    rooftop_npcs = [
        npc for npc in server.npc_pedestrians
        if int(getattr(npc, "level", 0)) == 1
    ]
    invalid_rooftop_roles = [npc.npc_id for npc in rooftop_npcs if npc.kind not in {"buyer", "supplier"}]
    require(not invalid_rooftop_roles,
            f"non-job NPCs appeared on building/rooftop footprints: {invalid_rooftop_roles[:8]}")
    require(len(rooftop_npcs) == 20 and all(world.circle_roof_walkable(npc.x, npc.y, server.PLAYER_RADIUS) for npc in rooftop_npcs),
            "all 20 supplier/buyer NPCs were not placed on accessible rooftops")
    require(all(int(getattr(npc, "level", 0)) == 0 for npc in server.npc_pedestrians if npc.kind in {"pedestrian", "dog"}),
            "an ambient pedestrian or dog leaked onto a rooftop")

    max_cluster = 0
    for npc in pedestrians:
        local_count = sum(math.hypot(npc.x - other.x, npc.y - other.y) < 72.0 for other in pedestrians)
        max_cluster = max(max_cluster, local_count)
    require(max_cluster <= 8, f"pedestrians still form a visibly stuck cluster: {max_cluster}")

    by_id = {npc.npc_id: npc for npc in server.npc_pedestrians}
    dogs = [npc for npc in server.npc_pedestrians if npc.kind == "dog"]
    require(len(dogs) == 3, "v2.8 requires exactly three distinct dog walkers")
    max_leash = 0.0
    for dog in dogs:
        walker = by_id.get(dog.companion_id)
        require(walker is not None and walker.kind == "pedestrian",
                f"dog has no paired pedestrian: {dog.npc_id}")
        require(walker.companion_id == dog.npc_id,
                f"dog/walker pairing is not reciprocal: {dog.npc_id}")
        dx, dy = dog.x - walker.x, dog.y - walker.y
        distance = math.hypot(dx, dy)
        max_leash = max(max_leash, distance)
        require(distance <= server.DOG_MAX_LEASH_LENGTH,
                f"dog exceeded leash length: {dog.npc_id} {distance:.1f}")
        require(dx * math.cos(walker.aim) + dy * math.sin(walker.aim) > 0.0,
                f"dog is not walking in front of its pedestrian: {dog.npc_id} "
                f"dog=({dog.x:.1f},{dog.y:.1f}) walker=({walker.x:.1f},{walker.y:.1f}) "
                f"aim={walker.aim:.3f} surface={world.collision_at('ground', walker.x, walker.y)}")

    car = next(car for car in server.traffic_vehicles if not car.parked)
    car.turn_signal = 1
    signal_multiplier = server.player_signal_turn_multiplier(car, 1.0)
    require(signal_multiplier > 1.0 and server.player_signal_turn_multiplier(car, -1.0) == 1.0,
            "indicator-assisted player turning is not direction-sensitive")
    # This audit fixture is an AI traffic car in the next test. Restore its
    # neutral signal state so the assertion cannot perturb traffic scheduling.
    car.turn_signal = 0
    return {
        "pedestrians_outside_buildings": len(pedestrians),
        "allowed_rooftop_npc_roles": sorted({npc.kind for npc in rooftop_npcs}),
        "max_local_cluster_72px": max_cluster,
        "paired_dog_walkers": len(dogs),
        "max_leash_px": round(max_leash, 3),
        "matching_indicator_turn_multiplier": round(signal_multiplier, 3),
    }


def _traffic_audit() -> dict:
    moving = [car for car in server.traffic_vehicles if not car.parked]
    require(len(moving) == 28, f"expected 28 moving traffic cars, got {len(moving)}")
    overlaps: set[tuple[str, str]] = set()
    max_junction_time = 0.0
    dt = 1.0 / 60.0
    for tick in range(int(20.0 / dt)):
        server.update_traffic(dt, [], tick * dt)
        # Production advances both simulations every tick. Freezing pedestrians
        # after the companion audit can strand a crosswalk occupant in front of
        # traffic for the full test and create an artificial junction timeout.
        server.update_npcs(dt, [], tick, server_time=12.0 + tick * dt)
        max_junction_time = max(max_junction_time, *(car.junction_time for car in moving))
        if tick % 12 == 0:
            overlaps.update(_overlap_pairs())
    require(not overlaps, f"cars overlapped/stuck together: {sorted(overlaps)[:6]}")
    require(max_junction_time < 12.0,
            f"a car remained in an intersection too long: {max_junction_time:.3f}s")

    # Report #174 asks for an explicit lone-car regression test. Keep one real
    # runtime car and require broad route progress without triggering the orbit
    # detector used by production recovery.
    server.TRAFFIC_COUNT = 1
    v110_grid_population.prepare_and_initialize(server, server.ACTIVE_MAP, server.GRID_WORLD)
    isolated = [car for car in server.traffic_vehicles if not car.parked]
    require(len(isolated) == 1, "isolated-car test did not initialize exactly one moving car")
    lone = isolated[0]
    server.traffic_vehicles[:] = [lone]
    server.npc_pedestrians.clear()
    server.bicycles.clear()
    v110_traffic_recovery._ORBIT_TRACK.clear()
    server._v110_traffic_recovery_stats = {}
    distance = 0.0
    visited: set[tuple[int, int]] = set()
    isolated_seconds = 60.0
    for tick in range(int(isolated_seconds / dt)):
        before = (lone.x, lone.y)
        server.update_traffic(dt, [], 20.0 + tick * dt)
        distance += math.hypot(lone.x - before[0], lone.y - before[1])
        visited.add(server.GRID_WORLD.world_to_cell(lone.x, lone.y))
    stats = dict(getattr(server, "_v110_traffic_recovery_stats", {}) or {})
    require(distance >= 1200.0 and len(visited) >= 8,
            f"isolated car failed broad route progress: distance={distance:.1f}, cells={len(visited)}")
    require(int(stats.get("orbit_detections", 0)) == 0,
            f"isolated car entered a tight orbit: {stats}")
    return {
        "multi_car_seconds": 20,
        "overlap_pairs": [],
        "max_junction_seconds": round(max_junction_time, 3),
        "isolated_car_seconds": int(isolated_seconds),
        "isolated_distance_px": round(distance, 3),
        "isolated_cells_visited": len(visited),
        "orbit_detections": 0,
    }


def main() -> int:
    world = v100_server.load_ground_grid()
    config = copy.deepcopy(get_map())
    old_map, old_world, old_grid = server.ACTIVE_MAP, server.GRID_WORLD, server.GRID_RUNTIME_ACTIVE
    old_count, old_max = server.TRAFFIC_COUNT, server.MAX_PLAYERS
    old_traffic, old_npcs = list(server.traffic_vehicles), list(server.npc_pedestrians)
    try:
        server.ACTIVE_MAP = config
        server.GRID_WORLD = world
        server.GRID_RUNTIME_ACTIVE = True
        server.TRAFFIC_COUNT = 28
        errors = v100_server.validate_active_authority(config)
        require(not errors, f"GridWorld population failed: {errors}")
        v110_grid_population.prepare_and_initialize(server, config, world)
        buildings = asyncio.run(_building_and_capacity_audit(world, config))
        map_art = _map_art_audit(world)
        sprites = _sprite_orientation_audit()
        companions = _pedestrian_companion_audit(world)
        traffic = _traffic_audit()
    finally:
        server.ACTIVE_MAP, server.GRID_WORLD, server.GRID_RUNTIME_ACTIVE = old_map, old_world, old_grid
        server.TRAFFIC_COUNT, server.MAX_PLAYERS = old_count, old_max
        server.traffic_vehicles[:] = old_traffic
        server.npc_pedestrians[:] = old_npcs

    results = {
        "reports": "#165-#184",
        "buildings_and_capacity": buildings,
        "map_art": map_art,
        "sprite_orientation": sprites,
        "pedestrians_and_dog_walkers": companions,
        "traffic": traffic,
        "release_status": "ready_for_v2.5_release_gate",
    }
    print("V2.5 CURRENT REPORTS AUDIT: PASS")
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
