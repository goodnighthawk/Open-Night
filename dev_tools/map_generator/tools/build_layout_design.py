from __future__ import annotations

"""Deterministic authored-layout dressing pass.

This module does NOT copy GTA2 map geometry. It borrows qualitative top-down
city-design principles: memorable loops, cut-throughs, service alleys, compact
landmark compounds, district identity and dense recurring street dressing.
The semantic reference-derived game map remains authoritative for collision/routing.
"""

import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cosmetic_pack import build_pack, load_catalog, stable_int

MAP = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"
OUT = ROOT / "working_cosmetics"


def read(path: Path | str):
    p = path if isinstance(path, Path) else MAP / path
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path: Path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def fv(r, key, default=0.0):
    try:
        return float(r.get(key, default) or default)
    except Exception:
        return float(default)


def nearest_zone(x, y):
    zones = []
    for r in read("districts.csv"):
        zones.append((math.hypot(x - fv(r, "x"), y - fv(r, "y")), r["name"]))
    name = min(zones)[1] if zones else "CITY"
    return {
        "FORT LEE": "commercial",
        "GWB PLAZA": "bridge_highway",
        "WASHINGTON HEIGHTS": "dense_urban",
        "WEST EXPANSION": "residential",
        "EAST EXPANSION": "dense_urban",
        "NORTH EDGE": "industrial",
        "SOUTH EDGE": "waterfront",
    }.get(name, "dense_urban")


def choose(catalog, category, key, families=None):
    rows = [r for r in catalog if r["category"] == category and (not families or r["family"] in families)]
    return rows[stable_int(key) % len(rows)]["archetype_id"] if rows else ""


