from __future__ import annotations

"""GridWorld traffic deadlock prevention and collision-safe recovery for v1.1.

The mature traffic solver already gives one car right-of-way when proposed
footprints conflict, but a queue can still freeze when the winner's proposal is
blocked by the loser's *current* body. The old visible-stall recovery only ran
for reservation-cancelled cars and nudged 10 px without checking nearby cars.
That left ordinary following queues able to accumulate ``stuck_time`` forever
and could recover one jam by creating another overlap.

This module keeps the existing authoritative solver and adds three bounded fixes:

* wider deterministic lane separation on the three-cell GridWorld road bands;
* a strict no-overlap collision envelope for v1.1 traffic (the mature solver's
  old 0.92 courtesy scale could permit a small real body overlap after waiting);
* a post-tick watchdog for every AI car, with recovery candidates verified
  against GridWorld collision and every nearby vehicle footprint.

Recovery prefers a short lane-aligned back-off, then a small lateral deflection.
No recovery point may enter buildings/sidewalk collision or overlap another car.
"""

import math

LANE_OFFSET_RATIO = 0.30
STALL_RECOVERY_SECONDS = 1.70
RECOVERY_ATTEMPT_INTERVAL_SECONDS = 0.40
RECOVERY_CLEARANCE_SCALE = 1.04

_LAST_ATTEMPT: dict[str, float] = {}


def _stats(server_module) -> dict:
    value = getattr(server_module, "_v110_traffic_recovery_stats", None)
    if not isinstance(value, dict):
        value = {
            "attempts": 0,
            "successes": 0,
            "backoff_successes": 0,
            "deflection_successes": 0,
            "courtesy_overlap_clamps": 0,
        }
        server_module._v110_traffic_recovery_stats = value
    else:
        value.setdefault("courtesy_overlap_clamps", 0)
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
    """Move a persistently stalled AI car to the nearest verified free road spot."""
    stats = _stats(server_module)
    stats["attempts"] += 1

    heading = _route_heading(server_module, car, route)
    hx, hy = math.cos(heading), math.sin(heading)
    sx, sy = -hy, hx
    side = max(18.0, float(car.collision_width) * 0.78 + 10.0)

    # Keep every correction small enough to read as collision deflection rather
    # than a teleport. Back-off is preferred because it preserves lane order.
    candidates = [
        ("backoff", -16.0, 0.0),
        ("backoff", -28.0, 0.0),
        ("backoff", -42.0, 0.0),
        ("deflection", -12.0, side),
        ("deflection", -12.0, -side),
        ("deflection", -26.0, side),
        ("deflection", -26.0, -side),
        ("deflection", 4.0, side),
        ("deflection", 4.0, -side),
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


def _install_grid_lane_separation() -> None:
    """Widen the generated one-way lane offset before routes are initialized."""
    try:
        import v110_grid_population as grid_population
    except ImportError:
        return
    if bool(getattr(grid_population, "_v110_traffic_lane_separation_installed", False)):
        return
    original = grid_population._build_traffic_routes

    def build_traffic_routes_v110(world):
        routes = original(world)
        minimum = max(28.0, float(world.cell_px) * LANE_OFFSET_RATIO)
        for route in routes:
            try:
                current = float(route.get("lane_offset", 0.0))
            except (TypeError, ValueError):
                current = 0.0
            sign = -1.0 if current < 0.0 else 1.0
            route["lane_offset"] = sign * max(abs(current), minimum)
            route["v110_lane_separation"] = True
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

    # Phase 2b in the mature solver used a 0.92 courtesy envelope after a car had
    # waited. That was intentionally permissive, but with larger v1.1 sprites it
    # becomes a real visible overlap. GridWorld now keeps the full physical body.
    server_module._traffic_footprints_conflict = traffic_footprints_conflict_v110

    def safe_visible_recovery(car, route: dict) -> bool:
        return recover_visible_stall(server_module, car, route)

    # The original solver calls this for reservation-cancelled cars. Replacing
    # only the helper removes the unsafe unchecked 10 px nudge.
    server_module._recover_visible_stall = safe_visible_recovery

    def update_traffic_v110(dt: float, sessions, server_time: float) -> None:
        original_update(dt, sessions, server_time)
        if not bool(getattr(server_module, "GRID_RUNTIME_ACTIVE", False)):
            return
        routes = server_module.ACTIVE_MAP.get("traffic_routes", []) or []
        if not routes:
            return
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
