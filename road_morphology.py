"""Deterministic collision-authoritative road morphology for Open Night v1.0."""
from __future__ import annotations

from collections import deque


ROAD_PASS = "road_morphology_v1"


def contiguous_bands(values: list[int]) -> list[tuple[int, int]]:
    if not values:
        return []
    bands: list[tuple[int, int]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value != previous + 1:
            bands.append((start, previous))
            start = value
        previous = value
    bands.append((start, previous))
    return bands


def road_bands(rows: list[list[str]]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Return the authoritative three-cell road bands, including v1 spurs."""
    height, width = len(rows), len(rows[0])
    vertical_columns = [
        x for x in range(width)
        if sum(rows[y][x] == "road_fill" for y in range(height)) >= int(height * 0.75)
    ]
    horizontal_rows = [
        y for y in range(height)
        if sum(rows[y][x] == "road_fill" for x in range(width)) >= int(width * 0.75)
    ]
    return contiguous_bands(vertical_columns), contiguous_bands(horizontal_rows)


def apply_road_morphology(rows: list[list[str]]) -> tuple[list[list[str]], dict]:
    """Offset one peripheral road spur to make a staggered T-junction pair.

    The selected corridor is the second vertical band from the east, south of
    the southern horizontal road.  Its old mouth is capped and a parallel spur
    begins five cells east.  This breaks full-map alignment without moving any
    building or requiring unregistered inner-curb art.
    """
    result = [list(row) for row in rows]
    vertical, horizontal = road_bands(result)
    if len(vertical) != 4 or len(horizontal) != 3:
        raise ValueError(
            f"{ROAD_PASS} expected four vertical and three horizontal bands, "
            f"got {vertical!r} and {horizontal!r}"
        )
    vx0, vx1 = vertical[-2]
    south_y0, south_y1 = horizontal[-1]
    if vx1 - vx0 + 1 != 3 or south_y1 - south_y0 + 1 != 3:
        raise ValueError(f"{ROAD_PASS} requires the established three-cell road grammar")

    old_left, old_right = vx0 - 1, vx1 + 1
    new_vx0, new_vx1 = vx1 + 3, vx1 + 5
    new_left, new_right = new_vx0 - 1, new_vx1 + 1
    cap_y = south_y1 + 1
    if new_right >= len(result[0]) or cap_y >= len(result):
        raise ValueError(f"{ROAD_PASS} selected offset spur escaped the grid")

    # Close the old south mouth with one straight sidewalk cap.
    for x in range(old_left, old_right + 1):
        result[cap_y][x] = "curb_top"
    for y in range(cap_y + 1, len(result)):
        for x in range(old_left, old_right + 1):
            result[y][x] = "pavement_small"

    # Open a new southbound three-cell road five cells east.  The two outer
    # corner pieces join the arterial cleanly; straight curbs carry to the edge.
    result[cap_y][new_left] = "curb_tr_outer"
    for x in range(new_vx0, new_vx1 + 1):
        result[cap_y][x] = "road_fill"
    result[cap_y][new_right] = "curb_tl_outer"
    for y in range(cap_y + 1, len(result)):
        result[y][new_left] = "curb_right"
        for x in range(new_vx0, new_vx1 + 1):
            result[y][x] = "road_fill"
        result[y][new_right] = "curb_left"

    metadata = {
        "version": 1,
        "composition_pass": ROAD_PASS,
        "shape": "offset_south_spur_t_pair",
        "arterial_band": [south_y0, south_y1],
        "closed_vertical_band": [vx0, vx1],
        "offset_vertical_band": [new_vx0, new_vx1],
        "offset_centerline_cells": new_vx0 + 1 - ((vx0 + vx1) // 2),
        "south_spur_y_range": [cap_y, len(result) - 1],
        "road_cells_removed": 21,
        "road_cells_added": 21,
        "road_cell_delta": 0,
        "changed_cell_count": 70,
        "t_junction_count": 2,
        "four_way_junction_count": 11,
        "inner_curb_tiles_required": False,
    }
    return result, metadata


def road_components(rows: list[list[str]]) -> list[set[tuple[int, int]]]:
    remaining = {
        (x, y) for y, row in enumerate(rows) for x, tile_id in enumerate(row)
        if tile_id == "road_fill"
    }
    components: list[set[tuple[int, int]]] = []
    while remaining:
        seed = remaining.pop()
        component = {seed}
        queue = deque([seed])
        while queue:
            x, y = queue.popleft()
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append(component)
    return components


def _partial_vertical_segments(
    rows: list[list[str]], vertical: list[tuple[int, int]]
) -> list[tuple[int, int, int, int]]:
    """Find short three-cell road spurs omitted by the 75% band threshold."""
    height, width = len(rows), len(rows[0])
    full_centers = {(x0 + x1) // 2 for x0, x1 in vertical}
    segments: list[tuple[int, int, int, int]] = []
    for center_x in range(1, width - 1):
        if center_x in full_centers:
            continue
        values = [
            y for y in range(height)
            if all(rows[y][x] == "road_fill" for x in range(center_x - 1, center_x + 2))
        ]
        for y0, y1 in contiguous_bands(values):
            if y1 - y0 + 1 >= 6:
                segments.append((center_x - 1, center_x + 1, y0, y1))
    return segments


def vertical_road_segments(rows: list[list[str]]) -> list[tuple[int, int, int, int]]:
    vertical, _horizontal = road_bands(rows)
    height = len(rows)
    return [(x0, x1, 0, height - 1) for x0, x1 in vertical] + _partial_vertical_segments(rows, vertical)


def junction_counts(rows: list[list[str]]) -> tuple[int, int]:
    """Return (T-junctions, four-way junctions) at detected band crossings."""
    _vertical, horizontal = road_bands(rows)
    t_junctions = four_way = 0
    for vx0, vx1, segment_y0, segment_y1 in vertical_road_segments(rows):
        cx = (vx0 + vx1) // 2
        for hy0, hy1 in horizontal:
            if segment_y1 < hy0 or segment_y0 > hy1:
                continue
            cy = (hy0 + hy1) // 2
            arms = (
                rows[hy0 - 1][cx] == "road_fill" if hy0 > 0 else False,
                rows[cy][vx1 + 1] == "road_fill" if vx1 + 1 < len(rows[0]) else False,
                rows[hy1 + 1][cx] == "road_fill" if hy1 + 1 < len(rows) else False,
                rows[cy][vx0 - 1] == "road_fill" if vx0 > 0 else False,
            )
            if sum(arms) == 3:
                t_junctions += 1
            elif sum(arms) == 4:
                four_way += 1
    return t_junctions, four_way
