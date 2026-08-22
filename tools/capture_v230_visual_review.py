from __future__ import annotations

"""Render a focused v2.3 visual review sheet from the actual runtime paths."""

import copy
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
import grid_client_entry  # noqa: F401 - installs the canonical GridWorld client entry
from grid_renderer import GridRenderer
import server
import v100_server
import vehicle_art


WIDTH, HEIGHT = 1600, 980
PANEL_W, PANEL_H = 500, 400


def _object_center(world, row: dict) -> tuple[float, float]:
    definition = world.catalog.object(str(row["asset"]))
    width = float(row.get("width_px", definition.native_width_px))
    height = float(row.get("height_px", definition.native_height_px))
    return (
        int(row["gx"]) * world.cell_px + float(row.get("offset_x_px", 0.0)) + width * 0.5,
        int(row["gy"]) * world.cell_px + float(row.get("offset_y_px", 0.0)) + height * 0.5,
    )


def _world_panel(world, config: dict, center: tuple[float, float]) -> pygame.Surface:
    screen = pygame.Surface((PANEL_W, PANEL_H)).convert()
    game = object.__new__(client.Game)
    game.screen = screen
    game.grid_world = world
    game.grid_renderer = GridRenderer(world)
    game.map_config = config
    game.local_id = "visual-review"
    game.players = {"visual-review": SimpleNamespace(level=0, render_x=center[0], render_y=center[1])}
    game.settings = {"render": {"camera_pixel_snap": True}}
    game._render_camera_override = (center[0] - PANEL_W * 0.5, center[1] - PANEL_H * 0.5)
    game.hydrants = {}
    game.traffic_lights = {
        str(row.get("id")): index % 2 == 0
        for index, row in enumerate(config.get("traffic_signals", []))
    }
    game.environment = SimpleNamespace(set_active_level=lambda _level: None, draw_view=lambda *_args: None)
    client.Game.draw_world(game)
    return screen


def _panel_frame(target: pygame.Surface, panel: pygame.Surface, x: int, y: int, title: str, font) -> None:
    target.blit(panel, (x, y))
    pygame.draw.rect(target, (133, 142, 140), pygame.Rect(x, y, panel.get_width(), panel.get_height()), width=2)
    label = font.render(title, True, (239, 236, 218))
    back = label.get_rect(topleft=(x + 12, y + 10)).inflate(14, 8)
    pygame.draw.rect(target, (13, 17, 19), back, border_radius=4)
    target.blit(label, (x + 19, y + 14))


def main() -> int:
    world = v100_server.load_ground_grid()
    config = copy.deepcopy(get_map())
    old_map, old_world = server.ACTIVE_MAP, server.GRID_WORLD
    old_traffic = list(server.traffic_vehicles)
    try:
        server.ACTIVE_MAP = config
        server.GRID_WORLD = world
        errors = v100_server.validate_active_authority(config)
        if errors:
            raise RuntimeError(errors)

        signal = config["traffic_signals"][len(config["traffic_signals"]) // 2]
        phone = next(row for row in world.objects if row.get("lighting_kind") == "public_phone")
        planter = next(row for row in world.objects if row.get("scale_policy") == "reported_tree_planter_scale_4x")
        empty_parking = next(row for row in config["parking_spots"] if not row["occupied"])

        signal_panel = _world_panel(world, config, tuple(map(float, signal["pos"])))
        phone_panel = _world_panel(world, config, _object_center(world, phone))
        planter_panel = _world_panel(world, config, _object_center(world, planter))
        parking_panel = _world_panel(world, config, tuple(map(float, empty_parking["pos"])))
    finally:
        server.ACTIVE_MAP, server.GRID_WORLD = old_map, old_world
        server.traffic_vehicles[:] = old_traffic

    review = pygame.Surface((WIDTH, HEIGHT)).convert()
    review.fill((9, 12, 14))
    title_font = pygame.font.Font(None, 44)
    panel_font = pygame.font.Font(None, 28)
    small = pygame.font.Font(None, 24)
    title = title_font.render("OPEN NIGHT v2.3 — CURRENT REPORT VISUAL REVIEW", True, (237, 220, 149))
    review.blit(title, (34, 24))
    subtitle = small.render(
        "Runtime GridWorld frames: synchronized signal, lit pavement phone, 4x collidable planter, open parking bay, corrected vehicle/cap art",
        True, (174, 190, 192),
    )
    review.blit(subtitle, (36, 72))

    _panel_frame(review, signal_panel, 34, 112, "TRAFFIC SIGNAL FIXTURE", panel_font)
    _panel_frame(review, phone_panel, 550, 112, "PHONE ON PAVEMENT + LIGHT", panel_font)
    _panel_frame(review, planter_panel, 1066, 112, "4x TREE PLANTER + COLLISION", panel_font)
    _panel_frame(review, parking_panel, 34, 536, "OPEN CURBSIDE PARKING BAY", panel_font)

    art_panel = pygame.Surface((1016, 400)).convert()
    art_panel.fill((25, 29, 31))
    pygame.draw.line(art_panel, (63, 70, 71), (508, 24), (508, 376), 2)
    vehicle_art.draw_car(art_panel, (260, 218), 0.0, 25, target_length=330)
    truck_label = panel_font.render("gridcar010 — complete source, no synthetic rear strip", True, (226, 229, 216))
    art_panel.blit(truck_label, truck_label.get_rect(midbottom=(260, 390)))
    cap = character_art.build_character_surface(
        {"hat": "hat_07", "head": "head_01", "body": "body_01"},
        aim_radians=-1.5707963267948966, scale=8.0,
    )
    art_panel.blit(cap, cap.get_rect(center=(760, 205)))
    north = panel_font.render("NORTH / DEFAULT CAMERA UP", True, (105, 217, 226))
    art_panel.blit(north, north.get_rect(center=(760, 38)))
    pygame.draw.polygon(art_panel, (105, 217, 226), ((760, 52), (751, 70), (769, 70)))
    cap_label = panel_font.render("hat_07 — north-facing white panel + peak", True, (226, 229, 216))
    art_panel.blit(cap_label, cap_label.get_rect(midbottom=(760, 390)))
    _panel_frame(review, art_panel, 550, 536, "CORRECTED RUNTIME SPRITES", panel_font)

    output = ROOT / "work" / "v230_current_reports_visual_review.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(review, output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
