#!/usr/bin/env python3
"""Production-detail post-pass for collision-locked v1.0 Underground/Night art.

Everything painted here stays inside the already-authored level -1 passage or
connector widths. The pass adds visual identity only; it never creates traversal
geometry.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

import build_v100_art_overlays as art

TILE = art.TILE


def _samples(points, spacing: float, phase: float = 0.0):
    """Sample a polyline at deterministic world-distance intervals."""
    if len(points) < 2 or spacing <= 0:
        return []
    result = []
    distance_to_next = max(0.0, float(phase) % spacing)
    first_segment = True
    for a, b in zip(points, points[1:]):
        ax, ay = map(float, a)
        bx, by = map(float, b)
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            continue
        ux, uy = dx / length, dy / length
        cursor = distance_to_next if first_segment else distance_to_next
        while cursor <= length + 1e-6:
            result.append((ax + ux * cursor, ay + uy * cursor, ux, uy))
            cursor += spacing
        distance_to_next = max(0.0, cursor - length)
        if distance_to_next >= spacing:
            distance_to_next %= spacing
        first_segment = False
    return result


def _oriented_rect(cx: float, cy: float, ux: float, uy: float, along: float, across: float):
    nx, ny = -uy, ux
    ha = along * 0.5
    hc = across * 0.5
    return [
        (cx - ux * ha - nx * hc, cy - uy * ha - ny * hc),
        (cx + ux * ha - nx * hc, cy + uy * ha - ny * hc),
        (cx + ux * ha + nx * hc, cy + uy * ha + ny * hc),
        (cx - ux * ha + nx * hc, cy - uy * ha + ny * hc),
    ]


def _local(points, ox: float, oy: float):
    return [(x - ox, y - oy) for x, y in points]


def _inside_tile(x: float, y: float, pad: float = 80.0):
    return -pad <= x <= TILE + pad and -pad <= y <= TILE + pad


def _draw_corridor_edges(d: ImageDraw.ImageDraw, points, width: float, tx: int, ty: int):
    ox, oy = tx * TILE, ty * TILE
    # Recessed wall/floor seam. Both lines sit inside the authored passage width.
    for sign in (-1, 1):
        off = sign * max(10.0, width * 0.43)
        seam = _local(art.parallel_points(points, off), ox, oy)
        d.line(seam, fill=(5, 8, 9, 220), width=7, joint="curve")
        inner_off = sign * max(8.0, width * 0.39)
        inner = _local(art.parallel_points(points, inner_off), ox, oy)
        d.line(inner, fill=(119, 113, 99, 86), width=2, joint="curve")

    # Central drain gives the passage a readable floor plane at player scale.
    center = _local(points, ox, oy)
    d.line(center, fill=(9, 13, 15, 205), width=7, joint="curve")
    d.line(center, fill=(74, 85, 85, 105), width=2, joint="curve")


def _draw_structural_ribs(d: ImageDraw.ImageDraw, rid: str, points, width: float, tx: int, ty: int):
    ox, oy = tx * TILE, ty * TILE
    phase = float(art.stable_int(rid) % 92)
    for x, y, ux, uy in _samples(points, 132.0, phase):
        lx, ly = x - ox, y - oy
        if not _inside_tile(lx, ly):
            continue
        nx, ny = -uy, ux
        half = width * 0.45
        a = (lx - nx * half, ly - ny * half)
        b = (lx + nx * half, ly + ny * half)
        d.line((a, b), fill=(4, 7, 8, 175), width=5)
        d.line((a, b), fill=(116, 109, 94, 63), width=1)
        # Small side-foot plates keep ribs from reading like lane markings.
        for sign in (-1, 1):
            px = lx + nx * half * sign
            py = ly + ny * half * sign
            plate = _oriented_rect(px, py, ux, uy, 13.0, 9.0)
            d.polygon(plate, fill=(59, 61, 57, 215), outline=(132, 124, 105, 95))


def _draw_conduit_and_clamps(d: ImageDraw.ImageDraw, rid: str, points, width: float, tx: int, ty: int):
    ox, oy = tx * TILE, ty * TILE
    side = -1 if art.stable_int(rid + ":conduit") % 2 else 1
    offset = side * width * 0.31
    conduit_world = art.parallel_points(points, offset)
    conduit = _local(conduit_world, ox, oy)
    d.line(conduit, fill=(8, 11, 12, 210), width=8, joint="curve")
    d.line(conduit, fill=(80, 100, 96, 220), width=3, joint="curve")
    phase = float(art.stable_int(rid + ":clamps") % 54)
    for x, y, ux, uy in _samples(points, 88.0, phase):
        nx, ny = -uy, ux
        x += nx * offset
        y += ny * offset
        lx, ly = x - ox, y - oy
        if not _inside_tile(lx, ly, 24):
            continue
        d.ellipse((lx - 3, ly - 3, lx + 3, ly + 3), fill=(141, 137, 119, 180), outline=(22, 28, 29, 190))


def _draw_cabinets_and_markers(d: ImageDraw.ImageDraw, rid: str, points, width: float, tx: int, ty: int):
    ox, oy = tx * TILE, ty * TILE
    seed = art.stable_int(rid + ":utility")
    phase = float(seed % 230)
    colors = (
        (137, 85, 48, 225),
        (75, 99, 91, 225),
        (92, 74, 67, 225),
    )
    for index, (x, y, ux, uy) in enumerate(_samples(points, 448.0, phase)):
        nx, ny = -uy, ux
        side = -1 if ((seed >> (index % 24)) & 1) else 1
        cx = x + nx * side * width * 0.29
        cy = y + ny * side * width * 0.29
        lx, ly = cx - ox, cy - oy
        if not _inside_tile(lx, ly, 48):
            continue
        cabinet = _oriented_rect(lx, ly, ux, uy, 28.0, 18.0)
        d.polygon(cabinet, fill=(47, 51, 49, 242), outline=(146, 137, 117, 145))
        inset = _oriented_rect(lx, ly, ux, uy, 17.0, 9.0)
        d.polygon(inset, fill=(20, 25, 26, 215), outline=(94, 96, 87, 95))
        # Tiny status lamp; enough to read at 1:1 without becoming neon clutter.
        sx = lx + ux * 7.0
        sy = ly + uy * 7.0
        d.ellipse((sx - 2, sy - 2, sx + 2, sy + 2), fill=colors[index % len(colors)])


def _draw_puddles_and_grime(d: ImageDraw.ImageDraw, rid: str, points, width: float, tx: int, ty: int):
    ox, oy = tx * TILE, ty * TILE
    seed = art.stable_int(rid + ":grime")
    phase = float(seed % 170)
    for index, (x, y, ux, uy) in enumerate(_samples(points, 392.0, phase)):
        nx, ny = -uy, ux
        lateral = (((seed >> ((index * 5) % 40)) & 15) / 15.0 - 0.5) * width * 0.28
        cx = x + nx * lateral
        cy = y + ny * lateral
        lx, ly = cx - ox, cy - oy
        if not _inside_tile(lx, ly, 56):
            continue
        along = 25.0 + float((seed >> ((index * 7 + 3) % 44)) & 15)
        across = 9.0 + float((seed >> ((index * 3 + 9) % 44)) & 7)
        puddle = _oriented_rect(lx, ly, ux, uy, along, across)
        d.polygon(puddle, fill=(34, 58, 63, 62), outline=(91, 114, 113, 52))
        # Dirt/water edge broken into a darker offset patch.
        grime = _oriented_rect(lx - nx * 2.0, ly - ny * 2.0, ux, uy, along * 0.62, across * 0.55)
        d.polygon(grime, fill=(17, 25, 25, 72))


def _draw_corridor_identity(d: ImageDraw.ImageDraw, rid: str, points, width: float, tx: int, ty: int):
    ox, oy = tx * TILE, ty * TILE
    if rid == "ug_181_crosspassage":
        # Tiled pedestrian/service cross-passage: restrained perpendicular joints.
        for x, y, ux, uy in _samples(points, 62.0, 18.0):
            lx, ly = x - ox, y - oy
            if not _inside_tile(lx, ly, 48):
                continue
            nx, ny = -uy, ux
            half = width * 0.27
            d.line((lx - nx * half, ly - ny * half, lx + nx * half, ly + ny * half), fill=(127, 123, 110, 34), width=1)
    elif rid == "ug_broadway_spine":
        # Broadway spine: paired maintenance channels distinguish it from the
        # cross-passage without implying additional collision lanes.
        for sign in (-1, 1):
            channel = _local(art.parallel_points(points, sign * 13.0), ox, oy)
            d.line(channel, fill=(13, 18, 19, 165), width=4, joint="curve")
            d.line(channel, fill=(94, 105, 100, 64), width=1, joint="curve")
    elif rid == "ug_gwb_service_branch":
        # Service branch: occasional muted hazard bars stay inside the floor.
        for x, y, ux, uy in _samples(points, 256.0, 44.0):
            lx, ly = x - ox, y - oy
            if not _inside_tile(lx, ly, 48):
                continue
            nx, ny = -uy, ux
            half = width * 0.23
            d.line((lx - nx * half, ly - ny * half, lx + nx * half, ly + ny * half), fill=(165, 119, 61, 70), width=3)


def _draw_stair_landings(d: ImageDraw.ImageDraw, connectors: list[dict], tx: int, ty: int):
    ox, oy = tx * TILE, ty * TILE
    for row in connectors:
        try:
            ex, ey = float(row["x1"]), float(row["y1"])
            sx, sy = float(row["x0"]), float(row["y0"])
            width = max(32.0, float(row.get("width", 64) or 64))
        except (KeyError, TypeError, ValueError):
            continue
        lx, ly = ex - ox, ey - oy
        if not _inside_tile(lx, ly, 64):
            continue
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        # Landing remains inside the connector/corridor envelope.
        landing = _oriented_rect(lx, ly, ux, uy, width * 0.66, width * 0.66)
        d.polygon(landing, fill=(52, 53, 48, 210), outline=(176, 148, 94, 150))
        inner = _oriented_rect(lx, ly, ux, uy, width * 0.42, width * 0.42)
        d.polygon(inner, outline=(9, 13, 14, 195))
        # Directional amber bars read as a stair landing, not another corridor.
        nx, ny = -uy, ux
        for offset in (-10.0, 0.0, 10.0):
            cx, cy = lx + ux * offset, ly + uy * offset
            half = width * 0.18
            d.line((cx - nx * half, cy - ny * half, cx + nx * half, cy + ny * half), fill=(219, 160, 80, 92), width=2)


def apply(im: Image.Image, tx: int, ty: int, roads: dict, pts_by_id: dict, connectors: list[dict]) -> Image.Image:
    """Add authored-mask-safe Underground production detail to one tile."""
    d = ImageDraw.Draw(im, "RGBA")
    for rid, row in roads.items():
        points = pts_by_id.get(rid, [])
        if len(points) < 2 or not art.intersects_tile(points, tx, ty, pad=120):
            continue
        width = max(48.0, float(row.get("width", 80) or 80))
        _draw_corridor_edges(d, points, width, tx, ty)
        _draw_structural_ribs(d, rid, points, width, tx, ty)
        _draw_conduit_and_clamps(d, rid, points, width, tx, ty)
        _draw_cabinets_and_markers(d, rid, points, width, tx, ty)
        _draw_puddles_and_grime(d, rid, points, width, tx, ty)
        _draw_corridor_identity(d, rid, points, width, tx, ty)
    _draw_stair_landings(d, connectors, tx, ty)
    return im
