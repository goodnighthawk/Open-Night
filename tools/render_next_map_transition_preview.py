#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from common import TRAFFIC_SIGNAL_ART_STATES, traffic_signal_state
from grid_renderer import GridRenderer
from grid_runtime import load_ground_grid


OUT = ROOT / "artifacts/next_map_generated_art"


def _draw_signals(target: pygame.Surface, renderer: GridRenderer, camera: tuple[float, float], server_time: float) -> None:
    for signal in renderer.world.data.get("traffic_signals", []):
        state = traffic_signal_state(signal, server_time)
        approved = renderer.catalog_object_at_pivot(state, width=70, height=96, rotation=0)
        if approved is None:
            continue
        image, pivot = approved
        sx = int(float(signal["pos"][0]) - camera[0])
        sy = int(float(signal["pos"][1]) - camera[1])
        target.blit(image, (sx - pivot[0], sy - pivot[1]))


def _draw_overview_signals(
    target: pygame.Surface,
    renderer: GridRenderer,
    scale: float,
    origin: tuple[int, int],
    server_time: float,
) -> None:
    ox, oy = origin
    for signal in renderer.world.data.get("traffic_signals", []):
        state = traffic_signal_state(signal, server_time)
        approved = renderer.catalog_object_at_pivot(state, width=70, height=96, rotation=0)
        if approved is None:
            continue
        image, pivot = approved
        scaled_size = (
            max(1, int(round(image.get_width() * scale))),
            max(1, int(round(image.get_height() * scale))),
        )
        image = pygame.transform.smoothscale(image, scaled_size)
        px = int(round(pivot[0] * scale))
        py = int(round(pivot[1] * scale))
        sx = ox + int(round(float(signal["pos"][0]) * scale))
        sy = oy + int(round(float(signal["pos"][1]) * scale))
        target.blit(image, (sx - px, sy - py))


def _label(target: pygame.Surface, text: str, position: tuple[int, int], font: pygame.font.Font) -> None:
    rendered = font.render(text, True, (226, 231, 236))
    box = rendered.get_rect(topleft=position).inflate(16, 10)
    panel = pygame.Surface(box.size, pygame.SRCALPHA)
    panel.fill((8, 12, 17, 220))
    target.blit(panel, box.topleft)
    pygame.draw.rect(target, (91, 108, 120), box, width=1, border_radius=3)
    target.blit(rendered, position)


def main() -> int:
    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        load_ground_grid.cache_clear()
        world = load_ground_grid()
        renderer = GridRenderer(world)
        font = pygame.font.Font(None, 25)
        small = pygame.font.Font(None, 20)

        full = pygame.Surface((3840, 1440)).convert()
        tile_px, overview_x, overview_y = renderer.draw_overview(full, "ground")
        _draw_overview_signals(
            full, renderer, tile_px / float(world.cell_px), (overview_x, overview_y), 4.0
        )
        pygame.image.save(full, str(OUT / "next_map_full_updated.png"))

        demo_door = next(item for item in world.objects if item.get("test_area") == "approved_transition_demo"
                         and item.get("interaction_kind") == "entrance_door")
        demo_ladder = next(item for item in world.objects if item.get("test_area") == "approved_transition_demo"
                           and item.get("interaction_kind") == "fire_escape_ladder")
        door_point = world.object_interaction_point(demo_door)
        ladder_point = world.object_interaction_point(demo_ladder)
        camera = (max(0.0, door_point[0] - 410.0), max(0.0, min(door_point[1], ladder_point[1]) - 220.0))
        virtual = pygame.Surface((1900, 1700)).convert()
        renderer.draw_view(virtual, camera, "ground")
        _draw_signals(virtual, renderer, camera, 4.0)
        _label(virtual, "APPROVED TRANSITION TEST AREA · RUNNING GROUND MAP", (24, 22), font)
        _label(virtual, "entrance + independent buzzer", (230, int(door_point[1] - camera[1] + 34)), small)
        _label(virtual, "compact ladder-only fire escape", (int(ladder_point[0] - camera[0] - 350), int(ladder_point[1] - camera[1] + 96)), small)
        _label(virtual, "six-state scripted intersection", (1180, 720), small)
        pygame.image.save(pygame.transform.smoothscale(virtual, (1710, 1530)), str(OUT / "next_map_transition_test_area.png"))

        roof_door = next(item for item in world.objects if item.get("test_area") == "approved_transition_demo"
                         and item.get("interaction_kind") == "roof_access_door")
        roof_center = world.cell_center(int(roof_door["gx"]), int(roof_door["gy"]))
        roof_camera = (max(0.0, roof_center[0] - 640.0), max(0.0, roof_center[1] - 440.0))
        roof = pygame.Surface((1280, 880)).convert()
        renderer.draw_rooftop_view(roof, roof_camera)
        _label(roof, "ROOF ACCESS + ELEVATOR LANDING · EXACT ROOF FOOTPRINT", (24, 22), font)
        pygame.image.save(roof, str(OUT / "next_map_transition_roof_access.png"))

        matrix = pygame.Surface((1200, 760)).convert()
        matrix.fill((13, 17, 21))
        asphalt = renderer._tile_surface_scaled("road_fill", 380)
        title = pygame.font.Font(None, 34)
        matrix.blit(title.render("APPROVED TRAFFIC SIGNAL MATRIX · IDENTICAL CANVAS + PIVOT", True, (232, 236, 240)), (36, 24))
        for index, state in enumerate(TRAFFIC_SIGNAL_ART_STATES):
            col, row = index % 3, index // 3
            panel = pygame.Rect(25 + col * 390, 78 + row * 330, 370, 310)
            matrix.blit(asphalt, panel.topleft, pygame.Rect(0, 0, panel.width, panel.height))
            pygame.draw.rect(matrix, (72, 84, 92), panel, width=2)
            approved = renderer.catalog_object_at_pivot(state, width=154, height=212)
            if approved is not None:
                image, pivot = approved
                anchor = (panel.centerx, panel.bottom - 54)
                matrix.blit(image, (anchor[0] - pivot[0], anchor[1] - pivot[1]))
            readable = state.removeprefix("traffic_").replace("_", " ").upper()
            label = small.render(readable, True, (236, 229, 199))
            label_box = label.get_rect(midbottom=(panel.centerx, panel.bottom - 8))
            matrix.blit(label, label_box)
        pygame.image.save(matrix, str(OUT / "next_map_traffic_signal_states.png"))
        print(
            "NEXT_MAP_TRANSITION_PREVIEWS_OK",
            "ground=next_map_transition_test_area.png",
            "roof=next_map_transition_roof_access.png",
            "signals=next_map_traffic_signal_states.png",
            "full=next_map_full_updated.png",
        )
        return 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
