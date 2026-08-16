from __future__ import annotations

"""Pass 20 RC3: repair corner-frontage switches without relaxing safety gates.

RC1/RC2 established that all 95 buildings can remain safely clear of asphalt,
but four buildings sit near road corners where a one-axis correction changes which
road segment is nearest.  This wrapper keeps the normal Pass 20 correction for the
whole map, then uses a small deterministic 2D search only for unresolved corner
cases.  The search stays within the original 64-world-unit movement budget and
rejects candidate footprints that touch other buildings, protected water/green
polygons, the Hudson band, or the road-clearance gate.
"""

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass20_streetwall as pass20


PASS_ID = "pass_20_streetwall_frontage_rc3"
SEARCH_STEP = 2.0


def rect_edges(rect):
    x, y, w, h = rect
    a = (x, y); b = (x + w, y); c = (x + w, y + h); d = (x, y + h)
    return ((a, b), (b, c), (c, d), (d, a))


def rect_hits_polygon(rect, polygon) -> bool:
    x, y, w, h = rect
    corners = ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
    if any(pass20.base.point_in_polygon(point, polygon) for point in corners):
        return True
    if any(x <= px <= x + w and y <= py <= y + h for px, py in polygon):
        return True
    poly_edges = tuple(zip(polygon, polygon[1:] + polygon[:1]))
    return any(
        pass20.base.segment_intersection(a, b, c, d) is not None
        for a, b in rect_edges(rect)
        for c, d in poly_edges
    )


def candidate_is_surface_safe(rect, protected_polygons) -> bool:
    x, y, w, h = rect
    if x < 0 or y < 2048 or x + w > 16384 or y + h > 10240:
        return False
    if x < pass20.base.HUDSON_EAST_X and x + w > pass20.base.HUDSON_WEST_X:
        return False
    return not any(rect_hits_polygon(rect, polygon) for polygon in protected_polygons)


def score_frontage(building, roads, road_points):
    nearest = pass20.nearest_frontage(building, roads, road_points)
    if nearest is None:
        return None
    _, sidewalk_gap, road_clearance, _, _, road = nearest
    target = pass20.target_frontage_gap(building, road)
    addressed = pass20.MIN_SIDEWALK_GAP - 1e-6 <= sidewalk_gap <= target + 14.0
    safe = road_clearance >= pass20.MIN_ROAD_CLEARANCE - 1e-6
    return sidewalk_gap, road_clearance, road, target, addressed, safe


def search_repair(building, original_xy, boxes, roads, road_points, protected_polygons):
    ox, oy = original_xy
    w = float(building["w"]); h = float(building["h"])
    current_x = float(building["x"]); current_y = float(building["y"])
    current = score_frontage(building, roads, road_points)
    if current is not None and current[4] and current[5]:
        return current_x, current_y, current

    best = None
    radius_steps = int(pass20.MAX_SHIFT / SEARCH_STEP)
    for ix in range(-radius_steps, radius_steps + 1):
        dx = ix * SEARCH_STEP
        max_dy = math.sqrt(max(0.0, pass20.MAX_SHIFT ** 2 - dx * dx))
        iy_max = int(max_dy / SEARCH_STEP)
        for iy in range(-iy_max, iy_max + 1):
            dy = iy * SEARCH_STEP
            distance = math.hypot(dx, dy)
            if distance > pass20.MAX_SHIFT + 1e-9:
                continue
            rect = [ox + dx, oy + dy, w, h]
            if not candidate_is_surface_safe(rect, protected_polygons):
                continue
            if any(
                other_id != building["id"] and pass20.overlaps(rect, other_box, clearance=0.0)
                for other_id, other_box in boxes.items()
            ):
                continue
            candidate = dict(building)
            candidate["x"] = rect[0]
            candidate["y"] = rect[1]
            result = score_frontage(candidate, roads, road_points)
            if result is None:
                continue
            sidewalk_gap, road_clearance, _, target, addressed, safe = result
            if not addressed or not safe:
                continue
            # Prefer the target frontage band, then the shortest movement from the
            # original accepted footprint.  Small current-position tie-break keeps
            # repair deterministic and visually conservative.
            target_error = abs(sidewalk_gap - target)
            from_current = math.hypot(rect[0] - current_x, rect[1] - current_y)
            score = (target_error, distance, from_current, rect[1], rect[0])
            if best is None or score < best[0]:
                best = (score, rect[0], rect[1], result)
    if best is None:
        return current_x, current_y, current
    return best[1], best[2], best[3]


