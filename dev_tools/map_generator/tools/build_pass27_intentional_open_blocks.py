from __future__ import annotations

"""Pass 27: replace accidental-looking blank/built pads with intentional open blocks.

Pass 26 RC4 remains the protected art-first base. This pass selects six complete
road-bounded block interiors (three green-space blocks and three car parks),
clears their previous building/infill art, redraws them as designed destinations,
and then rewrites gameplay masks/tiles from the same final visual decision.
Roads, bridge geometry, Hudson geometry, crossings and building scale contracts
outside the selected blocks are unchanged.
"""

import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass20_streetwall as pass20
import build_pass26_art_first_world as p26
import build_pass26_art_first_world_v4 as rc4

PASS_ID = "pass_27_intentional_open_blocks_rc1"
OPEN_BLOCK_CSV = "intentional_open_blocks_pass27.csv"
SUPPRESSED_BUILDINGS_CSV = "suppressed_buildings_pass27.csv"
SCREENSHOT_DIR = Path(__file__).resolve().parents[3] / "qa" / "pass27_screenshots"
TARGET_BLOCKS = 6


def centre(row):
    return float(row["x"]) + float(row["w"]) * .5, float(row["y"]) + float(row["h"]) * .5


def world_centre_to_master(row):
    x, y = centre(row)
    return pass20.base.world_to_master(x, y)


def inside_master(x, y, block, pad=0.0):
    bx=float(block["x"]);by=float(block["y"]);bw=float(block["w"]);bh=float(block["h"])
    return bx+pad <= x <= bx+bw-pad and by+pad <= y <= by+bh-pad


def rect_overlap(a, b, pad=0.0):
    ax,ay,aw,ah=a;bx,by,bw,bh=b
    return not (ax+aw+pad <= bx or bx+bw+pad <= ax or ay+ah+pad <= by or by+bh+pad <= ay)


