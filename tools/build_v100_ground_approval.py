#!/usr/bin/env python3
"""Generate only the collision-accurate v1.0 Ground/Night approval tiles."""
from __future__ import annotations

import math

import build_v100_art_overlays as art
import v100_ground_detail_pass as detail


def main():
    cfg = art.map_cfg()
    cols = math.ceil(int(cfg["world_w"]) / art.TILE)
    rows_n = math.ceil(int(cfg["world_h"]) / art.TILE)
    roads, pts = art.road_data()
    # Ground may show Ground and elevated bridge geometry, but subterranean
    # level -1 passages must never leak into the surface composition.
    ground_roads = {
        rid: row for rid, row in roads.items()
        if int(float(row.get("level", 0) or 0)) >= 0
    }
    ground_pts = {rid: p for rid, p in pts.items() if rid in ground_roads}
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
                ground_roads, ground_pts, buildings, levels,
                water, green, crosswalks, vegetation,
            )
            detail.apply(im, tx, ty, mode="night")
            im.save(target / f"tile_{tx:02d}_{ty:02d}.png", optimize=True)

    art.build_ground_preview(cols, rows_n)
    print(
        f"V100_GROUND_APPROVAL_OK tiles={cols * rows_n} "
        f"world={cfg['world_w']}x{cfg['world_h']} "
        "detail=authored_pass22 subterranean_roads=excluded "
        "preview=GROUND_NIGHT_APPROVAL_PREVIEW.png"
    )


if __name__ == "__main__":
    main()