_original_generate = pass20.generate_pass20_buildings


def generate_pass20_buildings_rc3(roads, road_points):
    buildings, parcel_uses = _original_generate(roads, road_points)
    row_by_id = {row["building_id"]: row for row in pass20.frontage_rows}
    boxes = {
        row["id"]: [float(row["x"]), float(row["y"]), float(row["w"]), float(row["h"])]
        for row in buildings
    }
    protected = pass20.base.authored_surfaces()
    protected_polygons = list(protected.get("water", ())) + list(protected.get("green", ()))
    repair_deltas: dict[str, tuple[float, float]] = {}
    repaired = 0

    for building in buildings:
        audit = row_by_id.get(building["id"])
        if audit is None:
            continue
        current_result = score_frontage(building, roads, road_points)
        if current_result is not None and current_result[4] and current_result[5]:
            continue

        # Reconstruct the pre-Pass20 footprint so the RC3 search respects the
        # same total 64-unit movement budget rather than adding another 64 units.
        ox = float(building["x"]) - float(audit.get("shift_x", 0) or 0)
        oy = float(building["y"]) - float(audit.get("shift_y", 0) or 0)
        old_x = float(building["x"]); old_y = float(building["y"])
        new_x, new_y, result = search_repair(
            building, (ox, oy), boxes, roads, road_points, protected_polygons
        )
        if result is None:
            continue

        repair_dx = new_x - old_x
        repair_dy = new_y - old_y
        building["x"] = round(new_x, 2)
        building["y"] = round(new_y, 2)
        building["stair_x"] = round(float(building["stair_x"]) + repair_dx, 2)
        building["stair_y"] = round(float(building["stair_y"]) + repair_dy, 2)
        boxes[building["id"]] = [new_x, new_y, float(building["w"]), float(building["h"])]
        repair_deltas[building["id"]] = (repair_dx, repair_dy)

        sidewalk_gap, road_clearance, road, target, addressed, safe = result
        total_dx = new_x - ox
        total_dy = new_y - oy
        audit.update({
            "road_id": road["road_id"],
            "road_class": road.get("highway", ""),
            "gap_after": round(sidewalk_gap, 2),
            "road_clearance_after": round(road_clearance, 2),
            "target_gap": round(target, 2),
            "shift_x": round(total_dx, 2),
            "shift_y": round(total_dy, 2),
            "shift_distance": round(math.hypot(total_dx, total_dy), 2),
            "shift_direction": "corner_2d_repair",
            "addressed": "true" if addressed else "false",
            "safe_clearance": "true" if safe else "false",
            "status": "pass" if addressed and safe else "frontage_limited",
        })
        if addressed and safe:
            repaired += 1

    if repair_deltas:
        pass20.rewrite_semantics(buildings, repair_deltas)
        pass20.base.write_csv(
            pass20.base.SEMANTIC / pass20.FRONTAGE_AUDIT_CSV,
            ("building_id", "district", "building_kind", "road_id", "road_class", "gap_before", "gap_after",
             "road_clearance_before", "road_clearance_after", "target_gap", "shift_x", "shift_y", "shift_distance",
             "shift_direction", "frontage_class", "addressed", "safe_clearance", "status"),
            pass20.frontage_rows,
        )

    unresolved = sum(
        1 for row in pass20.frontage_rows
        if row.get("addressed") != "true" or row.get("safe_clearance") != "true"
    )
    print(f"PASS20_RC3_CORNER_REPAIR repaired={repaired} unresolved={unresolved}")
    return buildings, parcel_uses


def main() -> None:
    pass20.PASS_ID = PASS_ID
    pass20.generate_pass20_buildings = generate_pass20_buildings_rc3
    pass20.main()


if __name__ == "__main__":
    main()
