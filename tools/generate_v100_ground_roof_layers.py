#!/usr/bin/env python3
"""Generate deterministic v1.0 Ground + Roof layers from city_block.

Current production scope is Ground + Roof only.

Building rules:
- existing building components define buildable envelopes;
- stable component envelopes receive deterministic single-corner notches;
- city_block modular tiles are selected only from filename semantics;
- modular building tiles are never rotated or stretched;
- Roof copies the exact generated Ground building footprint cell-for-cell;
- Roof detail is deterministic and remains inside the registered footprint.

assets/source_packs/city_block/example.png remains the visual orientation reference.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from building_morphology import (
    NOTCH_CORNERS, NOTCH_DEPTH_CELLS, assign_notches,
    footprint_for as _footprint_for, role_for_cell as _role_for_footprint_cell,
    transition_anchors,
)

MAP_DIR = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor" / "grid_v100"
GROUND_PATH = MAP_DIR / "ground_grid.json"
GROUND_GENERATED = MAP_DIR / "ground_generated_objects.json"
ROOF_PATH = MAP_DIR / "roof_grid.generated.json"
PLACEHOLDER_DIR = ROOT / "assets" / "grid_v100" / "placeholders"
CITY_BLOCK_DIR = ROOT / "assets" / "source_packs" / "city_block"
ORIENTATION_REFERENCE = CITY_BLOCK_DIR / "example.png"

MAGENTA = (255, 0, 255)
THEMES = ("blue", "dark_green", "green", "red", "yellow")
MIN_BUILDING_SIDE = 4
MIN_BUILDING_AREA = 24
ROOF_PROP_DRAW_SIZES = {
    "rooflayer_aircon": (190, 101), "rooflayer_aircon_large": (160, 165),
    "rooflayer_blue_roof": (190, 135), "rooflayer_green_roof": (180, 181),
    "rooflayer_grey_roof": (180, 181), "rooflayer_orange_roof": (188, 150),
    "rooflayer_water_brown": (154, 154), "rooflayer_water_green": (154, 154),
    "rooflayer_water_red": (154, 154), "rooflayer_open_pipe_top": (100, 115),
    "rooflayer_pipe": (100, 100), "rooflayer_pipe_work_02": (52, 198),
    "rooflayer_pipe_work_04": (190, 145), "rooflayer_white_box": (158, 150),
    "rooflayer_white_box_02": (130, 170), "rooflayer_white_box_03": (97, 124),
}
ROOF_ARCHETYPE_NAMES = ("mechanical", "waterworks", "mixed_service", "low_profile")
ROOF_SURFACE_EFFECT_QUOTAS = {"blue": 1, "dark_green": 4, "green": 2, "red": 2, "yellow": 3}
ZEBRA_STRIPE_WIDTH = 44
ZEBRA_STRIPE_LENGTH = 176
ZEBRA_STRIPE_GAP = 38
ZEBRA_EDGE_MARGIN = 36
ROAD_WEAR_TARGET = 36
CURB_DETAIL_TARGET = 24
STREET_EDGE_AWNING_TARGET = 18
STREET_LAMP_MIN_SEGMENT = 5
ROAD_WEAR_SPECS = (
    ("overlay_road_puddle", 116, 202),
    ("overlay_oil_splash", 130, 108),
    ("overlay_pot_hole", 112, 130),
    ("overlay_road_cracks", 94, 190),
    ("overlay_curb_drain", 80, 116),
)
AWNING_ASSETS = (
    "roof_awning_blue", "roof_awning_green", "roof_awning_red", "roof_awning_yellow",
)
ROOF_EDGE_MASS_SPECS = (
    ("rooflayer_duct_02", 76, 200),
    ("rooflayer_pipe_work_01", 44, 200),
    ("rooflayer_pipe_work_03", 148, 160),
    ("rooflayer_window", 117, 160),
)


def _write_ppm(path: Path, width: int, height: int, pixel_fn) -> None:
    lines = ["P3", f"{width} {height}", "255"]
    for y in range(height):
        row = []
        for x in range(width):
            r, g, b = pixel_fn(x, y)
            row.append(f"{r} {g} {b}")
        lines.append(" ".join(row))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def generate_placeholder_images() -> None:
    def door(x: int, y: int):
        if 2 <= x <= 13 and 2 <= y <= 23:
            if x in (2, 13) or y == 2:
                return (48, 36, 32)
            if 4 <= x <= 11 and 4 <= y <= 23:
                if (x, y) == (10, 13):
                    return (236, 202, 82)
                return (148, 76, 46) if ((x - 4) // 4) % 2 == 0 else (116, 58, 38)
        return MAGENTA

    def fire_escape(x: int, y: int):
        if x in (3, 16) and 2 <= y <= 30:
            return (52, 58, 64)
        if y in (5, 14, 23, 30) and 3 <= x <= 16:
            return (76, 82, 88)
        if 5 <= y <= 14:
            xx = 4 + int((y - 5) * 12 / 9)
            if abs(x - xx) <= 1:
                return (130, 136, 142)
        if 14 <= y <= 23:
            xx = 16 - int((y - 14) * 12 / 9)
            if abs(x - xx) <= 1:
                return (130, 136, 142)
        if 23 <= y <= 30:
            xx = 4 + int((y - 23) * 12 / 7)
            if abs(x - xx) <= 1:
                return (130, 136, 142)
        return MAGENTA

    def hatch(x: int, y: int):
        if 2 <= x <= 21 and 2 <= y <= 21:
            if x in (2, 21) or y in (2, 21):
                return (42, 48, 54)
            if x in (5, 18) or y in (5, 18):
                return (112, 118, 124)
            if 8 <= x <= 15 and 8 <= y <= 15:
                return (184, 190, 196) if y % 3 == 0 else (72, 78, 84)
            return (64, 70, 76)
        return MAGENTA

    _write_ppm(PLACEHOLDER_DIR / "street_door.ppm", 16, 24, door)
    _write_ppm(PLACEHOLDER_DIR / "fire_escape.ppm", 20, 32, fire_escape)
    _write_ppm(PLACEHOLDER_DIR / "roof_hatch.ppm", 24, 24, hatch)


def _decode_ground(data: dict) -> list[list[str]]:
    if data.get("layers", {}).get("ground"):
        return [list(row) for row in data["layers"]["ground"]]
    legend = data["tile_legend"]
    return [[legend[ch] for ch in row] for row in data["layers_ascii"]["ground"]]


def _building_components(rows: list[list[str]]) -> list[list[tuple[int, int]]]:
    h, w = len(rows), len(rows[0])
    remaining = {(x, y) for y in range(h) for x in range(w) if rows[y][x].startswith("bld_")}
    groups = []
    while remaining:
        seed = remaining.pop()
        q = deque([seed])
        group = [seed]
        while q:
            x, y = q.popleft()
            for n in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if n in remaining:
                    remaining.remove(n)
                    q.append(n)
                    group.append(n)
        groups.append(group)
    groups.sort(key=lambda g: (min(y for _, y in g), min(x for x, _ in g)))
    return groups


def _largest_axis_aligned_rect(group: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    cells = set(group)
    xs = [x for x, _ in group]
    ys = [y for _, y in group]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    best = None
    best_area = -1
    for y0 in range(min_y, max_y + 1):
        for y1 in range(y0, max_y + 1):
            for x0 in range(min_x, max_x + 1):
                for x1 in range(x0, max_x + 1):
                    area = (x1 - x0 + 1) * (y1 - y0 + 1)
                    if area < best_area:
                        continue
                    if all((x, y) in cells for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)):
                        candidate = (x0, y0, x1, y1)
                        if area > best_area or best is None or candidate < best:
                            best, best_area = candidate, area
    if best is None:
        x, y = min(group, key=lambda p: (p[1], p[0]))
        return x, y, x, y
    return best


def _theme_for_rect(index: int, rect: tuple[int, int, int, int]) -> str:
    payload = f"open-night-v100|{index}|{rect}".encode("ascii")
    digest = hashlib.sha256(payload).digest()
    return THEMES[int.from_bytes(digest[:2], "big") % len(THEMES)]


def _role_for_rect_cell(x: int, y: int, rect: tuple[int, int, int, int]) -> str:
    x0, y0, x1, y1 = rect
    if x0 == x1 or y0 == y1:
        return "fill"
    if y == y0:
        return "top_left_outer" if x == x0 else "top_right_outer" if x == x1 else "top_center"
    if y == y1:
        return "bottom_left_outer" if x == x0 else "bottom_right_outer" if x == x1 else "bottom_center"
    if x == x0:
        return "left"
    if x == x1:
        return "right"
    return "fill"


def _tile_for(theme: str, role: str) -> str:
    return f"bld_{theme}_{role}"


def _audit_footprint(rows: list[list[str]], cells: set[tuple[int, int]], theme: str) -> None:
    for x, y in cells:
        expected = _tile_for(theme, _role_for_footprint_cell(x, y, cells))
        if rows[y][x] != expected:
            raise RuntimeError(f"building seam/orientation audit failed at {(x, y)}")


def _road_cells(rows: list[list[str]]) -> list[tuple[int, int]]:
    return [(x, y) for y, row in enumerate(rows) for x, tid in enumerate(row) if tid == "road_fill"]


def _contiguous_bands(values: list[int]) -> list[tuple[int, int]]:
    if not values:
        return []
    bands = []
    start = prev = values[0]
    for value in values[1:]:
        if value != prev + 1:
            bands.append((start, prev))
            start = value
        prev = value
    bands.append((start, prev))
    return bands


def _road_bands(rows: list[list[str]]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    h, w = len(rows), len(rows[0])
    vertical_cols = [x for x in range(w) if sum(rows[y][x] == "road_fill" for y in range(h)) >= int(h * 0.75)]
    horizontal_rows = [y for y in range(h) if sum(rows[y][x] == "road_fill" for x in range(w)) >= int(w * 0.75)]
    return _contiguous_bands(vertical_cols), _contiguous_bands(horizontal_rows)


def _street_markings(rows: list[list[str]]) -> list[dict]:
    h, w = len(rows), len(rows[0])
    vertical, horizontal = _road_bands(rows)
    objects: list[dict] = []

    def in_h_intersection(y: int) -> bool:
        return any(y0 - 1 <= y <= y1 + 1 for y0, y1 in horizontal)

    def in_v_intersection(x: int) -> bool:
        return any(x0 - 1 <= x <= x1 + 1 for x0, x1 in vertical)

    # Repeating dashed centre lines between intersections.
    for x0, x1 in vertical:
        cx = (x0 + x1) // 2
        for y in range(1, h - 1, 2):
            if in_h_intersection(y):
                continue
            objects.append({
                "asset": "mark_yellow_repeating_single", "gx": cx, "gy": y,
                "width_px": 64, "height_px": 190, "rotation": 0,
                "street_marking": "dashed_center_line_vertical",
            })

    for y0, y1 in horizontal:
        cy = (y0 + y1) // 2
        for x in range(1, w - 1, 2):
            if in_v_intersection(x):
                continue
            objects.append({
                "asset": "mark_yellow_repeating_single", "gx": x, "gy": cy,
                "width_px": 64, "height_px": 190, "rotation": 90,
                "street_marking": "dashed_center_line_horizontal",
            })

    def stripe_offsets(span_px: int) -> list[int]:
        """Return centered stripe starts across a road-width span."""
        usable = max(0, span_px - 2 * ZEBRA_EDGE_MARGIN)
        pitch = ZEBRA_STRIPE_WIDTH + ZEBRA_STRIPE_GAP
        count = max(3, (usable + ZEBRA_STRIPE_GAP) // pitch)
        occupied = count * ZEBRA_STRIPE_WIDTH + (count - 1) * ZEBRA_STRIPE_GAP
        start = max(ZEBRA_EDGE_MARGIN, (span_px - occupied) // 2)
        return [start + index * pitch for index in range(count)]

    def add_vertical_zebra(gx: int, gy: int, span_px: int, name: str) -> None:
        # The user-approved grammar keeps each white bar parallel to the road.
        # On a north/south road that means vertical bars repeated east/west.
        for stripe_index, offset in enumerate(stripe_offsets(span_px)):
            objects.append({
                "asset": "mark_white_crossing_piece", "gx": gx, "gy": gy,
                "offset_x_px": offset, "offset_y_px": 40,
                "width_px": ZEBRA_STRIPE_WIDTH, "height_px": ZEBRA_STRIPE_LENGTH,
                "rotation": 0, "street_marking": name,
                "zebra_stripe_index": stripe_index,
            })

    def add_horizontal_zebra(gx: int, gy: int, span_px: int, name: str) -> None:
        # On an east/west road the same source stripe is rotated once and
        # repeated north/south, so every bar stays parallel to the lane lines.
        for stripe_index, offset in enumerate(stripe_offsets(span_px)):
            objects.append({
                "asset": "mark_white_crossing_piece", "gx": gx, "gy": gy,
                "offset_x_px": 40, "offset_y_px": offset,
                "width_px": ZEBRA_STRIPE_WIDTH, "height_px": ZEBRA_STRIPE_LENGTH,
                "rotation": 90, "street_marking": name,
                "zebra_stripe_index": stripe_index,
            })

    # Proper repeated zebra stripes on each of the four approaches. Each
    # crossing stays inside its road band and within one approach cell of the
    # intersection, rather than stretching a single sprite into a giant bar.
    for vx0, vx1 in vertical:
        for hy0, hy1 in horizontal:
            road_w = (vx1 - vx0 + 1) * 256
            road_h = (hy1 - hy0 + 1) * 256
            if hy0 - 1 >= 0:
                add_vertical_zebra(vx0, hy0 - 1, road_w, "zebra_north")
            if hy1 + 1 < h:
                add_vertical_zebra(vx0, hy1 + 1, road_w, "zebra_south")
            if vx0 - 1 >= 0:
                add_horizontal_zebra(vx0 - 1, hy0, road_h, "zebra_west")
            if vx1 + 1 < w:
                add_horizontal_zebra(vx1 + 1, hy0, road_h, "zebra_east")

    zebras = [obj for obj in objects if str(obj.get("street_marking", "")).startswith("zebra_")]
    if not zebras or any(int(obj["width_px"]) >= int(obj["height_px"]) for obj in zebras):
        raise RuntimeError("zebra audit failed: expected repeated narrow source stripes")
    if any(abs(int(obj.get("offset_x_px", 0))) >= 768 or abs(int(obj.get("offset_y_px", 0))) >= 768 for obj in zebras):
        raise RuntimeError("zebra audit failed: stripe offset escaped its road band")
    return objects


def _detail_cells(
    rect: tuple[int, int, int, int], center: tuple[int, int],
    valid_cells: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    x0, y0, x1, y1 = rect
    cx, cy = center
    candidates = [
        (x0 + 1, y0 + 1), (x1 - 1, y0 + 1),
        (x0 + 1, y1 - 1), (x1 - 1, y1 - 1),
        (cx, y0 + 1), (cx, y1 - 1),
        (x0 + 1, cy), (x1 - 1, cy),
    ]
    out = []
    for x, y in candidates:
        if (x0 <= x <= x1 and y0 <= y <= y1 and (x, y) != center and (x, y) not in out
                and (valid_cells is None or (x, y) in valid_cells)):
            out.append((x, y))
    if valid_cells is not None:
        extras = sorted(
            (x, y) for x, y in valid_cells
            if x0 < x < x1 and y0 < y < y1 and (x, y) != center and (x, y) not in out
        )
        out.extend(extras)
    return out


def _roof_palette(building: dict) -> tuple[str, list[str]]:
    """Return one coherent, deterministic six-piece equipment family."""
    building_id = str(building["building_id"])
    theme = str(building["theme"])
    digest = hashlib.sha256(
        f"open-night-roof-palette-v1|{building_id}|{theme}".encode("ascii")
    ).digest()
    theme_cap = {
        "blue": "rooflayer_blue_roof", "dark_green": "rooflayer_green_roof",
        "green": "rooflayer_green_roof", "red": "rooflayer_orange_roof",
        "yellow": "rooflayer_orange_roof",
    }[theme]
    theme_tank = {
        "blue": "rooflayer_water_brown", "dark_green": "rooflayer_water_green",
        "green": "rooflayer_water_green", "red": "rooflayer_water_red",
        "yellow": "rooflayer_water_brown",
    }[theme]
    archetypes = (
        ["rooflayer_aircon_large", "rooflayer_aircon", "rooflayer_pipe_work_04",
         "rooflayer_white_box_02", "rooflayer_white_box_03", "rooflayer_pipe"],
        [theme_tank, "rooflayer_open_pipe_top", "rooflayer_pipe", "rooflayer_pipe_work_02",
         "rooflayer_white_box_02", "rooflayer_aircon"],
        [theme_cap, "rooflayer_aircon", theme_tank, "rooflayer_white_box",
         "rooflayer_pipe_work_04", "rooflayer_open_pipe_top"],
        [theme_cap, "rooflayer_grey_roof", "rooflayer_white_box", "rooflayer_white_box_02",
         "rooflayer_white_box_03", "rooflayer_pipe"],
    )
    archetype_index = int.from_bytes(digest[:2], "big") % len(archetypes)
    palette = list(archetypes[archetype_index])
    start = digest[2] % len(palette)
    palette = palette[start:] + palette[:start]
    return ROOF_ARCHETYPE_NAMES[archetype_index], palette


def _roof_surface_effect_objects(
    rows: list[list[str]], buildings: list[dict], roof_objects: list[dict]
) -> list[dict]:
    """Add sparse native-aspect theme seams without wallpaper repetition."""
    reserved = {
        (str(obj.get("building_id")), int(obj["gx"]), int(obj["gy"]))
        for obj in roof_objects if obj.get("building_id")
    }
    chosen: list[dict] = []
    for theme in THEMES:
        themed = [building for building in buildings if str(building["theme"]) == theme]
        themed.sort(key=lambda building: hashlib.sha256(
            f"open-night-roof-surface-v1|building|{building['building_id']}|{theme}".encode("ascii")
        ).digest())
        quota = ROOF_SURFACE_EFFECT_QUOTAS[theme]
        if len(themed) < quota:
            raise RuntimeError(f"roof surface effect quota exceeds {theme} building count")
        for building in themed[:quota]:
            building_id = str(building["building_id"])
            x0, y0, x1, y1 = map(int, building["rect"])
            footprint = _footprint_for((x0, y0, x1, y1), building.get("notch"))
            digest = hashlib.sha256(
                f"open-night-roof-surface-v1|rotation|{building_id}".encode("ascii")
            ).digest()
            rotation = 90 if digest[0] & 1 else 0
            final_w, final_h = (442, 308) if rotation == 90 else (308, 442)
            offset_x, offset_y = (256 - final_w) // 2, (256 - final_h) // 2
            def contained(gx: int, gy: int) -> bool:
                left, top = gx * 256 + offset_x, gy * 256 + offset_y
                covered = {
                    (x, y)
                    for y in range(top // 256, (top + final_h - 1) // 256 + 1)
                    for x in range(left // 256, (left + final_w - 1) // 256 + 1)
                }
                return covered <= footprint
            candidates = [
                (gx, gy) for gy in range(y0 + 1, y1) for gx in range(x0 + 1, x1)
                if rows[gy][gx] == f"bld_{theme}_fill"
                and (building_id, gx, gy) not in reserved
                and contained(gx, gy)
            ]
            candidates.sort(key=lambda cell: hashlib.sha256(
                f"open-night-roof-surface-v1|cell|{building_id}|{cell[0]}|{cell[1]}".encode("ascii")
            ).digest())
            if not candidates:
                raise RuntimeError(f"roof surface effect has no unreserved interior cell for {building_id}")
            gx, gy = candidates[0]
            chosen.append({
                "asset": f"rooflayer_effect_{theme}", "gx": gx, "gy": gy,
                "offset_x_px": offset_x, "offset_y_px": offset_y,
                "width_px": 308, "height_px": 442, "rotation": rotation,
                "building_id": building_id, "roof_theme": theme,
                "composition_pass": "roof_surface_v1", "surface_kind": "theme_seam_overlay",
                "decorative_only": True,
            })
    if len(chosen) != sum(ROOF_SURFACE_EFFECT_QUOTAS.values()):
        raise RuntimeError("roof surface effect audit produced the wrong total quota")
    if len({obj["building_id"] for obj in chosen}) != len(chosen):
        raise RuntimeError("roof surface effect audit duplicated a building")
    return chosen


def _stable_density_rank(kind: str, gx: int, gy: int) -> bytes:
    return hashlib.sha256(f"open-night-ground-density-v2|{kind}|{gx}|{gy}".encode("ascii")).digest()


def _street_lighting_objects(rows: list[list[str]], reserved_objects: list[dict]) -> list[dict]:
    """Place one nonblocking lamp per usable straight curb segment.

    A single object record owns the fixture and emitter.  The renderer derives
    both world transforms from that record, so light and lamp cannot drift apart.
    """
    h, w = len(rows), len(rows[0])
    vertical, horizontal = _road_bands(rows)
    reserved = {(int(obj["gx"]), int(obj["gy"])) for obj in reserved_objects}
    curb_ids = {"curb_left", "curb_right", "curb_top", "curb_bottom"}

    def near_band(value: int, bands: list[tuple[int, int]]) -> bool:
        return any(start - 2 <= value <= end + 2 for start, end in bands)

    candidates: set[tuple[int, int]] = set()
    for gy, row in enumerate(rows):
        for gx, tile_id in enumerate(row):
            if tile_id not in curb_ids or gx in {0, w - 1} or gy in {0, h - 1}:
                continue
            if tile_id in {"curb_left", "curb_right"} and near_band(gy, horizontal):
                continue
            if tile_id in {"curb_top", "curb_bottom"} and near_band(gx, vertical):
                continue
            road_neighbors = sum(
                rows[gy + dy][gx + dx] == "road_fill"
                for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0))
            )
            if road_neighbors == 1:
                candidates.add((gx, gy))

    segments: list[list[tuple[int, int]]] = []
    seen: set[tuple[int, int]] = set()
    for start in sorted(candidates, key=lambda cell: (cell[1], cell[0])):
        if start in seen:
            continue
        gx, gy = start
        tile_id = rows[gy][gx]
        axis = (0, 1) if tile_id in {"curb_left", "curb_right"} else (1, 0)
        segment: list[tuple[int, int]] = []
        stack = [start]
        seen.add(start)
        while stack:
            cell = stack.pop()
            segment.append(cell)
            for sign in (-1, 1):
                nxt = (cell[0] + axis[0] * sign, cell[1] + axis[1] * sign)
                if nxt in candidates and nxt not in seen and rows[nxt[1]][nxt[0]] == tile_id:
                    seen.add(nxt)
                    stack.append(nxt)
        segment.sort(key=lambda cell: (cell[1], cell[0]))
        if len(segment) >= STREET_LAMP_MIN_SEGMENT:
            segments.append(segment)

    direction_rotation = {"north": 0, "east": 90, "south": 180, "west": 270}
    # Exact bulb/head pixel after the corresponding 128x128 sprite rotation.
    light_offsets = {0: (93, 48), 90: (79, 93), 180: (34, 79), 270: (48, 34)}
    objects: list[dict] = []
    for segment_index, segment in enumerate(segments, 1):
        midpoint = (len(segment) - 1) / 2.0
        choices = sorted(
            (cell for cell in segment if cell not in reserved),
            key=lambda cell: (
                abs(segment.index(cell) - midpoint),
                _stable_density_rank("street-lamp", cell[0], cell[1]),
            ),
        )
        if not choices:
            raise RuntimeError("street lighting segment has no unreserved curb anchor")
        gx, gy = choices[0]
        road_direction = next(
            name for dx, dy, name in ((0, -1, "north"), (1, 0, "east"), (0, 1, "south"), (-1, 0, "west"))
            if rows[gy + dy][gx + dx] == "road_fill"
        )
        rotation = direction_rotation[road_direction]
        light_x, light_y = light_offsets[rotation]
        objects.append({
            "asset": "street_lamp_10_night", "gx": gx, "gy": gy,
            "offset_x_px": 64, "offset_y_px": 64,
            "width_px": 128, "height_px": 128, "rotation": rotation,
            "curb_tile": rows[gy][gx], "road_direction": road_direction,
            "composition_pass": "street_lighting_v1", "lighting_kind": "sidewalk_lamp",
            "lighting_id": f"grid_lamp_{segment_index:02d}",
            "decorative_only": True, "emits_light": True,
            "light_offset_x_px": light_x, "light_offset_y_px": light_y,
            "light_radius_px": 280, "light_color_rgb": [255, 188, 92],
            "light_intensity": 0.28,
        })

    if not objects or len(objects) != len(segments):
        raise RuntimeError("street lighting audit did not place one lamp per eligible curb segment")
    if len({(obj["gx"], obj["gy"]) for obj in objects}) != len(objects):
        raise RuntimeError("street lighting audit found duplicate fixture anchors")
    if {obj["road_direction"] for obj in objects} != set(direction_rotation):
        raise RuntimeError("street lighting audit did not cover all four curb orientations")
    if any((obj["gx"], obj["gy"]) in reserved for obj in objects):
        raise RuntimeError("street lighting audit overlapped an existing street object")
    return objects


def _stable_silhouette_rank(kind: str, building_id: str, edge: str, gx: int, gy: int) -> bytes:
    key = f"open-night-building-silhouette-v1|{kind}|{building_id}|{edge}|{gx}|{gy}"
    return hashlib.sha256(key.encode("ascii")).digest()


def _building_silhouette_objects(
    rows: list[list[str]], buildings: list[dict], ground_objects: list[dict], roof_objects: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Add collision-neutral facade rhythm and Roof edge relief."""
    h, w = len(rows), len(rows[0])
    existing_awnings = {
        str(obj.get("building_id")) for obj in ground_objects
        if obj.get("density_kind") == "street_edge_awning"
    }
    reserved_ground = {
        (str(obj.get("building_id")), int(obj["gx"]), int(obj["gy"]))
        for obj in ground_objects if obj.get("building_id")
    }
    reserved_roof = {
        (str(obj.get("building_id")), int(obj["gx"]), int(obj["gy"]))
        for obj in roof_objects if obj.get("building_id")
    }
    edge_vectors = {
        "north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0),
    }
    ground_added: list[dict] = []
    roof_added: list[dict] = []

    for index, building in enumerate(buildings):
        building_id = str(building["building_id"])
        x0, y0, x1, y1 = map(int, building["rect"])
        footprint = _footprint_for((x0, y0, x1, y1), building.get("notch"))
        perimeter: list[tuple[str, int, int]] = [
            (edge, gx, gy)
            for gx, gy in sorted(footprint, key=lambda cell: (cell[1], cell[0]))
            for edge, (dx, dy) in edge_vectors.items()
            if (gx + dx, gy + dy) not in footprint
        ]

        roof_candidates = [
            item for item in perimeter
            if (building_id, item[1], item[2]) not in reserved_roof
            and rows[item[2]][item[1]].startswith("bld_")
        ]
        roof_candidates.sort(key=lambda item: _stable_silhouette_rank("roof-edge", building_id, *item))
        if not roof_candidates:
            raise RuntimeError(f"building silhouette has no Roof edge candidate for {building_id}")
        edge, gx, gy = roof_candidates[0]
        asset, natural_w, natural_h = ROOF_EDGE_MASS_SPECS[index % len(ROOF_EDGE_MASS_SPECS)]
        rotation = {"north": 90, "east": 0, "south": 270, "west": 180}[edge]
        final_w, final_h = (natural_h, natural_w) if rotation in {90, 270} else (natural_w, natural_h)
        roof_added.append({
            "asset": asset, "gx": gx, "gy": gy,
            "offset_x_px": (256 - final_w) // 2, "offset_y_px": (256 - final_h) // 2,
            "width_px": natural_w, "height_px": natural_h, "rotation": rotation,
            "building_id": building_id, "edge": edge,
            "composition_pass": "building_silhouette_v1", "silhouette_kind": "roof_edge_mass",
            "decorative_only": True,
        })

        if building_id in existing_awnings:
            continue
        facade_candidates: list[tuple[str, int, int]] = []
        for candidate_edge, candidate_x, candidate_y in perimeter:
            if not rows[candidate_y][candidate_x].startswith("bld_"):
                continue
            dx, dy = edge_vectors[candidate_edge]
            outside_x, outside_y = candidate_x + dx, candidate_y + dy
            if not (0 <= outside_x < w and 0 <= outside_y < h):
                continue
            outside = rows[outside_y][outside_x]
            if not (outside.startswith("pavement") or outside.startswith("curb_")):
                continue
            if (building_id, candidate_x, candidate_y) in reserved_ground:
                continue
            facade_candidates.append((candidate_edge, candidate_x, candidate_y))
        facade_candidates.sort(key=lambda item: _stable_silhouette_rank("facade", building_id, *item))
        if not facade_candidates:
            raise RuntimeError(f"building silhouette has no walkable facade candidate for {building_id}")
        edge, gx, gy = facade_candidates[0]
        rotation = {"north": 180, "east": 270, "south": 0, "west": 90}[edge]
        offset_x, offset_y = {
            "north": (16, 8), "east": (159, 16), "south": (16, 159), "west": (8, 16),
        }[edge]
        ground_added.append({
            "asset": AWNING_ASSETS[len(ground_added) % len(AWNING_ASSETS)],
            "gx": gx, "gy": gy, "offset_x_px": offset_x, "offset_y_px": offset_y,
            "width_px": 224, "height_px": 89, "rotation": rotation,
            "building_id": building_id, "edge": edge,
            "composition_pass": "building_silhouette_v1", "silhouette_kind": "facade_break",
            "decorative_only": True,
        })

    if len(roof_added) != len(buildings):
        raise RuntimeError("building silhouette audit expected one Roof edge mass per building")
    if len(ground_added) != len(buildings) - len(existing_awnings):
        raise RuntimeError("building silhouette audit expected one facade break on every untreated building")
    if len({obj["building_id"] for obj in roof_added}) != len(buildings):
        raise RuntimeError("building silhouette audit duplicated a Roof building")
    if any(max(int(obj["width_px"]), int(obj["height_px"])) > 200 for obj in roof_added):
        raise RuntimeError("building silhouette Roof mass escaped its one-cell containment contract")
    return ground_added, roof_added


