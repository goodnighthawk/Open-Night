#!/usr/bin/env python3
"""Build v1.0 collision-locked visual overlays for Map 001.

The functional CSV map remains authoritative. This tool only paints cosmetic
RGBA tiles in exact world coordinates. It intentionally refuses to derive
collision from pixels.

Ground uses the repository's approved material crops and authored cosmetic
placement tables, but every road, sidewalk, building, water, crossing and
vegetation footprint still comes from the map CSVs.
"""
from __future__ import annotations

import csv
import hashlib
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "mapfiles/data/map_001_gwb_corridor"
OUT = ROOT / "assets/environment/approved/map_001_gwb_corridor/v100_layers"
APPROVED = ROOT / "assets/environment/approved"
STREET_PROPS = ROOT / "assets/street_props"
TILE = 1024
LAYERS = ("hell", "underground", "ground", "first_floor", "second_floor", "roof", "clouds", "hud_space")

ROAD_MATERIAL = "asphalt_64.png"
SIDEWALK_MATERIAL = "sidewalk_64.png"
WATER_MATERIAL = "water_64.png"
ROOF_MATERIALS = (
    "city_roof_tar_64.png",
    "city_roof_gravel_64.png",
    "city_roof_concrete_64.png",
    "city_roof_metal_gray_64.png",
    "city_roof_metal_green_64.png",
    "city_roof_tile_64.png",
)
FACADE_MATERIALS = (
    "city_red_brick_64.png",
    "city_red_brick2_64.png",
    "city_brown_brick_64.png",
    "city_beige_stone_64.png",
    "city_gray_stone_64.png",
    "city_concrete_64.png",
    "city_painted_plaster_64.png",
)
PROP_FILES = {
    "streetlamp": "curved_streetlamp.png",
    "hydrant": "fire_hydrant.png",
    "bike_rack": "bicycle_rack.png",
}


@lru_cache(maxsize=None)
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


@lru_cache(maxsize=1)
def building_visuals():
    return {r["building_id"]: r for r in rows("building_visuals.csv") if r.get("building_id")}


def stable_int(text: str) -> int:
    return int.from_bytes(hashlib.sha256(str(text).encode("utf-8")).digest()[:8], "big")


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
        "ground": ((18, 22, 27, 255) if night else (91, 94, 89, 255), (43, 46, 49, 255) if night else (79, 81, 78, 255), (122, 118, 104, 255)),
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


@lru_cache(maxsize=64)
def _material_source(name: str, mode: str) -> Image.Image | None:
    path = APPROVED / name
    if not path.is_file():
        return None
    im = Image.open(path).convert("RGBA")
    if mode == "night":
        factors = {
            ROAD_MATERIAL: 0.53,
            SIDEWALK_MATERIAL: 0.55,
            WATER_MATERIAL: 0.52,
        }
        factor = factors.get(name, 0.58)
        im = ImageEnhance.Brightness(im).enhance(factor)
        wash = Image.new("RGBA", im.size, (9, 16, 27, 255))
        im = Image.blend(im, wash, 0.16)
    return im


@lru_cache(maxsize=96)
def _material_tile(name: str, mode: str) -> Image.Image | None:
    source = _material_source(name, mode)
    if source is None:
        return None
    canvas = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
    sw, sh = source.size
    if sw <= 0 or sh <= 0:
        return None
    for y in range(0, TILE, sh):
        for x in range(0, TILE, sw):
            canvas.alpha_composite(source, (x, y))
    return canvas


def fill_mask(im: Image.Image, mask: Image.Image, material_name: str, mode: str, fallback):
    texture = _material_tile(material_name, mode)
    if texture is None:
        solid = Image.new("RGBA", (TILE, TILE), fallback)
        im.paste(solid, (0, 0), mask)
    else:
        im.paste(texture, (0, 0), mask)


def polygon_mask(points, tx, ty):
    mask = Image.new("L", (TILE, TILE), 0)
    ImageDraw.Draw(mask).polygon(local_polyline(points, tx, ty), fill=255)
    return mask


def line_mask(points, tx, ty, width):
    mask = Image.new("L", (TILE, TILE), 0)
    ImageDraw.Draw(mask).line(local_polyline(points, tx, ty), fill=255, width=max(1, int(width)), joint="curve")
    return mask


