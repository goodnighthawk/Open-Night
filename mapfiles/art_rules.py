from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class ArtRuleIssue:
    severity: str
    code: str
    subject: str
    message: str


def _point_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx, vy = bx - ax, by - ay
    vv = vx * vx + vy * vy
    if vv <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / vv))
    qx, qy = ax + t * vx, ay + t * vy
    return math.hypot(px - qx, py - qy)


def _point_rect_distance(px: float, py: float, rect: Iterable[float]) -> float:
    x, y, w, h = map(float, list(rect)[:4])
    dx = max(x - px, 0.0, px - (x + w))
    dy = max(y - py, 0.0, py - (y + h))
    return math.hypot(dx, dy)


def _point_in_rect(px: float, py: float, rect: Iterable[float], margin: float = 0.0) -> bool:
    x, y, w, h = map(float, list(rect)[:4])
    return x - margin <= px <= x + w + margin and y - margin <= py <= y + h + margin


def _point_in_polygon(x: float, y: float, poly: list) -> bool:
    if len(poly) < 3:
        return False
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = map(float, poly[i]); xj, yj = map(float, poly[j])
        if ((yi > y) != (yj > y)) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _nearest_drivable_road(cfg: dict, x: float, y: float):
    best = None
    pedestrian = {"footway", "path", "cycleway", "steps", "pedestrian"}
    for road in cfg.get("roads", []) or []:
        if str(road.get("highway", "")) in pedestrian:
            continue
        pts = road.get("points", []) or []
        if len(pts) < 2:
            continue
        d = min(_point_segment_distance(x, y, float(a[0]), float(a[1]), float(b[0]), float(b[1])) for a, b in zip(pts, pts[1:]))
        if best is None or d < best[0]:
            best = (d, road)
    return best


def _best_sidewalk_band_road(cfg: dict, x: float, y: float):
    """Choose the road whose furnishing-band radius best matches the point."""
    best = None
    pedestrian = {"footway", "path", "cycleway", "steps", "pedestrian"}
    for road in cfg.get("roads", []) or []:
        if str(road.get("highway", "")) in pedestrian:
            continue
        pts = road.get("points", []) or []
        if len(pts) < 2:
            continue
        distance = min(
            _point_segment_distance(x, y, float(a[0]), float(a[1]), float(b[0]), float(b[1]))
            for a, b in zip(pts, pts[1:])
        )
        sidewalk = float(road.get("sidewalk_width", 0.0))
        target = (
            float(road.get("width", 0.0)) * 0.5
            + float(road.get("curb_width", 0.0))
            + (10.0 if sidewalk >= 20.0 else 0.0)
            + sidewalk * 0.52
        )
        score = abs(distance - target) if sidewalk >= 12.0 else float("inf")
        if best is None or score < best[0]:
            best = (score, distance, road)
    return best


def _protected_asphalt_conflict(cfg: dict, x: float, y: float) -> dict | None:
    pedestrian = {"footway", "path", "cycleway", "steps", "pedestrian"}
    for road in cfg.get("roads", []) or []:
        if str(road.get("highway", "")) in pedestrian:
            continue
        pts = road.get("points", []) or []
        if len(pts) < 2:
            continue
        distance = min(
            _point_segment_distance(x, y, float(a[0]), float(a[1]), float(b[0]), float(b[1]))
            for a, b in zip(pts, pts[1:])
        )
        protected = float(road.get("width", 0.0)) * 0.5 + float(road.get("curb_width", 0.0)) + 2.0
        if distance < protected:
            return road
    return None



def _nearest_road_tangent_deg(road: dict, x: float, y: float) -> float | None:
    best = None
    for a, b in zip(road.get("points", []) or [], (road.get("points", []) or [])[1:]):
        ax, ay = map(float, a); bx, by = map(float, b)
        d = _point_segment_distance(x, y, ax, ay, bx, by)
        if best is None or d < best[0]:
            best = (d, math.degrees(math.atan2(by - ay, bx - ax)) % 180.0)
    return None if best is None else best[1]

def _axis_angle_error_deg(a: float, b: float) -> float:
    return abs(((float(a) - float(b) + 90.0) % 180.0) - 90.0)


def _crosswalk_local_distance(crossing: dict, x: float, y: float) -> tuple[float, float]:
    """Absolute distance along crossing and across zebra from crossing center."""
    cx, cy = map(float, crossing.get("pos", [0, 0]))
    a = math.radians(float(crossing.get("angle", 0.0)))
    dx, dy = math.cos(a), math.sin(a)
    nx, ny = -dy, dx
    rx, ry = x - cx, y - cy
    return abs(rx * dx + ry * dy), abs(rx * nx + ry * ny)


