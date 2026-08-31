"""Pure deterministic building-footprint grammar shared by generation and runtime."""
from __future__ import annotations

import hashlib

NOTCH_DEPTH_CELLS = 2
NOTCH_CORNERS = ("top_left", "top_right", "bottom_right", "bottom_left")


def footprint_for(
    rect: tuple[int, int, int, int],
    notch: dict | list[dict] | tuple[dict, ...] | None = None,
) -> set[tuple[int, int]]:
    x0, y0, x1, y1 = rect
    cells = {(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)}
    if not notch:
        return cells
    notches = notch if isinstance(notch, (list, tuple)) else (notch,)
    for cut in notches:
        kind = str(cut.get("kind", "corner"))
        depth = int(cut.get("depth_cells", 1))
        if kind == "corner":
            corner = str(cut["corner"])
            xs = range(x0, x0 + depth) if corner.endswith("left") else range(x1 - depth + 1, x1 + 1)
            ys = range(y0, y0 + depth) if corner.startswith("top") else range(y1 - depth + 1, y1 + 1)
        elif kind == "edge_recess":
            edge = str(cut["edge"])
            offset = int(cut["offset_cells"])
            length = int(cut["length_cells"])
            if edge in {"top", "bottom"}:
                xs = range(x0 + offset, min(x1 + 1, x0 + offset + length))
                ys = range(y0, min(y1 + 1, y0 + depth)) if edge == "top" else range(max(y0, y1 - depth + 1), y1 + 1)
            else:
                xs = range(x0, min(x1 + 1, x0 + depth)) if edge == "left" else range(max(x0, x1 - depth + 1), x1 + 1)
                ys = range(y0 + offset, min(y1 + 1, y0 + offset + length))
        elif kind == "courtyard":
            inset_x = int(cut.get("inset_x_cells", 2))
            inset_y = int(cut.get("inset_y_cells", 2))
            xs = range(x0 + inset_x, x1 - inset_x + 1)
            ys = range(y0 + inset_y, y1 - inset_y + 1)
        else:
            raise ValueError(f"unknown building footprint cut kind {kind!r}")
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


def footprint_connected(cells: set[tuple[int, int]]) -> bool:
    """Return whether every occupied cell belongs to one four-way component."""
    if not cells:
        return False
    remaining = set(cells)
    stack = [remaining.pop()]
    while stack:
        x, y = stack.pop()
        for neighbour in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if neighbour in remaining:
                remaining.remove(neighbour)
                stack.append(neighbour)
    return not remaining


def assign_notches(buildings: list[dict], theme_order: tuple[str, ...]) -> None:
    """Assign the complete deterministic modular footprint grammar.

    The earlier balanced-per-theme policy discarded every notch if one color
    lacked two large candidates.  Building shape is geometry, not a palette
    quota, so each footprint now receives its own deterministic decision.
    """
    del theme_order  # Kept in the public signature for generator compatibility.
    adjacent_pairs = (
        ("top_left", "top_right"),
        ("top_right", "bottom_right"),
        ("bottom_right", "bottom_left"),
        ("bottom_left", "top_left"),
    )
    for index, building in enumerate(buildings):
        x0, y0, x1, y1 = map(int, building["rect"])
        width, height = x1 - x0 + 1, y1 - y0 + 1
        building["notch"] = None
        building["footprint_type"] = "rectangle"
        building["shape_variant"] = "rectangle"
        if width < 5 or height < 4:
            continue

        key = f"open-night-building-morphology-v2|{building['building_id']}|{building['theme']}|{building['rect']}"
        digest = hashlib.sha256(key.encode("ascii")).digest()
        preferred_family = index % 5
        if preferred_family == 0:
            continue

        corner_index = digest[0] % len(NOTCH_CORNERS)
        if preferred_family == 1:
            depth = NOTCH_DEPTH_CELLS if width >= 5 and height >= 4 else 1
            building["notch"] = {
                "kind": "corner", "corner": NOTCH_CORNERS[corner_index],
                "depth_cells": depth,
            }
            building["shape_variant"] = "l_corner"
            building["footprint_type"] = "corner_notched"
        elif preferred_family == 2 and width >= 6:
            corners = adjacent_pairs[corner_index]
            building["notch"] = [
                {"kind": "corner", "corner": corners[0], "depth_cells": 2},
                {"kind": "corner", "corner": corners[1], "depth_cells": 1},
            ]
            building["shape_variant"] = "stepped_side"
            building["footprint_type"] = "stepped"
        elif preferred_family == 3 and width >= 6 and height >= 5:
            edge = ("top", "right", "bottom", "left")[digest[1] % 4]
            along = width if edge in {"top", "bottom"} else height
            length = 2 if along < 8 else 3
            offset = 1 + digest[2] % max(1, along - length - 1)
            building["notch"] = {
                "kind": "edge_recess", "edge": edge, "offset_cells": offset,
                "length_cells": length, "depth_cells": 2,
            }
            building["shape_variant"] = "recessed_edge"
            building["footprint_type"] = "recessed"
        elif preferred_family == 4 and width >= 6 and height >= 6:
            building["notch"] = {
                "kind": "courtyard", "inset_x_cells": 2, "inset_y_cells": 2,
            }
            building["shape_variant"] = "courtyard"
            building["footprint_type"] = "courtyard"
        else:
            # Small envelopes fall back to an L rather than producing a
            # disconnected or one-cell-thick double-sided wall.
            building["notch"] = {
                "kind": "corner", "corner": NOTCH_CORNERS[corner_index],
                "depth_cells": 1,
            }
            building["shape_variant"] = "l_corner"
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
