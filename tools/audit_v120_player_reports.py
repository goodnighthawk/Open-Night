from __future__ import annotations

"""Regression gate for the player-visible v1.2 corrective report batch."""

import copy
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame

import v100_runtime_refinement
v100_runtime_refinement.install()
import v100_scale_normalization
v100_scale_normalization.install()
from common import get_map
from grid_renderer import GridRenderer
from grid_runtime import load_ground_grid
import v110_grid_population
import v110_job_locations


def main() -> None:
    pygame.init()
    pygame.display.set_mode((8, 8))
    world = load_ground_grid()
    config = copy.deepcopy(get_map())
    v110_job_locations.normalize(config, world)
    signals = config.get("traffic_signals", [])
    assert len(signals) >= 24, "GridWorld traffic signals were not restored"
    assert {int(row["phase"]) for row in signals} == {0, 1}
    roof_decals = [row for row in world.objects if row.get("composition_pass") == "roof_palette_v1"]
    assert roof_decals and all(int(row.get("width_px", 0)) >= 64 and int(row.get("height_px", 0)) >= 64
                               and row.get("placement_policy") == "centered_inboard_roof_cell_v12"
                               for row in roof_decals), "roof decals are not large, centered, and inboard"

    pavement = next((gx, gy) for gy in range(world.height) for gx in range(world.width)
                    if world.collision_at("ground", *world.cell_center(gx, gy)) in {"walk", "sidewalk"})
    px, py = world.cell_center(*pavement)
    ai_car = SimpleNamespace(collision_length=20.0, collision_width=12.0, controlled_by="")
    player_car = SimpleNamespace(collision_length=20.0, collision_width=12.0, controlled_by="player")
    assert v110_grid_population._grid_vehicle_blocked(world, ai_car, px, py, 0.0)
    assert not v110_grid_population._grid_vehicle_blocked(world, player_car, px, py, 0.0)

    sample = pygame.Surface((16, 16), pygame.SRCALPHA)
    sample.fill((0, 0, 0, 0))
    pygame.draw.rect(sample, (20, 20, 20, 255), (2, 2, 12, 12), width=2)
    pygame.draw.rect(sample, (90, 110, 120, 255), (4, 4, 8, 8))
    pygame.draw.rect(sample, (20, 20, 20, 255), (7, 7, 2, 2))
    cleaned = GridRenderer._suppress_building_perimeter_outline(sample)
    assert cleaned.get_at((2, 2)).a == 0, "exterior building frame remains visible"
    assert cleaned.get_at((7, 7)).a == 255, "interior rooftop detail was erased"

    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    updater_source = (ROOT / "UPDATE_OPEN_NIGHT.bat").read_text(encoding="utf-8")
    assert 'self.pause_page == "controls"' in client_source
    assert 'draw_character(self.screen, (sx, sy)' in client_source
    assert "Install: %CD%" in updater_source and "Commit: !LOCAL_SHA!" in updater_source
    print(f"V120_PLAYER_REPORTS_OK signals={len(signals)} roof_decals={len(roof_decals)} sidewalk_drive=yes job_npcs=yes controls_tab=yes frames_removed=yes")


if __name__ == "__main__":
    main()