def rect_mask(box):
    mask = Image.new("L", (TILE, TILE), 0)
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    return mask


def _procedural_green_texture(mode: str, tx: int, ty: int):
    night = mode == "night"
    base = (24, 45, 31, 255) if night else (61, 91, 60, 255)
    im = Image.new("RGBA", (TILE, TILE), base)
    d = ImageDraw.Draw(im, "RGBA")
    for gy in range(10, TILE, 28):
        for gx in range(10, TILE, 28):
            seed = stable_int(f"green:{tx}:{ty}:{gx}:{gy}")
            dx = int(seed % 13) - 6
            dy = int((seed >> 5) % 13) - 6
            r = 1 + int((seed >> 11) % 3)
            if night:
                col = (48 + seed % 18, 76 + (seed >> 8) % 18, 50 + (seed >> 16) % 12, 80)
            else:
                col = (88 + seed % 20, 116 + (seed >> 8) % 20, 76 + (seed >> 16) % 16, 75)
            d.ellipse((gx + dx - r, gy + dy - r, gx + dx + r, gy + dy + r), fill=col)
    return im


def parallel_points(points, offset):
    if len(points) < 2:
        return list(points)
    out = []
    for i, (x, y) in enumerate(points):
        ax, ay = points[max(0, i - 1)]
        bx, by = points[min(len(points) - 1, i + 1)]
        dx, dy = bx - ax, by - ay
        mag = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / mag, dx / mag
        out.append((x + nx * offset, y + ny * offset))
    return out


def sampled_polyline(points, spacing):
    if len(points) < 2:
        return []
    samples = []
    carry = 0.0
    for a, b in zip(points, points[1:]):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        seg = math.hypot(dx, dy)
        if seg <= 1e-6:
            continue
        ux, uy = dx / seg, dy / seg
        distance = spacing - carry if carry > 1e-6 else 0.0
        while distance <= seg:
            samples.append((ax + ux * distance, ay + uy * distance, ux, uy))
            distance += spacing
        carry = max(0.0, seg - (distance - spacing))
        if carry >= spacing:
            carry %= spacing
    return samples


