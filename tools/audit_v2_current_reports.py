from __future__ import annotations

"""Focused behavioral release gate for player reports #112-#125."""

import asyncio
import json
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
import server
import v100_server
from grid_renderer import GridRenderer
from grid_world import CURB_WORLD_TO_PACK_IMAGE
from vehicle_art import _base_car


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _exterior_neutral_fringe(surface: pygame.Surface) -> int:
    width, height = surface.get_size()
    pending = [(x, 0) for x in range(width)] + [(x, height - 1) for x in range(width)]
    pending += [(0, y) for y in range(1, height - 1)] + [(width - 1, y) for y in range(1, height - 1)]
    seen: set[tuple[int, int]] = set()
    fringe = 0
    while pending:
        x, y = pending.pop()
        if (x, y) in seen:
            continue
        pixel = surface.get_at((x, y))
        pale = min(pixel.r, pixel.g, pixel.b) >= 175 and max(pixel.r, pixel.g, pixel.b) - min(pixel.r, pixel.g, pixel.b) <= 30
        if pixel.a > 16 and not pale:
            continue
        seen.add((x, y))
        fringe += int(pixel.a > 16 and pale)
        if x:
            pending.append((x - 1, y))
        if x + 1 < width:
            pending.append((x + 1, y))
        if y:
            pending.append((x, y - 1))
        if y + 1 < height:
            pending.append((x, y + 1))
    return fringe


class _SidewalkWorld:
    @staticmethod
    def collision_at(_layer: str, _x: float, _y: float) -> str:
        return "sidewalk"


class _FakeWebSocket:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    async def send(self, raw: str) -> None:
        self.payloads.append(json.loads(raw))


async def _fire_escape_e_audit(world) -> None:
    fire = next(item for item in world.objects if item.get("asset") == "placeholder_fire_escape")
    ground_x, ground_y = world.cell_center(int(fire["gx"]), int(fire["gy"]))
    websocket = _FakeWebSocket()
    player = server.PlayerState("v2-fire-audit", "FireAudit", ground_x, ground_y)
    session = server.ClientSession(websocket, player, "5550000200", [])
    server.GRID_RUNTIME_ACTIVE = True
    server.GRID_WORLD = world
    await server.process_interaction(session)
    require(player.level == 1, "E interaction did not climb the fire escape")
    require(websocket.payloads and "ROOF" in websocket.payloads[-1].get("text", ""), "fire escape E notice missing")
    await server.process_interaction(session)
    require(player.level == 0, "E interaction did not descend the fire escape")


def _pedestrian_spacing_audit() -> None:
    route = {"id": "spacing", "waypoints": [[40.0, 100.0], [300.0, 100.0]], "speed": 72.0}
    first = server.NPCPedestrian(
        npc_id="v2-spacing-a", route_index=0, next_waypoint=1,
        x=100.0, y=100.0, speed=72.0, aim=0.0, appearance={},
        last_progress_x=100.0, last_progress_y=100.0,
    )
    second = server.NPCPedestrian(
        npc_id="v2-spacing-b", route_index=0, next_waypoint=1,
        x=112.0, y=100.0, speed=72.0, aim=0.0, appearance={},
        last_progress_x=112.0, last_progress_y=100.0,
    )
    server.ACTIVE_MAP = {"npc_routes": [route]}
    server.GRID_WORLD = _SidewalkWorld()
    server.npc_pedestrians[:] = [first, second]
    server.traffic_vehicles.clear()
    nearby_player = SimpleNamespace(player=SimpleNamespace(x=106.0, y=100.0))
    before = math.hypot(first.x - second.x, first.y - second.y)
    server.update_npcs(0.1, [nearby_player], 0, 0.0)
    after = math.hypot(first.x - second.x, first.y - second.y)
    require(after > before, f"crowded pedestrians did not separate: {before:.2f}->{after:.2f}")
    require(first.route_direction == 1 and second.route_direction == 1, "spacing response reversed a pedestrian route")


def _character_audit() -> dict:
    states = ("idle", "walk_left", "walk_right", "run_left", "run_right", "jump", "crouch", "prone")
    max_fringe = 0
    min_margin = character_art.COMPOSITE_SIZE
    for state in states:
        for index in range(1, 9):
            composed = character_art._composed_frame(
                f"hat_{index:02d}", f"head_{index:02d}", f"body_{index:02d}", state
            )
            rect = composed.get_bounding_rect(min_alpha=10)
            margins = (rect.x, rect.y, composed.get_width() - rect.right, composed.get_height() - rect.bottom)
            min_margin = min(min_margin, *margins)
            require(min(margins) >= 2, f"{state}/{index} touches its composite crop: {rect}")
            max_fringe = max(max_fringe, _exterior_neutral_fringe(composed))
    require(max_fringe == 0, f"exterior white/gray character fringe remains: {max_fringe}")

    appearance = {"hat": "hat_07", "head": "head_07", "body": "body_07"}
    source = character_art._scale_nearest(
        character_art._composed_frame("hat_07", "head_07", "body_07", "idle"), 2.0
    )
    east = character_art.build_character_surface(appearance, aim_radians=0.0, scale=2.0)
    south = character_art.build_character_surface(appearance, aim_radians=math.pi / 2.0, scale=2.0)
    require(pygame.image.tobytes(east, "RGBA") == pygame.image.tobytes(pygame.transform.rotate(source, -90), "RGBA"),
            "east-facing character is not a clockwise quarter-turn from north source art")
    require(pygame.image.tobytes(south, "RGBA") == pygame.image.tobytes(pygame.transform.rotate(source, -180), "RGBA"),
            "south-facing character is not a half-turn from north source art")
    for angle in (0.0, math.pi / 2.0, math.pi, math.pi * 1.5):
        prone = character_art.build_character_surface(
            appearance, aim_radians=angle, scale=3.0, animation="prone"
        )
        rect = prone.get_bounding_rect(min_alpha=10)
        require(rect.x > 0 and rect.y > 0 and rect.right < prone.get_width() and rect.bottom < prone.get_height(),
                f"rotated prone layers touch their render crop at angle {angle}: {rect}/{prone.get_size()}")
    return {"states": len(states), "variants": 8, "min_composite_margin_px": min_margin, "max_exterior_fringe_px": max_fringe}


