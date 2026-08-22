from __future__ import annotations

"""Behavioral gate for reports #47/#48: role-aware shared crossings."""

import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import v100_runtime_refinement
v100_runtime_refinement.install()
import v100_scale_normalization
v100_scale_normalization.install()

from grid_runtime import load_ground_grid
import server
import v110_grid_population
import v110_pedestrian_connectivity


def main() -> None:
    world = load_ground_grid()
    connectivity = v110_pedestrian_connectivity.apply(world)
    crossings = list(world._v110_crosswalks)
    assert crossings and connectivity["pedestrian_crosswalk_count"] == len(crossings)

    routes = v110_grid_population._build_traffic_routes(world)
    assert routes and all(set(map(int, route.get("signals", {}).values())) == {0, 1} for route in routes)
    assert all(len(route.get("signals", {})) == len(route.get("waypoints", [])) for route in routes)

    # A pedestrian entering a crossing waits while the conflicting vehicle role
    # is green and proceeds during the orthogonal phase/all-red window.
    for crossing in (next(c for c in crossings if c.axis == "x"), next(c for c in crossings if c.axis == "y")):
        first_road = crossing.road_cells()[0]
        road_x, road_y = world.cell_center(*first_road)
        if crossing.axis == "x":
            curb_x, curb_y = world.cell_center(crossing.road_start - 1, crossing.fixed_cell)
            conflict_phase = 1
        else:
            curb_x, curb_y = world.cell_center(crossing.fixed_cell, crossing.road_start - 1)
            conflict_phase = 0
        conflict_green_time = 9.0 if conflict_phase == 1 else 1.0
        safe_time = 1.0 if conflict_phase == 1 else 9.0
        assert not server._pedestrian_signal_allows_entry(
            world, curb_x, curb_y, road_x, road_y, conflict_green_time
        )
        assert server._pedestrian_signal_allows_entry(world, curb_x, curb_y, road_x, road_y, safe_time)

    # An endangered pedestrian already on the road abandons the route and makes
    # immediate measurable progress toward the nearest sidewalk.
    crossing = crossings[0]
    road_cell = crossing.road_cells()[len(crossing.road_cells()) // 2]
    x, y = world.cell_center(*road_cell)
    npc = server.NPCPedestrian(
        npc_id="road-hazard-npc", route_index=0, next_waypoint=1,
        x=x, y=y, speed=72.0, aim=0.0, appearance={},
        last_progress_x=x, last_progress_y=y,
    )
    car = server.TrafficVehicle(
        vehicle_id="road-hazard-car", route_index=0, next_waypoint=1,
        x=x + 32.0, y=y, angle=0.0, speed=0.0, color_index=0, sprite_index=0,
    )
    escape = server._nearest_sidewalk_escape(world, npc, car)
    assert escape is not None
    before = math.hypot(npc.x - escape[0], npc.y - escape[1])
    server.GRID_WORLD = world
    server.ACTIVE_MAP = {"npc_routes": [{"waypoints": [[x, y], [escape[0], escape[1]]], "speed": 72.0}]}
    server.npc_pedestrians[:] = [npc]
    server.traffic_vehicles[:] = [car]
    session = SimpleNamespace(player=SimpleNamespace(x=x, y=y))
    server.update_npcs(0.1, [session], 0)
    after = math.hypot(npc.x - escape[0], npc.y - escape[1])
    assert after < before and before - after >= 23.0, (before, after)

    print(
        f"V120_SIGNAL_HARMONY_OK traffic_routes={len(routes)} crossings={len(crossings)} "
        "car_phases=2 pedestrian_role_gate=yes road_escape=yes"
    )


if __name__ == "__main__":
    main()
