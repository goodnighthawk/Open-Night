from __future__ import annotations

"""Pass 29 RC2 art refinement: deterministic large church landmarks.

The doubled-world generator already supports merged apartment/church lots, but a
pure hash selection can produce too few churches in a particular deterministic
layout. This refinement also widens the protected-core exclusion used during lot
placement so no extension footprint can straddle the old-city boundary. Each
land-side extension receives recognizable large church landmarks while the
Pass-28 core remains untouched and component scale is unchanged.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageDraw

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))

import build_pass29_double_world as p29
import build_pass29_double_world_v2 as rc1

TARGET_PER_DISTRICT=2
ELIGIBLE_DISTRICTS=("new_jersey_extension","upper_manhattan_extension")
CORE_BUILDING_EXCLUSION=380.0


def read_rows(path:Path):
    with path.open("r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))


def church_overlay(im:Image.Image,row,night:bool):
    """Add fixed-pixel nave/transept/tower language to an existing merged roof."""
    P=p29.palette(night);d=ImageDraw.Draw(im,"RGB")
    x=int(float(row["x"]));y=int(float(row["y"]));w=int(float(row["w"]));h=int(float(row["h"]))
    cx=x+w//2;cy=y+h//2
    nave=max(18,min(34,w//7));transept=max(34,min(64,w//5));half_t=max(12,min(24,h//10))
    line=P["church2"];edge=P["edge"]
    # Fixed-width architectural accents preserve the same window/wall-scale
    # language even when the parent footprint spans several former lots.
    d.rounded_rectangle((cx-nave,y+12,cx+nave,y+h-12),radius=5,outline=edge,width=5)
    d.rounded_rectangle((cx-nave+3,y+15,cx+nave-3,y+h-15),radius=4,outline=line,width=2)
    d.rounded_rectangle((cx-transept,cy-half_t,cx+transept,cy+half_t),radius=4,outline=edge,width=4)
    d.rounded_rectangle((cx-transept+3,cy-half_t+3,cx+transept-3,cy+half_t-3),radius=3,outline=line,width=2)
    # Bell/clock tower and small apse are intentionally fixed-size modules.
    tower=18
    d.rectangle((cx-tower,cy-tower,cx+tower,cy+tower),fill=P["church2"],outline=edge,width=2)
    d.rectangle((cx-10,cy-10,cx+10,cy+10),fill=P["church"],outline=edge,width=2)
    r=13
    d.ellipse((cx-r,y+h-34-r,cx+r,y+h-34+r),outline=line,width=3)
    # Small repeated roof bays give the long nave human-scale detail rather than
    # making the whole landmark look like one enlarged sprite.
    for yy in range(y+38,y+h-46,34):
        d.line((cx-nave+7,yy,cx+nave-7,yy),fill=line,width=2)


def promote_churches(rows):
    churches=[r for r in rows if r.get("kind")=="church"]
    counts=defaultdict(int)
    for row in churches:counts[row.get("district","")]+=1
    selected=[]
    for district in ELIGIBLE_DISTRICTS:
        need=max(0,TARGET_PER_DISTRICT-counts[district])
        candidates=[r for r in rows if r.get("district")==district and r.get("kind")=="merged_apartment" and int(float(r.get("merged_lot_count",1)))>=2]
        candidates.sort(key=lambda r:float(r["w"])*float(r["h"]),reverse=True)
        for row in candidates[:need]:
            row["kind"]="church";selected.append(row);counts[district]+=1
    # Absolute fallback: at least four extension churches even if one district's
    # merged candidates were unusually sparse.
    if sum(counts.values())<4:
        candidates=[r for r in rows if r.get("kind")=="merged_apartment" and r not in selected]
        candidates.sort(key=lambda r:float(r["w"])*float(r["h"]),reverse=True)
        for row in candidates[:4-sum(counts.values())]:row["kind"]="church";selected.append(row)
    return selected


def update_manifest(rows,selected):
    path=p29.OUT/"composition_manifest.csv";manifest=p29.pass20.base.read_csv(path)
    remove={"pass_id","pass29_church_landmarks","pass29_church_landmark_refinement","pass29_church_landmark_rule",
            "pass29_core_building_exclusion_px"}
    manifest=[r for r in manifest if r.get("key") not in remove and not r.get("key","").startswith("sha256_unified_composition_")]
    church_count=sum(r.get("kind")=="church" for r in rows)
    manifest.extend([
        {"key":"pass_id","value":"pass_29_double_world_rc2"},
        {"key":"pass29_church_landmarks","value":str(church_count)},
        {"key":"pass29_church_landmark_refinement","value":"true"},
        {"key":"pass29_church_landmark_rule","value":"deterministic_large_merged_footprints_two_per_land_side_v1"},
        {"key":"pass29_core_building_exclusion_px","value":f"{CORE_BUILDING_EXCLUSION:g}"},
    ])
    for mode in ("day","night"):
        path_mode=p29.OUT/f"unified_composition_{mode}.png"
        manifest.append({"key":f"sha256_{path_mode.stem}","value":p29.pass20.base.sha256(path_mode)})
    p29.pass20.base.write_csv(path,("key","value"),manifest)


def main():
    # The base lot placer checked only a candidate centre with an 80 px margin.
    # Its largest merged footprints can extend ~310 px from the centre, so five
    # legal-looking lots crossed into the protected core in RC1. Expand only the
    # lot-placement core predicate; the core art itself is still pasted unchanged.
    original_core_contains=p29.core_contains
    def protected_core_contains(x:float,y:float,margin:float=0.0)->bool:
        return original_core_contains(x,y,max(float(margin),CORE_BUILDING_EXCLUSION))
    p29.core_contains=protected_core_contains
    rc1.main()

    path=p29.SEMANTIC/p29.EXTENSION_BUILDINGS
    rows=read_rows(path)
    selected=promote_churches(rows)
    if sum(r.get("kind")=="church" for r in rows)<4:
        raise RuntimeError("Pass 29 church refinement could not find four legal merged landmark sites")
    for mode in ("day","night"):
        image_path=p29.OUT/f"unified_composition_{mode}.png"
        im=Image.open(image_path).convert("RGB")
        for row in selected:church_overlay(im,row,mode=="night")
        im.save(image_path)
        p29.tile_image(im,p29.OUT/"tiles"/mode)
    p29.write_csv(path,("building_id","kind","district","x","y","w","h","merged_lot_count","fixed_component_scale"),rows)
    update_manifest(rows,selected)
    day=Image.open(p29.OUT/"unified_composition_day.png").convert("RGB")
    night=Image.open(p29.OUT/"unified_composition_night.png").convert("RGB")
    p29.save_review_screenshots(day,night)
    counts=defaultdict(int)
    for row in rows:
        if row.get("kind")=="church":counts[row.get("district","")]+=1
    print(f"PASS29_RC2_CHURCH_REFINEMENT promoted={len(selected)} churches={sum(counts.values())} by_district={dict(counts)} core_exclusion={CORE_BUILDING_EXCLUSION:g}")


if __name__=="__main__":main()
