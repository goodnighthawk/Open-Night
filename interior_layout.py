from __future__ import annotations


ROOM_W = 10
ROOM_H = 8
START_TILE = (2, 6)
EXIT_TILE = (1, 6)

# Shared collision contract for the procedural furniture layouts.  The client
# draws the furniture; the server owns whether an interior step is legal.
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
    tiles.discard(EXIT_TILE)
    return tiles


def interior_step(room_id: str, x: int, y: int, dx: int, dy: int) -> tuple[int, int, float]:
    import math

    dx, dy = int(dx), int(dy)
    if abs(dx) + abs(dy) != 1:
        return int(x), int(y), -math.pi / 2.0
    nx = max(0, min(ROOM_W - 1, int(x) + dx))
    ny = max(0, min(ROOM_H - 1, int(y) + dy))
    aim = 0.0 if dx > 0 else (math.pi if dx < 0 else (math.pi / 2.0 if dy > 0 else -math.pi / 2.0))
    if (nx, ny) in blocked_tiles(room_id):
        return int(x), int(y), aim
    return nx, ny, aim
