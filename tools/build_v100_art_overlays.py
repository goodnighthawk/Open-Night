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


def polygon_data(name: str):
    groups = defaultdict(list)
    for r in rows(name):
        groups[r["polygon_id"]].append((int(r["point_order"]), float(r["x"]), float(r["y"])))
    return {k: [(x, y) for _, x, y in sorted(v)] for k, v in groups.items()}


def building_levels():
    by_id = defaultdict(set)
    for r in rows("building_layers.csv"):
        by_id[r["building_id"]].add((int(r["level_id"]), r["layer_kind"]))
    return by_id


def local_polyline(points, tx, ty):
    ox, oy = tx * TILE, ty * TILE
    return [(x - ox, y - oy) for x, y in points]


def local_box(x, y, w, h, tx, ty):
    ox, oy = tx * TILE, ty * TILE
    return x - ox, y - oy, x + w - ox, y + h - oy


def palette(layer, mode):
    night = mode == "night"
    palettes = {
        "hell": ((39, 8, 13, 255), (93, 20, 19, 180), (177, 56, 28, 180)),
        "underground": ((24, 27, 27, 255), (51, 58, 54, 220), (108, 104, 78, 180)),
        "ground": ((20, 24, 29, 255) if night else (91, 94, 89, 255), (43, 46, 49, 255) if night else (79, 81, 78, 255), (122, 118, 104, 255)),
        "first_floor": ((0, 0, 0, 0), (82, 69, 61, 238), (145, 122, 92, 220)),
        "second_floor": ((0, 0, 0, 0), (74, 64, 60, 238), (132, 111, 90, 220)),
        "roof": ((0, 0, 0, 0), (69, 67, 64, 250), (115, 105, 91, 220)),
        "clouds": ((0, 0, 0, 0), (208, 213, 216, 42), (236, 239, 241, 58)),
        "hud_space": ((0, 0, 0, 0), (10, 12, 18, 0), (30, 34, 44, 0)),
    }
    return palettes[layer]


def intersects_tile(points, tx, ty, pad=0):
    if not points:
        return False
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, y0 = tx * TILE - pad, ty * TILE - pad
    x1, y1 = x0 + TILE + 2 * pad, y0 + TILE + 2 * pad
    return not (max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1)


def draw_rotated_crosswalk(im, row, tx, ty):
    x, y = float(row["x"]), float(row["y"])
    length = float(row["length"])
    width = float(row["width"])
    stripe = max(2, float(row.get("stripe_width", 5)))
    gap = max(2, float(row.get("stripe_gap", 10)))
    angle = float(row["angle"])
    ox, oy = tx * TILE, ty * TILE
    lx, ly = x - ox, y - oy
    if lx < -length or ly < -length or lx > TILE + length or ly > TILE + length:
        return

    # Zebra texture is cosmetic, but its center/angle/extent are exactly authored.
    patch_size = int(math.ceil(max(length, width) * 1.6 + 16))
    patch = Image.new("RGBA", (patch_size, patch_size), (0, 0, 0, 0))
    pd = ImageDraw.Draw(patch, "RGBA")
    cx = cy = patch_size / 2
    start = -width / 2
    pos = start
    while pos < width / 2:
        pd.rectangle((cx - length / 2, cy + pos, cx + length / 2, cy + min(pos + stripe, width / 2)), fill=(222, 219, 204, 205))
        pos += stripe + gap
    patch = patch.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=False)
    im.alpha_composite(patch, (int(lx - patch_size / 2), int(ly - patch_size / 2)))


