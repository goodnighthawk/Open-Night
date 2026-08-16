from __future__ import annotations

"""Pass 26 RC3: dense art-first map, gap-filled crossings, derived solid mask.

The visual master remains authoritative. Secondary urban mass uses the same
building-volume renderer as the primary city art. After artwork is complete,
combined collision, solid-object, walkability and cycle masks are tiled for the
runtime pipeline.
"""

import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))

import build_pass20_streetwall as pass20
import build_pass26_art_first_world as p26
import build_pass26_art_first_world_v2 as rc2

PASS_ID="pass_26_art_first_world_rc3"
_orig_crossings=p26.build_mobility_crossings
_orig_masks=p26.build_gameplay_masks


def rect_overlap(a,b,pad=0.0):
    ax,ay,aw,ah=a;bx,by,bw,bh=b
    return not (ax+aw+pad<=bx or bx+bw+pad<=ax or ay+ah+pad<=by or by+bh+pad<=ay)


def block_world(row):
    return float(row["x"])*2.0,float(row["y"])*2.0+2048.0,float(row["w"])*2.0,float(row["h"])*2.0


def centre_in(rect,outer):
    x,y,w,h=rect;ox,oy,ow,oh=outer
    return ox<=x+w*.5<=ox+ow and oy<=y+h*.5<=oy+oh


def split_strip(rect):
    x,y,w,h=rect
    if w<58 or h<50:return []
    horizontal=w>=h;long=w if horizontal else h
    count=3 if long>=430 else (2 if long>=250 else 1)
    gap=16.0;span=(long-gap*(count-1))/count
    pieces=[]
    for i in range(count):
        if horizontal:
            pw=min(230.0,max(58.0,span));ph=min(165.0,max(50.0,h))
            pieces.append((x+i*(span+gap)+(span-pw)*.5,y+(h-ph)*.5,pw,ph))
        else:
            pw=min(180.0,max(58.0,w));ph=min(220.0,max(50.0,span))
            pieces.append((x+(w-pw)*.5,y+i*(span+gap)+(span-ph)*.5,pw,ph))
    return pieces


