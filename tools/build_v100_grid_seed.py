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
    # A direct 256 px city_block pavement module is the default substrate.
    ground = blank("pavement_h")

    # Add some vertical-pavement bands so the first grid capture proves both
    # supplied pavement orientations are used directly by the renderer.
    for x0, x1 in ((0, 2), (11, 13), (16, 18), (23, 25), (28, 30), (36, 38), (42, 44), (49, 51), (55, 57), (62, 64)):
        paint_rect(ground, x0, 0, x1, H, "pavement_v")

    # Building blocks are authored directly on the grid. Their outlines are
    # intentionally varied so grid-authoritative does not mean uniform blocks.
    blocks = [
        (2, 2, 11, 7, "building_red"), (18, 2, 23, 7, "building_blue"),
        (30, 2, 36, 7, "building_green"), (44, 2, 49, 7, "building_red"),
        (57, 2, 62, 7, "building_blue"),
        (2, 10, 11, 17, "building_blue"), (18, 11, 23, 17, "building_green"),
        (30, 10, 36, 17, "building_red"), (44, 11, 49, 17, "building_blue"),
        (57, 10, 62, 17, "building_green"),
        (2, 22, 10, 29, "building_green"), (18, 22, 23, 29, "building_red"),
        (30, 22, 36, 29, "building_blue"), (44, 22, 49, 29, "building_green"),
        (57, 22, 63, 29, "building_red"),
        (3, 33, 11, 40, "building_red"), (18, 34, 23, 40, "building_blue"),
        (30, 33, 36, 40, "building_green"), (44, 34, 49, 40, "building_red"),
        (57, 33, 62, 40, "building_blue"),
        (2, 44, 10, 48, "building_blue"), (18, 44, 24, 48, "building_green"),
        (30, 44, 36, 48, "building_red"), (44, 44, 50, 48, "building_blue"),
        (57, 44, 64, 48, "building_green"),
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
