#!/usr/bin/env python3
"""Build v1.0 collision-locked visual overlays for Map 001.

The functional CSV map remains authoritative. This tool only paints cosmetic
RGBA tiles in exact world coordinates. It intentionally refuses to derive
collision from pixels.
"""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "mapfiles/data/map_001_gwb_corridor"
OUT = ROOT / "assets/environment/approved/map_001_gwb_corridor/v100_layers"
TILE = 1024
LAYERS = ("hell", "underground", "ground", "first_floor", "second_floor", "roof", "clouds", "hud_space")


def rows(name: str):
    p = MAP / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def map_cfg():
    return {r["key"]: r["value"] for r in rows("map.csv")}


def road_data():
    meta = {r["road_id"]: r for r in rows("roads.csv")}
    points = defaultdict(list)
    for r in rows("road_points.csv"):
        points[r["road_id"]].append((int(r["point_order"]), float(r["x"]), float(r["y"])))
    return meta, {k: [(x, y) for _, x, y in sorted(v)] for k, v in points.items()}


def building_levels():
    by_id = defaultdict(set)
    for r in rows("building_layers.csv"):
        by_id[r["building_id"]].add((int(r["level_id"]), r["layer_kind"]))
    return by_id


def world_to_tile(x, y):
    return int(x // TILE), int(y // TILE), x % TILE, y % TILE


def local_polyline(points, tx, ty):
    ox, oy = tx * TILE, ty * TILE
    return [(x - ox, y - oy) for x, y in points]


def palette(layer, mode):
    night = mode == "night"
    palettes = {
        "hell": ((39, 8, 13, 255), (93, 20, 19, 180), (177, 56, 28, 180)),
        "underground": ((24, 27, 27, 255), (51, 58, 54, 220), (108, 104, 78, 180)),
        "ground": ((24, 28, 31, 255) if night else (91, 94, 89, 255), (47, 50, 52, 255) if night else (79, 81, 78, 255), (122, 118, 104, 255)),
        "first_floor": ((0, 0, 0, 0), (82, 69, 61, 238), (145, 122, 92, 220)),
        "second_floor": ((0, 0, 0, 0), (74, 64, 60, 238), (132, 111, 90, 220)),
        "roof": ((0, 0, 0, 0), (69, 67, 64, 250), (115, 105, 91, 220)),
        "clouds": ((0, 0, 0, 0), (208, 213, 216, 42), (236, 239, 241, 58)),
        "hud_space": ((0, 0, 0, 0), (10, 12, 18, 0), (30, 34, 44, 0)),
    }
    return palettes[layer]


def paint_layer(layer, mode, tx, ty, roads, road_pts, buildings, levels):
    bg, primary, accent = palette(layer, mode)
    im = Image.new("RGBA", (TILE, TILE), bg)
    d = ImageDraw.Draw(im, "RGBA")
    ox, oy = tx * TILE, ty * TILE

    # Ground uses the authoritative road centerlines and exact authored widths.
    if layer == "ground":
        for rid, pts in road_pts.items():
            if len(pts) < 2:
                continue
            r = roads.get(rid, {})
            width = max(1, int(float(r.get("width", 70))))
            sidewalk = max(0, int(float(r.get("sidewalk_width", 0))))
            lp = local_polyline(pts, tx, ty)
            # sidewalk envelope first, then asphalt: guaranteed registered to gameplay road data
            if sidewalk:
                d.line(lp, fill=(117, 112, 99, 255), width=width + 2 * sidewalk, joint="curve")
            d.line(lp, fill=primary, width=width, joint="curve")
            # restrained worn center cue, never used for collision
            d.line(lp, fill=(111, 109, 101, 80), width=max(1, width // 32), joint="curve")

    # Building art follows authoritative footprint rectangles and layer declarations.
    wanted = {
        "ground": {(0, "ground")},
        "first_floor": {(1, "upper")},
        "second_floor": {(2, "upper2")},
        "roof": {(2, "roof"), (3, "roof")},
    }.get(layer, set())
    if wanted:
        for b in buildings:
            bid = b["id"]
            if layer != "ground" and not (levels.get(bid, set()) & wanted):
                continue
            x, y, w, h = (float(b[k]) for k in ("x", "y", "w", "h"))
            x0, y0, x1, y1 = x - ox, y - oy, x + w - ox, y + h - oy
            if x1 < 0 or y1 < 0 or x0 > TILE or y0 > TILE:
                continue
            inset = 4 if layer == "ground" else 10 if layer in ("first_floor", "second_floor") else 14
            d.rectangle((x0 + inset, y0 + inset, x1 - inset, y1 - inset), fill=primary, outline=accent, width=3)
            # deterministic roof/facade texture language: parapet + service blocks, no geometry changes
            if layer == "roof":
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                rw, rh = min(40, w * .18), min(28, h * .15)
                d.rectangle((cx-rw, cy-rh, cx+rw, cy+rh), fill=(91, 90, 84, 235), outline=(155, 146, 128, 220), width=2)

    # Lower layers are deliberately atmospheric until functional geometry exists.
    # They never paint fake walls/roads that could imply collision.
    if layer == "hell":
        for i in range(0, TILE, 96):
            d.line((0, i, TILE, i + 180), fill=primary, width=11)
    elif layer == "underground":
        # Only a neutral substrate; tunnels will be painted when underground semantic CSVs exist.
        for i in range(32, TILE, 128):
            d.line((i, 0, i, TILE), fill=(86, 83, 69, 45), width=2)
    elif layer == "clouds":
        # Cosmetic and translucent. No gameplay-significant shapes.
        seed = (tx * 73856093) ^ (ty * 19349663) ^ (0 if mode == "day" else 83492791)
        for n in range(8):
            cx = (seed + n * 181) % (TILE + 300) - 150
            cy = ((seed >> 5) + n * 271) % (TILE + 260) - 130
            rx = 90 + ((seed >> (n % 13)) & 63)
            ry = 38 + ((seed >> ((n + 3) % 13)) & 31)
            d.ellipse((cx-rx, cy-ry, cx+rx, cy+ry), fill=primary)

    return im


def main():
    cfg = map_cfg()
    cols = math.ceil(int(cfg["world_w"]) / TILE)
    rows_n = math.ceil(int(cfg["world_h"]) / TILE)
    roads, pts = road_data()
    buildings = rows("buildings.csv")
    levels = building_levels()
    OUT.mkdir(parents=True, exist_ok=True)

    for layer in LAYERS:
        for mode in ("day", "night"):
            target = OUT / layer / mode
            target.mkdir(parents=True, exist_ok=True)
            for ty in range(rows_n):
                for tx in range(cols):
                    im = paint_layer(layer, mode, tx, ty, roads, pts, buildings, levels)
                    im.save(target / f"tile_{tx:02d}_{ty:02d}.png", optimize=True)
    print(f"V100_ART_OVERLAYS_OK layers={len(LAYERS)} tiles_per_variant={cols*rows_n} world={cfg['world_w']}x{cfg['world_h']}")


if __name__ == "__main__":
    main()
