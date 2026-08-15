from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

from character_catalog import default_character as _default_character, normalize_character as _normalize_character

PLAYER_RADIUS = 18
PLAYER_SPEED = 240.0
SERVER_TICK_RATE = 30
SNAPSHOT_RATE = 20
INTERACT_DISTANCE = 78.0

BUY_PRICE = 25
SELL_PRICE = 40
STARTING_CASH = 200
MAX_PACKAGES = 12

DEFAULT_MAP_ID = "map_001_gwb_corridor"

# ---------------------------------------------------------------------------
# Large-world / chunk configuration
# ---------------------------------------------------------------------------
CHUNK_SIZE = 1024
NETWORK_INTEREST_RADIUS_CHUNKS = 2
CHUNK_CACHE_LIMIT = 24

# Original modular top-down character system. These are deliberately small
# palette/style indices rather than asset filenames so the renderer can be
# replaced later without changing persistence/network data.
CHARACTER_DEFAULT = _default_character()

SKIN_TONES = [
    [246, 211, 181], [224, 179, 142], [196, 145, 105], [146, 96, 68], [92, 58, 44],
]
HAIR_COLORS = [
    [35, 29, 26], [73, 49, 34], [126, 82, 43], [186, 147, 86], [122, 122, 118], [146, 46, 38],
]
TOP_COLORS = [
    [45, 48, 52], [60, 90, 124], [132, 49, 54], [53, 105, 73],
    [147, 111, 45], [112, 69, 128], [193, 191, 177], [49, 112, 122],
]
PANTS_COLORS = [
    [34, 38, 45], [55, 68, 86], [72, 62, 55], [47, 70, 55], [92, 91, 87], [26, 27, 29],
]
HAIR_STYLE_NAMES = ["Shaved", "Short", "Messy", "Side Part", "Long"]


def normalize_character(raw: dict | None) -> dict:
    return _normalize_character(raw)


# ---------------------------------------------------------------------------
# Data-driven maps
# ---------------------------------------------------------------------------
# World geometry is intentionally not authored in this module. CSV mapfiles are
# loaded from mapfiles/data so road/NPC/traffic/bicycle tweaks never require an
# engine-code edit.
from mapfiles import load_all_maps as _load_all_csv_maps
from mapfiles.grid import BUILDING as GRID_BUILDING, WATER as GRID_WATER, ROAD as GRID_ROAD, BRIDGE as GRID_BRIDGE


def _load_map_sources() -> dict[str, dict]:
    # v0.8.0 deliberately exposes one curated authoritative map. Extra folders
    # may exist in developer worktrees, but they can never become playable maps.
    loaded = _load_all_csv_maps()
    selected = loaded.get(DEFAULT_MAP_ID)
    return {DEFAULT_MAP_ID: selected} if selected is not None else {}


def reload_maps() -> dict[str, dict]:
    fresh = _load_map_sources()
    if fresh:
        MAPS.clear()
        MAPS.update(fresh)
    _CHUNK_BUILDING_CACHE.clear() if "_CHUNK_BUILDING_CACHE" in globals() else None
    return MAPS


MAPS: dict[str, dict] = _load_map_sources()
if not MAPS:
    # Tiny emergency fallback for diagnostics only. Normal development should
    # always have the CSV GWB/Fort Lee/upper-Manhattan region present.
    MAPS = {
        DEFAULT_MAP_ID: {
            "id": DEFAULT_MAP_ID,
            "name": "Emergency Empty Map",
            "description": "CSV mapfiles missing; diagnostic fallback only.",
            "chunked": False,
            "chunk_size": CHUNK_SIZE,
            "chunk_cols": 2,
            "chunk_rows": 2,
            "world_w": 2048,
            "world_h": 2048,
            "interest_radius_chunks": NETWORK_INTEREST_RADIUS_CHUNKS,
            "chunk_cache_limit": CHUNK_CACHE_LIMIT,
            "procedural_buildings": False,
            "supplier_pos": [700.0, 700.0],
            "customer_pos": [1300.0, 1300.0],
            "spawns": [[1024.0, 1024.0]],
            "login_spawns": [[1024.0, 1024.0]],
            "geo_bounds": {}, "districts": [], "landmarks": [], "interiors": [],
            "parked_vehicle_spawns": [], "parked_bicycle_spawns": [], "npc_routes": [],
            "water_polygons": [], "roads": [], "buildings": [], "traffic_routes": [],
            "traffic_signals": [], "crosswalks": [], "bike_lanes": [], "bicycle_routes": [],
        }
    }