def draw_bridge_details(im, d, tx, ty, mode, points, width, sidewalk):
    """Give authored bridge roads a recognizable GWB structural treatment.

    The drivable/walkable envelope is unchanged. Towers and steelwork use the
    authored landmark anchors and are decorative only.
    """
    if len(points) < 2 or not intersects_tile(points, tx, ty, pad=220):
        return
    night = mode == "night"
    ox, oy = tx * TILE, ty * TILE
    half_deck = width * 0.5
    outer = half_deck + sidewalk * 0.62
    deck_col = (162, 160, 150, 180) if night else (118, 120, 118, 190)
    steel_col = (113, 124, 126, 230) if night else (151, 155, 151, 235)
    shadow_col = (3, 8, 13, 150) if night else (39, 44, 45, 105)

    for off in (-outer, outer):
        rail = local_polyline(parallel_points(points, off), tx, ty)
        d.line(rail, fill=shadow_col, width=7, joint="curve")
        d.line(rail, fill=steel_col, width=2, joint="curve")
    for off in (-half_deck, half_deck):
        edge = local_polyline(parallel_points(points, off), tx, ty)
        d.line(edge, fill=deck_col, width=3, joint="curve")

    for x, y, ux, uy in sampled_polyline(points, 96.0):
        lx, ly = x - ox, y - oy
        if lx < -outer or ly < -outer or lx > TILE + outer or ly > TILE + outer:
            continue
        nx, ny = -uy, ux
        a = (lx - nx * outer, ly - ny * outer)
        b = (lx + nx * outer, ly + ny * outer)
        d.line((a, b), fill=(99, 111, 113, 45 if night else 38), width=2)
    for x, y, ux, uy in sampled_polyline(points, 144.0):
        lx, ly = x - ox, y - oy
        nx, ny = -uy, ux
        for sign in (-1, 1):
            px, py = lx + nx * outer, ly + ny * outer
            if -20 <= px <= TILE + 20 and -20 <= py <= TILE + 20:
                if night:
                    d.ellipse((px-8, py-8, px+8, py+8), fill=(236, 175, 92, 24))
                    d.ellipse((px-2.5, py-2.5, px+2.5, py+2.5), fill=(244, 189, 104, 215))
                else:
                    d.ellipse((px-2, py-2, px+2, py+2), fill=(207, 201, 177, 180))

    for lm in rows("landmarks.csv"):
        kind = str(lm.get("kind", ""))
        if kind not in {"bridge_tower", "bridge_portal"}:
            continue
        try:
            lx = float(lm["x"]) - ox
            ly = float(lm["y"]) - oy
        except (KeyError, TypeError, ValueError):
            continue
        if lx < -220 or ly < -220 or lx > TILE + 220 or ly > TILE + 220:
            continue
        if kind == "bridge_tower":
            tower_off = outer + 22
            for sign in (-1, 1):
                cy = ly + sign * tower_off
                d.rectangle((lx-15, cy-39, lx+15, cy+39), fill=(52, 61, 63, 245), outline=steel_col, width=3)
                d.rectangle((lx-7, cy-31, lx+7, cy+31), fill=(18, 26, 29, 230), outline=(141, 149, 145, 130), width=1)
                d.line((lx-13, cy-31, lx+13, cy+31), fill=(131, 141, 140, 100), width=2)
                d.line((lx+13, cy-31, lx-13, cy+31), fill=(131, 141, 140, 100), width=2)
            d.rectangle((lx-12, ly-outer-4, lx+12, ly+outer+4), outline=(132, 143, 143, 130), width=2)
            if night:
                for sign in (-1, 1):
                    cy = ly + sign * (tower_off + 38)
                    d.ellipse((lx-5, cy-5, lx+5, cy+5), fill=(235, 175, 91, 65))
        else:
            d.rectangle((lx-8, ly-outer-9, lx+8, ly+outer+9), fill=(47, 55, 57, 225), outline=steel_col, width=2)
            d.line((lx, ly-outer, lx, ly+outer), fill=(169, 165, 150, 100), width=2)


def draw_dashed_polyline(d, pts, fill, width=2, dash=22, gap=24):
    if len(pts) < 2:
        return
    drawing = True
    remaining = float(dash)
    for a, b in zip(pts, pts[1:]):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        seg = math.hypot(dx, dy)
        if seg <= 1e-6:
            continue
        ux, uy = dx / seg, dy / seg
        travelled = 0.0
        while travelled < seg:
            step = min(remaining, seg - travelled)
            if drawing and step > 0:
                x0 = ax + ux * travelled
                y0 = ay + uy * travelled
                x1 = ax + ux * (travelled + step)
                y1 = ay + uy * (travelled + step)
                d.line((x0, y0, x1, y1), fill=fill, width=width)
            travelled += step
            remaining -= step
            if remaining <= 1e-6:
                drawing = not drawing
                remaining = float(dash if drawing else gap)


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
    patch_size = int(math.ceil(max(length, width) * 1.6 + 16))
    patch = Image.new("RGBA", (patch_size, patch_size), (0, 0, 0, 0))
    pd = ImageDraw.Draw(patch, "RGBA")
    cx = cy = patch_size / 2
    pos = -width / 2
    stripe_index = 0
    while pos < width / 2:
        alpha = 212 if stripe_index % 3 else 188
        pd.rectangle((cx - length / 2, cy + pos, cx + length / 2, cy + min(pos + stripe, width / 2)), fill=(224, 222, 211, alpha))
        pos += stripe + gap
        stripe_index += 1
    patch = patch.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=False)
    im.alpha_composite(patch, (int(lx - patch_size / 2), int(ly - patch_size / 2)))


@lru_cache(maxsize=32)
def _prop_source(filename: str, mode: str) -> Image.Image | None:
    path = STREET_PROPS / filename
    if not path.is_file():
        return None
    im = Image.open(path).convert("RGBA")
    if mode == "night":
        im = ImageEnhance.Brightness(im).enhance(0.72)
    return im


