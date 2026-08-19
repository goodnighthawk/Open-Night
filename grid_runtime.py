from __future__ import annotations

from collections import deque
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any

from building_morphology import assign_notches, footprint_for, role_for_cell, transition_anchors
from road_morphology import apply_road_morphology

from grid_world import GridWorld, TileCatalog

ROOT = Path(__file__).resolve().parent
GRID_MAP_PATH = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor" / "grid_v100" / "ground_grid.json"
GRID_GENERATED_OBJECTS_PATH = GRID_MAP_PATH.with_name("ground_generated_objects.json")
GRID_ROOF_PATH = GRID_MAP_PATH.with_name("roof_grid.generated.json")
GRID_CATALOG_PATH = ROOT / "assets" / "grid_v100" / "tile_catalog.json"
GRID_MAP_ID = "map_001_gwb_corridor"
THEMES = ("blue", "dark_green", "green", "red", "yellow")
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


def _decode_ground(data: dict) -> list[list[str]]:
    explicit = data.get("layers", {}).get("ground")
    if explicit:
        return [list(row) for row in explicit]
    legend = data.get("tile_legend") or {}
    source = (data.get("layers_ascii") or {}).get("ground") or []
    return [[str(legend[ch]) for ch in str(row)] for row in source]


def _building_components(rows: list[list[str]]) -> list[list[tuple[int, int]]]:
    remaining = {
        (x, y) for y, row in enumerate(rows) for x, tile_id in enumerate(row)
        if tile_id.startswith("bld_")
    }
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
    digest = hashlib.sha256(f"open-night-v100|{index}|{rect}".encode("ascii")).digest()
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


def _synthesize_ground_runtime(data: dict) -> tuple[list[list[str]], list[dict]]:
    """Rebuild the exact shared rectangle/notch grammar in memory."""
    original = _decode_ground(data)
    prior = list((data.get("building_synthesis") or {}).get("buildings") or [])
    envelopes = ([tuple(map(int, building["rect"])) for building in prior]
                 if prior else [_largest_axis_aligned_rect(group) for group in _building_components(original)])
    rows = [list(row) for row in original]
    for y, row in enumerate(rows):
        for x, tile_id in enumerate(row):
            if tile_id.startswith("bld_"):
                rows[y][x] = "pavement_small"

    buildings = []
    for index, rect in enumerate(envelopes, 1):
        theme = _theme_for_rect(index, rect)
        x0, y0, x1, y1 = rect
        buildings.append({
            "building_id": f"grid_building_{index:02d}",
            "theme": theme, "rect": [x0, y0, x1, y1], "notch": None,
            "footprint_type": "rectangle",
            "orientation_policy": "filename_semantics_no_rotation",
        })
    assign_notches(buildings, THEMES)
    for building in buildings:
        rect = tuple(map(int, building["rect"]))
        footprint = footprint_for(rect, building.get("notch"))
        for x, y in footprint:
            rows[y][x] = f"bld_{building['theme']}_{role_for_cell(x, y, footprint)}"
        building["generated_cells"] = len(footprint)
        building["envelope_cells"] = (rect[2] - rect[0] + 1) * (rect[3] - rect[1] + 1)

    rows, road_morphology = apply_road_morphology(rows)
    if any(not rows[y][x].startswith("bld_") for building in buildings
           for x, y in footprint_for(tuple(map(int, building["rect"])), building.get("notch"))):
        raise ValueError("road morphology pass overlapped an authoritative building footprint")

    data["building_synthesis"] = {
        "version": 4,
        "shape_family": "rectangles_and_single_corner_notches",
        "morphology_pass": "building_morphology_v1",
        "notched_building_count": sum(b.get("notch") is not None for b in buildings),
        "removed_building_cell_count": sum(b["envelope_cells"] - b["generated_cells"] for b in buildings),
        "orientation_reference": "assets/source_packs/city_block/example.png",
        "orientation_authority": "filename_semantics",
        "random_rotation": False,
        "roof_registration": "exact_ground_footprint",
        "building_count": len(buildings),
        "buildings": buildings,
        "runtime_synthesized": True,
    }
    data["road_morphology"] = road_morphology
    return rows, buildings


