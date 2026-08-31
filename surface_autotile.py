"""Cardinal/diagonal surface autotiling for next-map curbs and shorelines."""
from __future__ import annotations

CARDINALS = {"top": (0, -1), "right": (1, 0), "bottom": (0, 1), "left": (-1, 0)}
DIAGONALS = {"tl": (-1, -1), "tr": (1, -1), "br": (1, 1), "bl": (-1, 1)}


def neighbour_mask(x: int, y: int, cells: set[tuple[int, int]]) -> dict[str, bool]:
    return {
        name: (x + dx, y + dy) in cells
        for name, (dx, dy) in {**CARDINALS, **DIAGONALS}.items()
    }


def boundary_role(x: int, y: int, cells: set[tuple[int, int]]) -> str:
    """Choose fill, straight, outside-corner, or inside-corner from eight neighbors."""
    mask = neighbour_mask(x, y, cells)
    missing = [side for side in CARDINALS if not mask[side]]
    if not missing:
        for corner in ("tl", "tr", "br", "bl"):
            if not mask[corner]:
                return f"{corner}_inner"
        return "fill"
    if len(missing) == 1:
        return missing[0]
    adjacent = {
        frozenset(("top", "left")): "tl_outer",
        frozenset(("top", "right")): "tr_outer",
        frozenset(("bottom", "right")): "br_outer",
        frozenset(("bottom", "left")): "bl_outer",
    }
    for pair, role in adjacent.items():
        if pair <= set(missing):
            return role
    return missing[0]


def autotile_ids(cells: set[tuple[int, int]], prefix: str, fill_id: str) -> dict[tuple[int, int], str]:
    result = {}
    for x, y in sorted(cells, key=lambda p: (p[1], p[0])):
        role = boundary_role(x, y, cells)
        result[(x, y)] = fill_id if role == "fill" else f"{prefix}_{role}"
    return result


def crossing_ramp_id(sidewalk_side: str) -> str:
    """Return a ramp that faces the road from the named sidewalk side."""
    return {
        "north": "curb_ramp_bottom",
        "south": "curb_ramp_top",
        "west": "curb_ramp_right",
        "east": "curb_ramp_left",
    }[sidewalk_side]


def road_topology_role(x: int, y: int, road_cells: set[tuple[int, int]]) -> str:
    """Classify a road cell for straight/turn/T/intersection overlay planning."""
    connected = {name for name, (dx, dy) in CARDINALS.items() if (x + dx, y + dy) in road_cells}
    count = len(connected)
    if count == 4:
        return "intersection"
    if count == 3:
        missing = next(side for side in CARDINALS if side not in connected)
        return f"t_missing_{missing}"
    if count == 2:
        if connected in ({"top", "bottom"}, {"left", "right"}):
            return "straight_vertical" if "top" in connected else "straight_horizontal"
        return "turn_" + "_".join(side for side in ("top", "right", "bottom", "left") if side in connected)
    if count == 1:
        return f"end_{next(iter(connected))}"
    return "isolated"
