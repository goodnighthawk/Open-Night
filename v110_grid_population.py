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

TRAFFIC_ROUTE_LIMIT = 84
PEDESTRIAN_ROUTE_LIMIT = 18
PEDESTRIAN_TARGET = 216


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


def _build_traffic_signals(world) -> list[dict]:
    """Place four synchronized, road-facing fixtures at every grid junction."""
    min_row_coverage = max(4, int(math.ceil(world.width * 0.55)))
    min_col_coverage = max(4, int(math.ceil(world.height * 0.55)))
    row_runs = _group_runs([
        gy for gy in range(world.height)
        if sum(_is_road(world, gx, gy) for gx in range(world.width)) >= min_row_coverage
    ])
    col_runs = _group_runs([
        gx for gx in range(world.width)
        if sum(_is_road(world, gx, gy) for gy in range(world.height)) >= min_col_coverage
    ])
    signals: list[dict] = []
    margin = max(10.0, world.cell_px * 0.12)
    for row_index, row_run in enumerate(row_runs):
        for col_index, col_run in enumerate(col_runs):
            north = row_run[0] * world.cell_px - margin
            south = (row_run[-1] + 1) * world.cell_px + margin
            west = col_run[0] * world.cell_px - margin
            east = (col_run[-1] + 1) * world.cell_px + margin
            junction_id = f"grid_junction_{row_index:02d}_{col_index:02d}"
            for orientation, pos, phase, axis in (
                ("nw", (west, north), 0, "east_west"),
                ("ne", (east, north), 1, "north_south"),
                ("se", (east, south), 0, "east_west"),
                ("sw", (west, south), 1, "north_south"),
            ):
                signals.append({
                    "id": f"{junction_id}_{orientation}",
                    "pos": [round(pos[0], 3), round(pos[1], 3)],
                    "phase": phase,
                    "orientation": orientation,
                    "junction_id": junction_id,
                    "controls_axis": axis,
                    "grid_native": True,
                })
    return signals


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
    # Three lanes in each direction fit the report-46 three-cell street: each
    # lane is one half-cell wide and remains large enough for normalized cars.
    # Three full-width lanes per direction inside each five-cell primary road.
    lane_width = world.cell_px * 5.0 / 6.0
    lane_offsets = tuple(lane_width * ratio for ratio in (0.5, 1.5, 2.5))
    turn_radius = max(24.0, world.cell_px * 0.28)
    speed_limit = max(80.0, world.cell_px * 0.86)
    # Traffic used to circle only one block forever. Build fourteen varied,
    # multi-block perimeter templates instead. Interleaving full-height, north,
    # and south row pairs distributes cars across the city while the stable
    # wide-first ordering gives the requested random-looking circulation without
    # making release proofs or multiplayer simulation nondeterministic.
    row_pairs: list[tuple[int, int]] = []
    for pair in ((0, len(rows) - 1), (0, 1), (len(rows) - 2, len(rows) - 1)):
        if 0 <= pair[0] < pair[1] < len(rows) and pair not in row_pairs:
            row_pairs.append(pair)
    rectangle_groups: list[list[tuple[int, int, int, int]]] = []
    for pair_index, (top_index, bottom_index) in enumerate(row_pairs):
        group = [
            (top_index, bottom_index, left_index, right_index)
            for left_index in range(len(cols) - 1)
            for right_index in range(left_index + 1, len(cols))
        ]
        group.sort(key=lambda item: (
            -(item[3] - item[2]),
            (item[2] * 47 + item[3] * 71 + pair_index * 97) % 1009,
            item[2], item[3],
        ))
        rectangle_groups.append(group)
    rectangles: list[tuple[int, int, int, int]] = []
    while len(rectangles) < 14 and any(rectangle_groups):
        for group in rectangle_groups:
            if group and len(rectangles) < 14:
                rectangles.append(group.pop(0))

    for rectangle_index, (top_index, bottom_index, left_index, right_index) in enumerate(rectangles):
        top, bottom = rows[top_index], rows[bottom_index]
        left, right = cols[left_index], cols[right_index]
        cells = (
            [(cols[index], top) for index in range(left_index, right_index + 1)]
            + [(right, rows[index]) for index in range(top_index + 1, bottom_index + 1)]
            + [(cols[index], bottom) for index in range(right_index - 1, left_index - 1, -1)]
            + [(left, rows[index]) for index in range(bottom_index - 1, top_index, -1)]
        )
        points = [world.cell_center(gx, gy) for gx, gy in cells]
        if not all(
            _segment_surface(world, points[i], points[(i + 1) % len(points)], "road")
            for i in range(len(points))
        ):
            continue
        for direction_name, directed_points in (("cw", points), ("ccw", list(reversed(points)))):
            for lane_index, lane_offset in enumerate(lane_offsets, start=1):
                # Signal every approach. Horizontal traffic uses phase 0;
                # vertical traffic uses phase 1. The server remaps these
                # authored corner indexes after curve smoothing.
                signals = {}
                for target_index, target in enumerate(directed_points):
                    previous = directed_points[(target_index - 1) % len(directed_points)]
                    horizontal_approach = abs(float(target[0]) - float(previous[0])) >= abs(
                        float(target[1]) - float(previous[1])
                    )
                    signals[str(target_index)] = 0 if horizontal_approach else 1
                routes.append({
                    "id": f"grid_circulation_{rectangle_index:02d}_{direction_name}_lane{lane_index}",
                    "waypoints": [[round(x, 3), round(y, 3)] for x, y in directed_points],
                    "speed_limit": speed_limit,
                    "lane_offset": lane_offset,
                    "turn_radius": turn_radius,
                    "grid_native": True,
                    "city_circulation": True,
                    "circulation_blocks": (right_index - left_index) + (bottom_index - top_index),
                    "six_lane_network": True,
                    "lane_index": lane_index,
                    "lane_direction": direction_name,
                    "signals": signals,
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
            # Mixed walk/sidewalk labels are valid; the exact cell test below is
            # authoritative, so only reject if a segment leaves pavement entirely.
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
        route_index = (index * 37 + 11) % len(routes)
        lap = index // len(routes)
        fraction = (0.11 + index * 0.381966 + lap * 0.29) % 1.0
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


def _build_parking_spots(world, traffic_signals: list[dict], limit: int = 18) -> list[dict]:
    """Create deterministic curbside bays away from junction conflict zones."""
    signals = [tuple(map(float, row.get("pos", (0.0, 0.0)))) for row in traffic_signals]
    candidates: list[tuple[int, int, str]] = []
    directions = (
        ("north", 0, -1), ("east", 1, 0),
        ("south", 0, 1), ("west", -1, 0),
    )
    for gy in range(1, world.height - 1):
        for gx in range(1, world.width - 1):
            if not _is_road(world, gx, gy):
                continue
            road_neighbours = sum(_is_road(world, gx + dx, gy + dy) for _, dx, dy in directions)
            pavement_edges = [
                direction for direction, dx, dy in directions
                if _cell_collision(world, gx + dx, gy + dy) in {"walk", "sidewalk"}
            ]
            # A straight road-edge cell has three road neighbours and one curb.
            # Four-way cells belong to junctions and are never parking bays.
            if road_neighbours != 3 or len(pavement_edges) != 1:
                continue
            cx, cy = world.cell_center(gx, gy)
            if any(math.hypot(cx - sx, cy - sy) < world.cell_px * 2.2 for sx, sy in signals):
                continue
            ex, ey = {
                "north": (0.0, -1.0), "east": (1.0, 0.0),
                "south": (0.0, 1.0), "west": (-1.0, 0.0),
            }[pavement_edges[0]]
            parking_x = cx + ex * world.cell_px * 0.18
            parking_y = cy + ey * world.cell_px * 0.18
            if world.object_collision_at(parking_x, parking_y, max(90.0, world.cell_px * 0.75)):
                continue
            candidates.append((gx, gy, pavement_edges[0]))

    candidates.sort(key=lambda row: ((row[0] * 47 + row[1] * 71) % 1009, row[1], row[0]))
    selected: list[tuple[int, int, str]] = []
    for candidate in candidates:
        gx, gy, _edge = candidate
        if any(abs(gx - ox) + abs(gy - oy) < 4 for ox, oy, _ in selected):
            continue
        selected.append(candidate)
        if len(selected) >= max(0, int(limit)):
            break

    spots: list[dict] = []
    edge_vectors = {
        "north": (0.0, -1.0), "east": (1.0, 0.0),
        "south": (0.0, 1.0), "west": (-1.0, 0.0),
    }
    for index, (gx, gy, edge) in enumerate(selected, 1):
        cx, cy = world.cell_center(gx, gy)
        ex, ey = edge_vectors[edge]
        # Sit near the curb while retaining enough road inside the cell for the
        # complete collision width. North/south curbs imply east/west parking.
        x = cx + ex * world.cell_px * 0.18
        y = cy + ey * world.cell_px * 0.18
        angle = 0.0 if edge in {"north", "south"} else math.pi / 2.0
        spots.append({
            "id": f"parking_spot_{index:02d}",
            "pos": [round(x, 3), round(y, 3)],
            "angle": round(angle, 6),
            "curb_edge": edge,
            "occupied": index % 3 == 1,
            "grid_native": True,
        })
    return spots


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
    allowed = {"road"}
    # Player-controlled cars may cross painted dividers and mount sidewalks.
    # Ambient traffic remains road-bound so its deterministic flow stays safe.
    player_controlled = bool(getattr(car, "controlled_by", ""))
    if player_controlled:
        allowed.update({"walk", "sidewalk"})
    if any(world.collision_at("ground", px, py) not in allowed for px, py in probes):
        return True
    # Street props intentionally stay out of deterministic ambient lanes, but a
    # player-driven vehicle must respect their authored cones/tree collision.
    return player_controlled and any(world.object_collision_at(px, py, 4.0) for px, py in probes)


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
    map_config["traffic_signals"] = _build_traffic_signals(world)
    map_config["parking_spots"] = _build_parking_spots(world, map_config["traffic_signals"])
    map_config["npc_routes"] = pedestrian_routes
    map_config["npc_starts"] = _pedestrian_starts(pedestrian_routes)
    map_config["parked_vehicle_spawns"] = [
        [*spot["pos"], spot["angle"]]
        for spot in map_config["parking_spots"]
        if spot["occupied"]
    ]
    map_config["bicycle_routes"] = []
    map_config["bicycle_starts"] = []
    map_config["parked_bicycle_spawns"] = []

    server_module.traffic_vehicles.clear()
    server_module.bicycles.clear()
    server_module.npc_pedestrians.clear()
    server_module.initialize_traffic(traffic_count)
    server_module.initialize_parked_vehicles()
    server_module.initialize_npcs()
    server_module.initialize_hydrants()

    # Initial spawn filtering is deterministic. Never allow one invalid body to
    # poison the traffic simulation simply because a catalog car is unusually wide.
    safe_cars = []
    for car in server_module.traffic_vehicles:
        def pose_clear() -> bool:
            if _grid_vehicle_blocked(world, car, car.x, car.y, car.angle):
                return False
            return not any(server_module._oriented_boxes_overlap(
                car.x, car.y, car.angle, car.collision_length, car.collision_width,
                other.x, other.y, other.angle, other.collision_length, other.collision_width,
            ) for other in safe_cars)

        if not pose_clear() and not car.parked and 0 <= car.route_index < len(traffic_routes):
            # Long circulation routes share several road segments. If two large
            # authored vehicles land on the same initial segment, reseat only the
            # later car by a stable route fraction instead of dropping traffic.
            route = traffic_routes[car.route_index]
            for offset in (0.073, 0.149, 0.227, 0.311, 0.419):
                fraction = (float(car.home_fraction) + offset) % 1.0
                x, y, next_waypoint, angle = server_module._sample_route(route, fraction)
                car.x, car.y, car.next_waypoint, car.angle = x, y, next_waypoint, angle
                car.last_progress_x, car.last_progress_y = x, y
                car.home_fraction = fraction
                if pose_clear():
                    break
        if not pose_clear():
            continue
        safe_cars.append(car)
    server_module.traffic_vehicles[:] = safe_cars

    if traffic_count > 0 and not any(not car.parked for car in server_module.traffic_vehicles):
        raise RuntimeError("v1.1 GridWorld traffic requested but every car spawn was rejected")
    if not server_module.npc_pedestrians:
        raise RuntimeError("v1.1 GridWorld pedestrian initialization produced no NPCs")

    audit = {
        "authority": "gridworld_native_surface_population",
        "traffic_route_count": len(traffic_routes),
        "traffic_requested": traffic_count,
        "traffic_spawned": sum(1 for car in server_module.traffic_vehicles if not car.parked),
        "traffic_signal_count": len(map_config["traffic_signals"]),
        "parking_spot_count": len(map_config["parking_spots"]),
        "parked_vehicle_count": sum(1 for car in safe_cars if car.parked),
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