def build_massing(catalog):
    out = []
    for b in read("buildings.csv"):
        bid = b["id"]
        x, y, w, h = (fv(b, k) for k in ("x", "y", "w", "h"))
        zone = nearest_zone(x + w / 2, y + h / 2)
        seed = stable_int(f"massing:{bid}:{zone}")
        # Large semantic footprints read better as several adjacent volumes.
        # All volumes remain inside the original collision footprint.
        if w >= 240 or h >= 240:
            count = 2 + (seed % 2)
        else:
            count = 1
        vertical_split = w >= h
        gap = 6 + seed % 7
        for j in range(count):
            if vertical_split:
                usable = max(30.0, w - gap * (count - 1))
                vw = usable / count
                vx = x + j * (vw + gap)
                vy = y
                vh = h
            else:
                usable = max(30.0, h - gap * (count - 1))
                vh = usable / count
                vy = y + j * (vh + gap)
                vx = x
                vw = w
            # Small deterministic setbacks create target-like roofline variation
            # without changing the semantic building footprint.
            inset = 0 if count == 1 else (seed >> (j * 3)) % 7
            vx += inset
            vy += inset
            vw = max(28, vw - inset * 1.3)
            vh = max(28, vh - inset * 1.3)
            height_scale = 0.82 + ((seed >> (j * 5 + 2)) % 48) / 100
            out.append({
                "massing_id": f"m_{bid}_{j}",
                "building_id": bid,
                "x": round(vx, 2), "y": round(vy, 2), "w": round(vw, 2), "h": round(vh, 2),
                "height_scale": round(height_scale, 2),
                "roof_variant": (seed + j) % 6,
                "facade_variant": (seed // 7 + j) % 8,
                "style_zone": zone,
                "notes": "Cosmetic sub-volume inside authoritative collision footprint.",
            })
    write(OUT / "building_massing.csv", out)
    return out


def _overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def build_overlays():
    buildings = read("buildings.csv")
    overlays = []
    # Service alleys / cut-throughs only in genuine gaps between neighboring buildings.
    # This is intentionally cosmetic-only for now; routing stays on the semantic road graph.
    candidates = []
    for ia, a in enumerate(buildings):
        ax, ay, aw, ah = (fv(a, k) for k in ("x", "y", "w", "h"))
        for b in buildings[ia + 1:]:
            bx, by, bw, bh = (fv(b, k) for k in ("x", "y", "w", "h"))
            xov = _overlap(ax, ax + aw, bx, bx + bw)
            yov = _overlap(ay, ay + ah, by, by + bh)
            # horizontal gap, buildings side-by-side
            if yov >= 90:
                left, right = (a, b) if ax < bx else (b, a)
                lx, ly, lw, lh = (fv(left, k) for k in ("x", "y", "w", "h"))
                rx = fv(right, "x")
                gap = rx - (lx + lw)
                if 18 <= gap <= 105:
                    cy0 = max(ay, by) + 15
                    cy1 = min(ay + ah, by + bh) - 15
                    if cy1 - cy0 >= 55:
                        candidates.append((gap, "service_alley", lx + lw + gap / 2, (cy0 + cy1) / 2, gap, cy1 - cy0, 90))
            # vertical gap, buildings above/below
            if xov >= 90:
                top, bottom = (a, b) if ay < by else (b, a)
                tx, ty, tw, th = (fv(top, k) for k in ("x", "y", "w", "h"))
                by0 = fv(bottom, "y")
                gap = by0 - (ty + th)
                if 18 <= gap <= 105:
                    cx0 = max(ax, bx) + 15
                    cx1 = min(ax + aw, bx + bw) - 15
                    if cx1 - cx0 >= 55:
                        candidates.append((gap, "service_alley", (cx0 + cx1) / 2, ty + th + gap / 2, cx1 - cx0, gap, 0))
    # prefer narrow memorable cut-throughs; hard cap prevents clutter
    candidates.sort(key=lambda z: (z[0], stable_int(str(z))))
    for n, (_, kind, cx, cy, w, h, rot) in enumerate(candidates[:64]):
        overlays.append({
            "overlay_id": f"alley_{n:03d}", "kind": kind,
            "x": round(cx - w / 2, 2), "y": round(cy - h / 2, 2),
            "w": round(w, 2), "h": round(h, 2), "rotation": rot,
            "style_zone": nearest_zone(cx, cy), "gameplay_collision": "false",
            "routing": "false", "notes": "Visual/service cut-through inspired by compact top-down city navigation design.",
        })
    # Rooftop/lightwell courtyards add visual complexity to oversized masses.
    for b in buildings:
        x, y, w, h = (fv(b, k) for k in ("x", "y", "w", "h"))
        if w < 260 or h < 230:
            continue
        seed = stable_int(f"court:{b['id']}")
        cw = min(w * 0.28, 115 + seed % 55)
        ch = min(h * 0.25, 90 + (seed >> 5) % 50)
        cx = x + w * (0.45 + ((seed % 17) - 8) / 100)
        cy = y + h * (0.45 + (((seed >> 4) % 17) - 8) / 100)
        overlays.append({
            "overlay_id": f"court_{b['id']}", "kind": "roof_courtyard",
            "x": round(cx - cw / 2, 2), "y": round(cy - ch / 2, 2), "w": round(cw, 2), "h": round(ch, 2),
            "rotation": 0, "style_zone": nearest_zone(cx, cy), "gameplay_collision": "inherit_building",
            "routing": "false", "notes": "Cosmetic roof/lightwell articulation; does not alter building collision.",
        })
    write(OUT / "layout_overlays.csv", overlays)
    return overlays


def build_dressing(catalog):
    rows = []
    buildings = read("buildings.csv")
    for b in buildings:
        bid = b["id"]
        x, y, w, h = (fv(b, k) for k in ("x", "y", "w", "h"))
        zone = nearest_zone(x + w / 2, y + h / 2)
        seed = stable_int(f"dress:{bid}:{zone}")
        # target-like tree/prop cadence. These are zero-collision cosmetic instances.
        if zone in {"dense_urban", "commercial", "residential"}:
            desired = 2 + (1 if max(w, h) > 300 else 0)
            families = ["street_tree", "planter_tree", "autumn_tree"]
            for j in range(desired):
                t = (j + 1) / (desired + 1)
                side = (seed >> (j * 2)) % 2
                if side == 0:
                    px, py = x + w * t, y + h + 18
                else:
                    px, py = x + w + 18, y + h * t
                aid = choose(catalog, "vegetation", f"dress-tree:{bid}:{j}", families)
                rows.append({"dress_id": f"dt_{bid}_{j}", "kind": "tree", "archetype_id": aid, "x": round(px,2), "y": round(py,2), "scale": 0.74 + ((seed >> (j+5)) % 23)/100, "rotation": 0, "style_zone": zone, "z_layer": 31})
        # street furniture / service clutter, more in commercial/industrial/waterfront
        prop_count = {"commercial": 3, "dense_urban": 2, "residential": 1, "industrial": 3, "waterfront": 3, "bridge_highway": 2}.get(zone, 1)
        fams_by_zone = {
            "commercial": ["bench", "mailbox", "newspaper_box", "planter", "hydrant"],
            "dense_urban": ["hydrant", "mailbox", "bench", "utility_box", "planter"],
            "residential": ["bench", "hydrant", "planter"],
            "industrial": ["dumpster", "utility_box", "barrier", "construction_barrel", "crate_cluster"],
            "waterfront": ["dumpster", "bollard", "barrier", "crate_cluster", "utility_box"],
            "bridge_highway": ["barrier", "construction_barrel", "bollard", "utility_box"],
        }
        fams = fams_by_zone.get(zone, ["utility_box"])
        for j in range(prop_count):
            t = (j + 1) / (prop_count + 1)
            if (seed >> (j * 3 + 2)) % 2:
                px, py = x - 13, y + h * t
            else:
                px, py = x + w * t, y - 13
            fam = fams[(seed + j) % len(fams)]
            aid = choose(catalog, "street_prop", f"dress-prop:{bid}:{j}", [fam])
            rows.append({"dress_id": f"dp_{bid}_{j}", "kind": fam, "archetype_id": aid, "x": round(px,2), "y": round(py,2), "scale": 0.38 + ((seed >> (j+8)) % 12)/100, "rotation": 0, "style_zone": zone, "z_layer": 32})
    write(OUT / "street_dressing.csv", rows)
    return rows


def build_design_contract():
    rows = [
        {"principle":"district_identity","enabled":"true","weight":"1.0","notes":"Each district reuses a coherent building/prop/light vocabulary."},
        {"principle":"road_loops","enabled":"true","weight":"0.9","notes":"Prefer memorable looped navigation and multiple return paths; do not copy GTA2 road geometry."},
        {"principle":"service_cutthroughs","enabled":"true","weight":"0.85","notes":"Use narrow alleys/service gaps where real geometry supports them."},
        {"principle":"landmark_compounds","enabled":"true","weight":"1.0","notes":"Give bridge/major landmarks clear approach spaces and visual identity."},
        {"principle":"chokepoints","enabled":"true","weight":"0.6","notes":"Allow some readable constrictions without making routing brittle."},
        {"principle":"street_wall_continuity","enabled":"true","weight":"1.0","notes":"Buildings visually form blocks rather than isolated semantic rectangles."},
        {"principle":"gameplay_readability","enabled":"true","weight":"1.0","notes":"Road edges, crossings, vehicles and props must remain legible at gameplay zoom."},
        {"principle":"semantic_geometry_authority","enabled":"true","weight":"1.0","notes":"This pass is cosmetic/layout dressing only; collision/network identities remain stable."},
    ]
    write(OUT / "layout_design_contract.csv", rows)
    return rows


def build():
    catalog = load_catalog()
    OUT.mkdir(parents=True, exist_ok=True)
    mass = build_massing(catalog)
    overlays = build_overlays()
    dressing = build_dressing(catalog)
    contract = build_design_contract()
    print(f"[layout] {len(mass)} building sub-volumes, {len(overlays)} authored overlays, {len(dressing)} cosmetic dressing instances, {len(contract)} design principles")


if __name__ == "__main__":
    build()
