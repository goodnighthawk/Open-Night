from __future__ import annotations

"""Curb-safe building-centering policy for the v1.0 GridWorld refinement."""

from collections import defaultdict, deque


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


def _nonroad_components(rows: list[list[str]]) -> tuple[dict[tuple[int, int], int], dict[int, set[tuple[int, int]]]]:
    height, width = len(rows), len(rows[0])
    remaining = {(x, y) for y in range(height) for x in range(width) if rows[y][x] not in {"road_fill", "void"}}
    lookup: dict[tuple[int, int], int] = {}
    components: dict[int, set[tuple[int, int]]] = {}
    component_id = 0
    while remaining:
        seed = remaining.pop()
        pending = deque([seed])
        cells = {seed}
        while pending:
            x, y = pending.popleft()
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    cells.add(neighbor)
                    pending.append(neighbor)
        components[component_id] = cells
        for cell in cells:
            lookup[cell] = component_id
        component_id += 1
    return lookup, components


def _safe_shift_candidates(
    rows: list[list[str]], building: dict, desired_center: tuple[float, float]
) -> list[tuple[float, int, int, set[tuple[int, int]]]]:
    original = _footprint(building)
    cx = sum(x for x, _ in original) / len(original)
    cy = sum(y for _, y in original) / len(original)
    height, width = len(rows), len(rows[0])
    candidates: list[tuple[float, int, int, set[tuple[int, int]]]] = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            shifted = {(x + dx, y + dy) for x, y in original}
            if any(not (0 <= x < width and 0 <= y < height) for x, y in shifted):
                continue
            safe = True
            for x, y in shifted:
                if (x - dx, y - dy) in original:
                    # Existing building cells are always safe to retain.
                    continue
                tile_id = rows[y][x]
                # Never consume roads or any curb tile. New footprint cells must
                # come from genuine in-block pavement/plaza area.
                if tile_id in {"road_fill", "void"} or tile_id.startswith("curb_") or tile_id.startswith("bld_"):
                    safe = False
                    break
                if not (tile_id.startswith("pavement_") or tile_id == "pavement_small"):
                    safe = False
                    break
            if not safe:
                continue
            nx, ny = cx + dx, cy + dy
            score = (nx - desired_center[0]) ** 2 + (ny - desired_center[1]) ** 2
            # Prefer the smallest movement when two options center equally well.
            candidates.append((score + 0.001 * (abs(dx) + abs(dy)), dx, dy, shifted))
    if not candidates:
        candidates.append((float("inf"), 0, 0, original))
    return sorted(candidates, key=lambda row: (row[0], abs(row[1]) + abs(row[2]), row[1], row[2]))


def _expanded_orthogonal(cells: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Return cells plus their cardinal neighbours.

    Distinct buildings must retain at least one GridWorld cell of setback. Besides
    preventing collision overlap, this keeps the authored pavement seam visible
    between different facade themes.
    """
    expanded = set(cells)
    for x, y in cells:
        expanded.update(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
    return expanded


def _joint_safe_shifts(
    rows: list[list[str]], group: list[dict], desired_center: tuple[float, float]
) -> dict[str, tuple[int, int]]:
    """Choose all shifts in a road-bounded lot as one deterministic assignment.

    The earlier selector optimized each building independently. Two neighbours
    could therefore both choose the same setback cell even though either shift
    was safe in isolation. This small branch-and-bound search scores the same
    nine local candidates while reserving complete footprints jointly.
    """
    ordered = sorted(group, key=lambda item: str(item["building_id"]))
    candidates = {
        str(building["building_id"]): _safe_shift_candidates(rows, building, desired_center)
        for building in ordered
    }
    best_score = float("inf")
    best_key: tuple[tuple[int, int], ...] | None = None
    best: dict[str, tuple[int, int]] | None = None

    def visit(
        index: int,
        score: float,
        reserved_with_margin: set[tuple[int, int]],
        chosen: dict[str, tuple[int, int]],
    ) -> None:
        nonlocal best_score, best_key, best
        if score > best_score:
            return
        if index == len(ordered):
            key = tuple(chosen[str(building["building_id"])] for building in ordered)
            if score < best_score or (score == best_score and (best_key is None or key < best_key)):
                best_score, best_key, best = score, key, dict(chosen)
            return
        building = ordered[index]
        building_id = str(building["building_id"])
        for candidate_score, dx, dy, footprint in candidates[building_id]:
            if footprint & reserved_with_margin:
                continue
            chosen[building_id] = (dx, dy)
            visit(
                index + 1,
                score + candidate_score,
                reserved_with_margin | _expanded_orthogonal(footprint),
                chosen,
            )
            chosen.pop(building_id, None)

    visit(0, 0.0, set(), {})
    if best is None:
        raise RuntimeError("no collision-free building-centering assignment for road-bounded lot")
    return best


def curb_safe_building_shifts(rows: list[list[str]], buildings: list[dict]) -> dict[str, tuple[int, int]]:
    lookup, components = _nonroad_components(rows)
    groups: dict[int, list[dict]] = defaultdict(list)
    for building in buildings:
        ids = {lookup[cell] for cell in _footprint(building) if cell in lookup}
        if len(ids) != 1:
            raise RuntimeError(f"building crosses road-bounded blocks: {building['building_id']}")
        groups[next(iter(ids))].append(building)

    shifts: dict[str, tuple[int, int]] = {}
    for component_id, group in groups.items():
        component = components[component_id]
        bx0 = min(x for x, _ in component); bx1 = max(x for x, _ in component)
        by0 = min(y for _, y in component); by1 = max(y for _, y in component)
        block_center = ((bx0 + bx1) / 2.0, (by0 + by1) / 2.0)
        shifts.update(_joint_safe_shifts(rows, group, block_center))
    return shifts


def install(refinement_module) -> None:
    """Replace only the centering selector before refinement.install()."""
    refinement_module._building_shifts = curb_safe_building_shifts
