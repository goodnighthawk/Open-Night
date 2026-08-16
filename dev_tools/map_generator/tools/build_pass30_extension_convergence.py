from __future__ import annotations

"""Pass 30: converge Pass-29 outer districts toward the protected art-first core.

Pass 29 solved the doubled extent, deterministic large landmarks and exact core
preservation. Review then showed two visible seams: the Hudson palette changed at
the protected-core boundary, and the first outer blocks read too sparsely compared
with the approved Fort Lee / Washington Heights street wall. Pass 30 is deliberately
limited to the extension:

* match the outer Hudson to the approved core water palette without touching core pixels;
* add a compact road-safe transition belt of fixed-scale buildings around core land edges;
* preserve all intentional open blocks and authored extension roads;
* add richer fixed-pixel rooftop/stair details rather than scaling components;
* emit ground/upper/roof layer and exterior stairwell metadata for every extension building;
* update art and gameplay-mask tiles from the same added footprints.
"""

import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass29_double_world as p29
import build_pass29_double_world_v3 as p29rc2

PASS_ID = "pass_30_extension_convergence_rc1"
OUT = p29.OUT
SEM = p29.SEMANTIC
MASK_DIR = OUT / "gameplay_masks"
SCREENSHOT_DIR = Path(__file__).resolve().parents[3] / "qa" / "pass30_screenshots"
CORE = p29.CORE_BOX
EDGE_GAP = 24
TARGET_TRANSITION_BUILDINGS = 84

TRANSITION_FILE = "pass30_transition_buildings.csv"
LAYER_FILE = "pass30_extension_building_layers.csv"
STAIR_FILE = "pass30_extension_stairwells.csv"

