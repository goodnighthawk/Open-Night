from __future__ import annotations

"""GridWorld traffic deadlock prevention and collision-safe recovery.

The mature traffic solver already gives one car right-of-way when proposed
footprints conflict, but a queue can still freeze when the winner's proposal is
blocked by the loser's *current* body. The old visible-stall recovery only ran
for reservation-cancelled cars and nudged 10 px without checking nearby cars.

This module keeps the mature authoritative solver and adds bounded GridWorld
fixes for full-size v1.1 cars: wider deterministic lane separation and turn radii,
a strict body envelope, post-tick overlap/road repair, and a watchdog for every AI
car. Normal recovery uses short backoff/deflection. Only when those candidates
cannot clear a junction does the car reseat to the nearest verified pose on its
own route, before the server publishes the tick.
"""

import math

LANE_OFFSET_RATIO = 0.50
TURN_RADIUS_RATIO = 0.60
STALL_RECOVERY_SECONDS = 1.70
RECOVERY_ATTEMPT_INTERVAL_SECONDS = 0.40
RECOVERY_CLEARANCE_SCALE = 1.04
OVERLAP_REPAIR_PASSES = 4
ROUTE_RESEAT_LOCAL_LIMIT_SCALE = 2.8
MAX_RECOVERY_HEADING_CHANGE_RADIANS = math.radians(8.0)
RECOVERY_INCH_SPEED_MIN = 12.0
RECOVERY_INCH_SPEED_MAX = 24.0

_LAST_ATTEMPT: dict[str, float] = {}


def _stats(server_module) -> dict:
    value = getattr(server_module, "_v110_traffic_recovery_stats", None)
    if not isinstance(value, dict):
        value = {}
        server_module._v110_traffic_recovery_stats = value
    for key in (
        "attempts", "successes", "backoff_successes", "deflection_successes",
        "courtesy_overlap_clamps", "overlaps_detected", "overlaps_repaired",
        "overlap_repair_failures", "route_reseats", "blocked_repairs",
    ):
        value.setdefault(key, 0)
    return value


def _route_heading(server_module, car, route: dict) -> float:
    points = server_module._route_points(route)
    if not points:
        return float(car.angle)
    target = points[int(car.next_waypoint) % len(points)]
    dx = float(target[0]) - float(car.x)
    dy = float(target[1]) - float(car.y)
    if math.hypot(dx, dy) < 1e-6:
        return float(car.angle)
    return math.atan2(dy, dx)


def _bounded_heading(current: float, target: float) -> float:
    """Turn toward a recovery heading without a visible collision spin."""
    delta = (float(target) - float(current) + math.pi) % (2.0 * math.pi) - math.pi
    delta = max(-MAX_RECOVERY_HEADING_CHANGE_RADIANS, min(MAX_RECOVERY_HEADING_CHANGE_RADIANS, delta))
    return float(current) + delta


def _candidate_clear(server_module, car, x: float, y: float, heading: float) -> bool:
    if server_module._vehicle_map_blocked(car, x, y, heading):
        return False
    for other in server_module.traffic_vehicles:
        if other is car:
            continue
        if server_module._traffic_footprints_conflict(
            car, x, y, heading,
            other, float(other.x), float(other.y), float(other.angle),
            courtesy_scale=RECOVERY_CLEARANCE_SCALE,
        ):
            return False
    return True


def _apply_recovery_pose(server_module, car, route: dict, x: float, y: float, heading: float) -> None:
    heading = _bounded_heading(float(car.angle), float(heading))
    car.x = float(x)
    car.y = float(y)
    car.angle = float(heading)
    route_speed = max(1.0, float(route.get("speed_limit", 120.0)))
    car.speed = max(
        RECOVERY_INCH_SPEED_MIN,
        min(RECOVERY_INCH_SPEED_MAX, route_speed * 0.16 * float(car.speed_factor)),
    )
    car.wait_age = 0.0
    car.stuck_time = 0.0
    car.last_progress_x = car.x
    car.last_progress_y = car.y


