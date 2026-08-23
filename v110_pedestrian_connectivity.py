from __future__ import annotations

"""Connected sidewalk + zebra-crossing network for Open Night v1.1.

The first v1.1 population pass made every local sidewalk component safe by forcing
one-way cycles, but those cycles were still isolated around individual blocks. This
module promotes the street grid itself into pedestrian infrastructure:

* every major road intersection exposes four safe zebra-crossing corridors;
* long road segments gain deterministic mid-block zebra crossings;
* pavement is visually widened into a narrow road-edge apron without changing the
  car-only collision authority; and
* pedestrian routes become clockwise, multi-block cycles that use those crossings.

The visual additions are collision-neutral GridWorld objects built only from the
repo-resident city_block pavement/crossing artwork. Cars therefore keep the same
road collision cells while ambient pedestrians get an explicit crossing surface.
"""

from dataclasses import dataclass
import math
from typing import Iterable

from grid_world import ObjectDef

SIDEWALK_APRON_FRACTION = 0.36
MAX_ROUTE_COUNT = 18
MIN_CROSSWALKS = 24


@dataclass(frozen=True)
class RoadBand:
    start: int
    end: int
    center: int


@dataclass(frozen=True)
class Crosswalk:
    crosswalk_id: str
    axis: str  # "x" crosses a vertical road; "y" crosses a horizontal road.
    fixed_cell: int
    road_start: int
    road_end: int
    kind: str

    def road_cells(self) -> tuple[tuple[int, int], ...]:
        if self.axis == "x":
            return tuple((cell, self.fixed_cell) for cell in range(self.road_start, self.road_end + 1))
        return tuple((self.fixed_cell, cell) for cell in range(self.road_start, self.road_end + 1))


def _group_runs(values: Iterable[int]) -> list[list[int]]:
    groups: list[list[int]] = []
    for value in sorted(set(int(v) for v in values)):
        if not groups or value != groups[-1][-1] + 1:
            groups.append([value])
        else:
            groups[-1].append(value)
    return groups


def _is_road(world, gx: int, gy: int) -> bool:
    return bool(world.in_bounds(gx, gy)) and str(world.tile("ground", gx, gy).collision) == "road"


def _is_sidewalk(world, gx: int, gy: int) -> bool:
    if not world.in_bounds(gx, gy):
        return False
    return str(world.tile("ground", gx, gy).collision) in {"walk", "sidewalk"}


def is_building_cell(world, gx: int, gy: int) -> bool:
    """Return whether a cell is covered by an authoritative building footprint."""
    buildings = list((world.data.get("building_synthesis") or {}).get("buildings") or [])
    for building in buildings:
        try:
            x0, y0, x1, y1 = map(int, building.get("rect", ()))
        except (TypeError, ValueError):
            continue
        if x0 <= int(gx) <= x1 and y0 <= int(gy) <= y1:
            return True
    return False