# These are the intentional Pass-29 park rectangles drawn independently of the
# hashed open-block catalogue. Keep them protected from transition infill too.
P29_PARKS = [
    (760, 420, 2220, 1190), (1110, 6740, 2820, 7860),
    (10540, 360, 12290, 1320), (13020, 660, 15140, 1690),
    (10820, 6740, 12640, 7890), (13700, 6420, 15720, 7760),
    (400, 2460, 2700, 3380), (13440, 3200, 16040, 4110),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def rects_overlap(a, b, gap: float = 0.0) -> bool:
    return not (a[2] + gap <= b[0] or a[0] - gap >= b[2] or a[3] + gap <= b[1] or a[1] - gap >= b[3])


def road_rows_to_network(rows):
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    meta = {}
    for row in rows:
        grouped[row["road_id"]].append(row); meta[row["road_id"]] = row
    roads = []
    for rid, pts in grouped.items():
        pts.sort(key=lambda r: int(float(r["point_order"])))
        roads.append({
            "road_id": rid,
            "road_class": meta[rid]["road_class"],
            "lanes": int(float(meta[rid]["lanes"])),
            "points": [(float(r["x"]), float(r["y"])) for r in pts],
        })
    return roads


def point_segment_distance(p, a, b):
    px,py=p; ax,ay=a; bx,by=b; dx=bx-ax; dy=by-ay; den=dx*dx+dy*dy
    t=0.0 if den <= 1e-9 else max(0.0, min(1.0, ((px-ax)*dx+(py-ay)*dy)/den))
    return math.hypot(px-(ax+t*dx), py-(ay+t*dy))


def nearest_road_distance(p, roads) -> float:
    best = 1e9
    for road in roads:
        for a,b in zip(road["points"], road["points"][1:]):
            best = min(best, point_segment_distance(p,a,b))
    return best


def box_outside_core(box) -> bool:
    expanded=(CORE[0]-EDGE_GAP,CORE[1]-EDGE_GAP,CORE[2]+EDGE_GAP,CORE[3]+EDGE_GAP)
    return not rects_overlap(box, expanded)


def in_transition_belt(cx: float, cy: float) -> bool:
    west = CORE[0]-940 <= cx < CORE[0]-EDGE_GAP and 80 < cy < p29.NEW_H-80
    east = CORE[2]+EDGE_GAP < cx <= CORE[2]+940 and 80 < cy < p29.NEW_H-80
    north = CORE[1]-820 <= cy < CORE[1]-EDGE_GAP and (cx < 6450 or cx > 9550)
    south = CORE[3]+EDGE_GAP < cy <= CORE[3]+820 and (cx < 6450 or cx > 9550)
    return west or east or north or south


def protected_open_rects(open_rows):
    rects=[]
    for r in open_rows:
        x=float(r["x"]);y=float(r["y"]);w=float(r["w"]);h=float(r["h"])
        rects.append((x,y,x+w,y+h))
    rects.extend(P29_PARKS)
    return rects


def make_transition_candidates(existing, roads, open_rects):
    occupied=[(float(r["x"]),float(r["y"]),float(r["x"])+float(r["w"]),float(r["y"])+float(r["h"])) for r in existing]
    accepted=[]
    # Offset grids on the four core sides avoid a visible perfect lattice while
    # keeping the belt denser than the outermost districts.
    grids=[]
    for y in range(130,p29.NEW_H-130,176):
        grids.extend([(CORE[0]-850,y),(CORE[0]-630,y+62),(CORE[0]-410,y+118),
                      (CORE[2]+250,y+35),(CORE[2]+500,y+104),(CORE[2]+760,y+151)])
    for x in list(range(150,6400,190))+list(range(9700,p29.NEW_W-150,190)):
        grids.extend([(x,CORE[1]-720),(x+72,CORE[1]-455),(x+122,CORE[1]-230),
                      (x+34,CORE[3]+170),(x+96,CORE[3]+410),(x+142,CORE[3]+665)])

    seen=set()
    for serial,(gx,gy) in enumerate(grids):
        if len(accepted)>=TARGET_TRANSITION_BUILDINGS:break
        key=(round(gx/24),round(gy/24))
        if key in seen:continue
        seen.add(key)
        q=p29.stable(f"pass30:{serial}:{gx}:{gy}")
        # A minority of transition sites become visibly merged apartment masses;
        # the rest stay at the same ordinary component scale as the approved core.
        merged=2 if q%6==0 else 1
        if merged==2:
            w=176+(q%74);h=122+((q>>7)%62);kind="transition_merged_apartment"
        else:
            w=112+(q%58);h=92+((q>>7)%54);kind="transition_streetwall"
        x=int(gx-w*.5+((q>>16)%21-10));y=int(gy-h*.5+((q>>23)%19-9))
        box=(x,y,x+w,y+h);cx=x+w*.5;cy=y+h*.5
        if not in_transition_belt(cx,cy):continue
        if x<28 or y<28 or x+w>p29.NEW_W-28 or y+h>p29.NEW_H-28:continue
        if not box_outside_core(box):continue
        if p29.intersects_water(box):continue
        if any(rects_overlap(box,r,22) for r in open_rects):continue
        if any(rects_overlap(box,r,18) for r in occupied):continue
        # Keep the whole axis-aligned footprint away from the road corridor. The
        # centre threshold grows with half-diagonal, so large merged footprints do
        # not gain permission merely because their centre happens to be clear.
        halfdiag=math.hypot(w,h)*.5
        dist=nearest_road_distance((cx,cy),roads)
        if dist < 72+halfdiag or dist > 295:continue
        bid=f"pass30_transition_{len(accepted)+1:04d}"
        row={"building_id":bid,"kind":kind,"district":p29.district_for(cx),"x":x,"y":y,"w":w,"h":h,
             "merged_lot_count":merged,"fixed_component_scale":"true","generation_rule":"pass30_core_edge_streetwall_convergence_v1"}
        accepted.append(row);occupied.append(box)
    return accepted


def recolor_extension_water(im: Image.Image, mode: str) -> tuple[int,int,int]:
    # Sample a known open-water pixel well inside the approved core, away from the
    # bridge. The protected image is the color authority; no guessed palette value.
    sample=(int((CORE[0]+CORE[2])*.5), CORE[1]+700)
    reference=im.getpixel(sample)
    mask=Image.new("L",im.size,0);md=ImageDraw.Draw(mask)
    md.polygon(p29.hudson_polygon(),fill=255);md.rectangle(CORE,fill=0)
    fill=Image.new("RGB",im.size,reference)
    im.paste(fill,mask=mask)
    # Tiny low-contrast water striations retain texture without reintroducing a
    # palette seam. They are also excluded from the protected core.
    td=ImageDraw.Draw(im)
    line=tuple(max(0,c-4) for c in reference)
    for y in range(17,p29.NEW_H,43):
        if CORE[1] <= y <= CORE[3]:continue
        td.line((6480,y,9460,y),fill=line,width=1)
    return reference


def shape_polygon(row):
    bid=row["building_id"];x=int(float(row["x"]));y=int(float(row["y"]));w=int(float(row["w"]));h=int(float(row["h"]))
    variant=("L","U","chamfer","rect")[p29.stable(bid)%4]
    return p29.building_shape(x,y,w,h,variant)[0]


def decorate_roof(im: Image.Image,row,night: bool,stair_side: str) -> None:
    P=p29.palette(night);d=ImageDraw.Draw(im)
    x=int(float(row["x"]));y=int(float(row["y"]));w=int(float(row["w"]));h=int(float(row["h"]));q=p29.stable("detail30:"+row["building_id"])
    if w>96 and h>82:
        inset=8+(q%5)
        d.rounded_rectangle((x+inset,y+inset,x+w-inset,y+h-inset),radius=3,outline=P["edge"],width=2)
    # Larger footprints get a fixed-size hierarchy: bulkhead/skylight/water tank.
    if w*h>19000:
        bx=x+14+(q%max(1,w-58));by=y+15+((q>>9)%max(1,h-50))
        bw,bh=34,22
        d.rectangle((bx+2,by+3,bx+bw+2,by+bh+3),fill=P["edge"])
        d.rectangle((bx,by,bx+bw,by+bh),fill=P["detail"],outline=P["edge"],width=2)
        if q%3==0:
            sx=max(x+12,min(x+w-56,x+w//2-24));sy=y+18
            d.rectangle((sx,sy,sx+48,sy+8),fill=P["glass"],outline=P["edge"],width=1)
            for xx in range(sx+8,sx+47,8):d.line((xx,sy+1,xx,sy+7),fill=P["edge"],width=1)
        if q%7==0:
            tx=x+w-34;ty=y+26;r=10
            d.line((tx-6,ty+r,tx-9,ty+r+9),fill=P["edge"],width=2);d.line((tx+6,ty+r,tx+9,ty+r+9),fill=P["edge"],width=2)
            d.ellipse((tx-r,ty-r,tx+r,ty+r//2),fill=P["warm"],outline=P["edge"])
            d.rectangle((tx-r,ty-r//3,tx+r,ty+r),fill=P["warm"],outline=P["edge"])
    # Exterior-fire-stair visual is deliberately fixed-pixel and kept on the roof
    # edge, while semantic traversal metadata records the actual level transition.
    stair_col=P["detail"]
    if stair_side in {"west","east"}:
        sx=x+5 if stair_side=="west" else x+w-7;sy=y+max(10,h//2-18)
        for k in range(6):d.line((sx,sy+k*6,sx+(6 if stair_side=="west" else -6),sy+k*6),fill=stair_col,width=1)
    else:
        sy=y+5 if stair_side=="north" else y+h-7;sx=x+max(10,w//2-18)
        for k in range(6):d.line((sx+k*6,sy,sx+k*6,sy+(6 if stair_side=="north" else -6)),fill=stair_col,width=1)


def add_transition_art_and_masks(day,night,solid,walk,cycle,collision,transition):
    sd=ImageDraw.Draw(solid);cd=ImageDraw.Draw(collision);wd=ImageDraw.Draw(walk);cyd=ImageDraw.Draw(cycle)
    dayd=ImageDraw.Draw(day);nightd=ImageDraw.Draw(night)
    for row in transition:
        x=int(float(row["x"]));y=int(float(row["y"]));w=int(float(row["w"]));h=int(float(row["h"]));bid=row["building_id"]
        # Draw exactly the same deterministic footprint into both art modes.
        p29.draw_building(day,dayd,(x,y,w,h),bid,row["kind"],False,solid)
        dummy=Image.new("L",day.size,0)
        p29.draw_building(night,nightd,(x,y,w,h),bid,row["kind"],True,dummy)
        poly=shape_polygon(row)
        sd.polygon(poly,fill=255);cd.polygon(poly,fill=255);wd.polygon(poly,fill=0);cyd.polygon(poly,fill=0)


def extension_layers_and_stairs(rows):
    layers=[];stairs=[];sides=("north","east","south","west")
    for i,row in enumerate(rows):
        bid=row["building_id"];q=p29.stable("stair30:"+bid);side=sides[q%4]
        x=float(row["x"]);y=float(row["y"]);w=float(row["w"]);h=float(row["h"])
        for level,kind,z in ((0,"ground",0),(1,"upper",10),(2,"roof",20)):
            layers.append({"building_id":bid,"level_id":level,"layer_kind":kind,"z_order":z,"walkable":"true",
                           "visual_role":"top_layer" if kind=="roof" else "intermediate_layer","transition_policy":"exterior_stairwell_pass30"})
        inset=8
        if side=="north":sx,sy=x+w*.5,y+inset
        elif side=="south":sx,sy=x+w*.5,y+h-inset
        elif side=="west":sx,sy=x+inset,y+h*.5
        else:sx,sy=x+w-inset,y+h*.5
        stairs.append({"stairwell_id":f"pass30_stair_{i+1:04d}","building_id":bid,"kind":"exterior_fire_stair","side":side,
                       "x":round(sx,2),"y":round(sy,2),"from_level":0,"intermediate_level":1,"to_level":2,
                       "interaction_keys":"SPACE;C","transition_mode":"authored_manual_stairwell_pass30"})
    return layers,stairs


def tile_masks(masks):
    total=0
    for name,image in masks.items():
        image.save(MASK_DIR/f"{name}_mask_master.png")
        total += p29.tile_image(image,MASK_DIR/name)
    return total


def save_screens(day,night):
    SCREENSHOT_DIR.mkdir(parents=True,exist_ok=True)
    day.resize((2048,1024),Image.Resampling.LANCZOS).save(SCREENSHOT_DIR/"00_whole_day.png")
    night.resize((2048,1024),Image.Resampling.LANCZOS).save(SCREENSHOT_DIR/"01_whole_night.png")
    boxes={
        "02_west_transition.png":(CORE[0]-1100,CORE[1]-500,CORE[0]+450,CORE[3]+500),
        "03_east_transition.png":(CORE[2]-450,CORE[1]-500,CORE[2]+1100,CORE[3]+500),
        "04_north_transition.png":(CORE[0]-450,CORE[1]-1050,CORE[2]+450,CORE[1]+550),
        "05_south_transition.png":(CORE[0]-450,CORE[3]-550,CORE[2]+450,CORE[3]+1050),
        "06_river_north_seam.png":(6100,CORE[1]-900,9900,CORE[1]+900),
        "07_river_south_seam.png":(6100,CORE[3]-900,9900,CORE[3]+900),
    }
    for name,box in boxes.items():
        crop=day.crop(box);crop.thumbnail((2048,1200),Image.Resampling.LANCZOS);crop.save(SCREENSHOT_DIR/name)


def update_manifest(transition,all_rows,layers,stairs,water_day,water_night,mask_tiles):
    path=OUT/"composition_manifest.csv";rows=p29.pass20.base.read_csv(path)
    rows=[r for r in rows if r.get("key")!="pass_id" and not r.get("key","").startswith("pass30_") and not r.get("key","").startswith("sha256_unified_composition_")]
    rows.extend([
        {"key":"pass_id","value":PASS_ID},
        {"key":"pass30_extension_convergence","value":"true"},
        {"key":"pass30_transition_buildings","value":str(len(transition))},
        {"key":"pass30_extension_buildings_total","value":str(len(all_rows))},
        {"key":"pass30_transition_rule","value":"road_safe_core_edge_streetwall_belt_v1"},
        {"key":"pass30_open_space_policy","value":"preserve_pass29_open_blocks_and_authored_parks"},
        {"key":"pass30_component_scale_policy","value":"fixed_pixel_roof_stair_vocabulary_no_parent_scaling"},
        {"key":"pass30_water_palette_authority","value":"protected_core_sample"},
        {"key":"pass30_water_day_rgb","value":",".join(map(str,water_day))},
        {"key":"pass30_water_night_rgb","value":",".join(map(str,water_night))},
        {"key":"pass30_building_layer_rows","value":str(len(layers))},
        {"key":"pass30_stairwells","value":str(len(stairs))},
        {"key":"pass30_gameplay_mask_tiles","value":str(mask_tiles)},
    ])
    for mode in ("day","night"):
        p=OUT/f"unified_composition_{mode}.png";rows.append({"key":f"sha256_{p.stem}","value":p29.pass20.base.sha256(p)})
    p29.pass20.base.write_csv(path,("key","value"),rows)


def main():
    p29rc2.main()
    roads=road_rows_to_network(read_csv(SEM/p29.EXTENSION_ROADS))
    buildings=read_csv(SEM/p29.EXTENSION_BUILDINGS)
    open_rows=read_csv(SEM/p29.EXTENSION_OPEN_BLOCKS)
    transition=make_transition_candidates(buildings,roads,protected_open_rects(open_rows))
    if len(transition)<56:
        raise RuntimeError(f"Pass 30 transition belt too sparse: only {len(transition)} legal buildings")

    day=Image.open(OUT/"unified_composition_day.png").convert("RGB")
    night=Image.open(OUT/"unified_composition_night.png").convert("RGB")
    solid=Image.open(MASK_DIR/"solid_mask_master.png").convert("L")
    walk=Image.open(MASK_DIR/"walkable_mask_master.png").convert("L")
    cycle=Image.open(MASK_DIR/"cycle_mask_master.png").convert("L")
    collision=Image.open(MASK_DIR/"collision_mask_master.png").convert("L")

    water_day=recolor_extension_water(day,"day");water_night=recolor_extension_water(night,"night")
    add_transition_art_and_masks(day,night,solid,walk,cycle,collision,transition)
    all_rows=buildings+transition
    layers,stairs=extension_layers_and_stairs(all_rows)
    stair_by_building={r["building_id"]:r["side"] for r in stairs}
    # Add richer fixed-size rooftop and exterior-stair vocabulary to every outer
    # building, including the original Pass-29 extension and the new transition belt.
    for row in all_rows:
        decorate_roof(day,row,False,stair_by_building[row["building_id"]])
        decorate_roof(night,row,True,stair_by_building[row["building_id"]])

    day.save(OUT/"unified_composition_day.png");night.save(OUT/"unified_composition_night.png")
    art_tiles=p29.tile_image(day,OUT/"tiles"/"day");p29.tile_image(night,OUT/"tiles"/"night")
    mask_tiles=tile_masks({"solid":solid,"walkable":walk,"cycle":cycle,"collision":collision})

    fields=("building_id","kind","district","x","y","w","h","merged_lot_count","fixed_component_scale","generation_rule")
    # Normalize original rows to the expanded Pass-30 schema.
    normalized=[]
    for row in all_rows:
        normalized.append({k:row.get(k,"") for k in fields})
    write_csv(SEM/p29.EXTENSION_BUILDINGS,fields,normalized)
    write_csv(SEM/TRANSITION_FILE,fields,transition)
    write_csv(SEM/LAYER_FILE,("building_id","level_id","layer_kind","z_order","walkable","visual_role","transition_policy"),layers)
    write_csv(SEM/STAIR_FILE,("stairwell_id","building_id","kind","side","x","y","from_level","intermediate_level","to_level","interaction_keys","transition_mode"),stairs)
    update_manifest(transition,normalized,layers,stairs,water_day,water_night,mask_tiles)
    save_screens(day,night)
    merged=sum(int(float(r.get("merged_lot_count",1) or 1))>=2 for r in normalized)
    print(f"PASS30_EXTENSION_CONVERGENCE transition={len(transition)} extension_total={len(normalized)} merged={merged} layers={len(layers)} stairs={len(stairs)} water_day={water_day} water_night={water_night} art_tiles={art_tiles} mask_tiles={mask_tiles}")


if __name__=="__main__":main()
