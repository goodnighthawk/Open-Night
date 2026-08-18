#!/usr/bin/env python3
"""Generate the current v1.0 Ground + Roof layer support files.

Only Ground and Roof are generated in this phase. Future traversal affordances are
kept as simple deterministic placeholders so later interior/underground work does
not require changing the map grammar:
- street door: future Ground -> First Floor
- fire escape: future stationary Jump near exterior -> Roof
- roof hatch: future Second Floor -> Roof
- real city_block manhole: future crouch-on-manhole -> Underground

The other semantic layers intentionally remain absent/blank for now.
"""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor" / "grid_v100"
GROUND_PATH = MAP_DIR / "ground_grid.json"
GROUND_GENERATED = MAP_DIR / "ground_generated_objects.json"
ROOF_PATH = MAP_DIR / "roof_grid.generated.json"
PLACEHOLDER_DIR = ROOT / "assets" / "grid_v100" / "placeholders"

MAGENTA = (255, 0, 255)


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


def _road_cells(rows: list[list[str]]) -> list[tuple[int, int]]:
    return [(x, y) for y, row in enumerate(rows) for x, tid in enumerate(row) if tid == "road_fill"]


def generate_layers() -> tuple[int, int]:
    data = json.loads(GROUND_PATH.read_text(encoding="utf-8"))
    ground = _decode_ground(data)
    groups = _building_components(ground)

    ground_objects = []
    roof_objects = []
    roof_rows = [["void" for _ in row] for row in ground]
    roof_prop_cycle = [
        "rooflayer_aircon_large",
        "rooflayer_water_red",
        "rooflayer_green_roof",
        "rooflayer_white_box",
    ]

    for index, group in enumerate(groups, 1):
        xs = [x for x, _ in group]
        ys = [y for _, y in group]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        building_id = f"grid_building_{index:02d}"
        for x, y in group:
            roof_rows[y][x] = ground[y][x]

        ground_objects.append({
            "asset": "placeholder_street_door", "gx": cx, "gy": y1,
            "width_px": 96, "height_px": 144, "building_id": building_id,
            "placeholder": True, "future_transition": "ground_to_first_floor_door",
        })
        ground_objects.append({
            "asset": "placeholder_fire_escape", "gx": x1, "gy": cy,
            "width_px": 128, "height_px": 256, "building_id": building_id,
            "placeholder": True, "future_transition": "stationary_jump_ground_to_roof",
        })
        roof_objects.append({
            "asset": "placeholder_roof_hatch", "gx": cx, "gy": cy,
            "width_px": 128, "height_px": 128, "building_id": building_id,
            "placeholder": True, "future_transition": "second_floor_to_roof",
        })
        roof_objects.append({
            "asset": roof_prop_cycle[(index - 1) % len(roof_prop_cycle)],
            "gx": max(x0, min(x1, cx - 1)), "gy": max(y0, min(y1, cy - 1)),
            "width_px": 150, "height_px": 150, "building_id": building_id,
        })

    # Keep actual city_block manholes in the Ground grammar now even though the
    # Underground layer itself is intentionally blank in this phase.
    roads = _road_cells(ground)
    if roads:
        for index in range(4):
            x, y = roads[(index + 1) * len(roads) // 5]
            ground_objects.append({
                "asset": "overlay_man_hole", "gx": x, "gy": y,
                "width_px": 128, "height_px": 128,
                "future_transition": "crouch_on_manhole_to_underground",
            })

    GROUND_GENERATED.write_text(json.dumps({
        "format": "open-night-ground-generated-v1",
        "generation_scope": ["ground", "roof"],
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
        "layers": {"roof": roof_rows},
        "objects": roof_objects,
        "login_spawns": [],
    }
    ROOF_PATH.write_text(json.dumps(roof_data, separators=(",", ":")) + "\n", encoding="utf-8")
    return len(groups), len(ground_objects) + len(roof_objects)


def main() -> None:
    generate_placeholder_images()
    buildings, objects = generate_layers()
    print(f"V100_GROUND_ROOF_GENERATED buildings={buildings} generated_objects={objects} scope=ground,roof")


if __name__ == "__main__":
    main()