def paste_prop(im, filename, lx, ly, height, rotation, mode):
    source = _prop_source(filename, mode)
    if source is None:
        return False
    height = max(8, int(height))
    width = max(6, int(round(source.width * height / max(1, source.height))))
    sprite = source.resize((width, height), Image.Resampling.LANCZOS)
    if abs(rotation) > 0.01:
        sprite = sprite.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True)
    im.alpha_composite(sprite, (int(lx - sprite.width / 2), int(ly - sprite.height / 2)))
    return True


def draw_street_details(im, d, tx, ty, mode):
    night = mode == "night"
    ox, oy = tx * TILE, ty * TILE
    for row in rows("street_detail_pass23.csv"):
        try:
            x, y = float(row["x"]), float(row["y"])
            size = max(0.5, float(row.get("size", 1) or 1))
            rotation = float(row.get("rotation", 0) or 0)
        except (TypeError, ValueError, KeyError):
            continue
        lx, ly = x - ox, y - oy
        if lx < -64 or ly < -64 or lx > TILE + 64 or ly > TILE + 64:
            continue
        kind = str(row.get("kind", ""))
        if kind == "streetlamp":
            if night:
                glow = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
                gd = ImageDraw.Draw(glow, "RGBA")
                for radius, alpha in ((34, 18), (22, 28), (10, 46)):
                    gd.ellipse((lx-radius, ly-radius, lx+radius, ly+radius), fill=(240, 178, 92, alpha))
                im.alpha_composite(glow)
            paste_prop(im, PROP_FILES[kind], lx, ly, 27 * size, rotation, mode)
        elif kind == "hydrant":
            paste_prop(im, PROP_FILES[kind], lx, ly, 20 * size, rotation, mode)
        elif kind == "bike_rack":
            paste_prop(im, PROP_FILES[kind], lx, ly, 18 * size, rotation, mode)
        elif kind == "drain":
            r = max(3, 6 * size)
            d.ellipse((lx-r, ly-r*.45, lx+r, ly+r*.45), fill=(20, 23, 25, 210), outline=(91, 94, 91, 120), width=1)
            for off in (-r*.45, 0, r*.45):
                d.line((lx+off, ly-r*.3, lx+off, ly+r*.3), fill=(105, 108, 103, 100), width=1)
        elif kind == "utility_cover":
            r = max(4, 6 * size)
            d.ellipse((lx-r, ly-r, lx+r, ly+r), fill=(49, 51, 50, 210), outline=(116, 115, 107, 125), width=1)
            d.ellipse((lx-r*.55, ly-r*.55, lx+r*.55, ly+r*.55), outline=(31, 33, 34, 145), width=1)
        elif kind in {"sidewalk_repair", "curb_patch", "tree_pit"}:
            rw = 8 * size
            rh = 5 * size
            fill = (66, 64, 59, 90) if night else (102, 99, 91, 85)
            d.rectangle((lx-rw, ly-rh, lx+rw, ly+rh), fill=fill, outline=(39, 41, 41, 90), width=1)
        elif kind == "bollard":
            d.ellipse((lx-3*size, ly-3*size, lx+3*size, ly+3*size), fill=(59, 62, 61, 235), outline=(146, 144, 131, 135), width=1)
        elif kind == "mailbox":
            d.rectangle((lx-4*size, ly-6*size, lx+4*size, ly+6*size), fill=(35, 61, 74, 235), outline=(106, 122, 124, 130), width=1)
        elif kind == "bench":
            d.rectangle((lx-10*size, ly-3*size, lx+10*size, ly+3*size), fill=(77, 62, 48, 235), outline=(35, 34, 32, 145), width=1)