# ---------------------------------------------------------------------------
# Server-authoritative civilian traffic
# ---------------------------------------------------------------------------
TRAFFIC_DEFAULT_COUNT = 28
TRAFFIC_CAR_LENGTH = 34.0
TRAFFIC_CAR_WIDTH = 18.0
TRAFFIC_SPRITE_COUNT = 81
TRAFFIC_FOLLOW_DISTANCE = 64.0
TRAFFIC_PEDESTRIAN_YIELD_DISTANCE = 68.0
TRAFFIC_LIGHT_CYCLE_S = 16.0
TRAFFIC_LIGHT_GREEN_S = 7.0
TRAFFIC_LIGHT_ALL_RED_S = 1.0
TRAFFIC_SPATIAL_CELL = 192.0
TRAFFIC_MIN_SEPARATION = 42.0
TRAFFIC_BRAKE_DECEL = 250.0
TRAFFIC_LOOKAHEAD_MIN = 78.0

TRAFFIC_CAR_COLORS = [
    [176,62,54],[55,96,145],[207,181,73],[63,128,92],[153,153,147],[44,46,49],[128,78,145],[203,108,51],
]

# ---------------------------------------------------------------------------
# Deterministic large-world geometry shared by client + server
# ---------------------------------------------------------------------------
def world_to_chunk(x: float, y: float, map_config: dict | None = None) -> tuple[int, int]:
    cfg = map_config or MAPS[DEFAULT_MAP_ID]
    size = int(cfg.get("chunk_size", CHUNK_SIZE))
    return int(max(0.0, x) // size), int(max(0.0, y) // size)




def world_to_region(x: float, y: float, map_config: dict | None = None) -> tuple[int, int]:
    """Map a world position to a coarse logical server region.

    v2.4 still runs one authoritative process, but this region contract is stable
    for future worker/shard handoff. Regions are integer groups of streaming
    chunks and never change the client-visible A1 chunk coordinates.
    """
    cfg = map_config or MAPS[DEFAULT_MAP_ID]
    cx, cy = world_to_chunk(x, y, cfg)
    span_x = max(1, int(cfg.get("server_region_chunk_cols", 8)))
    span_y = max(1, int(cfg.get("server_region_chunk_rows", 6)))
    return cx // span_x, cy // span_y


def region_label(rx: int, ry: int) -> str:
    return f"R{int(ry)+1}C{int(rx)+1}"

def _point_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    vv = vx * vx + vy * vy
    if vv <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / vv))
    qx, qy = ax + t * vx, ay + t * vy
    return math.hypot(px - qx, py - qy)


