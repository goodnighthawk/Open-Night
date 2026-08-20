from __future__ import annotations

"""GridWorld traffic deadlock prevention and collision-safe recovery for v1.1.

The mature traffic solver already gives one car right-of-way when proposed
footprints conflict, but a queue can still freeze when the winner's proposal is
blocked by the loser's *current* body. The old visible-stall recovery only ran
for reservation-cancelled cars and nudged 10 px without checking nearby cars.
That left ordinary following queues able to accumulate ``stuck_time`` forever
and could recover one jam by creating another overlap.

This module keeps the existing authoritative solver and adds bounded GridWorld
fixes: wider deterministic lane separation and turn radii sized for the full-size
v1.1 cars, a strict full-body collision envelope, a post-tick overlap repair for
legacy retreat collisions, and a watchdog for every AI car whose ``stuck_time``
keeps growing outside the reservation-cancel path.

Recovery scales with each vehicle body, preferring a lane-aligned back-off before
a lateral deflection. Every candidate is checked against authoritative road
collision and every other vehicle body before it is committed.
"""

import math

LANE_OFFSET_RATIO = 0.50
TURN_RADIUS_RATIO = 0.60
STALL_RECOVERY_SECONDS = 1.70
RECOVERY_ATTEMPT_INTERVAL_SECONDS = 0.40
RECOVERY_CLEARANCE_SCALE = 1.04
OVERLAP_REPAIR_PASSES = 4

_LAST_ATTEMPT: dict[str, float] = {}


def _stats(server_module) -> dict:
    value = getattr(server_module, "_v110_traffic_recovery_stats", None)
    if not isinstance(value, dict):
        value = {}
        server_module._v110_traffic_recovery_stats = value
    for key in (
        "attempts", "successes", "backoff_successes", "deflection_successes",
        "courtesy_overlap_clamps", "overlaps_detected", "overlaps_repaired",
        "overlap_repair_failures",
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

    # Distances scale with the body. The former fixed 16/28/42 px retreat was
    # appropriate for toy-sized cars but too short to separate a full-size sedan.
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
        if not _candidate_clear(server_module, car, x, y, heading):
            continue
        car.x = x
        car.y = y
        car.angle = heading
        route_speed = max(1.0, float(route.get("speed_limit", 120.0)))
        car.speed = max(20.0, min(48.0, route_speed * 0.32 * float(car.speed_factor)))
        car.wait_age = 0.0
        car.stuck_time = 0.0
        car.last_progress_x = x
        car.last_progress_y = y
        stats["successes"] += 1
        key = "backoff_successes" if kind == "backoff" else "deflection_successes"
        stats[key] += 1
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


def _repair_current_overlaps(server_module, routes: list[dict]) -> None:
    """Repair the mature solver's unchecked cancelled-car retreat collisions."""
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

    def safe_visible_recovery(car, route: dict) -> bool:
        return recover_visible_stall(server_module, car, route)

    server_module._recover_visible_stall = safe_visible_recovery

    def update_traffic_v110(dt: float, sessions, server_time: float) -> None:
        original_update(dt, sessions, server_time)
        if not bool(getattr(server_module, "GRID_RUNTIME_ACTIVE", False)):
            return
        routes = server_module.ACTIVE_MAP.get("traffic_routes", []) or []
        if not routes:
            return

        _repair_current_overlaps(server_module, routes)

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

    server_module.update_traffic = update_traffic_v110
    server_module._v110_traffic_recovery_installed = True
