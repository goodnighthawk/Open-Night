from __future__ import annotations

import math
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


def main() -> int:
    overlap = server._oriented_boxes_overlap
    assert overlap(0, 0, 0, 50, 20, 49, 0, 0, 50, 20)
    assert not overlap(0, 0, 0, 50, 20, 50, 0, 0, 50, 20)
    assert overlap(0, 0, 0, 50, 20, 0, 19, 0, 50, 20)
    assert not overlap(0, 0, 0, 50, 20, 0, 20, 0, 50, 20)
    assert overlap(0, 0, math.pi / 4, 50, 20, 0, 0, -math.pi / 4, 50, 20)

    routes = server.ACTIVE_MAP.get("npc_routes", []) or []
    assert routes, "playable map has no NPC routes"
    points = server._route_points(routes[0])
    assert points
    x, y = map(float, points[0])
    npc = server.NPCPedestrian(
        "audit-victim", 0, 1 % len(points), x, y, 54.0, 0.0,
        server._indexed_character_appearance(2),
    )
    car = server.TrafficVehicle(
        "audit-runover-car", -1, 0, x, y, 0.0, 90.0, 0, 0,
        collision_length=50.0, collision_width=20.0, npc_driver=False,
    )
    old_npcs = list(server.npc_pedestrians)
    old_cars = list(server.traffic_vehicles)
    old_blood = list(server.blood_stains)
    old_respawns = list(server.npc_respawns)
    try:
        server.npc_pedestrians[:] = [npc]
        server.traffic_vehicles[:] = [car]
        server.blood_stains.clear()
        server.npc_respawns.clear()
        now = time.monotonic()
        server.update_npc_runovers(now)
        assert not server.npc_pedestrians
        assert len(server.blood_stains) == 1
        assert len(server.npc_respawns) == 1
        delay = float(server.NPC_AI.get("runover_respawn_seconds", 18.0))
        server.traffic_vehicles.clear()
        server.update_npc_runovers(now + delay + 0.2)
        assert len(server.npc_pedestrians) == 1
        assert not server.npc_respawns
    finally:
        server.npc_pedestrians[:] = old_npcs
        server.traffic_vehicles[:] = old_cars
        server.blood_stains[:] = old_blood
        server.npc_respawns[:] = old_respawns

    client = (ROOT / "client.py").read_text(encoding="utf-8")
    assert "draw_blood_stain" in client and 'message.get("blood_stains"' in client
    print("VEHICLE BODY / NPC RUN-OVER AUDIT: PASS")
    print("  rotated boundary SAT + pedestrian removal + blood stain + delayed route respawn verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
