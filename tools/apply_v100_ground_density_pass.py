#!/usr/bin/env python3
"""Deterministically increase authored Ground detail without changing collision cells.

This pass is intentionally object-only: it keeps every authoritative ASCII tile
unchanged, then adds curated road wear and rooftop detail anchored to valid road
or building cells. It is safe to rerun and records its version in runtime metadata.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor" / "grid_v100" / "ground_grid.json"
PASS_VERSION = 1

ROAD_DETAILS = [
    ("overlay_man_hole", 150, 150, 0),
    ("overlay_pot_hole", 130, 145, 90),
    ("overlay_road_cracks", 120, 190, 180),
    ("overlay_oil_splash", 155, 135, 270),
    ("overlay_road_puddle", 135, 185, 0),
    ("overlay_curb_drain", 120, 140, 90),
]

ROOF_DETAILS = [
    ("roof_aircon_unit_large", 165, 165, 0),
    ("roof_duct_02", 145, 205, 90),
    ("roof_red_water_but", 165, 165, 180),
    ("roof_pipe_work_04", 150, 205, 270),
    ("roof_green_roof", 165, 165, 0),
    ("roof_window", 145, 190, 90),
    ("roof_white_box_01", 160, 160, 180),
    ("roof_brown_water_but", 165, 165, 270),
]

BUILDING_CODES = set("ABCDEFGHIJKLMONPQSTUVWXYZabcdefghijklmnopqrst")


def key(item: dict) -> tuple:
    return (
        str(item.get("asset", "")),
        int(item.get("gx", -1)),
        int(item.get("gy", -1)),
        int(item.get("width_px", 0)),
        int(item.get("height_px", 0)),
        int(float(item.get("rotation", 0))),
    )


def main() -> None:
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    assert data.get("authority") == "grid"
    assert data.get("cell_px") == 256
    assert data.get("width") == 64 and data.get("height") == 48

    rows = data["layers_ascii"]["ground"]
    assert len(rows) == 48 and all(len(row) == 64 for row in rows)

    objects = list(data.get("objects", []))
    existing = {key(item) for item in objects}

    # Road wear: distribute across the city, but avoid intersection-heavy cells
    # by requiring a 3x3 road neighborhood. This keeps crossings legible.
    road_candidates: list[tuple[int, int]] = []
    for gy in range(1, 47):
        for gx in range(1, 63):
            if rows[gy][gx] != "R":
                continue
            horizontal = rows[gy][gx - 1] == "R" and rows[gy][gx + 1] == "R"
            vertical = rows[gy - 1][gx] == "R" and rows[gy + 1][gx] == "R"
            if horizontal ^ vertical:
                road_candidates.append((gx, gy))

    for idx, (gx, gy) in enumerate(road_candidates):
        # Sparse deterministic sampling: enough texture to break repetition without noise.
        if (gx * 17 + gy * 29 + idx) % 11 != 0:
            continue
        asset, width, height, rotation = ROAD_DETAILS[(gx + gy + idx) % len(ROAD_DETAILS)]
        item = {
            "asset": asset,
            "gx": gx,
            "gy": gy,
            "width_px": width,
            "height_px": height,
            "rotation": rotation,
        }
        if key(item) not in existing:
            objects.append(item)
            existing.add(key(item))

    # Rooftop detail: use only interior/fill-like building cells where possible,
    # then sample deterministically to avoid decorating every roof tile.
    preferred_fill_codes = set("DMWfo")
    roof_candidates: list[tuple[int, int]] = []
    for gy, row in enumerate(rows):
        for gx, ch in enumerate(row):
            if ch in preferred_fill_codes:
                roof_candidates.append((gx, gy))

    # Small buildings may have no fill cell; add a limited secondary candidate set.
    if len(roof_candidates) < 24:
        for gy, row in enumerate(rows):
            for gx, ch in enumerate(row):
                if ch in BUILDING_CODES:
                    roof_candidates.append((gx, gy))

    for idx, (gx, gy) in enumerate(roof_candidates):
        if (gx * 31 + gy * 13 + idx) % 7 != 0:
            continue
        asset, width, height, rotation = ROOF_DETAILS[(gx * 3 + gy + idx) % len(ROOF_DETAILS)]
        item = {
            "asset": asset,
            "gx": gx,
            "gy": gy,
            "width_px": width,
            "height_px": height,
            "rotation": rotation,
        }
        if key(item) not in existing:
            objects.append(item)
            existing.add(key(item))

    # Add a few extra awnings to street-facing building edges. These are cosmetic
    # and leave the collision-authoritative cells untouched.
    awnings = [
        ("roof_awning_blue", 17, 29, 420, 110),
        ("roof_awning_green", 34, 18, 420, 110),
        ("roof_awning_red", 48, 46, 420, 110),
        ("roof_awning_yellow", 2, 46, 420, 110),
        ("roof_awning_blue", 34, 46, 420, 110),
    ]
    for asset, gx, gy, width, height in awnings:
        item = {"asset": asset, "gx": gx, "gy": gy, "width_px": width, "height_px": height}
        if key(item) not in existing:
            objects.append(item)
            existing.add(key(item))

    data["objects"] = objects
    data["map_goal"] = "approved_city_block_dense_irregular_night"
    runtime = data.setdefault("runtime", {})
    runtime["ground_visual_density_pass"] = PASS_VERSION
    runtime["collision_cells_unchanged_by_density_pass"] = True

    MAP_PATH.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Ground density pass v{PASS_VERSION}: {len(objects)} total objects")


if __name__ == "__main__":
    main()
