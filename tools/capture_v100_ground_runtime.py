#!/usr/bin/env python3
"""Capture a real 1920x720 Ground framebuffer using Open Night's runtime renderer."""
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

from environment_art import EnvironmentRenderer
from mapfiles.loader import load_map_folder

MAP_DIR = ROOT / "mapfiles/data/map_001_gwb_corridor"
OUT = ROOT / "assets/environment/approved/map_001_gwb_corridor/v100_layers/GROUND_RUNTIME_1920x720.png"
W, H = 1920, 720


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        cfg = load_map_folder(MAP_DIR)
        renderer = EnvironmentRenderer(cfg)
        renderer.set_active_level(0)

        spawns = cfg.get("login_spawns") or cfg.get("spawns") or []
        if spawns:
            px, py = map(float, spawns[0])
        else:
            px = float(cfg.get("world_w", W)) * 0.5
            py = float(cfg.get("world_h", H)) * 0.5

        world_w = float(cfg.get("world_w", W))
        world_h = float(cfg.get("world_h", H))
        cam_x = max(0.0, min(px - W * 0.5, max(0.0, world_w - W)))
        cam_y = max(0.0, min(py - H * 0.5, max(0.0, world_h - H)))

        frame = pygame.Surface((W, H)).convert()
        renderer.draw_view(frame, (cam_x, cam_y))

        OUT.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(frame, str(OUT))

        raw = pygame.image.tostring(frame, "RGB")
        if len(set(raw[::997])) < 12:
            raise SystemExit("Ground runtime capture appears blank/flat")

        print(
            "V100_GROUND_RUNTIME_CAPTURE_OK "
            f"size={W}x{H} level=0 camera=({cam_x:.1f},{cam_y:.1f}) output={OUT.name}"
        )
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
