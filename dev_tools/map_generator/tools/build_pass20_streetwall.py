from __future__ import annotations

"""Pass 20: street-wall/frontage correction on top of the promoted v0.9.0 art baseline.

Roads, bridge geometry, water/green surfaces and crosswalks remain owned by the
accepted unified generator. This pass only moves legal building footprints toward
their nearest sidewalk edge, within a conservative bounded shift, then regenerates
dependent collision/stair semantic rows from the moved footprints.
"""

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_unified_composition as base
import build_v090_release_candidate as v090

PASS_ID = "pass_20_streetwall_frontage_rc"
FRONTAGE_AUDIT_CSV = "building_frontage_audit.csv"
MAX_SHIFT = 64.0
MIN_CLEAR_GAP = 14.0
_original_generate_iterated_buildings = base.generate_iterated_buildings
frontage_rows: list[dict[str, object]] = []


def segment_projection(point, a, b):
    px, py = point
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx * dx + dy * dy
    if den <= 1e-9:
        q = a
    else:
        t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / den))
        q = (a[0] + t * dx, a[1] + t * dy)
    return q, math.hypot(px - q[0], py - q[1])


def road_outer_edge(road) -> float:
    lanes = max(1, int(float(road.get("lanes", 1))))
    carriageway_half = max(38.0, lanes * 38.0 + 10.0) * base.ROAD_WIDTH_SCALE * 0.5
    sidewalk = max(28.0, float(road.get("sidewalk_width", 28))) * base.SIDEWALK_SCALE
    curb = max(4.0, float(road.get("curb_width", 4)))
    return carriageway_half + sidewalk + curb


def nearest_frontage(building, roads, road_points):
    x = float(building["x"]); y = float(building["y"])
    w = float(building["w"]); h = float(building["h"])
    cx = x + w * 0.5; cy = y + h * 0.5
    best = None
    for road in roads:
        if str(road.get("bridge", "false")).lower() == "true":
            continue
        rid = road["road_id"]
        for a, b in zip(road_points[rid], road_points[rid][1:]):
            q, center_distance = segment_projection((cx, cy), a, b)
            if center_distance <= 1e-9:
                continue
            ux = (q[0] - cx) / center_distance
            uy = (q[1] - cy) / center_distance
            # Support distance of an axis-aligned footprint along the road-facing normal.
            facade_radius = abs(ux) * w * 0.5 + abs(uy) * h * 0.5
            gap = center_distance - facade_radius - road_outer_edge(road)
            candidate = (gap, center_distance, ux, uy, road)
            if best is None or candidate[0] < best[0]:
                best = candidate
    return best


def overlaps(a, b, clearance=6.0) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        ax + aw + clearance <= bx or bx + bw + clearance <= ax or
        ay + ah + clearance <= by or by + bh + clearance <= ay
    )


def target_frontage_gap(building, road) -> float:
    if building.get("building_kind") == "church_landmark":
        return 46.0
    district = building.get("district", "")
    highway = str(road.get("highway", "residential"))
    if district == "washington_heights":
        return 18.0 if highway in {"primary", "secondary"} else 22.0
    return 24.0 if highway in {"primary", "secondary"} else 30.0


def rewrite_semantics(buildings, deltas) -> None:
    base.write_csv(
        base.SEMANTIC / "iterated_buildings.csv",
        ("id", "x", "y", "w", "h", "district", "building_kind", "archetype_id", "height_scale",
         "generation_rule", "cosmetic_atlas", "cosmetic_cell", "cosmetic_world_units_per_pixel",
         "cosmetic_source_bbox_w", "cosmetic_source_bbox_h", "cosmetic_fit_scale_ratio",
         "cosmetic_render_scale_ratio", "cosmetic_scale_status", "layer_count", "roof_level",
         "stair_side", "stair_x", "stair_y", "interaction_keys", "render_mode"),
        buildings,
    )

    stair_path = base.SEMANTIC / "building_stairwells.csv"
    stairs = base.read_csv(stair_path)
    for row in stairs:
        dx, dy = deltas.get(row["building_id"], (0.0, 0.0))
        row["x"] = round(float(row["x"]) + dx, 2)
        row["y"] = round(float(row["y"]) + dy, 2)
    base.write_csv(
        stair_path,
        ("stairwell_id", "building_id", "kind", "side", "x", "y", "from_level",
         "intermediate_level", "to_level", "interaction_keys", "transition_mode"),
        stairs,
    )

    collision = []
    for row in buildings:
        x, y = base.world_to_master(row["x"], row["y"])
        collision.append({
            "building_id": row["id"], "x": x, "y": y,
            "w": round(float(row["w"]) * 0.5, 2),
            "h": round(float(row["h"]) * 0.5, 2),
        })
    base.write_csv(base.SEMANTIC / "buildings.csv", ("building_id", "x", "y", "w", "h"), collision)


