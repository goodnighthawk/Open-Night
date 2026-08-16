from __future__ import annotations

import argparse
import csv
import math
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SEM=ROOT/"dev_tools"/"map_generator"/"profiles"/"gwb_gameplay"/"unified_composition"/"semantic"


def rows(path):
    with Path(path).open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def segdist(p,a,b):
    dx=b[0]-a[0];dy=b[1]-a[1];den=dx*dx+dy*dy
    if den<=1e-9:return math.hypot(p[0]-a[0],p[1]-a[1])
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den))
    return math.hypot(p[0]-(a[0]+t*dx),p[1]-(a[1]+t*dy))


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--strict",action="store_true");args=ap.parse_args()
    details=rows(SEM/"street_detail_pass23.csv")
    stairs=rows(SEM/"building_stairwells.csv")
    crossings=rows(SEM/"crossings.csv")
    buildings=rows(SEM/"iterated_buildings.csv")
    counts=Counter(r["kind"] for r in details)
    districts=Counter(r["district"] for r in details)
    road_details=[r for r in details if r.get("side")=="road"]
    sidewalk_details=[r for r in details if r.get("side")!="road"]

    stair_pts=[(float(r["x"]),float(r["y"])) for r in stairs]
    crossing_pts=[(float(r["x"]),float(r["y"])) for r in crossings]
    boxes=[(float(b["x"])-8,float(b["y"])-8,float(b["x"])+float(b["w"])+8,float(b["y"])+float(b["h"])+8) for b in buildings]
    stair_viol=[];cross_viol=[];building_viol=[]
    for r in sidewalk_details:
        p=(float(r["x"]),float(r["y"]))
        if any(math.hypot(p[0]-x,p[1]-y)<68-1e-6 for x,y in stair_pts):stair_viol.append(r["id"])
        if any(math.hypot(p[0]-x,p[1]-y)<130-1e-6 for x,y in crossing_pts):cross_viol.append(r["id"])
        if any(x0<p[0]<x1 and y0<p[1]<y1 for x0,y0,x1,y1 in boxes):building_viol.append(r["id"])
    road_cross=[r["id"] for r in road_details if any(math.hypot(float(r["x"])-x,float(r["y"])-y)<150-1e-6 for x,y in crossing_pts)]

    required={"hydrant","streetlamp","trash_bin","bench","mailbox","bike_rack","bollard","utility_cover","sidewalk_repair","curb_patch","tree_pit","manhole","asphalt_patch","drain"}
    missing=sorted(required-set(counts))
    print("PASS23_STREET_DETAIL_AUDIT "
          f"rows={len(details)} kinds={len(counts)} sidewalk={len(sidewalk_details)} road={len(road_details)} "
          f"fort_lee={districts['fort_lee']} washington_heights={districts['washington_heights']} "
          f"stair_viol={len(stair_viol)} crossing_viol={len(cross_viol)+len(road_cross)} building_viol={len(building_viol)}")
    if not args.strict:return 0
    problems=[]
    if len(details)<180:problems.append(f"street-detail layer too sparse: {len(details)} rows (<180)")
    if missing:problems.append(f"missing detail kinds: {missing}")
    if len(sidewalk_details)<130:problems.append("fewer than 130 sidewalk/verge details")
    if len(road_details)<25:problems.append("fewer than 25 restrained road-surface details")
    if districts['fort_lee']<55 or districts['washington_heights']<85:problems.append(f"district density too low: {dict(districts)}")
    if stair_viol:problems.append(f"{len(stair_viol)} details violate stair keep-outs")
    if cross_viol or road_cross:problems.append(f"{len(cross_viol)+len(road_cross)} details violate crossing keep-outs")
    if building_viol:problems.append(f"{len(building_viol)} sidewalk details overlap building buffers")
    if problems:
        print("PASS23_STREET_DETAIL_GATE=FAIL")
        for p in problems:print(" - "+p)
        return 1
    print("PASS23_STREET_DETAIL_GATE=PASS");return 0

if __name__=="__main__":raise SystemExit(main())
