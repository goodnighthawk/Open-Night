#!/usr/bin/env python3
"""Build the first 64x48 authoritative v1.0 Ground tile grid.

This is deliberately a tile map, not a rasterization of the legacy vector roads.
The broad district layout may evolve, but every output cell is already a real
runtime/collision tile ID from assets/grid_v100/tile_catalog.json.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "mapfiles/data/map_001_gwb_corridor/grid_v100/ground_grid.json"
W, H, CELL = 64, 48, 256


def blank(fill: str) -> list[list[str]]:
    return [[fill for _ in range(W)] for _ in range(H)]


def paint_rect(grid, x0, y0, x1, y1, tile):
    for y in range(max(0, y0), min(H, y1)):
        for x in range(max(0, x0), min(W, x1)):
            grid[y][x] = tile


def main() -> None:
    # Full-cell sidewalk/lot material is the default urban substrate.
    ground = blank("pavement_center")

    # Building blocks are authored directly on the grid. Their outlines are
    # intentionally varied so grid-authoritative does not mean uniform blocks.
    blocks = [
        (2, 2, 12, 7, "building_red"), (17, 2, 24, 7, "building_blue"),
        (29, 2, 37, 7, "building_green"), (43, 2, 50, 7, "building_red"),
        (56, 2, 63, 7, "building_blue"),
        (3, 10, 11, 17, "building_blue"), (18, 11, 24, 17, "building_green"),
        (29, 10, 36, 17, "building_red"), (44, 11, 50, 17, "building_blue"),
        (56, 10, 62, 17, "building_green"),
        (2, 22, 10, 29, "building_green"), (17, 22, 24, 29, "building_red"),
        (29, 22, 36, 29, "building_blue"), (43, 22, 50, 29, "building_green"),
        (55, 22, 63, 29, "building_red"),
        (4, 33, 11, 40, "building_red"), (17, 34, 23, 40, "building_blue"),
        (29, 33, 37, 40, "building_green"), (44, 34, 51, 40, "building_red"),
        (56, 33, 62, 40, "building_blue"),
        (2, 44, 10, 48, "building_blue"), (17, 44, 25, 48, "building_green"),
        (30, 44, 37, 48, "building_red"), (43, 44, 51, 48, "building_blue"),
        (56, 44, 64, 48, "building_green"),
    ]
    for block in blocks:
        paint_rect(ground, *block)

    # Roads are actual road_fill cells. Corridors vary between one and two cells
    # wide and include offsets/T-connections rather than a perfectly repeated grid.
    for x0, x1 in ((13, 16), (25, 28), (38, 42), (51, 55)):
        paint_rect(ground, x0, 0, x1, H, "road_fill")
    for y0, y1 in ((8, 10), (18, 21), (30, 33), (41, 44)):
        paint_rect(ground, 0, y0, W, y1, "road_fill")

    # Break some corridors into asymmetrical neighborhood/service geometry.
    paint_rect(ground, 0, 12, 13, 14, "road_fill")
    paint_rect(ground, 42, 14, 64, 16, "road_fill")
    paint_rect(ground, 8, 33, 10, 41, "road_fill")
    paint_rect(ground, 55, 27, 64, 29, "road_fill")

    data = {
        "format": "open-night-grid-v1",
        "cell_px": CELL,
        "width": W,
        "height": H,
        "world_w": W * CELL,
        "world_h": H * CELL,
        "authority": "grid",
        "layers": {"ground": ground},
        "objects": [],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"V100_GRID_SEED_OK cells={W}x{H} cell_px={CELL} output={OUT}")


if __name__ == "__main__":
    main()
