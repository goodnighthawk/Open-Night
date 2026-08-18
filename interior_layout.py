from __future__ import annotations

import math


# The ten legacy room presets remain a useful *authoring grid* for furniture
# placement, but v1.0 no longer uses that grid as the player's coordinate
# system.  Every cell below is projected into the authoritative building
# footprint and all runtime player positions are world X/Y floats.
ROOM_W = 10
ROOM_H = 8
START_TILE = (2, 6)
EXIT_TILE = (1, 6)
FLOOR_INSET = 18.0
PLAYER_CLEARANCE = 10.0
INTERIOR_SPEED = 240.0
INTERIOR_SEND_RATE = 30.0
INTERIOR_STEP = INTERIOR_SPEED / INTERIOR_SEND_RATE

# Shared server-authoritative furniture collision template.  The cells are
# converted to world rectangles inside each room's actual building footprint.
_BLOCKED = {
    "starter_apartment": {(6,2),(5,3),(7,1),(2,2),(1,2),(1,1),(7,5),(8,5),(4,5),(8,2),(0,3),(8,7),(7,7)},
    "corner_shop": {(6,2),(7,2),(8,1),(8,3),(4,4),(1,1),(7,5),(2,2)},
    "night_diner": {(6,1),(7,1),(8,1),(3,3),(6,4),(3,6),(8,5),(1,1)},
    "pharmacy": {(6,2),(7,2),(2,2),(2,4),(5,5),(8,5),(1,1)},
    "laundromat": {(2,2),(3,2),(4,2),(6,4),(7,4),(4,6),(8,1)},
    "pawn_shop": {(6,2),(7,2),(2,1),(2,3),(5,4),(7,5),(3,5),(8,1)},
    "garage": {(7,1),(8,1),(1,1),(1,3),(5,5),(8,5),(2,6)},
    "nightclub": {(7,1),(8,1),(2,2),(5,4),(3,5),(1,1),(8,5),(7,3)},
    "warehouse_office": {(6,2),(3,3),(8,1),(8,3),(5,1),(7,6),(1,1)},
    "rooftop_loft": {(6,2),(5,3),(8,1),(2,2),(1,2),(1,1),(7,5),(8,5),(7,2),(2,5)},
}


def blocked_tiles(room_id: str) -> set[tuple[int, int]]:
    tiles = set(_BLOCKED.get(str(room_id), _BLOCKED["starter_apartment"]))
    # Spawn and exit are gameplay-reserved cells even if an old cosmetic preset
    # happened to put furniture there (the garage did this at START_TILE).
    tiles.discard(START_TILE)
    tiles.discard(EXIT_TILE)
    return tiles


def interior_info(map_config: dict, room_id: str) -> dict | None:
    wanted = str(room_id)
    return next((row for row in map_config.get("interiors", []) or [] if str(row.get("id", "")) == wanted), None)


def building_rect(map_config: dict, building_id: str) -> tuple[float, float, float, float] | None:
    wanted = str(building_id)
    ids = list(map_config.get("building_ids", []) or [])
    buildings = list(map_config.get("buildings", []) or [])
    for bid, rect in zip(ids, buildings):
        if str(bid) != wanted or not isinstance(rect, (list, tuple)) or len(rect) < 4:
            continue
        return tuple(float(v) for v in rect[:4])
    return None


def _distance_to_rect(px: float, py: float, rect: tuple[float, float, float, float]) -> float:
    x, y, w, h = rect
    qx = max(x, min(x + w, px))
    qy = max(y, min(y + h, py))
    return math.hypot(px - qx, py - qy)


def interior_building_id(map_config: dict, room_id: str) -> str:
    """Return the explicit authored building binding for an interior.

    New v1.0 loaders preserve ``building_id`` from interiors.csv.  The nearest
    footprint fallback keeps old cached/portable map packages readable while
    remaining deterministic and using only authoritative building geometry.
    """
    info = interior_info(map_config, room_id)
    if info is None:
        return ""
    explicit = str(info.get("building_id", "")).strip()
    if explicit and building_rect(map_config, explicit) is not None:
        return explicit
    entry = info.get("entry", [0.0, 0.0])
    try:
        ex, ey = float(entry[0]), float(entry[1])
    except (TypeError, ValueError, IndexError):
        return ""
    best_id = ""
    best_distance = float("inf")
    for bid, rect in zip(map_config.get("building_ids", []) or [], map_config.get("buildings", []) or []):
        if not isinstance(rect, (list, tuple)) or len(rect) < 4:
            continue
        parsed = tuple(float(v) for v in rect[:4])
        distance = _distance_to_rect(ex, ey, parsed)
        if distance < best_distance:
            best_id, best_distance = str(bid), distance
    return best_id


def interior_floor_rect(map_config: dict, room_id: str) -> tuple[float, float, float, float] | None:
    """Authoritative world-space walkable floor rectangle for one room.

    The exterior building footprint remains authoritative.  A small inset keeps
    the player's center clear of the visible/collision wall thickness.
    """
    bid = interior_building_id(map_config, room_id)
    rect = building_rect(map_config, bid)
    if rect is None:
        return None
    x, y, w, h = rect
    inset = min(FLOOR_INSET, max(4.0, min(w, h) * 0.08))
    fw, fh = max(32.0, w - 2.0 * inset), max(32.0, h - 2.0 * inset)
    return x + inset, y + inset, fw, fh


def interior_cell_size(map_config: dict, room_id: str) -> tuple[float, float]:
    floor = interior_floor_rect(map_config, room_id)
    if floor is None:
        return 32.0, 32.0
    return floor[2] / ROOM_W, floor[3] / ROOM_H


