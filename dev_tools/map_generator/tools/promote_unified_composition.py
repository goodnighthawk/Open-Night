from __future__ import annotations

"""Promote the reviewed unified composition into the sole runtime map.

The composition PNGs are the visual authority.  Runtime CSVs are regenerated
from the exact same Pass 18 authored geometry so rendering, collision and map
navigation cannot drift apart again.
"""

import csv
import zipfile
from pathlib import Path

import build_unified_composition as composition


ROOT = Path(__file__).resolve().parents[3]
MAP_DIRS = (
    ROOT / "mapfiles" / "data" / "map_001_gwb_corridor",
    ROOT / "dev_tools" / "map_generator" / "mapfiles" / "data" / "map_001_gwb_corridor",
)
SEMANTIC = composition.SEMANTIC
ART_ARCHIVE = ROOT / "assets" / "environment" / "approved" / "map_001_gwb_corridor" / "composition_tiles_v18.zip"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def map_rows() -> list[dict[str, str]]:
    return [
        {"key": "id", "value": "map_001_gwb_corridor", "type": "str"},
        {"key": "name", "value": "Open Night — Fort Lee / GWB / Washington Heights", "type": "str"},
        {"key": "description", "value": "Pass 18 reviewed unified corridor composition; the default and only playable map.", "type": "str"},
        {"key": "chunked", "value": "true", "type": "bool"},
        {"key": "chunk_size", "value": "1024", "type": "int"},
        {"key": "chunk_cols", "value": "16", "type": "int"},
        {"key": "chunk_rows", "value": "12", "type": "int"},
        {"key": "world_w", "value": "16384", "type": "int"},
        {"key": "world_h", "value": "12288", "type": "int"},
        {"key": "interest_radius_chunks", "value": "2", "type": "int"},
        {"key": "map_area_multiplier", "value": "2", "type": "int"},
        {"key": "chunk_cache_limit", "value": "30", "type": "int"},
        {"key": "procedural_buildings", "value": "false", "type": "bool"},
        {"key": "target_player_height_px", "value": "29", "type": "int"},
        {"key": "target_sedan_length_px", "value": "74", "type": "int"},
        {"key": "target_lane_width_px", "value": "38", "type": "int"},
        {"key": "target_sidewalk_width_px", "value": "44", "type": "float"},
        {"key": "bicycle_render_scale", "value": "0.72", "type": "float"},
        {"key": "edge_tunnel_count", "value": "0", "type": "int"},
        {"key": "render_style", "value": "approved_nyc_gta2_callback_v3", "type": "str"},
        {"key": "camera_projection", "value": "orthographic_topdown", "type": "str"},
        {"key": "outdoor_perspective_skew", "value": "0", "type": "float"},
        {"key": "global_map_rotation_deg", "value": "0", "type": "float"},
        {"key": "default_render_mode", "value": "night", "type": "str"},
        {"key": "default_lighting_profile", "value": "night_callback", "type": "str"},
        {"key": "street_lamps_enabled", "value": "true", "type": "bool"},
        {"key": "baked_composition", "value": "true", "type": "bool"},
        {"key": "baked_composition_archive", "value": "assets/environment/approved/map_001_gwb_corridor/composition_tiles_v18.zip", "type": "str"},
        {"key": "baked_composition_world_y", "value": "2048", "type": "int"},
        {"key": "baked_composition_source_scale", "value": "0.5", "type": "float"},
        {"key": "map_build_id", "value": "open_night_v0_8_0_pass18_default_only", "type": "str"},
        {"key": "grid_enabled", "value": "true", "type": "bool"},
        {"key": "grid_cell_size", "value": "32", "type": "int"},
        {"key": "grid_chunk_cache_limit", "value": "30", "type": "int"},
        {"key": "server_region_chunk_cols", "value": "8", "type": "int"},
        {"key": "server_region_chunk_rows", "value": "4", "type": "int"},
        {"key": "scalability_target_players", "value": "1000", "type": "int"},
        {"key": "render_pass", "value": "18", "type": "int"},
        {"key": "road_network_rule", "value": "terrain_aware_hierarchy_with_staggered_locals_v2", "type": "str"},
        {"key": "surface_preservation_rule", "value": "filtered_reference_polygons_with_district_caps_v1", "type": "str"},
        {"key": "building_cosmetic_rule", "value": "district_and_native_footprint_match_v2", "type": "str"},
        {"key": "building_sprite_scale_band", "value": "0.72..1.12", "type": "str"},
        {"key": "building_layer_model", "value": "ground_upper_roof_v1", "type": "str"},
        {"key": "outdoor_level_count", "value": "3", "type": "int"},
        {"key": "default_player_level", "value": "0", "type": "int"},
        {"key": "yellow_center_lines", "value": "false", "type": "bool"},
    ]


