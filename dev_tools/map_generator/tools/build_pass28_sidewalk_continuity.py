from __future__ import annotations

"""Pass 28: final-composition sidewalk continuity repair.

Pass 27 remains the protected map composition.  This pass rebuilds the exact
visual sidewalk/curb ribbons from the authoritative road geometry *after* all
building, infill and intentional-open-block artwork has been applied.  Only the
sidewalk and curb rings are repainted; asphalt is not touched, so lane markings
and zebra geometry remain intact.  Pass-23 sidewalk furniture/detail is then
redrawn from its semantic CSV.
"""

import math
import sys
from pathlib import Path
from collections import defaultdict

from PIL import Image, ImageChops, ImageDraw

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pass20_streetwall as pass20
import build_pass23_street_detail as pass23
import build_pass26_art_first_world as p26
import render_callback_preview as callback

PASS_ID = "pass_28_sidewalk_continuity_rc1"
REPORT_CSV = "sidewalk_continuity_pass28.csv"
REPAIR_MASK = "sidewalk_repair_mask_pass28.png"
SCREENSHOT_DIR = Path(__file__).resolve().parents[3] / "qa" / "pass28_screenshots"
MASTER_W = pass20.base.MASTER_W
MASTER_H = pass20.base.MASTER_H
MASTER_CX = 8192.0
MASTER_CY = 6144.0
MASTER_SCALE = 0.5


def road_metrics(road):
    lanes=max(1,int(float(road.get("lanes",1))))
    half=max(38.0,lanes*38.0+10.0)*pass20.base.ROAD_WIDTH_SCALE*.5
    sidewalk=max(28.0,float(road.get("sidewalk_width",28)))*pass20.base.SIDEWALK_SCALE
    curb=max(4.0,float(road.get("curb_width",4)))
    return half,sidewalk,curb


def expected_visual_rings(roads,rp):
    old_scale=callback.VIEW_SCALE;old_ortho=callback.ORTHOGONAL_GRID_PX
    callback.VIEW_SCALE=MASTER_SCALE;callback.ORTHOGONAL_GRID_PX=0.0
    try:
        masks=callback.surface_masks(
            MASTER_W,MASTER_H,MASTER_CX,MASTER_CY,callback.DAY,False,
            road_width_scale=pass20.base.ROAD_WIDTH_SCALE,
            sidewalk_scale=pass20.base.SIDEWALK_SCALE,
            roads_override=roads,rp_override=rp,
            surface_polygons_override=pass20.base.authored_surfaces(),
        )
        sidewalk_ring=ImageChops.subtract(masks["sidewalk"],masks["curb"])
        curb_ring=ImageChops.subtract(masks["curb"],masks["road"])
        return sidewalk_ring,curb_ring
    finally:
        callback.VIEW_SCALE=old_scale;callback.ORTHOGONAL_GRID_PX=old_ortho


def repaint_master(path:Path,night:bool,roads,rp,sidewalk_ring,curb_ring):
    before=Image.open(path).convert("RGB")
    im=before.copy();P=callback.NIGHT if night else callback.DAY
    callback.apply_mask(im,sidewalk_ring,"sidewalk_night.png" if night else "sidewalk_day.png",P["sidewalk"])
    callback.apply_mask(im,curb_ring,"curb_night.png" if night else "curb_day.png",P["curb"])

    # Restore the two thin visual seams from the canonical renderer without
    # repainting asphalt or changing semantic geometry.
    old_scale=callback.VIEW_SCALE;old_ortho=callback.ORTHOGONAL_GRID_PX
    callback.VIEW_SCALE=MASTER_SCALE;callback.ORTHOGONAL_GRID_PX=0.0
    try:
        callback.draw_street_edge_accents(
            ImageDraw.Draw(im),roads,rp,MASTER_CX,MASTER_CY,MASTER_W,MASTER_H,P,night,
            pass20.base.ROAD_WIDTH_SCALE,pass20.base.SIDEWALK_SCALE,
        )
    finally:
        callback.VIEW_SCALE=old_scale;callback.ORTHOGONAL_GRID_PX=old_ortho

    # Capture only places that actually differed from the canonical sidewalk or
    # curb material. This makes the regression visible and auditable rather than
    # merely asserting that a repaint function ran.
    diff=ImageChops.difference(before,im).convert("L")
    repaired=diff.point(lambda value:255 if value else 0)
    ring_union=ImageChops.lighter(sidewalk_ring,curb_ring)
    repaired=ImageChops.multiply(repaired,ring_union)
    im.save(path)
    return repaired


def redraw_sidewalk_detail(masters):
    path=pass20.base.SEMANTIC/pass23.DETAIL_CSV
    pass23.detail_rows.clear()
    if path.exists():
        pass23.detail_rows.extend(pass20.base.read_csv(path))
    pass23.draw_details(masters[0],False)
    pass23.draw_details(masters[1],True)


