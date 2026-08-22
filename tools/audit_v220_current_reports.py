from __future__ import annotations

"""Focused behavioral release gate for player reports #136-#149."""

import copy
import math
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

import character_art
import client
from common import get_map
from gameplay.audio import GameAudio
from grid_renderer import GridRenderer
import server
import v100_runtime_refinement
import v100_server
import v110_job_locations
import v110_traffic_recovery


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _job_map_audit(world) -> dict:
    config = copy.deepcopy(get_map())
    v110_job_locations.normalize(config, world, player_radius=server.PLAYER_RADIUS)
    jobs = config.get("job_locations", [])
    require(len(jobs) == 20, f"expected 20 jobs, got {len(jobs)}")
    payload = server.network_map_payload(config)
    require(len(payload.get("job_locations", [])) == 20, "server payload dropped job markers")

    game = object.__new__(client.Game)
    game.map_config = config
    game.npcs = {}
    merged = client.Game._job_locations(game)
    require(len(merged) == 20, "client M-map helper dropped normalized jobs")
    source = (ROOT / "client.py").read_text(encoding="utf-8")
    arrow_index = source.index("pygame.draw.polygon(mini, (244,244,237)")
    job_index = source.index("for marker_pos, marker_color, role_letter in minimap_job_markers")
    require(job_index > arrow_index, "local minimap arrow still covers a co-located buyer")
    return {"jobs": len(merged), "buyers": 10, "suppliers": 10, "jobs_draw_after_local_arrow": True}


def _npc_keep_clear_audit(world) -> dict:
    old_map, old_world = server.ACTIVE_MAP, server.GRID_WORLD
    old_npcs = list(server.npc_pedestrians)
    old_traffic = list(server.traffic_vehicles)
    try:
        config = copy.deepcopy(get_map())
        v110_job_locations.normalize(config, world, player_radius=server.PLAYER_RADIUS)
        server.ACTIVE_MAP = config
        server.GRID_WORLD = world
        server.traffic_vehicles[:] = []
        server.initialize_npcs()
        buyer = next(npc for npc in server.npc_pedestrians if npc.kind == "buyer")
        movers = [npc for npc in server.npc_pedestrians if npc.route_index >= 0][:6]
        require(len(movers) == 6, "not enough moving NPCs for buyer-cluster audit")
        for npc in movers:
            npc.x = npc.last_progress_x = buyer.x
            npc.y = npc.last_progress_y = buyer.y
            npc.pause_timer = 0.0
        session = SimpleNamespace(player=SimpleNamespace(x=buyer.x, y=buyer.y))
        for tick in range(120):
            server.update_npcs(1.0 / 30.0, [session], tick, server_time=1000.0 + tick / 30.0)
        distances = [math.hypot(npc.x - buyer.x, npc.y - buyer.y) for npc in movers]
        require(min(distances) >= 68.0, f"ambient NPC remained clustered on buyer: {distances}")
        require(len({(round(npc.x, 1), round(npc.y, 1)) for npc in movers}) >= 4,
                "crowd did not disperse into distinct legal positions")
        require(max(npc.stuck_time for npc in movers) < 1.25, "corner watchdog left an NPC stuck")
        return {"test_npcs": len(movers), "minimum_buyer_clearance_px": round(min(distances), 2)}
    finally:
        server.ACTIVE_MAP = old_map
        server.GRID_WORLD = old_world
        server.npc_pedestrians[:] = old_npcs
        server.traffic_vehicles[:] = old_traffic


def _traffic_orbit_audit() -> dict:
    v110_traffic_recovery._ORBIT_TRACK.clear()
    car = SimpleNamespace(
        vehicle_id="orbit-audit", controlled_by="", parked=False, route_index=0,
        x=34.0, y=0.0, angle=math.pi / 2,
    )
    fake_server = SimpleNamespace(traffic_vehicles=[car])
    detected = False
    for index in range(38):
        theta = index * (2.0 * math.pi / 34.0)
        car.x, car.y, car.angle = 34.0 * math.cos(theta), 34.0 * math.sin(theta), theta + math.pi / 2
        detected = bool(v110_traffic_recovery._orbiting_cars(fake_server, index * 0.1)) or detected
    stats = getattr(fake_server, "_v110_traffic_recovery_stats", {})
    require(detected and stats.get("orbit_detections", 0) >= 1, "circular-driving watchdog did not trigger")
    return {"synthetic_orbit_detected": True, "window_seconds": v110_traffic_recovery.ORBIT_WINDOW_SECONDS}


