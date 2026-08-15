from __future__ import annotations

"""Build Pass 19 while freezing the approved Pass 18 world geometry.

This wrapper changes deterministic cosmetic assignment only:
- building sprites converge toward a consistent native scale without obvious clones;
- vegetation becomes denser and more varied inside retained green areas;
- roads, water/green masks, crossings, block footprints, bridge geometry and
  collision footprints continue to come from build_unified_composition.py.
"""

import math
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_unified_composition as base


PASS_ID = "art_convergence_pass_19"
usage: dict[str, Counter[tuple[str, int]]] = defaultdict(Counter)
recent: dict[str, deque[tuple[str, int]]] = defaultdict(lambda: deque(maxlen=5))
vegetation_stats: Counter[str] = Counter()


def _candidate_set(district: str, landmark: bool) -> list[tuple[str, int]]:
    fort = "fort_lee_blocks_v1.png"
    heights = "washington_heights_blocks_v1.png"
    compact = "compact_lot_blocks_v1.png"
    if district == "fort_lee":
        return [(fort, cell) for cell in range(16)] + [(compact, cell) for cell in range(8)]
    if landmark:
        return [(heights, cell) for cell in (7, 12, 14)] + [(compact, 15)]
    return ([(heights, cell) for cell in range(16) if cell not in {7, 12, 14}]
            + [(compact, cell) for cell in range(8, 15)])


def choose_building_sprite(district: str, width: float, height: float, sequence: int, landmark: bool = False) -> dict:
    """Choose a native-scale sprite, then prefer underused visually suitable peers.

    Geometry and accepted component scale remain dominant. Diversity is allowed to
    break close visual matches; it cannot rescue an undersized or badly stretched
    candidate merely to make the map look different.
    """
    candidates = _candidate_set(district, landmark)
    metrics = {
        atlas: base.building_atlas_metrics(atlas)
        for atlas in {atlas for atlas, _ in candidates}
    }
    evaluated = []
    preferred = sequence % max(1, len(candidates))
    for candidate_index, (atlas, cell) in enumerate(candidates):
        source_w, source_h = metrics[atlas][cell]
        fit = min(
            width / (source_w * base.ATLAS_WORLD_UNITS_PER_PIXEL),
            height / (source_h * base.ATLAS_WORLD_UNITS_PER_PIXEL),
        )
        render = min(base.MAX_BUILDING_SPRITE_SCALE, fit)
        bounded_error = abs(1.0 - min(base.MAX_BUILDING_SPRITE_SCALE,
                                      max(base.MIN_BUILDING_SPRITE_SCALE, fit)))
        outlier = max(0.0, base.MIN_BUILDING_SPRITE_SCALE - fit) * 8.0
        oversize = max(0.0, fit - base.MAX_BUILDING_SPRITE_SCALE) * 0.35
        aspect_error = abs(math.log(max(0.05, width / height) /
                                    max(0.05, source_w / source_h))) * 0.12
        deterministic = abs(candidate_index - preferred) * 0.0012
        native_score = bounded_error + outlier + oversize + aspect_error + deterministic
        evaluated.append((native_score, atlas, cell, source_w, source_h, fit, render))

    best_native = min(item[0] for item in evaluated)
    # Only close native-size alternatives may enter the diversity competition.
    # A 0.055 score window is intentionally narrow compared with the scale and
    # undersize penalties above.
    shortlist = [item for item in evaluated
                 if item[0] <= best_native + 0.055
                 and item[5] >= base.MIN_BUILDING_SPRITE_SCALE]
    if not shortlist:
        shortlist = [min(evaluated)]

    def convergence_score(item):
        native_score, atlas, cell, *_ = item
        key = (atlas, cell)
        used = usage[district][key]
        recent_rows = recent[district]
        # Frequency pressure grows gently. Immediate/nearby repetition is more
        # expensive because adjacent clones are the most obvious procedural tell.
        use_penalty = used * 0.010
        recency_penalty = 0.0
        if recent_rows:
            if key == recent_rows[-1]:
                recency_penalty += 0.090
            elif key in recent_rows:
                recency_penalty += 0.040
        return native_score + use_penalty + recency_penalty

    selected = min(shortlist, key=convergence_score)
    _, atlas, cell, source_w, source_h, fit, render = selected
    key = (atlas, cell)
    usage[district][key] += 1
    recent[district].append(key)
    return {
        "cosmetic_atlas": atlas,
        "cosmetic_cell": cell,
        "cosmetic_source_bbox_w": round(source_w, 2),
        "cosmetic_source_bbox_h": round(source_h, 2),
        "cosmetic_fit_scale_ratio": round(fit, 4),
        "cosmetic_render_scale_ratio": round(render, 4),
        "cosmetic_scale_status": "pass" if fit >= base.MIN_BUILDING_SPRITE_SCALE else "undersized_lot",
    }


def _polygon_area(poly: list[tuple[float, float]]) -> float:
    if len(poly) < 3:
        return 0.0
    return abs(sum(
        a[0] * b[1] - b[0] * a[1]
        for a, b in zip(poly, poly[1:] + poly[:1])
    )) * 0.5