def audit_art_rules(cfg: dict) -> list[ArtRuleIssue]:
    issues: list[ArtRuleIssue] = []

    # Spawns must never be in buildings/water. They can intentionally be in plazas/setbacks.
    for group in ("spawns", "login_spawns"):
        for i, p in enumerate(cfg.get(group, []) or []):
            try:
                x, y = map(float, p[:2])
            except Exception:
                continue
            if any(_point_in_rect(x, y, b) for b in cfg.get("buildings", []) or []):
                issues.append(ArtRuleIssue("ERROR", "spawn_in_building", f"{group}[{i}]", f"spawn ({x:.0f},{y:.0f}) lies inside a building"))
            if any(_point_in_polygon(x, y, poly) for poly in cfg.get("water_polygons", []) or []):
                issues.append(ArtRuleIssue("ERROR", "spawn_in_water", f"{group}[{i}]", f"spawn ({x:.0f},{y:.0f}) lies in water"))

    # Street props: normal furniture must live on a real sidewalk/furnishing zone.
    sidewalk_kinds = {"street_tree", "curved_streetlamp", "fire_hydrant", "bicycle_rack"}
    for idx, prop in enumerate(cfg.get("street_props", []) or []):
        kind = str(prop.get("kind", ""))
        subject = str(prop.get("id", f"street_prop[{idx}]"))
        try:
            x, y = map(float, prop.get("pos", [0, 0]))
        except Exception:
            continue
        clearance = 18.0 if kind == "street_tree" else 8.0
        if any(_point_rect_distance(x, y, b) < clearance for b in cfg.get("buildings", []) or []):
            issues.append(ArtRuleIssue("ERROR", "prop_hits_building", subject, f"{kind} is within {clearance:g}px of a building footprint"))

        if kind in sidewalk_kinds:
            nearest = _best_sidewalk_band_road(cfg, x, y) if kind == "curved_streetlamp" else _nearest_drivable_road(cfg, x, y)
            if nearest is None:
                issues.append(ArtRuleIssue("ERROR", "prop_no_road", subject, f"{kind} has no nearby drivable street"))
            else:
                if kind == "curved_streetlamp":
                    score, d, road = nearest
                else:
                    d, road = nearest
                    score = None
                half = float(road.get("width", 0.0)) * 0.5
                curb = float(road.get("curb_width", 0.0))
                sidewalk = float(road.get("sidewalk_width", 0.0))
                furnishing = 10.0 if sidewalk >= 20.0 else 0.0
                inner = half + curb - 2.0
                outer = half + curb + furnishing + sidewalk + 8.0
                if sidewalk < 12.0:
                    issues.append(ArtRuleIssue("ERROR", "prop_no_sidewalk", subject, f"{kind} is nearest {road.get('id','road')}, which has no usable sidewalk"))
                elif kind == "curved_streetlamp" and _protected_asphalt_conflict(cfg, x, y) is not None:
                    conflict = _protected_asphalt_conflict(cfg, x, y)
                    issues.append(ArtRuleIssue("ERROR", "prop_on_asphalt", subject, f"{kind} overlaps protected asphalt for {conflict.get('id','road')}"))
                elif kind == "curved_streetlamp" and score is not None and score > max(4.0, min(12.0, sidewalk * 0.22)):
                    issues.append(ArtRuleIssue("ERROR", "prop_far_from_sidewalk", subject, f"{kind} misses {road.get('id','road')} furnishing band by {score:.1f}px"))
                elif d < inner:
                    issues.append(ArtRuleIssue("ERROR", "prop_on_asphalt", subject, f"{kind} is {d:.1f}px from {road.get('id','road')} centerline; protected asphalt/curb starts at {inner:.1f}px"))
                elif d > outer:
                    issues.append(ArtRuleIssue("WARN", "prop_far_from_sidewalk", subject, f"{kind} is {d:.1f}px from {road.get('id','road')} centerline; sidewalk envelope ends near {outer:.1f}px"))

            # Keep pedestrian crossing approaches clear of ordinary furniture.
            for crossing in cfg.get("crosswalks", []) or []:
                along, across = _crosswalk_local_distance(crossing, x, y)
                protected_along = float(crossing.get("length", 96.0)) * 0.5 + (26.0 if kind == "street_tree" else 14.0)
                protected_across = float(crossing.get("width", 38.0)) * 0.5 + 18.0
                if along <= protected_along and across <= protected_across:
                    issues.append(ArtRuleIssue("ERROR", "prop_blocks_crosswalk", subject, f"{kind} intrudes on crosswalk {crossing.get('id','?')} clear zone"))
                    break

        elif kind == "traffic_signal":
            # Signal hardware should stay close to an authored crossing and near the curb/intersection edge.
            if cfg.get("crosswalks"):
                nearest_cw = min(math.hypot(x - float(c.get("pos", [0, 0])[0]), y - float(c.get("pos", [0, 0])[1])) for c in cfg.get("crosswalks", []))
                if nearest_cw > 125.0:
                    issues.append(ArtRuleIssue("WARN", "signal_far_from_crosswalk", subject, f"traffic signal is {nearest_cw:.1f}px from the nearest authored zebra"))
            nearest = _nearest_drivable_road(cfg, x, y)
            if nearest is not None:
                d, road = nearest
                half = float(road.get("width", 0.0)) * 0.5
                # Signal poles can sit very near a curb, but not deep inside a traffic lane.
                if d < max(8.0, half - 8.0):
                    issues.append(ArtRuleIssue("ERROR", "signal_in_lane", subject, f"traffic signal is deep inside {road.get('id','road')} asphalt ({d:.1f}px from center; half-width {half:.1f}px)"))

    # Every collision building should have one editable visual profile in v1.4.
    allowed_profiles = {"brick_midrise", "concrete_midrise", "commercial_lowrise", "industrial", "tower", "stone_midrise", "painted_walkup"}
    allowed_roofs = {"auto", "light", "dark", "brown", "tan"}
    building_ids = set(map(str, cfg.get("building_ids", []) or []))
    visuals = cfg.get("building_visuals", {}) or {}
    for bid in building_ids:
        visual = visuals.get(bid)
        if visual is None:
            issues.append(ArtRuleIssue("ERROR", "building_visual_missing", bid, "building has no building_visuals.csv profile"))
            continue
        profile = str(visual.get("profile", ""))
        if profile not in allowed_profiles:
            issues.append(ArtRuleIssue("ERROR", "building_profile_unknown", bid, f"unsupported profile {profile!r}"))
        roof = str(visual.get("roof_style", "auto"))
        if roof not in allowed_roofs:
            issues.append(ArtRuleIssue("ERROR", "building_roof_unknown", bid, f"unsupported roof_style {roof!r}"))
        height = float(visual.get("height_px", 0.0))
        if not (6.0 <= height <= 36.0):
            issues.append(ArtRuleIssue("ERROR", "building_height_range", bid, f"height_px {height:g} must stay in 6..36 for current 2.5D projection"))
    for bid in set(map(str, visuals)) - building_ids:
        issues.append(ArtRuleIssue("WARN", "building_visual_orphan", bid, "visual profile has no matching collision building"))

    # Crosswalk endpoints should land in the sidewalk envelope of the road they cross.
    for crossing in cfg.get("crosswalks", []) or []:
        cid = str(crossing.get("id", "crosswalk"))
        x, y = map(float, crossing.get("pos", [0, 0]))
        road_id = str(crossing.get("road_id", "")).strip()
        authored_road = next((r for r in cfg.get("roads", []) if str(r.get("id", "")) == road_id), None)
        nearest = (0.0, authored_road) if authored_road is not None else _nearest_drivable_road(cfg, x, y)
        if nearest is None:
            continue
        _, road = nearest
        half = float(road.get("width", 0.0)) * 0.5
        curb = float(road.get("curb_width", 0.0))
        sidewalk = float(road.get("sidewalk_width", 0.0))
        furnishing = 10.0 if sidewalk >= 20.0 else 0.0
        endpoint_r = float(crossing.get("length", 96.0)) * 0.5
        expected_min = max(0.0, half + curb - 10.0)
        expected_max = half + curb + furnishing + sidewalk + 18.0
        if not (expected_min <= endpoint_r <= expected_max):
            issues.append(ArtRuleIssue("WARN", "crosswalk_endpoint_alignment", cid, f"half-length {endpoint_r:.1f}px should land near sidewalk envelope {expected_min:.1f}-{expected_max:.1f}px for {road.get('id','road')}"))
        tangent = _nearest_road_tangent_deg(road, x, y)
        if tangent is not None:
            # Crossing angle is the zebra-bar direction. Bars must remain parallel
            # to the road/lane tangent while the crossing spans its normal.
            stripe_angle = float(crossing.get("angle", 0.0)) % 180.0
            err = _axis_angle_error_deg(stripe_angle, tangent)
            if err > 6.0:
                issues.append(ArtRuleIssue("ERROR", "crosswalk_stripes_not_parallel", cid, f"zebra bars differ from {road.get('id','road')} lane direction by {err:.1f} deg"))
        if float(crossing.get("width", 0.0)) > 30.0:
            issues.append(ArtRuleIssue("ERROR", "crosswalk_too_deep", cid, f"zebra depth {float(crossing.get('width',0.0)):.1f}px exceeds compact 30px limit"))

    return issues
