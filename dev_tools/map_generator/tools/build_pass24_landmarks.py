from __future__ import annotations

"""Pass 24: hand-authored landmarks on top of the accepted Pass 23 map.

The world topology stays frozen.  This pass adds memorable, deterministic visual
identity at the GWB approaches/towers and at selected Fort Lee / Washington
Heights buildings, including all three church landmarks.  Building landmark art
stays inside its parent footprint; bridge landmark art is constrained to the GWB
corridor and is cosmetic only.
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass20_streetwall as pass20
import build_pass23_street_detail as pass23

PASS_ID = "pass_24_hand_authored_landmarks_rc1"
LANDMARK_CSV = "landmarks_pass24.csv"
landmark_rows: list[dict[str, object]] = []


def centre(building):
    return (
        float(building["x"]) + float(building["w"]) * .5,
        float(building["y"]) + float(building["h"]) * .5,
    )


def nearest_building(buildings, target, district, used, *, exclude_church=True):
    candidates=[]
    for b in buildings:
        if b.get("district") != district or b["id"] in used:
            continue
        if exclude_church and b.get("building_kind") == "church_landmark":
            continue
        cx,cy=centre(b)
        candidates.append((math.hypot(cx-target[0],cy-target[1]),b))
    if not candidates:
        raise RuntimeError(f"No landmark candidate for {district} near {target}")
    return min(candidates,key=lambda item:item[0])[1]


def add_landmark(landmark_id, kind, subject_id, district, x, y, w, h, visual_role, rule):
    landmark_rows.append({
        "landmark_id":landmark_id,
        "kind":kind,
        "subject_id":subject_id,
        "district":district,
        "x":round(x,2),"y":round(y,2),"w":round(w,2),"h":round(h,2),
        "visual_role":visual_role,
        "placement_rule":rule,
    })


def select_landmarks(buildings):
    landmark_rows.clear();used=set()

    # Four bridge landmarks: both approaches plus two tower/support zones.
    bridge_specs=(
        ("gwb_west_portal","bridge_portal",4450,5900,420,488,"gwb_west_gateway"),
        ("gwb_west_tower","bridge_tower",6336,5750,360,788,"gwb_west_tower_support"),
        ("gwb_east_tower","bridge_tower",8896,5750,360,788,"gwb_east_tower_support"),
        ("gwb_east_portal","bridge_portal",10560,5900,420,488,"gwb_east_gateway"),
    )
    for lid,kind,x,y,w,h,role in bridge_specs:
        add_landmark(lid,kind,"gwb_authored","bridge",x,y,w,h,role,"hand_authored_gwb_corridor_pass24_v1")

    # Fort Lee: main commercial approach, bluff transition and a distinctive row.
    fl_specs=(
        ("fort_lee_main_corner",(2304,6144),"commercial_corner","fort_lee_gwb_commercial_corner"),
        ("fort_lee_bluff_complex",(4200,7300),"bluff_complex","fort_lee_bluff_transition"),
        ("fort_lee_residential_row",(1500,8200),"residential_row","fort_lee_distinctive_residential_row"),
    )
    for lid,target,kind,role in fl_specs:
        b=nearest_building(buildings,target,"fort_lee",used)
        used.add(b["id"])
        add_landmark(lid,kind,b["id"],"fort_lee",float(b["x"]),float(b["y"]),float(b["w"]),float(b["h"]),role,"selected_nearest_final_building_pass24_v1")

    # Washington Heights: Broadway/181st, GWB/Broadway and 168th/Amsterdam.
    wh_specs=(
        ("wh_broadway_181_corner",(12160,4672),"commercial_corner","washington_heights_broadway_181_corner"),
        ("wh_gwb_broadway_corner",(12288,6144),"dense_corner","washington_heights_gwb_broadway_corner"),
        ("wh_168th_roof_row",(13888,7680),"residential_row","washington_heights_168th_roof_row"),
    )
    for lid,target,kind,role in wh_specs:
        b=nearest_building(buildings,target,"washington_heights",used)
        used.add(b["id"])
        add_landmark(lid,kind,b["id"],"washington_heights",float(b["x"]),float(b["y"]),float(b["w"]),float(b["h"]),role,"selected_nearest_final_building_pass24_v1")

    # All three church/parish buildings get explicitly different landmark treatment.
    churches=sorted((b for b in buildings if b.get("building_kind")=="church_landmark"),key=lambda b:b["id"])
    church_roles=("old_parish_church","stone_steeple_church","courtyard_basilica")
    for index,b in enumerate(churches):
        used.add(b["id"])
        add_landmark(f"church_landmark_{index+1:02d}","church",b["id"],b.get("district","washington_heights"),
                     float(b["x"]),float(b["y"]),float(b["w"]),float(b["h"]),church_roles[index%len(church_roles)],
                     "explicit_church_landmark_pass24_v1")

    pass20.base.write_csv(
        pass20.base.SEMANTIC/LANDMARK_CSV,
        ("landmark_id","kind","subject_id","district","x","y","w","h","visual_role","placement_rule"),
        landmark_rows,
    )
    return used


def mpoint(x,y):
    a,b=pass20.base.world_to_master(float(x),float(y));return int(round(a)),int(round(b))


def mrect(row,inset=0.0):
    x=float(row["x"])+inset;y=float(row["y"])+inset
    w=max(2.0,float(row["w"])-2*inset);h=max(2.0,float(row["h"])-2*inset)
    x0,y0=mpoint(x,y);x1,y1=mpoint(x+w,y+h)
    return x0,y0,x1,y1


def draw_bridge_landmark(d,row,night):
    x0,y0,x1,y1=mrect(row)
    edge=(126,130,128,245) if night else (172,176,171,245)
    dark=(29,34,35,235) if night else (66,72,71,235)
    light=(223,180,87,245) if night else (210,194,139,220)
    if row["kind"]=="bridge_tower":
        cx=(x0+x1)//2
        # Twin side towers sit off the traffic strip and visually frame the deck.
        tower_w=max(7,(x1-x0)//5)
        for tx in (x0+tower_w,cx+tower_w//2):
            d.rectangle((tx-tower_w//2,y0+4,tx+tower_w//2,y1-4),fill=dark,outline=edge,width=2)
            d.rectangle((tx-tower_w//2-2,y0+12,tx+tower_w//2+2,y0+24),fill=edge)
            d.rectangle((tx-tower_w//2-2,y1-24,tx+tower_w//2+2,y1-12),fill=edge)
        d.line((x0+3,(y0+y1)//2,x1-3,(y0+y1)//2),fill=edge,width=2)
        for yy in range(y0+16,y1-10,18):
            d.ellipse((x0+3,yy-2,x0+7,yy+2),fill=light)
            d.ellipse((x1-7,yy-2,x1-3,yy+2),fill=light)
    else:
        # Anchor/portal massing remains at the side of the roadway, with a clear center.
        mid=(y0+y1)//2;gap=max(10,(y1-y0)//5)
        d.rectangle((x0+4,y0+6,x1-4,mid-gap),fill=dark,outline=edge,width=2)
        d.rectangle((x0+4,mid+gap,x1-4,y1-6),fill=dark,outline=edge,width=2)
        for xx in range(x0+12,x1-8,18):
            d.ellipse((xx-2,y0+3,xx+2,y0+7),fill=light)
            d.ellipse((xx-2,y1-7,xx+2,y1-3),fill=light)


def draw_building_landmark(d,row,night):
    x0,y0,x1,y1=mrect(row,inset=12.0)
    dark=(31,34,33,230) if night else (67,70,65,225)
    edge=(142,136,119,240) if night else (183,173,144,240)
    warm=(132,83,48,230) if night else (175,111,60,230)
    glass=(53,80,88,220) if night else (88,129,138,210)
    role=row["visual_role"]
    w=max(1,x1-x0);h=max(1,y1-y0);cx=(x0+x1)//2;cy=(y0+y1)//2

    if "commercial_corner" in role:
        # Strong corner canopy/storefront band and roof sign.
        d.rectangle((x0+4,y1-10,x1-4,y1-4),fill=glass,outline=edge,width=1)
        d.rectangle((x0+6,y0+5,min(x1-6,x0+w//2),y0+11),fill=warm)
        d.rectangle((cx-12,y0+6,cx+12,y0+14),fill=dark,outline=edge,width=1)
    elif "bluff_transition" in role:
        # Terraced roof plates emphasize the bluff/waterfront transition.
        for i in range(3):
            inset=4+i*5
            d.rectangle((x0+inset,y0+inset,x1-inset,y1-inset),outline=edge,width=1)
        d.rectangle((cx-10,cy-7,cx+10,cy+7),fill=dark,outline=edge,width=1)
    elif "residential" in role or "roof_row" in role:
        # Repeated but fixed-size rooftop cues create a recognizable row.
        for i in range(3):
            px=x0+8+i*max(12,w//4)
            d.rectangle((px,y0+7,px+9,y0+14),fill=dark,outline=edge,width=1)
        d.line((x0+5,y1-7,x1-5,y1-7),fill=edge,width=2)
    elif "gwb_broadway_corner" in role:
        d.rectangle((x0+4,y0+4,x1-4,y0+11),fill=warm)
        d.rectangle((x1-13,y0+5,x1-6,y1-5),fill=glass)
        d.rectangle((cx-8,cy-8,cx+8,cy+8),outline=edge,width=2)
    elif role=="old_parish_church":
        d.line((cx,y0+4,cx,y1-5),fill=edge,width=3)
        d.polygon(((cx,y0+2),(cx+8,y0+14),(cx-8,y0+14)),fill=warm,outline=edge)
        d.line((cx,y0-2,cx,y0+6),fill=edge,width=1)
        d.line((cx-3,y0+1,cx+3,y0+1),fill=edge,width=1)
    elif role=="stone_steeple_church":
        r=max(8,min(w,h)//6)
        d.polygon(((cx,cy-r),(cx+r,cy),(cx,cy+r),(cx-r,cy)),fill=warm,outline=edge)
        d.rectangle((cx-3,cy-r-8,cx+3,cy-r+1),fill=edge)
    elif role=="courtyard_basilica":
        d.rectangle((x0+6,y0+6,x1-6,y1-6),outline=edge,width=2)
        cw=max(8,w//4);ch=max(8,h//4)
        d.rectangle((cx-cw//2,cy-ch//2,cx+cw//2,cy+ch//2),fill=(20,22,21,85),outline=edge,width=1)
        d.line((x0+8,cy,x1-8,cy),fill=warm,width=2)
    else:
        d.rectangle((x0+5,y0+5,x1-5,y1-5),outline=edge,width=2)


def draw_landmarks(path:Path,night:bool):
    im=Image.open(path).convert("RGBA")
    overlay=Image.new("RGBA",im.size,(0,0,0,0));d=ImageDraw.Draw(overlay,"RGBA")
    for row in landmark_rows:
        if row["district"]=="bridge":draw_bridge_landmark(d,row,night)
        else:draw_building_landmark(d,row,night)
    Image.alpha_composite(im,overlay).convert("RGB").save(path)


def update_manifest(masters):
    path=pass20.base.OUT/"composition_manifest.csv";rows=pass20.base.read_csv(path)
    remove={"pass_id","hand_authored_landmark_pass","landmark_count","bridge_landmark_count","church_landmark_count","building_landmark_count"}
    rows=[r for r in rows if r.get("key") not in remove and not r.get("key","").startswith("sha256_unified_composition_")]
    rows.extend([
        {"key":"pass_id","value":PASS_ID},
        {"key":"hand_authored_landmark_pass","value":"true"},
        {"key":"landmark_count","value":str(len(landmark_rows))},
        {"key":"bridge_landmark_count","value":str(sum(r["district"]=="bridge" for r in landmark_rows))},
        {"key":"church_landmark_count","value":str(sum(r["kind"]=="church" for r in landmark_rows))},
        {"key":"building_landmark_count","value":str(sum(r["district"]!="bridge" for r in landmark_rows))},
    ])
    for master in masters:rows.append({"key":f"sha256_{master.stem}","value":pass20.base.sha256(master)})
    pass20.base.write_csv(path,("key","value"),rows)


def main():
    if LANDMARK_CSV not in pass20.base.SEMANTIC_FILES:
        pass20.base.SEMANTIC_FILES=tuple(pass20.base.SEMANTIC_FILES)+(LANDMARK_CSV,)
    pass23.PASS_ID=PASS_ID
    pass23.main()
    buildings=pass20.base.read_csv(pass20.base.SEMANTIC/"iterated_buildings.csv")
    select_landmarks(buildings)
    masters=[pass20.base.OUT/"unified_composition_day.png",pass20.base.OUT/"unified_composition_night.png"]
    draw_landmarks(masters[0],False);draw_landmarks(masters[1],True)
    pass20.base.tile_masters(masters);update_manifest(masters)
    print(f"PASS24_LANDMARKS total={len(landmark_rows)} bridge={sum(r['district']=='bridge' for r in landmark_rows)} churches={sum(r['kind']=='church' for r in landmark_rows)}")


if __name__=="__main__":main()