def _ground_density_objects(
    rows: list[list[str]], buildings: list[dict], street_objects: list[dict]
) -> list[dict]:
    """Add collision-neutral wet-road wear and street-edge awnings.

    Selection is hash-ranked and count-bounded, never random. Road wear stays on
    straight ``road_fill`` cells outside marking/intersection reservations;
    awnings stay on the south perimeter of a building with a walkable frontage.
    No tile or collision value is modified by this composition pass.
    """
    h, w = len(rows), len(rows[0])
    vertical, horizontal = _road_bands(rows)
    marked = {
        (int(obj["gx"]), int(obj["gy"]))
        for obj in street_objects
        if obj.get("street_marking")
    }

    def in_band(value: int, bands: list[tuple[int, int]], margin: int = 0) -> bool:
        return any(start - margin <= value <= end + margin for start, end in bands)

    road_candidates: list[tuple[int, int, str]] = []
    for gy, row in enumerate(rows):
        for gx, tile_id in enumerate(row):
            if tile_id != "road_fill" or (gx, gy) in marked:
                continue
            vertical_straight = in_band(gx, vertical) and not in_band(gy, horizontal, 1)
            horizontal_straight = in_band(gy, horizontal) and not in_band(gx, vertical, 1)
            if vertical_straight ^ horizontal_straight:
                road_candidates.append((gx, gy, "vertical" if vertical_straight else "horizontal"))

    road_candidates.sort(key=lambda item: _stable_density_rank("road", item[0], item[1]))
    selected_roads: list[tuple[int, int, str]] = []
    for candidate in road_candidates:
        gx, gy, _axis = candidate
        if any(abs(gx - x) + abs(gy - y) < 3 for x, y, _ in selected_roads):
            continue
        selected_roads.append(candidate)
        if len(selected_roads) == min(ROAD_WEAR_TARGET, len(road_candidates)):
            break
    if len(selected_roads) < ROAD_WEAR_TARGET:
        for candidate in road_candidates:
            if candidate not in selected_roads:
                selected_roads.append(candidate)
            if len(selected_roads) == min(ROAD_WEAR_TARGET, len(road_candidates)):
                break

    objects: list[dict] = []
    for index, (gx, gy, axis) in enumerate(selected_roads):
        asset, width_px, height_px = ROAD_WEAR_SPECS[index % len(ROAD_WEAR_SPECS)]
        digest = _stable_density_rank(asset, gx, gy)
        rotation = 180 if digest[0] & 1 else 0
        objects.append({
            "asset": asset, "gx": gx, "gy": gy,
            "offset_x_px": (256 - width_px) // 2 + int(digest[1] % 25) - 12,
            "offset_y_px": (256 - height_px) // 2 + int(digest[2] % 25) - 12,
            "width_px": width_px, "height_px": height_px,
            "rotation": rotation, "road_axis": axis,
            "composition_pass": "ground_density_v2", "density_kind": "road_wear",
        })

    curb_candidates: list[tuple[int, int, str]] = []
    curb_ids = {"curb_left", "curb_right", "curb_top", "curb_bottom"}
    for gy, row in enumerate(rows):
        for gx, tile_id in enumerate(row):
            if tile_id not in curb_ids:
                continue
            if tile_id in {"curb_left", "curb_right"} and in_band(gy, horizontal, 2):
                continue
            if tile_id in {"curb_top", "curb_bottom"} and in_band(gx, vertical, 2):
                continue
            curb_candidates.append((gx, gy, tile_id))
    curb_candidates.sort(key=lambda item: _stable_density_rank("curb", item[0], item[1]))
    for gx, gy, tile_id in curb_candidates[:CURB_DETAIL_TARGET]:
        rotation = 90 if tile_id in {"curb_top", "curb_bottom"} else 0
        if tile_id in {"curb_right", "curb_bottom"}:
            rotation += 180
        objects.append({
            "asset": "overlay_curb_drain", "gx": gx, "gy": gy,
            "offset_x_px": 88, "offset_y_px": 70,
            "width_px": 80, "height_px": 116, "rotation": rotation,
            "curb_tile": tile_id,
            "composition_pass": "ground_density_v2", "density_kind": "curb_detail",
        })

    frontage_candidates: list[tuple[bytes, dict, int]] = []
    for building in buildings:
        x0, y0, x1, y1 = map(int, building["rect"])
        rect = (x0, y0, x1, y1)
        cx = (x0 + x1) // 2
        if y1 + 1 >= h:
            continue
        frontage = rows[y1 + 1][cx]
        if not (frontage.startswith("pavement") or frontage.startswith("curb_")):
            continue
        edge_cells = [
            x for x in range(x0 + 1, x1)
            if x != cx and rows[y1][x].startswith("bld_")
        ]
        if not edge_cells:
            continue
        edge_cells.sort(key=lambda x: _stable_density_rank("awning-cell", x, y1))
        frontage_candidates.append((_stable_density_rank("awning", cx, y1), building, edge_cells[0]))
    frontage_candidates.sort(key=lambda item: item[0])

    for index, (digest, building, awning_x) in enumerate(frontage_candidates[:STREET_EDGE_AWNING_TARGET]):
        _x0, _y0, _x1, y1 = map(int, building["rect"])
        asset = AWNING_ASSETS[index % len(AWNING_ASSETS)]
        objects.append({
            "asset": asset, "gx": awning_x, "gy": y1,
            "offset_x_px": 16, "offset_y_px": 159,
            "width_px": 224, "height_px": 89, "rotation": 0,
            "building_id": str(building["building_id"]), "edge": "south",
            "composition_pass": "ground_density_v2", "density_kind": "street_edge_awning",
        })

    road_wear = [obj for obj in objects if obj["density_kind"] == "road_wear"]
    curb_details = [obj for obj in objects if obj["density_kind"] == "curb_detail"]
    awnings = [obj for obj in objects if obj["density_kind"] == "street_edge_awning"]
    if len(road_wear) != ROAD_WEAR_TARGET:
        raise RuntimeError(f"ground density audit expected {ROAD_WEAR_TARGET} road-wear objects, got {len(road_wear)}")
    if len(awnings) != min(STREET_EDGE_AWNING_TARGET, len(frontage_candidates)):
        raise RuntimeError("ground density audit produced an unexpected awning count")
    if len(curb_details) != min(CURB_DETAIL_TARGET, len(curb_candidates)):
        raise RuntimeError("ground density audit produced an unexpected curb-detail count")
    if any(rows[int(obj["gy"])][int(obj["gx"])] != "road_fill" for obj in road_wear):
        raise RuntimeError("ground density audit found road wear outside road collision cells")
    if any((int(obj["gx"]), int(obj["gy"])) in marked for obj in road_wear):
        raise RuntimeError("ground density audit found road wear on a reserved street marking")
    if any(rows[int(obj["gy"])][int(obj["gx"])] not in curb_ids for obj in curb_details):
        raise RuntimeError("ground density audit found a curb detail outside curb semantics")
    if any(not rows[int(obj["gy"])][int(obj["gx"])].startswith("bld_") for obj in awnings):
        raise RuntimeError("ground density audit found an awning outside a building perimeter")
    return objects


