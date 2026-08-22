from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "assets" / "characters" / "grunge_topdown" / "bodies"
STATES = ("idle", "walk_left", "walk_right", "run_left", "run_right")


def main() -> int:
    pygame.init()
    pygame.display.set_mode((1, 1))
    comparisons = 0
    for index in range(1, 9):
        frames = {
            state: pygame.image.load(str(PACK / f"body_{index:02d}_{state}.png")).convert_alpha()
            for state in STATES
        }
        assert all(image.get_size() == (160, 128) for image in frames.values())
        assert all(image.get_bounding_rect(min_alpha=10).width for image in frames.values())
        rgba = {state: pygame.image.tobytes(image, "RGBA") for state, image in frames.items()}
        assert rgba["walk_left"] != rgba["walk_right"]
        assert rgba["run_left"] != rgba["run_right"]
        assert rgba["idle"] != rgba["run_left"]
        assert rgba["idle"] != rgba["run_right"]
        comparisons += 4

    source = (ROOT / "character_art.py").read_text(encoding="utf-8")
    assert '("run_left", "run_right")' in source
    assert 'animation == "run"' in source
    print("WIDE GAIT AUDIT PASSED")
    print(f"  8 body styles / {comparisons} distinct gait comparisons / live run animation active")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
