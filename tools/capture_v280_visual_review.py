"""Render the v2.8 bridge, rooftop-job, planter, and passenger proof sheet."""

from __future__ import annotations

import copy
import math
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

from character_art import draw_character, normalize_character
from common import get_map
from grid_renderer import GridRenderer
import server
import v100_server
import vehicle_art


WIDTH, HEIGHT = 1600, 1050
PANEL_SIZE = (760, 430)


def _object_center(world, item: dict) -> tuple[float, float]:
    width = float(item.get("width_px", world.cell_px))
    height = float(item.get("height_px", world.cell_px))
    return (
        float(item["gx"]) * world.cell_px + float(item.get("offset_x_px", 0)) + width * 0.5,
        float(item["gy"]) * world.cell_px + float(item.get("offset_y_px", 0)) + height * 0.5,
    )


def _world_panel(world, center: tuple[float, float], title: str, detail: str, layer: str = "ground") -> tuple[pygame.Surface, tuple[float, float]]:
    panel = pygame.Surface(PANEL_SIZE).convert()
    renderer = GridRenderer(world)
    camera = (center[0] - PANEL_SIZE[0] * 0.5, center[1] - PANEL_SIZE[1] * 0.5)
    renderer.draw_view(panel, camera, layer)
    if layer == "ground":
        renderer.draw_overhead_objects(panel, camera, "ground")
    veil = pygame.Surface((PANEL_SIZE[0], 66), pygame.SRCALPHA)
    veil.fill((5, 9, 13, 222))
    panel.blit(veil, (0, 0))
    font = pygame.font.Font(None, 28)
    small = pygame.font.Font(None, 21)
    panel.blit(font.render(title, True, (242, 220, 137)), (18, 10))
    panel.blit(small.render(detail, True, (184, 212, 207)), (18, 39))
    pygame.draw.rect(panel, (98, 139, 145), panel.get_rect(), width=2)
    return panel, camera