def _reseat_to_nearest_clear_route_pose(server_module, car, route: dict) -> bool:
    """Find the closest non-overlapping road pose on this car's own route."""
    points = server_module._route_points(route)
    if len(points) < 2:
        return False

    body_length = max(48.0, float(car.collision_length))
    local_limit = max(180.0, body_length * ROUTE_RESEAT_LOCAL_LIMIT_SCALE)
    candidates: list[tuple[float, float, float, float, int]] = []
    n = len(points)
    # Sample all runtime segments so the fallback is deterministic; distance sort
    # keeps the normal case local even though a whole-route escape remains possible.
    for i in range(n):
        a = points[i]
        b = points[(i + 1) % n]
        ax, ay = float(a[0]), float(a[1])
        bx, by = float(b[0]), float(b[1])
        dx, dy = bx - ax, by - ay
        if math.hypot(dx, dy) < 1e-6:
            continue
        heading = math.atan2(dy, dx)
        for t in (0.0, 0.25, 0.50, 0.75):
            x = ax + dx * t
            y = ay + dy * t
            distance = math.hypot(x - float(car.x), y - float(car.y))
            candidates.append((distance, x, y, heading, (i + 1) % n))

    candidates.sort(key=lambda row: (row[0], row[4], row[1], row[2]))
    # Prefer a visually local correction first, then allow the nearest whole-route
    # clear slot as a last-resort deadlock escape.
    for local_only in (True, False):
        for distance, x, y, heading, next_wp in candidates:
            if local_only and distance > local_limit:
                continue
            gentle_heading = _bounded_heading(float(car.angle), heading)
            if not _candidate_clear(server_module, car, x, y, gentle_heading):
                continue
            _apply_recovery_pose(server_module, car, route, x, y, gentle_heading)
            car.next_waypoint = next_wp
            _stats(server_module)["route_reseats"] += 1
            return True
    return False


def recover_visible_stall(server_module, car, route: dict) -> bool:
    """Move a stalled/overlapping AI car to the nearest verified free road spot."""
    stats = _stats(server_module)
    stats["attempts"] += 1

    heading = _route_heading(server_module, car, route)
    hx, hy = math.cos(heading), math.sin(heading)
    sx, sy = -hy, hx
    body_length = max(40.0, float(car.collision_length))
    body_width = max(24.0, float(car.collision_width))
    side = max(24.0, body_width * 0.72 + 10.0)
    back1 = max(24.0, body_length * 0.24)
    back2 = max(42.0, body_length * 0.42)
    back3 = max(62.0, body_length * 0.62)
    candidates = [
        ("backoff", -back1, 0.0),
        ("backoff", -back2, 0.0),
        ("backoff", -back3, 0.0),
        ("deflection", -back1 * 0.70, side),
        ("deflection", -back1 * 0.70, -side),
        ("deflection", -back2 * 0.70, side),
        ("deflection", -back2 * 0.70, -side),
        ("deflection", -back3 * 0.55, side),
        ("deflection", -back3 * 0.55, -side),
        ("deflection", body_length * 0.06, side),
        ("deflection", body_length * 0.06, -side),
    ]

    for kind, forward, lateral in candidates:
        x = float(car.x) + hx * forward + sx * lateral
        y = float(car.y) + hy * forward + sy * lateral
        gentle_heading = _bounded_heading(float(car.angle), heading)
        if not _candidate_clear(server_module, car, x, y, gentle_heading):
            continue
        _apply_recovery_pose(server_module, car, route, x, y, gentle_heading)
        stats["successes"] += 1
        key = "backoff_successes" if kind == "backoff" else "deflection_successes"
        stats[key] += 1
        return True

    if _reseat_to_nearest_clear_route_pose(server_module, car, route):
        stats["successes"] += 1
        return True
    return False


def _overlap_pairs(server_module) -> list[tuple[object, object]]:
    cars = list(server_module.traffic_vehicles)
    pairs: list[tuple[object, object]] = []
    for index, car in enumerate(cars):
        for other in cars[index + 1:]:
            if server_module._oriented_boxes_overlap(
                car.x, car.y, car.angle, car.collision_length, car.collision_width,
                other.x, other.y, other.angle, other.collision_length, other.collision_width,
            ):
                pairs.append((car, other))
    return pairs


def _repair_blocked_cars(server_module, routes: list[dict]) -> None:
    stats = _stats(server_module)
    for car in list(server_module.traffic_vehicles):
        if car.controlled_by or car.parked or int(car.route_index) < 0:
            continue
        if not server_module._vehicle_map_blocked(car, car.x, car.y, car.angle):
            continue
        route = routes[int(car.route_index) % len(routes)]
        if _reseat_to_nearest_clear_route_pose(server_module, car, route):
            stats["blocked_repairs"] += 1


def _repair_current_overlaps(server_module, routes: list[dict]) -> None:
    stats = _stats(server_module)
    for _ in range(OVERLAP_REPAIR_PASSES):
        pairs = _overlap_pairs(server_module)
        if not pairs:
            return
        stats["overlaps_detected"] += len(pairs)
        progress = False
        for car, other in pairs:
            movable = [
                obj for obj in (car, other)
                if not obj.controlled_by and not obj.parked and int(obj.route_index) >= 0
            ]
            movable.sort(key=lambda obj: (float(obj.wait_age), float(obj.stuck_time), str(obj.vehicle_id)))
            repaired = False
            for loser in movable:
                route = routes[int(loser.route_index) % len(routes)]
                if recover_visible_stall(server_module, loser, route):
                    stats["overlaps_repaired"] += 1
                    repaired = True
                    progress = True
                    break
            if not repaired:
                stats["overlap_repair_failures"] += 1
        if not progress:
            break


