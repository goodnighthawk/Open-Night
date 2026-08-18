#!/usr/bin/env python3
"""Render actual Ground and Roof frames from the current grid runtime.

This is not concept art. The script runs the deterministic Ground+Roof generator,
loads the same GridWorld/GridRenderer used by the game, and renders two real
2560x1440 Pygame framebuffers from repo-resident city_block assets.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from grid_renderer import GridRenderer
from grid_runtime import load_ground_grid, load_roof_grid

GROUND_OUT = ROOT / "assets/grid_v100/GROUND_RUNTIME_PROOF_2560x1440.png"
ROOF_OUT = ROOT / "assets/grid_v100/ROOF_RUNTIME_PROOF_2560x1440.png"
W, H = 2560, 1440


def first_cell(world, layer: str, predicate):
    for gy, row in enumerate(world.layers[layer]):
        for gx, tile_id in enumerate(row):
            if predicate(tile_id, world.catalog[tile_id]):
                return gx, gy
    raise RuntimeError(f"required {layer} proof cell not present")


def camera_for(world, x: float, y: float) -> tuple[float, float]:
    return (
        max(0.0, min(world.world_w - W, x - W / 2)),
        max(0.0, min(world.world_h - H, y - H / 2)),
    )


def main() -> None:
    from tools.generate_v100_ground_roof_layers import main as generate_layers
    from tools.build_v100_grid_seed import main as validate_map

    generate_layers()
    validate_map()

    # Generation changed files that load_ground_grid caches, so guarantee a fresh read.
    load_ground_grid.cache_clear()
    load_roof_grid.cache_clear()

    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        ground = load_ground_grid()
        ground_renderer = GridRenderer(ground)
        ground_frame = pygame.Surface((W, H)).convert()
        sx, sy = ground.choose_spawn("ground", 18.0)
        ground_renderer.draw_view(ground_frame, camera_for(ground, sx, sy), "ground")
        GROUND_OUT.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(ground_frame, str(GROUND_OUT))

        roof = load_roof_grid()
        roof_renderer = GridRenderer(roof)
        roof_frame = pygame.Surface((W, H)).convert()
        rgx, rgy = first_cell(roof, "roof", lambda tid, tile: tid.startswith("bld_"))
        rx, ry = roof.cell_center(rgx, rgy)
        roof_renderer.draw_view(roof_frame, camera_for(roof, rx, ry), "roof")
        pygame.image.save(roof_frame, str(ROOF_OUT))

        road_gx, road_gy = first_cell(ground, "ground", lambda _tid, tile: tile.collision == "road")
        bx, by = first_cell(ground, "ground", lambda tid, tile: tid.startswith("bld_") and tile.collision == "blocked")
        road_x, road_y = ground.cell_center(road_gx, road_gy)
        bld_x, bld_y = ground.cell_center(bx, by)
        if ground_renderer.collision_at("ground", road_x, road_y) != "road":
            raise SystemExit("Ground road collision/render contract failed")
        if ground_renderer.collision_at("ground", bld_x, bld_y) != "blocked":
            raise SystemExit("Ground building collision/render contract failed")
        if roof_renderer.collision_at("roof", rx, ry) != "blocked":
            raise SystemExit("Roof building footprint contract failed")

        print(
            "V100_GROUND_ROOF_RUNTIME_PROOF_OK "
            f"size={W}x{H} cell={ground.cell_px} grid={ground.width}x{ground.height} "
            f"ground_objects={len(ground.objects)} roof_objects={len(roof.objects)} "
            f"ground={GROUND_OUT.name} roof={ROOF_OUT.name}"
        )
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