def synthesize_ground(data: dict, original: list[list[str]]) -> tuple[list[list[str]], list[dict]]:
    prior_buildings = list((data.get("building_synthesis") or {}).get("buildings") or [])
    if prior_buildings:
        envelopes = [tuple(map(int, building["rect"])) for building in prior_buildings]
    else:
        envelopes = [_largest_axis_aligned_rect(group) for group in _building_components(original)]
    rows = [list(row) for row in original]
    for y, row in enumerate(rows):
        for x, tile_id in enumerate(row):
            if tile_id.startswith("bld_"):
                rows[y][x] = "pavement_small"

    buildings = []
    rejected = []
    accepted: list[tuple[int, tuple[int, int, int, int], int]] = []
    for legacy_index, rect in enumerate(envelopes, 1):
        x0, y0, x1, y1 = rect
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        area = bw * bh
        if bw < MIN_BUILDING_SIDE or bh < MIN_BUILDING_SIDE or area < MIN_BUILDING_AREA:
            rejected.append({"legacy_index": legacy_index, "rect": [x0, y0, x1, y1], "area": area})
            continue

        accepted.append((legacy_index, rect, area))

    for _legacy_index, rect, area in accepted:
        x0, y0, x1, y1 = rect
        index = len(buildings) + 1
        theme = _theme_for_rect(index, rect)
        buildings.append({
            "building_id": f"grid_building_{index:02d}", "footprint_type": "rectangle",
            "theme": theme, "rect": [x0, y0, x1, y1], "notch": None,
            "generated_cells": area, "envelope_cells": area,
            "orientation_policy": "filename_semantics_no_rotation",
        })
    assign_notches(buildings, THEMES)

    for building in buildings:
        x0, y0, x1, y1 = map(int, building["rect"])
        rect = (x0, y0, x1, y1)
        theme = str(building["theme"])
        notch = building.get("notch")
        footprint = _footprint_for(rect, notch)
        for x, y in footprint:
            rows[y][x] = _tile_for(theme, _role_for_footprint_cell(x, y, footprint))
        _audit_footprint(rows, footprint, theme)
        building["generated_cells"] = len(footprint)

    # Retire the old plus-sign/crossing pass before adding the new street grammar.
    data["objects"] = [obj for obj in data.get("objects", []) if not str(obj.get("asset", "")).startswith("mark_")]
    data["layers"] = {"ground": rows}
    data.pop("layers_ascii", None)
    data["building_synthesis"] = {
        "version": 4,
        "shape_family": "rectangles_and_single_corner_notches",
        "morphology_pass": "building_morphology_v1",
        "notched_building_count": sum(b.get("notch") is not None for b in buildings),
        "removed_building_cell_count": sum(int(b["envelope_cells"]) - int(b["generated_cells"]) for b in buildings),
        "notch_depth_cells": NOTCH_DEPTH_CELLS,
        "orientation_reference": "assets/source_packs/city_block/example.png",
        "orientation_authority": "filename_semantics",
        "random_rotation": False,
        "roof_registration": "exact_ground_footprint",
        "minimum_side_cells": MIN_BUILDING_SIDE,
        "minimum_area_cells": MIN_BUILDING_AREA,
        "rejected_small_building_count": len(rejected),
        "building_count": len(buildings),
        "buildings": buildings,
    }
    data.setdefault("source_pack", "city_block.zip")
    GROUND_PATH.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    return rows, buildings


