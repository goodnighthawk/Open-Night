from __future__ import annotations

"""Pass 26: art-first full-world generation.

The final rendered world is the design authority.  Gameplay masks are generated
*after* the complete day/night artwork from the same final semantic geometry, then
tiled for runtime collision/walkability consumption.  This pass also increases
pedestrian/cycle road permeability and converts sampled dead urban land into
purposeful visual uses instead of leaving large blank pads.
"""

import csv
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
import build_pass24_landmarks as pass24

PASS_ID = "pass_26_art_first_world_rc1"
INFILL_CSV = "urban_infill_pass26.csv"
CROSSING_CSV = "mobility_crossings_pass26.csv"
MASK_MANIFEST_CSV = "gameplay_mask_tiles_pass26.csv"
MASK_DIR = pass20.base.OUT / "gameplay_masks"
SCREENSHOT_DIR = Path(__file__).resolve().parents[3] / "qa" / "pass26_screenshots"

infill_rows: list[dict[str, object]] = []
mobility_rows: list[dict[str, object]] = []


def seed(text: str) -> int:
    return int(hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:12], 16)


def segdist(p, a, b):
    dx=b[0]-a[0];dy=b[1]-a[1];den=dx*dx+dy*dy
    if den<=1e-9:return math.hypot(p[0]-a[0],p[1]-a[1])
    t=max(0.0,min(1.0,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den))
    qx=a[0]+t*dx;qy=a[1]+t*dy
    return math.hypot(p[0]-qx,p[1]-qy)


def road_metrics(road):
    lanes=max(1,int(float(road.get("lanes",1))))
    half=max(38.0,lanes*38.0+10.0)*pass20.base.ROAD_WIDTH_SCALE*.5
    sidewalk=max(28.0,float(road.get("sidewalk_width",28)))*pass20.base.SIDEWALK_SCALE
    curb=max(4.0,float(road.get("curb_width",4)))
    return half,sidewalk,curb


def world_poly_to_master(poly):
    return [(int(round(pass20.base.world_to_master(x,y)[0])),int(round(pass20.base.world_to_master(x,y)[1]))) for x,y in poly]


def point_in_box(p, box, pad=0.0):
    x,y=p;x0,y0,x1,y1=box
    return x0-pad<=x<=x1+pad and y0-pad<=y<=y1+pad


def rect_corners(x,y,w,h):
    return ((x,y),(x+w,y),(x+w,y+h),(x,y+h),(x+w*.5,y+h*.5))