def sample_sidewalk_semantics(roads,rp):
    walkable=Image.open(p26.MASK_DIR/"walkable_mask_master.png").convert("L")
    solid=Image.open(p26.MASK_DIR/"solid_mask_master.png").convert("L")
    rows=[]
    for road in roads:
        rid=road["road_id"]
        if str(road.get("bridge","false")).lower()=="true":
            # The bridge deck has its own elevated pedestrian treatment; this
            # pass is aimed at disappearing street-level sidewalks.
            continue
        half,sidewalk,curb=road_metrics(road);samples=good=blocked=0
        points=rp[rid]
        for seg_index,(a,b) in enumerate(zip(points,points[1:])):
            dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
            if length<1:continue
            ux,uy=dx/length,dy/length;nx,ny=-uy,ux
            count=max(1,int(length/120.0))
            for index in range(count+1):
                t=(index+.5)/(count+1)
                bx=a[0]+dx*t;by=a[1]+dy*t
                for sign in (-1,1):
                    # Sample safely in the middle of the canonical sidewalk band.
                    offset=half+curb+sidewalk*.56
                    wx=bx+nx*sign*offset;wy=by+ny*sign*offset
                    mx,my=pass20.base.world_to_master(wx,wy)
                    x=int(round(mx));y=int(round(my))
                    if not (0<=x<walkable.width and 0<=y<walkable.height):continue
                    samples+=1
                    is_walk=walkable.getpixel((x,y))>0
                    is_blocked=solid.getpixel((x,y))>0
                    if is_walk and not is_blocked:good+=1
                    if is_blocked:blocked+=1
        share=good/samples if samples else 1.0
        rows.append({
            "road_id":rid,"road_class":road.get("highway",""),"samples":samples,
            "clear_walkable_samples":good,"solid_blocked_samples":blocked,
            "clear_walkable_share":round(share,4),
            "continuity_status":"pass" if share>=.94 else "fail",
        })
    pass20.base.write_csv(pass20.base.SEMANTIC/REPORT_CSV,
        ("road_id","road_class","samples","clear_walkable_samples","solid_blocked_samples","clear_walkable_share","continuity_status"),rows)
    return rows


def update_manifest(masters,repair_mask,report):
    path=pass20.base.OUT/"composition_manifest.csv";rows=pass20.base.read_csv(path)
    remove={"pass_id","pass28_sidewalk_continuity","pass28_sidewalk_rule","pass28_repaired_pixels",
            "pass28_sampled_roads","pass28_failed_roads","pass28_min_clear_walkable_share"}
    rows=[r for r in rows if r.get("key") not in remove and not r.get("key","").startswith("sha256_unified_composition_")]
    repaired_pixels=sum(repair_mask.histogram()[1:])//255
    failed=[r for r in report if r["continuity_status"]!="pass"]
    min_share=min((float(r["clear_walkable_share"]) for r in report),default=1.0)
    rows.extend([
        {"key":"pass_id","value":PASS_ID},
        {"key":"pass28_sidewalk_continuity","value":"true"},
        {"key":"pass28_sidewalk_rule","value":"canonical_visual_ribbon_repaint_after_final_art_then_redress_v1"},
        {"key":"pass28_repaired_pixels","value":str(repaired_pixels)},
        {"key":"pass28_sampled_roads","value":str(len(report))},
        {"key":"pass28_failed_roads","value":str(len(failed))},
        {"key":"pass28_min_clear_walkable_share","value":f"{min_share:.4f}"},
    ])
    for master in masters:
        rows.append({"key":f"sha256_{master.stem}","value":pass20.base.sha256(master)})
    pass20.base.write_csv(path,("key","value"),rows)


def make_screenshots(master,repair_mask):
    SCREENSHOT_DIR.mkdir(parents=True,exist_ok=True)
    im=Image.open(master).convert("RGB")
    # Compact whole-map review plus three automatically chosen repair hotspots.
    im.resize((2048,1024),Image.Resampling.LANCZOS).save(SCREENSHOT_DIR/"00_whole_day.png")
    mask=repair_mask
    # Score 768x576 windows on a coarse grid by repaired-pixel density.
    candidates=[];w=768;h=576;step=384
    integral=None
    # Pillow crop + histogram is fast enough for this small review search.
    for y in range(0,max(1,mask.height-h+1),step):
        for x in range(0,max(1,mask.width-w+1),step):
            crop=mask.crop((x,y,min(mask.width,x+w),min(mask.height,y+h)))
            score=sum(crop.histogram()[1:])
            candidates.append((score,x,y))
    chosen=[]
    for score,x,y in sorted(candidates,reverse=True):
        if score<=0:break
        if any(abs(x-cx)<w*.7 and abs(y-cy)<h*.7 for _,cx,cy in chosen):continue
        chosen.append((score,x,y))
        if len(chosen)>=3:break
    for index,(_,x,y) in enumerate(chosen,1):
        im.crop((x,y,min(im.width,x+w),min(im.height,y+h))).save(SCREENSHOT_DIR/f"0{index}_sidewalk_repair_hotspot.png")


def main():
    roads,rp,_=pass20.base.authored_block_network()
    masters=[pass20.base.OUT/"unified_composition_day.png",pass20.base.OUT/"unified_composition_night.png"]
    for master in masters:
        if not master.exists():raise RuntimeError(f"Pass 28 requires an already-built Pass 27 master: {master}")
    sidewalk_ring,curb_ring=expected_visual_rings(roads,rp)
    day_repair=repaint_master(masters[0],False,roads,rp,sidewalk_ring,curb_ring)
    night_repair=repaint_master(masters[1],True,roads,rp,sidewalk_ring,curb_ring)
    repair_mask=ImageChops.lighter(day_repair,night_repair)
    repair_mask.save(pass20.base.OUT/REPAIR_MASK)
    redraw_sidewalk_detail(masters)
    report=sample_sidewalk_semantics(roads,rp)
    pass20.base.tile_masters(masters)
    update_manifest(masters,repair_mask,report)
    make_screenshots(masters[0],repair_mask)
    repaired_pixels=sum(repair_mask.histogram()[1:])//255
    failed=sum(r["continuity_status"]!="pass" for r in report)
    minimum=min((float(r["clear_walkable_share"]) for r in report),default=1.0)
    print(f"PASS28_SIDEWALK_CONTINUITY repaired_pixels={repaired_pixels} sampled_roads={len(report)} failed_roads={failed} min_clear_share={minimum:.4f}")


if __name__=="__main__":main()
