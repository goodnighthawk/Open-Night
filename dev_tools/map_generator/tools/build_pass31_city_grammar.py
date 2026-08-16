from __future__ import annotations

"""Pass 31: apply the approved-core city grammar to doubled-world generation.

Pass 29/30 established the safe doubled geometry and removed the obvious core and
river seams.  Pass 31 changes *how extension buildings are generated*: lots are
organized into short street-wall runs, merged-lot frequency comes from the CSV
art contract, irregular massing dominates without one shape taking over, nearby
buildings share height/material families, and deliberate negative space remains
protected.  The protected Pass-28 core is still pasted unchanged.
"""

import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass29_double_world as p29
import build_pass30_extension_convergence as p30
import city_art_grammar as grammar

PASS_ID = "pass_31_city_grammar_rc1"
SEM = p29.SEMANTIC
OUT = p29.OUT
ASSIGNMENT_FILE = "pass31_city_grammar_assignments.csv"
SCREENSHOT_DIR = Path(__file__).resolve().parents[3] / "qa" / "pass31_screenshots"


def write_csv(path: Path, fields, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=fields,extrasaction="ignore")
        writer.writeheader();writer.writerows(rows)


def read_csv(path: Path):
    with path.open("r",encoding="utf-8-sig",newline="") as handle:
        return list(csv.DictReader(handle))


def shape_polygons(x:int,y:int,w:int,h:int,variant:str):
    """Single/multi-polygon massing families at fixed component scale."""
    if variant=="L":
        cutw=max(26,int(w*.35));cuth=max(26,int(h*.38))
        return [[(x,y),(x+w,y),(x+w,y+h),(x+cutw,y+h),(x+cutw,y+cuth),(x,y+cuth)]]
    if variant in {"U","courtyard"}:
        arm=max(28,int(w*.23));notch=max(30,int(h*.43))
        return [[(x,y),(x+w,y),(x+w,y+h),(x+w-arm,y+h),(x+w-arm,y+notch),(x+arm,y+notch),(x+arm,y+h),(x,y+h)]]
    if variant=="chamfer":
        c=max(12,min(34,int(min(w,h)*.14)))
        return [[(x+c,y),(x+w-c,y),(x+w,y+c),(x+w,y+h),(x,y+h),(x,y+c)]]
    if variant=="stepped":
        sx=max(24,int(w*.28));sy=max(22,int(h*.24))
        return [[(x,y),(x+w-sx,y),(x+w-sx,y+sy),(x+w,y+sy),(x+w,y+h),(x,y+h)]]
    if variant=="perimeter":
        c=max(10,min(28,int(min(w,h)*.11)))
        return [[(x+c,y),(x+w-c,y),(x+w,y+c),(x+w,y+h-c),(x+w-c,y+h),(x+c,y+h),(x,y+h-c),(x,y+c)]]
    return [[(x,y),(x+w,y),(x+w,y+h),(x,y+h)]]


def building_context(bid:str,x:int,y:int,w:int,h:int,kind:str):
    district=p29.district_for(x+w*.5)
    block=grammar.block_id_for(x+w*.5,y+h*.5,district)
    merged=1
    if kind in {"merged_apartment","church","transition_merged_apartment"}:merged=2
    variant="chamfer" if kind=="church" else grammar.massing_variant(bid,merged)
    family=grammar.material_family(district,block,bid)
    return district,block,variant,family


