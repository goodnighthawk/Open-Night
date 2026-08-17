#!/usr/bin/env python3
"""Generate only the collision-accurate v1.0 Ground/Night approval tiles."""
from __future__ import annotations

import math
from pathlib import Path

import build_v100_art_overlays as art


def main():
    cfg = art.map_cfg()
    cols = math.ceil(int(cfg["world_w"]) / art.TILE)
    rows_n = math.ceil(int(cfg["world_h"]) / art.TILE)
    roads, pts = art.road_data()
    buildings = art.rows("buildings.csv")
    levels = art.building_levels()
    water = art.polygon_data("water_polygons.csv")
    green = art.polygon_data("green_polygons.csv")
    crosswalks = art.rows("crosswalks.csv")
    vegetation = art.rows("iterated_vegetation.csv")

    target = art.OUT / "ground" / "night"
    target.mkdir(parents=True, exist_ok=True)

    for ty in range(rows_n):
        for tx in range(cols):
            im = art.paint_layer(
                "ground", "night", tx, ty,
                roads, pts, buildings, levels,
                water, green, crosswalks, vegetation,
            )
            im.save(target / f"tile_{tx:02d}_{ty:02d}.png", optimize=True)

    art.build_ground_preview(cols, rows_n)
    print(
        f"V100_GROUND_APPROVAL_OK tiles={cols * rows_n} "
        f"world={cfg['world_w']}x{cfg['world_h']} "
        "preview=GROUND_NIGHT_APPROVAL_PREVIEW.png"
    )


if __name__ == "__main__":
    main()
