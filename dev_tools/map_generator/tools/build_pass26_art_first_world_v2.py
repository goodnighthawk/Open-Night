from __future__ import annotations

"""Pass 26 RC2: block-aware art-first density correction.

RC1 proved the art->mask->tile architecture but sampled only completely empty
urban cells. RC2 targets the actual visual problem: unused strips inside the
road-bounded urban blocks around the primary detailed building art. Fixed-size
annexes, shop rows, garages, courts, alleys and small plazas fill those strips.
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))

import build_pass20_streetwall as pass20
import build_pass26_art_first_world as p26

PASS_ID="pass_26_art_first_world_rc2"


def rect_overlap(a,b,pad=0.0):
    ax,ay,aw,ah=a;bx,by,bw,bh=b
    return not (ax+aw+pad<=bx or bx+bw+pad<=ax or ay+ah+pad<=by or by+bh+pad<=ay)


def block_world(row):
    return float(row["x"])*2.0,float(row["y"])*2.0+2048.0,float(row["w"])*2.0,float(row["h"])*2.0


def centre_in(rect,outer):
    x,y,w,h=rect;ox,oy,ow,oh=outer
    cx=x+w*.5;cy=y+h*.5
    return ox<=cx<=ox+ow and oy<=cy<=oy+oh


def split_strip(rect,block_id,slot):
    """Turn a usable strip into one or two restrained fixed-scale urban modules."""
    x,y,w,h=rect
    if w<78 or h<68:return []
    horizontal=w>=h
    long=w if horizontal else h
    # Never create giant procedural slabs. Long strips become two independent
    # modules separated by a service/alley gap.
    count=2 if long>=330 else 1
    gap=24.0
    span=(long-gap*(count-1))/count
    pieces=[]
    for i in range(count):
        if horizontal:
            pw=min(250.0,max(78.0,span));ph=min(170.0,max(68.0,h))
            px=x+i*(span+gap)+(span-pw)*.5;py=y+(h-ph)*.5
        else:
            pw=min(190.0,max(78.0,w));ph=min(230.0,max(68.0,span))
            px=x+(w-pw)*.5;py=y+i*(span+gap)+(span-ph)*.5
        pieces.append((px,py,pw,ph))
    return pieces


def build_infill_v2(roads,rp,buildings):
    p26.infill_rows.clear()
    surfaces=pass20.base.authored_surfaces();water=surfaces.get("water",[]);green=surfaces.get("green",[])
    blocks=pass20.base.read_csv(pass20.base.SEMANTIC/"urban_blocks.csv")
    stairs=pass20.base.read_csv(pass20.base.SEMANTIC/"building_stairwells.csv")
    stair_pts=[(float(r["x"]),float(r["y"])) for r in stairs]
    building_rects=[(float(b["x"]),float(b["y"]),float(b["w"]),float(b["h"])) for b in buildings]
    accepted=[];serial=0;dead_regions=0
    solid_kinds=("row_annex","shop_row","garage_row")
    open_kinds=("paved_courtyard","service_court","pocket_plaza","parking_strip","alley_link","fenced_yard")

    road_segments=[]
    for road in roads:
        if str(road.get("bridge","false")).lower()=="true":continue
        half,sidewalk,curb=p26.road_metrics(road);radius=half+curb+sidewalk+6
        for a,b in zip(rp[road["road_id"]],rp[road["road_id"]][1:]):road_segments.append((a,b,radius))

    def legal(rect):
        x,y,w,h=rect
        if w<66 or h<58:return False
        pts=p26.rect_corners(x,y,w,h)
        for pt in pts:
            if any(pass20.base.point_in_polygon(pt,poly) for poly in water):return False
            if any(pass20.base.point_in_polygon(pt,poly) for poly in green):return False
            if any(p26.segdist(pt,a,b)<radius for a,b,radius in road_segments):return False
        if any(rect_overlap(rect,b,14) for b in building_rects):return False
        if any(rect_overlap(rect,a,10) for a in accepted):return False
        # Keep exterior stairs and their landing path clear.
        if any(x-42<sx<x+w+42 and y-42<sy<y+h+42 for sx,sy in stair_pts):return False
        return True

    for block_index,block in enumerate(blocks):
        bx,by,bw,bh=block_world(block)
        if bw<150 or bh<140:continue
        if bx<pass20.base.HUDSON_EAST_X and bx+bw>pass20.base.HUDSON_WEST_X:continue
        district="fort_lee" if bx+bw<=pass20.base.HUDSON_WEST_X else "washington_heights"
        inset=26.0
        interior=(bx+inset,by+inset,max(0,bw-2*inset),max(0,bh-2*inset))
        ix,iy,iw,ih=interior
        if iw<90 or ih<80:continue
        inside=[r for r in building_rects if centre_in(r,(bx,by,bw,bh))]
        candidates=[]
        if inside:
            ux=min(r[0] for r in inside);uy=min(r[1] for r in inside)
            ux1=max(r[0]+r[2] for r in inside);uy1=max(r[1]+r[3] for r in inside)
            gap=24.0
            # The four dead strips around the detailed primary building(s).
            candidates.extend([
                (ix,iy,iw,max(0,uy-iy-gap)),
                (ix,uy1+gap,iw,max(0,iy+ih-(uy1+gap))),
                (ix,max(iy,uy),max(0,ux-ix-gap),max(0,min(iy+ih,uy1)-max(iy,uy))),
                (ux1+gap,max(iy,uy),max(0,ix+iw-(ux1+gap)),max(0,min(iy+ih,uy1)-max(iy,uy))),
            ])
        else:
            # Explicit open-destination blocks still receive designed surface use
            # instead of reading as an unexplained blank pad.
            candidates=[(ix,iy,iw,ih)]

        pieces=[]
        for slot,candidate in enumerate(candidates):
            pieces.extend((slot,p) for p in split_strip(candidate,block.get("block_id",str(block_index)),slot))
        # Largest pieces first; cap each block so density rises without becoming noise.
        pieces.sort(key=lambda item:item[1][2]*item[1][3],reverse=True)
        placed_here=0
        for piece_index,(slot,rect) in enumerate(pieces):
            if placed_here>=2:break
            if not legal(rect):continue
            dead_regions+=1
            s=p26.seed(f"rc2:{block.get('block_id',block_index)}:{slot}:{piece_index}")
            area=rect[2]*rect[3]
            # Roughly two thirds of sufficiently large dead strips become actual
            # secondary roof mass. Smaller/slimmer spaces become purposeful courts.
            if area>=10500 and s%3!=0:
                kind=solid_kinds[(s//5)%len(solid_kinds)];walkable="false";collision="solid"
            else:
                kind=open_kinds[(s//7)%len(open_kinds)];walkable="true" if kind not in {"fenced_yard"} else "false";collision="none"
            serial+=1;x,y,w,h=rect
            p26.infill_rows.append({
                "id":f"infill26_{serial:04d}","kind":kind,"district":district,
                "x":round(x,2),"y":round(y,2),"w":round(w,2),"h":round(h,2),
                "walkable":walkable,"collision_class":collision,
                "placement_rule":"road_bounded_block_dead_strip_art_first_pass26_rc2",
            })
            accepted.append(rect);placed_here+=1

    # A second, smaller deterministic sampling catches service gaps between blocks
    # that are not represented by a large rectangular strip. It never overrides
    # the same road/water/green/building/stair protections above.
    for district,xmin,xmax,ymin,ymax in (("fort_lee",280,4660,2280,10020),("washington_heights",10680,16080,2280,10020)):
        for gx,x in enumerate(range(xmin,xmax+1,250)):
            for gy,y in enumerate(range(ymin,ymax+1,240)):
                if len(p26.infill_rows)>=110:break
                s=p26.seed(f"gap:{district}:{gx}:{gy}")
                w=92+(s%73);h=72+((s//79)%61);rect=(x-w*.5,y-h*.5,w,h)
                if not legal(rect):continue
                dead_regions+=1;kind=open_kinds[(s//19)%len(open_kinds)]
                serial+=1
                p26.infill_rows.append({
                    "id":f"infill26_{serial:04d}","kind":kind,"district":district,
                    "x":round(rect[0],2),"y":round(rect[1],2),"w":round(w,2),"h":round(h,2),
                    "walkable":"false" if kind=="fenced_yard" else "true","collision_class":"none",
                    "placement_rule":"small_service_gap_art_first_pass26_rc2",
                });accepted.append(rect)
            if len(p26.infill_rows)>=110:break
        if len(p26.infill_rows)>=110:break

    pass20.base.write_csv(pass20.base.SEMANTIC/p26.INFILL_CSV,
        ("id","kind","district","x","y","w","h","walkable","collision_class","placement_rule"),p26.infill_rows)
    return dead_regions


def draw_structure(d,box,kind,night,s):
    x0,y0,x1,y1=box
    if night:
        shadow=(14,16,15,120);roof=(57,55,50,245);roof2=(70,65,57,245);edge=(120,111,92,245);metal=(86,94,91,240);warm=(117,75,46,225)
    else:
        shadow=(27,27,24,85);roof=(103,96,83,245);roof2=(121,108,91,245);edge=(65,61,54,245);metal=(128,134,128,240);warm=(157,92,55,225)
    # Fixed world-scale parapet/shadow treatment rather than scaling details with lot size.
    d.rectangle((x0+3,y0+3,x1+3,y1+3),fill=shadow)
    d.rectangle(box,fill=roof if s%2 else roof2,outline=edge,width=2)
    if x1-x0>12 and y1-y0>12:d.rectangle((x0+4,y0+4,x1-4,y1-4),outline=edge,width=1)
    long_horizontal=(x1-x0)>=(y1-y0)
    if kind=="shop_row":
        step=18
        if long_horizontal:
            for xx in range(x0+6,x1-8,step):d.rectangle((xx,y1-6,min(xx+10,x1-4),y1-2),fill=warm)
        else:
            for yy in range(y0+6,y1-8,step):d.rectangle((x1-6,yy,x1-2,min(yy+10,y1-4)),fill=warm)
    elif kind=="garage_row":
        step=16
        if long_horizontal:
            for xx in range(x0+5,x1-7,step):d.rectangle((xx,y1-7,min(xx+9,x1-3),y1-3),fill=edge)
        else:
            for yy in range(y0+5,y1-7,step):d.rectangle((x1-7,yy,x1-3,min(yy+9,y1-3)),fill=edge)
    # Small rooftop mechanical boxes stay roughly constant visual size.
    count=max(1,min(3,((x1-x0)+(y1-y0))//70))
    for i in range(count):
        px=x0+8+((s//(11+i*3))%max(9,x1-x0-18));py=y0+7+((s//(17+i*5))%max(8,y1-y0-16))
        d.rectangle((px,py,min(px+6,x1-3),min(py+5,y1-3)),fill=metal,outline=edge,width=1)


def draw_infill_v2(path:Path,night:bool):
    im=Image.open(path).convert("RGBA");ov=Image.new("RGBA",im.size,(0,0,0,0));d=ImageDraw.Draw(ov,"RGBA")
    if night:
        paved=(58,59,55,210);paved2=(67,64,57,205);edge=(93,89,78,220);green=(48,65,47,205);mark=(135,123,88,180)
    else:
        paved=(126,121,108,205);paved2=(142,132,113,200);edge=(92,88,78,220);green=(79,103,70,200);mark=(190,171,119,185)
    solid={"row_annex","shop_row","garage_row"}
    for row in p26.infill_rows:
        x=float(row["x"]);y=float(row["y"]);w=float(row["w"]);h=float(row["h"])
        a=pass20.base.world_to_master(x,y);b=pass20.base.world_to_master(x+w,y+h)
        box=(int(round(a[0])),int(round(a[1])),int(round(b[0])),int(round(b[1])));kind=row["kind"];s=p26.seed(row["id"])
        if kind in solid:
            draw_structure(d,box,kind,night,s);continue
        fill=green if kind=="fenced_yard" else (paved if s%2 else paved2)
        d.rectangle(box,fill=fill,outline=edge,width=1)
        if kind=="parking_strip":
            horizontal=(box[2]-box[0])>=(box[3]-box[1])
            if horizontal:
                for xx in range(box[0]+7,box[2]-5,13):d.line((xx,box[1]+3,xx,box[3]-3),fill=mark,width=1)
            else:
                for yy in range(box[1]+7,box[3]-5,13):d.line((box[0]+3,yy,box[2]-3,yy),fill=mark,width=1)
        elif kind=="alley_link":
            d.line((box[0]+3,(box[1]+box[3])//2,box[2]-3,(box[1]+box[3])//2),fill=edge,width=2)
        elif kind=="pocket_plaza":
            cx=(box[0]+box[2])//2;cy=(box[1]+box[3])//2
            d.rectangle((cx-4,cy-4,cx+4,cy+4),outline=mark,width=1)
            for px,py in ((box[0]+6,box[1]+6),(box[2]-6,box[1]+6),(box[0]+6,box[3]-6),(box[2]-6,box[3]-6)):d.ellipse((px-2,py-2,px+2,py+2),fill=green)
        elif kind=="service_court":
            for i in range(3):
                px=box[0]+7+(s//(23+i*7))%max(8,box[2]-box[0]-15);py=box[1]+6+(s//(31+i*5))%max(7,box[3]-box[1]-13)
                d.rectangle((px,py,min(px+5,box[2]-2),min(py+4,box[3]-2)),fill=edge)
        elif kind=="fenced_yard":
            for xx in range(box[0]+4,box[2],8):d.point((xx,box[1]+1),fill=edge)
    Image.alpha_composite(im,ov).convert("RGB").save(path)


def main():
    p26.PASS_ID=PASS_ID
    p26.build_infill=build_infill_v2
    p26.draw_infill=draw_infill_v2
    p26.main()


if __name__=="__main__":main()
