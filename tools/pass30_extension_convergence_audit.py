from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"dev_tools"/"map_generator"/"profiles"/"gwb_gameplay"/"unified_composition"
SEM=OUT/"semantic"
MASK_DIR=OUT/"gameplay_masks"
CORE=(4096,2048,12288,6144)
NEW_SIZE=(16384,8192)
PARKS=[
    (760,420,2220,1190),(1110,6740,2820,7860),(10540,360,12290,1320),(13020,660,15140,1690),
    (10820,6740,12640,7890),(13700,6420,15720,7760),(400,2460,2700,3380),(13440,3200,16040,4110),
]


def read_csv(path):
    with path.open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


def manifest():return {r["key"]:r["value"] for r in read_csv(OUT/"composition_manifest.csv")}


def overlap(a,b,gap=0):
    return not (a[2]+gap<=b[0] or a[0]-gap>=b[2] or a[3]+gap<=b[1] or a[1]-gap>=b[3])


def point_segment_distance(p,a,b):
    px,py=p;ax,ay=a;bx,by=b;dx=bx-ax;dy=by-ay;den=dx*dx+dy*dy
    t=0 if den<=1e-9 else max(0,min(1,((px-ax)*dx+(py-ay)*dy)/den))
    return math.hypot(px-(ax+t*dx),py-(ay+t*dy))


def road_segments(rows):
    grouped=defaultdict(list)
    for r in rows:grouped[r["road_id"]].append(r)
    segs=[]
    for rid,pts in grouped.items():
        pts.sort(key=lambda r:int(float(r["point_order"])))
        for a,b in zip(pts,pts[1:]):segs.append(((float(a["x"]),float(a["y"])),(float(b["x"]),float(b["y"]))))
    return segs


def point_in_polygon(p,poly):
    x,y=p;inside=False;j=len(poly)-1
    for i in range(len(poly)):
        xi,yi=poly[i];xj,yj=poly[j]
        if ((yi>y)!=(yj>y)) and x < (xj-xi)*(y-yi)/((yj-yi) or 1e-9)+xi:inside=not inside
        j=i
    return inside


def hudson_polygon():
    return [(6620,0),(9340,0),(9250,620),(9410,1320),(9310,2048),(9344,2048),(9344,6144),
            (9270,6740),(9385,7360),(9290,8192),(6580,8192),(6660,7440),(6510,6810),(6528,6144),
            (6528,2048),(6600,1420),(6485,720)]


def patch_mean(im,x0,y0,x1,y1):
    crop=im.crop((x0,y0,x1,y1));n=max(1,crop.width*crop.height)
    sums=[0,0,0]
    for px in crop.getdata():
        for i in range(3):sums[i]+=px[i]
    return tuple(v/n for v in sums)


