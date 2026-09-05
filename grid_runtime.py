from __future__ import annotations

from collections import deque
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any

from building_morphology import (
    assign_notches, footprint_connected, footprint_for, role_for_cell,
    transition_anchors,
)
from road_morphology import apply_road_morphology
from procedural_block_props import build_procedural_block_props

from grid_world import GridWorld, TileCatalog

ROOT = Path(__file__).resolve().parent
GRID_MAP_PATH = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor" / "grid_v100" / "ground_grid.json"
GRID_GENERATED_OBJECTS_PATH = GRID_MAP_PATH.with_name("ground_generated_objects.json")
GRID_ROOF_PATH = GRID_MAP_PATH.with_name("roof_grid.generated.json")
GRID_CATALOG_PATH = ROOT / "assets" / "grid_v100" / "tile_catalog.json"
GRID_GENERATED_ART_OBJECTS_PATH = ROOT / "assets" / "grid_v100" / "generated_art_objects.json"
GRID_MAP_ID = "map_001_gwb_corridor"
THEMES = ("blue", "dark_green", "green", "red", "yellow")
ROOF_PROP_DRAW_SIZES = {
    "rooflayer_aircon": (190, 103), "rooflayer_aircon_large": (160, 167),
    "rooflayer_blue_roof": (180, 177), "rooflayer_green_roof": (180, 179),
    "rooflayer_grey_roof": (174, 181), "rooflayer_orange_roof": (185, 181),
    "rooflayer_water_brown": (154, 178), "rooflayer_water_green": (154, 181),
    "rooflayer_water_red": (154, 193), "rooflayer_open_pipe_top": (100, 115),
    "rooflayer_pipe": (100, 100), "rooflayer_pipe_work_02": (52, 198),
    "rooflayer_pipe_work_04": (190, 145), "rooflayer_white_box": (158, 150),
    "rooflayer_white_box_02": (130, 170), "rooflayer_white_box_03": (97, 124),
}
ROOF_ARCHETYPE_NAMES = ("mechanical", "waterworks", "mixed_service", "low_profile")
BASE_GRID_WIDTH = 64
PLAYABLE_AREA_MULTIPLIER = 2


def _east_district_copy(item: dict, x_offset: int) -> dict:
    copy = dict(item)
    if "gx" in copy:
        copy["gx"] = int(copy["gx"]) + x_offset
    for key in ("id", "object_id", "lighting_id", "crosswalk_id", "building_id"):
        if key in copy:
            copy[key] = f"{copy[key]}_east"
    if copy.pop("test_area", None) == "approved_transition_demo":
        if copy.get("interaction_kind") == "entrance_door":
            copy["target_interior_id"] = f"{copy.get('building_id', 'east_building')}_interior"
    return copy


