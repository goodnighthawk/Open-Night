from __future__ import annotations

"""Pass 19b: final cosmetic frontage dressing for the v0.9.0 release candidate.

This wraps Pass 19 without changing accepted world geometry.  It adds a deterministic
zero-collision dressing layer between building facades and their nearest streets so
blocks no longer read as sterile empty pads.  The generated layer is baked into the
day/night masters before tile export and also written to semantic CSV for auditing.
"""

import math
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_unified_composition as base
import build_pass19_art_convergence as pass19

PASS_ID = "art_convergence_pass_19b_frontage"
FRONTAGE_CSV = "iterated_frontage_dressing.csv"
frontage_stats: Counter[str] = Counter()
_original_render_masters = base.render_masters


def stable_seed(text: str) -> int:
    return sum((index + 17) * ord(ch) for index, ch in enumerate(str(text)))


def segment_projection(point, a, b):
    px, py = point
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx * dx + dy * dy
    if den <= 1e-9:
        return a, math.hypot(px - a[0], py - a[1])
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / den))
    q = (a[0] + t * dx, a[1] + t * dy)
    return q, math.hypot(px - q[0], py - q[1])


def nearest_road(building, roads, road_points):
    cx = float(building["x"]) + float(building["w"]) * 0.5
    cy = float(building["y"]) + float(building["h"]) * 0.5
    best = None
    for road in roads:
        if str(road.get("bridge", "false")).lower() == "true":
            continue
        rid = road["road_id"]
        for a, b in zip(road_points[rid], road_points[rid][1:]):
            q, distance = segment_projection((cx, cy), a, b)
            candidate = (distance, q, road)
            if best is None or candidate[0] < best[0]:
                best = candidate
    return best


def generate_frontage_dressing(buildings, roads, road_points):
    rows = []
    frontage_stats.clear()

    def add(building, kind, x, y, w, h, rotation, rule):
        row = {
            "id": f"frontage_{len(rows) + 1:04d}",
            "building_id": building["id"],
            "district": building.get("district", ""),
            "kind": kind,
            "x": round(x, 2), "y": round(y, 2),
            "w": round(max(2.0, w), 2), "h": round(max(2.0, h), 2),
            "rotation": round(rotation, 2),
            "placement_rule": rule,
        }
        rows.append(row)
        frontage_stats[kind] += 1

    dressed_buildings = 0
    cluttered_buildings = 0
    for index, building in enumerate(buildings):
        nearest = nearest_road(building, roads, road_points)
        if nearest is None:
            continue
        road_distance, q, road = nearest
        x = float(building["x"]); y = float(building["y"])
        w = float(building["w"]); h = float(building["h"])
        cx = x + w * 0.5; cy = y + h * 0.5
        vx, vy = q[0] - cx, q[1] - cy
        if abs(vx) >= abs(vy):
            side = "east" if vx >= 0 else "west"
            nx, ny = (1.0, 0.0) if side == "east" else (-1.0, 0.0)
            tx, ty = 0.0, 1.0
            facade_span = h
            fx = x + w if side == "east" else x
            fy = cy
            facade_half_depth = w * 0.5
        else:
            side = "south" if vy >= 0 else "north"
            nx, ny = (0.0, 1.0) if side == "south" else (0.0, -1.0)
            tx, ty = 1.0, 0.0
            facade_span = w
            fx = cx
            fy = y + h if side == "south" else y
            facade_half_depth = h * 0.5

        lanes = max(1, int(float(road.get("lanes", 1))))
        carriageway_half = max(38.0, lanes * 38.0 + 10.0) * base.ROAD_WIDTH_SCALE * 0.5
        sidewalk = max(28.0, float(road.get("sidewalk_width", 28))) * base.SIDEWALK_SCALE
        curb = max(4.0, float(road.get("curb_width", 4)))
        free_gap = max(18.0, road_distance - facade_half_depth - carriageway_half - sidewalk - curb - 12.0)
        apron_depth = min(78.0, max(24.0, free_gap))
        apron_span = max(54.0, facade_span * 0.72)
        seed = stable_seed(building["id"])
        district = building.get("district", "")
        density_cut = 48 if district == "fort_lee" else 72
        dressed = seed % 100 < density_cut
        cluttered = dressed and (seed // 7) % 100 < (12 if district == "fort_lee" else 22)

        # Every facade gets subtle pavement wear; only a controlled subset receives
        # obvious objects.  This removes the synthetic cleanliness without turning
        # every lot into the same prop strip.
        wear_depth = min(apron_depth, 48.0 + (seed % 17))
        wx = fx + nx * wear_depth * 0.52
        wy = fy + ny * wear_depth * 0.52
        wear_w = apron_span if abs(tx) > 0 else wear_depth
        wear_h = apron_span if abs(ty) > 0 else wear_depth
        add(building, "frontage_wear", wx, wy, wear_w, wear_h,
            0 if abs(tx) > 0 else 90, "facade_apron_wear_pass19b_v1")

        if not dressed:
            continue
        dressed_buildings += 1
        if cluttered:
            cluttered_buildings += 1

        count = 2 + (seed % 2) + (2 if cluttered else 0)
        if district == "fort_lee":
            palette = ("stoop", "planter", "railing", "utility_box", "basement_grate", "service_patch")
        else:
            palette = ("stoop", "awning", "trash_bin", "utility_box", "basement_grate",
                       "sandwich_board", "railing", "service_patch")

        usable = max(36.0, apron_span - 36.0)
        for prop_index in range(count):
            serial = seed + prop_index * 37 + index * 11
            kind = palette[serial % len(palette)]
            along = ((prop_index + 1) / (count + 1) - 0.5) * usable
            along += ((serial % 19) - 9) * 1.4
            depth = 10.0 + (serial % max(8, int(apron_depth - 10)))
            # Most fixtures hug the facade; service patches/trash can sit farther out.
            if kind not in {"trash_bin", "service_patch", "sandwich_board", "planter"}:
                depth = min(depth, 27.0)
            px = fx + tx * along + nx * depth
            py = fy + ty * along + ny * depth
            sizes = {
                "stoop": (32, 18), "planter": (24, 18), "railing": (46, 7),
                "utility_box": (18, 15), "basement_grate": (32, 15),
                "service_patch": (44, 28), "awning": (42, 18), "trash_bin": (15, 15),
                "sandwich_board": (13, 18),
            }
            pw, ph = sizes[kind]
            if abs(ty) > 0:
                pw, ph = ph, pw
            add(building, kind, px, py, pw, ph, 0 if abs(tx) > 0 else 90,
                f"district_frontage_cluster_pass19b_v1:{side}")

        # A few tiny litter/wear marks break pristine repetition without becoming
        # individually important objects.
        litter_count = 1 + (seed % 3 if cluttered else 0)
        for litter_index in range(litter_count):
            serial = seed + 101 + litter_index * 23
            along = (((serial % 101) / 100.0) - 0.5) * usable
            depth = 18.0 + (serial % max(8, int(apron_depth - 12)))
            px = fx + tx * along + nx * depth
            py = fy + ty * along + ny * depth
            add(building, "litter_cluster", px, py, 8 + serial % 8, 6 + serial % 6,
                serial % 180, "subtle_frontage_litter_pass19b_v1")

    frontage_stats["dressed_buildings"] = dressed_buildings
    frontage_stats["cluttered_buildings"] = cluttered_buildings
    base.write_csv(
        base.SEMANTIC / FRONTAGE_CSV,
        ("id", "building_id", "district", "kind", "x", "y", "w", "h", "rotation", "placement_rule"),
        rows,
    )
    return rows


def _master_rect(row):
    x0, y0 = base.world_to_master(float(row["x"]) - float(row["w"]) * 0.5,
                                  float(row["y"]) - float(row["h"]) * 0.5)
    x1, y1 = base.world_to_master(float(row["x"]) + float(row["w"]) * 0.5,
                                  float(row["y"]) + float(row["h"]) * 0.5)
    return (int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1)))