def _audio_audit() -> dict:
    audio = GameAudio()
    require(audio.enabled, "audio fixture failed to initialize")
    local = SimpleNamespace(
        render_x=0.0, render_y=0.0, in_vehicle=False, vehicle_id="", moving_until=0.0,
    )
    vehicles = {
        f"car{index}": SimpleNamespace(
            id=f"car{index}", parked=False, speed=100.0 + index * 8.0,
            render_x=40.0 + index * 90.0, render_y=0.0, horn=False,
        )
        for index in range(6)
    }
    game = SimpleNamespace(players={"local": local}, local_id="local", vehicles=vehicles, grid_world=None)
    try:
        audio.update(game)
        require(len(audio.traffic_engine_channels) == 4,
                f"expected four independent nearest traffic engines, got {len(audio.traffic_engine_channels)}")
        volumes = [channel.get_volume() for channel in audio.traffic_engine_channels.values()]
        require(max(volumes) <= 0.20, f"traffic engine mix is still too loud: {volumes}")
        near = GameAudio._traffic_distance_volume(local, 40.0, 0.0)
        far = GameAudio._traffic_distance_volume(local, 900.0, 0.0)
        require(near > far * 20.0, "traffic distance falloff is not sufficiently strong")
        return {"independent_channels": len(volumes), "maximum_volume": round(max(volumes), 3)}
    finally:
        for sound in audio.sounds.values():
            sound.stop()


def _prop_lamp_character_audit(world) -> dict:
    trees = [row for row in world.objects if row.get("scale_policy") == "reported_tree_scale_4x"]
    parasols = [row for row in world.objects if row.get("scale_policy") == "reported_parasol_scale_3x"]
    require(len(trees) == 5 and len(parasols) == 5, "procedural tree/parasol population changed")
    for tree in trees:
        require(int(tree["width_px"]) >= 448 and int(tree["height_px"]) >= 480, "tree is not 4x")
        require(float(tree.get("collision_radius_px", 0.0)) >= 130.0, "tree collision is missing")
        cx = int(tree["gx"]) * world.cell_px + int(tree["offset_x_px"]) + int(tree["width_px"]) * 0.5
        cy = int(tree["gy"]) * world.cell_px + int(tree["offset_y_px"]) + int(tree["height_px"]) * 0.5
        require(world.object_collision_at(cx, cy), "tree center is not collision-enabled")
    require(all(row.get("overhead") and row.get("walk_under") and row.get("decorative_only") for row in parasols),
            "parasols are not collision-free overhead props")
    require(all(int(row["width_px"]) >= 276 and int(row["height_px"]) >= 210 for row in parasols),
            "parasol is not 3x")

    renderer = GridRenderer(world)
    parasol = parasols[0]
    cx = int(parasol["gx"]) * world.cell_px + int(parasol["offset_x_px"]) + int(parasol["width_px"]) // 2
    cy = int(parasol["gy"]) * world.cell_px + int(parasol["offset_y_px"]) + int(parasol["height_px"]) // 2
    surface = pygame.Surface((700, 520)).convert()
    camera = (cx - 350, cy - 260)
    renderer.draw_view(surface, camera, "ground")
    before = surface.copy()
    count = renderer.draw_overhead_objects(surface, camera, "ground")
    changed = sum(before.get_at((x, y)) != surface.get_at((x, y)) for y in range(520) for x in range(700))
    require(count >= 1 and changed >= 1000, "overhead parasol pass did not paint after entities")

    lamps = [row for row in world.objects if row.get("lighting_kind") == "sidewalk_lamp"]
    require(lamps and all((int(row["width_px"]), int(row["height_px"])) == (51, 192) for row in lamps),
            "street lamps are not half their reported size")
    for lamp in lamps:
        base, _fixture = v100_runtime_refinement._lamp_anchor_geometry(
            int(lamp["rotation"]), int(lamp["width_px"]), int(lamp["height_px"]),
        )
        base_x = int(lamp["offset_x_px"]) + base[0]
        base_y = int(lamp["offset_y_px"]) + base[1]
        require(round(math.hypot(base_x - world.cell_px / 2, base_y - world.cell_px / 2)) == 26,
                "lamp base is not inset farther onto the sidewalk")

    require(character_art.HAT_SHIFT_Y == -8, "hat was not moved north")
    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    require("draw_shadow=not local" in client_source, "local player shadow is still enabled")
    require("pygame.draw.circle(self.screen, color, position, core)" not in client_source,
            "vehicle lamp core is still opaque")
    require("(*color, 88)" in client_source and "(255, 250, 222, 112)" in client_source,
            "vehicle light alpha treatment is missing")
    return {
        "trees": len(trees), "parasols": len(parasols), "overhead_changed_pixels": changed,
        "lamps": len(lamps), "lamp_runtime_size": [51, 192], "hat_shift_y": character_art.HAT_SHIFT_Y,
    }


def main() -> int:
    world = v100_server.load_ground_grid()
    results = {
        "reports": "#136-#149",
        "npc_flow": _npc_keep_clear_audit(world),
        "traffic": _traffic_orbit_audit(),
        "audio": _audio_audit(),
        "job_maps": _job_map_audit(world),
        "world_art": _prop_lamp_character_audit(world),
        "release_status": "ready_for_v2.2_release_gate",
    }
    print("V2.2 CURRENT REPORTS AUDIT: PASS")
    print(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
