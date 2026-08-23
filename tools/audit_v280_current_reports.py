"""Focused behavioral release gate for reports #185-#197 and the v2.8 map restoration."""

from __future__ import annotations

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

from common import PlayerState, empty_inventory, get_map, inventory_count
import server
import v100_server
import v110_grid_population
import vehicle_art
from grid_renderer import GridRenderer
import v110_pedestrian_connectivity


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


class CaptureSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send(self, raw: str) -> None:
        self.messages.append(json.loads(raw))


def _bridge_audit(world) -> dict:
    pieces = [row for row in world.objects if row.get("landmark_kind") == "george_washington_bridge"]
    require(len(pieces) == 9, f"expected nine GWB pieces, got {len(pieces)}")
    require(all(abs(int(row["gx"]) - world.width // 2) <= 5 for row in pieces),
            "George Washington Bridge is not at the map midpoint")
    require(all(row.get("placement_policy") == "central_highway_gwb_restore_v28" for row in pieces),
            "George Washington Bridge is missing the v2.8 restoration authority")
    river = dict(world.data.get("runtime_refinement", {}).get("hudson_river", {}) or {})
    river_columns = tuple(map(int, river.get("columns", ())))
    bridge_rows = set(map(int, river.get("bridge_rows", ())))
    require(len(river_columns) == 3 and int(river.get("water_cell_count", 0)) == 123,
            f"Hudson channel is incomplete: {river}")
    for gy in range(world.height):
        for gx in river_columns:
            collision = world.collision_at("ground", *world.cell_center(gx, gy))
            if gy in bridge_rows:
                require(collision == "road", f"GWB deck is not traversable at {(gx, gy)}")
            else:
                require(world.tile_id("ground", gx, gy) == "hudson_water_night" and collision == "blocked",
                        f"Hudson channel leaks city ground at {(gx, gy)}")
    return {
        "piece_count": len(pieces),
        "center_cell": [world.width // 2, world.height // 2],
        "piece_cells": sorted([[int(row["gx"]), int(row["gy"])] for row in pieces]),
        "hudson_columns": list(river_columns),
        "hudson_water_cells": int(river["water_cell_count"]),
        "bridge_deck_rows": sorted(bridge_rows),
    }


def _late_report_audit(world) -> dict:
    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    require("draw_rooftop_view" in client_source and "level_npcs" in client_source,
            "Ground view does not draw both rooftop players and rooftop NPCs")
    require(GridRenderer.ROOFTOP_BACKGROUND_BLUR_DIVISOR >= 12,
            "rooftop city backdrop is not strongly blurred")

    checker = __import__("pygame").Surface((280, 140))
    for y in range(checker.get_height()):
        for x in range(checker.get_width()):
            shade = 255 if (x + y) % 2 else 0
            checker.set_at((x, y), (shade, shade, shade))

    def edge_energy(surface) -> int:
        return sum(
            abs(surface.get_at((x, y)).r - surface.get_at((x + 1, y)).r)
            for y in range(surface.get_height())
            for x in range(surface.get_width() - 1)
        )

    before = edge_energy(checker)
    GridRenderer._apply_rooftop_background_blur(checker)
    after = edge_energy(checker)
    require(after <= before * 0.10, f"rooftop background retained readable Ground detail: {after}/{before}")

    closures: dict[str, list[dict]] = {}
    for item in world.objects:
        closure_id = str(item.get("road_closure_id", ""))
        if closure_id:
            closures.setdefault(closure_id, []).append(item)
    require(len(closures) == 3 and all(len(rows) == 5 for rows in closures.values()),
            f"expected three five-cone road closures: { {key: len(value) for key, value in closures.items()} }")
    closure_spacings = {}
    for closure_id, rows in closures.items():
        rows.sort(key=lambda row: int(row["road_closure_slot"]))
        centers = [(
            int(row["gx"]) * world.cell_px + int(row.get("offset_x_px", 0)) + int(row["width_px"]) * 0.5,
            int(row["gy"]) * world.cell_px + int(row.get("offset_y_px", 0)) + int(row["height_px"]) * 0.5,
        ) for row in rows]
        spacings = [math.hypot(bx - ax, by - ay) for (ax, ay), (bx, by) in zip(centers, centers[1:])]
        require(min(spacings) > max(int(row["width_px"]) for row in rows),
                f"{closure_id} cones still overlap: {spacings}")
        require(max(spacings) - min(spacings) <= 1.1,
                f"{closure_id} cones are not evenly spaced: {spacings}")
        edge = str(rows[0]["road_closure_edge"])
        x_span = max(x for x, _y in centers) - min(x for x, _y in centers)
        y_span = max(y for _x, y in centers) - min(y for _x, y in centers)
        require((edge in {"east", "west"} and x_span > y_span)
                or (edge in {"north", "south"} and y_span > x_span),
                f"{closure_id} does not cross the road from its {edge} edge")
        closure_spacings[closure_id] = [round(value, 3) for value in spacings]

    require(not any(item.get("density_kind") == "street_edge_awning" for item in world.objects),
            "the reported road tarp/loose street-edge awning remains")
    require(not any(str(item.get("street_marking", "")).startswith("six_lane_divider_") for item in world.objects),
            "the reported thick displaced white lane bars remain")

    connectivity = v110_pedestrian_connectivity.audit(world)
    require(float(connectivity.get("pedestrian_surface_coverage_ratio", 0.0)) >= 0.999,
            f"NPC patrols do not use all sidewalk cells: {connectivity}")
    return {
        "rooftop_background_blur_divisor": GridRenderer.ROOFTOP_BACKGROUND_BLUR_DIVISOR,
        "blur_edge_energy_ratio": round(after / max(1, before), 6),
        "ground_sees_rooftop_players_and_npcs": True,
        "road_closure_spacing_px": closure_spacings,
        "loose_road_awnings": 0,
        "displaced_white_lane_bars": 0,
        "pedestrian_surface_cells": int(connectivity["pedestrian_surface_cell_count"]),
        "pedestrian_surface_coverage_ratio": float(connectivity["pedestrian_surface_coverage_ratio"]),
    }


def _population_and_stability_audit(world) -> dict:
    moving = [car for car in server.traffic_vehicles if not car.parked]
    pedestrians = [npc for npc in server.npc_pedestrians if npc.kind == "pedestrian"]
    dogs = [npc for npc in server.npc_pedestrians if npc.kind == "dog"]
    jobs = [npc for npc in server.npc_pedestrians if npc.kind in {"supplier", "buyer"}]
    require(len(moving) == 28, f"moving traffic was not halved to 28: {len(moving)}")
    require(len(pedestrians) == 108, f"ambient pedestrians were not halved to 108: {len(pedestrians)}")
    require(len(dogs) == 3, f"expected exactly three dogs, got {len(dogs)}")
    require(len(jobs) == 20 and len(server.npc_pedestrians) == 131,
            f"unexpected NPC role totals: jobs={len(jobs)} total={len(server.npc_pedestrians)}")

    start = {car.vehicle_id: (car.x, car.y) for car in moving}
    overlaps: set[tuple[str, str]] = set()
    dt = 1.0 / 60.0
    for tick in range(int(20.0 / dt)):
        server.update_traffic(dt, [], tick * dt)
        server.update_npcs(dt, [], tick, server_time=tick * dt)
        if tick % 12:
            continue
        for index, car in enumerate(moving):
            for other in moving[index + 1:]:
                if server._oriented_boxes_overlap(
                    car.x, car.y, car.angle, car.collision_length, car.collision_width,
                    other.x, other.y, other.angle, other.collision_length, other.collision_width,
                ):
                    overlaps.add(tuple(sorted((car.vehicle_id, other.vehicle_id))))
    require(not overlaps, f"traffic overlap remained after density reduction: {sorted(overlaps)[:6]}")
    moved = {
        car.vehicle_id: round(math.hypot(car.x - start[car.vehicle_id][0], car.y - start[car.vehicle_id][1]), 3)
        for car in moving
    }
    require(sum(distance >= 60.0 for distance in moved.values()) >= 24,
            f"too many traffic cars failed to make route progress: {moved}")

    max_cluster = max(
        sum(math.hypot(npc.x - other.x, npc.y - other.y) < 72.0 for other in pedestrians)
        for npc in pedestrians
    )
    require(max_cluster <= 8, f"pedestrian cluster remained too dense: {max_cluster}")
    # Authored crosswalk links briefly occupy road-collision cells; blocked,
    # water, and building cells remain forbidden.
    require(all(world.collision_at("ground", npc.x, npc.y) in {"walk", "sidewalk", "road"} for npc in pedestrians),
            "an ambient pedestrian left the pavement/crosswalk network")
    return {
        "moving_traffic": len(moving),
        "ambient_pedestrians": len(pedestrians),
        "dogs": len(dogs),
        "rooftop_jobs": len(jobs),
        "npc_total": len(server.npc_pedestrians),
        "simulation_seconds": 20,
        "traffic_overlap_pairs": [],
        "cars_with_60px_progress": sum(distance >= 60.0 for distance in moved.values()),
        "max_pedestrian_cluster_72px": max_cluster,
    }


def _rooftop_and_companion_audit(config: dict, world) -> dict:
    locations = list(config.get("job_locations", []) or [])
    jobs = [npc for npc in server.npc_pedestrians if npc.kind in {"supplier", "buyer"}]
    ambient = [npc for npc in server.npc_pedestrians if npc.kind in {"pedestrian", "dog"}]
    require(len(locations) == len(jobs) == 20, "the complete rooftop job roster is missing")
    require(len({row.get("building_id") for row in locations}) == 20,
            "job NPCs do not occupy distinct buildings")
    require(all(int(row.get("level", 0)) == 1 for row in locations),
            "a supplier/buyer location is not on roof level 1")
    require(all(int(npc.level) == 1 and world.circle_roof_walkable(npc.x, npc.y, server.PLAYER_RADIUS) for npc in jobs),
            "a supplier/buyer NPC is not on an accessible roof")
    require(all(int(npc.level) == 0 for npc in ambient),
            "an ambient pedestrian or dog appeared on a rooftop")

    by_id = {npc.npc_id: npc for npc in server.npc_pedestrians}
    dogs = [npc for npc in server.npc_pedestrians if npc.kind == "dog"]
    walkers: set[str] = set()
    max_leash = 0.0
    for dog in dogs:
        walker = by_id.get(dog.companion_id)
        require(walker is not None and walker.kind == "pedestrian", f"dog lacks walker: {dog.npc_id}")
        require(walker.companion_id == dog.npc_id, f"dog/walker link is not reciprocal: {dog.npc_id}")
        require(walker.npc_id not in walkers, f"walker has more than one dog: {walker.npc_id}")
        walkers.add(walker.npc_id)
        dx, dy = dog.x - walker.x, dog.y - walker.y
        leash = math.hypot(dx, dy)
        max_leash = max(max_leash, leash)
        require(leash <= server.DOG_MAX_LEASH_LENGTH, f"dog exceeded leash: {dog.npc_id}")
        require(dx * math.cos(walker.aim) + dy * math.sin(walker.aim) > 0.0,
                f"dog is not leading walker: {dog.npc_id}")
    return {
        "job_npcs": len(jobs),
        "distinct_rooftops": len({row.get("building_id") for row in locations}),
        "ambient_rooftop_npcs": 0,
        "one_to_one_dog_walkers": len(walkers),
        "max_leash_px": round(max_leash, 3),
    }


def _art_audit(world) -> dict:
    source = "free-pixel-cars-link-in-comments-v0-fujphf59vg661.png#003"
    require(vehicle_art.SOURCE_NOSE_CORRECTIONS.get(source) == "up",
            "reported backwards parked-car source has no nose correction")
    require(str(server._parked_asset(3).get("source_name")) == source,
            "reported parked car no longer resolves to the corrected source")

    planters = [
        row for row in world.objects
        if row.get("scale_policy") == "sidewalk_fit_tree_planter_scale_1_5x_v28"
    ]
    require(planters, "v2.8 sidewalk-fit planters are missing")
    require(all(int(row["width_px"]) < world.cell_px and int(row["height_px"]) < world.cell_px for row in planters),
            "a reported planter is still larger than one runtime pavement cell")
    require(all(float(row.get("collision_radius_px", 0.0)) <= world.cell_px * 0.32 for row in planters),
            "a reported planter still blocks the pavement cell")
    return {
        "corrected_parked_source": source,
        "nose_direction": "up",
        "sidewalk_fit_planters": len(planters),
        "planter_dimensions": sorted({(int(row["width_px"]), int(row["height_px"])) for row in planters}),
        "runtime_cell_px": world.cell_px,
    }


async def _interaction_audit(config: dict) -> dict:
    ai_car = next(car for car in server.traffic_vehicles if not car.parked)
    ai_car.controlled_by = ""
    ai_car.npc_driver = True
    ai_car.speed = 0.0
    passenger = PlayerState("v28-passenger", "PassengerAudit", ai_car.x + 30.0, ai_car.y, level=0)
    passenger_socket = CaptureSocket()
    passenger_session = server.ClientSession(passenger_socket, passenger, "15550000280", empty_inventory())
    await server.process_passenger_action(passenger_session)
    require(passenger_session.passenger_vehicle_id == ai_car.vehicle_id,
            "E did not board the occupied AI car")
    require(passenger.vehicle_role == "passenger" and passenger.player_id in ai_car.passenger_ids,
            "AI-car passenger authority is incomplete")

    supplier = next(row for row in config["job_locations"] if row["role"] == "supplier")
    sx, sy = map(float, supplier["pos"])
    shopper = PlayerState("v28-shopper", "RooftopAudit", sx, sy, cash=200, level=1)
    shop_socket = CaptureSocket()
    shop_session = server.ClientSession(shop_socket, shopper, "15550000281", empty_inventory())
    await server.process_interaction(shop_session)
    require(inventory_count(shop_session.inventory, "package") == 1 and shopper.cash == 200 - server.BUY_PRICE,
            f"same-level rooftop supplier interaction failed: cash={shopper.cash} "
            f"packages={inventory_count(shop_session.inventory, 'package')} messages={shop_socket.messages}")

    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    require(client_source.count('car.driver in {"player", "npc"}') >= 2,
            "client E prompt/dispatch does not include AI-driven cars")
    return {
        "ai_vehicle_passenger_boarded": ai_car.vehicle_id,
        "passenger_role": passenger.vehicle_role,
        "rooftop_supplier_purchase": str(supplier["id"]),
    }


def main() -> int:
    world = v100_server.load_ground_grid()
    config = copy.deepcopy(get_map())
    old_map, old_world, old_grid = server.ACTIVE_MAP, server.GRID_WORLD, server.GRID_RUNTIME_ACTIVE
    old_count, old_use_mysql = server.TRAFFIC_COUNT, server.USE_MYSQL
    old_traffic, old_npcs = list(server.traffic_vehicles), list(server.npc_pedestrians)
    old_accounts = copy.deepcopy(server.memory_accounts)
    try:
        server.ACTIVE_MAP = config
        server.GRID_WORLD = world
        server.GRID_RUNTIME_ACTIVE = True
        server.TRAFFIC_COUNT = 28
        server.USE_MYSQL = False
        errors = v100_server.validate_active_authority(config)
        require(not errors, f"GridWorld initialization failed: {errors}")
        results = {
            "reports": "#185-#197",
            "bridge": _bridge_audit(world),
            "population_and_stability": _population_and_stability_audit(world),
            "rooftops_and_companions": _rooftop_and_companion_audit(config, world),
            "art": _art_audit(world),
            "interactions": asyncio.run(_interaction_audit(config)),
            "late_reports": _late_report_audit(world),
            "version": (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip(),
            "release_status": "ready_for_v2.8_release_gate",
        }
    finally:
        server.ACTIVE_MAP, server.GRID_WORLD, server.GRID_RUNTIME_ACTIVE = old_map, old_world, old_grid
        server.TRAFFIC_COUNT = old_count
        server.USE_MYSQL = old_use_mysql
        server.traffic_vehicles[:] = old_traffic
        server.npc_pedestrians[:] = old_npcs
        server.memory_accounts.clear()
        server.memory_accounts.update(old_accounts)

    require(results["version"] == "2.8", "release version is not 2.8")
    print("V2.8 CURRENT REPORTS AUDIT: PASS")
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
