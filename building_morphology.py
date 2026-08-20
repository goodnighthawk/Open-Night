"""Pure deterministic building-footprint grammar shared by generation and runtime."""
from __future__ import annotations

import hashlib

NOTCH_DEPTH_CELLS = 2
NOTCHES_PER_THEME = 2
NOTCH_CORNERS = ("top_left", "top_right", "bottom_right", "bottom_left")


def footprint_for(rect: tuple[int, int, int, int], notch: dict | None = None) -> set[tuple[int, int]]:
    x0, y0, x1, y1 = rect
    cells = {(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)}
    if not notch:
        return cells
    depth = int(notch["depth_cells"])
    corner = str(notch["corner"])
    xs = range(x0, x0 + depth) if corner.endswith("left") else range(x1 - depth + 1, x1 + 1)
    ys = range(y0, y0 + depth) if corner.startswith("top") else range(y1 - depth + 1, y1 + 1)
    cells.difference_update((x, y) for y in ys for x in xs)
    return cells


def role_for_cell(x: int, y: int, cells: set[tuple[int, int]]) -> str:
    north, east, south, west = ((x, y - 1) in cells, (x + 1, y) in cells,
                                (x, y + 1) in cells, (x - 1, y) in cells)
    if north and east and south and west:
        if (x - 1, y - 1) not in cells:
            return "bottom_left_inner"
        if (x + 1, y - 1) not in cells:
            return "bottom_right_inner"
        if (x + 1, y + 1) not in cells:
            return "top_right_inner"
        if (x - 1, y + 1) not in cells:
            return "top_left_inner"
        return "fill"
    if not north and not west:
        return "top_left_outer"
    if not north and not east:
        return "top_right_outer"
    if not south and not east:
        return "bottom_right_outer"
    if not south and not west:
        return "bottom_left_outer"
    if not north:
        return "top_center"
    if not south:
        return "bottom_center"
    if not west:
        return "left"
    if not east:
        return "right"
    return "fill"


def assign_notches(buildings: list[dict], theme_order: tuple[str, ...]) -> None:
    """Mutate building records with a balanced, byte-stable corner-notch selection."""
    for theme_index, theme in enumerate(theme_order):
        candidates = []
        for building in buildings:
            if str(building["theme"]) != theme:
                continue
            x0, y0, x1, y1 = map(int, building["rect"])
            area = (x1 - x0 + 1) * (y1 - y0 + 1)
            if x1 - x0 + 1 < 4 or y1 - y0 + 1 < 4 or area - NOTCH_DEPTH_CELLS ** 2 < 24:
                continue
            key = (
                f"open-night-building-morphology-v1|select|{building['building_id']}|"
                f"{theme}|{building['rect']}"
            )
            candidates.append((hashlib.sha256(key.encode("ascii")).digest(), building))
        candidates.sort(key=lambda item: item[0])
        if len(candidates) < NOTCHES_PER_THEME:
            raise RuntimeError(f"building morphology lacks two eligible {theme} footprints")
        for selected_index, (_rank, building) in enumerate(candidates[:NOTCHES_PER_THEME]):
            corner = NOTCH_CORNERS[(theme_index * NOTCHES_PER_THEME + selected_index) % len(NOTCH_CORNERS)]
            building["notch"] = {"corner": corner, "depth_cells": NOTCH_DEPTH_CELLS}
            building["footprint_type"] = "corner_notched"


def transition_anchors(building: dict, cells: set[tuple[int, int]]) -> dict[str, tuple[int, int]]:
    x0, y0, x1, y1 = map(int, building["rect"])
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    south = [(x, y) for x, y in cells if y == y1]
    east = [(x, y) for x, y in cells if x == x1]
    if not south or not east:
        raise RuntimeError(f"building morphology removed a required exterior edge: {building['building_id']}")
    return {
        "door": min(south, key=lambda cell: (abs(cell[0] - cx), cell[0])),
        "fire_escape": min(east, key=lambda cell: (abs(cell[1] - cy), cell[1])),
        "hatch": min(cells, key=lambda cell: (abs(cell[0] - cx) + abs(cell[1] - cy), cell[1], cell[0])),
    }