def point_in_polygon(x: float, y: float, polygon: list) -> bool:
    inside = False
    n = len(polygon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = float(polygon[i][0]), float(polygon[i][1])
        xj, yj = float(polygon[j][0]), float(polygon[j][1])
        intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_water(x: float, y: float, map_config: dict) -> bool:
    grid = map_config.get("_grid")
    if grid is not None:
        # The grid is a broad-phase accelerator. Near a coastline, retain the
        # authored polygon as the exact test so the 32 px logical grid never
        # makes the visible/playable shoreline blocky.
        if not grid.any_bits_near(x, y, grid.cell_size * 0.8, GRID_WATER):
            return False
    return any(point_in_polygon(x, y, poly) for poly in map_config.get("water_polygons", []))


def _feature_level(raw, default: int = 0) -> int:
    try:
        return int(float(raw if raw is not None else default))
    except (TypeError, ValueError):
        return int(default)


def point_near_road(
    x: float,
    y: float,
    map_config: dict,
    extra: float = 0.0,
    *,
    bridge_only: bool = False,
    level: int | None = None,
) -> bool:
    """Return whether a point is inside a road corridor.

    ``level`` is intentionally optional for old callers.  Supplying it is the
    grade-separation contract: a Level-0 street crossing beneath a Level-1
    bridge is *not* treated as the same walkable/drivable surface.
    """
    grid = map_config.get("_grid")
    if grid is not None:
        mask = GRID_BRIDGE if bridge_only else GRID_ROAD
        # Fast reject; exact centerline distance remains the narrow-phase test.
        # The grid is level-agnostic, so it is used only as a conservative reject.
        if not grid.any_bits_near(x, y, max(float(extra), grid.cell_size), mask):
            return False
    wanted_level = None if level is None else int(level)
    for road in map_config.get("roads", []):
        if bridge_only and not road.get("bridge"):
            continue
        if wanted_level is not None and _feature_level(road.get("level", 0)) != wanted_level:
            continue
        points = road.get("points", [])
        radius = float(road.get("width", 80)) * 0.5 + float(extra)
        for a, b in zip(points, points[1:]):
            if _point_segment_distance(x, y, float(a[0]), float(a[1]), float(b[0]), float(b[1])) <= radius:
                return True
    return False


def point_near_level_connector(
    x: float,
    y: float,
    map_config: dict,
    *,
    level: int | None = None,
    extra: float = 0.0,
) -> bool:
    """Return whether ``(x,y)`` lies on a ramp/stair/elevator connector.

    A connector belongs to both endpoint levels while it is being traversed.
    This lets a player walk down a ramp before the authoritative level switch is
    committed at the opposite endpoint.
    """
    wanted = None if level is None else int(level)
    for connector in map_config.get("level_connectors", []) or []:
        from_level = _feature_level(connector.get("from_level", 0))
        to_level = _feature_level(connector.get("to_level", 0))
        if wanted is not None and wanted not in {from_level, to_level}:
            continue
        try:
            a = connector.get("start", [connector.get("x0", 0), connector.get("y0", 0)])
            b = connector.get("end", [connector.get("x1", 0), connector.get("y1", 0)])
            x0, y0 = float(a[0]), float(a[1])
            x1, y1 = float(b[0]), float(b[1])
            radius = max(12.0, float(connector.get("width", 80)) * 0.5) + float(extra)
        except (TypeError, ValueError, IndexError):
            continue
        if _point_segment_distance(x, y, x0, y0, x1, y1) <= radius:
            return True
    return False


def resolve_level_transition(
    x: float,
    y: float,
    current_level: int,
    map_config: dict,
    *,
    previous_x: float | None = None,
    previous_y: float | None = None,
) -> int:
    """Resolve a completed map-level transition at a connector endpoint.

    The switch occurs only near the *opposite* endpoint of a connector.  A
    player therefore stays on their current collision level while walking along
    the ramp, then changes level once the ramp has actually been traversed.
    """
    current = int(current_level)
    movement_known = previous_x is not None and previous_y is not None
    move_x = float(x) - float(previous_x) if movement_known else 0.0
    move_y = float(y) - float(previous_y) if movement_known else 0.0
    for connector in map_config.get("level_connectors", []) or []:
        from_level = _feature_level(connector.get("from_level", 0))
        to_level = _feature_level(connector.get("to_level", 0))
        try:
            start = connector.get("start", [connector.get("x0", 0), connector.get("y0", 0)])
            end = connector.get("end", [connector.get("x1", 0), connector.get("y1", 0)])
            sx, sy = float(start[0]), float(start[1])
            ex, ey = float(end[0]), float(end[1])
            width = float(connector.get("width", 80))
        except (TypeError, ValueError, IndexError):
            continue
        endpoint_radius = max(24.0, min(72.0, width * 0.42))
        # Some compact authored ramps have endpoint trigger circles that overlap.
        # Position alone then alternates levels every server tick and makes a
        # quick turn-back feel locked or unpredictable.  When movement is
        # supplied, require travel along the connector in the appropriate
        # direction.  Reversing input can therefore reverse the transition on
        # the very next movement tick, while standing still never flickers.
        connector_x = ex - sx
        connector_y = ey - sy
        directional_progress = move_x * connector_x + move_y * connector_y
        moving_forward = not movement_known or directional_progress > 1e-6
        moving_backward = not movement_known or directional_progress < -1e-6
        if (
            current == from_level
            and moving_forward
            and math.hypot(x - ex, y - ey) <= endpoint_radius
        ):
            return to_level
        if (
            current == to_level
            and moving_backward
            and math.hypot(x - sx, y - sy) <= endpoint_radius
        ):
            return from_level
    return current


_CHUNK_BUILDING_CACHE: dict[tuple[str, int, int], list[list[int]]] = {}
_IMPORTED_BUILDING_INDEX_CACHE: dict[tuple[str, int, int, int], dict[tuple[int, int], list[list[int]]]] = {}


def _indexed_imported_buildings(map_config: dict) -> dict[tuple[int, int], list[list[int]]]:
    size = max(1, int(map_config.get("chunk_size", CHUNK_SIZE)))
    buildings = map_config.get("buildings", []) or []
    key = (str(map_config.get("id", "map")), size, len(buildings), id(buildings))
    cached = _IMPORTED_BUILDING_INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    index: dict[tuple[int,int], list[list[int]]] = {}
    for raw in buildings:
        try:
            x, y, w, h = map(int, raw)
        except (TypeError, ValueError):
            continue
        rect = [x,y,w,h]
        cx0 = max(0, x // size); cy0 = max(0, y // size)
        cx1 = max(0, (x + max(0,w-1)) // size); cy1 = max(0, (y + max(0,h-1)) // size)
        for cy in range(cy0, cy1+1):
            for cx in range(cx0, cx1+1):
                index.setdefault((cx,cy), []).append(rect)
    _IMPORTED_BUILDING_INDEX_CACHE.clear()
    _IMPORTED_BUILDING_INDEX_CACHE[key] = index
    return index


def chunk_buildings(map_config: dict, chunk_x: int, chunk_y: int) -> list[list[int]]:
    """Generate repeatable building collision rectangles for one chunk.

    No giant building array is stored or transmitted. The same function runs on
    the server for collision and on the client when rendering a chunk.
    """
    cache_key = (str(map_config.get("id", "map")), int(chunk_x), int(chunk_y))
    cached = _CHUNK_BUILDING_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if not map_config.get("chunked"):
        result = [list(map(int, r)) for r in map_config.get("buildings", [])]
        _CHUNK_BUILDING_CACHE[cache_key] = result
        return result
    if not bool(map_config.get("procedural_buildings", True)):
        result = list(_indexed_imported_buildings(map_config).get((int(chunk_x), int(chunk_y)), ()))
        _CHUNK_BUILDING_CACHE[cache_key] = result
        return result

    import random
    size = int(map_config.get("chunk_size", CHUNK_SIZE))
    cols = int(map_config.get("chunk_cols", max(1, int(map_config["world_w"]) // size)))
    rows = int(map_config.get("chunk_rows", max(1, int(map_config["world_h"]) // size)))
    if chunk_x < 0 or chunk_y < 0 or chunk_x >= cols or chunk_y >= rows:
        return []
    rng = random.Random(f"pymmo-v013:{map_config.get('id')}:{chunk_x}:{chunk_y}")
    ox, oy = chunk_x * size, chunk_y * size
    results: list[list[int]] = []
    cell = 256
    protected = [tuple(map_config.get("supplier_pos", [0, 0])), tuple(map_config.get("customer_pos", [0, 0]))]
    protected += [tuple(l.get("pos", [0, 0])) for l in map_config.get("landmarks", [])]
    protected += [tuple(i.get("entry", [0, 0])) for i in map_config.get("interiors", [])]
    # Spawn safety is an engine invariant. Procedural city dressing must never be
    # allowed to generate a building on top of a player spawn/login spawn.
    protected += [tuple(p) for p in map_config.get("spawns", [])]
    protected += [tuple(p) for p in map_config.get("login_spawns", [])]

    for gy in range(4):
        for gx in range(4):
            if rng.random() < 0.18:
                continue
            bw = rng.randint(116, 184)
            bh = rng.randint(108, 184)
            cx = ox + gx * cell + cell // 2 + rng.randint(-22, 22)
            cy = oy + gy * cell + cell // 2 + rng.randint(-22, 22)
            # Preserve rivers, arterial roads, landmarks and game interactions.
            half_diag = math.hypot(bw, bh) * 0.5
            corners = [
                (cx - bw * 0.5, cy - bh * 0.5), (cx + bw * 0.5, cy - bh * 0.5),
                (cx - bw * 0.5, cy + bh * 0.5), (cx + bw * 0.5, cy + bh * 0.5),
            ]
            if point_in_water(cx, cy, map_config) or any(point_in_water(px, py, map_config) for px, py in corners):
                continue
            if point_near_road(cx, cy, map_config, extra=half_diag + 26.0):
                continue
            if any(math.hypot(cx - px, cy - py) < 260.0 + half_diag for px, py in protected):
                continue
            x = int(cx - bw / 2)
            y = int(cy - bh / 2)
            results.append([x, y, bw, bh])
    _CHUNK_BUILDING_CACHE[cache_key] = results
    return results


def collision_buildings_near(x: float, y: float, map_config: dict) -> list[list[int]]:
    if not map_config.get("chunked"):
        return [list(r) for r in map_config.get("buildings", [])]
    size = int(map_config.get("chunk_size", CHUNK_SIZE))
    cx, cy = world_to_chunk(x, y, map_config)
    rects: list[list[int]] = []
    for yy in range(cy - 1, cy + 2):
        for xx in range(cx - 1, cx + 2):
            rects.extend(chunk_buildings(map_config, xx, yy))
    return rects

def traffic_phase_green(phase: int, server_time: float) -> bool:
    """Two-phase signal with a one-second all-red interval between directions."""
    t = float(server_time) % TRAFFIC_LIGHT_CYCLE_S
    if int(phase) % 2 == 0:
        return 0.0 <= t < TRAFFIC_LIGHT_GREEN_S
    start = TRAFFIC_LIGHT_GREEN_S + TRAFFIC_LIGHT_ALL_RED_S
    return start <= t < start + TRAFFIC_LIGHT_GREEN_S

def traffic_light_states(map_config: dict, server_time: float) -> dict[str, bool]:
    return {
        str(signal["id"]): traffic_phase_green(int(signal.get("phase", 0)), server_time)
        for signal in map_config.get("traffic_signals", [])
    }

def get_map(map_id: str | None = None) -> dict:
    """Return a map preset, falling back safely to the default map."""
    return MAPS.get(str(map_id or DEFAULT_MAP_ID).lower(), MAPS[DEFAULT_MAP_ID])


# Backward-compatible aliases for older code. New code should use get_map().
_DEFAULT_MAP = get_map(DEFAULT_MAP_ID)
WORLD_W = int(_DEFAULT_MAP["world_w"])
WORLD_H = int(_DEFAULT_MAP["world_h"])
SUPPLIER_POS = tuple(_DEFAULT_MAP["supplier_pos"])
CUSTOMER_POS = tuple(_DEFAULT_MAP["customer_pos"])
BUILDINGS = [tuple(rect) for rect in _DEFAULT_MAP["buildings"]]
SPAWNS = [tuple(pos) for pos in _DEFAULT_MAP["spawns"]]


@dataclass
class PlayerState:
    player_id: str
    name: str
    x: float
    y: float
    aim: float = 0.0
    cash: int = STARTING_CASH
    packages: int = 0
    appearance: dict | None = None
    in_vehicle: bool = False
    vehicle_id: str = ""
    vehicle_kind: str = ""
    vehicle_role: str = ""
    interior_id: str = ""
    interior_x: int = 0
    interior_y: int = 0
    interior_aim: float = 0.0
    level: int = 0

    def public_dict(self) -> dict:
        return {
            "id": self.player_id,
            "name": self.name,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "aim": round(self.aim, 4),
            "cash": self.cash,
            "packages": self.packages,
            "appearance": normalize_character(self.appearance),
            "in_vehicle": bool(self.in_vehicle),
            "vehicle_id": self.vehicle_id,
            "vehicle_kind": self.vehicle_kind,
            "vehicle_role": self.vehicle_role,
            "interior_id": self.interior_id,
            "interior_x": int(self.interior_x),
            "interior_y": int(self.interior_y),
            "interior_aim": round(float(self.interior_aim), 4),
            "level": int(self.level),
        }

    def map_marker_dict(self) -> dict:
        """Small global roster record; detailed rendering stays interest-limited."""
        return {
            "id": self.player_id,
            "name": self.name,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "level": int(self.level),
            "in_vehicle": bool(self.in_vehicle),
            "vehicle_role": self.vehicle_role,
            "interior_id": self.interior_id,
        }


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def circle_intersects_rect(cx: float, cy: float, radius: float, rect) -> bool:
    rx, ry, rw, rh = rect
    nearest_x = clamp(cx, rx, rx + rw)
    nearest_y = clamp(cy, ry, ry + rh)
    dx = cx - nearest_x
    dy = cy - nearest_y
    return dx * dx + dy * dy < radius * radius


def blocked(x: float, y: float, map_config: dict | None = None, *, level: int = 0) -> bool:
    cfg = map_config or _DEFAULT_MAP
    level = int(level)
    world_w = float(cfg["world_w"])
    world_h = float(cfg["world_h"])
    if x < PLAYER_RADIUS or y < PLAYER_RADIUS:
        return True
    if x > world_w - PLAYER_RADIUS or y > world_h - PLAYER_RADIUS:
        return True

    grid = cfg.get("_grid")

    # Water is impassable except where an explicitly marked bridge road crosses it.
    # The compiled grid eliminates almost all polygon work; authored geometry is
    # still used as the narrow-phase coastline test for visual/gameplay fidelity.
    water_candidate = True
    if grid is not None:
        water_candidate = grid.any_bits_near(x, y, PLAYER_RADIUS + grid.cell_size * 0.75, GRID_WATER)
    if cfg.get("chunked") and water_candidate and point_in_water(x, y, cfg):
        on_same_level_bridge = point_near_road(
            x, y, cfg, extra=PLAYER_RADIUS, bridge_only=True, level=level
        )
        on_level_connector = point_near_level_connector(
            x, y, cfg, level=level, extra=PLAYER_RADIUS
        )
        if not (on_same_level_bridge or on_level_connector):
            return True

    # Above/below-ground walkable levels are bounded by their authored roads and
    # connectors.  Without this gate a Level-1 player could walk off an overpass
    # and effectively float over the Level-0 city.
    if level != 0:
        if not point_near_road(x, y, cfg, extra=PLAYER_RADIUS, level=level) and not point_near_level_connector(
            x, y, cfg, level=level, extra=PLAYER_RADIUS
        ):
            return True
        # Current authored buildings are ground-level collision objects.  Future
        # elevated/underground structures can add a level-aware collision table.
        return False

    # Building collision uses the grid as broad phase and the original rectangles
    # as narrow phase. This preserves precise collision while avoiding neighborhood
    # rectangle scans over the majority of walkable/drivable cells.
    if grid is not None and not grid.any_bits_near(x, y, PLAYER_RADIUS + grid.cell_size, GRID_BUILDING):
        return False
    rects = collision_buildings_near(x, y, cfg) if cfg.get("chunked") else cfg.get("buildings", [])
    return any(circle_intersects_rect(x, y, PLAYER_RADIUS, rect) for rect in rects)


def move_with_collisions(
    x: float,
    y: float,
    dx: float,
    dy: float,
    map_config: dict | None = None,
    *,
    level: int = 0,
) -> tuple[float, float]:
    """Resolve one axis at a time so players slide naturally along walls."""
    nx = x + dx
    if not blocked(nx, y, map_config, level=level):
        x = nx

    ny = y + dy
    if not blocked(x, ny, map_config, level=level):
        y = ny

    return x, y


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalize_input(x: float, y: float) -> tuple[float, float]:
    mag = math.hypot(x, y)
    if mag > 1.0:
        return x / mag, y / mag
    return x, y

# Persistent grid inventory. The server is authoritative; clients only render the
# state sent to them. Item metadata is shared so the UI can label slots without
# trusting the client to define quantities or values.
INVENTORY_COLS = 5
INVENTORY_ROWS = 4
INVENTORY_SLOT_COUNT = INVENTORY_COLS * INVENTORY_ROWS
INVENTORY_MAX_WEIGHT_KG = 10.0

ITEM_DEFS: dict[str, dict] = {
    "package": {
        "id": "package",
        "name": "Sealed Package",
        "short": "PKG",
        "stack_max": 5,
        "weight_kg": 0.35,
        "ui_color": [172, 151, 91],
        "description": "A small sealed package bought from the supplier.",
    },
}


def empty_inventory() -> list[dict | None]:
    return [None for _ in range(INVENTORY_SLOT_COUNT)]


def normalize_inventory(slots: list | None) -> list[dict | None]:
    result = empty_inventory()
    if not isinstance(slots, list):
        return result
    for index, raw in enumerate(slots[:INVENTORY_SLOT_COUNT]):
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("item_id", ""))
        if item_id not in ITEM_DEFS:
            continue
        try:
            quantity = int(raw.get("quantity", 0))
        except (TypeError, ValueError):
            continue
        quantity = max(0, min(quantity, int(ITEM_DEFS[item_id]["stack_max"])))
        if quantity:
            result[index] = {"item_id": item_id, "quantity": quantity}
    return result


def inventory_count(slots: list[dict | None], item_id: str) -> int:
    return sum(int(slot.get("quantity", 0)) for slot in slots if slot and slot.get("item_id") == item_id)


def inventory_weight(slots: list[dict | None]) -> float:
    total = 0.0
    for slot in slots:
        if not slot:
            continue
        item = ITEM_DEFS.get(str(slot.get("item_id")))
        if item:
            total += float(item["weight_kg"]) * int(slot.get("quantity", 0))
    return total


def inventory_add(slots: list[dict | None], item_id: str, quantity: int = 1) -> bool:
    """Add a quantity atomically; return False if the whole quantity won't fit."""
    if item_id not in ITEM_DEFS or quantity <= 0:
        return False
    stack_max = int(ITEM_DEFS[item_id]["stack_max"])
    capacity = 0
    for slot in slots:
        if slot is None:
            capacity += stack_max
        elif slot.get("item_id") == item_id:
            capacity += stack_max - int(slot.get("quantity", 0))
    if capacity < quantity:
        return False

    remaining = quantity
    for slot in slots:
        if remaining <= 0:
            break
        if slot and slot.get("item_id") == item_id:
            room = stack_max - int(slot["quantity"])
            moved = min(room, remaining)
            slot["quantity"] += moved
            remaining -= moved
    for index, slot in enumerate(slots):
        if remaining <= 0:
            break
        if slot is None:
            moved = min(stack_max, remaining)
            slots[index] = {"item_id": item_id, "quantity": moved}
            remaining -= moved
    return remaining == 0


def inventory_remove(slots: list[dict | None], item_id: str, quantity: int = 1) -> bool:
    """Remove from later slots first; return False without changing state if insufficient."""
    if quantity <= 0 or inventory_count(slots, item_id) < quantity:
        return False
    remaining = quantity
    for index in range(len(slots) - 1, -1, -1):
        slot = slots[index]
        if not slot or slot.get("item_id") != item_id:
            continue
        moved = min(int(slot["quantity"]), remaining)
        slot["quantity"] -= moved
        remaining -= moved
        if slot["quantity"] <= 0:
            slots[index] = None
        if remaining <= 0:
            break
    return True