def select_open_blocks():
    blocks = pass20.base.read_csv(pass20.base.SEMANTIC / "urban_blocks.csv")
    buildings = pass20.base.read_csv(pass20.base.SEMANTIC / "iterated_buildings.csv")
    entrances = pass20.base.read_csv(pass20.base.SEMANTIC / "building_entrances.csv")

    master_buildings=[]
    for b in buildings:
        mx,my=world_centre_to_master(b)
        master_buildings.append((b,mx,my))
    entrance_pts=[(float(r["x"]),float(r["y"])) for r in entrances if r.get("x") and r.get("y")]

    west=pass20.base.HUDSON_WEST_X*.5
    east=pass20.base.HUDSON_EAST_X*.5
    by_district=defaultdict(list)
    for block in blocks:
        x=float(block["x"]);y=float(block["y"]);w=float(block["w"]);h=float(block["h"])
        if w < 175 or h < 145 or w*h < 31000:
            continue
        if x+w <= west-18:
            district="fort_lee"
        elif x >= east+18:
            district="washington_heights"
        else:
            continue
        cx=x+w*.5;cy=y+h*.5
        # Preserve the immediate bridge-approach composition as a dense protected
        # corridor; open blocks belong to the surrounding neighborhoods.
        if 1780 < cy < 2260:
            continue
        if any(inside_master(ex,ey,block,pad=10) for ex,ey in entrance_pts):
            continue
        suppressed=[b for b,bx,by in master_buildings if inside_master(bx,by,block,pad=5)]
        if not suppressed:
            continue
        if any(str(b.get("building_kind","")) == "church_landmark" for b in suppressed):
            continue
        # Favor substantial blocks that actually remove repetitive massing, while
        # keeping an edge penalty so open space does not become a boundary artifact.
        edge=min(cx,pass20.base.MASTER_W-cx,cy,pass20.base.MASTER_H-cy)
        score=w*h + len(suppressed)*24000 + min(500,edge)*40
        by_district[district].append((score,block,suppressed))

    selected=[]
    for district in ("fort_lee","washington_heights"):
        candidates=sorted(by_district[district],key=lambda item:item[0],reverse=True)
        chosen=[]
        for spacing in (520,360,220,0):
            for score,block,suppressed in candidates:
                if any(block is c[1] for c in chosen):
                    continue
                cx=float(block["x"])+float(block["w"])*.5;cy=float(block["y"])+float(block["h"])*.5
                if spacing and any(math.hypot(cx-(float(c[1]["x"])+float(c[1]["w"])*.5),
                                              cy-(float(c[1]["y"])+float(c[1]["h"])*.5)) < spacing for c in chosen):
                    continue
                chosen.append((score,block,suppressed))
                if len(chosen) == 3:
                    break
            if len(chosen) == 3:
                break
        if len(chosen) < 3:
            raise RuntimeError(f"Pass 27 could not find three safe intentional open blocks in {district}")
        selected.extend((district,block,suppressed) for _,block,suppressed in chosen[:3])

    rows=[];suppressed_rows=[]
    use_plan={
        "fort_lee":("green_space","car_park","green_space"),
        "washington_heights":("car_park","green_space","car_park"),
    }
    for district in ("fort_lee","washington_heights"):
        group=[item for item in selected if item[0]==district]
        group.sort(key=lambda item:float(item[1]["y"])+float(item[1]["h"])*.5)
        for index,(district,block,suppressed) in enumerate(group):
            use=use_plan[district][index]
            rows.append({
                "block_id":block.get("block_id",f"pass27_{district}_{index+1}"),
                "use":use,"district":district,
                "x":round(float(block["x"]),2),"y":round(float(block["y"]),2),
                "w":round(float(block["w"]),2),"h":round(float(block["h"]),2),
                "coordinate_space":"master_8192x4096",
                "walkable":"true",
                "cycle_policy":"through_paths" if use=="green_space" else "shared_surface",
                "design_rule":"whole_road_bounded_block_intentional_open_use_pass27",
            })
            for building in suppressed:
                suppressed_rows.append({
                    "block_id":rows[-1]["block_id"],"building_id":building["id"],
                    "building_kind":building.get("building_kind",""),
                    "override_rule":"pass27_open_block_supersedes_prior_building_art_and_collision",
                })

    if len(rows) != TARGET_BLOCKS:
        raise RuntimeError(f"Pass 27 expected {TARGET_BLOCKS} selected blocks, got {len(rows)}")
    pass20.base.write_csv(pass20.base.SEMANTIC/OPEN_BLOCK_CSV,
        ("block_id","use","district","x","y","w","h","coordinate_space","walkable","cycle_policy","design_rule"),rows)
    pass20.base.write_csv(pass20.base.SEMANTIC/SUPPRESSED_BUILDINGS_CSV,
        ("block_id","building_id","building_kind","override_rule"),suppressed_rows)
    return rows,suppressed_rows


def block_inner(row, inset=5):
    x=int(round(float(row["x"])));y=int(round(float(row["y"])))
    w=int(round(float(row["w"])));h=int(round(float(row["h"])))
    return x+inset,y+inset,max(4,w-2*inset),max(4,h-2*inset)


