#!/usr/bin/env python3
"""Render a real GridRenderer frame from the committed playable Ground map.

This is not a concept image. It loads ground_grid.json through GridWorld and the
original city_block.zip through GridRenderer. The script is intentionally optional
in public CI because the purchased/user-supplied source pack is not redistributed
by this repository.
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
from grid_runtime import GRID_MAP_PATH, GRID_CATALOG_PATH, load_ground_grid

OUT = ROOT / "assets/grid_v100/GRID_RUNTIME_PROOF_2560x1440.png"
W, H = 2560, 1440


def first_cell(world, predicate):
    for gy, row in enumerate(world.layers["ground"]):
        for gx, tile_id in enumerate(row):
            if predicate(tile_id, world.catalog[tile_id]):
                return gx, gy
    raise RuntimeError("required proof cell not present in playable map")


def main() -> None:
    # Historical command now validates the committed map; it never overwrites it.
    from tools.build_v100_grid_seed import main as validate_map
    validate_map()

    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        world = load_ground_grid()
        renderer = GridRenderer(world)
        frame = pygame.Surface((W, H)).convert()
        spawn_x, spawn_y = world.choose_spawn("ground", 18.0)
        camera = (
            max(0.0, min(world.world_w - W, spawn_x - W / 2)),
            max(0.0, min(world.world_h - H, spawn_y - H / 2)),
        )
        renderer.draw_view(frame, camera, "ground")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(frame, str(OUT))

        rgx, rgy = first_cell(world, lambda tid, tile: tile.collision == "road")
        bgx, bgy = first_cell(world, lambda tid, tile: tid.startswith("bld_") and tile.collision == "blocked")
        rx, ry = world.cell_center(rgx, rgy)
        bx, by = world.cell_center(bgx, bgy)
        road_collision = renderer.collision_at("ground", rx, ry)
        building_collision = renderer.collision_at("ground", bx, by)
        if road_collision != "road":
            raise SystemExit(f"expected road collision from road tile, got {road_collision!r}")
        if building_collision != "blocked":
            raise SystemExit(f"expected blocked collision from building tile, got {building_collision!r}")

        print(
            "V100_GRID_RUNTIME_PROOF_OK "
            f"size={W}x{H} cell={world.cell_px} grid={world.width}x{world.height} "
            f"objects={len(world.objects)} road_collision={road_collision} "
            f"building_collision={building_collision} output={OUT.name}"
        )
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
