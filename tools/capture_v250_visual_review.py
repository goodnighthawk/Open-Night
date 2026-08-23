from __future__ import annotations

"""Render the v2.5 bridge, infill, street-item, canopy, and vehicle proof sheet."""

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

from grid_renderer import GridRenderer
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


def _world_panel(world, center: tuple[float, float], title: str, detail: str) -> pygame.Surface:
    panel = pygame.Surface(PANEL_SIZE).convert()
    renderer = GridRenderer(world)
    camera = (center[0] - PANEL_SIZE[0] * 0.5, center[1] - PANEL_SIZE[1] * 0.5)
    renderer.draw_view(panel, camera, "ground")
    renderer.draw_overhead_objects(panel, camera, "ground")
    veil = pygame.Surface((PANEL_SIZE[0], 62), pygame.SRCALPHA)
    veil.fill((5, 9, 13, 218))
    panel.blit(veil, (0, 0))
    font = pygame.font.Font(None, 28)
    small = pygame.font.Font(None, 21)
    panel.blit(font.render(title, True, (242, 220, 137)), (18, 10))
    panel.blit(small.render(detail, True, (184, 212, 207)), (18, 37))
    pygame.draw.rect(panel, (98, 139, 145), panel.get_rect(), width=2)
    return panel


def main() -> int:
    world = v100_server.load_ground_grid()
    gwb = [item for item in world.objects if item.get("landmark_kind") == "george_washington_bridge"]
    infill_door = next(item for item in world.objects if str(item.get("building_id", "")).startswith("grid_infill_") and item.get("functional_entry"))
    closure = [item for item in world.objects if item.get("road_closure_id") == "road_closure_01"]
    canopy = next(item for item in world.objects if item.get("silhouette_kind") == "facade_break")

    gwb_center = (
        sum(_object_center(world, item)[0] for item in gwb) / len(gwb),
        sum(_object_center(world, item)[1] for item in gwb) / len(gwb),
    )
    closure_center = (
        sum(_object_center(world, item)[0] for item in closure) / len(closure),
        sum(_object_center(world, item)[1] for item in closure) / len(closure),
    )
    panels = [
        _world_panel(world, gwb_center, "GEORGE WASHINGTON BRIDGE — MAP CENTER", "Nine connected tower, truss, and pier pieces over the central highway"),
        _world_panel(world, _object_center(world, infill_door), "ENTERABLE INFILL BUILDING", "Wall-bound first-floor door • three-player-width curb setback • one server slot"),
        _world_panel(world, closure_center, "GROUPED ROAD CLOSURE", "Five cones in one closure; three compact closures across the map"),
        _world_panel(world, _object_center(world, canopy), "WALK-UNDER STREET ART", "3× wall-attached canopy and overhead lamp rendering"),
    ]

    # Runtime vehicle proof: the first two cars verify orientation; the final
    # three verify the newly closed rear exports from reports #177/#178/#181/#184.
    sprite_card = pygame.Surface((470, 152), pygame.SRCALPHA)
    sprite_card.fill((7, 10, 13, 225))
    pygame.draw.rect(sprite_card, (107, 151, 151), sprite_card.get_rect(), width=2)
    indices = (4, 14, 32, 31, 34)
    centers = (48, 140, 238, 332, 424)
    for center_x, index in zip(centers, indices):
        vehicle_art.draw_car(sprite_card, (center_x, 69), -math.pi / 2.0, index, target_length=96)
    tiny = pygame.font.Font(None, 18)
    for center_x, label in zip(centers, ("005", "015", "031", "032", "035")):
        text = tiny.render(label, True, (222, 221, 200))
        sprite_card.blit(text, text.get_rect(center=(center_x, 125)))
    sprite_card.blit(tiny.render("orientation", True, (151, 201, 201)), (52, 136))
    sprite_card.blit(tiny.render("completed rear exports", True, (151, 201, 201)), (258, 136))
    panels[3].blit(sprite_card, (PANEL_SIZE[0] - 490, PANEL_SIZE[1] - 172))

    review = pygame.Surface((WIDTH, HEIGHT)).convert()
    review.fill((7, 11, 15))
    title = pygame.font.Font(None, 46)
    subtitle = pygame.font.Font(None, 24)
    review.blit(title.render("OPEN NIGHT v2.5 — CURRENT REPORT VISUAL REVIEW", True, (242, 215, 125)), (38, 22))
    review.blit(subtitle.render(
        "Actual runtime GridWorld art for reports #165–#184, the restored GWB, and 30-building capacity",
        True, (163, 194, 198),
    ), (40, 67))
    positions = ((30, 102), (810, 102), (30, 552), (810, 552))
    for panel, position in zip(panels, positions):
        review.blit(panel, position)

    output = ROOT / "work" / "v250_current_reports_visual_review.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(review, output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