def generate_pass20_buildings(roads, road_points):
    buildings, parcel_uses = _original_generate_iterated_buildings(roads, road_points)
    frontage_rows.clear()

    # Test against every current footprint; accepted moves replace the live box.
    boxes = {
        row["id"]: [float(row["x"]), float(row["y"]), float(row["w"]), float(row["h"])]
        for row in buildings
    }
    deltas: dict[str, tuple[float, float]] = {}

    for building in buildings:
        bid = building["id"]
        nearest = nearest_frontage(building, roads, road_points)
        if nearest is None:
            deltas[bid] = (0.0, 0.0)
            continue
        gap_before, _, ux, uy, road = nearest
        target = target_frontage_gap(building, road)
        desired_shift = max(0.0, min(MAX_SHIFT, gap_before - target))
        accepted_shift = 0.0

        # Keep a modest minimum outside the full road+curb+sidewalk envelope.
        # If a neighboring footprint limits a move, progressively reduce it rather
        # than changing road geometry or creating a new collision overlap.
        trial = desired_shift
        current = boxes[bid]
        while trial > 0.5:
            candidate = [current[0] + ux * trial, current[1] + uy * trial, current[2], current[3]]
            left, top, width, height = candidate
            right = left + width
            if left < base.HUDSON_EAST_X and right > base.HUDSON_WEST_X:
                trial *= 0.5
                continue
            collision = any(
                other_id != bid and overlaps(candidate, other_box)
                for other_id, other_box in boxes.items()
            )
            if collision:
                trial *= 0.5
                continue
            accepted_shift = trial
            boxes[bid] = candidate
            break

        dx = ux * accepted_shift
        dy = uy * accepted_shift
        building["x"] = round(float(building["x"]) + dx, 2)
        building["y"] = round(float(building["y"]) + dy, 2)
        building["stair_x"] = round(float(building["stair_x"]) + dx, 2)
        building["stair_y"] = round(float(building["stair_y"]) + dy, 2)
        building["generation_rule"] = "pass20_sidewalk_addressed_streetwall_v1"
        deltas[bid] = (dx, dy)

        after = nearest_frontage(building, roads, road_points)
        gap_after = after[0] if after is not None else gap_before
        intentional = building.get("building_kind") == "church_landmark"
        addressed = gap_after <= target + 12.0
        safe = gap_after >= MIN_CLEAR_GAP - 1e-6
        status = "pass" if addressed and safe else ("clearance_limited" if safe else "road_overlap_risk")
        frontage_rows.append({
            "building_id": bid,
            "district": building.get("district", ""),
            "building_kind": building.get("building_kind", ""),
            "road_id": road["road_id"],
            "road_class": road.get("highway", ""),
            "gap_before": round(gap_before, 2),
            "gap_after": round(gap_after, 2),
            "target_gap": round(target, 2),
            "shift_x": round(dx, 2),
            "shift_y": round(dy, 2),
            "shift_distance": round(accepted_shift, 2),
            "frontage_class": "intentional_setback" if intentional else "ordinary_urban",
            "addressed": "true" if addressed else "false",
            "safe_clearance": "true" if safe else "false",
            "status": status,
        })

    rewrite_semantics(buildings, deltas)
    base.write_csv(
        base.SEMANTIC / FRONTAGE_AUDIT_CSV,
        ("building_id", "district", "building_kind", "road_id", "road_class", "gap_before", "gap_after",
         "target_gap", "shift_x", "shift_y", "shift_distance", "frontage_class", "addressed",
         "safe_clearance", "status"),
        frontage_rows,
    )
    return buildings, parcel_uses


def update_manifest() -> None:
    path = base.OUT / "composition_manifest.csv"
    rows = base.read_csv(path)
    remove = {
        "pass_id", "streetwall_frontage_pass", "streetwall_frontage_rule",
        "streetwall_frontage_rows", "ordinary_frontage_addressed_share",
        "streetwall_max_shift_world", "streetwall_min_clear_gap_world",
    }
    rows = [row for row in rows if row.get("key") not in remove]
    ordinary = [r for r in frontage_rows if r["frontage_class"] == "ordinary_urban"]
    addressed = [r for r in ordinary if r["addressed"] == "true"]
    share = len(addressed) / max(1, len(ordinary))
    rows.extend([
        {"key": "pass_id", "value": PASS_ID},
        {"key": "streetwall_frontage_pass", "value": "true"},
        {"key": "streetwall_frontage_rule", "value": "nearest_legal_sidewalk_edge_bounded_shift_v1"},
        {"key": "streetwall_frontage_rows", "value": str(len(frontage_rows))},
        {"key": "ordinary_frontage_addressed_share", "value": f"{share:.4f}"},
        {"key": "streetwall_max_shift_world", "value": str(MAX_SHIFT)},
        {"key": "streetwall_min_clear_gap_world", "value": str(MIN_CLEAR_GAP)},
    ])
    base.write_csv(path, ("key", "value"), rows)


def main() -> None:
    if FRONTAGE_AUDIT_CSV not in base.SEMANTIC_FILES:
        base.SEMANTIC_FILES = tuple(base.SEMANTIC_FILES) + (FRONTAGE_AUDIT_CSV,)
    base.generate_iterated_buildings = generate_pass20_buildings
    v090.PASS_ID = PASS_ID
    v090.main()
    update_manifest()

    ordinary = [r for r in frontage_rows if r["frontage_class"] == "ordinary_urban"]
    addressed = [r for r in ordinary if r["addressed"] == "true"]
    safe = [r for r in frontage_rows if r["safe_clearance"] == "true"]
    print(
        f"PASS20_STREETWALL buildings={len(frontage_rows)} "
        f"ordinary_addressed={len(addressed)}/{len(ordinary)} "
        f"safe_clearance={len(safe)}/{len(frontage_rows)} max_shift={MAX_SHIFT:g}"
    )


if __name__ == "__main__":
    main()