def _double_playable_area(data: dict, rows: list[list[str]], buildings: list[dict]) -> tuple[list[list[str]], list[dict]]:
    """Build a connected eastern district while preserving the approved grid grammar."""
    if not rows or len(rows[0]) != BASE_GRID_WIDTH:
        return rows, buildings
    doubled_rows = [list(row) + list(row) for row in rows]
    east_buildings = []
    for building in buildings:
        copy = dict(building)
        copy["building_id"] = f"{building['building_id']}_east"
        copy["rect"] = [int(value) + (BASE_GRID_WIDTH if index % 2 == 0 else 0)
                        for index, value in enumerate(building["rect"])]
        east_buildings.append(copy)
    doubled_buildings = buildings + east_buildings
    synthesis = data.setdefault("building_synthesis", {})
    synthesis["buildings"] = doubled_buildings
    synthesis["building_count"] = len(doubled_buildings)
    synthesis["playable_area_multiplier"] = PLAYABLE_AREA_MULTIPLIER
    base_objects = list(data.get("objects", []))
    data["objects"] = base_objects + [_east_district_copy(obj, BASE_GRID_WIDTH) for obj in base_objects]
    base_spawns = [list(spawn) for spawn in data.get("login_spawns", [])]
    data["login_spawns"] = base_spawns + [
        [float(spawn[0]) + BASE_GRID_WIDTH * int(data.get("cell_px", 256)), float(spawn[1])]
        for spawn in base_spawns
    ]
    data["width"] = BASE_GRID_WIDTH * PLAYABLE_AREA_MULTIPLIER
    data["world_w"] = data["width"] * int(data.get("cell_px", 256))
    data["playable_area_multiplier"] = PLAYABLE_AREA_MULTIPLIER
    data["procedural_districts"] = ["approved_west", "connected_east"]
    return doubled_rows, doubled_buildings


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
    # v1.2 fixed-release city grammar: real wide-road geometry, not extra lanes
    # painted into the former narrow streets. The central east/west corridor is
    # a still-wider highway and blocks are rebuilt at lower density around it.
    x_blocks = ((0, 7), (15, 25), (33, 40), (48, 54))
    y_blocks = ((0, 5), (13, 18), (30, 35), (43, 47))
    envelopes = []
    for row_index, (y0, y1) in enumerate(y_blocks):
        for col_index, (x0, x1) in enumerate(x_blocks):
            # Leave several deterministic open lots/plazas for density variation.
            if (row_index * 5 + col_index) % 7 == 5:
                continue
            inset_x = 1 if x1 - x0 >= 5 else 0
            # Keep the authored sidewalk row outside each block, but use the
            # full interior height so six-cell envelopes can support a true
            # two-cell-margin courtyard without weakening road clearance.
            inset_y = 1 if y1 == len(original) - 1 else 0
            envelopes.append((x0 + inset_x, y0 + inset_y, x1 - inset_x, y1 - inset_y))
    rows = [list(row) for row in original]
    for y, row in enumerate(rows):
        for x, tile_id in enumerate(row):
            if tile_id.startswith("bld_"):
                rows[y][x] = "pavement_small"

    buildings = []
    for index, rect in enumerate(envelopes, 1):
        theme = THEMES[(index - 1) % len(THEMES)]
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
        if not footprint_connected(footprint):
            raise ValueError(f"disconnected generated footprint: {building['building_id']}")
        for x, y in footprint:
            rows[y][x] = f"bld_{building['theme']}_{role_for_cell(x, y, footprint)}"
        building["generated_cells"] = len(footprint)
        building["envelope_cells"] = (rect[2] - rect[0] + 1) * (rect[3] - rect[1] + 1)

    road_morphology = {"version": 4, "composition_pass": "wide_road_morphology_v130"}
    vertical_centers = (11, 29, 44, 58)
    # Reports #46 and #59 require physical clearance, not merely six painted
    # lanes squeezed into a narrow band. Primary roads are five cells wide and
    # the central east/west highway is seven, leaving full-size lanes/shoulders.
    horizontal_bands = ((9, 2), (24, 3), (39, 2))
    for y in range(len(rows)):
        for x in range(len(rows[y])):
            if any(abs(x - center) <= 2 for center in vertical_centers) or any(
                abs(y - center) <= radius for center, radius in horizontal_bands
            ):
                rows[y][x] = "road_fill"
    if any(not rows[y][x].startswith("bld_") for building in buildings
           for x, y in footprint_for(tuple(map(int, building["rect"])), building.get("notch"))):
        raise ValueError("road morphology pass overlapped an authoritative building footprint")

    data["building_synthesis"] = {
        "version": 4,
        "shape_family": "rectangles_l_shapes_stepped_recessed_and_courtyards",
        "morphology_pass": "building_morphology_next",
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
    data["road_morphology"].update({
        "physical_primary_road_width_cells": 5,
        "physical_central_highway_width_cells": 7,
        "lower_density_block_count": len(buildings),
        "geometry_authority": "v130_six_lane_clearance_and_central_highway_report59",
    })
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
    for building_index, building in enumerate(buildings):
        x0, y0, x1, y1 = map(int, building["rect"])
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        building_id = str(building["building_id"])
        footprint = footprint_for((x0, y0, x1, y1), building.get("notch"))
        anchors = transition_anchors(building, footprint)
        door_edge_x, door_edge_y = anchors["door"]
        fire_edge_x, fire_edge_y = anchors["fire_escape"]
        door_x, door_y = door_edge_x, door_edge_y + 1
        fire_x, fire_y = fire_edge_x + 1, fire_edge_y
        if not (0 <= door_y < len(rows) and not rows[door_y][door_x].startswith("bld_") and rows[door_y][door_x] != "road_fill"):
            raise ValueError(f"door approach is not a clear sidewalk surface: {building_id}")
        if not (0 <= fire_x < len(rows[0]) and not rows[fire_y][fire_x].startswith("bld_") and rows[fire_y][fire_x] != "road_fill"):
            raise ValueError(f"fire-escape approach is not a clear sidewalk surface: {building_id}")
        door = {
            "asset": "entrance_door", "gx": door_x, "gy": door_y,
            "offset_x_px": 72, "offset_y_px": 2,
            "width_px": 112, "height_px": 144, "building_id": building_id,
            "object_id": f"{building_id}_entrance_door",
            "edge": "south", "rotation": 0,
            "collision_radius_px": 0, "collision_kind": "none",
            "interaction_kind": "entrance_door", "interaction_level": 0,
            "interaction_radius_px": 72, "interaction_offset_x_px": 56,
            "interaction_offset_y_px": 140, "interaction_active": True,
            "interaction_prompt": "ENTER BUILDING",
            "target_interior_id": f"{building_id}_interior",
        }
        ladder = {
            "asset": "fire_escape_ladder", "gx": fire_x, "gy": fire_y,
            "offset_x_px": 97, "offset_y_px": 20,
            "width_px": 62, "height_px": 216, "building_id": building_id,
            "object_id": f"{building_id}_fire_escape_ladder",
            "edge": "east", "rotation": 0,
            "collision_radius_px": 0, "collision_kind": "none",
            "interaction_kind": "fire_escape_ladder", "interaction_level": 0,
            "interaction_radius_px": 76, "interaction_offset_x_px": 31,
            "interaction_offset_y_px": 108, "interaction_active": True,
            "interaction_prompt": "CLIMB FIRE ESCAPE",
            "connected_levels": [0, 1],
        }
        objects.extend((door, ladder))

        # The first building is a contained, serialized proof area.  Its buzzer
        # has a smaller independent zone beside the door; public/NPC entrances do
        # not receive buzzer art or triggers.
        if building_index == 0:
            door["test_area"] = "approved_transition_demo"
            ladder["test_area"] = "approved_transition_demo"
            door["target_interior_id"] = "approved_transition_demo_interior"
            objects.append({
                "asset": "entrance_buzzer", "gx": door_x, "gy": door_y,
                "offset_x_px": 190, "offset_y_px": 78,
                "width_px": 24, "height_px": 58, "building_id": building_id,
                "object_id": "approved_transition_demo_buzzer", "demo_only": True,
                "collision_radius_px": 0, "collision_kind": "none",
                "interaction_kind": "entrance_buzzer", "interaction_level": 0,
                "interaction_radius_px": 38, "interaction_offset_x_px": 12,
                "interaction_offset_y_px": 29, "interaction_active": True,
                "interaction_prompt": "USE BUZZER",
                "target_interior_id": "approved_transition_demo_interior",
                "locked_entry_message": "The entry is locked. Use the buzzer to contact a resident.",
            })
            safe_neighbours = [
                (door_x + dx, door_y + dy)
                for dx, dy in ((-1, 0), (1, 0), (-2, 0), (2, 0), (0, 1))
                if 0 <= door_x + dx < len(rows[0]) and 0 <= door_y + dy < len(rows)
                and rows[door_y + dy][door_x + dx] != "road_fill"
                and not rows[door_y + dy][door_x + dx].startswith("bld_")
            ]
            elevator_x, elevator_y = safe_neighbours[0] if safe_neighbours else (door_x, door_y)
            objects.append({
                "asset": "elevator_transition", "gx": elevator_x, "gy": elevator_y,
                "offset_x_px": 62, "offset_y_px": 16,
                "width_px": 132, "height_px": 120, "building_id": building_id,
                "object_id": "approved_transition_demo_elevator_ground", "demo_only": True,
                "collision_radius_px": 0, "collision_kind": "none",
                "interaction_kind": "elevator_transition", "interaction_level": 0,
                "interaction_radius_px": 70, "interaction_offset_x_px": 66,
                "interaction_offset_y_px": 112, "interaction_active": True,
                "interaction_prompt": "ELEVATOR FLOOR [0/1]",
                "available_floors": [0, 1],
                "floor_targets": {
                    "0": [(elevator_x + 0.5) * 256, (elevator_y + 0.5) * 256],
                    "1": [(anchors["hatch"][0] + 0.5) * 256, (anchors["hatch"][1] + 0.5) * 256],
                },
            })
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


def _place_generated_art_objects(
    templates: list[dict], rows: list[list[str]], buildings: list[dict],
) -> list[dict]:
    """Move approved decorative art to clear pavement cells deterministically.

    Catalog art remains collision-neutral, but visual placement still must not
    cover a road, doorway, fire escape, or the outside approach to either one.
    Templates provide the preferred location; the nearest safe pavement cell is
    selected when procedural building morphology occupies that location.
    """
    height, width = len(rows), len(rows[0])
    reserved: set[tuple[int, int]] = set()
    for building in buildings:
        footprint = footprint_for(tuple(map(int, building["rect"])), building.get("notch"))
        anchors = transition_anchors(building, footprint)
        for anchor in (anchors["door"], anchors["fire_escape"]):
            ax, ay = anchor
            reserved.update(
                (ax + dx, ay + dy)
                for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))
                if 0 <= ax + dx < width and 0 <= ay + dy < height
            )

    occupied: set[tuple[int, int]] = set()

    def safe(gx: int, gy: int) -> bool:
        return (
            0 <= gx < width and 0 <= gy < height
            and rows[gy][gx] in {"pavement_small", "pavement_pattern"}
            and (gx, gy) not in reserved and (gx, gy) not in occupied
        )

    placed: list[dict] = []
    for template in templates:
        preferred = int(template["gx"]), int(template["gy"])
        chosen = preferred if safe(*preferred) else None
        for radius in range(1, max(width, height) + 1):
            if chosen is not None:
                break
            candidates = [
                (preferred[0] + dx, preferred[1] + dy)
                for dy in range(-radius, radius + 1)
                for dx in range(-radius, radius + 1)
                if abs(dx) + abs(dy) == radius
            ]
            for candidate in sorted(candidates, key=lambda p: (p[1], p[0])):
                if safe(*candidate):
                    chosen = candidate
                    break
        if chosen is None:
            raise ValueError(f"no clear pavement placement for generated art {template['asset']!r}")
        item = dict(template)
        item["gx"], item["gy"] = chosen
        item["decorative_only"] = True
        item["collision_radius_px"] = 0
        item["placement_policy"] = "nearest_clear_pavement_outside_transition_clearance"
        occupied.add(chosen)
        placed.append(item)
    return placed