def draw_frontage_dressing(im, d, tx, ty, mode):
    night = mode == "night"
    ox, oy = tx * TILE, ty * TILE
    for row in rows("iterated_frontage_dressing.csv"):
        try:
            x, y = float(row["x"]), float(row["y"])
            w, h = float(row.get("w", 0) or 0), float(row.get("h", 0) or 0)
        except (TypeError, ValueError, KeyError):
            continue
        lx, ly = x - ox, y - oy
        if lx + w < -32 or ly + h < -32 or lx > TILE + 32 or ly > TILE + 32:
            continue
        kind = str(row.get("kind", ""))
        box = (lx, ly, lx + w, ly + h)
        seed = stable_int(str(row.get("id", kind)))
        if kind == "frontage_wear":
            d.rectangle(box, fill=(19, 22, 24, 38 if night else 28))
        elif kind == "service_patch":
            d.rectangle(box, fill=(41, 42, 40, 170), outline=(89, 84, 75, 100), width=1)
        elif kind == "basement_grate":
            d.rectangle(box, fill=(29, 31, 31, 210), outline=(105, 102, 92, 110), width=1)
            step = max(3, int(min(max(w, 1), max(h, 1)) / 4))
            for gx in range(int(lx + 2), int(lx + w - 1), step):
                d.line((gx, ly + 2, gx, ly + h - 2), fill=(116, 115, 105, 85), width=1)
        elif kind == "awning":
            colors = ((91, 28, 31, 220), (31, 61, 52, 220), (38, 53, 82, 220))
            d.rectangle(box, fill=colors[seed % len(colors)], outline=(172, 152, 117, 105), width=1)
            if night:
                d.line((lx, ly + h, lx + w, ly + h), fill=(236, 174, 91, 125), width=2)
        elif kind == "stoop":
            d.rectangle(box, fill=(83, 82, 77, 205), outline=(133, 128, 115, 95), width=1)
        elif kind == "planter":
            d.rectangle(box, fill=(70, 54, 40, 220), outline=(119, 96, 67, 115), width=1)
            d.ellipse((lx+2, ly+2, lx+w-2, ly+h-2), fill=(39, 68, 44, 190))
        elif kind in {"sandwich_board", "trash_bin"}:
            fill = (117, 97, 65, 220) if kind == "sandwich_board" else (47, 51, 50, 235)
            d.rectangle(box, fill=fill, outline=(24, 26, 27, 140), width=1)
        elif kind == "railing":
            d.rectangle(box, outline=(118, 119, 113, 165), width=1)
        elif kind == "litter_cluster":
            for n in range(3):
                px = lx + (seed >> (n * 7)) % max(1, int(max(w, 1)))
                py = ly + (seed >> (n * 9 + 3)) % max(1, int(max(h, 1)))
                d.ellipse((px-1, py-1, px+1, py+1), fill=(129, 123, 108, 95))
        elif "sign" in kind:
            d.rectangle(box, fill=(34, 37, 40, 220), outline=(160, 149, 127, 90), width=1)
            if night:
                sign_cols = ((221, 82, 88, 130), (73, 161, 181, 120), (236, 173, 88, 135))
                d.line((lx+2, ly+h/2, lx+w-2, ly+h/2), fill=sign_cols[seed % len(sign_cols)], width=2)


