from __future__ import annotations

"""Pass 21: fixed physical component scale on top of accepted Pass 20 RC3.

The approved Pass 20 road/bridge/water/crossing geometry remains untouched.  This
pass audits the legacy whole-building atlas scale as a proxy for window/door/wall
scale, then repairs only footprints whose selected art would otherwise fall below
the fixed component band.  The repair grows the legal building footprint rather
than shrinking every architectural component.
"""

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass20_streetwall as pass20
import build_pass20_streetwall_v3 as pass20v3

PASS_ID = "pass_21_fixed_component_scale_rc1"
MIN_COMPONENT_SCALE = 0.88
MAX_COMPONENT_SCALE = 1.12
SEARCH_STEP = 2.0
MAX_CENTER_SHIFT = 36.0
COMPONENT_AUDIT_CSV = "building_component_scale_audit.csv"

_original_generate = pass20v3.generate_pass20_buildings_rc3
component_rows: list[dict[str, object]] = []


def required_extent(building):
    source_w = float(building.get("cosmetic_source_bbox_w", 0) or 0)
    source_h = float(building.get("cosmetic_source_bbox_h", 0) or 0)
    units = float(building.get("cosmetic_world_units_per_pixel", 2.0) or 2.0)
    return source_w * units * MIN_COMPONENT_SCALE, source_h * units * MIN_COMPONENT_SCALE


def recompute_stair(building) -> tuple[float, float]:
    x = float(building["x"]); y = float(building["y"])
    w = float(building["w"]); h = float(building["h"])
    side = str(building.get("stair_side", "north")).lower()
    offset = 18.0
    if side == "north":
        return x + w * 0.5, y - offset
    if side == "south":
        return x + w * 0.5, y + h + offset
    if side == "west":
        return x - offset, y + h * 0.5
    return x + w + offset, y + h * 0.5


def fit_ratio(building) -> float:
    source_w = float(building.get("cosmetic_source_bbox_w", 0) or 0)
    source_h = float(building.get("cosmetic_source_bbox_h", 0) or 0)
    units = float(building.get("cosmetic_world_units_per_pixel", 2.0) or 2.0)
    if source_w <= 0 or source_h <= 0 or units <= 0:
        return 0.0
    return min(
        float(building["w"]) / (source_w * units),
        float(building["h"]) / (source_h * units),
    )


def legal_candidate(building, rect, boxes, roads, road_points, protected_polygons) -> bool:
    if not pass20v3.candidate_is_surface_safe(rect, protected_polygons):
        return False
    if any(
        other_id != building["id"] and pass20.overlaps(rect, other_box, clearance=0.0)
        for other_id, other_box in boxes.items()
    ):
        return False
    candidate = dict(building)
    candidate.update({"x": rect[0], "y": rect[1], "w": rect[2], "h": rect[3]})
    result = pass20v3.score_frontage(candidate, roads, road_points)
    return bool(result is not None and result[4] and result[5])