def generate_layers() -> tuple[int, int]:
    if not ORIENTATION_REFERENCE.is_file():
        raise FileNotFoundError(f"city_block orientation reference missing: {ORIENTATION_REFERENCE}")

    data = json.loads(GROUND_PATH.read_text(encoding="utf-8"))
    ground, buildings = synthesize_ground(data, _decode_ground(data))
    ground_objects: list[dict] = _street_markings(ground)
    geometry_before_density = hashlib.sha256(
        json.dumps(ground, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    density_objects = _ground_density_objects(ground, buildings, ground_objects)
    density_repeat = _ground_density_objects(ground, buildings, ground_objects)
    if json.dumps(density_objects, sort_keys=True) != json.dumps(density_repeat, sort_keys=True):
        raise RuntimeError("ground density audit is not deterministic across repeated generation")
    geometry_after_density = hashlib.sha256(
        json.dumps(ground, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if geometry_after_density != geometry_before_density:
        raise RuntimeError("ground density pass mutated authoritative grid geometry")
    ground_objects.extend(density_objects)
    lighting_objects = _street_lighting_objects(ground, ground_objects)
    lighting_repeat = _street_lighting_objects(ground, ground_objects)
    if json.dumps(lighting_objects, sort_keys=True) != json.dumps(lighting_repeat, sort_keys=True):
        raise RuntimeError("street lighting audit is not deterministic across repeated generation")
    ground_objects.extend(lighting_objects)
    roof_objects: list[dict] = []
    roof_rows = [["void" for _ in row] for row in ground]

    for index, building in enumerate(buildings, 1):
        x0, y0, x1, y1 = map(int, building["rect"])
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        building_id = str(building["building_id"])
        footprint = _footprint_for((x0, y0, x1, y1), building.get("notch"))
        area = (x1 - x0 + 1) * (y1 - y0 + 1)
        anchors = transition_anchors(building, footprint)
        door_x, door_y = anchors["door"]
        fire_x, fire_y = anchors["fire_escape"]
        hatch_x, hatch_y = anchors["hatch"]

        for x, y in footprint:
            roof_rows[y][x] = ground[y][x]

        ground_objects.append({
            "asset": "placeholder_street_door", "gx": door_x, "gy": door_y,
            "width_px": 96, "height_px": 144, "building_id": building_id,
            "edge": "south", "rotation": 0, "placeholder": True,
            "future_transition": "ground_to_first_floor_door",
        })
        ground_objects.append({
            "asset": "placeholder_fire_escape", "gx": fire_x, "gy": fire_y,
            "width_px": 128, "height_px": 256, "building_id": building_id,
            "edge": "east", "rotation": 0, "placeholder": True,
            "future_transition": "stationary_jump_ground_to_roof",
        })
        roof_objects.append({
            "asset": "placeholder_roof_hatch", "gx": hatch_x, "gy": hatch_y,
            "width_px": 128, "height_px": 128, "building_id": building_id,
            "rotation": 0, "placeholder": True,
            "future_transition": "second_floor_to_roof",
        })

        detail_cells = _detail_cells((x0, y0, x1, y1), (hatch_x, hatch_y), footprint)
        detail_count = min(len(detail_cells), max(2, min(6, 2 + area // 12)))
        roof_archetype, roof_palette = _roof_palette(building)
        for j, (gx, gy) in enumerate(detail_cells[:detail_count]):
            asset = roof_palette[j]
            ww, hh = ROOF_PROP_DRAW_SIZES[asset]
            rotation = ((index + j) % 4) * 90
            final_w, final_h = (hh, ww) if rotation in {90, 270} else (ww, hh)
            roof_objects.append({
                "asset": asset, "gx": gx, "gy": gy,
                "offset_x_px": (256 - final_w) // 2, "offset_y_px": (256 - final_h) // 2,
                "width_px": ww, "height_px": hh,
                "building_id": building_id,
                "rotation": rotation, "deterministic_roof_detail": True,
                "composition_pass": "roof_palette_v1", "roof_archetype": roof_archetype,
                "roof_theme": str(building["theme"]), "decorative_only": True,
            })

    silhouette_ground, silhouette_roof = _building_silhouette_objects(
        ground, buildings, ground_objects, roof_objects
    )
    silhouette_repeat = _building_silhouette_objects(ground, buildings, ground_objects, roof_objects)
    if json.dumps((silhouette_ground, silhouette_roof), sort_keys=True) != json.dumps(silhouette_repeat, sort_keys=True):
        raise RuntimeError("building silhouette audit is not deterministic across repeated generation")
    ground_objects.extend(silhouette_ground)
    roof_objects.extend(silhouette_roof)
    surface_effects = _roof_surface_effect_objects(ground, buildings, roof_objects)
    surface_repeat = _roof_surface_effect_objects(ground, buildings, roof_objects)
    if json.dumps(surface_effects, sort_keys=True) != json.dumps(surface_repeat, sort_keys=True):
        raise RuntimeError("roof surface effect audit is not deterministic across repeated generation")
    roof_objects.extend(surface_effects)

    roads = _road_cells(ground)
    if roads:
        for index in range(4):
            x, y = roads[(index + 1) * len(roads) // 5]
            ground_objects.append({
                "asset": "overlay_man_hole", "gx": x, "gy": y,
                "width_px": 128, "height_px": 128, "rotation": 0,
                "future_transition": "crouch_on_manhole_to_underground",
            })

    GROUND_GENERATED.write_text(json.dumps({
        "format": "open-night-ground-generated-v9",
        "generation_scope": ["ground", "roof"],
        "building_synthesis": "filename_semantics_no_rotation_minimum_scale",
        "building_morphology": {
            "composition_pass": "building_morphology_v1",
            "notched_building_count": sum(b.get("footprint_type") == "corner_notched" for b in buildings),
            "notch_depth_cells": NOTCH_DEPTH_CELLS,
            "corner_distribution": {
                corner: sum((b.get("notch") or {}).get("corner") == corner for b in buildings)
                for corner in NOTCH_CORNERS
            },
        },
        "street_markings": "zebra_crossings_and_dashed_center_lines",
        "composition_pass": "ground_density_v2",
        "density_summary": {
            "road_wear": sum(obj.get("density_kind") == "road_wear" for obj in density_objects),
            "curb_detail": sum(obj.get("density_kind") == "curb_detail" for obj in density_objects),
            "street_edge_awnings": sum(obj.get("density_kind") == "street_edge_awning" for obj in density_objects),
            "geometry_sha256_before": geometry_before_density,
            "geometry_sha256_after": geometry_after_density,
        },
        "street_lighting": {
            "composition_pass": "street_lighting_v1",
            "fixture_and_emitter_authority": "same_grid_object_record",
            "lamp_count": len(lighting_objects),
            "eligible_curb_segment_min_cells": STREET_LAMP_MIN_SEGMENT,
            "geometry_sha256_before": geometry_before_density,
            "geometry_sha256_after": geometry_after_density,
        },
        "building_silhouette": {
            "composition_pass": "building_silhouette_v1",
            "geometry_policy": "collision_neutral_overlay",
            "facade_break_count": len(silhouette_ground),
            "roof_edge_mass_count": len(silhouette_roof),
            "ground_geometry_sha256": geometry_after_density,
        },
        "roof_palette": {
            "composition_pass": "roof_palette_v1",
            "archetypes": list(ROOF_ARCHETYPE_NAMES),
            "registered_asset_family_count": len(ROOF_PROP_DRAW_SIZES),
        },
        "roof_surface": {
            "composition_pass": "roof_surface_v1",
            "native_asset_size_px": [308, 442],
            "effect_count": len(surface_effects),
            "theme_quotas": ROOF_SURFACE_EFFECT_QUOTAS,
        },
        "roof_registration": "exact_ground_footprint",
        "orientation_reference": "assets/source_packs/city_block/example.png",
        "objects": ground_objects,
    }, separators=(",", ":")) + "\n", encoding="utf-8")

    roof_data = {
        "format": "open-night-grid-v1",
        "authority": "grid",
        "cell_px": data["cell_px"], "width": data["width"], "height": data["height"],
        "world_w": data["world_w"], "world_h": data["world_h"],
        "source_pack": "city_block",
        "generation_scope": ["ground", "roof"],
        "building_synthesis": {
            "version": 4,
            "matching_ground": True,
            "registration": "exact_ground_footprint",
            "shape_family": "rectangles_with_corner_notches",
            "notched_building_count": sum(b.get("footprint_type") == "corner_notched" for b in buildings),
            "orientation_reference": "assets/source_packs/city_block/example.png",
            "orientation_authority": "filename_semantics",
            "random_rotation": False,
            "minimum_side_cells": MIN_BUILDING_SIDE,
            "minimum_area_cells": MIN_BUILDING_AREA,
        },
        "building_silhouette": {
            "composition_pass": "building_silhouette_v1",
            "geometry_policy": "collision_neutral_overlay",
            "roof_edge_mass_count": len(silhouette_roof),
        },
        "roof_palette": {
            "composition_pass": "roof_palette_v1",
            "archetypes": list(ROOF_ARCHETYPE_NAMES),
            "detail_count": sum(obj.get("composition_pass") == "roof_palette_v1" for obj in roof_objects),
        },
        "roof_surface": {
            "composition_pass": "roof_surface_v1",
            "effect_count": len(surface_effects),
            "theme_quotas": ROOF_SURFACE_EFFECT_QUOTAS,
        },
        "layers": {"roof": roof_rows},
        "objects": roof_objects,
        "login_spawns": [],
    }
    ROOF_PATH.write_text(json.dumps(roof_data, separators=(",", ":")) + "\n", encoding="utf-8")
    return len(buildings), len(ground_objects) + len(roof_objects)


def main() -> None:
    generate_placeholder_images()
    buildings, objects = generate_layers()
    print(
        "V100_GROUND_ROOF_GENERATED",
        f"buildings={buildings}", f"generated_objects={objects}",
        f"min_building_side={MIN_BUILDING_SIDE}", f"min_building_area={MIN_BUILDING_AREA}",
        "street_markings=zebra+dashed", "orientation=filename_semantics_no_rotation",
        f"density_v2={ROAD_WEAR_TARGET}road+{CURB_DETAIL_TARGET}curb+{STREET_EDGE_AWNING_TARGET}awnings",
        "lighting=one-lamp-per-usable-curb-segment,same-record-emitter",
        f"silhouette_v1={buildings - STREET_EDGE_AWNING_TARGET}facade+{buildings}roof-edge",
        f"roof_palette_v1={len(ROOF_PROP_DRAW_SIZES)}families+{len(ROOF_ARCHETYPE_NAMES)}archetypes",
        f"roof_surface_v1={sum(ROOF_SURFACE_EFFECT_QUOTAS.values())}native-effects",
        f"morphology_v1={sum(b.get('footprint_type') == 'corner_notched' for b in json.loads(GROUND_PATH.read_text())['building_synthesis']['buildings'])}notched",
        "roof_registration=exact_ground_footprint", "scope=ground,roof",
    )


if __name__ == "__main__":
    main()
