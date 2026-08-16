from __future__ import annotations

"""Pass 29: double the protected Pass-28 composition in both dimensions.

The Pass-28 city is preserved pixel-for-pixel as the central protected core. New
territory is authored around all four sides at the same world/component scale;
nothing is stretched. The extension continues the Hudson, extends edge roads,
adds non-grid connectors, merged apartment/church footprints, open blocks and
fixed-size roof/detail vocabulary. Matching review gameplay masks are emitted from
the same extension geometry.
"""

import csv
import hashlib
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass20_streetwall as pass20
import build_pass26_art_first_world as p26
import render_callback_preview as callback

PASS_ID = "pass_29_double_world_rc1"
OUT = pass20.base.OUT
SEMANTIC = pass20.base.SEMANTIC
OLD_W = pass20.base.MASTER_W
OLD_H = pass20.base.MASTER_H
NEW_W = OLD_W * 2
NEW_H = OLD_H * 2
CORE_X = OLD_W // 2
CORE_Y = OLD_H // 2
CORE_BOX = (CORE_X, CORE_Y, CORE_X + OLD_W, CORE_Y + OLD_H)
TILE_SIZE = 1024
SCREENSHOT_DIR = Path(__file__).resolve().parents[3] / "qa" / "pass29_screenshots"
EXTENSION_BUILDINGS = "pass29_extension_buildings.csv"
EXTENSION_ROADS = "pass29_extension_roads.csv"
EXTENSION_CROSSINGS = "pass29_extension_crossings.csv"
EXTENSION_OPEN_BLOCKS = "pass29_extension_open_blocks.csv"


