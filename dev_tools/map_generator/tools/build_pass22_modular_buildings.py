from __future__ import annotations

"""Pass 22: deterministic modular building detail system.

Pass 21 remains authoritative for legal footprints and physical component scale.
This pass adds zero-collision roof/facade modules at fixed world scale and bakes
those modules into the day/night masters.  The underlying atlas cell becomes a
base mass/roof texture rather than the building's complete visual identity.
"""

import hashlib
import math
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass20_streetwall as pass20
import build_pass21_component_scale as pass21

PASS_ID = "pass_22_modular_building_details_rc1"
MODULES_CSV = "building_modules.csv"
SIGNATURES_CSV = "building_module_signatures.csv"

_original_generate = pass21.generate_pass21_buildings
module_rows: list[dict[str, object]] = []
signature_rows: list[dict[str, object]] = []


def stable_seed(text: str) -> int:
    return int(hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:12], 16)


def archetype_facade(archetype: str, district: str) -> str:
    text = str(archetype).lower()
    if "brownstone" in text:
        return "brownstone"
    if "stone" in text or "art_deco" in text:
        return "stone"
    if "concrete" in text:
        return "concrete"
    if "commercial" in text:
        return "commercial"
    if "warehouse" in text or "industrial" in text:
        return "industrial"
    if "painted" in text:
        return "painted_masonry"
    return "brick" if district == "washington_heights" else "painted_masonry"


def add_module(building, kind, variant, x, y, w, h, *, rotation=0.0, repeat_count=1, edge="roof", rule="pass22_fixed_scale_module_v1"):
    module_rows.append({
        "module_id": f"module_{len(module_rows)+1:05d}",
        "building_id": building["id"],
        "district": building.get("district", ""),
        "component_id": kind,
        "variant": variant,
        "x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2),
        "rotation": round(rotation, 2),
        "repeat_count": int(max(1, repeat_count)),
        "scale_ratio": 1.0,
        "edge": edge,
        "placement_rule": rule,
    })