def draw_building_ground(im, d, b, tx, ty, mode):
    bid = str(b["id"])
    x, y, w, h = (float(b[k]) for k in ("x", "y", "w", "h"))
    x0, y0, x1, y1 = local_box(x, y, w, h, tx, ty)
    if x1 < 0 or y1 < 0 or x0 > TILE or y0 > TILE:
        return
    seed = stable_int(bid)
    roof_material = ROOF_MATERIALS[seed % len(ROOF_MATERIALS)]
    facade_material = FACADE_MATERIALS[(seed >> 8) % len(FACADE_MATERIALS)]
    visual = building_visuals().get(bid, {})
    facade_depth = max(7, min(15, int(float(visual.get("height_px", 12) or 12))))
    footprint = (x0 + 2, y0 + 2, x1 - 2, y1 - 2)
    fill_mask(im, rect_mask(footprint), roof_material, mode, (48, 47, 47, 255))
    fd = min(facade_depth, max(3, int(min(max(w, 1), max(h, 1)) * 0.18)))
    south = (x0 + 2, max(y0 + 2, y1 - fd - 2), x1 - 2, y1 - 2)
    east = (max(x0 + 2, x1 - fd - 2), y0 + 2, x1 - 2, y1 - 2)
    fill_mask(im, rect_mask(south), facade_material, mode, (56, 48, 44, 255))
    fill_mask(im, rect_mask(east), facade_material, mode, (53, 46, 43, 255))
    d.rectangle(footprint, outline=(123, 112, 93, 190), width=2)
    inner = (x0 + 7, y0 + 7, x1 - fd - 6, y1 - fd - 6)
    if inner[2] > inner[0] and inner[3] > inner[1]:
        d.rectangle(inner, outline=(22, 25, 28, 150), width=2)
    if mode == "night":
        spacing = max(22, min(44, int(max(22, w / 7))))
        start_x = int(x0 + 10 + (seed % max(1, spacing // 2)))
        for wx in range(start_x, int(x1 - 8), spacing):
            if ((seed + wx) // spacing) % 3 != 0:
                d.rectangle((wx, y1 - fd + 2, min(wx + 7, x1 - 4), y1 - fd + 6), fill=(229, 161, 80, 180))
        spacing_y = max(24, min(46, int(max(24, h / 7))))
        start_y = int(y0 + 10 + ((seed >> 6) % max(1, spacing_y // 2)))
        for wy in range(start_y, int(y1 - 8), spacing_y):
            if ((seed + wy) // spacing_y) % 4 != 0:
                d.rectangle((x1 - fd + 2, wy, x1 - fd + 6, min(wy + 7, y1 - 4)), fill=(218, 151, 74, 160))
    roof_x0, roof_y0 = x0 + 12, y0 + 12
    roof_x1, roof_y1 = x1 - fd - 10, y1 - fd - 10
    if roof_x1 - roof_x0 > 26 and roof_y1 - roof_y0 > 22:
        area = max(1.0, w * h)
        count = max(1, min(5, int(area / 70000) + 1))
        for n in range(count):
            nseed = stable_int(f"{bid}:roof:{n}")
            rw = 10 + nseed % 13
            rh = 7 + (nseed >> 6) % 10
            span_x = max(1, int(roof_x1 - roof_x0 - 2 * rw))
            span_y = max(1, int(roof_y1 - roof_y0 - 2 * rh))
            cx = roof_x0 + rw + (nseed >> 12) % span_x
            cy = roof_y0 + rh + (nseed >> 24) % span_y
            d.rectangle((cx-rw, cy-rh, cx+rw, cy+rh), fill=(61, 63, 62, 235), outline=(126, 121, 108, 145), width=1)
            for fin in range(-int(rw)+4, int(rw)-3, 5):
                d.line((cx+fin, cy-rh+2, cx+fin, cy+rh-2), fill=(148, 145, 132, 80), width=1)
        if seed % 7 == 0 and min(w, h) > 120:
            r = min(13, max(8, int(min(w, h) * 0.06)))
            cx = (roof_x0 + roof_x1) / 2
            cy = roof_y0 + max(r + 4, (roof_y1 - roof_y0) * 0.28)
            d.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(79, 75, 66, 235), outline=(149, 137, 112, 150), width=2)
            d.line((cx, cy+r, cx, cy+r+7), fill=(74, 70, 62, 170), width=2)


def paint_ground_semantics(im, d, tx, ty, mode, roads, road_pts, water, green, crosswalks, vegetation):
    night = mode == "night"
    for pts in water.values():
        if not intersects_tile(pts, tx, ty):
            continue
        mask = polygon_mask(pts, tx, ty)
        fill_mask(im, mask, WATER_MATERIAL, mode, (13, 31, 44, 255) if night else (51, 92, 111, 255))
        lp = local_polyline(pts, tx, ty)
        overlay = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay, "RGBA")
        for yy in range(-20, TILE + 20, 42):
            od.line((0, yy, TILE, yy), fill=(77, 120, 143, 25 if night else 32), width=2)
        clipped = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 0))
        clipped.paste(overlay, (0, 0), mask)
        im.alpha_composite(clipped)
        d.line(lp + [lp[0]], fill=(90, 119, 126, 115), width=2)
    green_texture = _procedural_green_texture(mode, tx, ty)
    for pts in green.values():
        if intersects_tile(pts, tx, ty):
            mask = polygon_mask(pts, tx, ty)
            im.paste(green_texture, (0, 0), mask)
            lp = local_polyline(pts, tx, ty)
            d.line(lp + [lp[0]], fill=(76, 96, 72, 125), width=2)
    for rid, pts in road_pts.items():
        if len(pts) < 2 or not intersects_tile(pts, tx, ty, pad=180):
            continue
        r = roads.get(rid, {})
        width = max(1, int(float(r.get("width", 70))))
        sidewalk = max(0, int(float(r.get("sidewalk_width", 0))))
        curb = max(1, int(float(r.get("curb_width", 4))))
        lanes = max(1, int(float(r.get("lanes", 1) or 1)))
        lp = local_polyline(pts, tx, ty)
        if sidewalk:
            smask = line_mask(pts, tx, ty, width + 2 * sidewalk)
            fill_mask(im, smask, SIDEWALK_MATERIAL, mode, (91, 88, 81, 255) if night else (139, 136, 126, 255))
            d.line(lp, fill=(132, 122, 104, 120), width=width + 2 * curb, joint="curve")
        rmask = line_mask(pts, tx, ty, width)
        fill_mask(im, rmask, ROAD_MATERIAL, mode, (37, 41, 45, 255) if night else (76, 79, 78, 255))
        d.line(lp, fill=(121, 132, 136, 28 if night else 18), width=max(2, width // 9), joint="curve")
        if lanes >= 2:
            draw_dashed_polyline(d, lp, (205, 207, 201, 82 if night else 105), width=max(1, width // 42), dash=26, gap=30)
        if str(r.get("bridge", "")).strip().lower() in {"1", "true", "yes", "on"}:
            draw_bridge_details(im, d, tx, ty, mode, pts, width, sidewalk)
    for r in crosswalks:
        draw_rotated_crosswalk(im, r, tx, ty)
    draw_street_details(im, d, tx, ty, mode)
    for r in vegetation:
        x, y, size = float(r["x"]), float(r["y"]), float(r["size"])
        lx, ly = x - tx * TILE, y - ty * TILE
        if lx < -size or ly < -size or lx > TILE + size or ly > TILE + size:
            continue
        canopy = max(10, min(31, size * 0.22))
        pit = max(4, canopy * 0.18)
        seed = stable_int(str(r.get("id", f"{x}:{y}")))
        d.ellipse((lx-pit, ly-pit, lx+pit, ly+pit), fill=(53, 47, 41, 235), outline=(111, 96, 73, 120), width=1)
        colors = ((24, 52, 35, 238), (31, 66, 42, 225), (44, 76, 47, 205)) if night else ((45, 86, 50, 235), (55, 99, 57, 220), (76, 113, 65, 205))
        lobes = ((0, 0, 0.78), (-0.34, 0.04, 0.56), (0.30, -0.08, 0.58), (0.02, -0.31, 0.52))
        for n, (dx, dy, scale) in enumerate(lobes):
            jitter_x = ((seed >> (n * 5)) % 5 - 2) * 0.03
            jitter_y = ((seed >> (n * 7 + 3)) % 5 - 2) * 0.03
            rr = canopy * scale
            cx = lx + canopy * (dx + jitter_x)
            cy = ly + canopy * (dy + jitter_y)
            d.ellipse((cx-rr, cy-rr, cx+rr, cy+rr), fill=colors[n % len(colors)])
        d.arc((lx-canopy, ly-canopy, lx+canopy, ly+canopy), 205, 335, fill=(109, 133, 91, 90), width=2)


def paint_layer(layer, mode, tx, ty, roads, road_pts, buildings, levels, water, green, crosswalks, vegetation):
    bg, primary, accent = palette(layer, mode)
    im = Image.new("RGBA", (TILE, TILE), bg)
    d = ImageDraw.Draw(im, "RGBA")
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
            if layer == "ground":
                draw_building_ground(im, d, b, tx, ty, mode)
            else:
                inset = 10 if layer in ("first_floor", "second_floor") else 14
                d.rectangle((x0 + inset, y0 + inset, x1 - inset, y1 - inset), fill=primary, outline=accent, width=3)
                if layer == "roof":
                    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                    rw, rh = min(40, w * .18), min(28, h * .15)
                    d.rectangle((cx-rw, cy-rh, cx+rw, cy+rh), fill=(91, 90, 84, 235), outline=(155, 146, 128, 220), width=2)
    if layer == "ground":
        draw_frontage_dressing(im, d, tx, ty, mode)
    elif layer == "hell":
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
