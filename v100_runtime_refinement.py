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
        item["placeholder"] = False
        item["transition"] = "stationary_jump_ground_to_roof_and_back"
        item["transition_levels"] = [0, 1]
        moved += 1
    return moved


def _install_safe_login_spawns(world) -> list[list[float]]:
    """Replace legacy road-center starts with distributed interior sidewalks."""
    inset = 4
    candidates = []
    for gy in range(inset, world.height - inset):
        for gx in range(inset, world.width - inset):
            cx, cy = world.cell_center(gx, gy)
            if world.circle_spawnable("ground", cx, cy, 18.0):
                candidates.append((gx, gy, cx, cy))
    targets = (
        (0.22, 0.50), (0.35, 0.23), (0.16, 0.78),
        (0.72, 0.50), (0.85, 0.23), (0.63, 0.78),
    )
    selected: list[tuple[int, int, float, float]] = []
    for tx, ty in targets:
        target_x, target_y = world.width * tx, world.height * ty
        available = [
            row for row in candidates
            if all(abs(row[0] - other[0]) + abs(row[1] - other[1]) >= 7 for other in selected)
        ]
        if not available:
            raise RuntimeError("could not distribute safe login spawns across the grid")
        selected.append(min(available, key=lambda row: ((row[0] - target_x) ** 2 + (row[1] - target_y) ** 2, row[1], row[0])))
    spawns = [[float(cx), float(cy)] for _gx, _gy, cx, cy in selected]
    world.login_spawns = spawns
    world.data["login_spawns"] = spawns
    return spawns


def _install_road_edge_curbs(rows: list[list[str]]) -> dict[str, int]:
    """Dress pavement/road boundaries with straight and rounded curb tiles."""
    height, width = len(rows), len(rows[0])
    source = [list(row) for row in rows]
    counts: dict[str, int] = defaultdict(int)
    for gy in range(height):
        for gx in range(width):
            if not source[gy][gx].startswith("pavement"):
                continue
            north = gy > 0 and source[gy - 1][gx] == "road_fill"
            east = gx + 1 < width and source[gy][gx + 1] == "road_fill"
            south = gy + 1 < height and source[gy + 1][gx] == "road_fill"
            west = gx > 0 and source[gy][gx - 1] == "road_fill"
            tile_id = None
            if north and west:
                tile_id = "curb_tl_outer"
            elif north and east:
                tile_id = "curb_tr_outer"
            elif south and west:
                tile_id = "curb_bl_outer"
            elif south and east:
                tile_id = "curb_br_outer"
            elif north:
                tile_id = "curb_top"
            elif south:
                tile_id = "curb_bottom"
            elif west:
                tile_id = "curb_left"
            elif east:
                tile_id = "curb_right"
            if tile_id is not None:
                rows[gy][gx] = tile_id
                counts[tile_id] += 1
    return dict(counts)


def _install_city_block_street_item_defs(world) -> None:
    """Register the three transparent exports repacked from street_items.svg."""
    from grid_world import ObjectDef

    definitions = {
        "street_item_lamp": ("street_lamp.png", 112, 423, 155),
        "street_item_telephone_box": ("telephone_box.png", 231, 173, 150),
        "street_item_traffic_cone": ("traffic_cone.png", 206, 292, 145),
    }
    for object_id, (filename, width, height, z) in definitions.items():
        world.catalog.objects[object_id] = ObjectDef(
            object_id=object_id,
            image=f"city_block://street_decorations/{filename}",
            kind="street_furniture",
            layer="ground",
            z=z,
            native_width_px=width,
            native_height_px=height,
        )


