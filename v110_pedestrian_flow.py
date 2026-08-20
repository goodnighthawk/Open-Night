from __future__ import annotations

"""Deadlock-safe connected GridWorld pedestrian routes for Open Night v1.1.

Local one-way pavement cycles fixed the first head-on pedestrian deadlock, but they
left each block as an island. v1.1 now prefers the shared sidewalk/zebra network:
clockwise multi-block cycles can cross major roads only at registered zebra
crossings. The older 2-core cycle extractor remains as a conservative fallback for
maps that do not expose the connected street-grid pattern.
"""

from collections import deque
from typing import Iterable

import v110_pedestrian_connectivity


def _sort_cells(cells: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    return sorted(cells, key=lambda p: (p[1], p[0]))


def _two_core(population_module, component: list[tuple[int, int]]) -> set[tuple[int, int]]:
    """Return the maximal subgraph in which every pavement cell has degree >= 2."""
    core = set(component)
    degree = {node: len(population_module._neighbors(node, core)) for node in core}
    pending = deque(_sort_cells(node for node, value in degree.items() if value < 2))
    while pending:
        node = pending.popleft()
        if node not in core:
            continue
        core.remove(node)
        for neighbor in population_module._neighbors(node, core):
            degree[neighbor] = max(0, degree.get(neighbor, 0) - 1)
            if degree[neighbor] == 1:
                pending.append(neighbor)
    return core


def _normalize_cycle(cycle: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Canonicalize rotation and direction without repeating the first node."""
    if len(cycle) > 1 and cycle[0] == cycle[-1]:
        cycle = cycle[:-1]
    if len(cycle) < 4 or len(set(cycle)) != len(cycle):
        return []

    def rotate(values: list[tuple[int, int]]) -> list[tuple[int, int]]:
        start = min(range(len(values)), key=lambda i: (values[i][1], values[i][0]))
        return values[start:] + values[:start]

    forward = rotate(list(cycle))
    reverse = rotate(list(reversed(cycle)))
    return min(forward, reverse, key=lambda values: tuple((y, x) for x, y in values))


def _cycle_area(cycle: list[tuple[int, int]]) -> float:
    area2 = 0
    for index, (x1, y1) in enumerate(cycle):
        x2, y2 = cycle[(index + 1) % len(cycle)]
        area2 += x1 * y2 - x2 * y1
    return abs(area2) * 0.5


def _cycle_basis(population_module, core: set[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    """Build deterministic simple fundamental cycles from an undirected grid graph."""
    if len(core) < 4:
        return []
    parent: dict[tuple[int, int], tuple[int, int] | None] = {}
    depth: dict[tuple[int, int], int] = {}
    seen: set[tuple[int, int]] = set()
    cycles: dict[tuple[tuple[int, int], ...], list[tuple[int, int]]] = {}

    for root in _sort_cells(core):
        if root in seen:
            continue
        parent[root] = None
        depth[root] = 0
        seen.add(root)
        stack: list[tuple[tuple[int, int], object]] = [
            (root, iter(_sort_cells(population_module._neighbors(root, core))))
        ]
        while stack:
            node, iterator = stack[-1]
            try:
                neighbor = next(iterator)
            except StopIteration:
                stack.pop()
                continue
            if neighbor == parent.get(node):
                continue
            if neighbor not in seen:
                parent[neighbor] = node
                depth[neighbor] = depth[node] + 1
                seen.add(neighbor)
                stack.append((neighbor, iter(_sort_cells(population_module._neighbors(neighbor, core)))))
                continue
            if depth.get(neighbor, 0) >= depth.get(node, 0):
                continue
            path = [node]
            current = node
            while current != neighbor:
                current = parent.get(current)
                if current is None:
                    path = []
                    break
                path.append(current)
            cycle = _normalize_cycle(path)
            if cycle:
                cycles[tuple(cycle)] = cycle

    return sorted(
        cycles.values(),
        key=lambda cycle: (-_cycle_area(cycle), -len(cycle), tuple((y, x) for x, y in cycle)),
    )


def _segment_is_pavement(population_module, world, a: tuple[float, float], b: tuple[float, float]) -> bool:
    dx, dy = b[0] - a[0], b[1] - a[1]
    distance = (dx * dx + dy * dy) ** 0.5
    steps = max(1, int(distance / max(8.0, world.cell_px / 4.0)) + 1)
    for step in range(steps + 1):
        t = step / steps
        gx, gy = world.world_to_cell(a[0] + dx * t, a[1] + dy * t)
        if not population_module._is_pavement(world, gx, gy):
            return False
    return True


def _fallback_local_cycles(population_module, world) -> list[dict]:
    pavement = {
        (gx, gy)
        for gy in range(world.height)
        for gx in range(world.width)
        if population_module._is_pavement(world, gx, gy)
    }
    routes: list[dict] = []
    for component in population_module._components(pavement):
        if len(component) < 5:
            continue
        core = _two_core(population_module, component)
        candidates = _cycle_basis(population_module, core)
        if not candidates:
            continue
        cells = candidates[0]
        points = [world.cell_center(gx, gy) for gx, gy in cells]
        if not all(
            _segment_is_pavement(population_module, world, points[index], points[(index + 1) % len(points)])
            for index in range(len(points))
        ):
            continue
        routes.append({
            "id": f"grid_ped_cycle_{len(routes):02d}",
            "waypoints": [[round(x, 3), round(y, 3)] for x, y in points],
            "speed": max(42.0, world.cell_px * 0.43),
            "turn_radius": 0.0,
            "grid_native": True,
            "one_way_cycle": True,
            "crosswalk_connected": False,
            "block_span_rows": 1,
            "block_span_cols": 1,
        })
        if len(routes) >= population_module.PEDESTRIAN_ROUTE_LIMIT:
            break
    return routes


def build_pedestrian_routes(population_module, world) -> list[dict]:
    """Prefer one connected multi-block zebra network; retain a safe fallback."""
    connected = v110_pedestrian_connectivity.build_routes(
        population_module,
        world,
        max_routes=population_module.PEDESTRIAN_ROUTE_LIMIT,
    )
    return connected or _fallback_local_cycles(population_module, world)


def reciprocal_edge_count(routes: list[dict]) -> int:
    """Count physical route edges that are authored in both directions."""
    directed: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    reciprocal: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    for route in routes:
        points = [
            (round(float(point[0]), 3), round(float(point[1]), 3))
            for point in (route.get("waypoints") or [])
            if isinstance(point, (list, tuple)) and len(point) >= 2
        ]
        for index, start in enumerate(points):
            end = points[(index + 1) % len(points)]
            edge = (start, end)
            reverse = (end, start)
            if reverse in directed:
                reciprocal.add(min(edge, reverse))
            directed.add(edge)
    return len(reciprocal)


def install(population_module) -> None:
    """Install connected routes and expose their release invariants in the audit."""
    if bool(getattr(population_module, "_v110_pedestrian_flow_installed", False)):
        return
    original_prepare = population_module.prepare_and_initialize

    def build_routes_v110(world):
        return build_pedestrian_routes(population_module, world)

    def prepare_and_initialize_v110(server_module, map_config: dict, world) -> dict:
        audit = original_prepare(server_module, map_config, world)
        routes = list(map_config.get("npc_routes", []) or [])
        reciprocal = reciprocal_edge_count(routes)
        cycle_routes = sum(bool(route.get("one_way_cycle")) for route in routes)
        audit["pedestrian_one_way_cycle_routes"] = cycle_routes
        audit["pedestrian_reciprocal_edge_count"] = reciprocal
        audit.update(v110_pedestrian_connectivity.audit(world))

        if not routes or cycle_routes != len(routes):
            raise RuntimeError("v1.1 pedestrian flow requires one-way cycle routes only")
        if reciprocal:
            raise RuntimeError(f"v1.1 pedestrian routes contain {reciprocal} reciprocal physical edge(s)")
        if int(audit.get("pedestrian_crosswalk_count", 0)) < v110_pedestrian_connectivity.MIN_CROSSWALKS:
            raise RuntimeError("v1.1 pedestrian flow requires a dense zebra-crossing network")
        if int(audit.get("pedestrian_route_network_components", 99)) != 1:
            raise RuntimeError("v1.1 pedestrian routes are not one interconnected network")
        if int(audit.get("pedestrian_multiblock_route_count", 0)) < 6:
            raise RuntimeError("v1.1 pedestrian flow does not span enough city blocks")
        if int(audit.get("pedestrian_crosswalk_route_count", 0)) < 6:
            raise RuntimeError("v1.1 pedestrian flow does not use enough zebra crossings")
        return audit

    population_module._build_pedestrian_routes = build_routes_v110
    population_module.prepare_and_initialize = prepare_and_initialize_v110
    population_module._v110_pedestrian_flow_installed = True