def generate_pass19_vegetation(roads, road_points, crossings, buildings, parcel_uses):
    """Densify retained green areas with varied approved tree art.

    The pass remains cosmetic. Tree candidates are rejected near water, buildings,
    junctions and road/walkable corridors. Park interiors use a staggered lattice
    with deterministic jitter, minimum canopy spacing, sixteen atlas cells and
    several size tiers so large green polygons read as planted/wooded areas rather
    than five isolated duplicate sprites.
    """
    trees = []
    surfaces = base.authored_surfaces()
    water = surfaces["water"]
    green = surfaces["green"]
    junctions = [(float(c["x"]), float(c["y"])) for c in crossings]
    building_boxes = [
        (float(b["x"]) - 28, float(b["y"]) - 28,
         float(b["x"]) + float(b["w"]) + 28, float(b["y"]) + float(b["h"]) + 28)
        for b in buildings
    ]
    use_boxes = [
        (float(u["x"]) - 16, float(u["y"]) - 16,
         float(u["x"]) + float(u["w"]) + 16, float(u["y"]) + float(u["h"]) + 16)
        for u in parcel_uses
    ]
    road_segments = []
    for road in roads:
        n = max(1, int(float(road.get("lanes", 1))))
        half = max(38, n * 38 + 10) * base.ROAD_WIDTH_SCALE * 0.5
        for a, b in zip(road_points[road["road_id"]], road_points[road["road_id"]][1:]):
            road_segments.append((a, b, half))

    def segment_distance(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        den = dx * dx + dy * dy
        if den <= 1e-9:
            return math.hypot(p[0] - a[0], p[1] - a[1])
        t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / den))
        return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))

    def legal(p, allow_parcel=False, allow_road_edge=False):
        x, y = p
        if not (80 < x < 16304 and 2128 < y < 10160):
            return False
        if any(base.point_in_polygon(p, poly) for poly in water):
            return False
        if any(x0 < x < x1 and y0 < y < y1 for x0, y0, x1, y1 in building_boxes):
            return False
        if not allow_parcel and any(x0 < x < x1 and y0 < y < y1 for x0, y0, x1, y1 in use_boxes):
            return False
        if any(math.hypot(x - jx, y - jy) < 170 for jx, jy in junctions):
            return False
        if not allow_road_edge and any(segment_distance(p, a, b) < half + 26
                                       for a, b, half in road_segments):
            return False
        return True

    def add_tree(x, y, cell, size, district, rule):
        trees.append({
            "id": f"tree_{len(trees) + 1:04d}",
            "x": round(x, 2),
            "y": round(y, 2),
            "size": round(size, 2),
            "district": district,
            "cosmetic_atlas": "approved_sidewalk_trees_v1.png",
            "cosmetic_cell": cell % 16,
            "placement_rule": rule,
        })
        vegetation_stats[rule] += 1

    # Street trees stay deliberately less dense than park planting. Their job is
    # frontage rhythm, not to close the pedestrian corridor.
    for road_index, road in enumerate(roads):
        if road.get("bridge") == "true":
            continue
        n = max(1, int(float(road.get("lanes", 1))))
        carriageway = max(38, n * 38 + 10) * base.ROAD_WIDTH_SCALE
        sidewalk = max(28, float(road.get("sidewalk_width", 28))) * base.SIDEWALK_SCALE
        curb = max(4, float(road.get("curb_width", 4)))
        offset = carriageway * 0.5 + curb + sidewalk * 0.62
        district = ("fort_lee"
                    if max(x for x, _ in road_points[road["road_id"]]) <= base.HUDSON_WEST_X
                    else "washington_heights")
        spacing = 640 if district == "fort_lee" else 520
        for segment_index, (a, b) in enumerate(zip(
                road_points[road["road_id"]], road_points[road["road_id"]][1:])):
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length < 280:
                continue
            ux, uy = dx / length, dy / length
            nx, ny = -uy, ux
            count = max(1, int(length / spacing))
            for sample in range(count):
                t = (sample + 1) / (count + 1)
                side = -1 if (road_index + segment_index + sample) % 2 else 1
                x = a[0] + dx * t + nx * side * offset
                y = a[1] + dy * t + ny * side * offset
                if legal((x, y), allow_road_edge=True):
                    serial = road_index * 13 + segment_index * 7 + sample * 5
                    size = (142, 154, 166, 178)[serial % 4]
                    add_tree(x, y, serial, size, district,
                             "final_sidewalk_tree_pit_pass19_v2")

    # Retained green polygons get a much denser, irregular canopy. The target is
    # area-proportional but capped to avoid turning a large park into sprite noise.
    park_sizes = (158, 172, 186, 204, 220, 178, 194, 212)
    for poly_index, raw_poly in enumerate(green):
        poly = [(float(x), float(y)) for x, y in raw_poly]
        if len(poly) < 3:
            continue
        xs = [x for x, _ in poly]
        ys = [y for _, y in poly]
        left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        district = "fort_lee" if cx < base.HUDSON_WEST_X else "washington_heights"
        area = _polygon_area(poly)
        target = max(6, min(64, int(area / 36000.0) + 4))
        spacing = 196 if area > 900000 else 176
        min_spacing = spacing * 0.74
        edge_clearance = 46.0

        def comfortably_inside(p):
            x, y = p
            if not base.point_in_polygon(p, poly):
                return False
            # Keep the trunk/canopy anchor away from polygon edges where practical.
            return all(base.point_in_polygon(q, poly) for q in (
                (x + edge_clearance, y), (x - edge_clearance, y),
                (x, y + edge_clearance), (x, y - edge_clearance),
            ))

        candidates = [(cx, cy, 0, 0)]
        row = 0
        y = top + spacing * 0.55
        while y < bottom - spacing * 0.35:
            xoff = spacing * 0.5 if row % 2 else 0.0
            col = 0
            x = left + spacing * 0.45 + xoff
            while x < right - spacing * 0.30:
                # Stable sub-grid jitter breaks orchard-like regularity while
                # remaining byte-for-byte deterministic on every rebuild.
                h = (poly_index + 1) * 92821 + (row + 3) * 68917 + (col + 5) * 31337
                jx = ((h % 71) - 35) * 0.72
                jy = (((h // 71) % 71) - 35) * 0.72
                candidates.append((x + jx, y + jy, row, col))
                x += spacing
                col += 1
            y += spacing * 0.86
            row += 1

        # Secondary centroid-to-vertex candidates help narrow/irregular polygons
        # that a regular lattice could otherwise undersample.
        step = max(1, len(poly) // 8)
        for vertex_index in range(0, len(poly), step):
            vx, vy = poly[vertex_index]
            candidates.append(((cx * 2 + vx) / 3, (cy * 2 + vy) / 3,
                               100 + vertex_index, poly_index))

        placed: list[tuple[float, float]] = []
        for candidate_index, (x, y, row_id, col_id) in enumerate(candidates):
            if len(placed) >= target:
                break
            inside = comfortably_inside((x, y))
            # For very narrow green strips, allow a plain inside-polygon fallback
            # after the first pass so the vegetation layer never disappears.
            if not inside and candidate_index < len(candidates) - 8:
                continue
            if not base.point_in_polygon((x, y), poly) or not legal((x, y)):
                continue
            if any(math.hypot(x - px, y - py) < min_spacing for px, py in placed):
                continue
            serial = poly_index * 97 + candidate_index * 11 + row_id * 5 + col_id * 3
            size = park_sizes[serial % len(park_sizes)]
            # Every sixth accepted tree becomes a larger canopy anchor; adjacent
            # trees retain smaller tiers so the park has visual depth and hierarchy.
            if len(placed) % 6 == 0:
                size = max(size, 212 + (serial % 3) * 8)
            add_tree(x, y, serial, size, district,
                     "retained_park_canopy_pass19_v2")
            placed.append((x, y))

    # Plazas retain sparse, intentional planters rather than park-like density.
    for use_index, use in enumerate(parcel_uses):
        if use.get("kind") != "plaza":
            continue
        x = float(use["x"])
        y = float(use["y"])
        w = float(use["w"])
        h = float(use["h"])
        inset = min(90, max(44, min(w, h) * 0.14))
        candidates = (
            (x + inset, y + inset), (x + w - inset, y + inset),
            (x + inset, y + h - inset), (x + w - inset, y + h - inset),
        )
        for candidate_index, (tx, ty) in enumerate(candidates):
            if legal((tx, ty), allow_parcel=True):
                serial = use_index * 9 + candidate_index * 5
                add_tree(tx, ty, serial, 150 + (serial % 3) * 14, use["district"],
                         "intentional_plaza_planter_pass19_v2")

    base.write_csv(
        base.SEMANTIC / "iterated_vegetation.csv",
        ("id", "x", "y", "size", "district", "cosmetic_atlas", "cosmetic_cell", "placement_rule"),
        trees,
    )
    return trees


def main() -> None:
    usage.clear()
    recent.clear()
    vegetation_stats.clear()
    base.PASS_ID = PASS_ID
    base.choose_building_sprite = choose_building_sprite
    base.generate_iterated_vegetation = generate_pass19_vegetation
    # The source generator owns all accepted Pass 18 geometry. Calling its main
    # pipeline regenerates semantic CSVs, day/night masters and tiles with only
    # cosmetic building and vegetation assignment replaced above.
    base.main()
    total = sum(sum(counter.values()) for counter in usage.values())
    unique = len({key for counter in usage.values() for key in counter})
    max_use = max((count for counter in usage.values() for count in counter.values()), default=0)
    tree_total = sum(vegetation_stats.values())
    park_trees = vegetation_stats["retained_park_canopy_pass19_v2"]
    print(f"PASS19_ART_ASSIGNMENT buildings={total} unique_styles={unique} max_style_use={max_use}")
    print(f"PASS19_VEGETATION trees={tree_total} park_trees={park_trees} "
          f"atlas_cells=16 size_tiers=varied")
    print("Next: review unified_composition_day/night.png, then run promote_unified_composition.py only after visual approval.")


if __name__ == "__main__":
    main()
