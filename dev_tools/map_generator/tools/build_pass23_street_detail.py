from __future__ import annotations

"""Pass 23: deterministic street/sidewalk detail density.

Builds on accepted Pass 22b massing. Details are cosmetic-only and placed from the
final road geometry with explicit keep-outs around crossings, stair access and
building entrances. No traffic, collision, road, bridge, water or building geometry
is changed.
"""

import hashlib
import math
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass20_streetwall as pass20
import build_pass22b_massing_convergence as pass22b

PASS_ID = "pass_23_street_detail_density_rc1"
DETAIL_CSV = "street_detail_pass23.csv"
detail_rows: list[dict[str, object]] = []


def stable_seed(text: str) -> int:
    return int(hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:12], 16)


def segment_distance(p, a, b):
    dx=b[0]-a[0];dy=b[1]-a[1];den=dx*dx+dy*dy
    if den<=1e-9:return math.hypot(p[0]-a[0],p[1]-a[1])
    t=max(0.0,min(1.0,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den))
    q=(a[0]+t*dx,a[1]+t*dy)
    return math.hypot(p[0]-q[0],p[1]-q[1])


def road_metrics(road):
    lanes=max(1,int(float(road.get("lanes",1))))
    half=max(38.0,lanes*38.0+10.0)*pass20.base.ROAD_WIDTH_SCALE*.5
    sidewalk=max(28.0,float(road.get("sidewalk_width",28)))*pass20.base.SIDEWALK_SCALE
    curb=max(4.0,float(road.get("curb_width",4)))
    return half,sidewalk,curb


def add(kind,x,y,road_id,district,side,rule,size=1.0,rotation=0.0):
    detail_rows.append({
        "id":f"street_detail_{len(detail_rows)+1:05d}","kind":kind,
        "x":round(x,2),"y":round(y,2),"road_id":road_id,"district":district,
        "side":side,"size":round(size,2),"rotation":round(rotation,2),
        "placement_rule":rule,
    })