def _install_grid_lane_separation() -> None:
    """Size generated one-way lanes and corner fillets for full-size v1.1 cars."""
    try:
        import v110_grid_population as grid_population
    except ImportError:
        return
    if bool(getattr(grid_population, "_v110_traffic_lane_separation_installed", False)):
        return
    original = grid_population._build_traffic_routes

    def build_traffic_routes_v110(world):
        routes = original(world)
        minimum_offset = max(48.0, float(world.cell_px) * LANE_OFFSET_RATIO)
        minimum_turn = max(64.0, float(world.cell_px) * TURN_RADIUS_RATIO)
        for route in routes:
            try:
                current = float(route.get("lane_offset", 0.0))
            except (TypeError, ValueError):
                current = 0.0
            sign = -1.0 if current < 0.0 else 1.0
            if route.get("six_lane_network"):
                route["lane_offset"] = current
                route["v120_six_lane_usable"] = True
            else:
                route["lane_offset"] = sign * max(abs(current), minimum_offset)
            try:
                turn = float(route.get("turn_radius", 0.0))
            except (TypeError, ValueError):
                turn = 0.0
            route["turn_radius"] = max(turn, minimum_turn)
            route["v110_lane_separation"] = True
            route["v110_fullsize_turn_radius"] = True
        return routes

    grid_population._v110_original_build_traffic_routes = original
    grid_population._build_traffic_routes = build_traffic_routes_v110
    grid_population._v110_traffic_lane_separation_installed = True


def install(server_module) -> None:
    """Install v1.1 traffic recovery without replacing the mature AI solver."""
    _install_grid_lane_separation()
    if bool(getattr(server_module, "_v110_traffic_recovery_installed", False)):
        return

    original_update = server_module.update_traffic
    original_conflict = server_module._traffic_footprints_conflict
    server_module._v110_original_update_traffic = original_update
    server_module._v110_original_traffic_footprints_conflict = original_conflict

    def traffic_footprints_conflict_v110(
        car, x: float, y: float, heading: float,
        other, ox: float, oy: float, other_heading: float,
        *, courtesy_scale: float = 1.0,
    ) -> bool:
        scale = float(courtesy_scale)
        if bool(getattr(server_module, "GRID_RUNTIME_ACTIVE", False)) and scale < 1.0:
            _stats(server_module)["courtesy_overlap_clamps"] += 1
            scale = 1.0
        return original_conflict(
            car, x, y, heading,
            other, ox, oy, other_heading,
            courtesy_scale=scale,
        )

    server_module._traffic_footprints_conflict = traffic_footprints_conflict_v110
    server_module._recover_visible_stall = lambda car, route: recover_visible_stall(server_module, car, route)

    def update_traffic_v110(dt: float, sessions, server_time: float) -> None:
        original_update(dt, sessions, server_time)
        if not bool(getattr(server_module, "GRID_RUNTIME_ACTIVE", False)):
            return
        routes = server_module.ACTIVE_MAP.get("traffic_routes", []) or []
        if not routes:
            return

        # Enforce a valid published state every tick. A repair candidate must be
        # on road and clear of all current bodies, so these passes cannot trade
        # one collision for another.
        _repair_blocked_cars(server_module, routes)
        _repair_current_overlaps(server_module, routes)
        _repair_blocked_cars(server_module, routes)

        configured = float(server_module.TRAFFIC_AI.get("visible_stall_recovery_seconds", STALL_RECOVERY_SECONDS))
        threshold = min(STALL_RECOVERY_SECONDS, max(0.75, configured))
        stalled = sorted(
            (
                car for car in server_module.traffic_vehicles
                if not car.controlled_by and not car.parked and car.route_index >= 0
                and float(car.stuck_time) >= threshold
            ),
            key=lambda car: (-float(car.stuck_time), str(car.vehicle_id)),
        )
        for car in stalled:
            last = _LAST_ATTEMPT.get(str(car.vehicle_id), -1e9)
            if float(server_time) - last < RECOVERY_ATTEMPT_INTERVAL_SECONDS:
                continue
            _LAST_ATTEMPT[str(car.vehicle_id)] = float(server_time)
            route = routes[int(car.route_index) % len(routes)]
            recover_visible_stall(server_module, car, route)

        # A watchdog recovery can move a car near another body; make the returned
        # state clean before networking/next audit sample observes it.
        _repair_blocked_cars(server_module, routes)
        _repair_current_overlaps(server_module, routes)

    server_module.update_traffic = update_traffic_v110
    server_module._v110_traffic_recovery_installed = True
