from __future__ import annotations

"""GridWorld-native surface population for Open Night v1.1.

The v1.0 GridWorld intentionally disabled legacy vector-map traffic and NPC routes.
This module derives deterministic car loops from the centers of the three-cell road
bands and pedestrian walks from pavement connectivity, then feeds those routes into
the mature server-authoritative AI/networking systems.
"""

from collections import deque
import math
from typing import Iterable

TRAFFIC_ROUTE_LIMIT = 24
PEDESTRIAN_ROUTE_LIMIT = 18
PEDESTRIAN_TARGET = 36


def _group_runs(values: Iterable[int]) -> list[list[int]]:
    values = sorted(set(int(v) for v in values))
    groups: list[list[int]] = []
    for value in values:
        if not groups or value != groups[-1][-1] + 1:
            groups.append([value])
        else:
            groups[-1].append(value)
    return groups


def _cell_collision(world, gx: int, gy: int) -> str:
    if not world.in_bounds(gx, gy):
        return "blocked"
    return str(world.tile("ground", gx, gy).collision)


def _is_road(world, gx: int, gy: int) -> bool:
    return _cell_collision(world, gx, gy) == "road"


def _is_pavement(world, gx: int, gy: int) -> bool:
    if not world.in_bounds(gx, gy):
        return False
    tile_id = str(world.tile_id("ground", gx, gy))
    collision = _cell_collision(world, gx, gy)
    return tile_id.startswith("pavement") and collision in {"walk", "sidewalk"}


