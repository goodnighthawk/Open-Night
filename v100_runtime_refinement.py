from __future__ import annotations

"""Deterministic v1.0 runtime refinement shared by client and authoritative server."""

from collections import defaultdict, deque
from functools import lru_cache
import math

_INSTALLED = False


def _footprint(building: dict) -> set[tuple[int, int]]:
    x0, y0, x1, y1 = map(int, building["rect"])
    cells = {(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)}
    notch = building.get("notch")
    if not notch:
        return cells
    depth = int(notch["depth_cells"])
    corner = str(notch["corner"])
    xs = range(x0, x0 + depth) if corner.endswith("left") else range(x1 - depth + 1, x1 + 1)
    ys = range(y0, y0 + depth) if corner.startswith("top") else range(y1 - depth + 1, y1 + 1)
    cells.difference_update((x, y) for y in ys for x in xs)
    return cells


def _role_for_cell(x: int, y: int, cells: set[tuple[int, int]]) -> str:
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


def _bbox(cells: set[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs = [x for x, _ in cells]
    ys = [y for _, y in cells]
    return min(xs), min(ys), max(xs), max(ys)


def _block_components(rows: list[list[str]]) -> tuple[dict[tuple[int, int], int], dict[int, set[tuple[int, int]]]]:
    height, width = len(rows), len(rows[0])
    remaining = {
        (x, y) for y in range(height) for x in range(width)
        if rows[y][x] not in {"road_fill", "void"}
    }
    lookup: dict[tuple[int, int], int] = {}
    components: dict[int, set[tuple[int, int]]] = {}
    component_id = 0
    while remaining:
        seed = remaining.pop()
        queue = deque([seed])
        cells = {seed}
        while queue:
            x, y = queue.popleft()
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    cells.add(neighbor)
                    queue.append(neighbor)
        components[component_id] = cells
        for cell in cells:
            lookup[cell] = component_id
        component_id += 1
    return lookup, components


def _building_shifts(rows: list[list[str]], buildings: list[dict]) -> dict[str, tuple[int, int]]:
    lookup, components = _block_components(rows)
    groups: dict[int, list[dict]] = defaultdict(list)
    for building in buildings:
        ids = {lookup[cell] for cell in _footprint(building)}
        if len(ids) != 1:
            raise RuntimeError(f"building crosses road-bounded blocks: {building['building_id']}")
        groups[next(iter(ids))].append(building)

    shifts: dict[str, tuple[int, int]] = {}
    for component_id, group in groups.items():
        bx0, by0, bx1, by1 = _bbox(components[component_id])
        centers = [
            ((int(b["rect"][0]) + int(b["rect"][2])) / 2.0,
             (int(b["rect"][1]) + int(b["rect"][3])) / 2.0,
             b)
            for b in group
        ]
        spread_x = max(c[0] for c in centers) - min(c[0] for c in centers) if len(centers) > 1 else 0.0
        spread_y = max(c[1] for c in centers) - min(c[1] for c in centers) if len(centers) > 1 else 0.0
        axis = "x" if spread_x >= spread_y else "y"
        centers.sort(key=lambda item: (item[0], item[1]) if axis == "x" else (item[1], item[0]))

        for index, (cx, cy, building) in enumerate(centers):
            x0, y0, x1, y1 = map(int, building["rect"])
            bw, bh = x1 - x0 + 1, y1 - y0 + 1
            if len(centers) == 1:
                lx0, ly0, lx1, ly1 = bx0, by0, bx1, by1
            elif axis == "x":
                lx0 = bx0 if index == 0 else math.floor((centers[index - 1][0] + cx) / 2.0) + 1
                lx1 = bx1 if index == len(centers) - 1 else math.floor((cx + centers[index + 1][0]) / 2.0)
                ly0, ly1 = by0, by1
            else:
                ly0 = by0 if index == 0 else math.floor((centers[index - 1][1] + cy) / 2.0) + 1
                ly1 = by1 if index == len(centers) - 1 else math.floor((cy + centers[index + 1][1]) / 2.0)
                lx0, lx1 = bx0, bx1
            tx0 = int(round((lx0 + lx1 - bw + 1) / 2.0))
            ty0 = int(round((ly0 + ly1 - bh + 1) / 2.0))
            shifts[str(building["building_id"])] = (
                max(-1, min(1, tx0 - x0)),
                max(-1, min(1, ty0 - y0)),
            )
    return shifts


def _move_fire_escapes(world, rows: list[list[str]], buildings: list[dict]) -> int:
    by_id = {str(b["building_id"]): b for b in buildings}
    height, width = len(rows), len(rows[0])
    moved = 0
    for item in world.objects:
        if str(item.get("asset")) != "placeholder_fire_escape":
            continue
        building = by_id[str(item["building_id"])]
        footprint = _footprint(building)
        cx = sum(x for x, _ in footprint) / len(footprint)
        cy = sum(y for _, y in footprint) / len(footprint)
        candidates = []
        for priority, (dx, dy, edge, rotation) in enumerate(
            ((1, 0, "east", 0), (-1, 0, "west", 0), (0, 1, "south", 90), (0, -1, "north", 90))
        ):
            for x, y in footprint:
                nx, ny = x + dx, y + dy
                if (nx, ny) in footprint or not (0 <= nx < width and 0 <= ny < height):
                    continue
                tile = rows[ny][nx]
                if tile == "road_fill" or tile == "void" or tile.startswith("bld_"):
                    continue
                distance = abs(x - cx) + abs(y - cy)
                candidates.append((priority, distance, nx, ny, edge, rotation))
        if not candidates:
            raise RuntimeError(f"no exterior fire-escape anchor for {building['building_id']}")
        _priority, _distance, gx, gy, edge, rotation = min(candidates)
        item["gx"], item["gy"] = gx, gy
        item["offset_x_px"] = 64 if edge in {"east", "west"} else 0
        item["offset_y_px"] = 0 if edge in {"east", "west"} else 64
        item["edge"] = edge
        item["rotation"] = rotation
        item["collision_policy"] = "outside_building_footprint"
        moved += 1
    return moved


def apply_world_refinement(world):
    if getattr(world, "_v100_layout_refined", False):
        return world
    rows = world.layers.get("ground")
    buildings = list((world.data.get("building_synthesis") or {}).get("buildings") or [])
    if not rows or not buildings:
        world._v100_layout_refined = True
        return world

    roof_rows = world.layers.get("roof")
    old_footprints = {str(b["building_id"]): _footprint(b) for b in buildings}
    shifts = _building_shifts(rows, buildings)

    shifted_footprints = {
        building_id: {(x + shifts[building_id][0], y + shifts[building_id][1]) for x, y in cells}
        for building_id, cells in old_footprints.items()
    }
    building_ids = sorted(shifted_footprints)
    overlap_cells: set[tuple[int, int]] = set()
    adjacent_pairs: list[tuple[str, str]] = []
    for index, building_id in enumerate(building_ids):
        cells = shifted_footprints[building_id]
        neighbours = {
            (x + dx, y + dy)
            for x, y in cells
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        }
        for other_id in building_ids[index + 1:]:
            other = shifted_footprints[other_id]
            overlap_cells.update(cells & other)
            if neighbours & other:
                adjacent_pairs.append((building_id, other_id))
    if overlap_cells or adjacent_pairs:
        raise RuntimeError(
            "building centering violated the one-cell setback contract: "
            f"overlap_cells={sorted(overlap_cells)[:8]} adjacent_pairs={adjacent_pairs[:8]}"
        )

    for cells in old_footprints.values():
        for x, y in cells:
            rows[y][x] = "pavement_small"
            if roof_rows is not None:
                roof_rows[y][x] = "void"

    for building in buildings:
        building_id = str(building["building_id"])
        dx, dy = shifts[building_id]
        x0, y0, x1, y1 = map(int, building["rect"])
        building["rect"] = [x0 + dx, y0 + dy, x1 + dx, y1 + dy]
        footprint = _footprint(building)
        theme = str(building["theme"])
        for x, y in footprint:
            if rows[y][x] == "road_fill":
                raise RuntimeError(f"centered building entered road at {(x, y)}")
            tile_id = f"bld_{theme}_{_role_for_cell(x, y, footprint)}"
            rows[y][x] = tile_id
            if roof_rows is not None:
                roof_rows[y][x] = tile_id
        building["layout_refinement"] = "road_bounded_lot_center_v1"
        building["center_shift_cells"] = [dx, dy]

    refined_footprints = {str(building["building_id"]): _footprint(building) for building in buildings}
    roof_assignment_counts: dict[str, int] = defaultdict(int)
    for item in world.objects:
        building_id = str(item.get("building_id", ""))
        if building_id in shifts:
            dx, dy = shifts[building_id]
            item["gx"] = int(item["gx"]) + dx
            item["gy"] = int(item["gy"]) + dy

        if item.get("composition_pass") == "roof_palette_v1":
            # Keep equipment visibly legible while fully inside its authoritative
            # inboard roof cell. Recenter after scaling so no decal clips a wall.
            inset = max(24, int(round(world.cell_px * 0.1875)))
            minimum = max(64, int(round(world.cell_px * 0.50)))
            width = min(world.cell_px - inset * 2, max(minimum, int(round(float(item.get("width_px", minimum)) * 1.10))))
            height = min(world.cell_px - inset * 2, max(minimum, int(round(float(item.get("height_px", minimum)) * 1.10))))
            footprint = refined_footprints.get(building_id, set())
            core = sorted(
                ((gx, gy) for gx, gy in footprint
                 if all((gx + dx, gy + dy) in footprint for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))),
                key=lambda point: (point[1], point[0]),
            )
            if core:
                slot = roof_assignment_counts[building_id] % len(core)
                item["gx"], item["gy"] = core[slot]
                roof_assignment_counts[building_id] += 1
            item["width_px"], item["height_px"] = width, height
            item["offset_x_px"] = (world.cell_px - width) // 2
            item["offset_y_px"] = (world.cell_px - height) // 2
            item["placement_policy"] = "centered_core_roof_cell_v12" if core else "centered_safe_small_roof_v12"

        marking = str(item.get("street_marking", ""))
        if marking == "dashed_center_line_vertical":
            width = int(item.get("width_px", world.cell_px // 4))
            height = int(item.get("height_px", world.cell_px * 3 // 4))
            item["offset_x_px"] = (world.cell_px - width) // 2
            item["offset_y_px"] = (world.cell_px - height) // 2
            item["registration_policy"] = "road_cell_center_v12"
        elif marking == "dashed_center_line_horizontal":
            width = int(item.get("width_px", world.cell_px // 4))
            height = int(item.get("height_px", world.cell_px * 3 // 4))
            item["offset_x_px"] = (world.cell_px - height) // 2
            item["offset_y_px"] = (world.cell_px - width) // 2
            item["registration_policy"] = "road_cell_center_v12"

    # Each three-cell primary road is 384 px before normalization: six 64 px
    # lanes. Four white dividers plus the yellow median make all six lanes
    # visible; the traffic route builder supplies three usable lanes each way.
    lane_dividers = []
    for item in list(world.objects):
        marking = str(item.get("street_marking", ""))
        if marking not in {"dashed_center_line_vertical", "dashed_center_line_horizontal"}:
            continue
        for divider_index, displacement in enumerate((-128, -64, 64, 128), start=1):
            divider = dict(item)
            divider["asset"] = "mark_white_crossing_piece"
            divider["width_px"] = 10
            divider["street_marking"] = f"six_lane_divider_{'vertical' if marking.endswith('vertical') else 'horizontal'}"
            divider["lane_divider_index"] = divider_index
            divider["six_lane_network"] = True
            if marking.endswith("vertical"):
                divider["offset_x_px"] = world.cell_px // 2 + displacement - 5
            else:
                divider["offset_y_px"] = world.cell_px // 2 + displacement - 5
            lane_dividers.append(divider)
    world.objects.extend(lane_dividers)
    world.data.setdefault("runtime_refinement", {})["six_lane_divider_count"] = len(lane_dividers)

    fire_escape_count = _move_fire_escapes(world, rows, buildings)
    lamp_count = 0
    seen_lights: set[str] = set()
    for item in world.objects:
        if item.get("lighting_kind") != "sidewalk_lamp" and not item.get("emits_light"):
            continue
        lighting_id = str(item.get("lighting_id", ""))
        if not lighting_id or lighting_id in seen_lights:
            raise RuntimeError(f"streetlamp emitter record is missing/duplicated: {lighting_id!r}")
        seen_lights.add(lighting_id)
        item["asset"] = "street_lamp_10_night"
        item["emits_light"] = True
        item["fixture_light_sync"] = "same_grid_object_record"
        lamp_count += 1

    if roof_rows is not None:
        ground_mask = {(x, y) for y, row in enumerate(rows) for x, tile in enumerate(row) if tile.startswith("bld_")}
        roof_mask = {(x, y) for y, row in enumerate(roof_rows) for x, tile in enumerate(row) if tile.startswith("bld_")}
        if ground_mask != roof_mask:
            raise RuntimeError("Ground/Roof masks diverged during runtime refinement")

    world.data.setdefault("runtime_refinement", {}).update({
        "composition_pass": "road_bounded_lot_center_v1",
        "centered_building_count": sum(delta != (0, 0) for delta in shifts.values()),
        "building_overlap_cell_count": len(overlap_cells),
        "building_adjacent_pair_count": len(adjacent_pairs),
        "minimum_building_setback_cells": 1,
        "building_edge_alpha_policy": "source_alpha_preserved_exterior_frame_removed",
        "fire_escape_outside_collision_count": fire_escape_count,
        "street_lamp_asset_sync_count": lamp_count,
        "fixture_and_emitter_authority": "same_grid_object_record",
    })
    world._v100_layout_refined = True
    return world


def _install_outline_refinement() -> None:
    try:
        from grid_renderer import GridRenderer
    except Exception:
        return

    def is_outline(color) -> bool:
        if color.a <= 150:
            return False
        maximum = max(color.r, color.g, color.b)
        minimum = min(color.r, color.g, color.b)
        luminance = (54 * color.r + 183 * color.g + 19 * color.b) // 256
        # Only near-black perimeter ink is a frame. The former broad threshold
        # classified legitimate dark-blue/brown roof fills as outlines and made
        # whole building tiles bleed into their neighbours.
        return maximum < 165 and luminance < 135 and maximum - minimum < 28

    # GridRenderer removes only exterior-connected frame ink while preserving
    # source alpha and isolated rooftop detail. Keep the classifier narrow.
    GridRenderer._is_dark_building_outline = staticmethod(is_outline)
    try:
        GridRenderer._tile_surface.cache_clear()
        GridRenderer._tile_surface_scaled.cache_clear()
    except AttributeError:
        pass


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    import grid_runtime

    original = grid_runtime.load_ground_grid

    @lru_cache(maxsize=1)
    def refined_loader():
        return apply_world_refinement(original())

    grid_runtime.load_ground_grid = refined_loader
    _install_outline_refinement()
    _INSTALLED = True