def generate_modules(buildings):
    module_rows.clear()
    signature_rows.clear()
    recent: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=4))
    signature_counts: Counter[str] = Counter()
    church_index = 0

    for index, b in enumerate(buildings):
        x = float(b["x"]); y = float(b["y"]); w = float(b["w"]); h = float(b["h"])
        seed = stable_seed(b["id"])
        district = b.get("district", "")
        facade = archetype_facade(b.get("archetype_id", ""), district)
        church = b.get("building_kind") == "church_landmark"

        if church:
            church_variants = ("old_parish_gable", "stone_steeple", "courtyard_church")
            roof_family = church_variants[church_index % len(church_variants)]
            church_index += 1
        else:
            roof_family = ("tar", "gravel", "concrete", "metal")[seed % 4]

        parapet_variant = ("plain", "stepped", "corner_caps")[(seed // 5) % 3]
        hatch_quadrant = (seed // 11) % 4
        equipment_pattern = (seed // 17) % 7
        vent_count = 1 + ((seed // 29) % 3)
        hvac_count = 1 + ((seed // 37) % (3 if w * h > 260000 else 2))
        water_tank = district == "washington_heights" and not church and (seed % 9 == 0)
        rooftop_structure = not church and w * h > 340000 and ((seed // 13) % 3 == 0)
        storefront = facade in {"commercial", "brick", "brownstone"} and ((seed // 19) % 5 in {0, 1})
        fire_escape = district == "washington_heights" and not church and ((seed // 23) % 4 != 0)

        signature = (
            f"{facade}|{roof_family}|p:{parapet_variant}|h:{hatch_quadrant}|"
            f"e:{equipment_pattern}:{hvac_count}:{vent_count}|wt:{int(water_tank)}|"
            f"rs:{int(rooftop_structure)}|sf:{int(storefront)}|fe:{int(fire_escape)}"
        )
        # Deterministically perturb a near-neighbour duplicate without including
        # the building id in the signature itself.
        if signature in recent[district]:
            equipment_pattern = (equipment_pattern + 3) % 7
            parapet_variant = ("plain", "stepped", "corner_caps")[(seed // 5 + 1) % 3]
            signature = (
                f"{facade}|{roof_family}|p:{parapet_variant}|h:{hatch_quadrant}|"
                f"e:{equipment_pattern}:{hvac_count}:{vent_count}|wt:{int(water_tank)}|"
                f"rs:{int(rooftop_structure)}|sf:{int(storefront)}|fe:{int(fire_escape)}"
            )
        recent[district].append(signature)
        signature_counts[signature] += 1

        # Parapets are repeated fixed 32-world-unit modules; rows describe the
        # repeated edge system while the renderer draws one continuous band.
        inset = 8.0
        add_module(b, "parapet", parapet_variant, x + inset, y + inset,
                   max(8.0, w - 2 * inset), 8.0, repeat_count=max(1, int((w - 16) / 32)), edge="north")
        add_module(b, "parapet", parapet_variant, x + inset, y + h - 2 * inset,
                   max(8.0, w - 2 * inset), 8.0, repeat_count=max(1, int((w - 16) / 32)), edge="south")
        add_module(b, "parapet", parapet_variant, x + inset, y + inset,
                   8.0, max(8.0, h - 2 * inset), repeat_count=max(1, int((h - 16) / 32)), edge="west")
        add_module(b, "parapet", parapet_variant, x + w - 2 * inset, y + inset,
                   8.0, max(8.0, h - 2 * inset), repeat_count=max(1, int((h - 16) / 32)), edge="east")

        # Fixed-size roof hatch, selected from four stable quadrants.
        hw, hh = 28.0, 36.0
        anchors = (
            (x + w * .28, y + h * .30), (x + w * .68, y + h * .30),
            (x + w * .28, y + h * .66), (x + w * .68, y + h * .66),
        )
        hx, hy = anchors[hatch_quadrant]
        add_module(b, "roof_hatch", f"hatch_{hatch_quadrant}", hx - hw/2, hy - hh/2, hw, hh)

        # HVAC/roof equipment stays fixed-size and multiplies on larger roofs.
        equipment_anchors = (
            (.42, .42), (.62, .58), (.34, .68), (.70, .36), (.52, .74)
        )
        for j in range(hvac_count):
            fx, fy = equipment_anchors[(equipment_pattern + j) % len(equipment_anchors)]
            large = (w * h > 420000 and j == 0 and not church)
            ew, eh = (56.0, 40.0) if large else (28.0, 22.0)
            ex = min(x + w - inset - ew, max(x + inset, x + w * fx - ew/2))
            ey = min(y + h - inset - eh, max(y + inset, y + h * fy - eh/2))
            add_module(b, "hvac_large" if large else "hvac_small", f"hvac_{equipment_pattern}_{j}", ex, ey, ew, eh)

        for j in range(vent_count):
            fx = .24 + ((seed // (41 + j * 2)) % 50) / 100.0
            fy = .22 + ((seed // (47 + j * 2)) % 52) / 100.0
            cw = ch = 18.0
            cx = min(x + w - inset - cw, max(x + inset, x + w * fx - cw/2))
            cy = min(y + h - inset - ch, max(y + inset, y + h * fy - ch/2))
            add_module(b, "chimney", f"vent_{j%3}", cx, cy, cw, ch)

        if water_tank:
            tw = th = 42.0
            add_module(b, "water_tank", f"tank_{seed%3}", x + w*.5 - tw/2, y + h*.46 - th/2, tw, th)
        if rooftop_structure:
            rw, rh = min(96.0, w*.24), min(72.0, h*.20)
            add_module(b, "rooftop_structure", f"bulkhead_{seed%4}", x + w*.52 - rw/2, y + h*.25 - rh/2, rw, rh)

        # Facade systems are represented as repeatable fixed modules on the inside
        # edge of the footprint.  Top-down rendering shows them as cornice/awning
        # cues without changing collision geometry.
        facade_variant = f"{facade}_{seed%4}"
        add_module(b, "wall_module", facade_variant, x + 8, y + h - 16, max(32.0, w - 16), 8,
                   repeat_count=max(1, int((w - 16) / 32)), edge="south")
        if storefront:
            add_module(b, "storefront_module", f"storefront_{seed%3}", x + w*.5 - 48, y + h - 20, 96, 12,
                       repeat_count=2, edge="south")
        if fire_escape:
            fe_w, fe_h = 28.0, min(56.0, max(28.0, h*.16))
            add_module(b, "fire_escape", f"fire_escape_{seed%2}", x + 8, y + h*.5 - fe_h/2, fe_w, fe_h,
                       edge="west")

        if church:
            # Distinct fixed-scale old-church roof cues; no whole-building scaling.
            if roof_family == "old_parish_gable":
                add_module(b, "church_roof_detail", "gable_ridge", x + w*.48 - 10, y + h*.20, 20, h*.58)
            elif roof_family == "stone_steeple":
                add_module(b, "church_roof_detail", "steeple", x + w*.5 - 22, y + h*.22 - 22, 44, 44)
            else:
                add_module(b, "church_roof_detail", "courtyard_ridge", x + w*.32, y + h*.30, w*.36, 22)

        building_modules = [r for r in module_rows if r["building_id"] == b["id"]]
        signature_rows.append({
            "building_id": b["id"], "district": district, "building_kind": b.get("building_kind", ""),
            "facade_family": facade, "roof_family": roof_family, "parapet_variant": parapet_variant,
            "equipment_pattern": equipment_pattern, "module_count": len(building_modules),
            "visual_signature": signature,
        })

    pass20.base.write_csv(
        pass20.base.SEMANTIC / MODULES_CSV,
        ("module_id", "building_id", "district", "component_id", "variant", "x", "y", "w", "h",
         "rotation", "repeat_count", "scale_ratio", "edge", "placement_rule"), module_rows,
    )
    pass20.base.write_csv(
        pass20.base.SEMANTIC / SIGNATURES_CSV,
        ("building_id", "district", "building_kind", "facade_family", "roof_family", "parapet_variant",
         "equipment_pattern", "module_count", "visual_signature"), signature_rows,
    )
    return signature_counts


def generate_pass22_buildings(roads, road_points):
    buildings, parcel_uses = _original_generate(roads, road_points)
    counts = generate_modules(buildings)
    print(f"PASS22_MODULE_ASSIGNMENT buildings={len(buildings)} modules={len(module_rows)} unique_signatures={len(counts)} max_signature_use={max(counts.values(), default=0)}")
    return buildings, parcel_uses


def master_rect(row):
    x0, y0 = pass20.base.world_to_master(float(row["x"]), float(row["y"]))
    x1, y1 = pass20.base.world_to_master(float(row["x"]) + float(row["w"]), float(row["y"]) + float(row["h"]))
    return tuple(map(lambda v: int(round(v)), (x0, y0, x1, y1)))


def draw_module_layer(path: Path, night: bool):
    im = Image.open(path).convert("RGBA")
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay, "RGBA")
    if night:
        edge = (128, 129, 119, 150); dark = (28, 31, 31, 220); metal = (80, 88, 88, 220)
        roof = (54, 57, 54, 180); warm = (109, 82, 53, 210); glass = (54, 77, 83, 210)
    else:
        edge = (177, 169, 148, 150); dark = (61, 63, 59, 220); metal = (118, 124, 119, 220)
        roof = (103, 101, 91, 175); warm = (151, 105, 61, 210); glass = (91, 124, 132, 205)

    for row in module_rows:
        box = master_rect(row); x0, y0, x1, y1 = box
        if x1 < 0 or y1 < 0 or x0 >= im.width or y0 >= im.height:
            continue
        kind = row["component_id"]
        variant = str(row["variant"])
        if kind == "parapet":
            d.rectangle(box, fill=(edge[0], edge[1], edge[2], 60), outline=edge, width=1)
            if variant == "stepped":
                d.line((x0, y0, x1, y1), fill=(dark[0], dark[1], dark[2], 80), width=1)
            elif variant == "corner_caps":
                r = 2
                for px, py in ((x0,y0),(x1,y0),(x0,y1),(x1,y1)):
                    d.rectangle((px-r,py-r,px+r,py+r), fill=edge)
        elif kind in {"hvac_small", "hvac_large"}:
            d.rectangle(box, fill=metal, outline=dark, width=1)
            cx=(x0+x1)//2; cy=(y0+y1)//2; rr=max(1,min(abs(x1-x0),abs(y1-y0))//4)
            d.ellipse((cx-rr,cy-rr,cx+rr,cy+rr), outline=dark, width=1)
        elif kind == "roof_hatch":
            d.rectangle(box, fill=dark, outline=edge, width=1)
            d.line((x0+2,y0+2,x1-2,y1-2), fill=edge, width=1)
        elif kind == "chimney":
            d.rectangle(box, fill=dark, outline=metal, width=1)
        elif kind == "water_tank":
            d.ellipse(box, fill=warm, outline=dark, width=1)
            d.line(((x0+x1)//2,y0,(x0+x1)//2,y1), fill=dark, width=1)
            d.line((x0,(y0+y1)//2,x1,(y0+y1)//2), fill=dark, width=1)
        elif kind == "rooftop_structure":
            d.rectangle(box, fill=roof, outline=edge, width=1)
            d.rectangle((x0+2,y0+2,x1-2,y1-2), outline=dark, width=1)
        elif kind == "wall_module":
            d.rectangle(box, fill=(dark[0],dark[1],dark[2],85))
            repeats=max(1,int(row.get("repeat_count",1)))
            if x1>x0 and repeats>1:
                for j in range(1,repeats):
                    xx=int(x0+(x1-x0)*j/repeats);d.line((xx,y0,xx,y1),fill=(edge[0],edge[1],edge[2],80),width=1)
        elif kind == "storefront_module":
            d.rectangle(box, fill=glass, outline=dark, width=1)
            mid=(x0+x1)//2; d.line((mid,y0,mid,y1),fill=edge,width=1)
        elif kind == "fire_escape":
            d.rectangle(box, outline=metal, width=1)
            step=max(2,(y1-y0)//5)
            for yy in range(y0+step,y1,step): d.line((x0,yy,x1,yy),fill=metal,width=1)
        elif kind == "church_roof_detail":
            if variant == "steeple":
                cx=(x0+x1)//2;cy=(y0+y1)//2
                d.polygon(((cx,y0),(x1,cy),(cx,y1),(x0,cy)),fill=warm,outline=edge)
            elif variant == "gable_ridge":
                d.rectangle(box, fill=(warm[0],warm[1],warm[2],80))
                d.line(((x0+x1)//2,y0,(x0+x1)//2,y1),fill=edge,width=2)
            else:
                d.rectangle(box, fill=(warm[0],warm[1],warm[2],75), outline=edge, width=1)

    Image.alpha_composite(im, overlay).convert("RGB").save(path)


def update_manifest(masters):
    path = pass20.base.OUT / "composition_manifest.csv"
    rows = pass20.base.read_csv(path)
    remove = {
        "pass_id", "modular_building_detail_pass", "building_module_rows", "building_visual_signatures",
        "building_module_scale_mode", "church_module_variants",
    }
    rows = [r for r in rows if r.get("key") not in remove and not r.get("key", "").startswith("sha256_unified_composition_")]
    signatures = Counter(r["visual_signature"] for r in signature_rows)
    church_variants = len({r["roof_family"] for r in signature_rows if r["building_kind"] == "church_landmark"})
    rows.extend([
        {"key": "pass_id", "value": PASS_ID},
        {"key": "modular_building_detail_pass", "value": "true"},
        {"key": "building_module_rows", "value": str(len(module_rows))},
        {"key": "building_visual_signatures", "value": str(len(signatures))},
        {"key": "building_module_scale_mode", "value": "fixed_world_scale_1.0"},
        {"key": "church_module_variants", "value": str(church_variants)},
    ])
    for master in masters:
        rows.append({"key": f"sha256_{master.stem}", "value": pass20.base.sha256(master)})
    pass20.base.write_csv(path, ("key", "value"), rows)


def main():
    if MODULES_CSV not in pass20.base.SEMANTIC_FILES:
        pass20.base.SEMANTIC_FILES = tuple(pass20.base.SEMANTIC_FILES) + (MODULES_CSV, SIGNATURES_CSV)
    pass21.PASS_ID = PASS_ID
    pass21.generate_pass21_buildings = generate_pass22_buildings
    pass21.main()

    masters = [
        pass20.base.OUT / "unified_composition_day.png",
        pass20.base.OUT / "unified_composition_night.png",
    ]
    draw_module_layer(masters[0], False)
    draw_module_layer(masters[1], True)
    pass20.base.tile_masters(masters)
    update_manifest(masters)
    print(f"PASS22_MODULAR_BUILDINGS modules={len(module_rows)} signatures={len(signature_rows)} masters=2 tiles=64")


if __name__ == "__main__":
    main()