def paint_ground_semantics(im, d, tx, ty, mode, roads, road_pts, water, green, crosswalks, vegetation):
    night = mode == "night"

    # Authoritative water polygons first: preserve Hudson shape exactly.
    for pts in water.values():
        if intersects_tile(pts, tx, ty):
            lp = local_polyline(pts, tx, ty)
            d.polygon(lp, fill=(13, 31, 44, 255) if night else (51, 92, 111, 255))
            # deterministic reflected streaks remain clipped visually by redrawing polygon boundary later
            xs = [p[0] for p in lp]
            ys = [p[1] for p in lp]
            if xs and ys:
                for yy in range(int(min(ys)), int(max(ys)) + 1, 44):
                    d.line((min(xs), yy, max(xs), yy), fill=(69, 106, 127, 24 if night else 32), width=2)
            d.line(lp + [lp[0]], fill=(89, 118, 126, 105), width=2)

    # Parks/green polygons are equally authoritative.
    for pts in green.values():
        if intersects_tile(pts, tx, ty):
            lp = local_polyline(pts, tx, ty)
            d.polygon(lp, fill=(27, 47, 34, 255) if night else (63, 93, 63, 255))
            d.line(lp + [lp[0]], fill=(74, 91, 69, 120), width=2)

    # Roads: exact centerline, sidewalk envelope and authored widths.
    for rid, pts in road_pts.items():
        if len(pts) < 2 or not intersects_tile(pts, tx, ty, pad=160):
            continue
        r = roads.get(rid, {})
        width = max(1, int(float(r.get("width", 70))))
        sidewalk = max(0, int(float(r.get("sidewalk_width", 0))))
        curb = max(1, int(float(r.get("curb_width", 4))))
        lp = local_polyline(pts, tx, ty)
        if sidewalk:
            d.line(lp, fill=(94, 91, 84, 255) if night else (139, 136, 126, 255), width=width + 2 * sidewalk, joint="curve")
            d.line(lp, fill=(126, 117, 98, 95), width=width + 2 * curb, joint="curve")
        d.line(lp, fill=(39, 43, 47, 255) if night else (76, 79, 78, 255), width=width, joint="curve")
        # wet/worn road texture: narrow translucent cues do not alter geometry
        d.line(lp, fill=(105, 111, 112, 38 if night else 25), width=max(2, width // 8), joint="curve")
        d.line(lp, fill=(158, 151, 128, 58), width=max(1, width // 36), joint="curve")

    # Authored crossings after asphalt so they remain readable.
    for r in crosswalks:
        draw_rotated_crosswalk(im, r, tx, ty)

    # Trees: exact authored centers/sizes, visually restrained footprint to avoid the old giant-base problem.
    for r in vegetation:
        x, y, size = float(r["x"]), float(r["y"]), float(r["size"])
        lx, ly = x - tx * TILE, y - ty * TILE
        if lx < -size or ly < -size or lx > TILE + size or ly > TILE + size:
            continue
        canopy = max(12, size * 0.22)
        pit = max(5, canopy * 0.20)
        d.ellipse((lx-pit, ly-pit, lx+pit, ly+pit), fill=(55, 48, 41, 245), outline=(100, 91, 73, 140), width=1)
        d.ellipse((lx-canopy, ly-canopy, lx+canopy, ly+canopy), fill=(24, 53, 36, 235) if night else (46, 88, 51, 235), outline=(65, 91, 61, 170), width=2)


def paint_layer(layer, mode, tx, ty, roads, road_pts, buildings, levels, water, green, crosswalks, vegetation):
    bg, primary, accent = palette(layer, mode)
    im = Image.new("RGBA", (TILE, TILE), bg)
    d = ImageDraw.Draw(im, "RGBA")
    ox, oy = tx * TILE, ty * TILE

    if layer == "ground":
        paint_ground_semantics(im, d, tx, ty, mode, roads, road_pts, water, green, crosswalks, vegetation)

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
            x0, y0, x1, y1 = local_box(x, y, w, h, tx, ty)
            if x1 < 0 or y1 < 0 or x0 > TILE or y0 > TILE:
                continue
            inset = 4 if layer == "ground" else 10 if layer in ("first_floor", "second_floor") else 14
            if layer == "ground":
                # collision-locked footprint with gritty rooftop/facade language; never extends outside footprint
                d.rectangle((x0 + inset, y0 + inset, x1 - inset, y1 - inset), fill=(48, 47, 47, 255), outline=(104, 94, 78, 210), width=3)
                d.rectangle((x0 + inset + 7, y0 + inset + 7, x1 - inset - 7, y1 - inset - 7), outline=(24, 26, 28, 170), width=2)
                # warm window/service-light cues kept inside the footprint
                step = max(38, int(min(w, h) / 5))
                for wx in range(int(x0 + 18), int(x1 - 12), step):
                    if -20 <= wx <= TILE + 20:
                        d.rectangle((wx, y0 + 10, wx + 8, y0 + 15), fill=(219, 155, 79, 175))
                # deterministic rooftop utility blocks add authored density without modifying collision
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                rw = min(34, max(12, w * .09))
                rh = min(24, max(9, h * .07))
                d.rectangle((cx-rw, cy-rh, cx+rw, cy+rh), fill=(61, 61, 59, 245), outline=(109, 103, 91, 180), width=2)
            else:
                d.rectangle((x0 + inset, y0 + inset, x1 - inset, y1 - inset), fill=primary, outline=accent, width=3)
                if layer == "roof":
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                    rw, rh = min(40, w * .18), min(28, h * .15)
                    d.rectangle((cx-rw, cy-rh, cx+rw, cy+rh), fill=(91, 90, 84, 235), outline=(155, 146, 128, 220), width=2)

    if layer == "hell":
        for i in range(0, TILE, 96):
            d.line((0, i, TILE, i + 180), fill=primary, width=11)
    elif layer == "underground":
        for i in range(32, TILE, 128):
            d.line((i, 0, i, TILE), fill=(86, 83, 69, 45), width=2)
    elif layer == "clouds":
        seed = (tx * 73856093) ^ (ty * 19349663) ^ (0 if mode == "day" else 83492791)
        for n in range(8):
            cx = (seed + n * 181) % (TILE + 300) - 150
            cy = ((seed >> 5) + n * 271) % (TILE + 260) - 130
            rx = 90 + ((seed >> (n % 13)) & 63)
            ry = 38 + ((seed >> ((n + 3) % 13)) & 31)
            d.ellipse((cx-rx, cy-ry, cx+rx, cy+ry), fill=primary)

    return im


def build_ground_preview(cols, rows_n):
    # Stitches the same production tiles, then scales only for approval viewing.
    # This is not a separate concept render.
    scale = 0.125
    preview = Image.new("RGB", (int(cols*TILE*scale), int(rows_n*TILE*scale)), (8, 10, 13))
    ground = OUT / "ground" / "night"
    small = int(TILE * scale)
    for ty in range(rows_n):
        for tx in range(cols):
            p = ground / f"tile_{tx:02d}_{ty:02d}.png"
            tile = Image.open(p).convert("RGB").resize((small, small), Image.Resampling.LANCZOS)
            preview.paste(tile, (tx * small, ty * small))
    preview.save(OUT / "GROUND_NIGHT_APPROVAL_PREVIEW.png", optimize=True)


def main():
    cfg = map_cfg()
    cols = math.ceil(int(cfg["world_w"]) / TILE)
    rows_n = math.ceil(int(cfg["world_h"]) / TILE)
    roads, pts = road_data()
    buildings = rows("buildings.csv")
    levels = building_levels()
    water = polygon_data("water_polygons.csv")
    green = polygon_data("green_polygons.csv")
    crosswalks = rows("crosswalks.csv")
    vegetation = rows("iterated_vegetation.csv")
    OUT.mkdir(parents=True, exist_ok=True)

    for layer in LAYERS:
        for mode in ("day", "night"):
            target = OUT / layer / mode
            target.mkdir(parents=True, exist_ok=True)
            for ty in range(rows_n):
                for tx in range(cols):
                    im = paint_layer(layer, mode, tx, ty, roads, pts, buildings, levels, water, green, crosswalks, vegetation)
                    im.save(target / f"tile_{tx:02d}_{ty:02d}.png", optimize=True)

    build_ground_preview(cols, rows_n)
    print(f"V100_ART_OVERLAYS_OK layers={len(LAYERS)} tiles_per_variant={cols*rows_n} world={cfg['world_w']}x{cfg['world_h']} preview=GROUND_NIGHT_APPROVAL_PREVIEW.png")


if __name__ == "__main__":
    main()