def _install_report_152_infill(world, rows: list[list[str]], buildings: list[dict]) -> list[str]:
    """Fill the two large ordinary empty lots while reserving the center landmark lot.

    The one-cell inset is 128 px after world normalization, slightly more than
    three 36 px player widths. This keeps every facade clear of the curb while
    turning the photographed empty blocks into useful enterable buildings.
    """
    lookup, components = _block_components(rows)
    occupied = {
        next(iter({lookup[cell] for cell in _footprint(building)}))
        for building in buildings
    }
    candidates = []
    for component_id, cells in components.items():
        if component_id in occupied or len(cells) < 80:
            continue
        x0, y0, x1, y1 = _bbox(cells)
        # The center-north lot is the restored GWB's landmark/approach reserve.
        # Edge fragments are not complete city blocks.
        if x0 <= world.width // 2 <= x1 or x0 == 0 or x1 == world.width - 1:
            continue
        if x1 - x0 < 8 or y1 - y0 < 7:
            continue
        candidates.append((component_id, (x0, y0, x1, y1)))

    added: list[str] = []
    themes = ("red", "dark_green")
    for index, (_component_id, (x0, y0, x1, y1)) in enumerate(
        sorted(candidates, key=lambda row: (row[1][0], row[1][1]))[:2], 1
    ):
        rect = [x0 + 1, y0 + 1, x1 - 1, y1 - 1]
        building_id = f"grid_infill_{index:02d}"
        theme = themes[(index - 1) % len(themes)]
        generated_cells = (rect[2] - rect[0] + 1) * (rect[3] - rect[1] + 1)
        buildings.append({
            "building_id": building_id,
            "theme": theme,
            "rect": rect,
            "notch": None,
            "footprint_type": "rectangle",
            "orientation_policy": "filename_semantics_no_rotation",
            "generated_cells": generated_cells,
            "envelope_cells": generated_cells,
            "infill_policy": "empty_road_bounded_block_three_player_width_setback_v25",
        })
        door_gx = (rect[0] + rect[2]) // 2
        world.objects.append({
            "asset": "placeholder_street_door",
            "gx": door_gx,
            "gy": rect[3],
            "offset_x_px": 80,
            "offset_y_px": 112,
            "width_px": 96,
            "height_px": 144,
            "building_id": building_id,
            "edge": "south",
            "rotation": 0,
            "placeholder": False,
            "transition": "ground_to_first_floor_door",
            "functional_entry": True,
        })
        added.append(building_id)

    world.data.setdefault("building_synthesis", {})["buildings"] = buildings
    return added


def _install_gwb_landmark(world) -> int:
    """Restore the George Washington Bridge art over the central highway."""
    from grid_world import ObjectDef

    definitions = {
        "gwb_tower_night": "lan_gwb_tower_01_night.png",
        "gwb_truss_night": "lan_gwb_truss_02_night.png",
        "gwb_pier_night": "lan_gwb_pier_03_night.png",
    }
    for object_id, filename in definitions.items():
        world.catalog.objects[object_id] = ObjectDef(
            object_id=object_id,
            image=f"cosmetic_packs/nyc_gta2_callback/sprites/{filename}",
            kind="landmark",
            layer="ground",
            z=240,
            native_width_px=128,
            native_height_px=128,
        )

    center_y = world.height // 2
    center_x = world.width // 2
    placements = [
        ("gwb_pier_night", center_x - 5, center_y - 1, 512, 512),
        ("gwb_tower_night", center_x - 3, center_y - 2, 640, 640),
        ("gwb_truss_night", center_x - 2, center_y - 1, 512, 512),
        ("gwb_truss_night", center_x - 1, center_y - 1, 512, 512),
        ("gwb_truss_night", center_x, center_y - 1, 512, 512),
        ("gwb_truss_night", center_x + 1, center_y - 1, 512, 512),
        ("gwb_truss_night", center_x + 2, center_y - 1, 512, 512),
        ("gwb_tower_night", center_x + 3, center_y - 2, 640, 640),
        ("gwb_pier_night", center_x + 5, center_y - 1, 512, 512),
    ]
    for index, (asset, gx, gy, width, height) in enumerate(placements, 1):
        world.objects.append({
            "asset": asset,
            "gx": gx,
            "gy": gy,
            "offset_x_px": (world.cell_px - width) // 2,
            "offset_y_px": (world.cell_px - height) // 2,
            "width_px": width,
            "height_px": height,
            "overhead": True,
            "decorative_only": True,
            "landmark_kind": "george_washington_bridge",
            "landmark_piece_index": index,
            "placement_policy": "central_highway_gwb_restore_v28",
        })
    return len(placements)