def _major_road_centers(world) -> tuple[list[int], list[int]]:
    """Return one center row/column for each authored three-cell road band."""
    min_row_coverage = max(4, int(math.ceil(world.width * 0.55)))
    min_col_coverage = max(4, int(math.ceil(world.height * 0.55)))
    road_rows = [
        gy for gy in range(world.height)
        if sum(_is_road(world, gx, gy) for gx in range(world.width)) >= min_row_coverage
    ]
    road_cols = [
        gx for gx in range(world.width)
        if sum(_is_road(world, gx, gy) for gy in range(world.height)) >= min_col_coverage
    ]
    row_centers = [run[len(run) // 2] for run in _group_runs(road_rows)]
    col_centers = [run[len(run) // 2] for run in _group_runs(road_cols)]
    return row_centers, col_centers


def _segment_surface(world, a: tuple[float, float], b: tuple[float, float], collision: str) -> bool:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    steps = max(1, int(math.ceil(length / max(8.0, world.cell_px / 4.0))))
    for step in range(steps + 1):
        t = step / steps
        x, y = a[0] + dx * t, a[1] + dy * t
        gx, gy = world.world_to_cell(x, y)
        if _cell_collision(world, gx, gy) != collision:
            return False
    return True


def _build_traffic_routes(world) -> list[dict]:
    rows, cols = _major_road_centers(world)
    routes: list[dict] = []
    lane_offset = max(14.0, world.cell_px * 0.18)
    turn_radius = max(16.0, world.cell_px * 0.17)
    speed_limit = max(80.0, world.cell_px * 0.86)
    for row_index in range(len(rows) - 1):
        for col_index in range(len(cols) - 1):
            top, bottom = rows[row_index], rows[row_index + 1]
            left, right = cols[col_index], cols[col_index + 1]
            cells = [(left, top), (right, top), (right, bottom), (left, bottom)]
            points = [world.cell_center(gx, gy) for gx, gy in cells]
            if not all(_segment_surface(world, points[i], points[(i + 1) % 4], "road") for i in range(4)):
                continue
            routes.append({
                "id": f"grid_traffic_{row_index:02d}_{col_index:02d}",
                "waypoints": [[round(x, 3), round(y, 3)] for x, y in points],
                "speed_limit": speed_limit,
                "lane_offset": lane_offset,
                "turn_radius": turn_radius,
                "grid_native": True,
            })
            if len(routes) >= TRAFFIC_ROUTE_LIMIT:
                return routes
    return routes


def _neighbors(cell: tuple[int, int], allowed: set[tuple[int, int]]) -> list[tuple[int, int]]:
    x, y = cell
    candidates = ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1))
    return [candidate for candidate in candidates if candidate in allowed]


def _components(allowed: set[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    remaining = set(allowed)
    groups: list[list[tuple[int, int]]] = []
    while remaining:
        seed = min(remaining, key=lambda p: (p[1], p[0]))
        remaining.remove(seed)
        q = deque([seed])
        group = [seed]
        while q:
            node = q.popleft()
            for nxt in _neighbors(node, remaining):
                remaining.remove(nxt)
                q.append(nxt)
                group.append(nxt)
        groups.append(group)
    groups.sort(key=lambda group: (-len(group), min(y for _, y in group), min(x for x, _ in group)))
    return groups


def _closed_tree_walk(component: list[tuple[int, int]]) -> list[tuple[int, int]]:
    allowed = set(component)
    root = min(component, key=lambda p: (p[1], p[0]))
    visited = {root}
    walk = [root]

    def visit(node: tuple[int, int]) -> None:
        for nxt in _neighbors(node, allowed):
            if nxt in visited:
                continue
            visited.add(nxt)
            walk.append(nxt)
            visit(nxt)
            walk.append(node)

    visit(root)
    if len(walk) > 1 and walk[-1] == walk[0]:
        walk.pop()
    return walk


def _build_pedestrian_routes(world) -> list[dict]:
    pavement = {
        (gx, gy)
        for gy in range(world.height)
        for gx in range(world.width)
        if _is_pavement(world, gx, gy)
    }
    routes: list[dict] = []
    for component in _components(pavement):
        if len(component) < 5:
            continue
        cells = _closed_tree_walk(component)
        if len(cells) < 4:
            continue
        points = [world.cell_center(gx, gy) for gx, gy in cells]
        if not all(_segment_surface(world, points[i], points[(i + 1) % len(points)], "walk") or
                   _segment_surface(world, points[i], points[(i + 1) % len(points)], "sidewalk")
                   for i in range(len(points))):
            valid = True
            for i in range(len(points)):
                a, b = points[i], points[(i + 1) % len(points)]
                dx, dy = b[0] - a[0], b[1] - a[1]
                steps = max(1, int(math.ceil(math.hypot(dx, dy) / max(8.0, world.cell_px / 4.0))))
                for step in range(steps + 1):
                    t = step / steps
                    gx, gy = world.world_to_cell(a[0] + dx * t, a[1] + dy * t)
                    if not _is_pavement(world, gx, gy):
                        valid = False
                        break
                if not valid:
                    break
            if not valid:
                continue
        routes.append({
            "id": f"grid_ped_{len(routes):02d}",
            "waypoints": [[round(x, 3), round(y, 3)] for x, y in points],
            "speed": max(42.0, world.cell_px * 0.43),
            "turn_radius": 0.0,
            "grid_native": True,
        })
        if len(routes) >= PEDESTRIAN_ROUTE_LIMIT:
            break
    return routes


def _traffic_starts(routes: list[dict], count: int) -> list[dict]:
    if not routes or count <= 0:
        return []
    starts = []
    for index in range(max(0, min(120, int(count)))):
        route_index = index % len(routes)
        lap = index // len(routes)
        fraction = (0.11 + route_index * 0.071 + lap * 0.29) % 1.0
        starts.append({
            "id": f"gridcar{index + 1:03d}",
            "route_id": routes[route_index]["id"],
            "start_fraction": round(fraction, 6),
            "asset_index": index,
            "speed_scale": 0.92 + (index % 4) * 0.02,
        })
    return starts


def _pedestrian_starts(routes: list[dict], target: int = PEDESTRIAN_TARGET) -> list[dict]:
    if not routes:
        return []
    starts = []
    target = max(len(routes), int(target))
    for index in range(target):
        route_index = index % len(routes)
        lap = index // len(routes)
        fraction = (0.08 + route_index * 0.113 + lap * 0.31) % 1.0
        starts.append({
            "id": f"gridnpc{index + 1:03d}",
            "route_id": routes[route_index]["id"],
            "start_fraction": round(fraction, 6),
            "appearance_index": index,
            "speed_scale": 0.90 + (index % 5) * 0.025,
        })
    return starts


def _grid_vehicle_blocked(world, car, x: float, y: float, angle: float) -> bool:
    hl = max(12.0, float(car.collision_length) * 0.5)
    hw = max(8.0, float(car.collision_width) * 0.5)
    ca, sa = math.cos(angle), math.sin(angle)
    probes = [
        (x, y),
        (x + ca * hl, y + sa * hl), (x - ca * hl, y - sa * hl),
        (x - sa * hw, y + ca * hw), (x + sa * hw, y - ca * hw),
        (x + ca * hl - sa * hw, y + sa * hl + ca * hw),
        (x + ca * hl + sa * hw, y + sa * hl - ca * hw),
        (x - ca * hl - sa * hw, y - sa * hl + ca * hw),
        (x - ca * hl + sa * hw, y - sa * hl - ca * hw),
    ]
    return any(world.collision_at("ground", px, py) != "road" for px, py in probes)


def install(server_module, world) -> None:
    """Make vehicle body collision obey the same GridWorld as player collision."""
    original = getattr(server_module, "_v110_original_vehicle_map_blocked", None)
    if original is None:
        original = server_module._vehicle_map_blocked
        server_module._v110_original_vehicle_map_blocked = original

    def vehicle_map_blocked(car, x: float, y: float, angle: float) -> bool:
        if bool(getattr(server_module, "GRID_RUNTIME_ACTIVE", False)) and world is not None:
            return _grid_vehicle_blocked(world, car, x, y, angle)
        return original(car, x, y, angle)

    server_module._vehicle_map_blocked = vehicle_map_blocked


def prepare_and_initialize(server_module, map_config: dict, world) -> dict:
    """Derive GridWorld routes and populate the mature server AI systems."""
    install(server_module, world)
    traffic_routes = _build_traffic_routes(world)
    pedestrian_routes = _build_pedestrian_routes(world)
    if not traffic_routes:
        raise RuntimeError("v1.1 GridWorld population found no safe traffic loops")
    if not pedestrian_routes:
        raise RuntimeError("v1.1 GridWorld population found no safe pavement routes")

    traffic_count = max(0, int(getattr(server_module, "TRAFFIC_COUNT", 0)))
    map_config["traffic_routes"] = traffic_routes
    map_config["traffic_starts"] = _traffic_starts(traffic_routes, traffic_count)
    map_config["npc_routes"] = pedestrian_routes
    map_config["npc_starts"] = _pedestrian_starts(pedestrian_routes)
    map_config["parked_vehicle_spawns"] = []
    map_config["bicycle_routes"] = []
    map_config["bicycle_starts"] = []
    map_config["parked_bicycle_spawns"] = []

    server_module.traffic_vehicles.clear()
    server_module.bicycles.clear()
    server_module.npc_pedestrians.clear()
    server_module.initialize_traffic(traffic_count)
    server_module.initialize_npcs()
    server_module.initialize_hydrants()

    safe_cars = []
    for car in server_module.traffic_vehicles:
        if _grid_vehicle_blocked(world, car, car.x, car.y, car.angle):
            continue
        if any(server_module._oriented_boxes_overlap(
            car.x, car.y, car.angle, car.collision_length, car.collision_width,
            other.x, other.y, other.angle, other.collision_length, other.collision_width,
        ) for other in safe_cars):
            continue
        safe_cars.append(car)
    server_module.traffic_vehicles[:] = safe_cars

    if traffic_count > 0 and not server_module.traffic_vehicles:
        raise RuntimeError("v1.1 GridWorld traffic requested but every car spawn was rejected")
    if not server_module.npc_pedestrians:
        raise RuntimeError("v1.1 GridWorld pedestrian initialization produced no NPCs")

    audit = {
        "authority": "gridworld_native_surface_population",
        "traffic_route_count": len(traffic_routes),
        "traffic_requested": traffic_count,
        "traffic_spawned": len(server_module.traffic_vehicles),
        "pedestrian_route_count": len(pedestrian_routes),
        "pedestrians_spawned": sum(1 for npc in server_module.npc_pedestrians if npc.kind == "pedestrian"),
        "dogs_spawned": sum(1 for npc in server_module.npc_pedestrians if npc.kind == "dog"),
        "road_center_rows": _major_road_centers(world)[0],
        "road_center_cols": _major_road_centers(world)[1],
        "grid_cell_px": world.cell_px,
    }
    map_config.setdefault("runtime", {})["legacy_surface_entities"] = False
    map_config["runtime"]["grid_native_surface_entities"] = True
    map_config["runtime"]["grid_population_audit"] = audit
    return audit