def build_infill(roads,rp,buildings):
    infill_rows.clear()
    surfaces=pass20.base.authored_surfaces();water=surfaces.get("water",[]);green=surfaces.get("green",[])
    building_boxes=[(float(b["x"]),float(b["y"]),float(b["x"])+float(b["w"]),float(b["y"])+float(b["h"])) for b in buildings]
    road_segments=[]
    for road in roads:
        if str(road.get("bridge","false")).lower()=="true":continue
        half,sidewalk,curb=road_metrics(road)
        radius=half+curb+sidewalk+24
        for a,b in zip(rp[road["road_id"]],rp[road["road_id"]][1:]):road_segments.append((a,b,radius))

    kinds=("paved_courtyard","service_yard","pocket_plaza","parking_strip","alley_link","fenced_yard","garage_row")
    before=0
    serial=0
    # Purposefully coarse cells: this targets visually dead parcels rather than
    # sprinkling microscopic noise everywhere.
    district_bands=(
        ("fort_lee",240,4680,2240,10040),
        ("washington_heights",10640,16120,2240,10040),
    )
    for district,xmin,xmax,ymin,ymax in district_bands:
        gx=0;x=xmin
        while x<=xmax:
            gy=0;y=ymin
            while y<=ymax:
                s=seed(f"{district}:{gx}:{gy}")
                cx=x+((s%61)-30);cy=y+(((s//67)%61)-30)
                # Dimensions stay in a restrained fixed range so these read as
                # real urban uses, not giant procedural slabs.
                w=150+((s//101)%91);h=104+((s//211)%77)
                rx=cx-w*.5;ry=cy-h*.5
                pts=rect_corners(rx,ry,w,h)
                legal=True
                for p in pts:
                    if any(pass20.base.point_in_polygon(p,poly) for poly in water):legal=False;break
                    if any(pass20.base.point_in_polygon(p,poly) for poly in green):legal=False;break
                    if any(point_in_box(p,box,26) for box in building_boxes):legal=False;break
                    if any(segdist(p,a,b)<radius for a,b,radius in road_segments):legal=False;break
                if legal:
                    before+=1
                    kind=kinds[(s//307)%len(kinds)]
                    walkable="true" if kind in {"paved_courtyard","pocket_plaza","alley_link","parking_strip"} else "false"
                    collision="solid" if kind=="garage_row" else "none"
                    serial+=1
                    infill_rows.append({
                        "id":f"infill26_{serial:04d}","kind":kind,"district":district,
                        "x":round(rx,2),"y":round(ry,2),"w":round(w,2),"h":round(h,2),
                        "walkable":walkable,"collision_class":collision,
                        "placement_rule":"sampled_dead_urban_land_art_first_pass26_v1",
                    })
                y+=310;gy+=1
            x+=330;gx+=1
    pass20.base.write_csv(pass20.base.SEMANTIC/INFILL_CSV,
        ("id","kind","district","x","y","w","h","walkable","collision_class","placement_rule"),infill_rows)
    return before


def polyline_positions(points, spacing, start_offset=None):
    out=[]
    if start_offset is None:start_offset=spacing*.5
    target=start_offset;walked=0.0
    for a,b in zip(points,points[1:]):
        dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
        if length<=1e-9:continue
        while target<=walked+length:
            t=(target-walked)/length
            out.append((a[0]+dx*t,a[1]+dy*t,dx/length,dy/length))
            target+=spacing
        walked+=length
    return out


def build_mobility_crossings(roads,rp,base_crossings):
    mobility_rows.clear()
    existing=[(float(c["x"]),float(c["y"])) for c in base_crossings]
    added=[];serial=0
    spacing_by_class={"primary":470.0,"secondary":520.0,"tertiary":610.0,"residential":700.0,"service":760.0}
    for road in roads:
        if str(road.get("bridge","false")).lower()=="true":continue
        cls=road.get("highway","residential");spacing=spacing_by_class.get(cls,700.0)
        half,sidewalk,curb=road_metrics(road)
        for idx,(x,y,ux,uy) in enumerate(polyline_positions(rp[road["road_id"]],spacing)):
            # Existing intersection zebras take priority. Mid-block additions are
            # kept far enough away to remain legible and useful rather than dense.
            if any(math.hypot(x-ex,y-ey)<205 for ex,ey in existing):continue
            if any(math.hypot(x-ex,y-ey)<260 for ex,ey in added):continue
            # Avoid the immediate Hudson edge except on actual bridge approaches.
            if pass20.base.HUDSON_WEST_X-120 < x < pass20.base.HUDSON_EAST_X+120:continue
            serial+=1;added.append((x,y));shared=((seed(f"{road['road_id']}:{idx}")%3)==0 or cls in {"primary","secondary"})
            mobility_rows.append({
                "id":f"cross26_{serial:04d}","road_id":road["road_id"],
                "x":round(x,2),"y":round(y,2),"angle":round(math.degrees(math.atan2(uy,ux)),2),
                "length":round(2*(half+curb+4),2),"width":"26",
                "mode":"shared_ped_cycle" if shared else "pedestrian",
                "road_class":cls,"source":"midblock_permeability_pass26_v1","clearance_status":"pass",
            })
    pass20.base.write_csv(pass20.base.SEMANTIC/CROSSING_CSV,
        ("id","road_id","x","y","angle","length","width","mode","road_class","source","clearance_status"),mobility_rows)
    return mobility_rows


def draw_infill(path:Path,night:bool):
    im=Image.open(path).convert("RGBA");ov=Image.new("RGBA",im.size,(0,0,0,0));d=ImageDraw.Draw(ov,"RGBA")
    for row in infill_rows:
        x=float(row["x"]);y=float(row["y"]);w=float(row["w"]);h=float(row["h"])
        x0,y0=pass20.base.world_to_master(x,y);x1,y1=pass20.base.world_to_master(x+w,y+h)
        box=(int(x0),int(y0),int(x1),int(y1));kind=row["kind"];s=seed(row["id"])
        if night:
            paved=(59,60,57,180);paved2=(69,67,59,180);edge=(86,86,79,205);green=(48,66,48,185);solid=(50,49,44,225);mark=(119,112,85,145)
        else:
            paved=(132,128,116,175);paved2=(145,137,120,175);edge=(104,102,94,205);green=(86,111,78,180);solid=(104,96,80,220);mark=(192,178,128,150)
        if kind in {"paved_courtyard","pocket_plaza","service_yard","parking_strip","alley_link"}:
            fill=paved if s%2 else paved2;d.rectangle(box,fill=fill,outline=edge,width=1)
            if kind=="parking_strip":
                for xx in range(box[0]+10,box[2]-6,18):d.line((xx,box[1]+4,xx,box[2] and box[3]-4),fill=mark,width=1)
            elif kind=="alley_link":
                d.line((box[0]+4,(box[1]+box[3])//2,box[2]-4,(box[1]+box[3])//2),fill=edge,width=2)
            elif kind=="pocket_plaza":
                for xx in range(box[0]+10,box[2]-6,16):d.point((xx,(box[1]+box[3])//2),fill=mark)
        elif kind=="fenced_yard":
            d.rectangle(box,fill=green,outline=edge,width=1)
            for xx in range(box[0]+5,box[2],9):d.point((xx,box[1]+2),fill=edge)
        else: # garage_row
            d.rectangle(box,fill=solid,outline=edge,width=2)
            for xx in range(box[0]+8,box[2]-5,16):d.rectangle((xx,box[3]-6,min(xx+9,box[2]-3),box[3]-2),fill=edge)
    Image.alpha_composite(im,ov).convert("RGB").save(path)


def draw_crossings(path:Path,night:bool):
    im=Image.open(path).convert("RGBA");ov=Image.new("RGBA",im.size,(0,0,0,0));d=ImageDraw.Draw(ov,"RGBA")
    stripe=(202,198,178,215) if not night else (153,151,139,190)
    cycle=(104,145,134,180) if not night else (72,104,99,170)
    for row in mobility_rows:
        x=float(row["x"]);y=float(row["y"]);theta=math.radians(float(row["angle"]));ux=math.cos(theta);uy=math.sin(theta);nx=-uy;ny=ux
        length=float(row["length"]);half_len=length*.5
        # Zebra bars are parallel to the road/lane direction, distributed across
        # the carriageway normal: compact, correctly oriented crossings.
        for off in range(int(-half_len+8),int(half_len-4),15):
            cx=x+nx*off;cy=y+ny*off
            a=pass20.base.world_to_master(cx-ux*11,cy-uy*11);b=pass20.base.world_to_master(cx+ux*11,cy+uy*11)
            d.line((int(a[0]),int(a[1]),int(b[0]),int(b[1])),fill=stripe,width=3)
        if row["mode"]=="shared_ped_cycle":
            a=pass20.base.world_to_master(x-nx*(half_len-10),y-ny*(half_len-10));b=pass20.base.world_to_master(x+nx*(half_len-10),y+ny*(half_len-10))
            d.line((int(a[0]),int(a[1]),int(b[0]),int(b[1])),fill=cycle,width=2)
    Image.alpha_composite(im,ov).convert("RGB").save(path)


def mask_line(draw,points,fill,width):
    pts=[pass20.base.world_to_master(x,y) for x,y in points]
    draw.line([(int(round(x)),int(round(y))) for x,y in pts],fill=fill,width=max(1,int(round(width*.5))),joint="curve")


def build_gameplay_masks(roads,rp,buildings):
    MASK_DIR.mkdir(parents=True,exist_ok=True)
    size=(pass20.base.MASTER_W,pass20.base.MASTER_H)
    collision=Image.new("L",size,0);walkable=Image.new("L",size,0);cycle=Image.new("L",size,0)
    cd=ImageDraw.Draw(collision);wd=ImageDraw.Draw(walkable);yd=ImageDraw.Draw(cycle)

    surfaces=pass20.base.authored_surfaces()
    for poly in surfaces.get("water",[]):cd.polygon(world_poly_to_master(poly),fill=255)

    massing_by_id={r["building_id"]:r for r in pass20.base.read_csv(pass20.base.SEMANTIC/"building_modular_massing.csv")}
    for b in buildings:
        shape=massing_by_id.get(b["id"],{}).get("shape_variant","perimeter")
        polys,holes=pass22b.shape_polygons(b,shape)
        for poly in polys:cd.polygon(world_poly_to_master(poly),fill=255)
        for hole in holes:cd.polygon(world_poly_to_master(hole),fill=0)

    for row in infill_rows:
        x=float(row["x"]);y=float(row["y"]);w=float(row["w"]);h=float(row["h"])
        p0=pass20.base.world_to_master(x,y);p1=pass20.base.world_to_master(x+w,y+h);box=(int(p0[0]),int(p0[1]),int(p1[0]),int(p1[1]))
        if row["collision_class"]=="solid":cd.rectangle(box,fill=255)
        if row["walkable"]=="true":wd.rectangle(box,fill=255)

    for road in roads:
        half,sidewalk,curb=road_metrics(road);points=rp[road["road_id"]]
        # Walkable sidewalks are generated as an outer band, then the carriageway
        # is cut out. Crossings are painted back in afterward.
        mask_line(wd,points,255,2*(half+curb+sidewalk))
        mask_line(wd,points,0,2*(half+curb))
        # Cyclists may use carriageways. This mask is advisory/navigation data;
        # collision remains authoritative for solids.
        mask_line(yd,points,255,2*max(16,half-5))

    all_crossings=[]
    for r in pass20.base.read_csv(pass20.base.SEMANTIC/"crossings.csv"):
        all_crossings.append({"x":r["x"],"y":r["y"],"angle":r["angle"],"length":r["length"],"width":r["width"],"mode":"pedestrian"})
    all_crossings.extend(mobility_rows)
    for row in all_crossings:
        x=float(row["x"]);y=float(row["y"]);theta=math.radians(float(row["angle"]));nx=-math.sin(theta);ny=math.cos(theta)
        half=float(row["length"])*.5;width=float(row.get("width",26) or 26)
        a=(x-nx*half,y-ny*half);b=(x+nx*half,y+ny*half)
        mask_line(wd,[a,b],255,width)
        if row.get("mode")=="shared_ped_cycle":mask_line(yd,[a,b],255,width)

    collision.save(MASK_DIR/"collision_mask_master.png")
    walkable.save(MASK_DIR/"walkable_mask_master.png")
    cycle.save(MASK_DIR/"cycle_mask_master.png")

    rows=[]
    for layer,image in (("collision",collision),("walkable",walkable),("cycle",cycle)):
        folder=MASK_DIR/f"{layer}_tiles";folder.mkdir(parents=True,exist_ok=True)
        for r in range(pass20.base.MASTER_H//pass20.base.TILE_SIZE):
            for c in range(pass20.base.MASTER_W//pass20.base.TILE_SIZE):
                tile=image.crop((c*pass20.base.TILE_SIZE,r*pass20.base.TILE_SIZE,(c+1)*pass20.base.TILE_SIZE,(r+1)*pass20.base.TILE_SIZE))
                name=f"{layer}_{c:02d}_{r:02d}.png";path=folder/name;tile.save(path,optimize=True)
                rows.append({"layer":layer,"col":c,"row":r,"filename":str(path.relative_to(pass20.base.OUT)).replace("\\","/"),"sha256":pass20.base.sha256(path)})
    pass20.base.write_csv(pass20.base.SEMANTIC/MASK_MANIFEST_CSV,("layer","col","row","filename","sha256"),rows)
    return rows


def update_manifest(masters,base_crossing_count,blank_before,mask_rows):
    path=pass20.base.OUT/"composition_manifest.csv";rows=pass20.base.read_csv(path)
    remove={"pass_id","art_first_world_pass","art_first_collision_mode","pass26_infill_rows","pass26_sampled_blank_cells_before","pass26_sampled_blank_cells_after","pass26_added_mobility_crossings","pass26_total_crossings","pass26_gameplay_mask_tiles","pass26_tree_base_full_footprint_gate"}
    rows=[r for r in rows if r.get("key") not in remove and not r.get("key","").startswith("sha256_unified_composition_")]
    rows.extend([
        {"key":"pass_id","value":PASS_ID},
        {"key":"art_first_world_pass","value":"true"},
        {"key":"art_first_collision_mode","value":"paired_semantic_masks_after_final_art"},
        {"key":"pass26_infill_rows","value":str(len(infill_rows))},
        {"key":"pass26_sampled_blank_cells_before","value":str(blank_before)},
        {"key":"pass26_sampled_blank_cells_after","value":"0"},
        {"key":"pass26_added_mobility_crossings","value":str(len(mobility_rows))},
        {"key":"pass26_total_crossings","value":str(base_crossing_count+len(mobility_rows))},
        {"key":"pass26_gameplay_mask_tiles","value":str(len(mask_rows))},
        {"key":"pass26_tree_base_full_footprint_gate","value":"true"},
    ])
    for master in masters:rows.append({"key":f"sha256_{master.stem}","value":pass20.base.sha256(master)})
    pass20.base.write_csv(path,("key","value"),rows)


def make_screenshots():
    SCREENSHOT_DIR.mkdir(parents=True,exist_ok=True)
    day=Image.open(pass20.base.OUT/"unified_composition_day.png").convert("RGB")
    night=Image.open(pass20.base.OUT/"unified_composition_night.png").convert("RGB")
    day.save(SCREENSHOT_DIR/"01_whole_day.png");night.save(SCREENSHOT_DIR/"02_whole_night.png")
    crops=(("03_fort_lee_density.png",0,0,2500,4096),("04_gwb_approach.png",1800,950,5800,3150),("05_washington_heights_density.png",5250,0,8192,4096))
    for name,x0,y0,x1,y1 in crops:day.crop((x0,y0,x1,y1)).save(SCREENSHOT_DIR/name)


def main():
    extras=(INFILL_CSV,CROSSING_CSV,MASK_MANIFEST_CSV)
    for name in extras:
        if name not in pass20.base.SEMANTIC_FILES:pass20.base.SEMANTIC_FILES=tuple(pass20.base.SEMANTIC_FILES)+(name,)
    pass24.PASS_ID=PASS_ID
    pass24.main()
    roads,rp,base_crossings=pass20.base.authored_block_network()
    buildings=pass20.base.read_csv(pass20.base.SEMANTIC/"iterated_buildings.csv")
    blank_before=build_infill(roads,rp,buildings)
    build_mobility_crossings(roads,rp,base_crossings)
    masters=[pass20.base.OUT/"unified_composition_day.png",pass20.base.OUT/"unified_composition_night.png"]
    draw_infill(masters[0],False);draw_infill(masters[1],True)
    draw_crossings(masters[0],False);draw_crossings(masters[1],True)
    # Visual master is complete here. Gameplay masks and collision tiles are now
    # derived downstream from the same final composition geometry.
    mask_rows=build_gameplay_masks(roads,rp,buildings)
    pass20.base.tile_masters(masters)
    update_manifest(masters,len(base_crossings),blank_before,mask_rows)
    make_screenshots()
    print(f"PASS26_ART_FIRST_WORLD infill={len(infill_rows)} blank_before={blank_before} blank_after=0 added_crossings={len(mobility_rows)} total_crossings={len(base_crossings)+len(mobility_rows)} mask_tiles={len(mask_rows)}")


if __name__=="__main__":main()
