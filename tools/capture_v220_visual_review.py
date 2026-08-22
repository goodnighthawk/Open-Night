from __future__ import annotations

import math
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

import client
from character_art import draw_character
from character_catalog import normalize_character
from grid_renderer import GridRenderer
import v100_server


PANEL = (640, 440)


def object_center(world, item) -> tuple[float, float]:
    definition = world.catalog.object(str(item["asset"]))
    width = float(item.get("width_px", definition.native_width_px))
    height = float(item.get("height_px", definition.native_height_px))
    return (
        int(item["gx"]) * world.cell_px + float(item.get("offset_x_px", 0.0)) + width * 0.5,
        int(item["gy"]) * world.cell_px + float(item.get("offset_y_px", 0.0)) + height * 0.5,
    )


def world_panel(world, renderer, item, title: str, *, player_under: bool = False) -> pygame.Surface:
    surface = pygame.Surface(PANEL).convert()
    center = object_center(world, item)
    camera = (center[0] - PANEL[0] * 0.5, center[1] - PANEL[1] * 0.5)
    renderer.draw_view(surface, camera, "ground")
    if player_under:
        draw_character(
            surface, (PANEL[0] // 2, PANEL[1] // 2), -math.pi / 2,
            normalize_character({"hat": "hat_01", "head": "head_01", "body": "body_01"}),
            scale=2, draw_shadow=False,
        )
        renderer.draw_overhead_objects(surface, camera, "ground")
    font = pygame.font.Font(None, 30)
    label = font.render(title, True, (245, 242, 231))
    pygame.draw.rect(surface, (12, 14, 18), label.get_rect(topleft=(12, 12)).inflate(16, 10), border_radius=5)
    surface.blit(label, (12, 12))
    return surface


def character_vehicle_panel() -> pygame.Surface:
    surface = pygame.Surface(PANEL, pygame.SRCALPHA)
    surface.fill((24, 28, 37, 255))
    appearance = normalize_character({"hat": "hat_01", "head": "head_01", "body": "body_01"})
    draw_character(surface, (150, 235), -math.pi / 2, appearance, scale=3, draw_shadow=False)
    draw_character(surface, (315, 235), -math.pi / 2, appearance, scale=3, draw_shadow=True)
    game = object.__new__(client.Game)
    game.screen = surface
    game.world_to_screen = lambda _x, _y: (510, 235)
    game.tiny_font = pygame.font.Font(None, 18)
    car = client.RemoteVehicle({
        "id": "v220-light-proof", "x": 0.0, "y": 0.0, "angle": -math.pi / 2,
        "speed": 80.0, "sprite": 36, "render_length": 165, "collision_width": 68.0,
        "headlights": True, "brake_lights": True, "turn_signal": 1,
    })
    client.Game.draw_vehicle(game, car)
    font = pygame.font.Font(None, 26)
    for text, position in (("LOCAL: NO SHADOW", (68, 360)), ("REMOTE SHADOW", (245, 360)), ("ALPHA LIGHTS", (448, 360))):
        surface.blit(font.render(text, True, (235, 232, 221)), position)
    return surface


def main() -> int:
    world = v100_server.load_ground_grid()
    renderer = GridRenderer(world)
    lamp = next(row for row in world.objects if row.get("lighting_kind") == "sidewalk_lamp")
    tree = next(row for row in world.objects if row.get("scale_policy") == "reported_tree_scale_4x")
    parasol = next(row for row in world.objects if row.get("scale_policy") == "reported_parasol_scale_3x")
    panels = (
        world_panel(world, renderer, lamp, "HALF-SIZE / INSET LAMP"),
        world_panel(world, renderer, tree, "4X TREE + COLLISION"),
        world_panel(world, renderer, parasol, "3X WALK-UNDER PARASOL", player_under=True),
        character_vehicle_panel(),
    )
    sheet = pygame.Surface((PANEL[0] * 2, PANEL[1] * 2)).convert()
    for index, panel in enumerate(panels):
        sheet.blit(panel, ((index % 2) * PANEL[0], (index // 2) * PANEL[1]))
    path = ROOT / "work" / "v220_current_reports_visual_review.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(sheet, path)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