def draw_frontage_layer(master: Path, rows, night: bool) -> None:
    im = Image.open(master).convert("RGBA")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay, "RGBA")
    if night:
        pavement = (50, 52, 49, 128); seam = (28, 31, 30, 150); metal = (88, 92, 88, 235)
        dark = (22, 25, 24, 230); green = (48, 78, 49, 235); warm = (126, 84, 48, 235)
        trash = (42, 48, 45, 245); paper = (117, 108, 82, 165)
    else:
        pavement = (126, 121, 109, 115); seam = (83, 82, 76, 145); metal = (133, 134, 125, 235)
        dark = (48, 50, 47, 235); green = (72, 111, 67, 235); warm = (166, 106, 54, 235)
        trash = (68, 75, 69, 245); paper = (164, 147, 109, 175)

    for row in rows:
        kind = row["kind"]
        box = _master_rect(row)
        x0, y0, x1, y1 = box
        if x1 < 0 or y1 < 0 or x0 >= im.width or y0 >= im.height:
            continue
        if kind == "frontage_wear":
            d.rectangle(box, fill=pavement)
            # Unequal slab divisions make the apron feel repaired over time.
            if x1 - x0 >= y1 - y0:
                for frac in (0.23, 0.56, 0.79):
                    xx = int(x0 + (x1 - x0) * frac)
                    d.line((xx, y0, xx, y1), fill=seam, width=1)
            else:
                for frac in (0.19, 0.49, 0.76):
                    yy = int(y0 + (y1 - y0) * frac)
                    d.line((x0, yy, x1, yy), fill=seam, width=1)
        elif kind == "stoop":
            d.rectangle(box, fill=dark, outline=metal, width=1)
            if x1 - x0 >= y1 - y0:
                for frac in (0.30, 0.58, 0.82):
                    xx = int(x0 + (x1 - x0) * frac); d.line((xx, y0, xx, y1), fill=metal, width=1)
            else:
                for frac in (0.30, 0.58, 0.82):
                    yy = int(y0 + (y1 - y0) * frac); d.line((x0, yy, x1, yy), fill=metal, width=1)
        elif kind == "planter":
            d.rectangle(box, fill=(78, 70, 54, 235), outline=metal, width=1)
            cx = (x0 + x1) // 2; cy = (y0 + y1) // 2; r = max(2, min(x1-x0, y1-y0)//3)
            d.ellipse((cx-r, cy-r, cx+r, cy+r), fill=green)
        elif kind == "railing":
            d.rectangle(box, outline=metal, width=1)
            if x1 - x0 >= y1 - y0:
                for frac in (0.2, 0.5, 0.8):
                    xx=int(x0+(x1-x0)*frac); d.line((xx,y0,xx,y1),fill=metal,width=1)
            else:
                for frac in (0.2, 0.5, 0.8):
                    yy=int(y0+(y1-y0)*frac); d.line((x0,yy,x1,yy),fill=metal,width=1)
        elif kind == "utility_box":
            d.rectangle(box, fill=metal, outline=dark, width=1)
            d.line((x0+2, (y0+y1)//2, x1-2, (y0+y1)//2), fill=dark, width=1)
        elif kind == "basement_grate":
            d.rectangle(box, fill=dark, outline=metal, width=1)
            step=max(2,(x1-x0)//5)
            for xx in range(x0+2,x1-1,step): d.line((xx,y0+1,xx,y1-1),fill=metal,width=1)
        elif kind == "service_patch":
            d.rectangle(box, fill=(seam[0], seam[1], seam[2], 105), outline=seam, width=1)
            d.line((x0+2,y1-2,x1-3,y0+3),fill=seam,width=1)
        elif kind == "awning":
            d.rectangle(box, fill=warm, outline=dark, width=1)
            if x1-x0 >= y1-y0:
                step=max(2,(x1-x0)//6)
                for xx in range(x0+step,x1,step): d.line((xx,y0,xx,y1),fill=(223,193,145,120),width=1)
            else:
                step=max(2,(y1-y0)//6)
                for yy in range(y0+step,y1,step): d.line((x0,yy,x1,yy),fill=(223,193,145,120),width=1)
        elif kind == "trash_bin":
            d.rectangle(box, fill=trash, outline=dark, width=1)
            d.line((x0, y0+2, x1, y0+2), fill=metal, width=1)
        elif kind == "sandwich_board":
            d.polygon(((x0,(y0+y1)//2),((x0+x1)//2,y0),(x1,(y0+y1)//2),((x0+x1)//2,y1)),
                      fill=warm, outline=dark)
        elif kind == "litter_cluster":
            cx=(x0+x1)//2; cy=(y0+y1)//2
            d.ellipse((cx-2,cy-1,cx+1,cy+1),fill=paper)
            d.rectangle((cx+2,cy,cx+4,cy+1),fill=paper)
            d.point((cx-3,cy+2),fill=paper)

    im = Image.alpha_composite(im, overlay).convert("RGB")
    im.save(master)


def render_masters_with_frontage(additional_buildings, parcel_uses, vegetation,
                                  roads_override, rp_override, crossings_override):
    masters = _original_render_masters(additional_buildings, parcel_uses, vegetation,
                                       roads_override, rp_override, crossings_override)
    dressing = generate_frontage_dressing(additional_buildings, roads_override, rp_override)
    for master in masters:
        draw_frontage_layer(Path(master), dressing, "night" in Path(master).name)
    return masters


def update_manifest() -> None:
    path = base.OUT / "composition_manifest.csv"
    rows = base.read_csv(path)
    rows = [row for row in rows if row.get("key") not in {
        "pass_id", "late_sidewalk_dressing_pass", "sidewalk_dressing_rule",
        "frontage_dressing_rows", "frontage_dressed_buildings", "frontage_cluttered_buildings"
    }]
    rows.extend([
        {"key": "pass_id", "value": PASS_ID},
        {"key": "late_sidewalk_dressing_pass", "value": "true"},
        {"key": "sidewalk_dressing_rule", "value": "district_frontage_cluster_pass19b_v1"},
        {"key": "frontage_dressing_rows", "value": str(sum(v for k,v in frontage_stats.items() if k not in {"dressed_buildings","cluttered_buildings"}))},
        {"key": "frontage_dressed_buildings", "value": str(frontage_stats["dressed_buildings"])},
        {"key": "frontage_cluttered_buildings", "value": str(frontage_stats["cluttered_buildings"])},
    ])
    base.write_csv(path, ("key", "value"), rows)


def main() -> None:
    base.PASS_ID = PASS_ID
    if FRONTAGE_CSV not in base.SEMANTIC_FILES:
        base.SEMANTIC_FILES = tuple(base.SEMANTIC_FILES) + (FRONTAGE_CSV,)
    base.render_masters = render_masters_with_frontage
    pass19.main()
    update_manifest()
    total_rows = sum(v for k,v in frontage_stats.items() if k not in {"dressed_buildings","cluttered_buildings"})
    print(
        f"PASS19B_FRONTAGE rows={total_rows} dressed_buildings={frontage_stats['dressed_buildings']} "
        f"cluttered_buildings={frontage_stats['cluttered_buildings']} wear={frontage_stats['frontage_wear']}"
    )
    print("Release candidate remains geometry-frozen; review day/night masters before promotion.")


if __name__ == "__main__":
    main()