def repair_component_scale(building, boxes, roads, road_points, protected_polygons):
    current_ratio = fit_ratio(building)
    if current_ratio >= MIN_COMPONENT_SCALE - 1e-9:
        return False

    required_w, required_h = required_extent(building)
    old_x = float(building["x"]); old_y = float(building["y"])
    old_w = float(building["w"]); old_h = float(building["h"])
    new_w = max(old_w, required_w)
    new_h = max(old_h, required_h)
    old_cx = old_x + old_w * 0.5
    old_cy = old_y + old_h * 0.5

    best = None
    steps = int(MAX_CENTER_SHIFT / SEARCH_STEP)
    for ix in range(-steps, steps + 1):
        for iy in range(-steps, steps + 1):
            sx = ix * SEARCH_STEP
            sy = iy * SEARCH_STEP
            shift = math.hypot(sx, sy)
            if shift > MAX_CENTER_SHIFT + 1e-9:
                continue
            rect = [old_cx + sx - new_w * 0.5, old_cy + sy - new_h * 0.5, new_w, new_h]
            if not legal_candidate(building, rect, boxes, roads, road_points, protected_polygons):
                continue
            candidate = dict(building)
            candidate.update({"x": rect[0], "y": rect[1], "w": rect[2], "h": rect[3]})
            frontage = pass20v3.score_frontage(candidate, roads, road_points)
            ratio = fit_ratio(candidate)
            if ratio < MIN_COMPONENT_SCALE - 1e-9:
                continue
            target_error = abs(float(frontage[0]) - float(frontage[3])) if frontage else 9999.0
            score = (shift, target_error, rect[1], rect[0])
            if best is None or score < best[0]:
                best = (score, rect, frontage, ratio)

    if best is None:
        return False

    _, rect, frontage, ratio = best
    building["x"] = round(rect[0], 2)
    building["y"] = round(rect[1], 2)
    building["w"] = round(rect[2], 2)
    building["h"] = round(rect[3], 2)
    building["cosmetic_fit_scale_ratio"] = round(ratio, 4)
    building["cosmetic_render_scale_ratio"] = round(min(MAX_COMPONENT_SCALE, ratio), 4)
    building["cosmetic_scale_status"] = "pass"
    building["generation_rule"] = "pass21_component_scale_locked_footprint_repair_v1"
    building["render_mode"] = "late_cosmetic_sprite_v3_component_scale_locked"
    stair_x, stair_y = recompute_stair(building)
    building["stair_x"] = round(stair_x, 2)
    building["stair_y"] = round(stair_y, 2)
    boxes[building["id"]] = list(rect)

    audit = next((r for r in pass20.frontage_rows if r["building_id"] == building["id"]), None)
    if audit is not None and frontage is not None:
        sidewalk_gap, road_clearance, road, target, addressed, safe = frontage
        audit.update({
            "road_id": road["road_id"],
            "road_class": road.get("highway", ""),
            "gap_after": round(sidewalk_gap, 2),
            "road_clearance_after": round(road_clearance, 2),
            "target_gap": round(target, 2),
            "addressed": "true" if addressed else "false",
            "safe_clearance": "true" if safe else "false",
            "status": "pass" if addressed and safe else "frontage_limited",
        })
    return True


def rewrite_pass21_semantics(buildings) -> None:
    pass20.base.write_csv(
        pass20.base.SEMANTIC / "iterated_buildings.csv",
        ("id", "x", "y", "w", "h", "district", "building_kind", "archetype_id", "height_scale",
         "generation_rule", "cosmetic_atlas", "cosmetic_cell", "cosmetic_world_units_per_pixel",
         "cosmetic_source_bbox_w", "cosmetic_source_bbox_h", "cosmetic_fit_scale_ratio",
         "cosmetic_render_scale_ratio", "cosmetic_scale_status", "layer_count", "roof_level",
         "stair_side", "stair_x", "stair_y", "interaction_keys", "render_mode"),
        buildings,
    )

    collision = []
    for row in buildings:
        x, y = pass20.base.world_to_master(row["x"], row["y"])
        collision.append({
            "building_id": row["id"], "x": x, "y": y,
            "w": round(float(row["w"]) * 0.5, 2),
            "h": round(float(row["h"]) * 0.5, 2),
        })
    pass20.base.write_csv(
        pass20.base.SEMANTIC / "buildings.csv",
        ("building_id", "x", "y", "w", "h"), collision,
    )

    stair_path = pass20.base.SEMANTIC / "building_stairwells.csv"
    stairs = pass20.base.read_csv(stair_path)
    by_id = {row["id"]: row for row in buildings}
    for row in stairs:
        building = by_id[row["building_id"]]
        row["side"] = building["stair_side"]
        row["x"] = building["stair_x"]
        row["y"] = building["stair_y"]
    pass20.base.write_csv(
        stair_path,
        ("stairwell_id", "building_id", "kind", "side", "x", "y", "from_level",
         "intermediate_level", "to_level", "interaction_keys", "transition_mode"),
        stairs,
    )

    scale_rows = []
    component_rows.clear()
    for row in buildings:
        ratio = float(row.get("cosmetic_render_scale_ratio", 0) or 0)
        status = "pass" if MIN_COMPONENT_SCALE - 1e-9 <= ratio <= MAX_COMPONENT_SCALE + 1e-9 else "fail"
        scale_rows.append({
            "building_id": row["id"], "district": row["district"], "building_kind": row["building_kind"],
            "target_w": row["w"], "target_h": row["h"], "cosmetic_atlas": row["cosmetic_atlas"],
            "cosmetic_cell": row["cosmetic_cell"], "source_bbox_w": row["cosmetic_source_bbox_w"],
            "source_bbox_h": row["cosmetic_source_bbox_h"], "fit_scale_ratio": row["cosmetic_fit_scale_ratio"],
            "render_scale_ratio": row["cosmetic_render_scale_ratio"], "status": status,
        })
        component_rows.append({
            "building_id": row["id"], "district": row["district"], "building_kind": row["building_kind"],
            "atlas": row["cosmetic_atlas"], "cell": row["cosmetic_cell"],
            "component_scale_ratio": round(ratio, 4),
            "min_allowed": MIN_COMPONENT_SCALE, "max_allowed": MAX_COMPONENT_SCALE,
            "scale_mode": "whole_sprite_proxy_until_modular_pass22",
            "status": status,
        })
    pass20.base.write_csv(
        pass20.base.SEMANTIC / "building_sprite_scale_audit.csv",
        ("building_id", "district", "building_kind", "target_w", "target_h", "cosmetic_atlas", "cosmetic_cell",
         "source_bbox_w", "source_bbox_h", "fit_scale_ratio", "render_scale_ratio", "status"),
        scale_rows,
    )
    pass20.base.write_csv(
        pass20.base.SEMANTIC / COMPONENT_AUDIT_CSV,
        ("building_id", "district", "building_kind", "atlas", "cell", "component_scale_ratio",
         "min_allowed", "max_allowed", "scale_mode", "status"), component_rows,
    )

    pass20.base.write_csv(
        pass20.base.SEMANTIC / pass20.FRONTAGE_AUDIT_CSV,
        ("building_id", "district", "building_kind", "road_id", "road_class", "gap_before", "gap_after",
         "road_clearance_before", "road_clearance_after", "target_gap", "shift_x", "shift_y", "shift_distance",
         "shift_direction", "frontage_class", "addressed", "safe_clearance", "status"),
        pass20.frontage_rows,
    )


