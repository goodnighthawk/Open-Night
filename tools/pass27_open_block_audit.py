from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

from PIL import Image, ImageStat

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"dev_tools"/"map_generator"/"profiles"/"gwb_gameplay"/"unified_composition"
SEM=OUT/"semantic"
MASK=OUT/"gameplay_masks"


def read_csv(path):
    with path.open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


def inside(x,y,row,pad=0):
    bx=float(row["x"]);by=float(row["y"]);bw=float(row["w"]);bh=float(row["h"])
    return bx+pad<=x<=bx+bw-pad and by+pad<=y<=by+bh-pad


def overlap(a,b):
    ax,ay,aw,ah=map(float,(a["x"],a["y"],a["w"],a["h"]));bx,by,bw,bh=map(float,(b["x"],b["y"],b["w"],b["h"]))
    return not (ax+aw<=bx or bx+bw<=ax or ay+ah<=by or by+bh<=ay)


def ratio_nonzero(image,row,inset=8):
    x=int(float(row["x"]))+inset;y=int(float(row["y"]))+inset
    w=max(1,int(float(row["w"]))-2*inset);h=max(1,int(float(row["h"]))-2*inset)
    crop=image.crop((x,y,x+w,y+h))
    hist=crop.histogram();nonzero=sum(hist[1:]);return nonzero/max(1,crop.width*crop.height)


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--strict",action="store_true");args=parser.parse_args()
    problems=[]
    rows=read_csv(SEM/"intentional_open_blocks_pass27.csv")
    suppressed=read_csv(SEM/"suppressed_buildings_pass27.csv")
    manifest={r["key"]:r["value"] for r in read_csv(OUT/"composition_manifest.csv")}
    if len(rows)!=6:problems.append(f"expected 6 open blocks, got {len(rows)}")
    uses=Counter(r["use"] for r in rows);districts=Counter(r["district"] for r in rows)
    if uses!={"green_space":3,"car_park":3}:problems.append(f"use balance wrong: {dict(uses)}")
    if districts!={"fort_lee":3,"washington_heights":3}:problems.append(f"district balance wrong: {dict(districts)}")
    for i,a in enumerate(rows):
        for b in rows[i+1:]:
            if overlap(a,b):problems.append(f"open blocks overlap: {a['block_id']} / {b['block_id']}")
    by_block=Counter(r["block_id"] for r in suppressed)
    for row in rows:
        if by_block[row["block_id"]]<1:problems.append(f"{row['block_id']} did not actually replace a prior building")

    entrances=read_csv(SEM/"building_entrances.csv")
    for e in entrances:
        ex=float(e["x"]);ey=float(e["y"])
        for row in rows:
            if inside(ex,ey,row,pad=8):problems.append(f"{row['block_id']} erased interior entrance {e.get('interior_id','?')}")

    infill=read_csv(SEM/"urban_infill_pass26.csv")
    for item in infill:
        # Pass-26 infill is in world coordinates; master is x*.5,(y-2048)*.5.
        mx=(float(item["x"])+float(item["w"])*.5)*.5
        my=(float(item["y"])+float(item["h"])*.5-2048.0)*.5
        for row in rows:
            if inside(mx,my,row,pad=2):problems.append(f"legacy infill remains inside {row['block_id']}: {item['id']}")

    collision=Image.open(MASK/"collision_mask_master.png").convert("L")
    solid=Image.open(MASK/"solid_mask_master.png").convert("L")
    walk=Image.open(MASK/"walkable_mask_master.png").convert("L")
    cycle=Image.open(MASK/"cycle_mask_master.png").convert("L")
    day=Image.open(OUT/"unified_composition_day.png").convert("RGB")
    for row in rows:
        c=ratio_nonzero(collision,row);s=ratio_nonzero(solid,row);w=ratio_nonzero(walk,row);cy=ratio_nonzero(cycle,row)
        if c>0.22 or s>0.22:problems.append(f"{row['block_id']} remains too solid collision={c:.3f} solid={s:.3f}")
        if w<0.88:problems.append(f"{row['block_id']} is not predominantly walkable: {w:.3f}")
        if row["use"]=="green_space" and cy<0.07:problems.append(f"{row['block_id']} lacks through-cycle/path permeability: {cy:.3f}")
        if row["use"]=="car_park" and cy<0.72:problems.append(f"{row['block_id']} car park is not shared-surface cycleable: {cy:.3f}")
        x=int(float(row["x"]));y=int(float(row["y"]));ww=int(float(row["w"]));hh=int(float(row["h"]))
        crop=day.crop((x+6,y+6,x+ww-6,y+hh-6))
        stat=ImageStat.Stat(crop)
        if sum(stat.var)/3.0<45:problems.append(f"{row['block_id']} artwork is too visually flat")

    protected={"selected_gameplay_roads":"38","road_segments":"157","angled_road_segments":"96","t_junctions":"23","non_bridge_hudson_violations":"0"}
    for k,v in protected.items():
        if manifest.get(k)!=v:problems.append(f"protected geometry changed: {k}={manifest.get(k)} expected {v}")
    expected={
        "pass_id":"pass_27_intentional_open_blocks_rc1",
        "pass27_intentional_open_blocks":"true",
        "pass27_open_blocks":"6",
        "pass27_green_blocks":"3",
        "pass27_car_park_blocks":"3",
        "pass27_blank_block_policy":"classified_green_or_car_park_whole_blocks_only",
        "pass27_mask_consistency":"final_open_block_art_and_gameplay_masks_paired",
        "pass26_gameplay_mask_tiles":"128",
    }
    for k,v in expected.items():
        if manifest.get(k)!=v:problems.append(f"manifest {k}={manifest.get(k)} expected {v}")

    print(f"PASS27_OPEN_BLOCK_AUDIT blocks={len(rows)} uses={dict(uses)} districts={dict(districts)} suppressed={len(suppressed)}")
    if problems:
        print("PASS27_OPEN_BLOCK_GATE=FAIL")
        for p in problems[:30]:print(" - "+p)
        return 1 if args.strict else 0
    print("PASS27_OPEN_BLOCK_GATE=PASS")
    return 0


if __name__=="__main__":raise SystemExit(main())
