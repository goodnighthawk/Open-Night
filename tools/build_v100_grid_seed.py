#!/usr/bin/env python3
"""Build the first 64x48 authoritative v1.0 Ground tile grid.

The map is authored as 256 px cells. Native premade city-block buildings are
anchored objects spanning multiple cells; those cells are independently marked
blocked, so the artwork never becomes the collision source.
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
    ground = blank("pavement_h")
    for x in range(0, W, 5):
        paint_rect(ground, x, 0, min(W, x + 1), H, "pavement_v")

    # Grid-native streets. These are tile cells, not vector centerlines.
    vertical_roads = [(7, 9), (19, 22), (34, 36), (49, 52)]
    horizontal_roads = [(8, 10), (22, 25), (37, 39)]
    for x0, x1 in vertical_roads:
        paint_rect(ground, x0, 0, x1, H, "road_fill")
    for y0, y1 in horizontal_roads:
        paint_rect(ground, 0, y0, W, y1, "road_fill")

    # Curb/sidewalk cells use the source pack's directional curb modules.
    for x0, x1 in vertical_roads:
        for y in range(H):
            if any(ya <= y < yb for ya, yb in horizontal_roads):
                continue
            if x0 - 1 >= 0:
                ground[y][x0 - 1] = "curb_right"
            if x1 < W:
                ground[y][x1] = "curb_left"
    for y0, y1 in horizontal_roads:
        for x in range(W):
            if any(xa <= x < xb for xa, xb in vertical_roads):
                continue
            if y0 - 1 >= 0:
                ground[y0 - 1][x] = "curb_bottom"
            if y1 < H:
                ground[y1][x] = "curb_top"

    objects = []

    def add_building(asset: str, gx: int, gy: int, span_w: int, span_h: int):
        paint_rect(ground, gx, gy, gx + span_w, gy + span_h, "building_blocked")
        objects.append({"asset": asset, "gx": gx, "gy": gy})

    # Native-size building sprites: red 01 = 5x6 cells; blue 04 = 6x7 cells.
    for spec in [
        ("building_red_01", 1, 1, 5, 6),
        ("building_blue_04", 10, 1, 6, 7),
        ("building_red_01", 24, 2, 5, 6),
        ("building_blue_04", 39, 1, 6, 7),
        ("building_red_01", 55, 1, 5, 6),
        ("building_blue_04", 1, 12, 6, 7),
        ("building_red_01", 11, 12, 5, 6),
        ("building_blue_04", 25, 12, 6, 7),
        ("building_red_01", 39, 13, 5, 6),
        ("building_blue_04", 54, 12, 6, 7),
        ("building_red_01", 2, 28, 5, 6),
        ("building_blue_04", 11, 28, 6, 7),
        ("building_red_01", 25, 29, 5, 6),
        ("building_blue_04", 39, 28, 6, 7),
        ("building_red_01", 55, 29, 5, 6),
        ("building_blue_04", 1, 41, 6, 7),
        ("building_red_01", 11, 41, 5, 6),
        ("building_blue_04", 25, 41, 6, 7),
        ("building_red_01", 39, 41, 5, 6),
        ("building_blue_04", 54, 41, 6, 7),
    ]:
        add_building(*spec)

    # Road markings and wear are grid-anchored visual objects; underlying road
    # cells remain the collision authority.
    for gx, gy, rot in [(8, 6, 0), (20, 20, 90), (35, 35, 0), (50, 20, 90)]:
        objects.append({"asset": "crosswalk_white", "gx": gx, "gy": gy, "width_px": 96, "height_px": 300, "rotation": rot})
    for gx, gy, rot in [(8, 7, 0), (35, 36, 180), (50, 21, 90)]:
        objects.append({"asset": "stop_white", "gx": gx, "gy": gy, "width_px": 180, "height_px": 100, "rotation": rot})
    for gx, gy, rot in [(8, 15, 0), (20, 30, 90), (50, 5, 180)]:
        objects.append({"asset": "arrow_white_short", "gx": gx, "gy": gy, "width_px": 72, "height_px": 112, "rotation": rot})
    objects.extend([
        {"asset": "manhole", "gx": 20, "gy": 15, "width_px": 128, "height_px": 126},
        {"asset": "road_cracks", "gx": 35, "gy": 17, "width_px": 120, "height_px": 244},
        {"asset": "roof_aircon_large", "gx": 12, "gy": 2, "width_px": 194, "height_px": 200},
        {"asset": "roof_duct", "gx": 41, "gy": 2, "width_px": 150, "height_px": 277},
        {"asset": "roof_water_red", "gx": 26, "gy": 13, "width_px": 158, "height_px": 158},
    ])

    data = {
        "format": "open-night-grid-v1",
        "cell_px": CELL,
        "width": W,
        "height": H,
        "world_w": W * CELL,
        "world_h": H * CELL,
        "authority": "grid",
        "layers": {"ground": ground},
        "objects": objects,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"V100_GRID_SEED_OK cells={W}x{H} objects={len(objects)} cell_px={CELL} output={OUT}")


if __name__ == "__main__":
    main()