def rgb_distance(a,b):return sum(abs(x-y) for x,y in zip(a,b))/3


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--strict",action="store_true");args=ap.parse_args()
    m=manifest();problems=[]
    expected={
        "pass_id":"pass_30_extension_convergence_rc1",
        "pass30_extension_convergence":"true",
        "pass30_transition_rule":"road_safe_core_edge_streetwall_belt_v1",
        "pass30_open_space_policy":"preserve_pass29_open_blocks_and_authored_parks",
        "pass30_component_scale_policy":"fixed_pixel_roof_stair_vocabulary_no_parent_scaling",
        "pass30_water_palette_authority":"protected_core_sample",
    }
    for k,v in expected.items():
        if m.get(k)!=v:problems.append(f"manifest {k}={m.get(k)!r}, expected {v!r}")

    day=Image.open(OUT/"unified_composition_day.png").convert("RGB")
    night=Image.open(OUT/"unified_composition_night.png").convert("RGB")
    if day.size!=NEW_SIZE or night.size!=NEW_SIZE:problems.append(f"wrong master size day={day.size} night={night.size}")

    transition=read_csv(SEM/"pass30_transition_buildings.csv")
    buildings=read_csv(SEM/"pass29_extension_buildings.csv")
    layers=read_csv(SEM/"pass30_extension_building_layers.csv")
    stairs=read_csv(SEM/"pass30_extension_stairwells.csv")
    open_rows=read_csv(SEM/"pass29_extension_open_blocks.csv")
    road_rows=read_csv(SEM/"pass29_extension_roads.csv")
    segs=road_segments(road_rows)

    by_id={r["building_id"]:r for r in buildings}
    transition_ids={r["building_id"] for r in transition}
    if not transition_ids.issubset(by_id):problems.append("transition catalogue is not a subset of extension buildings")
    fixed_fail=[r["building_id"] for r in buildings if r.get("fixed_component_scale")!="true"]
    if fixed_fail:problems.append(f"non-fixed-scale buildings: {fixed_fail[:8]}")

    open_rects=[]
    for r in open_rows:
        x=float(r["x"]);y=float(r["y"]);w=float(r["w"]);h=float(r["h"]);open_rects.append((x,y,x+w,y+h))
    open_rects.extend(PARKS)
    core_exp=(CORE[0]-24,CORE[1]-24,CORE[2]+24,CORE[3]+24)
    core_hits=[];water_hits=[];open_hits=[];road_hits=[]
    poly=hudson_polygon()
    for r in transition:
        x=float(r["x"]);y=float(r["y"]);w=float(r["w"]);h=float(r["h"]);box=(x,y,x+w,y+h);cx=x+w*.5;cy=y+h*.5
        if overlap(box,core_exp):core_hits.append(r["building_id"])
        samples=((x,y),(x+w,y),(x,y+h),(x+w,y+h),(cx,cy))
        if any(point_in_polygon(p,poly) for p in samples):water_hits.append(r["building_id"])
        if any(overlap(box,o,22) for o in open_rects):open_hits.append(r["building_id"])
        halfdiag=math.hypot(w,h)*.5
        dist=min((point_segment_distance((cx,cy),a,b) for a,b in segs),default=1e9)
        if dist < 72+halfdiag:road_hits.append((r["building_id"],round(dist,1),round(72+halfdiag,1)))
    if core_hits:problems.append(f"transition/core overlap: {core_hits[:8]}")
    if water_hits:problems.append(f"transition/Hudson overlap: {water_hits[:8]}")
    if open_hits:problems.append(f"transition/open-block overlap: {open_hits[:8]}")
    if road_hits:problems.append(f"transition road-clearance failures: {road_hits[:8]}")

    layer_counts=Counter(r["building_id"] for r in layers);stair_counts=Counter(r["building_id"] for r in stairs)
    bad_layers=[bid for bid in by_id if layer_counts[bid]!=3]
    bad_stairs=[bid for bid in by_id if stair_counts[bid]!=1]
    layer_kinds=defaultdict(set)
    for r in layers:layer_kinds[r["building_id"]].add(r["layer_kind"])
    bad_layer_kinds=[bid for bid in by_id if layer_kinds[bid]!={"ground","upper","roof"}]
    if bad_layers:problems.append(f"buildings without exactly 3 layers: {bad_layers[:8]}")
    if bad_layer_kinds:problems.append(f"bad ground/upper/roof layer sets: {bad_layer_kinds[:8]}")
    if bad_stairs:problems.append(f"buildings without exactly one stairwell: {bad_stairs[:8]}")

    # Compare small open-water patches immediately inside/outside the protected
    # north/south boundary. A same-palette river should have sub-pixel mean error;
    # use a patch so a single low-contrast texture line cannot cause false failure.
    seam_errors=[]
    for im in (day,night):
        north_in=patch_mean(im,8050,CORE[1]+24,8330,CORE[1]+64)
        north_out=patch_mean(im,8050,CORE[1]-64,8330,CORE[1]-24)
        south_in=patch_mean(im,8050,CORE[3]-64,8330,CORE[3]-24)
        south_out=patch_mean(im,8050,CORE[3]+24,8330,CORE[3]+64)
        seam_errors.extend([rgb_distance(north_in,north_out),rgb_distance(south_in,south_out)])
    worst_seam=max(seam_errors,default=999)
    if worst_seam>2.0:problems.append(f"Hudson palette seam error {worst_seam:.3f} > 2 RGB")

    mask_tiles=int(m.get("pass30_gameplay_mask_tiles","0") or 0)
    for name in ("solid","walkable","cycle","collision"):
        p=MASK_DIR/f"{name}_mask_master.png"
        if not p.exists():problems.append(f"missing {p.name}")
        elif Image.open(p).size!=NEW_SIZE:problems.append(f"{p.name} wrong size")
    if mask_tiles!=512:problems.append(f"gameplay mask tiles={mask_tiles}, expected 512")

    merged=sum(int(float(r.get("merged_lot_count",1) or 1))>=2 for r in transition)
    district_counts=Counter(r.get("district","") for r in transition)
    print(
        "PASS30_EXTENSION_AUDIT "
        f"transition={len(transition)} merged_transition={merged} extension_total={len(buildings)} "
        f"districts={dict(district_counts)} layers={len(layers)} stairs={len(stairs)} "
        f"worst_water_seam={worst_seam:.3f} mask_tiles={mask_tiles}"
    )

    if args.strict:
        if len(transition)<56:problems.append(f"only {len(transition)} transition buildings")
        if merged<6:problems.append(f"only {merged} merged transition buildings")
        if len(buildings)<350:problems.append(f"extension total only {len(buildings)}")
        if len(open_rows)<50:problems.append(f"only {len(open_rows)} Pass-29 open blocks survived")
        if len(layers)!=len(buildings)*3:problems.append("layer row count is not exactly 3x extension buildings")
        if len(stairs)!=len(buildings):problems.append("stair row count is not exactly 1x extension buildings")

    if problems:
        print("PASS30_EXTENSION_GATE=FAIL")
        for p in problems:print(" - "+p)
        return 1
    print("PASS30_EXTENSION_GATE=PASS")
    return 0


if __name__=="__main__":raise SystemExit(main())
