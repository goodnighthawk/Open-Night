#!/usr/bin/env python3
"""Generate deterministic v1.0 Ground + Roof layers from city_block.

Current production scope is Ground + Roof only.

Building rules:
- existing building components define buildable envelopes;
- each component is reduced deterministically to its largest filled rectangle;
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

ROOT = Path(__file__).resolve().parents[1]
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
ROOF_PROP_SPECS = (
    ("rooflayer_aircon_large", 164, 164),
    ("rooflayer_water_red", 154, 154),
    ("rooflayer_green_roof", 190, 190),
    ("rooflayer_white_box", 146, 146),
)
ZEBRA_STRIPE_WIDTH = 44
ZEBRA_STRIPE_LENGTH = 176
ZEBRA_STRIPE_GAP = 38
ZEBRA_EDGE_MARGIN = 36


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


def _audit_rect(rows: list[list[str]], rect: tuple[int, int, int, int], theme: str) -> None:
    x0, y0, x1, y1 = rect
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            expected = _tile_for(theme, _role_for_rect_cell(x, y, rect))
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


def _detail_cells(rect: tuple[int, int, int, int], center: tuple[int, int]) -> list[tuple[int, int]]:
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
        if x0 <= x <= x1 and y0 <= y <= y1 and (x, y) != center and (x, y) not in out:
            out.append((x, y))
    return out


def synthesize_ground(data: dict, original: list[list[str]]) -> tuple[list[list[str]], list[dict]]:
    groups = _building_components(original)
    rows = [list(row) for row in original]
    for y, row in enumerate(rows):
        for x, tile_id in enumerate(row):
            if tile_id.startswith("bld_"):
                rows[y][x] = "pavement_small"

    buildings = []
    rejected = []
    for legacy_index, group in enumerate(groups, 1):
        rect = _largest_axis_aligned_rect(group)
        x0, y0, x1, y1 = rect
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        area = bw * bh
        if bw < MIN_BUILDING_SIDE or bh < MIN_BUILDING_SIDE or area < MIN_BUILDING_AREA:
            rejected.append({"legacy_index": legacy_index, "rect": [x0, y0, x1, y1], "area": area})
            continue

        index = len(buildings) + 1
        theme = _theme_for_rect(index, rect)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                rows[y][x] = _tile_for(theme, _role_for_rect_cell(x, y, rect))
        _audit_rect(rows, rect, theme)
        buildings.append({
            "building_id": f"grid_building_{index:02d}",
            "footprint_type": "rectangle",
            "theme": theme,
            "rect": [x0, y0, x1, y1],
            "generated_cells": area,
            "legacy_component_cells": len(group),
            "orientation_policy": "filename_semantics_no_rotation",
        })

    # Retire the old plus-sign/crossing pass before adding the new street grammar.
    data["objects"] = [obj for obj in data.get("objects", []) if not str(obj.get("asset", "")).startswith("mark_")]
    data["layers"] = {"ground": rows}
    data.pop("layers_ascii", None)
    data["building_synthesis"] = {
        "version": 3,
        "shape_family": "axis_aligned_rectangles",
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
    roof_objects: list[dict] = []
    roof_rows = [["void" for _ in row] for row in ground]

    for index, building in enumerate(buildings, 1):
        x0, y0, x1, y1 = map(int, building["rect"])
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        building_id = str(building["building_id"])
        area = (x1 - x0 + 1) * (y1 - y0 + 1)

        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                roof_rows[y][x] = ground[y][x]

        ground_objects.append({
            "asset": "placeholder_street_door", "gx": cx, "gy": y1,
            "width_px": 96, "height_px": 144, "building_id": building_id,
            "edge": "south", "rotation": 0, "placeholder": True,
            "future_transition": "ground_to_first_floor_door",
        })
        ground_objects.append({
            "asset": "placeholder_fire_escape", "gx": x1, "gy": cy,
            "width_px": 128, "height_px": 256, "building_id": building_id,
            "edge": "east", "rotation": 0, "placeholder": True,
            "future_transition": "stationary_jump_ground_to_roof",
        })
        roof_objects.append({
            "asset": "placeholder_roof_hatch", "gx": cx, "gy": cy,
            "width_px": 128, "height_px": 128, "building_id": building_id,
            "rotation": 0, "placeholder": True,
            "future_transition": "second_floor_to_roof",
        })

        detail_cells = _detail_cells((x0, y0, x1, y1), (cx, cy))
        detail_count = min(len(detail_cells), max(2, min(6, 2 + area // 12)))
        for j, (gx, gy) in enumerate(detail_cells[:detail_count]):
            asset, ww, hh = ROOF_PROP_SPECS[(index + j - 1) % len(ROOF_PROP_SPECS)]
            roof_objects.append({
                "asset": asset, "gx": gx, "gy": gy,
                "width_px": ww, "height_px": hh,
                "building_id": building_id,
                "rotation": ((index + j) % 4) * 90,
                "deterministic_roof_detail": True,
            })

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
        "format": "open-night-ground-generated-v4",
        "generation_scope": ["ground", "roof"],
        "building_synthesis": "filename_semantics_no_rotation_minimum_scale",
        "street_markings": "zebra_crossings_and_dashed_center_lines",
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
            "version": 3,
            "matching_ground": True,
            "registration": "exact_ground_footprint",
            "orientation_reference": "assets/source_packs/city_block/example.png",
            "orientation_authority": "filename_semantics",
            "random_rotation": False,
            "minimum_side_cells": MIN_BUILDING_SIDE,
            "minimum_area_cells": MIN_BUILDING_AREA,
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
        "roof_registration=exact_ground_footprint", "scope=ground,roof",
    )


if __name__ == "__main__":
    main()
