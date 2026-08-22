from __future__ import annotations

"""Deterministic grunge-neon visual-director release authority."""

import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame

import v100_runtime_refinement
v100_runtime_refinement.install()
from grid_renderer import GridRenderer
from grid_runtime import load_ground_grid
import v110_pedestrian_connectivity


def main() -> None:
    pygame.init()
    pygame.display.set_mode((8, 8))
    world = load_ground_grid()
    connectivity = v110_pedestrian_connectivity.apply(world)
    horizontal, vertical = v110_pedestrian_connectivity.road_bands(world)
    junctions = {(gx, gy) for h in horizontal for v in vertical
                 for gx in range(v.start, v.end + 1) for gy in range(h.start, h.end + 1)}
    road_lines = [row for row in world.objects
                  if str(row.get("street_marking", "")).startswith(("dashed_center_line_", "six_lane_divider_"))]
    assert road_lines and all((int(row["gx"]), int(row["gy"])) not in junctions for row in road_lines)
    aprons = [row for row in world.objects if row.get("sidewalk_extension")]
    assert aprons and all(row.get("visual_style") == "grunge_sidewalk_infill_v130" for row in aprons)
    assert connectivity["sidewalk_infill_asset"] == "pavement_small"
    assert GridRenderer.GROUND_NIGHT_MULTIPLY == (82, 94, 136)
    assert GridRenderer.GROUND_NIGHT_AMBIENT == (3, 5, 14)
    refinement = world.data["runtime_refinement"]
    assert refinement["road_art_authority"] == "grunge_neon_clean_junctions_v130"
    assert refinement["junction_clear_cell_count"] == len(junctions)
    print(f"V130_ART_CONSOLIDATION_OK junction_cells={len(junctions)} road_lines={len(road_lines)} aprons={len(aprons)}")


if __name__ == "__main__":
    main()