def runtime_roads(roads: list[dict]) -> tuple[list[dict], list[dict]]:
    result = []
    points = []
    for road in roads:
        authored_lanes = max(1, int(float(road["lanes"])))
        width = max(38.0, authored_lanes * 38.0 + 10.0) * composition.ROAD_WIDTH_SCALE
        lanes = max(1, authored_lanes - 1)
        while lanes > 1 and width / lanes < 34.0:
            lanes -= 1
        sidewalk = max(28.0, float(road["sidewalk_width"])) * composition.SIDEWALK_SCALE
        rid = road["road_id"]
        result.append({
            "road_id": rid,
            "name": rid.replace("_", " ").title(),
            "base_width": round(width, 2),
            "width": round(width, 2),
            "lanes": lanes,
            "sidewalk_width": round(sidewalk, 2),
            "curb_width": road.get("curb_width", "5"),
            "building_setback": 0,
            "bridge": road.get("bridge", "false"),
            "map_label": "true" if road.get("highway") in {"primary", "secondary"} else "false",
            "highway": road.get("highway", "residential"),
            "level": road.get("level", "0"),
            "walkable": "true",
        })
        for order, (x, y) in enumerate(ROAD_POINTS[rid]):
            points.append({"road_id": rid, "point_order": order, "x": x, "y": y})
    return result, points


def authored_routes() -> dict[str, tuple[list[dict], list[dict], list[dict]]]:
    route_defs = {
        "traffic": [
            ("traffic_fort_lee", "Fort Lee block loop", 86, [(576,2944),(2240,2880),(3200,2880),(3264,3904),(3264,5184),(3264,6144),(2304,6144),(576,6144),(576,4672),(512,3712),(576,2944)]),
            ("traffic_heights", "Washington Heights block loop", 82, [(10752,2752),(12032,2816),(13760,2752),(15424,2816),(15424,3776),(15552,4672),(13824,4608),(12160,4672),(10752,4608),(10752,3584),(10816,2752),(10752,2752)]),
            ("traffic_gwb", "GWB two-way shuttle", 94, [(4608,6144),(10752,6144),(4608,6144)]),
        ],
        "bicycle": [
            ("bike_fort_lee", "Fort Lee neighborhood loop", 48, [(576,7040),(1472,6976),(2368,7040),(2368,8128),(1472,8192),(512,8128),(576,7040)]),
            ("bike_heights", "Washington Heights neighborhood loop", 48, [(10752,6912),(12352,6912),(13824,6912),(13888,7680),(12416,7680),(10816,7680),(10752,6912)]),
        ],
        "npc": [
            ("walk_fort_lee", "Fort Lee sidewalk loop", 54, [(656,3020),(2160,2960),(2220,3630),(620,3580),(656,3020)]),
            ("walk_heights", "Washington Heights sidewalk loop", 54, [(10880,2870),(11920,2940),(12000,3520),(10880,3460),(10880,2870)]),
        ],
    }
    output = {}
    for kind, defs in route_defs.items():
        routes = []
        points = []
        starts = []
        for route_index, (rid, name, speed, coords) in enumerate(defs):
            row = {"route_id": rid, "name": name, "speed": speed, "speed_limit": speed,
                   "loop": "true", "lane_offset": 0, "turn_radius": 42,
                   "axis": "mixed", "direction": "loop"}
            routes.append(row)
            for order, (x, y) in enumerate(coords):
                points.append({"route_id": rid, "point_order": order, "x": x, "y": y})
            count = 3 if kind == "traffic" else 2
            for slot in range(count):
                starts.append({"spawn_id": f"{kind}_{route_index+1:02d}_{slot+1:02d}", "route_id": rid,
                               "start_fraction": round(slot / count, 4), "asset_index": route_index * 3 + slot,
                               "appearance_index": route_index * 3 + slot, "speed_scale": 1.0})
        output[kind] = (routes, points, starts)
    return output