def build_details(roads,rp,crossings,buildings,stairs):
    detail_rows.clear()
    crossing_points=[(float(c["x"]),float(c["y"])) for c in crossings]
    stair_points=[(float(s["x"]),float(s["y"])) for s in stairs]
    entrance_points=[]
    entrance_path=pass20.base.SEMANTIC/"building_entrances.csv"
    if entrance_path.exists():
        for row in pass20.base.read_csv(entrance_path):
            try: entrance_points.append((float(row["x"]),float(row["y"])))
            except (KeyError,ValueError): pass
    building_boxes=[(float(b["x"])-8,float(b["y"])-8,float(b["x"])+float(b["w"])+8,float(b["y"])+float(b["h"])+8) for b in buildings]
    surfaces=pass20.base.authored_surfaces();water=surfaces.get("water",[])

    all_segments=[]
    for r in roads:
        if str(r.get("bridge","false")).lower()=="true":continue
        half,sidewalk,curb=road_metrics(r)
        for a,b in zip(rp[r["road_id"]],rp[r["road_id"]][1:]):
            all_segments.append((a,b,half,sidewalk,curb,r["road_id"]))

    def legal_point(p, road, *, sidewalk_object=True, road_margin=2.0):
        x,y=p
        if any(pass20.base.point_in_polygon(p,poly) for poly in water):return False
        if any(x0<x<x1 and y0<y<y1 for x0,y0,x1,y1 in building_boxes):return False
        if any(math.hypot(x-cx,y-cy)<130 for cx,cy in crossing_points):return False
        if any(math.hypot(x-sx,y-sy)<68 for sx,sy in stair_points):return False
        if any(math.hypot(x-ex,y-ey)<58 for ex,ey in entrance_points):return False
        # An object may only occupy the sidewalk/verge of its source road, never asphalt.
        # road_margin is the full visible footprint allowance, not just the center point.
        source_half,source_sidewalk,source_curb=road_metrics(road)
        source_segments=list(zip(rp[road["road_id"]],rp[road["road_id"]][1:]))
        d=min(segment_distance(p,a,b) for a,b in source_segments)
        if sidewalk_object and not (source_half+source_curb+road_margin <= d <= source_half+source_curb+source_sidewalk-4):return False
        # Also reject accidental overlap with any other road ribbon using the same full-footprint margin.
        for a,b,half,_,curb,rid in all_segments:
            if segment_distance(p,a,b)<half+curb+road_margin:return False
        return True

    furniture=("hydrant","streetlamp","trash_bin","bench","mailbox","bike_rack","bollard")
    surface_marks=("utility_cover","sidewalk_repair","curb_patch","tree_pit")
    street_marks=("manhole","asphalt_patch","drain")

    for road_index,road in enumerate(roads):
        if str(road.get("bridge","false")).lower()=="true":continue
        rid=road["road_id"];half,sidewalk,curb=road_metrics(road)
        district="fort_lee" if max(x for x,_ in rp[rid])<=pass20.base.HUDSON_WEST_X else "washington_heights"
        spacing=440.0 if district=="washington_heights" else 560.0
        for segment_index,(a,b) in enumerate(zip(rp[rid],rp[rid][1:])):
            dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
            if length<240:continue
            ux,uy=dx/length,dy/length;nx,ny=-uy,ux
            count=max(1,int(length/spacing))
            for sample in range(count):
                t=(sample+1)/(count+1)
                base_x=a[0]+dx*t;base_y=a[1]+dy*t
                seed=stable_seed(f"{rid}:{segment_index}:{sample}")
                side=1 if seed%2==0 else -1
                side_name="left" if side>0 else "right"
                sidewalk_offset=half+curb+sidewalk*.58
                px=base_x+nx*side*sidewalk_offset;py=base_y+ny*side*sidewalk_offset
                if legal_point((px,py),road):
                    kind=furniture[(seed//7)%len(furniture)]
                    add(kind,px,py,rid,district,side_name,"final_sidewalk_furniture_pass23_v1",.82+(seed%5)*.06,math.degrees(math.atan2(dy,dx)))
                    # Adjacent subtle surface detail makes the sidewalk look used without cluttering movement.
                    along=((seed//17)%61-30)
                    skind=surface_marks[(seed//31)%len(surface_marks)]
                    if skind=="tree_pit":
                        # Tree bases have a visible radius of about 10-12 world px. Put the
                        # complete base inside the sidewalk/verge instead of validating only
                        # its center, which previously allowed the green circle to clip asphalt.
                        tree_margin=14.0
                        usable=max(tree_margin+4.0,sidewalk-tree_margin)
                        tree_sidewalk_offset=half+curb+min(sidewalk*.76,usable)
                        sx=base_x+nx*side*tree_sidewalk_offset+ux*along
                        sy=base_y+ny*side*tree_sidewalk_offset+uy*along
                        if legal_point((sx,sy),road,road_margin=tree_margin):
                            add(skind,sx,sy,rid,district,side_name,"tree_base_full_footprint_keepout_pass23_v2",.8+(seed%4)*.07,math.degrees(math.atan2(dy,dx)))
                    else:
                        sx=px+ux*along;sy=py+uy*along
                        if legal_point((sx,sy),road):
                            add(skind,sx,sy,rid,district,side_name,"sidewalk_surface_detail_pass23_v1",.8+(seed%4)*.07,math.degrees(math.atan2(dy,dx)))

                # Sparse road-surface wear, safely inside the carriageway and away from crossings.
                if (seed//13)%3==0:
                    lateral=((seed//23)%41-20)*.35
                    rx=base_x+nx*lateral;ry=base_y+ny*lateral
                    if not any(math.hypot(rx-cx,ry-cy)<150 for cx,cy in crossing_points):
                        rkind=street_marks[(seed//43)%len(street_marks)]
                        add(rkind,rx,ry,rid,district,"road","road_surface_detail_pass23_v1",.8+(seed%4)*.08,math.degrees(math.atan2(dy,dx)))

    pass20.base.write_csv(pass20.base.SEMANTIC/DETAIL_CSV,
        ("id","kind","x","y","road_id","district","side","size","rotation","placement_rule"),detail_rows)
    return Counter(r["kind"] for r in detail_rows)


def world_point(x,y):
    mx,my=pass20.base.world_to_master(float(x),float(y));return int(round(mx)),int(round(my))


def draw_details(path:Path,night:bool):
    im=Image.open(path).convert("RGBA");overlay=Image.new("RGBA",im.size,(0,0,0,0));d=ImageDraw.Draw(overlay,"RGBA")
    if night:
        pavement=(92,94,88,125);dark=(31,35,34,220);metal=(98,106,101,235);warm=(125,75,48,235);green=(52,76,51,225);paper=(111,104,84,150)
    else:
        pavement=(143,139,127,120);dark=(57,61,58,225);metal=(127,133,126,235);warm=(167,83,48,235);green=(69,103,64,225);paper=(168,154,119,155)
    for row in detail_rows:
        x,y=world_point(row["x"],row["y"]);kind=row["kind"];s=max(.6,float(row.get("size",1) or 1))
        r=max(1,int(3*s))
        if kind=="hydrant":
            d.ellipse((x-r,y-r,x+r,y+r),fill=warm,outline=dark)
        elif kind=="streetlamp":
            d.ellipse((x-r,y-r,x+r,y+r),fill=metal,outline=dark);d.point((x,y),fill=(220,192,112,240) if night else metal)
        elif kind in {"trash_bin","mailbox"}:
            rr=max(2,int(4*s));d.rectangle((x-rr,y-rr,x+rr,y+rr),fill=green if kind=="trash_bin" else metal,outline=dark,width=1)
        elif kind=="bench":
            rr=max(3,int(6*s));d.rectangle((x-rr,y-2,x+rr,y+2),fill=warm,outline=dark,width=1)
        elif kind=="bike_rack":
            rr=max(3,int(5*s));d.arc((x-rr,y-rr,x+rr,y+rr),180,360,fill=metal,width=1)
        elif kind=="bollard":
            d.ellipse((x-r,y-r,x+r,y+r),fill=dark,outline=metal)
        elif kind in {"utility_cover","tree_pit"}:
            rr=max(3,int(5*s));d.ellipse((x-rr,y-rr,x+rr,y+rr),fill=dark if kind=="utility_cover" else green,outline=metal,width=1)
        elif kind in {"sidewalk_repair","curb_patch"}:
            rr=max(4,int(7*s));d.rectangle((x-rr,y-r,x+rr,y+r),fill=pavement,outline=dark,width=1)
        elif kind=="manhole":
            rr=max(3,int(6*s));d.ellipse((x-rr,y-rr,x+rr,y+rr),fill=dark,outline=metal,width=1);d.line((x-rr+2,y,x+rr-2,y),fill=metal,width=1)
        elif kind=="asphalt_patch":
            rr=max(5,int(10*s));d.rectangle((x-rr,y-r,x+rr,y+r),fill=(dark[0],dark[1],dark[2],95),outline=(dark[0],dark[1],dark[2],130),width=1)
        elif kind=="drain":
            rr=max(3,int(6*s));d.rectangle((x-rr,y-2,x+rr,y+2),fill=dark)
            for xx in range(x-rr+2,x+rr,3):d.line((xx,y-2,xx,y+2),fill=metal,width=1)
    Image.alpha_composite(im,overlay).convert("RGB").save(path)


def update_manifest(masters,counts):
    path=pass20.base.OUT/"composition_manifest.csv";rows=pass20.base.read_csv(path)
    remove={"pass_id","street_detail_density_pass","street_detail_rows","street_detail_kinds","street_detail_rule"}
    rows=[r for r in rows if r.get("key") not in remove and not r.get("key","").startswith("sha256_unified_composition_")]
    rows.extend([
        {"key":"pass_id","value":PASS_ID},
        {"key":"street_detail_density_pass","value":"true"},
        {"key":"street_detail_rows","value":str(len(detail_rows))},
        {"key":"street_detail_kinds","value":str(len(counts))},
        {"key":"street_detail_rule","value":"final_geometry_keepout_pass23_v2_full_tree_base"},
    ])
    for master in masters:rows.append({"key":f"sha256_{master.stem}","value":pass20.base.sha256(master)})
    pass20.base.write_csv(path,("key","value"),rows)


def main():
    if DETAIL_CSV not in pass20.base.SEMANTIC_FILES:
        pass20.base.SEMANTIC_FILES=tuple(pass20.base.SEMANTIC_FILES)+(DETAIL_CSV,)
    pass22b.PASS_ID=PASS_ID
    pass22b.main()
    roads,rp,crossings=pass20.base.authored_block_network()
    buildings=pass20.base.read_csv(pass20.base.SEMANTIC/"iterated_buildings.csv")
    stairs=pass20.base.read_csv(pass20.base.SEMANTIC/"building_stairwells.csv")
    counts=build_details(roads,rp,crossings,buildings,stairs)
    masters=[pass20.base.OUT/"unified_composition_day.png",pass20.base.OUT/"unified_composition_night.png"]
    draw_details(masters[0],False);draw_details(masters[1],True)
    pass20.base.tile_masters(masters);update_manifest(masters,counts)
    print(f"PASS23_STREET_DETAIL rows={len(detail_rows)} kinds={dict(sorted(counts.items()))}")


if __name__=="__main__":main()
