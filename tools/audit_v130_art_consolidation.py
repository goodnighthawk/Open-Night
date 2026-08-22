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
    lamps = [row for row in world.objects if row.get("lighting_kind") == "sidewalk_lamp"]
    expected_vectors = {
        "north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0),
    }
    inward_vectors = {
        "north": (0, 1), "east": (-1, 0), "south": (0, -1), "west": (1, 0),
    }
    for lamp in lamps:
        width, height = int(lamp["width_px"]), int(lamp["height_px"])
        expected_size = (int(round(102 * world.cell_px / 256.0)), int(round(384 * world.cell_px / 256.0)))
        assert (width, height) == expected_size
        base, fixture = v100_runtime_refinement._lamp_anchor_geometry(int(lamp["rotation"]), width, height)
        inward = inward_vectors[str(lamp["road_overhang_direction"])]
        assert int(lamp.get("sidewalk_inset_px", 0)) == 52
        inset = int(round(52 * world.cell_px / 256.0))
        assert abs(int(lamp["offset_x_px"]) + base[0] - (world.cell_px / 2 + inward[0] * inset)) <= 1
        assert abs(int(lamp["offset_y_px"]) + base[1] - (world.cell_px / 2 + inward[1] * inset)) <= 1
        assert abs(int(lamp["light_offset_x_px"]) - fixture[0]) <= 1
        assert abs(int(lamp["light_offset_y_px"]) - fixture[1]) <= 1
        dx, dy = fixture[0] - base[0], fixture[1] - base[1]
        wanted = expected_vectors[str(lamp["road_overhang_direction"])]
        assert (0 if dx == 0 else dx // abs(dx), 0 if dy == 0 else dy // abs(dy)) == wanted
    print(f"V130_ART_CONSOLIDATION_OK junction_cells={len(junctions)} road_lines={len(road_lines)} aprons={len(aprons)}")


if __name__ == "__main__":
    main()