def _wide_road_surface_features(rows: list[list[str]]) -> tuple[list[dict], list[tuple[int, int, str]]]:
    """Aligned overlay markings and authored crossing ramps for the wide grid."""
    objects: list[dict] = []
    ramps: dict[tuple[int, int], str] = {}
    vertical = ((11, 2), (29, 2), (44, 2), (58, 2))
    horizontal = ((9, 2), (24, 3), (39, 2))

    def add(asset: str, gx: int, gy: int, rotation: int, kind: str, **extra) -> None:
        item = {
            "asset": asset, "gx": gx, "gy": gy, "rotation": rotation,
            "width_px": int(extra.pop("width_px", 18)),
            "height_px": int(extra.pop("height_px", 150)),
            "offset_x_px": int(extra.pop("offset_x_px", 119 if rotation == 0 else 53)),
            "offset_y_px": int(extra.pop("offset_y_px", 53 if rotation == 0 else 119)),
            "street_marking": kind, "decorative_only": True,
            "collision_radius_px": 0, "art_pass": "next_map_surface_markings",
        }
        item.update(extra)
        objects.append(item)

    for center, _radius in vertical:
        for gy in range(1, len(rows), 2):
            if any(abs(gy - hcenter) <= hradius + 1 for hcenter, hradius in horizontal):
                continue
            if rows[gy][center] != "road_fill":
                continue
            add("mark_double_yellow", center, gy, 0, "double_yellow_vertical", width_px=26)
            for divider in (center - 1, center + 1):
                if rows[gy][divider] == "road_fill":
                    add("mark_dashed_white_lane", divider, gy, 0, "dashed_white_vertical")

    for center, _radius in horizontal:
        for gx in range(1, len(rows[0]), 2):
            if any(abs(gx - vcenter) <= vradius + 1 for vcenter, vradius in vertical):
                continue
            if rows[center][gx] != "road_fill":
                continue
            add("mark_double_yellow", gx, center, 90, "double_yellow_horizontal", width_px=26)
            for divider in (center - 1, center + 1):
                if rows[divider][gx] == "road_fill":
                    add("mark_dashed_white_lane", gx, divider, 90, "dashed_white_horizontal")

    for vcenter, vradius in vertical:
        vx0, vx1 = vcenter - vradius, vcenter + vradius
        for hcenter, hradius in horizontal:
            hy0, hy1 = hcenter - hradius, hcenter + hradius
            for approach_y, suffix in ((hy0 - 1, "north"), (hy1 + 1, "south")):
                if 0 <= approach_y < len(rows):
                    for stripe, gx in enumerate(range(vx0, vx1 + 1)):
                        add(
                            "mark_zebra_crossing", gx, approach_y, 0, f"zebra_{suffix}",
                            width_px=44, height_px=176, offset_x_px=106, offset_y_px=40,
                            zebra_stripe_index=stripe,
                        )
                    ramps[(vx0 - 1, approach_y)] = "curb_ramp_right"
                    ramps[(vx1 + 1, approach_y)] = "curb_ramp_left"
            for approach_x, suffix in ((vx0 - 1, "west"), (vx1 + 1, "east")):
                if 0 <= approach_x < len(rows[0]):
                    for stripe, gy in enumerate(range(hy0, hy1 + 1)):
                        add(
                            "mark_zebra_crossing", approach_x, gy, 90, f"zebra_{suffix}",
                            width_px=44, height_px=176, offset_x_px=40, offset_y_px=106,
                            zebra_stripe_index=stripe,
                        )
                    ramps[(approach_x, hy0 - 1)] = "curb_ramp_bottom"
                    ramps[(approach_x, hy1 + 1)] = "curb_ramp_top"

    safe_ramps = []
    for (gx, gy), tile_id in sorted(ramps.items(), key=lambda item: (item[0][1], item[0][0])):
        if 0 <= gy < len(rows) and 0 <= gx < len(rows[0]) and rows[gy][gx] != "road_fill" and not rows[gy][gx].startswith("bld_"):
            safe_ramps.append((gx, gy, tile_id))
    return objects, safe_ramps


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
            "asset": "roof_access_door", "gx": hatch_x, "gy": hatch_y,
            "offset_x_px": 70, "offset_y_px": 58,
            "width_px": 116, "height_px": 140, "building_id": building_id,
            "object_id": f"{building_id}_roof_access_door",
            "rotation": 0, "collision_radius_px": 0, "collision_kind": "none",
            "interaction_kind": "roof_access_door", "interaction_level": 1,
            "interaction_radius_px": 72, "interaction_offset_x_px": 58,
            "interaction_offset_y_px": 70, "interaction_active": True,
            "interaction_prompt": "ENTER UPPER INTERIOR",
            "target_interior_id": f"{building_id}_upper_interior",
            "connected_levels": ["upper_interior", 1],
        })
        if index == 1:
            roof_objects[-1]["target_interior_id"] = "approved_transition_demo_upper_interior"
            roof_objects[-1]["test_area"] = "approved_transition_demo"
            roof_objects.append({
                "asset": "elevator_transition", "layer": "roof", "gx": hatch_x, "gy": hatch_y,
                "offset_x_px": 4, "offset_y_px": 68,
                "width_px": 62, "height_px": 58, "building_id": building_id,
                "object_id": "approved_transition_demo_elevator_roof", "demo_only": True,
                "collision_radius_px": 0, "collision_kind": "none",
                "interaction_kind": "elevator_transition", "interaction_level": 1,
                "interaction_radius_px": 58, "interaction_offset_x_px": 31,
                "interaction_offset_y_px": 50, "interaction_active": True,
                "interaction_prompt": "ELEVATOR FLOOR [0/1]",
                "available_floors": [0, 1],
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


def _transition_demo_runtime(rows: list[list[str]], objects: list[dict]) -> dict:
    """Build one contained transition/signal proof area from serialized data."""
    door = next((item for item in objects if item.get("test_area") == "approved_transition_demo"), None)
    if door is None:
        return {"interiors": [], "traffic_signals": [], "object_ids": []}
    door_x = int(door["gx"])
    door_y = int(door["gy"])
    entry_x = door_x * 256 + int(door.get("offset_x_px", 0)) + int(door.get("interaction_offset_x_px", 56))
    entry_y = door_y * 256 + int(door.get("offset_y_px", 0)) + int(door.get("interaction_offset_y_px", 140))

    road_cells = [
        (x, y) for y, row in enumerate(rows) for x, tile_id in enumerate(row)
        if tile_id == "road_fill"
        and all(
            0 <= x + dx < len(rows[0]) and 0 <= y + dy < len(rows)
            and rows[y + dy][x + dx] == "road_fill"
            for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3))
        )
    ]
    junction_x, junction_y = min(
        road_cells or [(door_x, door_y)],
        key=lambda cell: abs(cell[0] - door_x) + abs(cell[1] - door_y),
    )
    fixtures: list[tuple[int, int]] = []
    preferred = (
        (junction_x - 2, junction_y - 2), (junction_x + 2, junction_y - 2),
        (junction_x + 2, junction_y + 2), (junction_x - 2, junction_y + 2),
    )
    candidates = [
        (x, y) for y, row in enumerate(rows) for x, tile_id in enumerate(row)
        if tile_id != "road_fill" and not tile_id.startswith("bld_")
    ]
    for wanted_x, wanted_y in preferred:
        available = [cell for cell in candidates if cell not in fixtures]
        fixtures.append(min(available, key=lambda cell: abs(cell[0] - wanted_x) + abs(cell[1] - wanted_y)))

    traffic_signals = []
    for index, (gx, gy) in enumerate(fixtures):
        traffic_signals.append({
            "id": f"approved_transition_demo_signal_{index + 1}",
            "pos": [(gx + 0.5) * 256, (gy + 0.5) * 256],
            "phase": index % 2, "orientation": ("north", "east", "south", "west")[index],
            "rotation": index * 90, "signal_cycle_all_six": True,
            "signal_cycle_seconds": 9.0, "signal_cycle_offset": index * 0.75,
            "collision_radius_px": 0, "interaction_radius_px": 0,
            "test_area": "approved_transition_demo",
        })
    demo_objects = [
        str(item.get("object_id")) for item in objects
        if item.get("test_area") == "approved_transition_demo" or item.get("demo_only")
    ]
    return {
        "interiors": [{
            "id": "approved_transition_demo_interior", "name": "Transition Test Interior",
            "kind": "demo_interior", "entry": [entry_x, entry_y],
            "building_id": str(door.get("building_id", "")), "grid_native": True,
        }],
        "upper_interiors": [{
            "id": "approved_transition_demo_upper_interior", "name": "Transition Test Upper Interior",
            "kind": "demo_upper_interior", "building_id": str(door.get("building_id", "")),
        }],
        "traffic_signals": traffic_signals,
        "object_ids": demo_objects,
        "junction_cell": [junction_x, junction_y],
        "serialization": "grid_object_interactions_v1",
    }


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
    if bool((data.get("runtime") or {}).get("workbench_layout_authority", False)):
        # The promoted v4 map is already a complete Ground/Roof composition.
        # Do not rebuild the superseded 64x48 demonstration grammar over it.
        return GridWorld(data, TileCatalog.load(GRID_CATALOG_PATH))
    ground_rows, buildings = _synthesize_ground_runtime(data)
    ground_rows, buildings = _double_playable_area(data, ground_rows, buildings)

    if GRID_GENERATED_OBJECTS_PATH.is_file():
        generated = json.loads(GRID_GENERATED_OBJECTS_PATH.read_text(encoding="utf-8"))
        ground_generated = [
            obj for obj in generated.get("objects", [])
            if not obj.get("street_marking")
            and obj.get("asset") not in {
                "placeholder_street_door", "placeholder_fire_escape",
                "entrance_door", "fire_escape_ladder", "entrance_buzzer",
                "elevator_transition", "overlay_man_hole",
            }
            # Building-bound overlays were authored for the previous rectangular
            # footprints. Drop them instead of leaving old city_block awnings or
            # facade pieces floating across new recesses and courtyards.
            and not obj.get("building_id")
        ]
        # Transition anchors must be regenerated from the exact new footprint;
        # retaining positions authored for rectangles can strand a door or fire
        # escape inside a recess or courtyard void.
        base_rows = [row[:BASE_GRID_WIDTH] for row in ground_rows]
        base_buildings = buildings[:len(buildings) // PLAYABLE_AREA_MULTIPLIER]
        ground_generated.extend(_generated_ground_objects(base_rows, base_buildings))
        road_markings, crossing_ramps = _wide_road_surface_features(base_rows)
        ground_generated.extend(road_markings)
        for gx, gy, tile_id in crossing_ramps:
            ground_rows[gy][gx] = tile_id
            ground_rows[gy][gx + BASE_GRID_WIDTH] = tile_id
        ground_generated += [
            _east_district_copy(obj, BASE_GRID_WIDTH)
            for obj in ground_generated if not obj.get("demo_only")
        ]
    else:
        ground_generated = _generated_ground_objects(ground_rows, buildings)
    data.setdefault("objects", []).extend(ground_generated)

    # Generated v4 artwork remains separate from the source packs and map
    # geometry. It is visual-only, while sharing the same mirrored district
    # convention as the rest of the authored ground dressing.
    if GRID_GENERATED_ART_OBJECTS_PATH.is_file():
        generated_art = json.loads(GRID_GENERATED_ART_OBJECTS_PATH.read_text(encoding="utf-8"))
        art_objects = _place_generated_art_objects(
            list(generated_art.get("objects", [])), ground_rows[:], buildings[:len(buildings) // 2],
        )
        if art_objects:
            art_objects += [_east_district_copy(obj, BASE_GRID_WIDTH) for obj in art_objects]
            data.setdefault("objects", []).extend(art_objects)
    else:
        art_objects = []

    roof_data = _load_roof_data(data, ground_rows, buildings)
    roof_rows = [list(row) for row in roof_data["layers"]["roof"]]
    _assert_exact_roof_registration(ground_rows, roof_rows)

    data["layers"] = {"ground": ground_rows, "roof": roof_rows}
    data.pop("layers_ascii", None)
    roof_objects = list(roof_data.get("objects", []))
    data.setdefault("objects", []).extend(roof_objects)
    block_props = build_procedural_block_props(ground_rows, buildings)
    data.setdefault("objects", []).extend(block_props)
    data["generation_scope"] = ["ground", "roof"]
    data["external_ground_roof_composite"] = True
    data["external_composite_object_count"] = len(roof_objects)
    data["generated_ground_object_count"] = len(ground_generated)
    data["generated_v4_art_object_count"] = len(art_objects)
    data["procedural_block_prop_count"] = len(block_props)
    data["roof_registration"] = "exact_ground_building_footprint"
    transition_demo = _transition_demo_runtime(ground_rows, data["objects"])
    data["transition_demo"] = transition_demo
    data["traffic_signals"] = list(transition_demo["traffic_signals"])
    data["interiors"] = list(transition_demo["interiors"])
    data["upper_interiors"] = list(transition_demo["upper_interiors"])
    runtime = data.setdefault("runtime", {})
    runtime["external_roofs_visible_on_ground"] = True
    runtime["roof_collision_authority"] = "ground"
    return GridWorld(data, TileCatalog.load(GRID_CATALOG_PATH))


@lru_cache(maxsize=1)
def load_roof_grid() -> GridWorld:
    ground_data = json.loads(GRID_MAP_PATH.read_text(encoding="utf-8"))
    if bool((ground_data.get("runtime") or {}).get("workbench_layout_authority", False)):
        return GridWorld(ground_data, TileCatalog.load(GRID_CATALOG_PATH))
    ground_rows, buildings = _synthesize_ground_runtime(ground_data)
    ground_rows, buildings = _double_playable_area(ground_data, ground_rows, buildings)
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
        "transition_demo": dict(world.data.get("transition_demo", {})),
        "grid_traffic_signals": [dict(row) for row in world.data.get("traffic_signals", [])],
        "grid_interiors": [dict(row) for row in world.data.get("interiors", [])],
    }