def road_bands(world) -> tuple[list[RoadBand], list[RoadBand]]:
    """Find authored major horizontal and vertical road bands from collision."""
    min_row_coverage = max(4, int(math.ceil(world.width * 0.55)))
    min_col_coverage = max(4, int(math.ceil(world.height * 0.55)))
    rows = [
        gy for gy in range(world.height)
        if sum(_is_road(world, gx, gy) for gx in range(world.width)) >= min_row_coverage
    ]
    cols = [
        gx for gx in range(world.width)
        if sum(_is_road(world, gx, gy) for gy in range(world.height)) >= min_col_coverage
    ]

    def bands(values: list[int]) -> list[RoadBand]:
        out: list[RoadBand] = []
        for run in _group_runs(values):
            out.append(RoadBand(run[0], run[-1], run[len(run) // 2]))
        return out

    return bands(rows), bands(cols)


def _safe_cross_x(world, vertical: RoadBand, fixed_y: int) -> bool:
    return (
        world.in_bounds(vertical.start - 1, fixed_y)
        and world.in_bounds(vertical.end + 1, fixed_y)
        and _is_sidewalk(world, vertical.start - 1, fixed_y)
        and _is_sidewalk(world, vertical.end + 1, fixed_y)
        and all(_is_road(world, gx, fixed_y) for gx in range(vertical.start, vertical.end + 1))
    )


def _safe_cross_y(world, horizontal: RoadBand, fixed_x: int) -> bool:
    return (
        world.in_bounds(fixed_x, horizontal.start - 1)
        and world.in_bounds(fixed_x, horizontal.end + 1)
        and _is_sidewalk(world, fixed_x, horizontal.start - 1)
        and _is_sidewalk(world, fixed_x, horizontal.end + 1)
        and all(_is_road(world, fixed_x, gy) for gy in range(horizontal.start, horizontal.end + 1))
    )


def _nearest_safe_mid_y(world, vertical: RoadBand, low: int, high: int) -> int | None:
    if low > high:
        return None
    middle = (low + high) // 2
    candidates = sorted(range(low, high + 1), key=lambda y: (abs(y - middle), y))
    return next((y for y in candidates if _safe_cross_x(world, vertical, y)), None)


def _nearest_safe_mid_x(world, horizontal: RoadBand, low: int, high: int) -> int | None:
    if low > high:
        return None
    middle = (low + high) // 2
    candidates = sorted(range(low, high + 1), key=lambda x: (abs(x - middle), x))
    return next((x for x in candidates if _safe_cross_y(world, horizontal, x)), None)


def build_crosswalks(world) -> list[Crosswalk]:
    """Return intersection + mid-block pedestrian corridors over road cells."""
    horizontal, vertical = road_bands(world)
    crossings: list[Crosswalk] = []
    seen: set[tuple[str, int, int, int]] = set()

    def add(item: Crosswalk) -> None:
        key = (item.axis, item.fixed_cell, item.road_start, item.road_end)
        if key not in seen:
            seen.add(key)
            crossings.append(item)

    # Four approach crossings at every major intersection. These align with the
    # existing curb geometry and make every corner a valid route hand-off.
    for h_index, hband in enumerate(horizontal):
        for v_index, vband in enumerate(vertical):
            for side_name, fixed_y in (("north", hband.start - 1), ("south", hband.end + 1)):
                if _safe_cross_x(world, vband, fixed_y):
                    add(Crosswalk(
                        f"ix_{h_index}_{v_index}_{side_name}", "x", fixed_y,
                        vband.start, vband.end, "intersection",
                    ))
            for side_name, fixed_x in (("west", vband.start - 1), ("east", vband.end + 1)):
                if _safe_cross_y(world, hband, fixed_x):
                    add(Crosswalk(
                        f"iy_{h_index}_{v_index}_{side_name}", "y", fixed_x,
                        hband.start, hband.end, "intersection",
                    ))

    # Long blocks also receive a mid-block crossing. These are additional visual
    # zebras and alternative pedestrian links, not replacements for intersections.
    for v_index, vband in enumerate(vertical):
        for row in range(len(horizontal) - 1):
            low = horizontal[row].end + 2
            high = horizontal[row + 1].start - 2
            fixed_y = _nearest_safe_mid_y(world, vband, low, high)
            if fixed_y is not None:
                add(Crosswalk(
                    f"mx_{row}_{v_index}", "x", fixed_y,
                    vband.start, vband.end, "midblock",
                ))

    for h_index, hband in enumerate(horizontal):
        for col in range(len(vertical) - 1):
            low = vertical[col].end + 2
            high = vertical[col + 1].start - 2
            fixed_x = _nearest_safe_mid_x(world, hband, low, high)
            if fixed_x is not None:
                add(Crosswalk(
                    f"my_{h_index}_{col}", "y", fixed_x,
                    hband.start, hband.end, "midblock",
                ))

    return crossings


def _ensure_runtime_object_defs(world) -> None:
    # Use the compact pavement swatch for extensions. Stretching the directional
    # curb strips created the thick white/blue bars reported at road edges.
    if "v110_sidewalk_apron_h" not in world.catalog.objects:
        tile = world.catalog["pavement_small"]
        world.catalog.objects["v110_sidewalk_apron_h"] = ObjectDef(
            "v110_sidewalk_apron_h", tile.image, kind="sidewalk_extension",
            layer="ground", z=18, native_width_px=world.cell_px, native_height_px=world.cell_px,
        )
    if "v110_sidewalk_apron_v" not in world.catalog.objects:
        tile = world.catalog["pavement_small"]
        world.catalog.objects["v110_sidewalk_apron_v"] = ObjectDef(
            "v110_sidewalk_apron_v", tile.image, kind="sidewalk_extension",
            layer="ground", z=18, native_width_px=world.cell_px, native_height_px=world.cell_px,
        )


def _add_sidewalk_aprons(world, horizontal: list[RoadBand], vertical: list[RoadBand]) -> int:
    """Visually widen each block-face sidewalk into the road edge by ~18%."""
    _ensure_runtime_object_defs(world)
    cell = int(world.cell_px)
    apron = max(10, int(round(cell * SIDEWALK_APRON_FRACTION)))
    added = 0

    def append(item: dict) -> None:
        nonlocal added
        world.objects.append(item)
        added += 1

    # One stretched pavement apron per block face keeps the object count small.
    for hband in horizontal:
        for col in range(len(vertical) - 1):
            x0 = vertical[col].end + 1
            x1 = vertical[col + 1].start - 1
            if x1 < x0:
                continue
            width = (x1 - x0 + 1) * cell
            if hband.start - 1 >= 0 and _is_sidewalk(world, x0, hband.start - 1):
                append({
                    "asset": "v110_sidewalk_apron_h", "gx": x0, "gy": hband.start,
                    "offset_x_px": 0, "offset_y_px": 0, "width_px": width, "height_px": apron,
                    "composition_pass": "v110_pedestrian_connectivity", "sidewalk_extension": "north",
                    "decorative_only": True, "visual_style": "grunge_sidewalk_infill_v130",
                })
            if hband.end + 1 < world.height and _is_sidewalk(world, x0, hband.end + 1):
                append({
                    "asset": "v110_sidewalk_apron_h", "gx": x0, "gy": hband.end,
                    "offset_x_px": 0, "offset_y_px": cell - apron, "width_px": width, "height_px": apron,
                    "composition_pass": "v110_pedestrian_connectivity", "sidewalk_extension": "south",
                    "decorative_only": True, "visual_style": "grunge_sidewalk_infill_v130",
                })

    for vband in vertical:
        for row in range(len(horizontal) - 1):
            y0 = horizontal[row].end + 1
            y1 = horizontal[row + 1].start - 1
            if y1 < y0:
                continue
            height = (y1 - y0 + 1) * cell
            if vband.start - 1 >= 0 and _is_sidewalk(world, vband.start - 1, y0):
                append({
                    "asset": "v110_sidewalk_apron_v", "gx": vband.start, "gy": y0,
                    "offset_x_px": 0, "offset_y_px": 0, "width_px": apron, "height_px": height,
                    "composition_pass": "v110_pedestrian_connectivity", "sidewalk_extension": "west",
                    "decorative_only": True, "visual_style": "grunge_sidewalk_infill_v130",
                })
            if vband.end + 1 < world.width and _is_sidewalk(world, vband.end + 1, y0):
                append({
                    "asset": "v110_sidewalk_apron_v", "gx": vband.end, "gy": y0,
                    "offset_x_px": cell - apron, "offset_y_px": 0, "width_px": apron, "height_px": height,
                    "composition_pass": "v110_pedestrian_connectivity", "sidewalk_extension": "east",
                    "decorative_only": True, "visual_style": "grunge_sidewalk_infill_v130",
                })
    return added


def _add_midblock_zebra_art(world, crossings: list[Crosswalk]) -> int:
    """Render full-width zebras for every widened-road crossing."""
    if "mark_white_crossing_piece" not in world.catalog.objects:
        return 0
    scale = float(world.cell_px) / 256.0
    stripe_width = max(10, int(round(world.cell_px * 0.20)))
    stripe_length = max(34, int(round(176 * scale)))
    near = int(round(40 * scale))
    added = 0
    painted_crossing_index = 0
    for crossing in crossings:
        # Keep every crossing available to pedestrian routing, but reserve
        # painted zebras for mid-block crossings. Painting all four approaches
        # at every intersection overwhelmed the widened-road presentation.
        if crossing.kind != "midblock":
            continue
        # All crossings remain authoritative route links, but only every third
        # mid-block link is painted. Report #44 showed that drawing every safe
        # link made the streets read as one continuous field of zebra stripes.
        if painted_crossing_index % 3 != 0:
            painted_crossing_index += 1
            continue
        painted_crossing_index += 1
        road_cells = crossing.road_end - crossing.road_start + 1
        stripe_count = 6
        span = road_cells * world.cell_px
        spacing = span / stripe_count
        if crossing.axis == "x":
            for stripe in range(stripe_count):
                world.objects.append({
                    "asset": "mark_white_crossing_piece",
                    "gx": crossing.road_start,
                    "gy": crossing.fixed_cell,
                    "offset_x_px": int(round((stripe + 0.5) * spacing - stripe_width * 0.5)),
                    "offset_y_px": near,
                    "width_px": stripe_width,
                    "height_px": stripe_length,
                    "rotation": 0,
                    "street_marking": f"zebra_{crossing.kind}",
                    "zebra_stripe_index": stripe,
                    "crosswalk_id": crossing.crosswalk_id,
                    "composition_pass": "v110_pedestrian_connectivity",
                })
                added += 1
        else:
            for stripe in range(stripe_count):
                world.objects.append({
                    "asset": "mark_white_crossing_piece",
                    "gx": crossing.fixed_cell,
                    "gy": crossing.road_start,
                    "offset_x_px": near,
                    "offset_y_px": int(round((stripe + 0.5) * spacing - stripe_width * 0.5)),
                    "width_px": stripe_width,
                    "height_px": stripe_length,
                    "rotation": 90,
                    "street_marking": f"zebra_{crossing.kind}",
                    "zebra_stripe_index": stripe,
                    "crosswalk_id": crossing.crosswalk_id,
                    "composition_pass": "v110_pedestrian_connectivity",
                })
                added += 1
    return added


def apply(world) -> dict:
    """Idempotently attach widened sidewalks + crossing metadata/art to a GridWorld."""
    existing = getattr(world, "_v110_pedestrian_connectivity_audit", None)
    if isinstance(existing, dict):
        return existing

    horizontal, vertical = road_bands(world)
    crossings = build_crosswalks(world)
    if len(crossings) < MIN_CROSSWALKS:
        raise RuntimeError(
            f"v1.1 pedestrian connectivity found only {len(crossings)} safe crosswalks; expected >= {MIN_CROSSWALKS}"
        )
    world._v110_crosswalks = crossings
    world._v110_crosswalk_cells = {
        cell for crossing in crossings for cell in crossing.road_cells()
    }
    sidewalk_aprons = _add_sidewalk_aprons(world, horizontal, vertical)
    zebra_stripes = _add_midblock_zebra_art(world, crossings)
    audit = {
        "pedestrian_crosswalk_count": len(crossings),
        "pedestrian_intersection_crosswalk_count": sum(c.kind == "intersection" for c in crossings),
        "pedestrian_midblock_crosswalk_count": sum(c.kind == "midblock" for c in crossings),
        "pedestrian_crosswalk_road_cell_count": len(world._v110_crosswalk_cells),
        "pedestrian_sidewalk_apron_count": sidewalk_aprons,
        "pedestrian_added_zebra_stripe_objects": zebra_stripes,
        "sidewalk_infill_asset": "pavement_small",
        "visual_style": "open_night_grunge_neon",
    }
    world._v110_pedestrian_connectivity_audit = audit
    return audit


def is_pedestrian_surface_cell(world, gx: int, gy: int) -> bool:
    if _is_sidewalk(world, gx, gy):
        return True
    apply(world)
    return (int(gx), int(gy)) in getattr(world, "_v110_crosswalk_cells", set())


def is_pedestrian_surface(world, x: float, y: float) -> bool:
    gx, gy = world.world_to_cell(float(x), float(y))
    return is_pedestrian_surface_cell(world, gx, gy)


def _rectangle_cycle_cells(left: int, top: int, right: int, bottom: int) -> list[tuple[int, int]]:
    if right <= left or bottom <= top:
        return []
    cells: list[tuple[int, int]] = []
    cells.extend((x, top) for x in range(left, right + 1))
    cells.extend((right, y) for y in range(top + 1, bottom + 1))
    cells.extend((x, bottom) for x in range(right - 1, left - 1, -1))
    cells.extend((left, y) for y in range(bottom - 1, top, -1))
    return cells


def _route_uses_crosswalk(world, cells: list[tuple[int, int]]) -> bool:
    crossing_cells = getattr(world, "_v110_crosswalk_cells", set())
    return any(cell in crossing_cells for cell in cells)


def build_routes(population_module, world, max_routes: int | None = None) -> list[dict]:
    """Build clockwise block-grid cycles, preferring routes that span many blocks."""
    connectivity = apply(world)
    horizontal, vertical = road_bands(world)
    limit = max(1, int(max_routes or getattr(population_module, "PEDESTRIAN_ROUTE_LIMIT", MAX_ROUTE_COUNT)))
    candidates: list[tuple[int, int, int, int, int, int, list[tuple[int, int]]]] = []

    # Every pair of horizontal roads and vertical roads defines a legal sidewalk
    # perimeter. Non-adjacent pairs are the important new multi-block routes.
    for hi in range(len(horizontal) - 1):
        for hj in range(hi + 1, len(horizontal)):
            top = horizontal[hi].end + 1
            bottom = horizontal[hj].start - 1
            for vi in range(len(vertical) - 1):
                for vj in range(vi + 1, len(vertical)):
                    left = vertical[vi].end + 1
                    right = vertical[vj].start - 1
                    cells = _rectangle_cycle_cells(left, top, right, bottom)
                    if len(cells) < 8:
                        continue
                    if not all(
                        is_pedestrian_surface_cell(world, gx, gy)
                        and not is_building_cell(world, gx, gy)
                        for gx, gy in cells
                    ):
                        continue
                    block_rows = hj - hi
                    block_cols = vj - vi
                    block_area = block_rows * block_cols
                    candidates.append((block_area, len(cells), hi, hj, vi, vj, cells))

    # Largest/multi-block loops first so all six central blocks participate before
    # small local cycles consume the route budget.
    candidates.sort(key=lambda item: (
        0 if item[0] > 1 else 1,
        0 if item[2] == 0 and item[4] == 0 else 1,
        -item[0], -item[1], item[2], item[4], item[3], item[5],
    ))
    if candidates:
        connected = [candidates.pop(0)]
        connected_cells = set(connected[0][-1])
        while candidates and len(connected) < limit:
            match = next((index for index, item in enumerate(candidates)
                          if connected_cells & set(item[-1])), None)
            if match is None:
                break
            item = candidates.pop(match)
            connected.append(item)
            connected_cells.update(item[-1])
        candidates = connected
    routes: list[dict] = []
    multi_block = 0
    crosswalk_routes = 0
    route_cells: list[set[tuple[int, int]]] = []
    for block_area, _length, hi, hj, vi, vj, cells in candidates:
        points = [world.cell_center(gx, gy) for gx, gy in cells]
        uses_crosswalk = _route_uses_crosswalk(world, cells)
        if block_area > 1:
            multi_block += 1
        if uses_crosswalk:
            crosswalk_routes += 1
        routes.append({
            "id": f"grid_ped_connected_{len(routes):02d}",
            "waypoints": [[round(x, 3), round(y, 3)] for x, y in points],
            "speed": max(42.0, world.cell_px * 0.43),
            "turn_radius": 0.0,
            "grid_native": True,
            "one_way_cycle": True,
            "crosswalk_connected": uses_crosswalk,
            "block_span_rows": hj - hi,
            "block_span_cols": vj - vi,
        })
        route_cells.append(set(cells))
        if len(routes) >= limit:
            break

    # Wide corridors reduce the number of distinct rectangle perimeters. Add a
    # parallel traversal of a safe multi-block route; individual pedestrians can
    # still reverse through the server's bounded change-of-mind behaviour.
    if routes and multi_block < 6 and len(routes) < limit:
        source_index = next((index for index, route in enumerate(routes)
                             if int(route.get("block_span_rows", 0)) * int(route.get("block_span_cols", 0)) > 1), None)
        if source_index is not None:
            source = routes[source_index]
            parallel = dict(source)
            parallel["id"] = f"grid_ped_connected_{len(routes):02d}_parallel"
            parallel["waypoints"] = list(source["waypoints"])
            parallel["parallel_flow_pair"] = source["id"]
            routes.append(parallel)
            route_cells.append(set(route_cells[source_index]))
            multi_block += 1
            if source.get("crosswalk_connected"):
                crosswalk_routes += 1

    if not routes:
        return []

    # Route graph connectivity: two routes belong to the same pedestrian network
    # when they share any sidewalk/crosswalk cell. The desired city grid should
    # collapse to one connected component rather than isolated building loops.
    remaining = set(range(len(route_cells)))
    components = 0
    while remaining:
        components += 1
        seed = remaining.pop()
        frontier = [seed]
        while frontier:
            current = frontier.pop()
            touched = [other for other in remaining if route_cells[current] & route_cells[other]]
            for other in touched:
                remaining.remove(other)
                frontier.append(other)

    connectivity.update({
        "pedestrian_connected_route_count": len(routes),
        "pedestrian_multiblock_route_count": multi_block,
        "pedestrian_crosswalk_route_count": crosswalk_routes,
        "pedestrian_route_network_components": components,
    })
    return routes


def audit(world) -> dict:
    return dict(apply(world))


def install_client(client_module) -> None:
    """Apply the same pedestrian art/network metadata before any client render."""
    game_cls = client_module.Game
    if bool(getattr(game_cls, "_v110_pedestrian_connectivity_installed", False)):
        return
    original_init = game_cls.__init__
    original_draw_world = game_cls.draw_world

    def init_connected(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        world = getattr(self, "grid_world", None)
        if world is not None:
            apply(world)

    def draw_world_connected(self, *args, **kwargs):
        world = getattr(self, "grid_world", None)
        if world is not None:
            apply(world)
        return original_draw_world(self, *args, **kwargs)

    game_cls.__init__ = init_connected
    game_cls.draw_world = draw_world_connected
    game_cls._v110_pedestrian_connectivity_installed = True