def build_infill_v3(roads,rp,buildings):
    p26.infill_rows.clear()
    surfaces=pass20.base.authored_surfaces();water=surfaces.get("water",[]);green=surfaces.get("green",[])
    blocks=pass20.base.read_csv(pass20.base.SEMANTIC/"urban_blocks.csv")
    stairs=pass20.base.read_csv(pass20.base.SEMANTIC/"building_stairwells.csv")
    stair_pts=[(float(r["x"]),float(r["y"])) for r in stairs]
    building_rects=[(float(b["x"]),float(b["y"]),float(b["w"]),float(b["h"])) for b in buildings]
    accepted=[];serial=0
    solid_kinds=("row_annex","shop_row","garage_row")
    open_kinds=("paved_courtyard","service_court","pocket_plaza","parking_strip","alley_link","fenced_yard")

    road_segments=[]
    for road in roads:
        if str(road.get("bridge","false")).lower()=="true":continue
        half,sidewalk,curb=p26.road_metrics(road);radius=half+curb+sidewalk+2
        for a,b in zip(rp[road["road_id"]],rp[road["road_id"]][1:]):road_segments.append((a,b,radius))

    def legal(rect):
        x,y,w,h=rect
        if w<52 or h<46:return False
        for pt in p26.rect_corners(x,y,w,h):
            if any(pass20.base.point_in_polygon(pt,poly) for poly in water):return False
            if any(pass20.base.point_in_polygon(pt,poly) for poly in green):return False
            if any(p26.segdist(pt,a,b)<radius for a,b,radius in road_segments):return False
        if any(rect_overlap(rect,b,8) for b in building_rects):return False
        if any(rect_overlap(rect,a,7) for a in accepted):return False
        if any(x-34<sx<x+w+34 and y-34<sy<y+h+34 for sx,sy in stair_pts):return False
        return True

    def append_rect(rect,district,key,force_open=False):
        nonlocal serial
        if not legal(rect):return False
        x,y,w,h=rect;s=p26.seed(key);area=w*h
        solid=(not force_open and w>=88 and h>=68 and area>=7200 and s%5!=0)
        if solid:
            kind=solid_kinds[(s//5)%len(solid_kinds)];walkable="false";collision="solid"
        else:
            kind=open_kinds[(s//7)%len(open_kinds)];walkable="false" if kind=="fenced_yard" else "true";collision="none"
        serial+=1
        p26.infill_rows.append({"id":f"infill26_{serial:04d}","kind":kind,"district":district,
            "x":round(x,2),"y":round(y,2),"w":round(w,2),"h":round(h,2),
            "walkable":walkable,"collision_class":collision,
            "placement_rule":"road_bounded_block_art_generation_pass26_rc3"})
        accepted.append(rect);return True

    for block_index,block in enumerate(blocks):
        bx,by,bw,bh=block_world(block)
        if bw<125 or bh<115:continue
        if bx<pass20.base.HUDSON_EAST_X and bx+bw>pass20.base.HUDSON_WEST_X:continue
        district="fort_lee" if bx+bw<=pass20.base.HUDSON_WEST_X else "washington_heights"
        inset=18.0;ix,iy,iw,ih=bx+inset,by+inset,max(0,bw-2*inset),max(0,bh-2*inset)
        if iw<70 or ih<64:continue
        inside=[r for r in building_rects if centre_in(r,(bx,by,bw,bh))]
        if inside:
            ux=min(r[0] for r in inside);uy=min(r[1] for r in inside);ux1=max(r[0]+r[2] for r in inside);uy1=max(r[1]+r[3] for r in inside)
            gap=16.0
            strips=[(ix,iy,iw,max(0,uy-iy-gap)),(ix,uy1+gap,iw,max(0,iy+ih-(uy1+gap))),
                    (ix,max(iy,uy),max(0,ux-ix-gap),max(0,min(iy+ih,uy1)-max(iy,uy))),
                    (ux1+gap,max(iy,uy),max(0,ix+iw-(ux1+gap)),max(0,min(iy+ih,uy1)-max(iy,uy)))]
        else:
            strips=[(ix,iy,iw,ih)]
        pieces=[]
        for slot,strip in enumerate(strips):pieces.extend((slot,p) for p in split_strip(strip))
        pieces.sort(key=lambda it:it[1][2]*it[1][3],reverse=True)
        placed=0
        for piece_idx,(slot,rect) in enumerate(pieces):
            if placed>=3:break
            if append_rect(rect,district,f"block:{block.get('block_id',block_index)}:{slot}:{piece_idx}"):placed+=1

    # Smaller gaps are converted to courts/alleys only after all block strips have
    # had first priority. This prevents a noisy scatter and provides a hard floor
    # on purposeful urban coverage.
    if len(p26.infill_rows)<75:
        for district,xmin,xmax,ymin,ymax in (("fort_lee",240,4700,2220,10060),("washington_heights",10620,16140,2220,10060)):
            for gx,x in enumerate(range(xmin,xmax+1,185)):
                for gy,y in enumerate(range(ymin,ymax+1,180)):
                    if len(p26.infill_rows)>=90:break
                    s=p26.seed(f"micro:{district}:{gx}:{gy}");w=70+(s%65);h=58+((s//71)%55)
                    append_rect((x-w*.5,y-h*.5,w,h),district,f"micro:{district}:{gx}:{gy}",force_open=True)
                if len(p26.infill_rows)>=90:break
            if len(p26.infill_rows)>=90:break

    # If enough legal large courts were found but deterministic classification
    # happened to leave too few roof masses, convert the largest suitable open
    # uses to secondary structures. Geometry stays identical; only art/use class
    # changes.
    solid_count=sum(r["collision_class"]=="solid" for r in p26.infill_rows)
    if solid_count<30:
        candidates=sorted((r for r in p26.infill_rows if r["collision_class"]!="solid" and float(r["w"])>=88 and float(r["h"])>=68),
                          key=lambda r:float(r["w"])*float(r["h"]),reverse=True)
        for r in candidates:
            if solid_count>=30:break
            s=p26.seed("promote:"+r["id"]);r["kind"]=solid_kinds[s%len(solid_kinds)];r["collision_class"]="solid";r["walkable"]="false";solid_count+=1

    pass20.base.write_csv(pass20.base.SEMANTIC/p26.INFILL_CSV,
        ("id","kind","district","x","y","w","h","walkable","collision_class","placement_rule"),p26.infill_rows)
    return len(p26.infill_rows)


def path_length_and_positions(points,rows):
    segments=[];total=0.0
    for a,b in zip(points,points[1:]):
        length=math.hypot(b[0]-a[0],b[1]-a[1]);segments.append((a,b,total,length));total+=length
    positions=[]
    for row in rows:
        p=(float(row["x"]),float(row["y"]));best=None
        for a,b,start,length in segments:
            dx=b[0]-a[0];dy=b[1]-a[1];den=dx*dx+dy*dy
            t=0 if den<=1e-9 else max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den))
            q=(a[0]+t*dx,a[1]+t*dy);dist=math.hypot(p[0]-q[0],p[1]-q[1])
            if best is None or dist<best[0]:best=(dist,start+t*length)
        if best and best[0]<110:positions.append(best[1])
    return total,sorted(positions)


def point_at(points,distance):
    walked=0.0
    for a,b in zip(points,points[1:]):
        dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
        if distance<=walked+length or b==points[-1]:
            t=0 if length<=1e-9 else max(0,min(1,(distance-walked)/length))
            return a[0]+dx*t,a[1]+dy*t,(dx/length if length else 1.0),(dy/length if length else 0.0)
        walked+=length
    a,b=points[-2:];length=math.hypot(b[0]-a[0],b[1]-a[1]);return b[0],b[1],(b[0]-a[0])/length,(b[1]-a[1])/length


def build_crossings_v3(roads,rp,base_crossings):
    _orig_crossings(roads,rp,base_crossings)
    thresholds={"primary":680.0,"secondary":740.0,"tertiary":860.0}
    by_road=defaultdict(list)
    for r in base_crossings+p26.mobility_rows:
        if r.get("road_id"):by_road[r["road_id"]].append(r)
    serial=len(p26.mobility_rows)
    for road in roads:
        cls=road.get("highway","residential")
        if cls not in thresholds or str(road.get("bridge","false")).lower()=="true":continue
        rid=road["road_id"];points=rp[rid]
        while True:
            total,pos=path_length_and_positions(points,by_road[rid]);check=[0.0]+pos+[total]
            gaps=[(b-a,a,b) for a,b in zip(check,check[1:])]
            gap,a,b=max(gaps,default=(0,0,0))
            if gap<=thresholds[cls]:break
            target=(a+b)*.5;x,y,ux,uy=point_at(points,target)
            if pass20.base.HUDSON_WEST_X-100 < x < pass20.base.HUDSON_EAST_X+100:break
            half,sidewalk,curb=p26.road_metrics(road);serial+=1
            row={"id":f"cross26_{serial:04d}","road_id":rid,"x":round(x,2),"y":round(y,2),
                 "angle":round(math.degrees(math.atan2(uy,ux)),2),"length":round(2*(half+curb+4),2),"width":"26",
                 "mode":"shared_ped_cycle","road_class":cls,"source":"major_road_gap_fill_pass26_rc3","clearance_status":"pass"}
            p26.mobility_rows.append(row);by_road[rid].append(row)
    pass20.base.write_csv(pass20.base.SEMANTIC/p26.CROSSING_CSV,
        ("id","road_id","x","y","angle","length","width","mode","road_class","source","clearance_status"),p26.mobility_rows)
    return p26.mobility_rows


def draw_infill_v3(path:Path,night:bool):
    # Open/service uses retain RC2's designed surfaces. Solid uses are redrawn
    # through the main renderer's building-volume vocabulary for consistent art.
    open_rows=[r for r in p26.infill_rows if r["collision_class"]!="solid"]
    solid_rows=[r for r in p26.infill_rows if r["collision_class"]=="solid"]
    saved=p26.infill_rows
    p26.infill_rows=open_rows
    rc2.draw_infill_v2(path,night)
    p26.infill_rows=saved
    im=Image.open(path).convert("RGB")
    callback=pass20.base.callback;old_scale=callback.VIEW_SCALE;callback.VIEW_SCALE=.5
    d=ImageDraw.Draw(im)
    P=callback.NIGHT if night else callback.DAY
    fort=("bui_painted_walkup_04","bui_stone_midrise_15","bui_commercial_lowrise_18","bui_warehouse_20")
    wh=("bui_brick_midrise_01","bui_brownstone_row_14","bui_commercial_corner_17","bui_art_deco_22")
    for row in solid_rows:
        s=p26.seed(row["id"]);families=fort if row["district"]=="fort_lee" else wh
        if row["kind"]=="garage_row":aid="bui_warehouse_20"
        elif row["kind"]=="shop_row":aid="bui_commercial_lowrise_18" if row["district"]=="fort_lee" else "bui_commercial_corner_17"
        else:aid=families[s%len(families)]
        parent={"id":row["id"],"x":row["x"],"y":row["y"],"w":row["w"],"h":row["h"],"archetype_id":aid}
        mass=dict(parent,massing_id="secondary_"+row["id"],height_scale=.34+(s%5)*.045)
        callback.draw_building_volume(im,d,parent,mass,{"archetype_id":aid},8192,6144,8192,4096,P,night)
    callback.VIEW_SCALE=old_scale
    im.save(path)


def build_masks_v3(roads,rp,buildings):
    rows=_orig_masks(roads,rp,buildings)
    collision=Image.open(p26.MASK_DIR/"collision_mask_master.png").convert("L")
    water=Image.new("L",collision.size,0);wd=ImageDraw.Draw(water)
    for poly in pass20.base.authored_surfaces().get("water",[]):wd.polygon(p26.world_poly_to_master(poly),fill=255)
    solid=ImageChops.subtract(collision,water);solid.save(p26.MASK_DIR/"solid_mask_master.png")
    folder=p26.MASK_DIR/"solid_tiles";folder.mkdir(parents=True,exist_ok=True)
    rows=[r for r in rows if r.get("layer")!="solid"]
    for rr in range(pass20.base.MASTER_H//pass20.base.TILE_SIZE):
        for cc in range(pass20.base.MASTER_W//pass20.base.TILE_SIZE):
            tile=solid.crop((cc*pass20.base.TILE_SIZE,rr*pass20.base.TILE_SIZE,(cc+1)*pass20.base.TILE_SIZE,(rr+1)*pass20.base.TILE_SIZE))
            name=f"solid_{cc:02d}_{rr:02d}.png";path=folder/name;tile.save(path,optimize=True)
            rows.append({"layer":"solid","col":cc,"row":rr,"filename":str(path.relative_to(pass20.base.OUT)).replace("\\","/"),"sha256":pass20.base.sha256(path)})
    pass20.base.write_csv(pass20.base.SEMANTIC/p26.MASK_MANIFEST_CSV,("layer","col","row","filename","sha256"),rows)
    return rows


def main():
    p26.PASS_ID=PASS_ID
    p26.build_infill=build_infill_v3
    p26.build_mobility_crossings=build_crossings_v3
    p26.draw_infill=draw_infill_v3
    p26.build_gameplay_masks=build_masks_v3
    p26.main()
    counts=Counter(r["kind"] for r in p26.infill_rows)
    print(f"PASS26_RC3_DENSITY solid={sum(r['collision_class']=='solid' for r in p26.infill_rows)} open={sum(r['collision_class']!='solid' for r in p26.infill_rows)} kinds={dict(sorted(counts.items()))}")


if __name__=="__main__":main()
