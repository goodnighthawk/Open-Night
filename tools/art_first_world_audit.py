from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"dev_tools"/"map_generator"/"profiles"/"gwb_gameplay"/"unified_composition"
SEM=OUT/"semantic";MASK=OUT/"gameplay_masks"
TOOLS=ROOT/"dev_tools"/"map_generator"/"tools"
if str(TOOLS) not in sys.path:sys.path.insert(0,str(TOOLS))
import build_pass20_streetwall as pass20


def rows(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


def polyline_distance_positions(points,crossings):
    segs=[];walked=0.0
    for a,b in zip(points,points[1:]):
        dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
        segs.append((a,b,walked,length));walked+=length
    pos=[]
    for c in crossings:
        p=(float(c["x"]),float(c["y"]));best=None
        for a,b,start,length in segs:
            dx=b[0]-a[0];dy=b[1]-a[1];den=dx*dx+dy*dy
            t=0 if den<=1e-9 else max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den))
            q=(a[0]+t*dx,a[1]+t*dy);d=math.hypot(p[0]-q[0],p[1]-q[1])
            candidate=(d,start+t*length)
            if best is None or candidate<best:best=candidate
        if best and best[0]<110:pos.append(best[1])
    return walked,sorted(pos)


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--strict",action="store_true");args=ap.parse_args()
    manifest={r["key"]:r["value"] for r in rows(OUT/"composition_manifest.csv")}
    infill=rows(SEM/"urban_infill_pass26.csv");mobility=rows(SEM/"mobility_crossings_pass26.csv");tiles=rows(SEM/"gameplay_mask_tiles_pass26.csv")
    # The exported semantic crossings are in master-image coordinates and omit
    # road_id. For gameplay permeability, use the authored final world crossings
    # directly; they retain road ownership and the exact world coordinates.
    roads,rp,base=pass20.base.authored_block_network()
    masters={name:Image.open(MASK/name).convert("L") for name in ("collision_mask_master.png","walkable_mask_master.png","cycle_mask_master.png")}
    expected_size=(8192,4096)
    size_fail=[name for name,im in masters.items() if im.size!=expected_size]
    tile_counts=Counter(r["layer"] for r in tiles)
    missing_tiles=[]
    for r in tiles:
        if not (OUT/r["filename"]).exists():missing_tiles.append(r["filename"])

    blank_before=int(manifest.get("pass26_sampled_blank_cells_before","0"));blank_after=int(manifest.get("pass26_sampled_blank_cells_after","999999"))
    total_crossings=len(base)+len(mobility);shared=sum(r.get("mode")=="shared_ped_cycle" for r in mobility)
    collision=masters["collision_mask_master.png"]
    collision_cross=[]
    for r in mobility:
        mx,my=pass20.base.world_to_master(float(r["x"]),float(r["y"]));px=max(0,min(collision.width-1,int(round(mx))));py=max(0,min(collision.height-1,int(round(my))))
        if collision.getpixel((px,py))>0:collision_cross.append(r["id"])

    # Permeability is checked by maximum along-road gap on major urban roads,
    # using old intersection crossings plus new art-first mid-block crossings.
    major_gaps=[]
    thresholds={"primary":720.0,"secondary":780.0,"tertiary":900.0}
    by_road=defaultdict(list)
    for r in base+mobility:
        rid=r.get("road_id")
        if rid:by_road[rid].append(r)
    for road in roads:
        cls=road.get("highway","residential")
        if cls not in thresholds or str(road.get("bridge","false")).lower()=="true":continue
        length,pos=polyline_distance_positions(rp[road["road_id"]],by_road.get(road["road_id"],[]))
        checkpoints=[0.0]+pos+[length]
        gap=max((b-a for a,b in zip(checkpoints,checkpoints[1:])),default=length)
        major_gaps.append((road["road_id"],cls,gap,thresholds[cls]))
    gap_fail=[r for r in major_gaps if r[2]>r[3]]
    worst=max((r[2] for r in major_gaps),default=0.0)

    collision_nonzero=sum(1 for p in collision.getdata() if p>0)
    collision_share=collision_nonzero/(collision.width*collision.height)
    kinds=Counter(r["kind"] for r in infill)
    solid=sum(r.get("collision_class")=="solid" for r in infill)
    open_use=len(infill)-solid
    print("PASS26_ART_FIRST_AUDIT "
          f"infill={len(infill)} solid={solid} open_use={open_use} infill_kinds={len(kinds)} blank={blank_before}->{blank_after} "
          f"base_crossings={len(base)} added_crossings={len(mobility)} shared_cycle={shared} total_crossings={total_crossings} "
          f"major_gap_failures={len(gap_fail)} worst_major_gap={worst:.1f} collision_crossings={len(collision_cross)} "
          f"mask_tiles={dict(tile_counts)} collision_share={collision_share:.3f} size_fail={len(size_fail)} missing_tiles={len(missing_tiles)}")
    if not args.strict:return 0
    problems=[]
    if manifest.get("pass_id")!="pass_26_art_first_world_rc2":problems.append("Pass 26 RC2 manifest id missing")
    if manifest.get("art_first_world_pass")!="true":problems.append("art-first world flag missing")
    if len(infill)<55:problems.append(f"functional infill too sparse: {len(infill)} (<55)")
    if len(kinds)<6:problems.append(f"functional infill lacks variety: {len(kinds)} kinds")
    if solid<25:problems.append(f"too few secondary solid urban structures: {solid} (<25)")
    if open_use<20:problems.append(f"too few purposeful open/service uses: {open_use} (<20)")
    if blank_before<55:problems.append(f"too few dead-space regions were identified: {blank_before}")
    if blank_after>max(3,int(blank_before*.15)):problems.append(f"too many sampled blank regions remain: {blank_after}/{blank_before}")
    if len(mobility)<35:problems.append(f"too few added ped/cycle crossings: {len(mobility)} (<35)")
    if shared<20:problems.append(f"too few shared pedestrian/cycle crossings: {shared} (<20)")
    if total_crossings<=len(base):problems.append("road permeability did not increase")
    if gap_fail:
        worst_rows=sorted(gap_fail,key=lambda r:r[2],reverse=True)[:5]
        problems.append("major-road crossing gaps too large: "+", ".join(f"{rid}={gap:.0f}>{limit:.0f}" for rid,_,gap,limit in worst_rows))
    if collision_cross:problems.append(f"{len(collision_cross)} new crossings are collision-blocked")
    if size_fail:problems.append(f"gameplay mask size mismatch: {size_fail}")
    for layer in ("collision","walkable","cycle"):
        if tile_counts[layer]!=32:problems.append(f"{layer} tile count {tile_counts[layer]} != 32")
    if missing_tiles:problems.append(f"{len(missing_tiles)} gameplay mask tiles missing")
    if not (.05<=collision_share<=.55):problems.append(f"implausible collision-mask occupancy {collision_share:.3f}")
    if problems:
        print("PASS26_ART_FIRST_GATE=FAIL")
        for p in problems:print(" - "+p)
        return 1
    print("PASS26_ART_FIRST_GATE=PASS");return 0

if __name__=="__main__":raise SystemExit(main())