def tile_center_world(map_config: dict, room_id: str, tile: tuple[int, int]) -> tuple[float, float]:
    floor = interior_floor_rect(map_config, room_id)
    if floor is None:
        return 0.0, 0.0
    x, y, w, h = floor
    gx = max(0, min(ROOM_W - 1, int(tile[0])))
    gy = max(0, min(ROOM_H - 1, int(tile[1])))
    return x + (gx + 0.5) * w / ROOM_W, y + (gy + 0.5) * h / ROOM_H


def world_to_tile(map_config: dict, room_id: str, x: float, y: float) -> tuple[int, int]:
    floor = interior_floor_rect(map_config, room_id)
    if floor is None:
        return 0, 0
    fx, fy, fw, fh = floor
    gx = int((float(x) - fx) / max(1e-6, fw) * ROOM_W)
    gy = int((float(y) - fy) / max(1e-6, fh) * ROOM_H)
    return max(0, min(ROOM_W - 1, gx)), max(0, min(ROOM_H - 1, gy))


def blocked_world_rects(map_config: dict, room_id: str) -> list[tuple[float, float, float, float]]:
    floor = interior_floor_rect(map_config, room_id)
    if floor is None:
        return []
    fx, fy, fw, fh = floor
    cw, ch = fw / ROOM_W, fh / ROOM_H
    # Leave a small aisle around furniture so the collision model does not turn
    # adjacent visual cells into an artificially solid wall.
    mx, my = cw * 0.10, ch * 0.10
    result = []
    for gx, gy in sorted(blocked_tiles(room_id)):
        result.append((fx + gx * cw + mx, fy + gy * ch + my, max(2.0, cw - 2 * mx), max(2.0, ch - 2 * my)))
    return result


def point_walkable(map_config: dict, room_id: str, x: float, y: float, clearance: float = PLAYER_CLEARANCE) -> bool:
    floor = interior_floor_rect(map_config, room_id)
    if floor is None:
        return False
    fx, fy, fw, fh = floor
    c = max(0.0, float(clearance))
    px, py = float(x), float(y)
    if px < fx + c or px > fx + fw - c or py < fy + c or py > fy + fh - c:
        return False
    for bx, by, bw, bh in blocked_world_rects(map_config, room_id):
        if bx - c <= px <= bx + bw + c and by - c <= py <= by + bh + c:
            return False
    return True


def interior_start_world(map_config: dict, room_id: str) -> tuple[float, float]:
    pos = tile_center_world(map_config, room_id, START_TILE)
    if point_walkable(map_config, room_id, *pos):
        return pos
    # Deterministic safe fallback: scan authored template cells, never outside
    # the registered building floor.
    for gy in range(ROOM_H - 1, -1, -1):
        for gx in range(ROOM_W):
            candidate = tile_center_world(map_config, room_id, (gx, gy))
            if point_walkable(map_config, room_id, *candidate):
                return candidate
    return pos


def interior_exit_world(map_config: dict, room_id: str) -> tuple[float, float]:
    return tile_center_world(map_config, room_id, EXIT_TILE)


def near_exit(map_config: dict, room_id: str, x: float, y: float) -> bool:
    ex, ey = interior_exit_world(map_config, room_id)
    cw, ch = interior_cell_size(map_config, room_id)
    return math.hypot(float(x) - ex, float(y) - ey) <= max(18.0, min(cw, ch) * 0.55)


def interior_move_world(
    map_config: dict,
    room_id: str,
    x: float,
    y: float,
    dx: float,
    dy: float,
    *,
    step: float = INTERIOR_STEP,
) -> tuple[float, float, float]:
    """Resolve one continuous authoritative movement sample in world X/Y.

    ``dx``/``dy`` are direction inputs, not trusted distances.  Their magnitude
    is clamped to one and the server applies its own fixed step, preventing a
    client from moving faster by sending larger values.
    """
    px, py = float(x), float(y)
    try:
        vx, vy = float(dx), float(dy)
    except (TypeError, ValueError):
        return px, py, 0.0
    mag = math.hypot(vx, vy)
    if mag <= 1e-6:
        return px, py, 0.0
    if mag > 1.0:
        vx, vy = vx / mag, vy / mag
    distance = max(0.0, min(float(step), INTERIOR_STEP * 1.25))
    aim = math.atan2(vy, vx)

    # Resolve in short substeps with axis sliding so a diagonal cannot tunnel
    # through a furniture rectangle or snag unnecessarily on its corner.
    subdivisions = max(1, int(math.ceil(distance / 3.0)))
    sx, sy = vx * distance / subdivisions, vy * distance / subdivisions
    for _ in range(subdivisions):
        nx = px + sx
        if point_walkable(map_config, room_id, nx, py):
            px = nx
        ny = py + sy
        if point_walkable(map_config, room_id, px, ny):
            py = ny
    return px, py, aim


# Backward-compatible grid helper for old cached clients/tests. v1.0 server
# runtime does not use this function after First Floor promotion.
def interior_step(room_id: str, x: int, y: int, dx: int, dy: int) -> tuple[int, int, float]:
    dx, dy = int(dx), int(dy)
    if abs(dx) + abs(dy) != 1:
        return int(x), int(y), -math.pi / 2.0
    nx = max(0, min(ROOM_W - 1, int(x) + dx))
    ny = max(0, min(ROOM_H - 1, int(y) + dy))
    aim = 0.0 if dx > 0 else (math.pi if dx < 0 else (math.pi / 2.0 if dy > 0 else -math.pi / 2.0))
    if (nx, ny) in blocked_tiles(room_id):
        return int(x), int(y), aim
    return nx, ny, aim