def draw_building_grammar(im,d,box,bid,kind,night,solid):
    P=p29.palette(night);x,y,w,h=map(int,box);s=p29.stable(bid)
    district,block,variant,family=building_context(bid,x,y,w,h,kind)
    polys=shape_polygons(x,y,w,h,variant);sd=ImageDraw.Draw(solid)
    family_index=(int(family.rsplit("_",1)[-1])-1)%len(P["roof"])
    roof=P["church"] if kind=="church" else P["roof"][family_index]
    for poly in polys:d.polygon([(px+4,py+5) for px,py in poly],fill=P["edge"])
    for poly in polys:
        d.polygon(poly,fill=roof,outline=P["edge"]);sd.polygon(poly,fill=255)

    # Fixed-size parapet/seam rhythm. Larger parents contain more repeated modules
    # rather than enlarged windows/HVAC units.
    seam_pitch=20+(s%6)
    for xx in range(x+13,x+w-10,seam_pitch):d.line((xx,y+7,xx,y+h-7),fill=P["detail"],width=1)
    for yy in range(y+18,y+h-12,38+(s%7)):
        d.line((x+8,yy,x+w-8,yy),fill=tuple(max(0,c-12) for c in P["detail"]),width=1)
    modules=max(2,min(11,(w*h)//8500+2))
    module_types=("hvac","skylight","bulkhead","vent","tank")
    for j in range(modules):
        q=p29.stable(f"grammar31:{bid}:{j}");typ=module_types[q%len(module_types)]
        if typ=="hvac":mw,mh=18,13
        elif typ=="skylight":mw,mh=24,9
        elif typ=="bulkhead":mw,mh=28,20
        elif typ=="vent":mw,mh=9,9
        else:mw,mh=16,16
        mx=x+9+(q>>9)%max(1,w-mw-18);my=y+9+(q>>19)%max(1,h-mh-18)
        d.rectangle((mx+2,my+2,mx+mw+2,my+mh+2),fill=P["edge"])
        if typ=="tank":
            d.ellipse((mx,my,mx+mw,my+mh),fill=P["warm"],outline=P["edge"])
        else:
            col=P["glass"] if typ=="skylight" else P["detail"]
            d.rectangle((mx,my,mx+mw,my+mh),fill=col,outline=P["edge"])

    if kind=="church":
        cx=x+w//2;cy=y+h//2;nav=max(18,min(w//4,34));tran=max(24,min(h//4,42))
        d.rectangle((cx-nav,y+10,cx+nav,y+h-10),outline=P["church2"],width=3)
        d.rectangle((x+10,cy-tran//2,x+w-10,cy+tran//2),outline=P["church2"],width=3)
        r=9;d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=P["church2"],outline=P["edge"])


def place_buildings_grammar(im,roads,night,solid):
    P=p29.palette(night);d=ImageDraw.Draw(im);rows=[];open_rows=[]
    occupied=[];serial=0;open_serial=0
    # Slightly smaller cells than Pass 29 increase opportunities for short frontage
    # runs while the occupancy and service-gap checks prevent visual crowding.
    cell_w,cell_h=226,188
    open_target=grammar.midpoint("block_open_space_share")
    min_gap,max_gap=grammar.bounds("block_alley_gap")
    service_gap=int(round((min_gap+max_gap)*.5))
    for gy in range(110,p29.NEW_H-110,cell_h):
        row_phase=((gy//cell_h)%2)*74
        for gx0 in range(110,p29.NEW_W-110,cell_w):
            gx=gx0+row_phase
            cx=gx+cell_w*.5;cy=gy+cell_h*.5
            if p29.core_contains(cx,cy,margin=80):continue
            if 6400<cx<9540:continue
            dist=p29.road_distance(cx,cy,roads)
            if dist<96 or dist>325:continue
            q=p29.stable(f"grammar31-lot:{gx}:{gy}")

            # Negative space is generated intentionally and at a configured rate.
            if (q%10000)<int(open_target*10000):
                w=168+(q%35);h=132+((q>>7)%30);x=int(gx+(q%21));y=int(gy+((q>>11)%23))
                box=(x,y,x+w,y+h)
                if not p29.intersects_water(box) and p29.road_distance(x+w*.5,y+h*.5,roads)>88:
                    kind=("green_court","service_court","paved_courtyard")[(q>>17)%3];open_serial+=1
                    col=P["green"] if kind=="green_court" else P["road2"]
                    d.rounded_rectangle(box,radius=10,fill=col,outline=P["curb"],width=2)
                    open_rows.append({"id":f"p31_open_{open_serial:03d}","kind":kind,"x":x,"y":y,"w":w,"h":h,"district":p29.district_for(cx)})
                continue

            key=f"{gx}:{gy}:{p29.district_for(cx)}"
            merge=grammar.merged_lot_count(key)
            w,h=grammar.candidate_size(key,merge)
            x=int(cx-w*.5+((q>>23)%25-12));y=int(cy-h*.5+((q>>29)%23-11))
            box=(x,y,x+w,y+h)
            if p29.intersects_water(box):continue
            final_dist=p29.road_distance(x+w*.5,y+h*.5,roads)
            if final_dist<92 or final_dist>305:continue
            gap=max(int(min_gap),service_gap-((q>>31)%12))
            if any(not (box[2]+gap<o[0] or box[0]-gap>o[2] or box[3]+gap<o[1] or box[1]-gap>o[3]) for o in occupied):continue
            occupied.append(box);serial+=1
            kind="merged_apartment" if merge>=2 else "urban_block"
            bid=f"pass29_building_{serial:04d}"
            draw_building_grammar(im,d,(x,y,w,h),bid,kind,night,solid)
            rows.append({"building_id":bid,"kind":kind,"district":p29.district_for(cx),"x":x,"y":y,"w":w,"h":h,
                         "merged_lot_count":merge,"fixed_component_scale":"true"})
    return rows,open_rows


def make_transition_candidates_grammar(existing,roads,open_rects):
    occupied=[(float(r["x"]),float(r["y"]),float(r["x"])+float(r["w"]),float(r["y"])+float(r["h"])) for r in existing]
    accepted=[];grids=[]
    for y in range(130,p29.NEW_H-130,166):
        grids.extend([(p30.CORE[0]-850,y),(p30.CORE[0]-620,y+58),(p30.CORE[0]-390,y+112),
                      (p30.CORE[2]+245,y+34),(p30.CORE[2]+490,y+96),(p30.CORE[2]+745,y+146)])
    for x in list(range(150,6400,178))+list(range(9700,p29.NEW_W-150,178)):
        grids.extend([(x,p30.CORE[1]-710),(x+66,p30.CORE[1]-445),(x+116,p30.CORE[1]-225),
                      (x+32,p30.CORE[3]+165),(x+90,p30.CORE[3]+402),(x+136,p30.CORE[3]+654)])
    min_gap,max_gap=grammar.bounds("block_alley_gap")
    for serial,(gx,gy) in enumerate(grids):
        if len(accepted)>=p30.TARGET_TRANSITION_BUILDINGS:break
        q=p29.stable(f"grammar31-transition:{serial}:{gx}:{gy}")
        district=p29.district_for(gx);key=f"transition:{district}:{gx}:{gy}"
        merge=grammar.merged_lot_count(key);w,h=grammar.candidate_size(key,merge)
        x=int(gx-w*.5+((q>>16)%19-9));y=int(gy-h*.5+((q>>23)%17-8))
        box=(x,y,x+w,y+h);cx=x+w*.5;cy=y+h*.5
        if not p30.in_transition_belt(cx,cy):continue
        if x<28 or y<28 or x+w>p29.NEW_W-28 or y+h>p29.NEW_H-28:continue
        if not p30.box_outside_core(box) or p29.intersects_water(box):continue
        if any(p30.rects_overlap(box,r,20) for r in open_rects):continue
        gap=int(min_gap + (q%max(1,int(max_gap-min_gap+1))))
        if any(p30.rects_overlap(box,r,gap) for r in occupied):continue
        halfdiag=math.hypot(w,h)*.5;dist=p30.nearest_road_distance((cx,cy),roads)
        if dist<68+halfdiag or dist>285:continue
        bid=f"pass30_transition_{len(accepted)+1:04d}"
        kind="transition_merged_apartment" if merge>=2 else "transition_streetwall"
        accepted.append({"building_id":bid,"kind":kind,"district":district,"x":x,"y":y,"w":w,"h":h,
                         "merged_lot_count":merge,"fixed_component_scale":"true","generation_rule":"pass31_city_grammar_streetwall_v1"})
        occupied.append(box)
    return accepted


def add_transition_art_and_masks_grammar(day,night,solid,walk,cycle,collision,transition):
    sd=ImageDraw.Draw(solid);cd=ImageDraw.Draw(collision);wd=ImageDraw.Draw(walk);cyd=ImageDraw.Draw(cycle)
    dayd=ImageDraw.Draw(day);nightd=ImageDraw.Draw(night)
    for row in transition:
        x=int(float(row["x"]));y=int(float(row["y"]));w=int(float(row["w"]));h=int(float(row["h"]));bid=row["building_id"]
        draw_building_grammar(day,dayd,(x,y,w,h),bid,row["kind"],False,solid)
        dummy=Image.new("L",day.size,0);draw_building_grammar(night,nightd,(x,y,w,h),bid,row["kind"],True,dummy)
        merged=int(float(row.get("merged_lot_count",1) or 1));variant=grammar.massing_variant(bid,merged)
        for poly in shape_polygons(x,y,w,h,variant):
            sd.polygon(poly,fill=255);cd.polygon(poly,fill=255);wd.polygon(poly,fill=0);cyd.polygon(poly,fill=0)


def write_assignments_and_manifest():
    buildings=read_csv(SEM/p29.EXTENSION_BUILDINGS);assignments=grammar.grammar_metadata(buildings)
    fields=("building_id","block_id","frontage_run_id","height_band","material_family","massing_variant","merged_lot_count","city_grammar_version")
    write_csv(SEM/ASSIGNMENT_FILE,fields,assignments)
    summary=grammar.grammar_summary(assignments)
    manifest_path=OUT/"composition_manifest.csv";manifest=p29.pass20.base.read_csv(manifest_path)
    manifest=[r for r in manifest if r.get("key")!="pass_id" and not r.get("key","").startswith("pass31_")]
    shape_counts=Counter(r["massing_variant"] for r in assignments)
    block_counts=Counter(r["block_id"] for r in assignments)
    run_counts=Counter(r["frontage_run_id"] for r in assignments)
    manifest.extend([
        {"key":"pass_id","value":PASS_ID},
        {"key":"pass31_city_grammar","value":"approved_core_v1"},
        {"key":"pass31_rules_csv","value":"config/city_art_rules.csv"},
        {"key":"pass31_buildings","value":str(len(assignments))},
        {"key":"pass31_blocks","value":str(len(block_counts))},
        {"key":"pass31_frontage_runs","value":str(len(run_counts))},
        {"key":"pass31_merged_share","value":f"{summary['merged_share']:.4f}"},
        {"key":"pass31_irregular_share","value":f"{summary['irregular_share']:.4f}"},
        {"key":"pass31_height_cluster_share","value":f"{summary['height_cluster_share']:.4f}"},
        {"key":"pass31_shape_counts","value":";".join(f"{k}:{v}" for k,v in sorted(shape_counts.items()))},
        {"key":"pass31_generation_policy","value":"block_frontage_runs_clustered_height_material_irregular_massing_deliberate_open_space"},
    ])
    p29.pass20.base.write_csv(manifest_path,("key","value"),manifest)
    return assignments,summary,shape_counts,run_counts


def save_screens(day:Image.Image,night:Image.Image):
    SCREENSHOT_DIR.mkdir(parents=True,exist_ok=True)
    day.resize((2048,1024),Image.Resampling.LANCZOS).save(SCREENSHOT_DIR/"00_whole_day.png")
    night.resize((2048,1024),Image.Resampling.LANCZOS).save(SCREENSHOT_DIR/"01_whole_night.png")
    boxes={
        "02_fort_lee_transition.png":(p30.CORE[0]-1300,p30.CORE[1]-700,p30.CORE[0]+700,p30.CORE[3]+700),
        "03_manhattan_transition.png":(p30.CORE[2]-700,p30.CORE[1]-700,p30.CORE[2]+1300,p30.CORE[3]+700),
        "04_northwest_blocks.png":(0,0,6200,3100),
        "05_northeast_blocks.png":(10100,0,p29.NEW_W,3100),
        "06_southwest_blocks.png":(0,5100,6200,p29.NEW_H),
        "07_southeast_blocks.png":(10100,5100,p29.NEW_W,p29.NEW_H),
    }
    for name,box in boxes.items():
        crop=day.crop(box);crop.thumbnail((2048,1200),Image.Resampling.LANCZOS);crop.save(SCREENSHOT_DIR/name)


def main():
    original_place=p29.place_buildings;original_draw=p29.draw_building
    original_transition=p30.make_transition_candidates;original_transition_draw=p30.add_transition_art_and_masks
    p29.place_buildings=place_buildings_grammar;p29.draw_building=draw_building_grammar
    p30.make_transition_candidates=make_transition_candidates_grammar;p30.add_transition_art_and_masks=add_transition_art_and_masks_grammar
    try:
        p30.main()
    finally:
        p29.place_buildings=original_place;p29.draw_building=original_draw
        p30.make_transition_candidates=original_transition;p30.add_transition_art_and_masks=original_transition_draw

    assignments,summary,shape_counts,run_counts=write_assignments_and_manifest()
    day=Image.open(OUT/"unified_composition_day.png").convert("RGB");night=Image.open(OUT/"unified_composition_night.png").convert("RGB")
    save_screens(day,night)
    run_sizes=list(run_counts.values())
    attached=sum(2<=n<=6 for n in run_sizes)/max(1,len(run_sizes))
    print(
        "PASS31_CITY_GRAMMAR "
        f"buildings={len(assignments)} merged_share={summary['merged_share']:.3f} irregular_share={summary['irregular_share']:.3f} "
        f"height_cluster={summary['height_cluster_share']:.3f} frontage_runs={len(run_counts)} run_target_share={attached:.3f} "
        f"shapes={dict(shape_counts)}"
    )


if __name__=="__main__":main()