def _install_hudson_river(world, rows, roof_rows) -> dict[str, object]:
    """Cut a continuous Hudson channel beneath the central GWB span."""
    from grid_world import TileDef

    river_columns = tuple(range(world.width // 2 - 3, world.width // 2))
    bridge_rows = tuple(range(world.height // 2 - 3, world.height // 2 + 4))
    world.catalog.entries["hudson_water_night"] = TileDef(
        tile_id="hudson_water_night",
        image="assets/environment/approved/water_64.png",
        collision="blocked",
        kind="water",
        layer="ground",
        z=8,
    )

    water_cells = 0
    for gy in range(world.height):
        for gx in river_columns:
            # The seven-cell central highway is the GWB deck. It remains Road
            # collision so existing traffic authority crosses only at the bridge.
            if gy in bridge_rows:
                continue
            rows[gy][gx] = "hudson_water_night"
            if roof_rows is not None:
                roof_rows[gy][gx] = "void"
            water_cells += 1

    # Derived road marks/props authored before the channel existed must not float
    # on the water. Keep anything on the actual bridge deck and the GWB art itself.
    kept = []
    removed = 0
    for item in world.objects:
        gx = int(item.get("gx", -1))
        gy = int(item.get("gy", -1))
        if gx in river_columns and gy not in bridge_rows and item.get("landmark_kind") != "george_washington_bridge":
            removed += 1
            continue
        kept.append(item)
    world.objects[:] = kept
    return {
        "columns": list(river_columns),
        "bridge_rows": list(bridge_rows),
        "water_cell_count": water_cells,
        "removed_floating_object_count": removed,
        "placement_policy": "continuous_central_hudson_under_gwb_v28",
    }


def _spaced_cells(candidates, occupied: set[tuple[int, int]], count: int, spacing: int) -> list[tuple[int, int]]:
    selected: list[tuple[int, int]] = []
    for gx, gy in candidates:
        if (gx, gy) in occupied:
            continue
        if any(abs(gx - ox) + abs(gy - oy) < spacing for ox, oy in occupied | set(selected)):
            continue
        selected.append((gx, gy))
        if len(selected) >= count:
            break
    return selected


def _add_city_block_street_items(world, occupied_lamp_cells: set[tuple[int, int]]) -> dict[str, int]:
    _install_city_block_street_item_defs(world)
    sidewalks = [
        (gx, gy) for gy in range(world.height) for gx in range(world.width)
        if world.collision_at("ground", *world.cell_center(gx, gy)) == "sidewalk"
    ]
    # Spread telephone points over both procedural districts. The modular score
    # avoids a visible scan-line pattern while remaining deterministic.
    sidewalks.sort(key=lambda cell: ((cell[0] * 37 + cell[1] * 61) % 997, cell[1], cell[0]))
    telephone_cells = _spaced_cells(sidewalks, occupied_lamp_cells, 16, 6)
    occupied = occupied_lamp_cells | set(telephone_cells)

    road_edges = []
    for gy in range(world.height):
        for gx in range(world.width):
            if world.collision_at("ground", *world.cell_center(gx, gy)) != "road":
                continue
            if any(
                0 <= gx + dx < world.width and 0 <= gy + dy < world.height
                and world.collision_at("ground", *world.cell_center(gx + dx, gy + dy)) == "sidewalk"
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ):
                road_edges.append((gx, gy))
    road_edges.sort(key=lambda cell: ((cell[0] * 53 + cell[1] * 29) % 991, cell[1], cell[0]))

    # Report #166: three recognizable curb-lane closures replace twenty-four
    # unrelated single cones. Each closure is a compact five-cone line on one
    # straight road edge, well separated from the other two closures.
    closure_anchors: list[tuple[int, int, str]] = []
    for gx, gy in road_edges:
        edge = next((
            direction for direction, (dx, dy) in (
                ("north", (0, -1)), ("south", (0, 1)),
                ("west", (-1, 0)), ("east", (1, 0)),
            )
            if 0 <= gx + dx < world.width and 0 <= gy + dy < world.height
            and world.collision_at("ground", *world.cell_center(gx + dx, gy + dy)) == "sidewalk"
        ), "")
        if not edge:
            continue
        if any(abs(gx - ox) + abs(gy - oy) < 22 for ox, oy, _ in closure_anchors):
            continue
        closure_anchors.append((gx, gy, edge))
        if len(closure_anchors) >= 3:
            break

    for index, (gx, gy) in enumerate(telephone_cells, 1):
        road_direction = next(
            (
                direction for direction, (dx, dy) in (
                    ("north", (0, -1)), ("east", (1, 0)),
                    ("south", (0, 1)), ("west", (-1, 0)),
                )
                if 0 <= gx + dx < world.width and 0 <= gy + dy < world.height
                and world.collision_at("ground", *world.cell_center(gx + dx, gy + dy)) == "road"
            ),
            "north",
        )
        # Keep the handset/box visually inside the pavement instead of centered
        # on the curb edge. Values are authored in the 256 px source-cell space
        # and are normalized together with every other GridWorld object.
        inward = {
            "north": (0, 1), "east": (-1, 0),
            "south": (0, -1), "west": (1, 0),
        }[road_direction]
        width_px, height_px = 128, 96
        center_x = world.cell_px // 2 + inward[0] * 104
        center_y = world.cell_px // 2 + inward[1] * 104
        world.objects.append({
            "asset": "street_item_telephone_box", "gx": gx, "gy": gy,
            "offset_x_px": center_x - width_px // 2,
            "offset_y_px": center_y - height_px // 2,
            "width_px": width_px, "height_px": height_px,
            "street_item_kind": "telephone_box", "street_item_index": index,
            "composition_pass": "city_block_street_items_svg_v1", "decorative_only": True,
            "placement_policy": "deep_pavement_inset_public_phone_v25",
            "road_edge_direction": road_direction,
            # A compact cyan pool makes the pavement phone discoverable at
            # night. Fixture and light remain one authoritative object record.
            "emits_light": True,
            "lighting_kind": "public_phone",
            "light_offset_x_px": width_px // 2,
            "light_offset_y_px": height_px // 2,
            "light_radius_px": 190,
            "light_color_rgb": [62, 194, 224],
            "light_intensity": 0.24,
            "light_registration": "public_phone_same_object_v23",
        })
    cone_index = 0
    for closure_index, (gx, gy, edge) in enumerate(closure_anchors, 1):
        inward_x, inward_y = {
            "north": (0, 1), "south": (0, -1),
            "west": (1, 0), "east": (-1, 0),
        }[edge]
        road_cells = [(gx, gy)]
        for step in range(1, 10):
            nx, ny = gx + inward_x * step, gy + inward_y * step
            if not world.in_bounds(nx, ny):
                break
            if world.collision_at("ground", *world.cell_center(nx, ny)) != "road":
                break
            road_cells.append((nx, ny))
        first_x = gx * world.cell_px + world.cell_px * 0.20
        first_y = gy * world.cell_px + world.cell_px * 0.20
        last_gx, last_gy = road_cells[-1]
        last_x = last_gx * world.cell_px + world.cell_px * 0.80
        last_y = last_gy * world.cell_px + world.cell_px * 0.80
        if inward_x < 0:
            first_x = gx * world.cell_px + world.cell_px * 0.80
            last_x = last_gx * world.cell_px + world.cell_px * 0.20
        if inward_y < 0:
            first_y = gy * world.cell_px + world.cell_px * 0.80
            last_y = last_gy * world.cell_px + world.cell_px * 0.20
        for cone_slot in range(5):
            fraction = cone_slot / 4.0
            center_world_x = first_x + (last_x - first_x) * fraction if inward_x else (gx + 0.5) * world.cell_px
            center_world_y = first_y + (last_y - first_y) * fraction if inward_y else (gy + 0.5) * world.cell_px
            cone_gx = max(0, min(world.width - 1, int(center_world_x // world.cell_px)))
            cone_gy = max(0, min(world.height - 1, int(center_world_y // world.cell_px)))
            cone_index += 1
            world.objects.append({
                "asset": "street_item_traffic_cone", "gx": cone_gx, "gy": cone_gy,
                "offset_x_px": int(round(center_world_x - cone_gx * world.cell_px - 42)),
                "offset_y_px": int(round(center_world_y - cone_gy * world.cell_px - 60)),
                "width_px": 84, "height_px": 120,
                "street_item_kind": "traffic_cone", "street_item_index": cone_index,
                "road_closure_slot": cone_slot + 1,
                "road_closure_id": f"road_closure_{closure_index:02d}",
                "road_closure_edge": edge,
                "composition_pass": "cross_road_closures_v28", "decorative_only": False,
                "collision_radius_px": 22, "collision_kind": "traffic_cone",
                "placement_policy": "five_cone_evenly_spaced_across_road_v28",
            })
    return {
        "telephone_box_count": len(telephone_cells),
        "traffic_cone_count": cone_index,
        "traffic_cone_closure_count": len(closure_anchors),
    }


def _lamp_anchor_geometry(rotation: int, source_w: int, source_h: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return transformed (base, light-head) anchors for clockwise rotation."""
    rotation = int(rotation) % 360
    # In street_lamp.png the round sidewalk mount is at the top and the
    # rectangular luminaire is at the bottom.  Keeping those semantic anchors
    # explicit prevents the fixture from pointing away from its registered pool.
    original_base = (source_w // 2, int(source_h * .10))
    original_fixture = (source_w // 2, int(source_h * .90))
    if rotation == 0:
        return original_base, original_fixture
    if rotation == 90:
        return ((source_h - original_base[1], original_base[0]),
                (source_h - original_fixture[1], original_fixture[0]))
    if rotation == 180:
        return ((source_w - original_base[0], source_h - original_base[1]),
                (source_w - original_fixture[0], source_h - original_fixture[1]))
    if rotation == 270:
        return ((original_base[1], source_w - original_base[0]),
                (original_fixture[1], source_w - original_fixture[0]))
    raise ValueError(f"streetlamp rotation must be cardinal, got {rotation}")


def apply_world_refinement(world):
    if getattr(world, "_v100_layout_refined", False):
        return world
    rows = world.layers.get("ground")
    buildings = list((world.data.get("building_synthesis") or {}).get("buildings") or [])
    if not rows or not buildings:
        world._v100_layout_refined = True
        return world

    infill_buildings = _install_report_152_infill(world, rows, buildings)

    from v110_pedestrian_connectivity import road_bands
    horizontal_roads, vertical_roads = road_bands(world)
    junction_cells = {
        (gx, gy)
        for hband in horizontal_roads for vband in vertical_roads
        for gx in range(vband.start, vband.end + 1)
        for gy in range(hband.start, hband.end + 1)
    }
    # Rebuild the derived line layer and leave intersections visually clean.
    # This is the deterministic road-art consolidation authority for #55/#56.
    world.objects[:] = [
        item for item in world.objects
        if not str(item.get("street_marking", "")).startswith("six_lane_divider_")
        and str(item.get("density_kind", "")) != "street_edge_awning"
        and not (
            str(item.get("street_marking", "")).startswith("dashed_center_line_")
            and (int(item.get("gx", -1)), int(item.get("gy", -1))) in junction_cells
        )
    ]

    roof_rows = world.layers.get("roof")
    old_footprints = {str(b["building_id"]): _footprint(b) for b in buildings}
    shifts = _building_shifts(rows, buildings)
    # The report-46 road contraction creates larger pavement buffers. Retain an
    # already-safe authored footprint when a block-centering delta would move it
    # back into the smaller road band.
    for building_id, cells in old_footprints.items():
        dx, dy = shifts[building_id]
        if any(rows[y + dy][x + dx] == "road_fill" for x, y in cells):
            shifts[building_id] = (0, 0)

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

    # Break up large repeated sidewalk fields with deterministic variants from
    # the same approved city-block pavement set. Collision stays sidewalk-only.
    pavement_variant_count = 0
    for gy, row in enumerate(rows):
        for gx, tile_id in enumerate(row):
            if tile_id != "pavement_small":
                continue
            score = (gx * 37 + gy * 53 + gx * gy * 3) % 65
            if score in {0, 17, 41}:
                rows[gy][gx] = "pavement_pattern"
                pavement_variant_count += 1
            elif score % 5 == 0:
                rows[gy][gx] = "pavement_v"
                pavement_variant_count += 1

    refined_footprints = {str(building["building_id"]): _footprint(building) for building in buildings}
    roof_assignment_counts: dict[str, int] = defaultdict(int)
    for item in world.objects:
        building_id = str(item.get("building_id", ""))
        if building_id in shifts:
            dx, dy = shifts[building_id]
            item["gx"] = int(item["gx"]) + dx
            item["gy"] = int(item["gy"]) + dy

        if str(item.get("asset", "")) == "placeholder_street_door" and building_id in refined_footprints:
            footprint = refined_footprints[building_id]
            width = int(item.get("width_px", 96))
            height = int(item.get("height_px", 144))
            center_x = sum(x for x, _y in footprint) / len(footprint)
            center_y = sum(y for _x, y in footprint) / len(footprint)
            candidates = []
            for priority, (dx, dy, edge, rotation) in enumerate((
                (0, 1, "south", 0), (0, -1, "north", 180),
                (1, 0, "east", 270), (-1, 0, "west", 90),
            )):
                for gx, gy in footprint:
                    nx, ny = gx + dx, gy + dy
                    if (nx, ny) in footprint or not (0 <= nx < world.width and 0 <= ny < world.height):
                        continue
                    exterior = str(rows[ny][nx])
                    if not (exterior.startswith("pavement") or exterior.startswith("curb_")):
                        continue
                    candidates.append((priority, abs(gx - center_x) + abs(gy - center_y), gx, gy, edge, rotation))
            if not candidates:
                raise RuntimeError(f"no pavement-facing wall door for {building_id}")
            _priority, _distance, door_x, door_y, edge, rotation = min(candidates)
            offsets = {
                "south": ((world.cell_px - width) // 2, world.cell_px - height),
                "north": ((world.cell_px - width) // 2, 0),
                "east": (world.cell_px - height, (world.cell_px - width) // 2),
                "west": (0, (world.cell_px - width) // 2),
            }
            offset_x, offset_y = offsets[edge]
            item.update({
                "gx": door_x,
                "gy": door_y,
                "offset_x_px": offset_x,
                "offset_y_px": offset_y,
                "edge": edge,
                "rotation": rotation,
                "placeholder": False,
                "functional_entry": True,
                "transition": "ground_to_first_floor_door",
                "placement_policy": "building_wall_boundary_functional_door_v25",
            })

        if item.get("silhouette_kind") == "facade_break" and building_id in refined_footprints:
            # Report #176: a three-times-larger canopy is wall-attached, keeps
            # half its depth on the facade, and is always walk-under art.
            footprint = refined_footprints[building_id]
            south_y = max(y for _x, y in footprint)
            south_cells = sorted(x for x, y in footprint if y == south_y)
            width = int(item.get("width_px", 224)) * 3
            height = int(item.get("height_px", 88)) * 3
            item.update({
                "gx": south_cells[len(south_cells) // 2],
                "gy": south_y,
                "rotation": 0,
                "width_px": width,
                "height_px": height,
                "offset_x_px": (world.cell_px - width) // 2,
                "offset_y_px": world.cell_px - height // 2,
                "edge": "south",
                "overhead": True,
                "decorative_only": True,
                "placement_policy": "triple_scale_wall_attached_walk_under_canopy_v25",
            })

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

    # Report #176: remove the derived off-cell white divider copies. The original
    # centered road markings remain, while the displaced bars no longer cross
    # sidewalks or appear as thick white map seams.
    lane_dividers = []
    world.data.setdefault("runtime_refinement", {})["six_lane_divider_count"] = 0
    world.data["runtime_refinement"]["six_lane_divider_policy"] = "removed_thick_off_cell_bars_v28"

    curb_counts = _install_road_edge_curbs(rows)
    safe_login_spawns = _install_safe_login_spawns(world)
    fire_escape_count = _move_fire_escapes(world, rows, buildings)
    lamp_count = 0
    seen_lights: set[str] = set()
    occupied_lamp_cells: set[tuple[int, int]] = set()
    for item in world.objects:
        if item.get("lighting_kind") != "sidewalk_lamp" and not item.get("emits_light"):
            continue
        lighting_id = str(item.get("lighting_id", ""))
        if not lighting_id or lighting_id in seen_lights:
            raise RuntimeError(f"streetlamp emitter record is missing/duplicated: {lighting_id!r}")
        seen_lights.add(lighting_id)
        # Anchor the base on the nearest free road-edge sidewalk and point the
        # fixture over that road. Fixture and emitter share this exact record.
        source_x, source_y = int(item.get("gx", 0)), int(item.get("gy", 0))
        candidates = []
        for radius in range(0, 13):
            for dx in range(-radius, radius + 1):
                dy = radius - abs(dx)
                for sign in ({1} if dy == 0 else {-1, 1}):
                    gx, gy = source_x + dx, source_y + dy * sign
                    if not (0 <= gx < world.width and 0 <= gy < world.height):
                        continue
                    if (gx, gy) in occupied_lamp_cells:
                        continue
                    cx, cy = world.cell_center(gx, gy)
                    if world.collision_at("ground", cx, cy) == "sidewalk":
                        road_dirs = []
                        for direction, (nx, ny) in (
                            ("north", (gx, gy - 1)), ("east", (gx + 1, gy)),
                            ("south", (gx, gy + 1)), ("west", (gx - 1, gy)),
                        ):
                            if 0 <= nx < world.width and 0 <= ny < world.height:
                                tx, ty = world.cell_center(nx, ny)
                                if world.collision_at("ground", tx, ty) == "road":
                                    road_dirs.append(direction)
                        if road_dirs:
                            candidates.append((radius, gy, gx, road_dirs[0]))
            if candidates:
                break
        if not candidates:
            raise RuntimeError(f"streetlamp has no nearby sidewalk placement: {lighting_id}")
        _, gy, gx, road_direction = min(candidates)
        item["gx"], item["gy"] = gx, gy
        # The source fixture points south. Rotate that end over the adjacent road.
        rotation = {"north": 180, "east": 270, "south": 0, "west": 90}[road_direction]
        item["rotation"] = rotation
        # Reports #119/#128: the prior 204x768 presentation dominated an
        # entire sidewalk cell. Render the same source at exactly half size and
        # register its mount farther inside the sidewalk while the head still
        # reaches the adjacent road.
        source_w, source_h = 102, 384
        base, fixture = _lamp_anchor_geometry(rotation, source_w, source_h)
        inward = {
            "north": (0, 1), "east": (-1, 0),
            "south": (0, -1), "west": (1, 0),
        }[road_direction]
        sidewalk_inset = 52
        target_base_x = world.cell_px // 2 + inward[0] * sidewalk_inset
        target_base_y = world.cell_px // 2 + inward[1] * sidewalk_inset
        offset_x = target_base_x - base[0]
        offset_y = target_base_y - base[1]
        light_x, light_y = fixture
        item["offset_x_px"] = offset_x
        item["offset_y_px"] = offset_y
        item["width_px"] = source_w
        item["height_px"] = source_h
        item["placement_policy"] = "half_scale_inset_sidewalk_base_v22"
        item["sidewalk_inset_px"] = sidewalk_inset
        item["road_overhang_direction"] = road_direction
        occupied_lamp_cells.add((gx, gy))
        _install_city_block_street_item_defs(world)
        item["asset"] = "street_item_lamp"
        item["emits_light"] = True
        item["light_offset_x_px"] = light_x
        item["light_offset_y_px"] = light_y
        item["light_radius_px"] = 360
        item["light_color_rgb"] = [92, 145, 255]
        item["light_intensity"] = 0.28
        item["light_registration"] = "cardinal_transform_shared_anchors_report60"
        item["fixture_light_sync"] = "same_grid_object_record"
        item["overhead"] = True
        item["decorative_only"] = True
        item["collision_radius_px"] = 0
        item["render_policy"] = "walk_under_overhead_street_lamp_v25"
        lamp_count += 1

    hudson_river = _install_hudson_river(world, rows, roof_rows)
    street_item_counts = _add_city_block_street_items(world, occupied_lamp_cells)
    gwb_piece_count = _install_gwb_landmark(world)

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
        "infill_building_count": len(infill_buildings),
        "infill_building_ids": infill_buildings,
        "enterable_building_count": len(buildings),
        "safe_login_spawn_count": len(safe_login_spawns),
        "safe_login_spawn_policy": "distributed_interior_sidewalks_v19",
        "pavement_variant_cell_count": pavement_variant_count,
        "pavement_variation_policy": "deterministic_city_block_pack_mix_v19",
        "rounded_road_edge_curb_count": sum(curb_counts.values()),
        "rounded_curb_corner_count": sum(count for tile, count in curb_counts.items() if "outer" in tile),
        "building_edge_alpha_policy": "source_alpha_preserved_exterior_frame_removed",
        "fire_escape_outside_collision_count": fire_escape_count,
        "street_lamp_asset_sync_count": lamp_count,
        "street_lamp_overhead_count": lamp_count,
        "george_washington_bridge_piece_count": gwb_piece_count,
        "hudson_river": hudson_river,
        "fixture_and_emitter_authority": "same_grid_object_record",
        "junction_clear_cell_count": len(junction_cells),
        "road_art_authority": "grunge_neon_clean_junctions_v130",
        **street_item_counts,
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
        chroma = maximum - minimum
        # Neutral dark frame ink may be moderately bright; coloured outline ink
        # is admitted only when it is genuinely near-black. This preserves dark
        # blue/brown roof fills and isolated mechanical detail.
        return (
            maximum < 170 and luminance < 145 and chroma < 25
        ) or (
            maximum < 112 and luminance < 100 and chroma < 62
        )

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
