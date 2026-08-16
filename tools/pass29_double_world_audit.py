from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageChops

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"dev_tools"/"map_generator"/"profiles"/"gwb_gameplay"/"unified_composition"
SEM=OUT/"semantic"
OLD_W,OLD_H=8192,4096
NEW_W,NEW_H=16384,8192
CORE_X,CORE_Y=4096,2048
CORE_BOX=(CORE_X,CORE_Y,CORE_X+OLD_W,CORE_Y+OLD_H)


def read_csv(path):
    with path.open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


def manifest():
    return {r["key"]:r["value"] for r in read_csv(OUT/"composition_manifest.csv")}


def segments(rows):
    grouped=defaultdict(list);meta={}
    for r in rows:
        grouped[r["road_id"]].append(r);meta[r["road_id"]]=r
    out=[]
    for rid,pts in grouped.items():
        pts=sorted(pts,key=lambda r:int(r["point_order"]))
        for a,b in zip(pts,pts[1:]):out.append((rid,a,b,meta[rid]))
    return out


def point_segment_distance(p,a,b):
    px,py=p;ax,ay=a;bx,by=b;dx=bx-ax;dy=by-ay;den=dx*dx+dy*dy
    t=0 if den<=1e-9 else max(0,min(1,((px-ax)*dx+(py-ay)*dy)/den))
    return math.hypot(px-(ax+t*dx),py-(ay+t*dy))


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--strict",action="store_true");args=ap.parse_args()
    m=manifest();problems=[]
    expected={
        "pass_id":"pass_29_double_world_rc2",
        "pass29_double_world":"true",
        "pass29_linear_extent_multiplier":"2",
        "pass29_area_multiplier":"4",
        "pass29_master_size":"16384x8192",
        "pass29_world_size":"32768x16384",
        "pass29_component_scale_policy":"fixed_pixels_no_map_stretch",
        "pass29_hudson_policy":"continuous_north_south_extension_protected_core_unchanged",
        "pass29_church_landmark_refinement":"true",
        "pass29_church_landmark_rule":"deterministic_large_merged_footprints_two_per_land_side_v1",
    }
    for k,v in expected.items():
        if m.get(k)!=v:problems.append(f"manifest {k}={m.get(k)!r}, expected {v!r}")

    day=Image.open(OUT/"unified_composition_day.png").convert("RGB")
    night=Image.open(OUT/"unified_composition_night.png").convert("RGB")
    if day.size!=(NEW_W,NEW_H) or night.size!=(NEW_W,NEW_H):problems.append(f"master size day={day.size} night={night.size}")
    if float(m.get("pass29_protected_core_mean_rgb_error","999"))>1e-9:problems.append("protected Pass-28 core changed")

    roads=read_csv(SEM/"pass29_extension_roads.csv")
    buildings=read_csv(SEM/"pass29_extension_buildings.csv")
    crossings=read_csv(SEM/"pass29_extension_crossings.csv")
    opens=read_csv(SEM/"pass29_extension_open_blocks.csv")
    segs=segments(roads)
    angled=0
    for _,a,b,_ in segs:
        dx=abs(float(b["x"])-float(a["x"]));dy=abs(float(b["y"])-float(a["y"]))
        if dx>4 and dy>4:angled+=1
    angled_share=angled/max(1,len(segs))

    merged=sum(int(float(r["merged_lot_count"]))>=2 for r in buildings)
    churches=sum(r["kind"]=="church" for r in buildings)
    merged_share=merged/max(1,len(buildings))
    church_by_district=Counter(r.get("district","") for r in buildings if r.get("kind")=="church")
    if any(r.get("fixed_component_scale")!="true" for r in buildings):problems.append("extension has non-fixed-scale building components")

    # No new building may intrude into the protected core or the conservative
    # Hudson continuation. A generous road-centre clearance catches obvious
    # building-over-road regressions without pretending this is the final mask QA.
    road_hits=[];core_hits=[];hudson_hits=[]
    for r in buildings:
        x=float(r["x"]);y=float(r["y"]);w=float(r["w"]);h=float(r["h"]);cx=x+w*.5;cy=y+h*.5
        if x<CORE_BOX[2] and x+w>CORE_BOX[0] and y<CORE_BOX[3] and y+h>CORE_BOX[1]:core_hits.append(r["building_id"])
        if 6470<cx<9550:hudson_hits.append(r["building_id"])
        if segs:
            dist=min(point_segment_distance((cx,cy),(float(a["x"]),float(a["y"])),(float(b["x"]),float(b["y"]))) for _,a,b,_ in segs)
            if dist<82:road_hits.append((r["building_id"],round(dist,1)))
    if core_hits:problems.append(f"extension buildings overlap protected core: {core_hits[:6]}")
    if hudson_hits:problems.append(f"extension buildings occupy Hudson band: {hudson_hits[:6]}")
    if road_hits:problems.append(f"extension building centres too close to roads: {road_hits[:6]}")

    # New mask dimensions and tile counts must scale with area: 128 art tiles per
    # mode and 512 gameplay-mask tiles across the four mask families.
    mask_names=("solid","walkable","cycle","collision")
    for name in mask_names:
        p=OUT/"gameplay_masks"/f"{name}_mask_master.png"
        if not p.exists():problems.append(f"missing {p.name}");continue
        if Image.open(p).size!=(NEW_W,NEW_H):problems.append(f"{p.name} wrong size")
    art_tiles=int(m.get("pass29_art_tiles_per_mode","0") or 0);mask_tiles=int(m.get("pass29_gameplay_mask_tiles","0") or 0)
    if art_tiles!=128:problems.append(f"art tiles/mode={art_tiles}, expected 128")
    if mask_tiles!=512:problems.append(f"gameplay mask tiles={mask_tiles}, expected 512")

    print(
        "PASS29_DOUBLE_WORLD_AUDIT "
        f"size={day.size[0]}x{day.size[1]} roads={len(set(r['road_id'] for r in roads))} segments={len(segs)} "
        f"angled_share={angled_share:.3f} crossings={len(crossings)} buildings={len(buildings)} "
        f"merged={merged} merged_share={merged_share:.3f} churches={churches} church_by_district={dict(church_by_district)} "
        f"open_blocks={len(opens)} art_tiles={art_tiles} gameplay_mask_tiles={mask_tiles}"
    )

    if args.strict:
        if len(set(r["road_id"] for r in roads))<18:problems.append("too few extension roads")
        if angled_share<0.45:problems.append(f"extension road angled-segment share {angled_share:.1%} < 45%")
        if len(crossings)<20:problems.append("too few extension zebra crossings")
        if len(buildings)<220:problems.append(f"only {len(buildings)} extension buildings")
        if merged_share<0.10:problems.append(f"merged-footprint share {merged_share:.1%} < 10%")
        if churches<4:problems.append(f"only {churches} extension church landmarks")
        for district in ("new_jersey_extension","upper_manhattan_extension"):
            if church_by_district[district]<2:problems.append(f"{district} has only {church_by_district[district]} church landmarks")
        if len(opens)<8:problems.append(f"only {len(opens)} intentional open blocks")

    if problems:
        print("PASS29_DOUBLE_WORLD_GATE=FAIL")
        for p in problems:print(" - "+p)
        return 1
    print("PASS29_DOUBLE_WORLD_GATE=PASS")
    return 0


if __name__=="__main__":raise SystemExit(main())
