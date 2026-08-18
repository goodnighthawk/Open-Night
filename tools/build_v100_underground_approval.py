#!/usr/bin/env python3
"""Build collision-accurate v1.0 Underground/Night approval art.

Underground traversal is authoritative in roads.csv (level=-1) and
level_connectors.csv. This renderer paints only those semantics; pixels never
create additional walkable space.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

import build_v100_art_overlays as art
import v100_underground_detail_pass as detail

OUT = art.OUT / "underground" / "night"
FULL_PREVIEW = art.OUT / "UNDERGROUND_NIGHT_APPROVAL_PREVIEW.png"
FOCUS_PREVIEW = art.OUT / "UNDERGROUND_NIGHT_FOCUS_PREVIEW.png"
PLAYER_SCALE_PREVIEW = art.OUT / "UNDERGROUND_NIGHT_PLAYER_SCALE_PREVIEW.png"
CONCRETE = "city_concrete_64.png"
FLOOR = art.ROAD_MATERIAL


def underground_roads():
    roads, pts = art.road_data()
    selected = {
        rid: row for rid, row in roads.items()
        if int(float(row.get("level", 0) or 0)) == -1
        and str(row.get("walkable", "true")).strip().lower() not in {"0", "false", "no", "off"}
    }
    return selected, {rid: pts[rid] for rid in selected if rid in pts}


def underground_connectors():
    result = []
    for row in art.rows("level_connectors.csv"):
        try:
            levels = {int(float(row.get("from_level", 0))), int(float(row.get("to_level", 0)))}
        except (TypeError, ValueError):
            continue
        if -1 in levels:
            result.append(row)
    return result


def sampled(points, spacing=176.0):
    if len(points) < 2:
        return []
    result = []
    remaining = 0.0
    for a, b in zip(points, points[1:]):
        ax, ay = map(float, a)
        bx, by = map(float, b)
        dx, dy = bx - ax, by - ay
        seg = math.hypot(dx, dy)
        if seg <= 1e-6:
            continue
        ux, uy = dx / seg, dy / seg
        distance = 0.0 if not result else max(0.0, spacing - remaining)
        while distance <= seg:
            result.append((ax + ux * distance, ay + uy * distance, ux, uy))
            distance += spacing
        remaining = max(0.0, seg - (distance - spacing))
    return result


def paint_tile(tx: int, ty: int, roads: dict, pts_by_id: dict, connectors: list[dict]) -> Image.Image:
    im = Image.new("RGBA", (art.TILE, art.TILE), (7, 9, 10, 255))
    d = ImageDraw.Draw(im, "RGBA")
    ox, oy = tx * art.TILE, ty * art.TILE

    # First pass: wall envelope and exact walkable floor. The visual floor is
    # deliberately narrower than collision, never wider.
    for rid, row in roads.items():
        pts = pts_by_id.get(rid, [])
        if len(pts) < 2 or not art.intersects_tile(pts, tx, ty, pad=120):
            continue
        width = max(48, int(float(row.get("width", 80) or 80)))
        outer = width + 34
        wall_mask = art.line_mask(pts, tx, ty, outer)
        art.fill_mask(im, wall_mask, CONCRETE, "night", (35, 39, 38, 255))
        floor_mask = art.line_mask(pts, tx, ty, max(32, width - 12))
        art.fill_mask(im, floor_mask, FLOOR, "night", (27, 31, 33, 255))
        local = art.local_polyline(pts, tx, ty)
        d.line(local, fill=(83, 87, 82, 115), width=max(2, width // 28), joint="curve")

        # Service pipes hug the corridor edges but remain inside the semantic
        # passage envelope. Their warm/rust accent makes Underground distinct
        # from the blue-black street layer above.
        for sign, col in ((-1, (117, 73, 49, 205)), (1, (70, 94, 88, 205))):
            pipe = art.local_polyline(art.parallel_points(pts, sign * width * 0.34), tx, ty)
            d.line(pipe, fill=(10, 12, 12, 170), width=6, joint="curve")
            d.line(pipe, fill=col, width=2, joint="curve")

        # Drain/grate rhythm and practical maintenance lights are world-spaced,
        # so no pattern jumps at 1024px tile boundaries.
        for x, y, ux, uy in sampled(pts):
            lx, ly = x - ox, y - oy
            if not (-48 <= lx <= art.TILE + 48 and -48 <= ly <= art.TILE + 48):
                continue
            nx, ny = -uy, ux
            grate_half = max(12.0, width * 0.18)
            d.line(
                (lx - nx * grate_half, ly - ny * grate_half, lx + nx * grate_half, ly + ny * grate_half),
                fill=(118, 116, 101, 90), width=2,
            )
            lamp_x, lamp_y = lx + nx * width * 0.27, ly + ny * width * 0.27
            for radius, alpha in ((22, 14), (12, 26), (4, 180)):
                d.ellipse(
                    (lamp_x-radius, lamp_y-radius, lamp_x+radius, lamp_y+radius),
                    fill=(232, 166, 84, alpha),
                )

    # Stairs are themselves authoritative connectors. Paint the whole connector
    # within its declared width and add tread lines perpendicular to travel.
    for row in connectors:
        try:
            a = (float(row["x0"]), float(row["y0"]))
            b = (float(row["x1"]), float(row["y1"]))
            width = max(32.0, float(row.get("width", 64) or 64))
        except (KeyError, TypeError, ValueError):
            continue
        if not art.intersects_tile([a, b], tx, ty, pad=96):
            continue
        connector_mask = art.line_mask([a, b], tx, ty, width)
        art.fill_mask(im, connector_mask, CONCRETE, "night", (44, 45, 42, 255))
        ax, ay = a[0] - ox, a[1] - oy
        bx, by = b[0] - ox, b[1] - oy
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        steps = max(4, int(length / 13.0))
        for i in range(1, steps):
            t = i / steps
            cx, cy = ax + dx * t, ay + dy * t
            half = width * 0.40
            d.line((cx - nx * half, cy - ny * half, cx + nx * half, cy + ny * half), fill=(139, 134, 116, 125), width=2)
        d.line((ax, ay, bx, by), fill=(222, 165, 88, 62), width=2)

    # Production detail is a second cosmetic pass over the same semantic masks.
    detail.apply(im, tx, ty, roads, pts_by_id, connectors)
    return im


def _world_crop(center_x: int, center_y: int, width: int, height: int, cols: int, rows_n: int) -> Image.Image:
    """Stitch a 1:1 screen-sized crop directly from production tiles."""
    world_w, world_h = cols * art.TILE, rows_n * art.TILE
    x0 = max(0, min(world_w - width, int(center_x - width / 2)))
    y0 = max(0, min(world_h - height, int(center_y - height / 2)))
    x1, y1 = x0 + width, y0 + height
    out = Image.new("RGB", (width, height), (3, 4, 5))
    tx0, ty0 = x0 // art.TILE, y0 // art.TILE
    tx1, ty1 = (x1 - 1) // art.TILE, (y1 - 1) // art.TILE
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            tile_path = OUT / f"tile_{tx:02d}_{ty:02d}.png"
            tile = Image.open(tile_path).convert("RGB")
            tile_x0, tile_y0 = tx * art.TILE, ty * art.TILE
            wx0, wy0 = max(x0, tile_x0), max(y0, tile_y0)
            wx1, wy1 = min(x1, tile_x0 + art.TILE), min(y1, tile_y0 + art.TILE)
            src = (wx0 - tile_x0, wy0 - tile_y0, wx1 - tile_x0, wy1 - tile_y0)
            dst = (wx0 - x0, wy0 - y0)
            out.paste(tile.crop(src), dst)
    return out


def build_preview(cols: int, rows_n: int, roads: dict, pts_by_id: dict):
    scale = 0.125
    small = int(art.TILE * scale)
    preview = Image.new("RGB", (cols * small, rows_n * small), (3, 4, 5))
    for ty in range(rows_n):
        for tx in range(cols):
            tile = Image.open(OUT / f"tile_{tx:02d}_{ty:02d}.png").convert("RGB")
            preview.paste(tile.resize((small, small), Image.Resampling.LANCZOS), (tx * small, ty * small))
    preview.save(FULL_PREVIEW, optimize=True)

    all_points = [p for rid in roads for p in pts_by_id.get(rid, [])]
    if all_points:
        pad = 420
        min_x = max(0, int(min(p[0] for p in all_points) - pad))
        min_y = max(0, int(min(p[1] for p in all_points) - pad))
        max_x = min(cols * art.TILE, int(max(p[0] for p in all_points) + pad))
        max_y = min(rows_n * art.TILE, int(max(p[1] for p in all_points) + pad))
        # Crop from the stitched preview using the same production tiles. This
        # is a network-composition review, not a separate concept render.
        crop = preview.crop((int(min_x*scale), int(min_y*scale), int(max_x*scale), int(max_y*scale)))
        if crop.width > 0 and crop.height > 0:
            factor = min(2.5, 1400 / max(crop.width, 1), 900 / max(crop.height, 1))
            focus = crop.resize((max(1, int(crop.width*factor)), max(1, int(crop.height*factor))), Image.Resampling.LANCZOS)
            focus.save(FOCUS_PREVIEW, optimize=True)

    # True screen-sized 1:1 review around Broadway / W 181st and its stair.
    _world_crop(12160, 4672, 1280, 720, cols, rows_n).save(PLAYER_SCALE_PREVIEW, optimize=True)


def main():
    cfg = art.map_cfg()
    cols = math.ceil(int(cfg["world_w"]) / art.TILE)
    rows_n = math.ceil(int(cfg["world_h"]) / art.TILE)
    roads, pts = underground_roads()
    connectors = underground_connectors()
    if not roads:
        raise SystemExit("No walkable level -1 roads are authored")
    if not connectors:
        raise SystemExit("No Ground/Underground connectors are authored")
    OUT.mkdir(parents=True, exist_ok=True)
    for ty in range(rows_n):
        for tx in range(cols):
            paint_tile(tx, ty, roads, pts, connectors).save(OUT / f"tile_{tx:02d}_{ty:02d}.png", optimize=True)
    build_preview(cols, rows_n, roads, pts)
    print(
        f"V100_UNDERGROUND_APPROVAL_OK tiles={cols*rows_n} roads={len(roads)} "
        f"connectors={len(connectors)} level=-1 detail=production_v2 "
        f"preview={FULL_PREVIEW.name} focus={FOCUS_PREVIEW.name} player_scale={PLAYER_SCALE_PREVIEW.name}"
    )


if __name__ == "__main__":
    main()
