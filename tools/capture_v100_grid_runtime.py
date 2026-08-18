#!/usr/bin/env python3
"""Render a grid-native v1.0 proof frame using the actual imported city-block tiles."""
from __future__ import annotations

import os
import subprocess
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
from grid_world import GridWorld

MAP = ROOT / "mapfiles/data/map_001_gwb_corridor/grid_v100/ground_grid.json"
CATALOG = ROOT / "assets/grid_v100/tile_catalog.json"
OUT = ROOT / "assets/grid_v100/GRID_RUNTIME_PROOF_2560x1440.png"
W, H = 2560, 1440


def main() -> None:
    subprocess.run([sys.executable, str(ROOT / "tools/build_v100_grid_seed.py")], check=True)
    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        world = GridWorld.load(MAP, CATALOG)
        renderer = GridRenderer(world)
        frame = pygame.Surface((W, H)).convert()
        # Show a representative block/road area. Location is not semantically special.
        camera = (2048.0, 1024.0)
        renderer.draw_view(frame, camera, "ground")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(frame, str(OUT))

        # Prove gameplay semantics come from the same tile records.
        road_collision = renderer.collision_at("ground", 14 * 256 + 128, 4 * 256 + 128)
        building_collision = renderer.collision_at("ground", 4 * 256 + 128, 4 * 256 + 128)
        if road_collision != "road":
            raise SystemExit(f"expected road collision from road tile, got {road_collision!r}")
        if building_collision != "blocked":
            raise SystemExit(f"expected blocked collision from building tile, got {building_collision!r}")

        print(
            "V100_GRID_RUNTIME_PROOF_OK "
            f"size={W}x{H} cell=256 grid=64x48 road_collision={road_collision} "
            f"building_collision={building_collision} output={OUT.name}"
        )
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