def _detail_cells(
    rect: tuple[int, int, int, int], center: tuple[int, int],
    valid_cells: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    x0, y0, x1, y1 = rect
    cx, cy = center
    candidates = [
        (x0 + 1, y0 + 1), (x1 - 1, y0 + 1),
        (x0 + 1, y1 - 1), (x1 - 1, y1 - 1),
        (cx, y0 + 1), (cx, y1 - 1), (x0 + 1, cy), (x1 - 1, cy),
    ]
    out = []
    for x, y in candidates:
        if (x0 <= x <= x1 and y0 <= y <= y1 and (x, y) != center and (x, y) not in out
                and (valid_cells is None or (x, y) in valid_cells)):
            out.append((x, y))
    if valid_cells is not None:
        out.extend(sorted(
            (x, y) for x, y in valid_cells
            if x0 < x < x1 and y0 < y < y1 and (x, y) != center and (x, y) not in out
        ))
    return out


def _roof_palette(building: dict) -> tuple[str, list[str]]:
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
    return ROOF_ARCHETYPE_NAMES[archetype_index], palette[start:] + palette[:start]


def _generated_ground_objects(rows: list[list[str]], buildings: list[dict]) -> list[dict]:
    objects = []
    for building in buildings:
        x0, y0, x1, y1 = map(int, building["rect"])
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        building_id = str(building["building_id"])
        footprint = footprint_for((x0, y0, x1, y1), building.get("notch"))
        anchors = transition_anchors(building, footprint)
        door_x, door_y = anchors["door"]
        fire_x, fire_y = anchors["fire_escape"]
        objects.extend([
            {
                "asset": "placeholder_street_door", "gx": door_x, "gy": door_y,
                "width_px": 96, "height_px": 144, "building_id": building_id,
                "edge": "south", "rotation": 0, "placeholder": True,
                "future_transition": "ground_to_first_floor_door",
            },
            {
                "asset": "placeholder_fire_escape", "gx": fire_x, "gy": fire_y,
                "width_px": 128, "height_px": 256, "building_id": building_id,
                "edge": "east", "rotation": 0, "placeholder": True,
                "future_transition": "stationary_jump_ground_to_roof",
            },
        ])
    roads = [(x, y) for y, row in enumerate(rows) for x, tid in enumerate(row) if tid == "road_fill"]
    if roads:
        for index in range(4):
            x, y = roads[(index + 1) * len(roads) // 5]
            objects.append({
                "asset": "overlay_man_hole", "gx": x, "gy": y,
                "width_px": 128, "height_px": 128, "rotation": 0,
                "future_transition": "crouch_on_manhole_to_underground",
            })
    return objects


def _fallback_roof_data(ground_data: dict, rows: list[list[str]], buildings: list[dict]) -> dict:
    roof = [[tile_id if tile_id.startswith("bld_") else "void" for tile_id in row] for row in rows]
    roof_objects = []
    for index, building in enumerate(buildings, 1):
        x0, y0, x1, y1 = map(int, building["rect"])
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        building_id = str(building["building_id"])
        footprint = footprint_for((x0, y0, x1, y1), building.get("notch"))
        area = (x1 - x0 + 1) * (y1 - y0 + 1)
        anchors = transition_anchors(building, footprint)
        hatch_x, hatch_y = anchors["hatch"]
        roof_objects.append({
            "asset": "placeholder_roof_hatch", "gx": hatch_x, "gy": hatch_y,
            "width_px": 128, "height_px": 128, "building_id": building_id,
            "rotation": 0, "placeholder": True,
            "future_transition": "second_floor_to_roof",
        })
        candidates = _detail_cells((x0, y0, x1, y1), (hatch_x, hatch_y), footprint)
        detail_count = min(len(candidates), max(2, min(6, 2 + area // 12)))
        roof_archetype, roof_palette = _roof_palette(building)
        for j, (gx, gy) in enumerate(candidates[:detail_count]):
            asset = roof_palette[j]
            ww, hh = ROOF_PROP_DRAW_SIZES[asset]
            rotation = ((index + j) % 4) * 90
            final_w, final_h = (hh, ww) if rotation in {90, 270} else (ww, hh)
            roof_objects.append({
                "asset": asset, "gx": gx, "gy": gy,
                "offset_x_px": (256 - final_w) // 2, "offset_y_px": (256 - final_h) // 2,
                "width_px": ww, "height_px": hh, "building_id": building_id,
                "rotation": rotation, "deterministic_roof_detail": True,
                "composition_pass": "roof_palette_v1", "roof_archetype": roof_archetype,
                "roof_theme": str(building["theme"]), "decorative_only": True,
            })
    return {
        "format": "open-night-grid-v1",
        "authority": "grid",
        "cell_px": ground_data.get("cell_px", 256),
        "width": ground_data.get("width", 64),
        "height": ground_data.get("height", 48),
        "world_w": ground_data.get("world_w", 16384),
        "world_h": ground_data.get("world_h", 12288),
        "source_pack": "city_block",
        "generation_scope": ["ground", "roof"],
        "layers": {"roof": roof},
        "objects": roof_objects,
        "login_spawns": [],
        "fallback_exact_ground_registration": True,
    }


def _assert_exact_roof_registration(ground_rows: list[list[str]], roof_rows: list[list[str]]) -> None:
    if len(ground_rows) != len(roof_rows):
        raise ValueError("Roof/Ground row count mismatch")
    for y, ground_row in enumerate(ground_rows):
        if len(ground_row) != len(roof_rows[y]):
            raise ValueError(f"Roof/Ground width mismatch at row {y}")
        for x, ground_tile in enumerate(ground_row):
            roof_tile = roof_rows[y][x]
            if ground_tile.startswith("bld_"):
                if roof_tile != ground_tile:
                    raise ValueError(f"Roof registration mismatch at {(x, y)}")
            elif roof_tile != "void":
                raise ValueError(f"Roof extends outside Ground footprint at {(x, y)}")


def _load_roof_data(data: dict, rows: list[list[str]], buildings: list[dict]) -> dict:
    if GRID_ROOF_PATH.is_file():
        candidate = json.loads(GRID_ROOF_PATH.read_text(encoding="utf-8"))
        try:
            _assert_exact_roof_registration(rows, candidate["layers"]["roof"])
            return candidate
        except (KeyError, ValueError):
            pass
    return _fallback_roof_data(data, rows, buildings)


@lru_cache(maxsize=1)
def load_ground_grid() -> GridWorld:
    data = json.loads(GRID_MAP_PATH.read_text(encoding="utf-8"))
    ground_rows, buildings = _synthesize_ground_runtime(data)

    if GRID_GENERATED_OBJECTS_PATH.is_file():
        generated = json.loads(GRID_GENERATED_OBJECTS_PATH.read_text(encoding="utf-8"))
        ground_generated = list(generated.get("objects", []))
    else:
        ground_generated = _generated_ground_objects(ground_rows, buildings)
    data.setdefault("objects", []).extend(ground_generated)

    roof_data = _load_roof_data(data, ground_rows, buildings)
    roof_rows = [list(row) for row in roof_data["layers"]["roof"]]
    _assert_exact_roof_registration(ground_rows, roof_rows)

    data["layers"] = {"ground": ground_rows, "roof": roof_rows}
    data.pop("layers_ascii", None)
    roof_objects = list(roof_data.get("objects", []))
    data.setdefault("objects", []).extend(roof_objects)
    data["generation_scope"] = ["ground", "roof"]
    data["external_ground_roof_composite"] = True
    data["external_composite_object_count"] = len(roof_objects)
    data["generated_ground_object_count"] = len(ground_generated)
    data["roof_registration"] = "exact_ground_building_footprint"
    runtime = data.setdefault("runtime", {})
    runtime["external_roofs_visible_on_ground"] = True
    runtime["roof_collision_authority"] = "ground"
    return GridWorld(data, TileCatalog.load(GRID_CATALOG_PATH))


@lru_cache(maxsize=1)
def load_roof_grid() -> GridWorld:
    ground_data = json.loads(GRID_MAP_PATH.read_text(encoding="utf-8"))
    ground_rows, buildings = _synthesize_ground_runtime(ground_data)
    roof_data = _load_roof_data(ground_data, ground_rows, buildings)
    _assert_exact_roof_registration(ground_rows, roof_data["layers"]["roof"])
    return GridWorld(roof_data, TileCatalog.load(GRID_CATALOG_PATH))


def ground_grid_enabled(map_config: dict[str, Any] | None = None) -> bool:
    if not GRID_MAP_PATH.is_file() or not GRID_CATALOG_PATH.is_file():
        return False
    if map_config is None:
        return True
    map_id = str(map_config.get("id", ""))
    return map_id in {GRID_MAP_ID, "001", "map_001", "gwb_corridor"} or "gwb" in map_id.lower()


def grid_network_metadata(map_config: dict[str, Any]) -> dict[str, Any]:
    if not ground_grid_enabled(map_config):
        return {}
    world = load_ground_grid()
    return {
        "grid_runtime": True,
        "grid_format": str(world.data.get("format", "open-night-grid-v1")),
        "grid_cell_px": world.cell_px,
        "grid_width": world.width,
        "grid_height": world.height,
        "world_w": world.world_w,
        "world_h": world.world_h,
        "grid_source_pack": str(world.data.get("source_pack", "city_block")),
        "generated_layers": ["ground", "roof"],
        "blank_layers": ["underground", "first_floor", "second_floor", "hell", "clouds", "hud_space"],
        "legacy_surface_entities": bool(world.data.get("runtime", {}).get("legacy_surface_entities", False)),
        "external_ground_roof_composite": True,
        "roof_registration": "exact_ground_building_footprint",
        "external_composite_object_count": int(world.data.get("external_composite_object_count", 0)),
        "generated_ground_object_count": int(world.data.get("generated_ground_object_count", 0)),
    }