def _bus_audit() -> dict:
    buses = []
    for index in (22, 23, 24):
        sprite = _base_car(index, 113)
        require(sprite is not None, f"bus {index} did not load")
        rect = sprite.get_bounding_rect(min_alpha=10)
        require(rect.x > 0 and rect.y > 0 and rect.right < sprite.get_width() and rect.bottom < sprite.get_height(),
                f"bus {index} still touches a clipped source edge: {rect}/{sprite.get_size()}")
        buses.append(sprite)
    preview = pygame.Surface((420, 160), pygame.SRCALPHA)
    preview.fill((37, 40, 43, 255))
    for col, sprite in enumerate(buses):
        preview.blit(sprite, sprite.get_rect(center=(70 + col * 140, 80)))
    output = ROOT / "work" / "v2_bus_runtime_preview.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(preview, output)
    return {"variants": len(buses), "preview": str(output)}


def main() -> int:
    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    server_source = (ROOT / "server.py").read_text(encoding="utf-8")
    audio_source = (ROOT / "gameplay" / "audio.py").read_text(encoding="utf-8")

    expected_corners = {
        "curb_tl_outer": "circle_bottom_right_outer.png",
        "curb_tr_outer": "circle_bottom_left_outer.png",
        "curb_bl_outer": "circle_top_right_outer.png",
        "curb_br_outer": "circle_top_left_outer.png",
    }
    for tile_id, filename in expected_corners.items():
        require(CURB_WORLD_TO_PACK_IMAGE[tile_id].endswith(filename), f"wrong curb transform for {tile_id}")

    world = v100_server.load_ground_grid()
    renderer = GridRenderer(world)
    for tile_id in CURB_WORLD_TO_PACK_IMAGE:
        require(renderer._tile_surface(tile_id).get_size() == (world.cell_px, world.cell_px),
                f"curb {tile_id} is not normalized to one grid cell")

    lamps = [item for item in world.objects if item.get("emits_light")]
    require(len(lamps) >= 80, f"expected visible lamp population, got {len(lamps)}")
    direction_ok = {"north": lambda dx, dy: dy < 0, "east": lambda dx, dy: dx > 0,
                    "south": lambda dx, dy: dy > 0, "west": lambda dx, dy: dx < 0}
    for lamp in lamps:
        base_x, base_y = world.cell_center(int(lamp["gx"]), int(lamp["gy"]))
        object_x = int(lamp["gx"]) * world.cell_px + int(lamp.get("offset_x_px", 0))
        object_y = int(lamp["gy"]) * world.cell_px + int(lamp.get("offset_y_px", 0))
        light_x = object_x + int(lamp["light_offset_x_px"])
        light_y = object_y + int(lamp["light_offset_y_px"])
        road_direction = str(lamp.get("road_overhang_direction", ""))
        require(direction_ok[road_direction](light_x - base_x, light_y - base_y),
                f"lamp fixture points away from {road_direction} road")
        require(world.collision_at("ground", light_x, light_y) == "road", "lamp fixture/light no longer reaches road")

    signals = world.data.get("traffic_signals", []) or []
    if not signals:
        signals = v100_server.server.ACTIVE_MAP.get("traffic_signals", []) if hasattr(v100_server, "server") else []
    require("for signal in self.map_config.get(\"traffic_signals\", [])" in client_source,
            "client no longer renders every published traffic signal")
    require("red_pos" in client_source and "green_pos" in client_source,
            "traffic fixtures do not visibly show both signal aspects")
    require("car.horn_until = recovery_now + 0.80" in server_source and "car.turn_signal =" in server_source,
            "stuck traffic does not request room with horn and indicator")
    require("not red_light and car.stuck_time >= recovery_after" in server_source,
            "bounded recovery is not guarded against red lights")

    _pedestrian_spacing_audit()
    # Restore the authoritative world/map before interaction checks.
    world = v100_server.load_ground_grid()
    asyncio.run(_fire_escape_e_audit(world))

    for token in ("self.customizing = True", "self.character_step_confirmed = False",
                  "Confirm your character with DONE", "CHARACTER REQUIRED"):
        require(token in client_source, f"explicit customization step missing {token!r}")
    require("fire_escape_target" in client_source and "CLIMB FIRE ESCAPE" in client_source,
            "fire escape E prompt is missing")
    require("traffic_engine_channel" in audio_source and "radius=1400.0" in audio_source,
            "distance-attenuated NPC engine loop is missing")

    character = _character_audit()
    bus = _bus_audit()
    print("V2 CURRENT REPORTS AUDIT: PASS")
    print(json.dumps({
        "reports": "#112-#125",
        "curb_tiles": len(CURB_WORLD_TO_PACK_IMAGE),
        "lamps": len(lamps),
        "character": character,
        "bus": bus,
        "release_status": "held",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
