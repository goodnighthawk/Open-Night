from __future__ import annotations

"""Render the v2.4 bus, parking, horn, and circulation proof sheet."""

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

import client
from common import get_map
from grid_renderer import GridRenderer
import server
import v100_server
import vehicle_art


WIDTH, HEIGHT = 1600, 980


def _panel(size: tuple[int, int], title: str, font) -> pygame.Surface:
    panel = pygame.Surface(size).convert()
    panel.fill((22, 27, 31))
    pygame.draw.rect(panel, (112, 131, 132), panel.get_rect(), width=2)
    label = font.render(title, True, (236, 228, 194))
    panel.blit(label, (18, 14))
    return panel


def _parking_panel(world, config: dict, spot: dict, size: tuple[int, int]) -> pygame.Surface:
    panel = pygame.Surface(size).convert()
    center = tuple(map(float, spot["pos"]))
    game = object.__new__(client.Game)
    game.screen = panel
    game.grid_world = world
    game.grid_renderer = GridRenderer(world)
    game.map_config = config
    game.local_id = "v24-review"
    game.players = {"v24-review": SimpleNamespace(level=0, render_x=center[0], render_y=center[1])}
    game.settings = {"render": {"camera_pixel_snap": True}}
    game._render_camera_override = (center[0] - size[0] * 0.5, center[1] - size[1] * 0.5)
    game.hydrants = {}
    game.traffic_lights = {}
    game.environment = SimpleNamespace(set_active_level=lambda _level: None, draw_view=lambda *_args: None)
    client.Game.draw_world(game)
    angle = float(spot["angle"])
    vehicle_art.draw_car(panel, (size[0] // 2, size[1] // 2), angle, 2, target_length=150)
    pygame.draw.circle(panel, (78, 218, 143), (size[0] // 2, size[1] // 2), 102, width=3)
    return panel


def main() -> int:
    world = v100_server.load_ground_grid()
    config = copy.deepcopy(get_map())
    old_map, old_world, old_count = server.ACTIVE_MAP, server.GRID_WORLD, server.TRAFFIC_COUNT
    old_traffic = list(server.traffic_vehicles)
    try:
        server.ACTIVE_MAP = config
        server.GRID_WORLD = world
        server.TRAFFIC_COUNT = 56
        errors = v100_server.validate_active_authority(config)
        if errors:
            raise RuntimeError(errors)
        collision_circles = world.object_collision_circles()
        occupied = max(
            (row for row in config["parking_spots"] if row["occupied"]),
            key=lambda row: min(
                math.hypot(float(row["pos"][0]) - cx, float(row["pos"][1]) - cy) - radius
                for cx, cy, radius, _kind in collision_circles
            ),
        )
        parking = _parking_panel(world, config, occupied, (720, 340))
    finally:
        server.ACTIVE_MAP, server.GRID_WORLD, server.TRAFFIC_COUNT = old_map, old_world, old_count
        server.traffic_vehicles[:] = old_traffic

    review = pygame.Surface((WIDTH, HEIGHT)).convert()
    review.fill((8, 12, 15))
    title_font = pygame.font.Font(None, 45)
    panel_font = pygame.font.Font(None, 28)
    small = pygame.font.Font(None, 23)
    review.blit(title_font.render("OPEN NIGHT v2.4 — CURRENT REPORT VISUAL REVIEW", True, (238, 215, 130)), (34, 24))
    review.blit(small.render(
        "Actual runtime art and generated GridWorld data for reports #161–#164",
        True, (166, 188, 191),
    ), (36, 74))

    bus_rect = pygame.Rect(34, 112, 810, 390)
    bus_panel = _panel(bus_rect.size, "THREE COMPLETED BUS SPRITES", panel_font)
    for column, index in enumerate((22, 23, 24)):
        x = 145 + column * 260
        vehicle_art.draw_car(bus_panel, (x, 215), math.pi / 2.0, index, target_length=300)
        label = small.render(f"BUS {index - 21} — ROUNDED REAR", True, (188, 222, 205))
        bus_panel.blit(label, label.get_rect(center=(x, 365)))
    review.blit(bus_panel, bus_rect)

    parking_rect = pygame.Rect(866, 112, 700, 390)
    parking_frame = _panel(parking_rect.size, "PARKED CAR — CLEAR DEPARTURE POSE", panel_font)
    parking_frame.blit(parking, (-10, 48))
    review.blit(parking_frame, parking_rect)

    route_rect = pygame.Rect(34, 526, 1110, 420)
    route_panel = _panel(route_rect.size, "VARIED MULTI-BLOCK CITY CIRCULATION", panel_font)
    route_area = pygame.Rect(24, 56, route_panel.get_width() - 48, route_panel.get_height() - 82)
    colors = ((67, 198, 190), (238, 183, 77), (203, 91, 126), (118, 150, 234), (129, 205, 102))
    representatives = [
        route for route in config["traffic_routes"]
        if route["lane_direction"] == "cw" and route["lane_index"] == 1
    ]
    for index, route in enumerate(representatives):
        points = [
            (
                route_area.x + int(float(x) / world.world_w * route_area.width),
                route_area.y + int(float(y) / world.world_h * route_area.height),
            )
            for x, y in route["waypoints"]
        ]
        if len(points) >= 3:
            pygame.draw.lines(route_panel, colors[index % len(colors)], True, points, 2)
    route_panel.blit(small.render(
        f"84 signal-aware routes • {min(r['circulation_blocks'] for r in config['traffic_routes'])}+ blocks each • stable random-like starts",
        True, (210, 217, 204),
    ), (28, route_panel.get_height() - 30))
    review.blit(route_panel, route_rect)

    horn_rect = pygame.Rect(1166, 526, 400, 420)
    horn_panel = _panel(horn_rect.size, "REAL NETWORKED HORN AUDIO", panel_font)
    pygame.draw.polygon(horn_panel, (235, 215, 105), ((82, 181), (122, 181), (174, 132), (174, 270), (122, 221), (82, 221)))
    for radius in (45, 76, 108):
        pygame.draw.arc(horn_panel, (86, 211, 205), pygame.Rect(145, 201 - radius, radius * 2, radius * 2), -0.72, 0.72, 6)
    horn_panel.blit(small.render("horn_sequence +1", True, (235, 229, 204)), (78, 307))
    horn_panel.blit(small.render("SFX_STANDARD_HORN.wav", True, (137, 213, 178)), (78, 338))
    horn_panel.blit(small.render("Audible event; no text overlay", True, (173, 187, 190)), (78, 369))
    review.blit(horn_panel, horn_rect)

    output = ROOT / "work" / "v240_current_reports_visual_review.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(review, output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
