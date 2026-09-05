#!/usr/bin/env python3
"""Compile the approved GWB workbench layout into the sole v4.0 runtime map."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT = ROOT / "dev_tools" / "map_generator" / "working_cosmetics" / "approved_v4_layout"
MAP = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"
GRID = MAP / "grid_v100"
CELL = 128
WORLD_W = 16384
WORLD_H = 10240
GRID_W = WORLD_W // CELL
GRID_H = WORLD_H // CELL
THEMES = ("blue", "dark_green", "green", "red", "yellow")
SOUTH_FACING_ROTATION = 0


def read_csv(name: str) -> list[dict[str, str]]:
    with (LAYOUT / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def stable(text: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(str(text)))


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def point_segment_distance(px: float, py: float, road: dict) -> float:
    ax, ay, bx, by = (number(road, key) for key in ("x1", "y1", "x2", "y2"))
    vx, vy = bx - ax, by - ay
    denominator = vx * vx + vy * vy
    if denominator <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / denominator))
    return math.hypot(px - (ax + vx * t), py - (ay + vy * t))


def pavement_asset(block: dict) -> str:
    seed = stable(str(block.get("block_id", "block")))
    if str(block.get("district", "")) == "morningside" and seed % 3 == 0:
        family = "pavement_plaza"
    elif seed % 5 == 0:
        family = "pavement_patched"
    else:
        family = "pavement_standard"
    return f"{family}_variant_{seed % 4}"


def footprint(row: dict) -> set[tuple[int, int]]:
    x, y, w, h = (number(row, key) for key in ("x", "y", "w", "h"))
    nx, ny = max(2, round(w / CELL)), max(2, round(h / CELL))
    local = {(gx, gy) for gy in range(ny) for gx in range(nx)}
    shape = str(row.get("shape", "rectangle"))
    notch_w, notch_h = max(1, nx // 3), max(1, ny // 3)
    if shape.startswith("notch_"):
        north = shape.endswith(("ne", "nw"))
        east = shape.endswith(("ne", "se"))
        xs = range(nx - notch_w, nx) if east else range(notch_w)
        ys = range(notch_h) if north else range(ny - notch_h, ny)
        local.difference_update((gx, gy) for gy in ys for gx in xs)
    elif shape == "courtyard" and nx >= 3 and ny >= 3:
        local.difference_update((gx, gy) for gy in range(1, ny - 1) for gx in range(1, nx - 1))
    cells = set()
    for gx, gy in local:
        wx, wy = x + (gx + 0.5) * w / nx, y + (gy + 0.5) * h / ny
        cells.add((max(0, min(GRID_W - 1, int(wx // CELL))), max(0, min(GRID_H - 1, int(wy // CELL)))))
    return cells


def role_for_cell(x: int, y: int, cells: set[tuple[int, int]]) -> str:
    n, s, w, e = (x, y - 1) in cells, (x, y + 1) in cells, (x - 1, y) in cells, (x + 1, y) in cells
    nw, ne, sw, se = (x - 1, y - 1) in cells, (x + 1, y - 1) in cells, (x - 1, y + 1) in cells, (x + 1, y + 1) in cells
    if n and s and w and e and not nw: return "top_left_inner"
    if n and s and w and e and not ne: return "top_right_inner"
    if n and s and w and e and not sw: return "bottom_left_inner"
    if n and s and w and e and not se: return "bottom_right_inner"
    if not n and not w: return "top_left_outer"
    if not n and not e: return "top_right_outer"
    if not s and not w: return "bottom_left_outer"
    if not s and not e: return "bottom_right_outer"
    if not n: return "top_center"
    if not s: return "bottom_center"
    if not w: return "left"
    if not e: return "right"
    return "fill"


def object_definitions() -> dict[str, dict]:
    objects: dict[str, dict] = {}
    for name in ("tile_catalog.json", "generated_art_tiles.json", "generated_transition_objects.json"):
        payload = json.loads((ROOT / "assets" / "grid_v100" / name).read_text(encoding="utf-8"))
        objects.update(payload.get("objects", {}))
    return objects


def placed_object(asset: str, left: float, top: float, width: int, height: int, *, layer: str = "ground", **extra) -> dict:
    gx, gy = math.floor(left / CELL), math.floor(top / CELL)
    return {
        "asset": asset, "gx": gx, "gy": gy,
        "offset_x_px": round(left - gx * CELL), "offset_y_px": round(top - gy * CELL),
        "width_px": width, "height_px": height, "layer": layer,
        "rotation": SOUTH_FACING_ROTATION, "visual_facing": "south", **extra,
    }


def centered_object(defs: dict[str, dict], asset: str, cx: float, cy: float, height: int, *, layer: str = "ground", **extra) -> dict:
    definition = defs[asset]
    width = max(2, round(height * int(definition.get("native_width_px", height)) / max(1, int(definition.get("native_height_px", height)))))
    return placed_object(asset, cx - width / 2, cy - height / 2, width, height, layer=layer, **extra)


def build_runtime() -> tuple[dict, list[dict], list[dict]]:
    streets = read_csv("streets.csv")
    blocks = read_csv("pavement_blocks.csv")
    houses = read_csv("empty_houses.csv")
    slots = read_csv("sprite_slots.csv")
    access = read_csv("building_access.csv")
    features = read_csv("street_features.csv")
    contract = {row["key"]: row["value"] for row in read_csv("layout_contract.csv")}
    regular_width = float(contract["regular_road_width"])
    bridge_width = float(contract["gwb_road_width"])
    road_width = {"bridge": bridge_width, "primary": regular_width, "secondary": regular_width, "residential": regular_width}

    ground = [["pavement_standard_variant_0" for _ in range(GRID_W)] for _ in range(GRID_H)]
    for block in blocks:
        x0, y0, w, h = (number(block, key) for key in ("x", "y", "w", "h"))
        asset = pavement_asset(block)
        for gy in range(max(0, int(y0 // CELL)), min(GRID_H, math.ceil((y0 + h) / CELL))):
            for gx in range(max(0, int(x0 // CELL)), min(GRID_W, math.ceil((x0 + w) / CELL))):
                cx, cy = (gx + 0.5) * CELL, (gy + 0.5) * CELL
                if x0 <= cx <= x0 + w and y0 <= cy <= y0 + h:
                    ground[gy][gx] = asset

    river_x0, river_x1 = float(contract["hudson_west_x"]), float(contract["hudson_east_x"])
    for gy in range(GRID_H):
        for gx in range(GRID_W):
            cx = (gx + 0.5) * CELL
            if river_x0 <= cx <= river_x1:
                ground[gy][gx] = "water_deep"
            elif river_x0 - 180 <= cx < river_x0 or river_x1 < cx <= river_x1 + 180:
                ground[gy][gx] = "sand_damp"

    road_cells: set[tuple[int, int]] = set()
    for gy in range(GRID_H):
        for gx in range(GRID_W):
            cx, cy = (gx + 0.5) * CELL, (gy + 0.5) * CELL
            for road in streets:
                if point_segment_distance(cx, cy, road) <= road_width[str(road.get("road_class", "residential"))] * 0.5:
                    road_cells.add((gx, gy)); ground[gy][gx] = "road_fill"; break

    # Cardinal and diagonal-aware curb selection around the final road mask.
    for gy in range(GRID_H):
        for gx in range(GRID_W):
            if (gx, gy) in road_cells or ground[gy][gx].startswith(("water_", "sand_")):
                continue
            rn, rs, rw, re = (gx, gy - 1) in road_cells, (gx, gy + 1) in road_cells, (gx - 1, gy) in road_cells, (gx + 1, gy) in road_cells
            if re and rs: ground[gy][gx] = "curb_br_outer"
            elif rw and rs: ground[gy][gx] = "curb_bl_outer"
            elif re and rn: ground[gy][gx] = "curb_tr_outer"
            elif rw and rn: ground[gy][gx] = "curb_tl_outer"
            elif rs: ground[gy][gx] = "curb_bottom"
            elif rn: ground[gy][gx] = "curb_top"
            elif re: ground[gy][gx] = "curb_right"
            elif rw: ground[gy][gx] = "curb_left"

    building_rows = houses + [row for row in slots if row.get("sprite_role") not in {"small_pier", "bridge_tower", "athletic_field"}]
    buildings = []
    all_building_cells: set[tuple[int, int]] = set()
    for index, row in enumerate(building_rows):
        cells = footprint(row)
        if cells & road_cells:
            raise RuntimeError(f"building overlaps runtime road cells: {row.get('housing_id') or row.get('slot_id')}")
        building_id = str(row.get("housing_id") or row.get("slot_id"))
        theme = THEMES[stable(building_id) % len(THEMES)]
        for gx, gy in cells:
            ground[gy][gx] = f"bld_{theme}_{role_for_cell(gx, gy, cells)}"
        all_building_cells.update(cells)
        xs, ys = [p[0] for p in cells], [p[1] for p in cells]
        buildings.append({
            "building_id": building_id, "theme": theme,
            "rect": [min(xs), min(ys), max(xs), max(ys)],
            "footprint_cells": [[x, y] for x, y in sorted(cells, key=lambda p: (p[1], p[0]))],
            "shape": row.get("shape", "rectangle"), "ground_roof_registration": "exact",
        })
    roof = [[ground[y][x] if (x, y) in all_building_cells else "void" for x in range(GRID_W)] for y in range(GRID_H)]

    defs = object_definitions()
    objects: list[dict] = []
    feature_assets = {
        "street_lamp": ("street_lamp_10_night", 150), "street_tree": ("v4_art_tree", 185),
        "fire_hydrant": ("v4_art_hydrant", 62), "telephone": ("v4_art_phone_box", 78),
        "traffic_cone": ("v4_art_cone", 46), "manhole": ("overlay_man_hole", 52),
    }
    for row in features:
        kind = str(row.get("kind", ""))
        if kind in feature_assets:
            asset, height = feature_assets[kind]
            objects.append(centered_object(defs, asset, number(row, "x"), number(row, "y"), height,
                                           overhead=(kind == "street_tree"), decorative_only=True))

    road_by_id = {str(row["street_id"]): row for row in streets}
    crossings = [row for row in features if row.get("kind") == "crosswalk"]
    for row in crossings:
        rotation = int(number(row, "rotation"))
        span = number(row, "length", regular_width + 130) - 130
        pieces = max(5, round(span / 62))
        for index in range(pieces):
            offset = -span / 2 + (index + 0.5) * span / pieces
            cx = number(row, "x") if rotation % 180 == 90 else number(row, "x") + offset
            cy = number(row, "y") + offset if rotation % 180 == 90 else number(row, "y")
            width, height = (144, 56) if rotation % 180 == 90 else (56, 144)
            obj = placed_object("mark_zebra_crossing", cx - width / 2, cy - height / 2, 56, 144,
                                rotation=rotation, geometry_rotation=True, decorative_only=True)
            objects.append(obj)
        group, approach = str(row.get("group", ":")).rsplit(":", 1)
        horizontal_id, vertical_id = group.split("+", 1)
        crossed = road_by_id[vertical_id if approach in {"north", "south"} else horizontal_id]
        curb = road_width[str(crossed.get("road_class", "residential"))] * 0.5
        ramps = ((number(row, "x") - curb, number(row, "y"), "curb_ramp_left"), (number(row, "x") + curb, number(row, "y"), "curb_ramp_right")) if rotation % 180 == 0 else ((number(row, "x"), number(row, "y") - curb, "curb_ramp_top"), (number(row, "x"), number(row, "y") + curb, "curb_ramp_bottom"))
        for rx, ry, tile_id in ramps:
            gx, gy = max(0, min(GRID_W - 1, int(rx // CELL))), max(0, min(GRID_H - 1, int(ry // CELL)))
            if (gx, gy) not in road_cells and (gx, gy) not in all_building_cells:
                ground[gy][gx] = tile_id

    # Lane markings remain geometric rotations; all perspective-bearing art is south-facing.
    junctions = [(number(row, "x"), number(row, "y")) for row in crossings]
    for road in streets:
        width = road_width[str(road.get("road_class", "residential"))]
        lanes = 9 if road.get("road_class") == "bridge" else 4
        ax, ay, bx, by = (number(road, key) for key in ("x1", "y1", "x2", "y2"))
        horizontal = abs(bx - ax) >= abs(by - ay)
        length = abs(bx - ax) if horizontal else abs(by - ay)
        for lane in range(1, lanes):
            lateral = -width / 2 + width * lane / lanes
            for along in range(128, max(129, int(length)), 192):
                cx = min(ax, bx) + along if horizontal else ax + lateral
                cy = ay + lateral if horizontal else min(ay, by) + along
                if any(math.hypot(cx - jx, cy - jy) < width * 0.8 for jx, jy in junctions):
                    continue
                width_px, height_px, rotation = (10, 72, 0) if not horizontal else (72, 10, 90)
                objects.append(placed_object("mark_white_repeating_single", cx - width_px / 2, cy - height_px / 2,
                                             10, 72, rotation=rotation, geometry_rotation=True, decorative_only=True))

    access_by_building: dict[str, list[dict]] = {}
    for row in access:
        access_by_building.setdefault(str(row.get("building_id", "")), []).append(row)
        kind = str(row.get("kind", ""))
        asset, height, layer = {
            "player_house_door": ("entrance_door", 78, "ground"), "public_door": ("entrance_door", 78, "ground"),
            "roof_access_door": ("roof_access_door", 74, "roof"), "elevator_transition": ("elevator_transition", 78, "ground"),
            "fire_escape": ("fire_escape_ladder", 112, "ground"),
        }.get(kind, ("", 0, "ground"))
        if not asset: continue
        definition = defs[asset]
        width = max(2, round(height * int(definition["native_width_px"]) / int(definition["native_height_px"])))
        px, py = number(row, "x"), number(row, "y")
        pivot_x = width * int(definition.get("pivot_x_px", 0)) / int(definition["native_width_px"])
        pivot_y = height * int(definition.get("pivot_y_px", 0)) / int(definition["native_height_px"])
        destination = str(row.get("destination", ""))
        if destination.startswith("interior:"):
            destination = destination.split(":", 1)[1]
        objects.append(placed_object(asset, px - pivot_x, py - pivot_y, width, height, layer=layer,
                                     object_id=str(row.get("access_id", "")), building_id=str(row.get("building_id", "")),
                                     interaction_kind=kind, interaction_radius_px=number(row, "interaction_radius"),
                                     collision_radius_px=0, interaction_active=True, target_interior_id=destination))
    for house in houses:
        if str(house.get("buzzer_enabled", "")).lower() != "true": continue
        objects.append(centered_object(defs, "entrance_buzzer", number(house, "buzzer_x") + 48, number(house, "buzzer_y") - 13, 26,
                                       object_id=f"buzzer_{house['housing_id']}", building_id=house["housing_id"],
                                       interaction_kind="entrance_buzzer", interaction_radius_px=number(house, "buzzer_interaction_radius"),
                                       collision_radius_px=0, interaction_active=True))

    roof_props = ("rooflayer_aircon", "rooflayer_aircon_large", "rooflayer_blue_roof", "rooflayer_green_roof", "rooflayer_grey_roof", "rooflayer_orange_roof", "rooflayer_water_brown", "rooflayer_water_green", "rooflayer_water_red")
    for row in building_rows:
        building_id = str(row.get("housing_id") or row.get("slot_id"))
        if row in houses or stable(building_id) % 3: continue
        asset = roof_props[stable(building_id) % len(roof_props)]
        objects.append(centered_object(defs, asset, number(row, "x") + number(row, "w") / 2, number(row, "y") + number(row, "h") / 2,
                                       max(48, round(min(number(row, "w"), number(row, "h")) * 0.22)), layer="roof", decorative_only=True))

    signals = []
    for index, row in enumerate(feature for feature in features if feature.get("kind") == "traffic_signal"):
        signals.append({
            "id": f"gwb_signal_{index + 1:03d}", "pos": [number(row, "x"), number(row, "y")],
            "phase": stable(str(row.get("group", ""))) % 2, "orientation": "south", "semantic_rotation": int(number(row, "rotation")),
            "rotation": SOUTH_FACING_ROTATION, "visual_facing": "south", "signal_cycle_all_six": True,
            "signal_cycle_seconds": 9.0, "signal_cycle_offset": (index % 6) * 0.75,
            "collision_radius_px": 0, "interaction_radius_px": 0,
        })

    def nearest_sidewalk_spawn(x: float, y: float) -> list[float]:
        """Choose a whole collision cell outside a building and out of traffic."""
        start_x = max(0, min(GRID_W - 1, int(x // CELL)))
        start_y = max(0, min(GRID_H - 1, int(y // CELL)))
        candidates: list[tuple[float, int, int]] = []
        for radius in range(0, 9):
            for dy in range(-radius, radius + 1):
                dx = radius - abs(dy)
                for gx in ({start_x - dx, start_x + dx} if dx else {start_x}):
                    gy = start_y + dy
                    if not (0 <= gx < GRID_W and 0 <= gy < GRID_H):
                        continue
                    tile_id = ground[gy][gx]
                    if tile_id.startswith("bld_") or tile_id.startswith(("water_", "road_")) or tile_id == "void":
                        continue
                    cx, cy = (gx + 0.5) * CELL, (gy + 0.5) * CELL
                    candidates.append((math.hypot(cx - x, cy - y), gx, gy))
            if candidates:
                _distance, gx, gy = min(candidates)
                return [(gx + 0.5) * CELL, (gy + 0.5) * CELL]
        raise RuntimeError(f"no safe sidewalk spawn near {(x, y)}")

    login_spawns = [nearest_sidewalk_spawn(number(house, "buzzer_x"), number(house, "buzzer_y") + 48) for house in houses[:8]]
    data = {
        "format": "open-night-grid-v4", "authority": "approved_gwb_workbench_v4", "cell_px": CELL,
        "width": GRID_W, "height": GRID_H, "world_w": WORLD_W, "world_h": WORLD_H,
        "source_pack": "generated_v4_catalog_overrides", "layers": {"ground": ground, "roof": roof},
        "objects": objects, "login_spawns": login_spawns,
        "building_synthesis": {"version": 4, "buildings": buildings, "building_count": len(buildings),
                               "shape_family": "rectangles_l_shapes_stepped_recessed_and_courtyards", "roof_registration": "exact_ground_footprint"},
        "traffic_signals": signals, "interiors": [], "upper_interiors": [],
        "runtime": {"ground_playable": True, "legacy_surface_entities": False, "workbench_layout_authority": True,
                    "visual_orientation": "south", "vehicle_water_blocked": True, "pedestrian_water_speed_multiplier": 0.55},
        "generation_scope": ["ground", "roof"], "roof_registration": "exact_ground_building_footprint",
    }
    return data, buildings, crossings


def write_mapfiles(data: dict, buildings: list[dict], crossings: list[dict]) -> None:
    streets, houses = read_csv("streets.csv"), read_csv("empty_houses.csv")
    zones = read_csv("district_zones.csv")
    map_rows = [
        ("id", "map_001_gwb_corridor", "str"), ("name", "Open Night v4.0 — GWB Corridor", "str"),
        ("description", "Approved Fort Lee / Hudson / Washington Heights GWB workbench promoted for v4.0 playtesting.", "str"),
        ("chunked", "true", "bool"), ("chunk_size", "1024", "int"), ("chunk_cols", "16", "int"), ("chunk_rows", "10", "int"),
        ("world_w", str(WORLD_W), "int"), ("world_h", str(WORLD_H), "int"), ("interest_radius_chunks", "2", "int"),
        ("network_zone_size", "3072", "int"), ("network_zone_radius", "1", "int"), ("chunk_cache_limit", "30", "int"),
        ("procedural_buildings", "false", "bool"), ("grid_enabled", "true", "bool"), ("grid_cell_size", str(CELL), "int"),
        ("grid_chunk_cache_limit", "30", "int"), ("baked_composition", "false", "bool"),
        ("render_style", "approved_gwb_workbench_v4", "str"), ("camera_projection", "orthographic_topdown", "str"),
        ("outdoor_perspective_skew", "0", "float"), ("global_map_rotation_deg", "0", "float"),
        ("default_render_mode", "night", "str"), ("release_version", "4.0", "str"),
        ("map_build_id", "open_night_v4_0_gwb_workbench_playtest", "str"), ("approved_visual_checkpoint", "gwb_workbench_v4", "str"),
        ("yellow_center_lines", "false", "bool"), ("runtime_building_collision_inset", "0", "float"),
    ]
    write_csv(MAP / "map.csv", ("key", "value", "type"), [dict(zip(("key", "value", "type"), row)) for row in map_rows])
    road_rows, road_points, sidewalks = [], [], []
    for road in streets:
        rid, cls = road["street_id"], road.get("road_class", "residential")
        width, lanes = (1050, 9) if cls == "bridge" else (420, 4)
        road_rows.append({"road_id": rid, "name": road["name"], "base_width": width, "width": width, "lanes": lanes,
                          "sidewalk_width": 75, "curb_width": 12, "building_setback": 0, "bridge": str(cls == "bridge").lower(),
                          "map_label": "true", "highway": "motorway" if cls == "bridge" else "primary", "level": 0, "walkable": "true"})
        road_points += [{"road_id": rid, "point_order": 0, "x": road["x1"], "y": road["y1"]}, {"road_id": rid, "point_order": 1, "x": road["x2"], "y": road["y2"]}]
        sidewalks += [{"sidewalk_id": f"{rid}_{side}", "road_id": rid, "side": side, "width": 75} for side in ("left", "right")]
    write_csv(MAP / "roads.csv", ("road_id","name","base_width","width","lanes","sidewalk_width","curb_width","building_setback","bridge","map_label","highway","level","walkable"), road_rows)
    write_csv(MAP / "road_points.csv", ("road_id","point_order","x","y"), road_points)
    write_csv(MAP / "sidewalks.csv", ("sidewalk_id","road_id","side","width"), sidewalks)
    building_csv = []
    for building in buildings:
        xs, ys = [cell[0] for cell in building["footprint_cells"]], [cell[1] for cell in building["footprint_cells"]]
        building_csv.append({"id": building["building_id"], "x": min(xs)*CELL, "y": min(ys)*CELL, "w": (max(xs)-min(xs)+1)*CELL, "h": (max(ys)-min(ys)+1)*CELL})
    write_csv(MAP / "buildings.csv", ("id","x","y","w","h"), building_csv)
    write_csv(MAP / "building_visuals.csv", ("building_id","profile","height_px","roof_style","roof_inset","penthouses","shadow_scale"), [])
    write_csv(MAP / "building_sprites.csv", ("building_id","district","building_kind","atlas","cell","world_units_per_source_pixel","render_scale_ratio","scale_status"), [])
    write_csv(MAP / "building_layers.csv", ("building_id","level_id","layer_kind","z_order","walkable","visual_role","transition_policy"), [])
    write_csv(MAP / "building_stairwells.csv", ("stairwell_id","building_id","kind","side","x","y","from_level","intermediate_level","to_level","interaction_keys","transition_mode"), [])
    interiors = [{"id": house["housing_id"], "name": "Empty House", "kind": "blank_house", "entry_x": house["buzzer_x"], "entry_y": house["buzzer_y"], "building_id": house["housing_id"], "door_hint": "south"} for house in houses]
    write_csv(MAP / "interiors.csv", ("id","name","kind","entry_x","entry_y","building_id","door_hint"), interiors)
    points = []
    for index, spawn in enumerate(data["login_spawns"]):
        points += [{"group":"spawn","id":index,"x":spawn[0],"y":spawn[1]}, {"group":"login_spawn","id":index,"x":spawn[0],"y":spawn[1]}]
    points += [{"group":"supplier","id":0,"x":3900,"y":6000}, {"group":"customer","id":0,"x":12400,"y":6000}]
    write_csv(MAP / "points.csv", ("group","id","x","y"), points)
    write_csv(MAP / "districts.csv", ("name","x","y"), [{"name": row["name"], "x": number(row,"x")+80, "y": number(row,"y")+80} for row in zones if row.get("density") != "water"])
    write_csv(MAP / "water_polygons.csv", ("polygon_id","point_order","x","y"), [{"polygon_id":"hudson","point_order":i,"x":x,"y":y} for i,(x,y) in enumerate(((6553,0),(9830,0),(9830,WORLD_H),(6553,WORLD_H)))])
    write_csv(MAP / "green_polygons.csv", ("polygon_id","point_order","x","y"), [])
    road_by_id = {row["street_id"]: row for row in streets}
    cross_rows = []
    for index, row in enumerate(crossings):
        junction, approach = row["group"].rsplit(":", 1); horizontal, vertical = junction.split("+", 1)
        cross_rows.append({"id":f"gwb_cross_{index+1:03d}","road_id":vertical if approach in {"north","south"} else horizontal,
                           "x":row["x"],"y":row["y"],"angle":row["rotation"],"length":row["length"],"width":144,
                           "stripe_width":56,"stripe_gap":32,"curb_cut_depth":32,"stop_bar_gap":36,"priority":"signalized"})
    write_csv(MAP / "crosswalks.csv", ("id","road_id","x","y","angle","length","width","stripe_width","stripe_gap","curb_cut_depth","stop_bar_gap","priority"), cross_rows)
    write_csv(MAP / "traffic_signals.csv", ("id","x","y","phase","orientation","rotation","signal_cycle_all_six","signal_cycle_seconds","signal_cycle_offset"), [])
    write_csv(MAP / "street_props.csv", ("id","kind","x","y","scale","rotation"), [])
    write_csv(MAP / "levels.csv", ("level_id","name","z_order","walkable"), [{"level_id":0,"name":"Ground","z_order":0,"walkable":"true"},{"level_id":2,"name":"Roof","z_order":2,"walkable":"true"}])
    write_csv(MAP / "level_connectors.csv", ("connector_id","kind","from_level","to_level","x0","y0","x1","y1","width"), [])
    write_csv(MAP / "landmarks.csv", ("id","name","kind","x","y"), [{"id":"gwb","name":"George Washington Bridge","kind":"bridge","x":8192,"y":3560}])

    routes = {
        "traffic_fort_lee": [(1900,3000),(4700,3000),(4700,7350),(1900,7350),(1900,3000)],
        "traffic_heights": [(11600,1800),(14300,1800),(14300,8800),(11600,8800),(11600,1800)],
        "traffic_gwb": [(6100,3560),(10250,3560),(6100,3560)],
    }
    route_rows, route_points = [], []
    for rid, points_for_route in routes.items():
        route_rows.append({"route_id":rid,"name":rid.replace("_"," ").title(),"speed_limit":94 if rid.endswith("gwb") else 82,"loop":"true","lane_offset":0,"turn_radius":90,"axis":"mixed","direction":"loop"})
        route_points += [{"route_id":rid,"point_order":i,"x":x,"y":y} for i,(x,y) in enumerate(points_for_route)]
    write_csv(MAP / "traffic_routes.csv", ("route_id","name","speed_limit","loop","lane_offset","turn_radius","axis","direction"), route_rows)
    write_csv(MAP / "traffic_route_points.csv", ("route_id","point_order","x","y"), route_points)
    traffic_starts=[]
    for index in range(28):
        rid=tuple(routes)[index%3]; traffic_starts.append({"spawn_id":f"traffic_{index+1:02d}","route_id":rid,"start_fraction":round((index//3)/10,3),"asset_index":index%28,"appearance_index":index%28,"speed_scale":1})
    write_csv(MAP / "traffic_starts.csv", ("spawn_id","route_id","start_fraction","asset_index","appearance_index","speed_scale"), traffic_starts)
    npc_routes={"walk_fort_lee":[(1500,2600),(5100,2600),(5100,7600),(1500,7600),(1500,2600)],"walk_heights":[(11000,1400),(15000,1400),(15000,9200),(11000,9200),(11000,1400)]}
    write_csv(MAP / "npc_routes.csv", ("route_id","name","speed","loop","lane_offset","turn_radius","axis","direction"), [{"route_id":rid,"name":rid,"speed":54,"loop":"true","lane_offset":0,"turn_radius":42,"axis":"mixed","direction":"loop"} for rid in npc_routes])
    write_csv(MAP / "npc_routes_points.csv", ("route_id","point_order","x","y"), [{"route_id":rid,"point_order":i,"x":x,"y":y} for rid,pts in npc_routes.items() for i,(x,y) in enumerate(pts)])
    write_csv(MAP / "npc_starts.csv", ("spawn_id","route_id","start_fraction","asset_index","appearance_index","speed_scale"), [{"spawn_id":f"npc_{i+1:03d}","route_id":tuple(npc_routes)[i%2],"start_fraction":round((i//2)/54,3),"asset_index":i,"appearance_index":i,"speed_scale":1} for i in range(108)])
    for name, fields in {
        "bicycle_routes.csv":("route_id","name","speed","loop","lane_offset","turn_radius","axis","direction"),
        "bicycle_routes_points.csv":("route_id","point_order","x","y"), "bicycle_starts.csv":("spawn_id","route_id","start_fraction","asset_index","appearance_index","speed_scale"),
        "parked_vehicles.csv":("x","y","angle"), "parked_bicycles.csv":("x","y","angle"), "bike_lanes.csv":("lane_id","name","width","protected","direction"),
        "bike_lane_points.csv":("lane_id","point_order","x","y"), "transit_routes.csv":("route_id","mode","name"),
        "transit_route_points.csv":("route_id","point_order","x","y"), "transit_stops.csv":("stop_id","route_id","name","x","y"),
    }.items(): write_csv(MAP / name, fields, [])
    write_csv(MAP / "render_contract.csv", ("key","value","type"), [{"key":"camera_projection","value":"orthographic_topdown","type":"str"},{"key":"outdoor_perspective_skew","value":0,"type":"float"},{"key":"baked_composition","value":"false","type":"bool"},{"key":"approved_visual_checkpoint","value":"gwb_workbench_v4","type":"str"}])


def main() -> int:
    data, buildings, crossings = build_runtime()
    GRID.mkdir(parents=True, exist_ok=True)
    (GRID / "ground_grid.json").write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    roof_data = {key: value for key, value in data.items() if key not in {"traffic_signals", "interiors", "upper_interiors"}}
    roof_data["layers"] = {"ground": data["layers"]["ground"], "roof": data["layers"]["roof"]}
    (GRID / "roof_grid.generated.json").write_text(json.dumps(roof_data, separators=(",", ":")) + "\n", encoding="utf-8")
    (GRID / "ground_generated_objects.json").write_text(json.dumps({"format":"open-night-gwb-v4-promoted","objects":[]}, separators=(",", ":")) + "\n", encoding="utf-8")
    write_mapfiles(data, buildings, crossings)
    print(f"GWB_V4_PROMOTED grid={GRID_W}x{GRID_H}@{CELL} buildings={len(buildings)} objects={len(data['objects'])} signals={len(data['traffic_signals'])} crossings={len(crossings)} houses=32")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
