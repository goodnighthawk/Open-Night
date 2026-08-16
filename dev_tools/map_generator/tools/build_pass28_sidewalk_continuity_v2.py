from __future__ import annotations

"""Pass 28 RC2: junction-aware semantic continuity on top of RC1 visual repair.

RC1 correctly restores the canonical visual sidewalk/curb ribbons after all late
art layers. Its first semantic sampler also proved that no sampled sidewalk was
blocked by a solid, but it incorrectly counted intersection asphalt as a missing
sidewalk on long avenues. RC2 excludes samples that lie inside another road's
full ribbon; those locations are junction/crossing space, not sidewalk gaps.
"""

import math
import sys
from pathlib import Path

from PIL import Image

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))

import build_pass20_streetwall as pass20
import build_pass26_art_first_world as p26
import build_pass28_sidewalk_continuity as base

PASS_ID="pass_28_sidewalk_continuity_rc2"


def segment_distance(p,a,b):
    dx=b[0]-a[0];dy=b[1]-a[1];den=dx*dx+dy*dy
    if den<=1e-9:return math.hypot(p[0]-a[0],p[1]-a[1])
    t=max(0.0,min(1.0,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den))
    q=(a[0]+t*dx,a[1]+t*dy)
    return math.hypot(p[0]-q[0],p[1]-q[1])


def sample_sidewalk_semantics_v2(roads,rp):
    walkable=Image.open(p26.MASK_DIR/"walkable_mask_master.png").convert("L")
    solid=Image.open(p26.MASK_DIR/"solid_mask_master.png").convert("L")
    ribbons=[]
    for road in roads:
        if str(road.get("bridge","false")).lower()=="true":continue
        half,sidewalk,curb=base.road_metrics(road)
        outer=half+curb+sidewalk+8.0
        for a,b in zip(rp[road["road_id"]],rp[road["road_id"]][1:]):
            ribbons.append((road["road_id"],a,b,outer))

    rows=[]
    for road in roads:
        rid=road["road_id"]
        if str(road.get("bridge","false")).lower()=="true":continue
        half,sidewalk,curb=base.road_metrics(road);samples=good=blocked=excluded_junction=0
        points=rp[rid]
        for a,b in zip(points,points[1:]):
            dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
            if length<1:continue
            ux,uy=dx/length,dy/length;nx,ny=-uy,ux
            count=max(1,int(length/120.0))
            for index in range(count+1):
                t=(index+.5)/(count+1);bx=a[0]+dx*t;by=a[1]+dy*t
                for sign in (-1,1):
                    offset=half+curb+sidewalk*.56
                    wx=bx+nx*sign*offset;wy=by+ny*sign*offset;p=(wx,wy)
                    # If this sidewalk-center sample is inside another street's
                    # complete ribbon, it belongs to a junction/crossing zone.
                    # Crossings provide the pedestrian connection there; requiring
                    # a sidewalk material pixel would be geometrically wrong.
                    if any(other!=rid and segment_distance(p,aa,bb)<outer
                           for other,aa,bb,outer in ribbons):
                        excluded_junction+=1;continue
                    mx,my=pass20.base.world_to_master(wx,wy);x=int(round(mx));y=int(round(my))
                    if not (0<=x<walkable.width and 0<=y<walkable.height):continue
                    samples+=1
                    is_walk=walkable.getpixel((x,y))>0;is_blocked=solid.getpixel((x,y))>0
                    if is_walk and not is_blocked:good+=1
                    if is_blocked:blocked+=1
        share=good/samples if samples else 1.0
        rows.append({
            "road_id":rid,"road_class":road.get("highway",""),"samples":samples,
            "excluded_junction_samples":excluded_junction,
            "clear_walkable_samples":good,"solid_blocked_samples":blocked,
            "clear_walkable_share":round(share,4),
            "continuity_status":"pass" if share>=.97 else "fail",
        })
    pass20.base.write_csv(pass20.base.SEMANTIC/base.REPORT_CSV,
        ("road_id","road_class","samples","excluded_junction_samples","clear_walkable_samples","solid_blocked_samples","clear_walkable_share","continuity_status"),rows)
    return rows


def update_manifest_v2(masters,repair_mask,report):
    path=pass20.base.OUT/"composition_manifest.csv";rows=pass20.base.read_csv(path)
    remove={"pass_id","pass28_sidewalk_continuity","pass28_sidewalk_rule","pass28_repaired_pixels",
            "pass28_sampled_roads","pass28_failed_roads","pass28_min_clear_walkable_share",
            "pass28_excluded_junction_samples"}
    rows=[r for r in rows if r.get("key") not in remove and not r.get("key","").startswith("sha256_unified_composition_")]
    repaired_pixels=sum(repair_mask.histogram()[1:])
    failed=[r for r in report if r["continuity_status"]!="pass"]
    min_share=min((float(r["clear_walkable_share"]) for r in report),default=1.0)
    excluded=sum(int(r["excluded_junction_samples"]) for r in report)
    rows.extend([
        {"key":"pass_id","value":PASS_ID},
        {"key":"pass28_sidewalk_continuity","value":"true"},
        {"key":"pass28_sidewalk_rule","value":"canonical_visual_ribbon_repaint_after_final_art_then_redress_junction_aware_v2"},
        {"key":"pass28_repaired_pixels","value":str(repaired_pixels)},
        {"key":"pass28_sampled_roads","value":str(len(report))},
        {"key":"pass28_failed_roads","value":str(len(failed))},
        {"key":"pass28_min_clear_walkable_share","value":f"{min_share:.4f}"},
        {"key":"pass28_excluded_junction_samples","value":str(excluded)},
    ])
    for master in masters:rows.append({"key":f"sha256_{master.stem}","value":pass20.base.sha256(master)})
    pass20.base.write_csv(path,("key","value"),rows)


def main():
    base.PASS_ID=PASS_ID
    base.sample_sidewalk_semantics=sample_sidewalk_semantics_v2
    base.update_manifest=update_manifest_v2
    base.main()


if __name__=="__main__":main()