def stable(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


def write_csv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def core_contains(x: float, y: float, margin: float = 0.0) -> bool:
    return CORE_X - margin <= x <= CORE_X + OLD_W + margin and CORE_Y - margin <= y <= CORE_Y + OLD_H + margin


def district_for(x: float) -> str:
    # Hudson centre in the shifted composition is around x=7936 master px.
    if x < 6500:
        return "new_jersey_extension"
    if x > 9500:
        return "upper_manhattan_extension"
    return "hudson_edge"


def palette(night: bool):
    if night:
        return {
            "land": (48, 54, 49), "land2": (55, 60, 53), "water": (26, 45, 57), "water2": (35, 58, 70),
            "road": (38, 41, 41), "road2": (48, 51, 50), "curb": (92, 92, 86), "sidewalk": (70, 72, 69),
            "lane": (153, 148, 124), "cross": (192, 190, 181), "green": (47, 68, 48), "green2": (58, 81, 56),
            "roof": ((66, 64, 58), (72, 69, 61), (61, 69, 68), (77, 67, 58), (68, 63, 70)),
            "edge": (37, 39, 37), "detail": (105, 104, 94), "glass": (45, 65, 70), "warm": (134, 91, 56),
            "church": (78, 66, 55), "church2": (105, 87, 65), "tree": (44, 75, 49), "tree2": (61, 92, 57),
        }
    return {
        "land": (67, 74, 67), "land2": (76, 81, 73), "water": (39, 61, 72), "water2": (50, 76, 88),
        "road": (42, 45, 45), "road2": (53, 56, 55), "curb": (118, 118, 110), "sidewalk": (82, 84, 80),
        "lane": (171, 164, 137), "cross": (218, 215, 202), "green": (72, 98, 69), "green2": (85, 112, 77),
        "roof": ((111, 104, 91), (101, 105, 101), (124, 96, 82), (92, 101, 94), (116, 108, 103)),
        "edge": (45, 46, 43), "detail": (150, 143, 124), "glass": (70, 93, 99), "warm": (158, 117, 76),
        "church": (124, 104, 82), "church2": (153, 128, 92), "tree": (53, 91, 58), "tree2": (78, 113, 70),
    }


def make_land(night: bool) -> Image.Image:
    P = palette(night)
    im = Image.new("RGB", (NEW_W, NEW_H), P["land"])
    d = ImageDraw.Draw(im)
    rng = random.Random(stable("pass29-land-night" if night else "pass29-land-day"))
    for _ in range((NEW_W * NEW_H) // 4600):
        x = rng.randrange(NEW_W); y = rng.randrange(NEW_H)
        r = 1 + rng.randrange(3)
        d.rectangle((x, y, x+r, y+r), fill=P["land2"])
    return im


def hudson_polygon() -> list[tuple[int, int]]:
    # Continue the protected Hudson north/south with a mild shoreline meander.
    return [
        (6620, 0), (9340, 0), (9250, 620), (9410, 1320), (9310, 2048),
        (9344, CORE_Y), (9344, CORE_Y + OLD_H), (9270, 6740), (9385, 7360), (9290, NEW_H),
        (6580, NEW_H), (6660, 7440), (6510, 6810), (6528, CORE_Y + OLD_H),
        (6528, CORE_Y), (6600, 1420), (6485, 720),
    ]


def draw_water_and_green(im: Image.Image, night: bool, solid: Image.Image, cycle: Image.Image):
    P = palette(night); d = ImageDraw.Draw(im); sd = ImageDraw.Draw(solid); cd = ImageDraw.Draw(cycle)
    hudson = hudson_polygon()
    # Do not cover the protected core: extension water is clipped to outer bands.
    water_layer = Image.new("L", im.size, 0); wd = ImageDraw.Draw(water_layer); wd.polygon(hudson, fill=255)
    wd.rectangle(CORE_BOX, fill=0)
    water_color = Image.new("RGB", im.size, P["water"])
    water_color2 = Image.new("RGB", im.size, P["water2"])
    im.paste(water_color, mask=water_layer)
    # sparse horizontal water texture
    stripe = Image.new("L", im.size, 0); st = ImageDraw.Draw(stripe)
    for y in range(18, NEW_H, 29): st.line((0, y, NEW_W, y), fill=80, width=1)
    im.paste(water_color2, mask=ImageChops.multiply(water_layer, stripe))
    sd.bitmap((0,0), water_layer, fill=255); cd.bitmap((0,0), water_layer, fill=0)

    parks = [
        (760, 420, 2220, 1190), (1110, 6740, 2820, 7860),
        (10540, 360, 12290, 1320), (13020, 660, 15140, 1690),
        (10820, 6740, 12640, 7890), (13700, 6420, 15720, 7760),
        (400, 2460, 2700, 3380), (13440, 3200, 16040, 4110),
    ]
    for i, (x0,y0,x1,y1) in enumerate(parks):
        # keep protected core exact
        if x1 > CORE_X and x0 < CORE_X + OLD_W and y1 > CORE_Y and y0 < CORE_Y + OLD_H:
            continue
        d.rounded_rectangle((x0,y0,x1,y1), radius=28, fill=P["green"], outline=P["green2"], width=3)
        rng = random.Random(stable(f"park29:{i}"))
        for _ in range(max(8, int((x1-x0)*(y1-y0)/125000))):
            x=rng.randint(x0+22,x1-22); y=rng.randint(y0+22,y1-22); r=rng.randint(5,9)
            d.ellipse((x-r-2,y-r+1,x+r+2,y+r+5), fill=P["edge"])
            d.ellipse((x-r,y-r,x+r,y+r), fill=P["tree"])
            d.ellipse((x-r+2,y-r+1,x+r-2,y+r-3), fill=P["tree2"])


def source_edge_points():
    roads, rp, _ = pass20.base.authored_block_network()
    edges = defaultdict(list)
    for road in roads:
        rid = road["road_id"]
        pts = [pass20.base.world_to_master(x,y) for x,y in rp[rid]]
        for x,y in (pts[0], pts[-1]):
            if x <= 2: edges["west"].append((rid, x+CORE_X, y+CORE_Y, road))
            if x >= OLD_W-2: edges["east"].append((rid, x+CORE_X, y+CORE_Y, road))
            if y <= 2: edges["north"].append((rid, x+CORE_X, y+CORE_Y, road))
            if y >= OLD_H-2: edges["south"].append((rid, x+CORE_X, y+CORE_Y, road))
    return edges


def make_extension_roads():
    edges = source_edge_points(); roads=[]
    serial=0
    def add(name, pts, road_class="residential", lanes=2, source="new_connector"):
        nonlocal serial
        serial += 1
        rid=f"p29_{serial:03d}_{name}"
        roads.append({"road_id":rid,"road_class":road_class,"lanes":lanes,"source":source,"points":pts})

    # Continue every meaningful old-city edge road outward, introducing a small
    # deterministic bend so the extension does not become a perfect lattice.
    for side, items in edges.items():
        for idx,(source_id,x,y,road) in enumerate(items):
            cls=str(road.get("highway","residential")); lanes=max(1,int(float(road.get("lanes",2))))
            wobble=((stable(source_id+side)%121)-60)
            if side=="west": pts=[(x,y),(x-760,y+wobble*.35),(1380,y+wobble),(0,y+wobble*.55)]
            elif side=="east": pts=[(x,y),(x+760,y-wobble*.3),(14940,y+wobble),(NEW_W,y+wobble*.6)]
            elif side=="north": pts=[(x,y),(x+wobble*.4,y-540),(x+wobble,980),(x+wobble*.6,0)]
            else: pts=[(x,y),(x-wobble*.35,y+560),(x+wobble,7240),(x+wobble*.55,NEW_H)]
            add(source_id.replace("_","-")[:24],pts,cls,lanes,"protected_edge_continuation")

    # Additional long roads break the enormous extension faces into plausible
    # districts. Coordinates deliberately vary and several roads are diagonal.
    extras=[
        ("nj_outer_north",[(0,820),(1380,860),(3020,760),(CORE_X,940)],"secondary",3),
        ("nj_outer_mid",[(0,1550),(1540,1480),(3020,1610),(CORE_X,1540)],"primary",4),
        ("nj_outer_south",[(0,7040),(1440,6960),(2960,7130),(CORE_X,7010)],"secondary",3),
        ("nj_ridge_diag",[(820,0),(1460,1120),(2150,2240),(2960,3380),(CORE_X,4200)],"tertiary",2),
        ("nj_bluff_diag",[(3140,0),(2910,950),(2730,1760),(2510,2048)],"residential",2),
        ("man_north_avenue",[(CORE_X+OLD_W,920),(13620,850),(14940,940),(NEW_W,820)],"primary",4),
        ("man_mid_avenue",[(CORE_X+OLD_W,1580),(13720,1660),(15120,1530),(NEW_W,1610)],"secondary",3),
        ("man_south_avenue",[(CORE_X+OLD_W,7040),(13780,6960),(15100,7110),(NEW_W,7030)],"primary",4),
        ("man_diagonal",[(NEW_W,260),(15180,1220),(14260,2180),(13220,3180),(CORE_X+OLD_W,3930)],"secondary",3),
        ("north_crosstown",[(740,0),(2140,620),(4040,760),(6100,640)],"secondary",3),
        ("north_east_crosstown",[(10180,620),(12200,720),(14320,620),(NEW_W,380)],"secondary",3),
        ("south_crosstown",[(520,NEW_H),(2180,7660),(3920,7540),(6080,7690)],"secondary",3),
        ("south_east_crosstown",[(10120,7700),(12200,7580),(14380,7700),(NEW_W,7480)],"secondary",3),
    ]
    for name,pts,cls,lanes in extras:add(name,pts,cls,lanes,"pass29_authored_extension")
    return roads


def road_style(row):
    lanes=int(row["lanes"]); cls=row["road_class"]
    asphalt={1:34,2:48,3:66,4:82}.get(lanes,48)
    if cls in {"primary","trunk"}: asphalt=max(asphalt,82)
    elif cls=="secondary": asphalt=max(asphalt,64)
    sidewalk=24 if lanes<=2 else 30
    curb=5
    return asphalt,sidewalk,curb


def draw_polyline(d: ImageDraw.ImageDraw, pts, fill, width):
    ip=[(int(round(x)),int(round(y))) for x,y in pts]
    d.line(ip,fill=fill,width=max(1,int(width)),joint="curve")
    r=max(1,int(width)//2)
    for p in ip:d.ellipse((p[0]-r,p[1]-r,p[0]+r,p[1]+r),fill=fill)


def draw_roads(im: Image.Image, roads, night: bool, walkable: Image.Image, roadmask: Image.Image):
    P=palette(night);d=ImageDraw.Draw(im);wd=ImageDraw.Draw(walkable);rd=ImageDraw.Draw(roadmask)
    for row in roads:
        asphalt,sidewalk,curb=road_style(row);pts=row["points"]
        # Clip by drawing through masks that exclude protected core.
        layer=Image.new("RGB",im.size,(0,0,0)); mask=Image.new("L",im.size,0); md=ImageDraw.Draw(mask)
        draw_polyline(md,pts,255,asphalt+2*(sidewalk+curb))
        ImageDraw.Draw(mask).rectangle(CORE_BOX,fill=0)
        ld=ImageDraw.Draw(layer)
        draw_polyline(ld,pts,P["sidewalk"],asphalt+2*(sidewalk+curb))
        draw_polyline(ld,pts,P["curb"],asphalt+2*curb)
        draw_polyline(ld,pts,P["road"],asphalt)
        im.paste(layer,mask=mask)
        rd.bitmap((0,0),mask,fill=255)
        wd.bitmap((0,0),mask,fill=255)
        # center/lane dashes remain thin and scale-stable
        if int(row["lanes"])>=2:
            line_layer=Image.new("RGB",im.size,(0,0,0));lm=Image.new("L",im.size,0);lmd=ImageDraw.Draw(lm);lld=ImageDraw.Draw(line_layer)
            for a,b in zip(pts,pts[1:]):
                dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
                if length<1:continue
                ux,uy=dx/length,dy/length
                step=34;dash=12
                q=0
                while q<length:
                    q2=min(length,q+dash)
                    p0=(a[0]+ux*q,a[1]+uy*q);p1=(a[0]+ux*q2,a[1]+uy*q2)
                    lld.line((p0,p1),fill=P["lane"],width=2);lmd.line((p0,p1),fill=255,width=2);q+=step
            lmd.rectangle(CORE_BOX,fill=0);im.paste(line_layer,mask=lm)


def segment_intersection(a,b,c,d):
    rx,ry=b[0]-a[0],b[1]-a[1];sx,sy=d[0]-c[0],d[1]-c[1];den=rx*sy-ry*sx
    if abs(den)<1e-7:return None
    qx,qy=c[0]-a[0],c[1]-a[1];t=(qx*sy-qy*sx)/den;u=(qx*ry-qy*rx)/den
    if 0<=t<=1 and 0<=u<=1:return a[0]+t*rx,a[1]+t*ry
    return None


def draw_crossings(im:Image.Image,roads,night:bool):
    P=palette(night);d=ImageDraw.Draw(im);rows=[];seen=set();serial=0
    segs=[]
    for r in roads:
        for a,b in zip(r["points"],r["points"][1:]):segs.append((r,a,b))
    for i,(r,a,b) in enumerate(segs):
        for s,c,e in segs[i+1:]:
            if r["road_id"]==s["road_id"]:continue
            hit=segment_intersection(a,b,c,e)
            if hit is None or core_contains(*hit,margin=10):continue
            key=(round(hit[0]/18),round(hit[1]/18))
            if key in seen:continue
            seen.add(key)
            # Do not zebra every residential crossing; keep GTA2-scale clutter sane.
            priority=max(int(r["lanes"]),int(s["lanes"]))
            if priority<3 and stable(str(key))%3:continue
            for target,p0,p1 in ((r,a,b),(s,c,e)):
                serial+=1;dx=p1[0]-p0[0];dy=p1[1]-p0[1];L=math.hypot(dx,dy) or 1;ux,uy=dx/L,dy/L;nx,ny=-uy,ux
                asphalt,_,_=road_style(target); depth=14; centre=(hit[0]+ux*(asphalt*.58+24),hit[1]+uy*(asphalt*.58+24))
                # bars parallel to road/lane direction; entire zebra spans carriageway
                for off in range(-asphalt//2+5,asphalt//2-4,10):
                    cx=centre[0]+nx*off;cy=centre[1]+ny*off
                    pA=(cx-ux*depth*.5,cy-uy*depth*.5);pB=(cx+ux*depth*.5,cy+uy*depth*.5)
                    d.line((pA,pB),fill=P["cross"],width=4)
                rows.append({"crossing_id":f"pass29_cross_{serial:04d}","road_id":target["road_id"],"x":round(centre[0],2),"y":round(centre[1],2),"angle":round(math.degrees(math.atan2(dy,dx)),2),"span":asphalt,"depth":depth})
    return rows


def road_distance(x,y,roads):
    best=1e9
    for r in roads:
        for a,b in zip(r["points"],r["points"][1:]):
            dx=b[0]-a[0];dy=b[1]-a[1];den=dx*dx+dy*dy
            t=0 if den<=1e-9 else max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/den))
            qx=a[0]+t*dx;qy=a[1]+t*dy;best=min(best,math.hypot(x-qx,y-qy))
    return best


def intersects_water(box):
    x0,y0,x1,y1=box
    # conservative Hudson band, with current-core exclusion irrelevant to extension lots
    samples=((x0,y0),(x1,y0),(x0,y1),(x1,y1),((x0+x1)/2,(y0+y1)/2))
    poly=hudson_polygon()
    def inside(p):
        x,y=p;ok=False;j=len(poly)-1
        for i in range(len(poly)):
            xi,yi=poly[i];xj,yj=poly[j]
            if ((yi>y)!=(yj>y)) and x < (xj-xi)*(y-yi)/((yj-yi) or 1e-9)+xi:ok=not ok
            j=i
        return ok
    return any(inside(p) for p in samples)


def building_shape(x,y,w,h,variant):
    if variant=="L":
        cutw=max(26,int(w*.34));cuth=max(26,int(h*.36));return [[(x,y),(x+w,y),(x+w,y+h),(x+cutw,y+h),(x+cutw,y+cuth),(x,y+cuth)]]
    if variant=="U":
        arm=max(28,int(w*.24));notch=max(28,int(h*.42));return [[(x,y),(x+w,y),(x+w,y+h),(x+w-arm,y+h),(x+w-arm,y+notch),(x+arm,y+notch),(x+arm,y+h),(x,y+h)]]
    if variant=="chamfer":
        c=max(12,min(34,int(min(w,h)*.14)));return [[(x+c,y),(x+w-c,y),(x+w,y+c),(x+w,y+h),(x,y+h),(x,y+c)]]
    return [[(x,y),(x+w,y),(x+w,y+h),(x,y+h)]]


def draw_building(im,d,box,bid,kind,night,solid):
    P=palette(night);x,y,w,h=box;s=stable(bid);variant=("L","U","chamfer","rect")[s%4]
    if kind=="church":variant="chamfer"
    polys=building_shape(x,y,w,h,variant);sd=ImageDraw.Draw(solid)
    roof=P["church"] if kind=="church" else P["roof"][s%len(P["roof"])]
    # compact contact shadow, then fixed-scale roof art
    for poly in polys:d.polygon([(px+4,py+5) for px,py in poly],fill=P["edge"])
    for poly in polys:
        d.polygon(poly,fill=roof,outline=P["edge"]);sd.polygon(poly,fill=255)
    # fixed-width seams and rooftop components: never scaled with footprint
    for xx in range(x+14,x+w-10,22):d.line((xx,y+6,xx,y+h-6),fill=P["detail"],width=1)
    modules=max(2,min(9,(w*h)//10500+2))
    for j in range(modules):
        q=stable(f"{bid}:{j}");mw=(10,14,18,22)[q%4];mh=(8,10,12,16)[(q>>5)%4]
        mx=x+8+(q>>9)%max(1,w-mw-16);my=y+8+(q>>19)%max(1,h-mh-16)
        d.rectangle((mx+2,my+2,mx+mw+2,my+mh+2),fill=P["edge"])
        d.rectangle((mx,my,mx+mw,my+mh),fill=P["glass"] if j%3==0 else P["detail"],outline=P["edge"])
    if kind=="church":
        # larger nave + transept + tower reads as a real landmark footprint.
        cx=x+w//2;cy=y+h//2;nav=max(18,min(w//4,34));tran=max(24,min(h//4,42))
        d.rectangle((cx-nav, y+10, cx+nav, y+h-10),outline=P["church2"],width=3)
        d.rectangle((x+10,cy-tran//2,x+w-10,cy+tran//2),outline=P["church2"],width=3)
        r=9;d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=P["church2"],outline=P["edge"])


def place_buildings(im:Image.Image,roads,night:bool,solid:Image.Image):
    P=palette(night);d=ImageDraw.Draw(im);rows=[];open_rows=[]
    # A coarse candidate lattice is deliberately jittered. Lots merge across 2-3
    # base cells, producing larger apartment/institutional footprints while local
    # fixed-size details preserve the existing wall/window/roof scale language.
    cell_w=250;cell_h=210
    occupied=[];serial=0;open_serial=0
    for gy in range(120,NEW_H-120,cell_h):
        for gx in range(120,NEW_W-120,cell_w):
            cx=gx+cell_w*.5;cy=gy+cell_h*.5
            if core_contains(cx,cy,margin=80):continue
            if 6400<cx<9540:continue
            if road_distance(cx,cy,roads)<105:continue
            q=stable(f"lot29:{gx}:{gy}")
            # some whole cells become intentional green/service courts instead of blank dirt
            if q%31 in (3,17):
                w=180;h=145;x=int(gx+(q%27));y=int(gy+((q>>7)%31))
                if not intersects_water((x,y,x+w,y+h)) and road_distance(x+w/2,y+h/2,roads)>92:
                    kind="green_court" if q%2 else "service_court";open_serial+=1
                    col=P["green"] if kind=="green_court" else P["road2"]
                    d.rounded_rectangle((x,y,x+w,y+h),radius=12,fill=col,outline=P["curb"],width=2)
                    open_rows.append({"id":f"p29_open_{open_serial:03d}","kind":kind,"x":x,"y":y,"w":w,"h":h,"district":district_for(cx)})
                continue
            merge=1 + (1 if q%7==0 else 0) + (1 if q%29==0 else 0)
            w=min(620,150+merge*92+((q>>5)%54));h=min(460,118+(1+(q>>11)%2)*72+((q>>17)%46))
            x=int(cx-w/2 + ((q>>23)%31-15));y=int(cy-h/2 + ((q>>29)%27-13))
            box=(x,y,x+w,y+h)
            if intersects_water(box):continue
            if road_distance(x+w/2,y+h/2,roads)<95:continue
            if any(not (box[2]+18<o[0] or box[0]-18>o[2] or box[3]+18<o[1] or box[1]-18>o[3]) for o in occupied):continue
            occupied.append(box);serial+=1
            # larger church landmarks use deliberately merged 2-3-lot footprints
            church=(q%137==0 and w>=330 and h>=210)
            kind="church" if church else ("merged_apartment" if merge>=2 else "urban_block")
            bid=f"pass29_building_{serial:04d}"
            draw_building(im,d,(x,y,w,h),bid,kind,night,solid)
            rows.append({"building_id":bid,"kind":kind,"district":district_for(cx),"x":x,"y":y,"w":w,"h":h,"merged_lot_count":merge,"fixed_component_scale":"true"})
    return rows,open_rows


def build_mode(mode:str,roads):
    night=mode=="night";old=Image.open(OUT/f"unified_composition_{mode}.png").convert("RGB")
    if old.size!=(OLD_W,OLD_H):raise RuntimeError(f"Pass 29 expected protected Pass-28 master {(OLD_W,OLD_H)}, got {old.size}")
    im=make_land(night)
    solid=Image.new("L",(NEW_W,NEW_H),0);walk=Image.new("L",(NEW_W,NEW_H),255);cycle=Image.new("L",(NEW_W,NEW_H),255);roadmask=Image.new("L",(NEW_W,NEW_H),0)
    draw_water_and_green(im,night,solid,cycle)
    draw_roads(im,roads,night,walk,roadmask)
    crossings=draw_crossings(im,roads,night)
    buildings,open_blocks=place_buildings(im,roads,night,solid)
    # protected core is pasted last and therefore remains byte-for-byte visually identical
    im.paste(old,(CORE_X,CORE_Y))
    # Preserve Pass-28 gameplay masks in the same shifted core.
    for name,target in (("solid_mask_master.png",solid),("walkable_mask_master.png",walk),("cycle_mask_master.png",cycle)):
        src=Image.open(p26.MASK_DIR/name).convert("L")
        if src.size==(OLD_W,OLD_H):target.paste(src,(CORE_X,CORE_Y))
    collision=solid.copy()
    # Walk/cycle exclude extension solids; the protected core remains authoritative after paste.
    inv=ImageChops.invert(solid);walk=ImageChops.multiply(walk,inv);cycle=ImageChops.multiply(cycle,inv)
    return im,solid,walk,cycle,collision,crossings,buildings,open_blocks,old


def tile_image(image:Image.Image,target:Path,prefix="tile"):
    target.mkdir(parents=True,exist_ok=True)
    for old in target.glob("*.png"):old.unlink()
    count=0
    for row in range(NEW_H//TILE_SIZE):
        for col in range(NEW_W//TILE_SIZE):
            image.crop((col*TILE_SIZE,row*TILE_SIZE,(col+1)*TILE_SIZE,(row+1)*TILE_SIZE)).save(target/f"{prefix}_{col:02d}_{row:02d}.png");count+=1
    return count


def save_review_screenshots(day:Image.Image,night:Image.Image):
    SCREENSHOT_DIR.mkdir(parents=True,exist_ok=True)
    day.resize((2048,1024),Image.Resampling.LANCZOS).save(SCREENSHOT_DIR/"00_whole_day.png")
    night.resize((2048,1024),Image.Resampling.LANCZOS).save(SCREENSHOT_DIR/"01_whole_night.png")
    crops={
        "02_northwest_extension.png":(0,0,CORE_X,CORE_Y+1100),
        "03_northeast_extension.png":(CORE_X+OLD_W-1100,0,NEW_W,CORE_Y+1100),
        "04_southwest_extension.png":(0,CORE_Y+OLD_H-1100,CORE_X+1100,NEW_H),
        "05_southeast_extension.png":(CORE_X+OLD_W-1100,CORE_Y+OLD_H-1100,NEW_W,NEW_H),
        "06_core_boundary.png":(CORE_X-520,CORE_Y-420,CORE_X+OLD_W+520,CORE_Y+OLD_H+420),
    }
    for name,box in crops.items():
        crop=day.crop(box);crop.thumbnail((2048,1200),Image.Resampling.LANCZOS);crop.save(SCREENSHOT_DIR/name)


def update_manifest(core_error,roads,crossings,buildings,open_blocks,art_tiles,mask_tiles):
    path=OUT/"composition_manifest.csv";rows=pass20.base.read_csv(path)
    remove={"pass_id"}
    rows=[r for r in rows if r.get("key") not in remove and not r.get("key","").startswith("pass29_") and not r.get("key","").startswith("sha256_unified_composition_")]
    merged=sum(int(r["merged_lot_count"])>=2 for r in buildings);churches=sum(r["kind"]=="church" for r in buildings)
    rows.extend([
        {"key":"pass_id","value":PASS_ID},
        {"key":"pass29_double_world","value":"true"},
        {"key":"pass29_linear_extent_multiplier","value":"2"},
        {"key":"pass29_area_multiplier","value":"4"},
        {"key":"pass29_master_size","value":f"{NEW_W}x{NEW_H}"},
        {"key":"pass29_world_size","value":f"{NEW_W*2}x{NEW_H*2}"},
        {"key":"pass29_protected_core_offset","value":f"{CORE_X},{CORE_Y}"},
        {"key":"pass29_protected_core_mean_rgb_error","value":f"{core_error:.6f}"},
        {"key":"pass29_extension_roads","value":str(len(roads))},
        {"key":"pass29_extension_crossings","value":str(len(crossings))},
        {"key":"pass29_extension_buildings","value":str(len(buildings))},
        {"key":"pass29_merged_footprint_buildings","value":str(merged)},
        {"key":"pass29_church_landmarks","value":str(churches)},
        {"key":"pass29_intentional_open_blocks","value":str(len(open_blocks))},
        {"key":"pass29_component_scale_policy","value":"fixed_pixels_no_map_stretch"},
        {"key":"pass29_road_policy","value":"protected_edge_continuations_plus_irregular_authored_connectors"},
        {"key":"pass29_hudson_policy","value":"continuous_north_south_extension_protected_core_unchanged"},
        {"key":"pass29_art_tiles_per_mode","value":str(art_tiles)},
        {"key":"pass29_gameplay_mask_tiles","value":str(mask_tiles)},
    ])
    for mode in ("day","night"):
        p=OUT/f"unified_composition_{mode}.png";rows.append({"key":f"sha256_{p.stem}","value":pass20.base.sha256(p)})
    pass20.base.write_csv(path,("key","value"),rows)


def main():
    for mode in ("day","night"):
        p=OUT/f"unified_composition_{mode}.png"
        if not p.exists():raise RuntimeError(f"Pass 29 requires an already-built Pass 28 master: {p}")
    roads=make_extension_roads()
    day=build_mode("day",roads);night=build_mode("night",roads)
    day_im,solid,walk,cycle,collision,crossings,buildings,open_blocks,old_day=day
    night_im=night[0];old_night=night[-1]
    # Day/night topology must be identical; semantics come from day build.
    day_core=day_im.crop(CORE_BOX);night_core=night_im.crop(CORE_BOX)
    err_day=sum(ImageStat.mean for ImageStat in []) if False else 0.0
    diff=ImageChops.difference(day_core,old_day);hist=diff.histogram();core_error=sum((i%256)*v for i,v in enumerate(hist))/max(1,OLD_W*OLD_H*3)
    diff_n=ImageChops.difference(night_core,old_night);hist_n=diff_n.histogram();core_error_n=sum((i%256)*v for i,v in enumerate(hist_n))/max(1,OLD_W*OLD_H*3)
    core_error=max(core_error,core_error_n)

    day_path=OUT/"unified_composition_day.png";night_path=OUT/"unified_composition_night.png"
    day_im.save(day_path);night_im.save(night_path)
    write_csv(SEMANTIC/EXTENSION_ROADS,("road_id","road_class","lanes","source","point_order","x","y"),[
        {"road_id":r["road_id"],"road_class":r["road_class"],"lanes":r["lanes"],"source":r["source"],"point_order":i,"x":round(x,2),"y":round(y,2)}
        for r in roads for i,(x,y) in enumerate(r["points"])
    ])
    write_csv(SEMANTIC/EXTENSION_CROSSINGS,("crossing_id","road_id","x","y","angle","span","depth"),crossings)
    write_csv(SEMANTIC/EXTENSION_BUILDINGS,("building_id","kind","district","x","y","w","h","merged_lot_count","fixed_component_scale"),buildings)
    write_csv(SEMANTIC/EXTENSION_OPEN_BLOCKS,("id","kind","x","y","w","h","district"),open_blocks)

    art_tiles=tile_image(day_im,OUT/"tiles"/"day")
    tile_image(night_im,OUT/"tiles"/"night")
    mask_dir=OUT/"gameplay_masks";mask_dir.mkdir(parents=True,exist_ok=True)
    masks={"solid":solid,"walkable":walk,"cycle":cycle,"collision":collision}
    for name,image in masks.items():
        image.save(mask_dir/f"{name}_mask_master.png")
    mask_tiles=sum(tile_image(image,mask_dir/name) for name,image in masks.items())
    save_review_screenshots(day_im,night_im)
    update_manifest(core_error,roads,crossings,buildings,open_blocks,art_tiles,mask_tiles)
    print(f"PASS29_DOUBLE_WORLD size={NEW_W}x{NEW_H} core_error={core_error:.6f} roads={len(roads)} crossings={len(crossings)} buildings={len(buildings)} merged={sum(int(r['merged_lot_count'])>=2 for r in buildings)} churches={sum(r['kind']=='church' for r in buildings)} open_blocks={len(open_blocks)} art_tiles_per_mode={art_tiles} mask_tiles={mask_tiles}")


if __name__=="__main__":main()
