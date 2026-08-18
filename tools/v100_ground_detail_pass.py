#!/usr/bin/env python3
"""Authored land, rooftop and block-identity detail for v1.0 Ground/Night.

This is a cosmetic post-pass. It reads only existing Map 001 authoring tables and
approved material crops; it never changes collision, traversal, road, water,
green or building footprints.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "mapfiles/data/map_001_gwb_corridor"
APPROVED = ROOT / "assets/environment/approved"
TILE = 1024
GROUND_BG_NIGHT = (18, 22, 27)
GROUND_BG_DAY = (91, 94, 89)


@lru_cache(maxsize=None)
def rows(name: str):
    p = MAP / name
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def massing():
    return {str(r.get("building_id", "")): r for r in rows("building_modular_massing.csv") if r.get("building_id")}


def _tile_span(x: float, y: float, w: float, h: float, pad: float = 24.0):
    x0 = max(0, int((x - pad) // TILE))
    y0 = max(0, int((y - pad) // TILE))
    x1 = max(x0, int((x + max(0.0, w) + pad) // TILE))
    y1 = max(y0, int((y + max(0.0, h) + pad) // TILE))
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            yield tx, ty


@lru_cache(maxsize=1)
def module_index():
    out = defaultdict(list)
    for r in rows("building_modules.csv"):
        try:
            x, y = float(r["x"]), float(r["y"])
            w, h = float(r.get("w", 0) or 0), float(r.get("h", 0) or 0)
        except (KeyError, TypeError, ValueError):
            continue
        for key in _tile_span(x, y, w, h):
            out[key].append(r)
    return out


@lru_cache(maxsize=1)
def building_index():
    out = defaultdict(list)
    for r in rows("buildings.csv"):
        try:
            x, y = float(r["x"]), float(r["y"])
            w, h = float(r["w"]), float(r["h"])
        except (KeyError, TypeError, ValueError):
            continue
        for key in _tile_span(x, y, w, h, 8.0):
            out[key].append(r)
    return out


def _local_box(row, tx: int, ty: int):
    x, y = float(row["x"]), float(row["y"])
    w, h = float(row.get("w", 0) or 0), float(row.get("h", 0) or 0)
    ox, oy = tx * TILE, ty * TILE
    return x - ox, y - oy, x + w - ox, y + h - oy


@lru_cache(maxsize=2)
def _urban_land_texture(mode: str) -> Image.Image | None:
    """Return a restrained service-lot/urban-land texture at world tile scale."""
    path = APPROVED / "city_concrete_64.png"
    if not path.is_file():
        return None
    source = Image.open(path).convert("RGBA")
    night = mode == "night"
    source = ImageEnhance.Brightness(source).enhance(0.38 if night else 0.78)
    wash_color = (10, 16, 22, 255) if night else (92, 94, 88, 255)
    source = Image.blend(source, Image.new("RGBA", source.size, wash_color), 0.18 if night else 0.10)
    tile = Image.new("RGBA", (TILE, TILE), (0, 0, 0, 255))
    sw, sh = source.size
    for y in range(0, TILE, sh):
        for x in range(0, TILE, sw):
            tile.alpha_composite(source, (x, y))
    return tile


def apply_land_base(im: Image.Image, mode: str) -> None:
    """Replace only untouched Ground background pixels with urban land texture.

    Roads, sidewalks, water, green polygons, buildings and authored props have
    already painted over the background. Exact-color masking therefore fills
    only the previously empty urban/service parcels and cannot move geometry.
    """
    texture = _urban_land_texture(mode)
    if texture is None:
        return
    base_rgb = GROUND_BG_NIGHT if mode == "night" else GROUND_BG_DAY
    rgb = im.convert("RGB")
    difference = ImageChops.difference(rgb, Image.new("RGB", im.size, base_rgb)).convert("L")
    untouched = difference.point(lambda value: 255 if value == 0 else 0)
    im.paste(texture, (0, 0), untouched)


def draw_module(d: ImageDraw.ImageDraw, row: dict, tx: int, ty: int, night: bool):
    try:
        x0, y0, x1, y1 = _local_box(row, tx, ty)
    except (KeyError, TypeError, ValueError):
        return
    if x1 < -24 or y1 < -24 or x0 > TILE + 24 or y0 > TILE + 24:
        return
    component = str(row.get("component_id", ""))
    metal = (76, 82, 82, 238) if night else (135, 139, 134, 238)
    edge = (157, 149, 130, 155) if night else (91, 89, 82, 160)
    dark = (28, 32, 34, 240) if night else (80, 82, 79, 230)
    if component == "parapet":
        d.rectangle((x0, y0, x1, y1), fill=(106, 103, 95, 185), outline=(176, 165, 143, 105), width=1)
    elif component in {"hvac_small", "hvac_large"}:
        d.rectangle((x0, y0, x1, y1), fill=metal, outline=edge, width=1)
        if abs(x1 - x0) >= abs(y1 - y0):
            for fx in range(int(x0 + 4), int(x1 - 2), 6):
                d.line((fx, y0 + 2, fx, y1 - 2), fill=(198, 190, 171, 88), width=1)
        else:
            for fy in range(int(y0 + 4), int(y1 - 2), 6):
                d.line((x0 + 2, fy, x1 - 2, fy), fill=(198, 190, 171, 88), width=1)
    elif component == "roof_hatch":
        d.rectangle((x0, y0, x1, y1), fill=dark, outline=edge, width=2)
        d.line((x0 + 4, y0 + 4, x1 - 4, y1 - 4), fill=(170, 161, 142, 90), width=1)
    elif component == "chimney":
        d.rectangle((x0, y0, x1, y1), fill=(72, 62, 53, 238), outline=(154, 132, 108, 130), width=1)
        if x1 - x0 > 7 and y1 - y0 > 7:
            d.ellipse((x0 + 3, y0 + 3, x1 - 3, y1 - 3), fill=(22, 25, 26, 220))
    elif component == "rooftop_structure":
        d.rectangle((x0, y0, x1, y1), fill=(48, 50, 49, 248), outline=edge, width=2)
        if x1 - x0 > 14 and y1 - y0 > 14:
            d.rectangle((x0 + 6, y0 + 6, x1 - 6, y1 - 6), outline=(19, 23, 25, 165), width=1)
        if night and x1 - x0 > 18:
            d.rectangle((x0 + 7, y1 - 8, min(x0 + 19, x1 - 4), y1 - 4), fill=(226, 157, 78, 155))
    elif component == "wall_module":
        d.rectangle((x0, y0, x1, y1), fill=(94, 72, 60, 120), outline=(151, 131, 110, 75), width=1)
    elif "water" in component or "tank" in component:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        rr = max(4.0, min(abs(x1 - x0), abs(y1 - y0)) * 0.45)
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=(77, 72, 61, 240), outline=edge, width=2)
    else:
        d.rectangle((x0, y0, x1, y1), fill=(62, 64, 62, 200), outline=(129, 124, 112, 95), width=1)


def draw_identity(d: ImageDraw.ImageDraw, building: dict, tx: int, ty: int, night: bool):
    bid = str(building.get("id", ""))
    meta = massing().get(bid)
    if not meta:
        return
    try:
        x0, y0, x1, y1 = _local_box(building, tx, ty)
    except (KeyError, TypeError, ValueError):
        return
    if x1 < 0 or y1 < 0 or x0 > TILE or y0 > TILE:
        return
    variant = str(meta.get("shape_variant", ""))
    kind = str(meta.get("building_kind", ""))
    seam = (168, 151, 124, 78) if night else (74, 70, 63, 88)
    shade = (10, 15, 18, 62) if night else (57, 59, 56, 52)
    ix0, iy0, ix1, iy1 = x0 + 20, y0 + 20, x1 - 30, y1 - 30
    if ix1 <= ix0 + 16 or iy1 <= iy0 + 16:
        return
    cx, cy = (ix0 + ix1) / 2, (iy0 + iy1) / 2
    iw, ih = ix1 - ix0, iy1 - iy0
    if variant == "courtyard":
        dx, dy = iw * 0.24, ih * 0.24
        d.rectangle((ix0 + dx, iy0 + dy, ix1 - dx, iy1 - dy), fill=shade, outline=seam, width=2)
    elif variant == "u_shape":
        d.line((ix0, cy, cx, cy, cx, iy1), fill=seam, width=3)
    elif variant == "l_shape":
        d.line((cx, iy0, cx, cy, ix1, cy), fill=seam, width=3)
    elif variant == "stepped":
        d.line((ix0, iy0 + ih * .33, ix0 + iw * .35, iy0 + ih * .33, ix0 + iw * .35, iy0 + ih * .66, ix1, iy0 + ih * .66), fill=seam, width=3)
    elif variant == "chamfered":
        cut = min(24.0, iw * .12, ih * .12)
        d.line((ix0, iy0 + cut, ix0 + cut, iy0), fill=seam, width=2)
        d.line((ix1 - cut, iy1, ix1, iy1 - cut), fill=seam, width=2)
    elif variant == "perimeter":
        d.rectangle((ix0, iy0, ix1, iy1), outline=seam, width=3)
    if kind == "church_landmark" or variant == "cruciform_church":
        ridge = (95, 84, 67, 150)
        if ih >= iw:
            d.rectangle((cx - 8, iy0, cx + 8, iy1), fill=ridge, outline=seam, width=1)
            d.rectangle((ix0 + iw * .20, cy - 8, ix1 - iw * .20, cy + 8), fill=ridge, outline=seam, width=1)
        else:
            d.rectangle((ix0, cy - 8, ix1, cy + 8), fill=ridge, outline=seam, width=1)
            d.rectangle((cx - 8, iy0 + ih * .20, cx + 8, iy1 - ih * .20), fill=ridge, outline=seam, width=1)
        rr = 11
        d.polygon(((cx, cy - rr), (cx + rr, cy), (cx, cy + rr), (cx - rr, cy)), fill=(72, 76, 74, 245), outline=(173, 158, 130, 165))
        d.line((cx, cy - rr - 7, cx, cy + rr + 7), fill=(184, 166, 133, 130), width=2)
        if night:
            d.ellipse((cx - 4, cy - 4, cx + 4, cy + 4), fill=(239, 180, 96, 185))


def apply(im: Image.Image, tx: int, ty: int, mode: str = "night") -> Image.Image:
    """Overlay urban land and authored building detail onto one Ground tile."""
    apply_land_base(im, mode)
    d = ImageDraw.Draw(im, "RGBA")
    night = mode == "night"
    for building in building_index().get((tx, ty), []):
        draw_identity(d, building, tx, ty, night)
    for module in module_index().get((tx, ty), []):
        draw_module(d, module, tx, ty, night)
    return im
