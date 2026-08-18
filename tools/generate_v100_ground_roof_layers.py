#!/usr/bin/env python3
"""Generate deterministic v1.0 Ground + Roof building layers.

Current production scope is Ground + Roof only.

Building synthesis rules:
- existing building components define the buildable lot envelope;
- each component is reduced deterministically to its largest axis-aligned rectangle;
- one city_block colour family is chosen from a stable hash of that rectangle;
- modular tiles are assigned strictly from filename semantics:
  top_left_outer / top_center / top_right_outer / left / fill / right /
  bottom_left_outer / bottom_center / bottom_right_outer;
- modular building tiles are never rotated or stretched;
- Roof uses the exact same generated footprint as Ground.

``assets/source_packs/city_block/example.png`` is retained as the pack's visual
orientation reference. The generator never guesses orientation from pixels: the
filenames are authoritative, and the example image is a human/audit reference.

Future traversal affordances remain simple deterministic placeholders:
- street door: future Ground -> First Floor;
- fire escape: future stationary Jump near exterior -> Roof;
- roof hatch: future Second Floor -> Roof;
- real city_block manhole: future crouch-on-manhole -> Underground.

All other semantic layers intentionally remain absent/blank for now.
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
BUILDING_ROLE_ORDER = (
    "top_left_outer", "top_center", "top_right_outer",
    "left", "fill", "right",
    "bottom_left_outer", "bottom_center", "bottom_right_outer",
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
    """Largest filled rectangle contained in the existing component.

    Irregular legacy footprints are shrunk rather than expanded into sidewalks or
    roads. Ties resolve top-to-bottom then left-to-right, so output is stable.
    """
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
                            best = candidate
                            best_area = area
    if best is None:
        x, y = min(group, key=lambda p: (p[1], p[0]))
        return x, y, x, y
    return best


def _theme_for_rect(index: int, rect: tuple[int, int, int, int]) -> str:
    payload = f"open-night-v100|{index}|{rect[0]}|{rect[1]}|{rect[2]}|{rect[3]}".encode("ascii")
    digest = hashlib.sha256(payload).digest()
    return THEMES[int.from_bytes(digest[:2], "big") % len(THEMES)]


def _role_for_rect_cell(x: int, y: int, rect: tuple[int, int, int, int]) -> str:
    x0, y0, x1, y1 = rect
    if x0 == x1 or y0 == y1:
        return "fill"
    if y == y0:
        if x == x0:
            return "top_left_outer"
        if x == x1:
            return "top_right_outer"
        return "top_center"
    if y == y1:
        if x == x0:
            return "bottom_left_outer"
        if x == x1:
            return "bottom_right_outer"
        return "bottom_center"
    if x == x0:
        return "left"
    if x == x1:
        return "right"
    return "fill"


def _tile_for(theme: str, role: str) -> str:
    if role not in BUILDING_ROLE_ORDER:
        raise ValueError(f"unsupported modular building role: {role}")
    return f"bld_{theme}_{role}"


def _audit_rect(rows: list[list[str]], rect: tuple[int, int, int, int], theme: str) -> None:
    x0, y0, x1, y1 = rect
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            expected = _tile_for(theme, _role_for_rect_cell(x, y, rect))
            actual = rows[y][x]
            if actual != expected:
                raise RuntimeError(
                    f"building seam/orientation audit failed at {(x, y)}: expected {expected!r}, got {actual!r}"
                )


def _road_cells(rows: list[list[str]]) -> list[tuple[int, int]]:
    return [(x, y) for y, row in enumerate(rows) for x, tid in enumerate(row) if tid == "road_fill"]


def synthesize_ground(data: dict, original: list[list[str]]) -> tuple[list[list[str]], list[dict]]:
    groups = _building_components(original)
    rows = [list(row) for row in original]

    # No legacy/randomly-oriented building tile survives this pass.
    for y, row in enumerate(rows):
        for x, tile_id in enumerate(row):
            if tile_id.startswith("bld_"):
                rows[y][x] = "pavement_small"

    buildings = []
    for index, group in enumerate(groups, 1):
        rect = _largest_axis_aligned_rect(group)
        x0, y0, x1, y1 = rect
        theme = _theme_for_rect(index, rect)
        building_id = f"grid_building_{index:02d}"
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                rows[y][x] = _tile_for(theme, _role_for_rect_cell(x, y, rect))
        _audit_rect(rows, rect, theme)
        buildings.append({
            "building_id": building_id,
            "footprint_type": "rectangle",
            "theme": theme,
            "rect": [x0, y0, x1, y1],
            "generated_cells": (x1 - x0 + 1) * (y1 - y0 + 1),
            "legacy_component_cells": len(group),
            "orientation_policy": "filename_semantics_no_rotation",
        })

    data["layers"] = {"ground": rows}
    data.pop("layers_ascii", None)
    data["building_synthesis"] = {
        "version": 1,
        "shape_family": "axis_aligned_rectangles",
        "orientation_reference": "assets/source_packs/city_block/example.png",
        "orientation_authority": "filename_semantics",
        "random_rotation": False,
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
    original_ground = _decode_ground(data)
    ground, buildings = synthesize_ground(data, original_ground)

    ground_objects = []
    roof_objects = []
    roof_rows = [["void" for _ in row] for row in ground]
    roof_prop_cycle = (
        "rooflayer_aircon_large",
        "rooflayer_water_red",
        "rooflayer_green_roof",
        "rooflayer_white_box",
    )

    for index, building in enumerate(buildings, 1):
        x0, y0, x1, y1 = map(int, building["rect"])
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        building_id = str(building["building_id"])

        # Ground -> Roof registration is copied cell-for-cell; no second orientation decision.
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
        roof_objects.append({
            "asset": roof_prop_cycle[(index - 1) % len(roof_prop_cycle)],
            "gx": max(x0, min(x1, cx - 1)), "gy": max(y0, min(y1, cy - 1)),
            "width_px": 150, "height_px": 150, "building_id": building_id,
            "rotation": 0,
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
        "format": "open-night-ground-generated-v2",
        "generation_scope": ["ground", "roof"],
        "building_synthesis": "filename_semantics_no_rotation",
        "orientation_reference": "assets/source_packs/city_block/example.png",
        "objects": ground_objects,
    }, separators=(",", ":")) + "\n", encoding="utf-8")

    roof_data = {
        "format": "open-night-grid-v1",
        "authority": "grid",
        "cell_px": data["cell_px"],
        "width": data["width"],
        "height": data["height"],
        "world_w": data["world_w"],
        "world_h": data["world_h"],
        "source_pack": "city_block",
        "generation_scope": ["ground", "roof"],
        "building_synthesis": {
            "version": 1,
            "matching_ground": True,
            "orientation_reference": "assets/source_packs/city_block/example.png",
            "orientation_authority": "filename_semantics",
            "random_rotation": False,
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
        f"buildings={buildings}",
        f"generated_objects={objects}",
        "shape=rectangles",
        "orientation=filename_semantics_no_rotation",
        "scope=ground,roof",
    )


if __name__ == "__main__":
    main()
