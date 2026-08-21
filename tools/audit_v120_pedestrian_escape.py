from __future__ import annotations

"""Behavioral regression for trusted-player report #45."""

import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server


class SurfaceWorld:
    def __init__(self, surface: str = "sidewalk"):
        self.surface = surface

    def collision_at(self, _layer: str, _x: float, _y: float) -> str:
        return self.surface


def npc(npc_id: str, x: float, y: float) -> server.NPCPedestrian:
    return server.NPCPedestrian(
        npc_id=npc_id,
        route_index=0,
        next_waypoint=1,
        x=x,
        y=y,
        speed=72.0,
        aim=0.0,
        appearance={},
        last_progress_x=x,
        last_progress_y=y,
    )


def car(x: float, y: float) -> server.TrafficVehicle:
    return server.TrafficVehicle(
        vehicle_id="horn-car",
        route_index=0,
        next_waypoint=1,
        x=x,
        y=y,
        angle=0.0,
        speed=0.0,
        color_index=0,
        sprite_index=0,
        horn_until=time.monotonic() + 2.0,
    )


def main() -> None:
    server.ACTIVE_MAP = {
        "npc_routes": [{"id": "walk", "waypoints": [[40.0, 100.0], [300.0, 100.0]], "speed": 72.0}],
    }
    player = SimpleNamespace(player=SimpleNamespace(x=100.0, y=100.0))

    # A horn behind the pedestrian must produce immediate movement away from it.
    fleeing = npc("gridnpc-horn", 100.0, 100.0)
    server.GRID_WORLD = SurfaceWorld("sidewalk")
    server.npc_pedestrians[:] = [fleeing]
    server.traffic_vehicles[:] = [car(70.0, 100.0)]
    server.update_npcs(0.1, [player], 0)
    assert fleeing.x > 100.0, fleeing

    # If every local sidestep is obstructed, change route intent immediately;
    # never enter the old repeated pause/deadlock state.
    leader = npc("gridnpc-leader", 112.0, 100.0)
    jammed = npc("gridnpc-jammed", 100.0, 100.0)
    original_direction = jammed.route_direction
    server.GRID_WORLD = SurfaceWorld("blocked")
    server.npc_pedestrians[:] = [jammed, leader]
    server.traffic_vehicles.clear()
    server.update_npcs(0.1, [player], 0)
    assert jammed.route_direction == -original_direction, jammed
    assert jammed.pause_timer == 0.0, jammed
    assert jammed.stuck_time > 0.0, jammed

    print("V120_PEDESTRIAN_ESCAPE_OK horn_flee=yes jam_reverse=yes indefinite_pause=no")


if __name__ == "__main__":
    main()