def generate_pass21_buildings(roads, road_points):
    buildings, parcel_uses = _original_generate(roads, road_points)
    boxes = {
        row["id"]: [float(row["x"]), float(row["y"]), float(row["w"]), float(row["h"])]
        for row in buildings
    }
    surfaces = pass20.base.authored_surfaces()
    protected = list(surfaces.get("water", ())) + list(surfaces.get("green", ()))
    repaired = 0
    unresolved = []
    for building in buildings:
        if fit_ratio(building) < MIN_COMPONENT_SCALE - 1e-9:
            if repair_component_scale(building, boxes, roads, road_points, protected):
                repaired += 1
            else:
                unresolved.append(building["id"])
    rewrite_pass21_semantics(buildings)
    print(f"PASS21_COMPONENT_REPAIR repaired={repaired} unresolved={len(unresolved)} ids={','.join(unresolved[:6])}")
    return buildings, parcel_uses


def update_manifest() -> None:
    path = pass20.base.OUT / "composition_manifest.csv"
    rows = pass20.base.read_csv(path)
    remove = {
        "pass_id", "fixed_component_scale_pass", "component_scale_contract",
        "component_scale_min", "component_scale_max", "component_scale_failures",
    }
    rows = [r for r in rows if r.get("key") not in remove]
    failures = sum(1 for r in component_rows if r["status"] != "pass")
    rows.extend([
        {"key": "pass_id", "value": PASS_ID},
        {"key": "fixed_component_scale_pass", "value": "true"},
        {"key": "component_scale_contract", "value": "config/environment_component_scale.csv"},
        {"key": "component_scale_min", "value": str(MIN_COMPONENT_SCALE)},
        {"key": "component_scale_max", "value": str(MAX_COMPONENT_SCALE)},
        {"key": "component_scale_failures", "value": str(failures)},
    ])
    pass20.base.write_csv(path, ("key", "value"), rows)


def main() -> None:
    if COMPONENT_AUDIT_CSV not in pass20.base.SEMANTIC_FILES:
        pass20.base.SEMANTIC_FILES = tuple(pass20.base.SEMANTIC_FILES) + (COMPONENT_AUDIT_CSV,)
    pass20v3.PASS_ID = PASS_ID
    pass20v3.generate_pass20_buildings_rc3 = generate_pass21_buildings
    pass20v3.main()
    update_manifest()
    failures = [r for r in component_rows if r["status"] != "pass"]
    print(f"PASS21_FIXED_COMPONENT_SCALE buildings={len(component_rows)} failures={len(failures)} band={MIN_COMPONENT_SCALE:.2f}..{MAX_COMPONENT_SCALE:.2f}")


if __name__ == "__main__":
    main()