def block_features(row):
    x,y,w,h=block_inner(row,7);s=p26.seed("pass27:"+str(row["block_id"]));features=[]
    if row["use"]=="green_space":
        path_w=12
        features.append(("cycle_path",(x+6,y+h//2-path_w//2,x+w-6,y+h//2+path_w//2)))
        features.append(("cycle_path",(x+w//2-path_w//2,y+6,x+w//2+path_w//2,y+h-6)))
        # Tree positions are fixed-size and remain comfortably inside the block,
        # never on surrounding roads/curbs.
        margin=20;pitch=38
        for yy in range(y+margin,y+h-margin+1,pitch):
            for xx in range(x+margin,x+w-margin+1,pitch):
                if abs(xx-(x+w//2))<22 or abs(yy-(y+h//2))<22:
                    continue
                q=p26.seed(f"tree27:{row['block_id']}:{xx}:{yy}")
                if q%3==0:
                    features.append(("tree",(xx,yy,4)))
    else:
        horizontal=w>=h
        if horizontal:
            aisle=(x+8,y+h//2-13,x+w-8,y+h//2+13)
            features.append(("cycle_path",aisle))
            pitch=28
            for xx in range(x+18,x+w-18,pitch):
                for side in (-1,1):
                    cy=y+h//2 + side*30
                    q=p26.seed(f"car27:{row['block_id']}:{xx}:{side}")
                    if q%4!=0:
                        features.append(("parked_car",(xx-7,cy-4,xx+7,cy+4)))
        else:
            aisle=(x+w//2-13,y+8,x+w//2+13,y+h-8)
            features.append(("cycle_path",aisle))
            pitch=28
            for yy in range(y+18,y+h-18,pitch):
                for side in (-1,1):
                    cx=x+w//2 + side*30
                    q=p26.seed(f"car27:{row['block_id']}:{yy}:{side}")
                    if q%4!=0:
                        features.append(("parked_car",(cx-4,yy-7,cx+4,yy+7)))
    return (x,y,w,h),features


def draw_open_blocks(path:Path, rows, night:bool):
    im=Image.open(path).convert("RGB");d=ImageDraw.Draw(im,"RGB")
    if night:
        curb=(78,79,74);grass=(47,66,48);grass2=(57,76,53);path=(84,82,74);asphalt=(52,55,54);stripe=(142,137,118);tree=(45,76,51);tree2=(63,91,58);car=(81,83,79);lamp=(196,156,86)
    else:
        curb=(121,119,108);grass=(79,107,73);grass2=(91,119,80);path=(142,137,123);asphalt=(78,82,80);stripe=(205,198,170);tree=(52,91,58);tree2=(76,112,69);car=(117,119,112);lamp=(224,184,104)
    for row in rows:
        (x,y,w,h),features=block_features(row);box=(x,y,x+w,y+h)
        # Fully opaque base erases the previous building pad. A two-step curb/base
        # makes the new use visibly intentional rather than an unexplained blank.
        d.rectangle((x-3,y-3,x+w+3,y+h+3),fill=curb)
        if row["use"]=="green_space":
            d.rectangle(box,fill=grass)
            for yy in range(y+8,y+h-6,16):
                d.line((x+3,yy,x+w-3,yy),fill=grass2,width=1)
            # Cross-shaped pedestrian/cycle paths create useful permeability.
            for kind,geom in features:
                if kind=="cycle_path":d.rectangle(geom,fill=path)
            # benches and lamps sit beside, not in, the through-path.
            for off in (-36,36):
                bx=x+w//2+off;by=y+h//2+22
                d.rectangle((bx-8,by-2,bx+8,by+2),fill=curb)
            for lx,ly in ((x+14,y+14),(x+w-14,y+14),(x+14,y+h-14),(x+w-14,y+h-14)):
                d.ellipse((lx-3,ly-3,lx+3,ly+3),fill=lamp)
            for kind,geom in features:
                if kind=="tree":
                    tx,ty,r=geom
                    d.ellipse((tx-r-2,ty-r-1,tx+r+2,ty+r+3),fill=(39,53,40))
                    d.ellipse((tx-r,ty-r,tx+r,ty+r),fill=tree)
                    d.ellipse((tx-r+1,ty-r+1,tx+r-2,ty+r-2),fill=tree2)
        else:
            d.rectangle(box,fill=asphalt)
            horizontal=w>=h
            if horizontal:
                mid=y+h//2
                d.rectangle((x+5,mid-14,x+w-5,mid+14),fill=(65,68,66) if not night else (45,48,47))
                for xx in range(x+10,x+w-8,28):
                    d.line((xx,y+5,xx,mid-17),fill=stripe,width=1)
                    d.line((xx,mid+17,xx,y+h-5),fill=stripe,width=1)
            else:
                mid=x+w//2
                d.rectangle((mid-14,y+5,mid+14,y+h-5),fill=(65,68,66) if not night else (45,48,47))
                for yy in range(y+10,y+h-8,28):
                    d.line((x+5,yy,mid-17,yy),fill=stripe,width=1)
                    d.line((mid+17,yy,x+w-5,yy),fill=stripe,width=1)
            for kind,geom in features:
                if kind=="parked_car":
                    x0,y0,x1,y1=geom
                    d.rectangle((x0+2,y0+2,x1+2,y1+2),fill=(35,37,36))
                    d.rectangle(geom,fill=car,outline=curb,width=1)
            for lx,ly in ((x+12,y+12),(x+w-12,y+12),(x+12,y+h-12),(x+w-12,y+h-12)):
                d.ellipse((lx-2,ly-2,lx+2,ly+2),fill=lamp)
    im.save(path)


def filter_prior_infill(rows):
    path=pass20.base.SEMANTIC/p26.INFILL_CSV
    infill=pass20.base.read_csv(path)
    kept=[]
    for item in infill:
        mx,my=pass20.base.world_to_master(float(item["x"])+float(item["w"])*.5,
                                          float(item["y"])+float(item["h"])*.5)
        if any(inside_master(mx,my,row,pad=2) for row in rows):
            continue
        kept.append(item)
    fields=tuple(infill[0].keys()) if infill else ("id",)
    pass20.base.write_csv(path,fields,kept)
    return len(infill)-len(kept)


def rewrite_masks(rows):
    masks={}
    for layer in ("collision","solid","walkable","cycle"):
        path=p26.MASK_DIR/f"{layer}_mask_master.png"
        masks[layer]=Image.open(path).convert("L")
    draws={name:ImageDraw.Draw(image) for name,image in masks.items()}
    obstacle_count=0
    for row in rows:
        (x,y,w,h),features=block_features(row);box=(x,y,x+w,y+h)
        # Pass-27 semantics supersede prior building/infill solids inside the
        # selected block. The entire designed open use is walkable.
        draws["collision"].rectangle(box,fill=0)
        draws["solid"].rectangle(box,fill=0)
        draws["walkable"].rectangle(box,fill=255)
        draws["cycle"].rectangle(box,fill=0)
        for kind,geom in features:
            if kind=="cycle_path":
                draws["cycle"].rectangle(geom,fill=255)
            elif kind=="parked_car":
                draws["collision"].rectangle(geom,fill=255);draws["solid"].rectangle(geom,fill=255);obstacle_count+=1
            elif kind=="tree":
                tx,ty,r=geom
                draws["collision"].ellipse((tx-r,ty-r,tx+r,ty+r),fill=255)
                draws["solid"].ellipse((tx-r,ty-r,tx+r,ty+r),fill=255);obstacle_count+=1
        if row["use"]=="car_park":
            # Parking aisles are intentionally cycle-accessible/shared surface.
            draws["cycle"].rectangle(box,fill=255)
            for kind,geom in features:
                if kind=="parked_car":
                    draws["cycle"].rectangle(geom,fill=0)

    manifest=[]
    for layer,image in masks.items():
        master=p26.MASK_DIR/f"{layer}_mask_master.png";image.save(master,optimize=True)
        folder=p26.MASK_DIR/f"{layer}_tiles";folder.mkdir(parents=True,exist_ok=True)
        for old in folder.glob("*.png"):old.unlink()
        for rr in range(pass20.base.MASTER_H//pass20.base.TILE_SIZE):
            for cc in range(pass20.base.MASTER_W//pass20.base.TILE_SIZE):
                tile=image.crop((cc*pass20.base.TILE_SIZE,rr*pass20.base.TILE_SIZE,
                                 (cc+1)*pass20.base.TILE_SIZE,(rr+1)*pass20.base.TILE_SIZE))
                name=f"{layer}_{cc:02d}_{rr:02d}.png";path=folder/name;tile.save(path,optimize=True)
                manifest.append({"layer":layer,"col":cc,"row":rr,
                    "filename":str(path.relative_to(pass20.base.OUT)).replace("\\","/"),
                    "sha256":pass20.base.sha256(path)})
    pass20.base.write_csv(pass20.base.SEMANTIC/p26.MASK_MANIFEST_CSV,
        ("layer","col","row","filename","sha256"),manifest)
    return manifest,obstacle_count


def update_manifest(rows,suppressed,removed_infill,mask_rows,masters,obstacle_count):
    path=pass20.base.OUT/"composition_manifest.csv";manifest=pass20.base.read_csv(path)
    remove={
        "pass_id","pass27_intentional_open_blocks","pass27_open_blocks","pass27_green_blocks",
        "pass27_car_park_blocks","pass27_suppressed_buildings","pass27_removed_infill_rows",
        "pass27_open_block_obstacles","pass27_blank_block_policy","pass27_mask_consistency",
    }
    manifest=[r for r in manifest if r.get("key") not in remove and not r.get("key","").startswith("sha256_unified_composition_")]
    counts=Counter(r["use"] for r in rows)
    manifest.extend([
        {"key":"pass_id","value":PASS_ID},
        {"key":"pass27_intentional_open_blocks","value":"true"},
        {"key":"pass27_open_blocks","value":str(len(rows))},
        {"key":"pass27_green_blocks","value":str(counts["green_space"])},
        {"key":"pass27_car_park_blocks","value":str(counts["car_park"])},
        {"key":"pass27_suppressed_buildings","value":str(len(suppressed))},
        {"key":"pass27_removed_infill_rows","value":str(removed_infill)},
        {"key":"pass27_open_block_obstacles","value":str(obstacle_count)},
        {"key":"pass27_blank_block_policy","value":"classified_green_or_car_park_whole_blocks_only"},
        {"key":"pass27_mask_consistency","value":"final_open_block_art_and_gameplay_masks_paired"},
        {"key":"pass26_gameplay_mask_tiles","value":str(len(mask_rows))},
    ])
    for master in masters:
        manifest.append({"key":f"sha256_{master.stem}","value":pass20.base.sha256(master)})
    pass20.base.write_csv(path,("key","value"),manifest)


def make_review_crops(rows):
    SCREENSHOT_DIR.mkdir(parents=True,exist_ok=True)
    day=Image.open(pass20.base.OUT/"unified_composition_day.png").convert("RGB")
    day.save(SCREENSHOT_DIR/"00_whole_day.png")
    for index,row in enumerate(rows,1):
        x=float(row["x"]);y=float(row["y"]);w=float(row["w"]);h=float(row["h"]);m=70
        crop=(max(0,int(x-m)),max(0,int(y-m)),min(day.width,int(x+w+m)),min(day.height,int(y+h+m)))
        day.crop(crop).save(SCREENSHOT_DIR/f"{index:02d}_{row['district']}_{row['use']}.png")


def main():
    rc4.main()
    rows,suppressed=select_open_blocks()
    masters=[pass20.base.OUT/"unified_composition_day.png",pass20.base.OUT/"unified_composition_night.png"]
    draw_open_blocks(masters[0],rows,False)
    draw_open_blocks(masters[1],rows,True)
    removed_infill=filter_prior_infill(rows)
    mask_rows,obstacle_count=rewrite_masks(rows)
    # Re-tile the final day/night composition so review/runtime chunks correspond
    # to the same Pass-27 visual authority.
    pass20.base.tile_masters(masters)
    update_manifest(rows,suppressed,removed_infill,mask_rows,masters,obstacle_count)
    make_review_crops(rows)
    counts=Counter(r["use"] for r in rows)
    districts=Counter(r["district"] for r in rows)
    print(f"PASS27_OPEN_BLOCKS total={len(rows)} uses={dict(counts)} districts={dict(districts)} "
          f"suppressed_buildings={len(suppressed)} removed_infill={removed_infill} obstacles={obstacle_count} "
          f"mask_tiles={len(mask_rows)}")


if __name__=="__main__":
    main()