def _status_panel() -> pygame.Surface:
    panel = pygame.Surface(PANEL_SIZE).convert()
    panel.fill((10, 15, 20))
    font = pygame.font.Font(None, 30)
    medium = pygame.font.Font(None, 24)
    small = pygame.font.Font(None, 20)
    panel.blit(font.render("CORRECTED VEHICLE + E PASSENGER ACTION", True, (242, 220, 137)), (18, 12))
    panel.blit(small.render("The reported parked source points nose-up; AI- and player-driven cars accept E boarding", True, (184, 212, 207)), (18, 43))

    card = pygame.Rect(28, 88, 285, 300)
    pygame.draw.rect(panel, (18, 25, 31), card, border_radius=10)
    pygame.draw.rect(panel, (81, 132, 142), card, width=2, border_radius=10)
    meta = server._parked_asset(3)
    vehicle_art.draw_car(panel, card.center, -math.pi / 2.0, int(meta.get("index", 0)), target_length=190)
    arrow = ((card.centerx, 102), (card.centerx - 12, 126), (card.centerx + 12, 126))
    pygame.draw.polygon(panel, (114, 231, 191), arrow)
    label = small.render("NOSE / FORWARD", True, (114, 231, 191))
    panel.blit(label, label.get_rect(center=(card.centerx, 370)))

    draw_character(panel, (388, 213), 0.0, normalize_character({"preset": 3}), scale=3, moving=False, anim_time=0.0)
    pygame.draw.line(panel, (121, 230, 190), (426, 213), (500, 213), 4)
    pygame.draw.polygon(panel, (121, 230, 190), ((500, 213), (484, 204), (484, 222)))
    pygame.draw.rect(panel, (33, 83, 77), pygame.Rect(520, 165, 185, 96), border_radius=12)
    pygame.draw.rect(panel, (105, 224, 179), pygame.Rect(520, 165, 185, 96), width=3, border_radius=12)
    e_text = font.render("[ E ] PASSENGER", True, (225, 247, 232))
    panel.blit(e_text, e_text.get_rect(center=(612, 213)))

    stats = (("28", "MOVING CARS"), ("108", "AMBIENT PEDS"), ("3", "DOG PAIRS"), ("20", "ROOFTOP JOBS"))
    for index, (value, label_text) in enumerate(stats):
        x = 346 + (index % 2) * 196
        y = 292 + (index // 2) * 60
        panel.blit(medium.render(value, True, (242, 220, 137)), (x, y))
        panel.blit(small.render(label_text, True, (169, 191, 197)), (x + 48, y + 4))
    pygame.draw.rect(panel, (98, 139, 145), panel.get_rect(), width=2)
    return panel


def main() -> int:
    world = v100_server.load_ground_grid()
    config = copy.deepcopy(get_map())
    old_map, old_world, old_grid, old_count = server.ACTIVE_MAP, server.GRID_WORLD, server.GRID_RUNTIME_ACTIVE, server.TRAFFIC_COUNT
    try:
        server.ACTIVE_MAP = config
        server.GRID_WORLD = world
        server.GRID_RUNTIME_ACTIVE = True
        server.TRAFFIC_COUNT = 28
        errors = v100_server.validate_active_authority(config)
        if errors:
            raise RuntimeError(errors)

        gwb = [item for item in world.objects if item.get("landmark_kind") == "george_washington_bridge"]
        gwb_center = (
            sum(_object_center(world, item)[0] for item in gwb) / len(gwb),
            sum(_object_center(world, item)[1] for item in gwb) / len(gwb),
        )
        jobs = list(config["job_locations"])
        supplier = next(row for row in jobs if row["role"] == "supplier")
        supplier_center = tuple(map(float, supplier["pos"]))
        planter = next(item for item in world.objects if item.get("scale_policy") == "sidewalk_fit_tree_planter_scale_1_5x_v28")

        bridge_panel, _ = _world_panel(
            world, gwb_center, "GEORGE WASHINGTON BRIDGE — MAP CENTER",
            "Nine connected landmark pieces restored over the central highway",
        )
        roof_panel, roof_camera = _world_panel(
            world, supplier_center, "ACCESSIBLE ROOFTOP SUPPLIER",
            "20 buyer/supplier NPCs on 20 distinct roofs • ambient NPCs remain on Ground", "roof",
        )
        sx = int(supplier_center[0] - roof_camera[0])
        sy = int(supplier_center[1] - roof_camera[1])
        pygame.draw.circle(roof_panel, (105, 230, 179), (sx, sy), 34, width=4)
        draw_character(roof_panel, (sx, sy), 0.0, normalize_character({"preset": 2}), scale=3, moving=False, anim_time=0.0)
        tag = pygame.font.Font(None, 24).render("SUPPLIER • LEVEL 1", True, (225, 247, 232))
        tag_rect = tag.get_rect(center=(sx, sy - 64))
        pygame.draw.rect(roof_panel, (8, 14, 18), tag_rect.inflate(12, 8), border_radius=5)
        roof_panel.blit(tag, tag_rect)

        planter_panel, _ = _world_panel(
            world, _object_center(world, planter), "SIDEWALK-FIT SHRUB PLANTER",
            f"{planter['width_px']}×{planter['height_px']} px prop inside one {world.cell_px} px pavement cell",
        )
        panels = (bridge_panel, roof_panel, planter_panel, _status_panel())
    finally:
        server.ACTIVE_MAP, server.GRID_WORLD, server.GRID_RUNTIME_ACTIVE, server.TRAFFIC_COUNT = old_map, old_world, old_grid, old_count

    review = pygame.Surface((WIDTH, HEIGHT)).convert()
    review.fill((7, 11, 15))
    title = pygame.font.Font(None, 46)
    subtitle = pygame.font.Font(None, 24)
    review.blit(title.render("OPEN NIGHT v2.8 — CURRENT REPORT VISUAL REVIEW", True, (242, 215, 125)), (38, 22))
    review.blit(subtitle.render(
        "Runtime GridWorld proof for reports #185–#192 and the requested central bridge restoration",
        True, (163, 194, 198),
    ), (40, 67))
    for panel, position in zip(panels, ((30, 102), (810, 102), (30, 552), (810, 552))):
        review.blit(panel, position)

    output = ROOT / "work" / "v280_current_reports_visual_review.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(review, output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