def build_archive() -> None:
    ART_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ART_ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for mode in ("day", "night"):
            for tile in sorted((composition.TILES / mode).glob("tile_*.png")):
                archive.write(tile, f"{mode}/{tile.name}")


def promote_folder(folder: Path, roads: list[dict], crossings: list[dict], surfaces: dict, buildings: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    write_csv(folder / "map.csv", ("key", "value", "type"), map_rows())
    write_csv(folder / "render_contract.csv", ("key", "value", "type"), [
        {"key": "camera_projection", "value": "orthographic_topdown", "type": "str"},
        {"key": "outdoor_perspective_skew", "value": "0", "type": "float"},
        {"key": "baked_composition", "value": "true", "type": "bool"},
        {"key": "render_pass", "value": "18", "type": "int"},
    ])

    road_rows, road_points = runtime_roads(roads)
    write_csv(folder / "roads.csv", ("road_id","name","base_width","width","lanes","sidewalk_width","curb_width","building_setback","bridge","map_label","highway","level","walkable"), road_rows)
    write_csv(folder / "road_points.csv", ("road_id","point_order","x","y"), road_points)

    water_rows = []
    for index, polygon in enumerate(surfaces["water"], 1):
        for order, (x, y) in enumerate(polygon):
            water_rows.append({"polygon_id": f"hudson_{index:02d}", "point_order": order, "x": x, "y": y})
    green_rows = []
    for index, polygon in enumerate(surfaces["green"], 1):
        for order, (x, y) in enumerate(polygon):
            green_rows.append({"polygon_id": f"green_{index:02d}", "point_order": order, "x": x, "y": y})
    write_csv(folder / "water_polygons.csv", ("polygon_id","point_order","x","y"), water_rows)
    write_csv(folder / "green_polygons.csv", ("polygon_id","point_order","x","y"), green_rows)

    # The visible approved sprite includes parapets, facade lips and contact AO.
    # Collision sits just inside that silhouette so players do not snag on art.
    collision_inset = 36.0
    collision_rows = [
        {"id": row["id"], "x": round(float(row["x"]) + collision_inset, 2),
         "y": round(float(row["y"]) + collision_inset, 2),
         "w": round(float(row["w"]) - 2 * collision_inset, 2),
         "h": round(float(row["h"]) - 2 * collision_inset, 2)} for row in buildings
    ]
    write_csv(folder / "buildings.csv", ("id","x","y","w","h"), collision_rows)
    write_csv(folder / "building_visuals.csv", ("building_id","profile","height_px","roof_style","roof_inset","penthouses","shadow_scale"), [
        {"building_id": row["id"], "profile": "brick_midrise", "height_px": 14, "roof_style": "auto", "roof_inset": 0, "penthouses": 1, "shadow_scale": 1} for row in buildings
    ])
    write_csv(folder / "building_sprites.csv", ("building_id","district","building_kind","atlas","cell","world_units_per_source_pixel","render_scale_ratio","scale_status"), [
        {"building_id": row["id"], "district": row["district"], "building_kind": row["building_kind"],
         "atlas": row["cosmetic_atlas"], "cell": row["cosmetic_cell"],
         "world_units_per_source_pixel": row["cosmetic_world_units_per_pixel"],
         "render_scale_ratio": row["cosmetic_render_scale_ratio"], "scale_status": row["cosmetic_scale_status"]} for row in buildings
    ])
    for name in ("building_layers.csv", "building_stairwells.csv", "building_sprite_scale_audit.csv"):
        rows = read_csv(SEMANTIC / name)
        fields = tuple(rows[0].keys()) if rows else ("id",)
        write_csv(folder / name, fields, rows)

    road_by_id = {row["road_id"]: row for row in road_rows}
    points_by_id: dict[str, list[tuple[float, float]]] = {}
    for point in road_points:
        points_by_id.setdefault(point["road_id"], []).append((float(point["x"]), float(point["y"])))

    def segment_distance(px, py, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        den = dx * dx + dy * dy
        if den <= 1e-9:
            return ((px - a[0]) ** 2 + (py - a[1]) ** 2) ** 0.5
        t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / den))
        return ((px - (a[0] + t * dx)) ** 2 + (py - (a[1] + t * dy)) ** 2) ** 0.5

    valid_crossings = []
    for row in crossings:
        px, py = float(row["x"]), float(row["y"])
        if any(min(segment_distance(px, py, a, b) for a, b in zip(points_by_id[rid], points_by_id[rid][1:]))
               <= float(road["width"]) * 0.5 + float(road["curb_width"]) + 6.0
               for rid, road in road_by_id.items()):
            valid_crossings.append(row)

    write_csv(folder / "crosswalks.csv", ("id","road_id","x","y","angle","length","width","stripe_width","stripe_gap","curb_cut_depth","stop_bar_gap","priority"), [
        {"id": row["id"], "road_id": row.get("road_id", ""), "x": row["x"], "y": row["y"], "angle": row["angle"],
         "length": row["length"], "width": row["width"], "stripe_width": row.get("stripe_width", 5),
         "stripe_gap": row.get("stripe_gap", 10), "curb_cut_depth": 16,
         "stop_bar_gap": row.get("stop_bar_gap", 14), "priority": "authored_intersection"} for row in valid_crossings
    ])

    write_csv(folder / "points.csv", ("group","id","x","y"), [
        {"group":"spawn","id":0,"x":4100,"y":6320}, {"group":"spawn","id":1,"x":11200,"y":6320},
        {"group":"login_spawn","id":0,"x":4100,"y":6320}, {"group":"login_spawn","id":1,"x":11200,"y":6320},
        {"group":"supplier","id":0,"x":3900,"y":6420}, {"group":"customer","id":0,"x":11400,"y":6420},
    ])
    write_csv(folder / "districts.csv", ("name","x","y"), [
        {"name":"FORT LEE","x":2400,"y":5600}, {"name":"GEORGE WASHINGTON BRIDGE","x":7680,"y":6144},
        {"name":"WASHINGTON HEIGHTS","x":13200,"y":5600},
    ])
    write_csv(folder / "landmarks.csv", ("id","name","kind","x","y"), [
        {"id":"gwb","name":"George Washington Bridge","kind":"bridge","x":7680,"y":6144},
        {"id":"fort_lee","name":"Fort Lee","kind":"district","x":2400,"y":5600},
        {"id":"washington_heights","name":"Washington Heights","kind":"district","x":13200,"y":5600},
    ])

    routes = authored_routes()
    for kind, meta_name, points_name in (("traffic","traffic_routes.csv","traffic_route_points.csv"),
                                          ("bicycle","bicycle_routes.csv","bicycle_routes_points.csv"),
                                          ("npc","npc_routes.csv","npc_routes_points.csv")):
        route_rows, point_rows, starts = routes[kind]
        fields = ("route_id","name","speed_limit","loop","lane_offset","turn_radius","axis","direction") if kind == "traffic" else ("route_id","name","speed","loop","lane_offset","turn_radius","axis","direction")
        write_csv(folder / meta_name, fields, route_rows)
        write_csv(folder / points_name, ("route_id","point_order","x","y"), point_rows)
        write_csv(folder / f"{kind}_starts.csv", ("spawn_id","route_id","start_fraction","asset_index","appearance_index","speed_scale"), starts)

    empty_tables = {
        "traffic_route_signals.csv": ("route_id","waypoint_index","phase"),
        "traffic_signals.csv": ("id","x","y","phase","orientation"),
        "parked_vehicles.csv": ("id","x","y","angle"),
        "parked_bicycles.csv": ("id","x","y","angle"),
        "bike_lanes.csv": ("lane_id","name","width","protected","direction"),
        "bike_lane_points.csv": ("lane_id","point_order","x","y"),
        "street_props.csv": ("id","kind","x","y","angle","scale","district","placement_rule"),
        "parking_regions.csv": ("id","x","y","w","h"),
        "transit_routes.csv": ("route_id","mode","name"),
        "transit_route_points.csv": ("route_id","point_order","x","y"),
        "transit_stops.csv": ("stop_id","route_id","name","x","y"),
    }
    for filename, fields in empty_tables.items():
        write_csv(folder / filename, fields, [])
    write_csv(folder / "sidewalks.csv", ("sidewalk_id","road_id","side","width"), [
        {"sidewalk_id": f"{road['road_id']}_{side}", "road_id": road["road_id"],
         "side": side, "width": road["sidewalk_width"]}
        for road in road_rows for side in ("left", "right")
    ])
    interior_specs = (
        ("starter_apartment", "Starter Apartment", "apartment"),
        ("corner_shop", "Bridge Corner Store", "shop"),
        ("night_diner", "Open Night Diner", "diner"),
        ("pharmacy", "Hudson Pharmacy", "shop"),
        ("laundromat", "24 Hour Laundromat", "shop"),
        ("pawn_shop", "Pawn & Exchange", "shop"),
        ("garage", "Riverside Garage", "garage"),
        ("nightclub", "After Hours Club", "club"),
        ("warehouse_office", "Warehouse Office", "office"),
        ("rooftop_loft", "Washington Heights Loft", "apartment"),
    )
    interior_buildings = collision_rows[:5] + collision_rows[48:53]
    write_csv(folder / "interiors.csv", ("id","name","kind","entry_x","entry_y","building_id","door_hint"), [
        {"id": spec[0], "name": spec[1], "kind": spec[2],
         "entry_x": round(float(building["x"]) - 18.0, 2),
         "entry_y": round(float(building["y"]) + float(building["h"]) * 0.5, 2),
         "building_id": building["id"], "door_hint": "west_collision_frontage"}
        for spec, building in zip(interior_specs, interior_buildings)
    ])
    write_csv(folder / "level_connectors.csv", ("connector_id","kind","from_level","to_level","x0","y0","x1","y1","width"), [
        {"connector_id":"gwb_fort_lee_ramp","kind":"ramp","from_level":0,"to_level":1,
         "x0":4384,"y0":6144,"x1":4608,"y1":6144,"width":96},
        {"connector_id":"gwb_washington_heights_ramp","kind":"ramp","from_level":0,"to_level":1,
         "x0":10976,"y0":6144,"x1":10752,"y1":6144,"width":96},
    ])
    write_csv(folder / "levels.csv", ("level_id","name","z_order","walkable"), [
        {"level_id":0,"name":"Ground","z_order":0,"walkable":"true"},
        {"level_id":1,"name":"Bridge deck / upper","z_order":1,"walkable":"true"},
        {"level_id":2,"name":"Roof","z_order":2,"walkable":"true"},
    ])


def main() -> None:
    global ROAD_POINTS
    roads, ROAD_POINTS, crossings = composition.authored_block_network()
    buildings = read_csv(SEMANTIC / "iterated_buildings.csv")
    if len(buildings) != 95:
        raise RuntimeError("Pass 18 semantic output is missing; rebuild the unified composition first")
    surfaces = composition.authored_surfaces()
    build_archive()
    for folder in MAP_DIRS:
        promote_folder(folder, roads, crossings, surfaces, buildings)
    print(f"PROMOTED release=0.8.0 maps={len(MAP_DIRS)} roads={len(roads)} crossings={len(crossings)} buildings={len(buildings)} archive={ART_ARCHIVE.stat().st_size}")


ROAD_POINTS: dict[str, list[tuple[float, float]]] = {}


if __name__ == "__main__":
    main()
