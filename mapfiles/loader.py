from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from .grid import try_load_compiled_grid, chunk_label

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = ROOT / "data"


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(r) for r in csv.DictReader(handle)]


def _bool(value: Any, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _typed(value: str, type_name: str):
    t = (type_name or "str").strip().lower()
    if t == "bool":
        return _bool(value)
    if t == "int":
        return _int(value)
    if t == "float":
        return _float(value)
    return str(value)


def _group_points(rows: list[dict[str, str]], id_field: str) -> dict[str, list[list[float]]]:
    grouped: dict[str, list[tuple[int, list[float]]]] = defaultdict(list)
    for row in rows:
        rid = str(row.get(id_field, "")).strip()
        if not rid:
            continue
        grouped[rid].append((_int(row.get("point_order")), [_float(row.get("x")), _float(row.get("y"))]))
    return {rid: [point for _, point in sorted(values, key=lambda item: item[0])] for rid, values in grouped.items()}


def _load_routes(folder: Path, stem: str, *, traffic: bool = False) -> list[dict]:
    meta_rows = _rows(folder / f"{stem}.csv")
    point_name = "traffic_route_points.csv" if traffic else f"{stem}_points.csv"
    points = _group_points(_rows(folder / point_name), "route_id")
    result = []
    for row in meta_rows:
        rid = str(row.get("route_id", "")).strip()
        if not rid:
            continue
        route = {
            "id": rid,
            "name": str(row.get("name", "")).strip(),
            "waypoints": points.get(rid, []),
        }
        if traffic:
            route["speed_limit"] = _float(row.get("speed_limit"), 100.0)
            route["signals"] = {}
            route["loop"] = _bool(row.get("loop"), True)
        else:
            route["speed"] = _float(row.get("speed"), 50.0)
            route["loop"] = _bool(row.get("loop"), True)
        # v2.1 fixed-flow metadata is shared by traffic, bicycle, and pedestrian
        # routes.  Keeping it in CSV lets us tune throughput without engine edits.
        if row.get("lane_offset") not in {None, ""}:
            route["lane_offset"] = _float(row.get("lane_offset"), 0.0)
        if row.get("turn_radius") not in {None, ""}:
            route["turn_radius"] = max(0.0, _float(row.get("turn_radius"), 0.0))
        route["axis"] = str(row.get("axis", "mixed")).strip().lower() or "mixed"
        route["direction"] = str(row.get("direction", "loop")).strip().lower() or "loop"
        result.append(route)
    if traffic:
        by_id = {r["id"]: r for r in result}
        for row in _rows(folder / "traffic_route_signals.csv"):
            route = by_id.get(str(row.get("route_id", "")).strip())
            if route is not None:
                route["signals"][str(_int(row.get("waypoint_index")))] = _int(row.get("phase"))
    return result


def _load_ai_starts(folder: Path, filename: str) -> list[dict]:
    """Load fixed AI route/start assignments.

    Runtime AI never rolls a route or start position.  Every moving traffic car,
    cyclist, and pedestrian begins from one authored row in these CSV tables.
    """
    result: list[dict] = []
    for index, row in enumerate(_rows(folder / filename)):
        route_id = str(row.get("route_id", "")).strip()
        if not route_id:
            continue
        result.append({
            "id": str(row.get("spawn_id", f"slot{index+1:03d}")).strip() or f"slot{index+1:03d}",
            "route_id": route_id,
            "start_fraction": _float(row.get("start_fraction"), 0.0),
            "asset_index": max(0, _int(row.get("asset_index"), index)),
            "appearance_index": max(0, _int(row.get("appearance_index"), index)),
            "speed_scale": max(0.1, _float(row.get("speed_scale"), 1.0)),
        })
    return result


def load_map_folder(folder: Path, *, attach_grid: bool = True) -> dict:
    folder = Path(folder)
    cfg: dict[str, Any] = {}
    for row in _rows(folder / "map.csv"):
        key = str(row.get("key", "")).strip()
        if key:
            cfg[key] = _typed(str(row.get("value", "")), str(row.get("type", "str")))
    if not cfg.get("id"):
        raise ValueError(f"{folder}: map.csv must define an id")

    cfg["data_folder"] = folder.name
    cfg["geo_bounds"] = {str(r.get("key", "")): _float(r.get("value")) for r in _rows(folder / "geo_bounds.csv") if r.get("key")}

    # Viewer/render contract is intentionally separate from authoritative geometry.
    # Values also remain mirrored in map.csv for older clients.
    cfg["render_contract"] = {}
    for row in _rows(folder / "render_contract.csv"):
        key = str(row.get("key", "")).strip()
        if not key:
            continue
        value = _typed(str(row.get("value", "")), str(row.get("type", "str")))
        cfg["render_contract"][key] = value
        cfg.setdefault(key, value)

    points = _rows(folder / "points.csv")
    cfg["spawns"] = []
    cfg["login_spawns"] = []
    for group, out_key in (("spawn", "spawns"), ("login_spawn", "login_spawns")):
        selected = [(str(r.get("id", "")), [_float(r.get("x")), _float(r.get("y"))]) for r in points if str(r.get("group", "")) == group]
        selected.sort(key=lambda item: _int(item[0]))
        cfg[out_key] = [p for _, p in selected]
    for group, key in (("supplier", "supplier_pos"), ("customer", "customer_pos")):
        row = next((r for r in points if str(r.get("group", "")) == group), None)
        cfg[key] = [_float(row.get("x")), _float(row.get("y"))] if row else [0.0, 0.0]

    cfg["districts"] = [{"name": str(r.get("name", "")), "pos": [_float(r.get("x")), _float(r.get("y"))]} for r in _rows(folder / "districts.csv")]
    cfg["landmarks"] = [{"id": str(r.get("id", "")), "name": str(r.get("name", "")), "kind": str(r.get("kind", "landmark")), "pos": [_float(r.get("x")), _float(r.get("y"))]} for r in _rows(folder / "landmarks.csv")]
    cfg["interiors"] = [
        {
            "id": str(r.get("id", "")),
            "name": str(r.get("name", "")),
            "kind": str(r.get("kind", "interior")),
            "entry": [_float(r.get("entry_x")), _float(r.get("entry_y"))],
            "building_id": str(r.get("building_id", "")).strip(),
            "door_hint": str(r.get("door_hint", "")).strip(),
        }
        for r in _rows(folder / "interiors.csv")
    ]
    cfg["parked_vehicle_spawns"] = [[_float(r.get("x")), _float(r.get("y")), _float(r.get("angle"))] for r in _rows(folder / "parked_vehicles.csv")]
    cfg["parked_bicycle_spawns"] = [[_float(r.get("x")), _float(r.get("y")), _float(r.get("angle"))] for r in _rows(folder / "parked_bicycles.csv")]
    building_rows = _rows(folder / "buildings.csv")
    cfg["buildings"] = [[_int(r.get("x")), _int(r.get("y")), _int(r.get("w")), _int(r.get("h"))] for r in building_rows]
    cfg["building_ids"] = [str(r.get("id", i)).strip() or str(i) for i, r in enumerate(building_rows)]
    cfg["building_id_by_rect"] = {tuple(rect): bid for rect, bid in zip(cfg["buildings"], cfg["building_ids"])}
    cfg["building_visuals"] = {}
    for row in _rows(folder / "building_visuals.csv"):
        bid = str(row.get("building_id", "")).strip()
        if not bid:
            continue
        cfg["building_visuals"][bid] = {
            "profile": str(row.get("profile", "brick_midrise")).strip() or "brick_midrise",
            "height_px": max(6.0, _float(row.get("height_px"), 14.0)),
            "roof_style": str(row.get("roof_style", "auto")).strip() or "auto",
            "roof_inset": max(0.0, _float(row.get("roof_inset"), 0.0)),
            "penthouses": max(0, _int(row.get("penthouses"), 1)),
            "shadow_scale": max(0.4, _float(row.get("shadow_scale"), 1.0)),
        }
    cfg["building_sprites"] = {}
    for row in _rows(folder / "building_sprites.csv"):
        bid = str(row.get("building_id", "")).strip()
        if not bid:
            continue
        cfg["building_sprites"][bid] = {
            "district": str(row.get("district", "")).strip(),
            "building_kind": str(row.get("building_kind", "")).strip(),
            "atlas": str(row.get("atlas", "")).strip(),
            "cell": max(0, _int(row.get("cell"), 0)),
            "world_units_per_source_pixel": max(0.01, _float(row.get("world_units_per_source_pixel"), 2.0)),
            "render_scale_ratio": max(0.01, _float(row.get("render_scale_ratio"), 1.0)),
            "scale_status": str(row.get("scale_status", "")).strip(),
        }
    cfg["building_layers"] = [{
        "building_id": str(r.get("building_id", "")).strip(),
        "level_id": _int(r.get("level_id"), 0),
        "layer_kind": str(r.get("layer_kind", "")).strip(),
        "z_order": _int(r.get("z_order"), 0),
        "walkable": _bool(r.get("walkable"), False),
        "visual_role": str(r.get("visual_role", "")).strip(),
        "transition_policy": str(r.get("transition_policy", "")).strip(),
    } for r in _rows(folder / "building_layers.csv") if str(r.get("building_id", "")).strip()]
    cfg["building_stairwells"] = [{
        "id": str(r.get("stairwell_id", "")).strip(),
        "building_id": str(r.get("building_id", "")).strip(),
        "kind": str(r.get("kind", "exterior_fire_stair")).strip(),
        "side": str(r.get("side", "")).strip(),
        "pos": [_float(r.get("x")), _float(r.get("y"))],
        "from_level": _int(r.get("from_level"), 0),
        "intermediate_level": _int(r.get("intermediate_level"), 1),
        "to_level": _int(r.get("to_level"), 2),
        "interaction_keys": str(r.get("interaction_keys", "")).strip(),
        "transition_mode": str(r.get("transition_mode", "")).strip(),
    } for r in _rows(folder / "building_stairwells.csv") if str(r.get("stairwell_id", "")).strip()]

    road_points = _group_points(_rows(folder / "road_points.csv"), "road_id")
    cfg["roads"] = []
    for row in _rows(folder / "roads.csv"):
        rid = str(row.get("road_id", "")).strip()
        if not rid:
            continue
        cfg["roads"].append({
            "id": rid,
            "name": str(row.get("name", "")),
            "width": _float(row.get("width"), 80.0),
            "lanes": max(1, _int(row.get("lanes"), 2)),
            "sidewalk_width": max(0.0, _float(row.get("sidewalk_width"), 28.0)),
            "curb_width": max(0.0, _float(row.get("curb_width"), 5.0)),
            "building_setback": max(0.0, _float(row.get("building_setback"), 12.0)),
            "bridge": _bool(row.get("bridge"), False),
            "map_label": _bool(row.get("map_label"), False),
            "highway": str(row.get("highway", "")).strip(),
            "level": _int(row.get("level"), 0),
            "walkable": _bool(row.get("walkable"), True),
            "points": road_points.get(rid, []),
        })

    cfg["levels"] = [{
        "id": _int(r.get("level_id"), 0), "name": str(r.get("name", "Level")),
        "z_order": _int(r.get("z_order"), _int(r.get("level_id"), 0)), "walkable": _bool(r.get("walkable"), True)
    } for r in _rows(folder / "levels.csv")]
    if not cfg["levels"]:
        cfg["levels"] = [{"id": 0, "name": "Ground", "z_order": 0, "walkable": True}]
    cfg["level_connectors"] = [{
        "id": str(r.get("connector_id", "")), "kind": str(r.get("kind", "ramp")),
        "from_level": _int(r.get("from_level"), 0), "to_level": _int(r.get("to_level"), 1),
        "start": [_float(r.get("x0")), _float(r.get("y0"))], "end": [_float(r.get("x1")), _float(r.get("y1"))],
        "width": max(24.0, _float(r.get("width"), 80.0))
    } for r in _rows(folder / "level_connectors.csv") if str(r.get("connector_id", "")).strip()]

    water = _group_points(_rows(folder / "water_polygons.csv"), "polygon_id")
    cfg["water_polygons"] = list(water.values())
    green = _group_points(_rows(folder / "green_polygons.csv"), "polygon_id")
    cfg["green_polygons"] = list(green.values())
    cfg["npc_routes"] = _load_routes(folder, "npc_routes")
    cfg["bicycle_routes"] = _load_routes(folder, "bicycle_routes")
    cfg["traffic_routes"] = _load_routes(folder, "traffic_routes", traffic=True)
    cfg["traffic_starts"] = _load_ai_starts(folder, "traffic_starts.csv")
    cfg["bicycle_starts"] = _load_ai_starts(folder, "bicycle_starts.csv")
    cfg["npc_starts"] = _load_ai_starts(folder, "npc_starts.csv")
    cfg["traffic_signals"] = [{
        "id": str(r.get("id", "")),
        "pos": [_float(r.get("x")), _float(r.get("y"))],
        "phase": _int(r.get("phase")),
        "orientation": str(r.get("orientation", "h")),
    } for r in _rows(folder / "traffic_signals.csv")]

    # Crosswalks are first-class authored map geometry in v1.2.2. They are
    # deliberately independent of traffic-light sprites so zebra placement,
    # curb cuts, and stop bars remain stable even when signal art changes.
    cfg["crosswalks"] = [{
        "id": str(r.get("id", "")).strip(),
        "road_id": str(r.get("road_id", "")).strip(),
        "pos": [_float(r.get("x")), _float(r.get("y"))],
        "angle": _float(r.get("angle"), 0.0),
        "length": max(24.0, _float(r.get("length"), 96.0)),
        "width": max(18.0, _float(r.get("width"), 38.0)),
        "stripe_width": max(3.0, _float(r.get("stripe_width"), 7.0)),
        "stripe_gap": max(3.0, _float(r.get("stripe_gap"), 7.0)),
        "curb_cut_depth": max(0.0, _float(r.get("curb_cut_depth"), 16.0)),
        "stop_bar_gap": max(0.0, _float(r.get("stop_bar_gap"), 12.0)),
        "priority": str(r.get("priority", "normal")).strip() or "normal",
    } for r in _rows(folder / "crosswalks.csv") if str(r.get("id", "")).strip()]

    # Visual street furniture is authored map data rather than runtime randomness.
    # This keeps the approved-art streetscape deterministic and editable in CSV.
    cfg["street_props"] = [{
        "id": str(r.get("id", "")).strip(),
        "kind": str(r.get("kind", "")).strip(),
        "pos": [_float(r.get("x")), _float(r.get("y"))],
        "scale": max(0.25, _float(r.get("scale"), 1.0)),
        "rotation": _float(r.get("rotation"), 0.0),
    } for r in _rows(folder / "street_props.csv") if str(r.get("kind", "")).strip()]

    lane_points = _group_points(_rows(folder / "bike_lane_points.csv"), "lane_id")
    # Open Night screenshot-reference semantic overlays. These are optional and
    # do not affect collision until a gameplay system explicitly consumes them.
    transit_points = _group_points(_rows(folder / "transit_route_points.csv"), "route_id")
    cfg["transit_routes"] = [{
        "id": str(r.get("route_id", "")).strip(),
        "mode": str(r.get("mode", "transit")).strip() or "transit",
        "name": str(r.get("name", "")).strip(),
        "points": transit_points.get(str(r.get("route_id", "")).strip(), []),
    } for r in _rows(folder / "transit_routes.csv") if str(r.get("route_id", "")).strip()]
    cfg["transit_stops"] = [{
        "id": str(r.get("stop_id", "")).strip(), "route_id": str(r.get("route_id", "")).strip(),
        "name": str(r.get("name", "")).strip(), "pos": [_float(r.get("x")), _float(r.get("y"))]
    } for r in _rows(folder / "transit_stops.csv") if str(r.get("stop_id", "")).strip()]

    cfg["bike_lanes"] = []
    for row in _rows(folder / "bike_lanes.csv"):
        lid = str(row.get("lane_id", "")).strip()
        if not lid:
            continue
        cfg["bike_lanes"].append({
            "id": lid,
            "name": str(row.get("name", "")),
            "width": _float(row.get("width"), 18.0),
            "protected": _bool(row.get("protected"), False),
            "direction": str(row.get("direction", "both")),
            "points": lane_points.get(lid, []),
        })

    # Derived fields are generated centrally so all engine systems agree.
    chunk_size = max(64, _int(cfg.get("chunk_size"), 1024))
    cfg["chunk_size"] = chunk_size
    cfg["world_w"] = max(chunk_size, _int(cfg.get("world_w"), chunk_size))
    cfg["world_h"] = max(chunk_size, _int(cfg.get("world_h"), chunk_size))
    cfg["chunk_cols"] = max(1, _int(cfg.get("chunk_cols"), (cfg["world_w"] + chunk_size - 1) // chunk_size))
    cfg["chunk_rows"] = max(1, _int(cfg.get("chunk_rows"), (cfg["world_h"] + chunk_size - 1) // chunk_size))
    cfg.setdefault("chunked", True)
    cfg.setdefault("interest_radius_chunks", 2)
    cfg["network_zone_size"] = max(chunk_size, _int(cfg.get("network_zone_size"), chunk_size * 3))
    cfg["network_zone_radius"] = 1
    cfg.setdefault("chunk_cache_limit", 24)
    cfg.setdefault("procedural_buildings", True)
    cfg["grid_cell_size"] = max(8, _int(cfg.get("grid_cell_size"), 32))
    cfg["grid_enabled"] = _bool(cfg.get("grid_enabled"), True)
    if attach_grid and cfg["grid_enabled"]:
        grid = try_load_compiled_grid(folder, cache_limit=max(8, _int(cfg.get("grid_chunk_cache_limit"), 20)))
        if grid is not None:
            cfg["_grid"] = grid
            cfg["grid_compiled"] = True
        else:
            cfg["grid_compiled"] = False
    else:
        cfg["grid_compiled"] = False
    return cfg


def _point_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx, vy = bx - ax, by - ay
    vv = vx * vx + vy * vy
    if vv <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / vv))
    qx, qy = ax + t * vx, ay + t * vy
    return math.hypot(px - qx, py - qy)


def _segment_intersects_rect(ax: float, ay: float, bx: float, by: float, rect: tuple[float, float, float, float]) -> bool:
    x, y, w, h = rect
    dx, dy = bx - ax, by - ay
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, ax - x), (dx, x + w - ax), (-dy, ay - y), (dy, y + h - ay)):
        if abs(p) <= 1e-12:
            if q < 0.0:
                return False
            continue
        t = q / p
        if p < 0.0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return True


def _segment_rect_distance(a, b, rect: tuple[float, float, float, float]) -> float:
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    x, y, w, h = rect
    if _segment_intersects_rect(ax, ay, bx, by, rect):
        return 0.0
    def point_rect_distance(px: float, py: float) -> float:
        dx = max(x - px, 0.0, px - (x + w))
        dy = max(y - py, 0.0, py - (y + h))
        return math.hypot(dx, dy)
    corners = ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
    return min(
        point_rect_distance(ax, ay),
        point_rect_distance(bx, by),
        *(_point_segment_distance(cx, cy, ax, ay, bx, by) for cx, cy in corners),
    )


def validate_map(cfg: dict) -> list[str]:
    errors: list[str] = []
    world_w = float(cfg.get("world_w", 0))
    world_h = float(cfg.get("world_h", 0))
    if world_w <= 0 or world_h <= 0:
        errors.append("world_w/world_h must be positive")

    chunk_size = max(1, int(cfg.get("chunk_size", 1024)))
    def chunk_ref(x: float, y: float) -> str:
        cx = max(0, int(float(x) // chunk_size)); cy = max(0, int(float(y) // chunk_size))
        lx = int(float(x) - cx * chunk_size); ly = int(float(y) - cy * chunk_size)
        return f"[{chunk_label(cx, cy)} @ ({lx},{ly})]"

    def check_point(label: str, point) -> None:
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError, IndexError):
            errors.append(f"{label}: invalid point {point!r}")
            return
        if not (0 <= x <= world_w and 0 <= y <= world_h):
            errors.append(f"{label} {chunk_ref(x,y)}: point ({x:g},{y:g}) outside world {world_w:g}x{world_h:g}")

    for i, p in enumerate(cfg.get("spawns", [])): check_point(f"spawn[{i}]", p)
    for i, p in enumerate(cfg.get("login_spawns", [])): check_point(f"login_spawn[{i}]", p)
    check_point("supplier", cfg.get("supplier_pos", [None, None]))
    check_point("customer", cfg.get("customer_pos", [None, None]))

    for collection, point_key, min_points in (("roads", "points", 2), ("traffic_routes", "waypoints", 2), ("npc_routes", "waypoints", 2), ("bicycle_routes", "waypoints", 2), ("bike_lanes", "points", 2)):
        seen = set()
        for item in cfg.get(collection, []):
            iid = str(item.get("id", ""))
            if not iid:
                errors.append(f"{collection}: item missing id")
            elif iid in seen:
                errors.append(f"{collection}: duplicate id {iid}")
            seen.add(iid)
            pts = item.get(point_key, [])
            if len(pts) < min_points:
                errors.append(f"{collection}:{iid}: needs at least {min_points} points")
            for idx, p in enumerate(pts): check_point(f"{collection}:{iid}[{idx}]", p)

    # Fixed AI assignments are the v2.1 source of truth for route/start choice.
    for starts_key, routes_key in (("traffic_starts", "traffic_routes"), ("bicycle_starts", "bicycle_routes"), ("npc_starts", "npc_routes")):
        route_ids = {str(r.get("id", "")) for r in cfg.get(routes_key, [])}
        seen_start_ids: set[str] = set()
        for idx, start in enumerate(cfg.get(starts_key, [])):
            sid = str(start.get("id", ""))
            rid = str(start.get("route_id", ""))
            if not sid:
                errors.append(f"{starts_key}[{idx}]: missing spawn_id")
            elif sid in seen_start_ids:
                errors.append(f"{starts_key}: duplicate spawn_id {sid}")
            seen_start_ids.add(sid)
            if rid not in route_ids:
                errors.append(f"{starts_key}:{sid}: unknown route_id {rid}")
            frac = float(start.get("start_fraction", -1.0))
            if not (0.0 <= frac < 1.0):
                errors.append(f"{starts_key}:{sid}: start_fraction must be in [0,1)")

    # Gameplay-scale invariants: maps may be geographically liberal, but visible
    # road/sidewalk proportions must remain compatible with players and vehicles.
    for road in cfg.get("roads", []):
        rid = str(road.get("id", "road"))
        lanes = max(1, int(road.get("lanes", 2)))
        lane_width = float(road.get("width", 0.0)) / lanes
        highway = str(road.get("highway", ""))
        pts = road.get("points", []) or []
        ref = chunk_ref(float(pts[0][0]), float(pts[0][1])) if pts else ""
        if highway not in {"motorway", "motorway_link", "trunk", "trunk_link"} and lane_width < 34.0:
            errors.append(f"roads:{rid} {ref}: lane width {lane_width:.1f}px is too narrow for the approved vehicle scale")
        if highway not in {"motorway", "motorway_link", "trunk", "trunk_link"} and float(road.get("sidewalk_width", 0.0)) < 20.0:
            errors.append(f"roads:{rid} {ref}: sidewalk width must be at least 20px on ordinary streets")

    # Buildings must remain outside the complete authored street corridor. This
    # protects the explicit asphalt -> curb -> furnishing strip -> sidewalk ->
    # frontage separation that defines the approved gameplay scale.
    for bidx, raw in enumerate(cfg.get("buildings", [])):
        try:
            bx, by, bw, bh = map(float, raw[:4])
        except (TypeError, ValueError, IndexError):
            errors.append(f"building[{bidx}]: invalid rectangle {raw!r}")
            continue
        if bw <= 0 or bh <= 0 or bx < 0 or by < 0 or bx + bw > world_w or by + bh > world_h:
            errors.append(f"building[{bidx}] {chunk_ref(bx+bw*0.5,by+bh*0.5)}: rectangle outside world or non-positive")
            continue
        for road in cfg.get("roads", []):
            points = road.get("points", [])
            if len(points) < 2:
                continue
            sidewalk = float(road.get("sidewalk_width", 0.0))
            furnishing = 10.0 if sidewalk >= 20.0 else 0.0
            frontage = 8.0 if sidewalk >= 20.0 else 0.0
            clearance = (float(road.get("width", 0.0)) * 0.5 + float(road.get("curb_width", 0.0))
                         + furnishing + sidewalk + frontage + float(road.get("building_setback", 0.0)))
            distance = min(_segment_rect_distance(a, b, (bx, by, bw, bh)) for a, b in zip(points, points[1:]))
            if distance + 0.01 < clearance:
                errors.append(f"building[{bidx}] {chunk_ref(bx+bw*0.5,by+bh*0.5)} intrudes into road corridor {road.get('id','?')} ({distance:.1f}px < {clearance:.1f}px)")

    # Crosswalk geometry must sit on a drivable road and be wide enough to span
    # the carriageway. This catches decorative zebras drifting away from the
    # authoritative street mesh.
    crosswalk_ids = set()
    for idx, crossing in enumerate(cfg.get("crosswalks", [])):
        cid = str(crossing.get("id", ""))
        if not cid:
            errors.append(f"crosswalk[{idx}]: missing id")
        elif cid in crosswalk_ids:
            errors.append(f"crosswalk[{idx}]: duplicate id {cid}")
        crosswalk_ids.add(cid)
        check_point(f"crosswalk[{idx}]", crossing.get("pos", [None, None]))
        length = float(crossing.get("length", 0.0))
        width = float(crossing.get("width", 0.0))
        if length < 24 or width < 18:
            errors.append(f"crosswalk:{cid} {chunk_ref(float(crossing.get('pos',[0,0])[0]), float(crossing.get('pos',[0,0])[1]))}: invalid dimensions {length:g}x{width:g}")
        try:
            px, py = map(float, crossing.get("pos", [0, 0]))
        except (TypeError, ValueError):
            continue
        candidates=[]
        for road in cfg.get("roads", []):
            highway=str(road.get("highway", ""))
            if highway in {"footway", "path", "cycleway", "steps", "pedestrian"}:
                continue
            pts=road.get("points", [])
            if len(pts)<2:
                continue
            d=min(_point_segment_distance(px, py, float(a[0]), float(a[1]), float(b[0]), float(b[1])) for a,b in zip(pts,pts[1:]))
            half=float(road.get("width",0.0))*0.5
            if d <= half + max(8.0, float(road.get("curb_width",0.0)) + 6.0):
                candidates.append((d, road))
        if not candidates:
            errors.append(f"crosswalk:{cid} {chunk_ref(px,py)}: does not intersect a drivable road")
        else:
            _, nearest=min(candidates, key=lambda item:item[0])
            minimum=float(nearest.get("width",0.0)) + 2.0*float(nearest.get("curb_width",0.0))
            if length + 8.0 < minimum:
                errors.append(f"crosswalk:{cid} {chunk_ref(px,py)}: length {length:.1f}px is too short for {nearest.get('id','road')} ({minimum:.1f}px curb-to-curb)")

    for idx, prop in enumerate(cfg.get("street_props", [])):
        check_point(f"street_prop[{idx}]", prop.get("pos", [None, None]))
        if str(prop.get("kind", "")) not in {"street_tree", "curved_streetlamp", "fire_hydrant", "bicycle_rack", "traffic_signal", "edge_tunnel"}:
            errors.append(f"street_prop[{idx}]: unsupported kind {prop.get('kind')!r}")

    for idx, poly in enumerate(cfg.get("water_polygons", [])):
        if len(poly) < 3:
            errors.append(f"water polygon {idx}: needs at least 3 points")
        for j, p in enumerate(poly): check_point(f"water[{idx}][{j}]", p)
    return errors


def load_all_maps(data_root: Path = DEFAULT_DATA_ROOT) -> dict[str, dict]:
    maps: dict[str, dict] = {}
    if not data_root.exists():
        return maps
    for folder in sorted(p for p in data_root.iterdir() if p.is_dir()):
        try:
            cfg = load_map_folder(folder)
        except (OSError, ValueError, csv.Error):
            continue
        maps[str(cfg["id"]).lower()] = cfg
    return maps
