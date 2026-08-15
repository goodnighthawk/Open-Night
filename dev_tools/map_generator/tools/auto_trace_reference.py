from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import label as ndi_label
from skimage.morphology import skeletonize

ROOT = Path(__file__).resolve().parents[1]
REFDIR = ROOT / "references"
LAYERS = REFDIR / "layers"
WORK = ROOT / "working_reference"
OUT = ROOT / "output"


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def _load(name: str) -> np.ndarray:
    path = (LAYERS / f"{name}.png") if name != "roads" else (LAYERS / "roads.png")
    if not path.exists() and name == "roads":
        path = REFDIR / "street_map_reference.png"
    if not path.exists():
        raise SystemExit(f"Missing reference layer: {path}")
    return np.asarray(Image.open(path).convert("RGB"))


def _align_layer_to_master(master: np.ndarray, source: np.ndarray, name: str) -> tuple[np.ndarray, dict]:
    """Register map screenshots with a similarity transform only.

    The map reference images are captures of the same north-up map at essentially
    the same zoom, but browser/UI cropping changes their pixel origins.  We use
    feature matches only to estimate *uniform scale + translation*.  Rotation,
    shear, anisotropic scaling and perspective/homography are deliberately
    forbidden so the generated outdoor world can never inherit a perspective
    skew from the source screenshots.
    """
    mh, mw = master.shape[:2]; sh, sw = source.shape[:2]
    g1 = cv2.cvtColor(master, cv2.COLOR_RGB2GRAY)
    g2 = cv2.cvtColor(source, cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(nfeatures=7000, fastThreshold=12)
    k1, d1 = orb.detectAndCompute(g1, None); k2, d2 = orb.detectAndCompute(g2, None)
    method='fallback_contain'; matches=0; inliers=0
    scale=min(mw/max(1,sw), mh/max(1,sh)); tx=(mw-sw*scale)/2; ty=(mh-sh*scale)/2
    if d1 is not None and d2 is not None and len(k1)>=12 and len(k2)>=12:
        bf=cv2.BFMatcher(cv2.NORM_HAMMING)
        good=[]
        for pair in bf.knnMatch(d2,d1,k=2):
            if len(pair)==2 and pair[0].distance < 0.72*pair[1].distance:
                good.append(pair[0])
        matches=len(good)
        if len(good)>=18:
            src=np.float32([k2[m.queryIdx].pt for m in good])
            dst=np.float32([k1[m.trainIdx].pt for m in good])
            M, mask=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=3,maxIters=5000,confidence=.995)
            if M is not None:
                est_scale=float(math.hypot(M[0,0],M[0,1]))
                if 0.94 <= est_scale <= 1.06:
                    keep=(mask.ravel()>0) if mask is not None else np.ones(len(src),dtype=bool)
                    ss=src[keep]; dd=dst[keep]
                    if len(ss)>=12:
                        scale=est_scale
                        tx=float(np.median(dd[:,0]-scale*ss[:,0])); ty=float(np.median(dd[:,1]-scale*ss[:,1]))
                        method='orb_uniform_scale_translate'; inliers=int(len(ss))
    M=np.array([[scale,0.0,tx],[0.0,scale,ty]],dtype=np.float32)
    aligned=cv2.warpAffine(source,M,(mw,mh),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=(255,255,255))
    meta={'layer':name,'method':method,'source_w':sw,'source_h':sh,'master_w':mw,'master_h':mh,'uniform_scale':f'{scale:.8f}','translate_x':f'{tx:.3f}','translate_y':f'{ty:.3f}','feature_matches':matches,'inliers':inliers,'perspective_skew':'0','anisotropic_scale':'false'}
    return aligned,meta


def _clean_components(mask: np.ndarray, minimum_area: int) -> np.ndarray:
    lab, _ = ndi_label(mask.astype(bool))
    sizes = np.bincount(lab.ravel())
    keep = sizes >= int(minimum_area)
    if len(keep): keep[0] = False
    return keep[lab]


def _neighbors(p: tuple[int, int], pixels: set[tuple[int, int]]) -> list[tuple[int, int]]:
    y, x = p
    out=[]
    for dy in (-1,0,1):
        for dx in (-1,0,1):
            if dx == 0 and dy == 0: continue
            q=(y+dy,x+dx)
            if q in pixels: out.append(q)
    return out


def _path_length(points: list[tuple[float,float]]) -> float:
    return sum(math.hypot(b[0]-a[0], b[1]-a[1]) for a,b in zip(points,points[1:]))


def _simplify(points: list[tuple[float,float]], eps: float = 4.0) -> list[tuple[int,int]]:
    if len(points) < 2: return []
    arr=np.array(points,dtype=np.float32).reshape(-1,1,2)
    simp=cv2.approxPolyDP(arr, eps, False).reshape(-1,2)
    out=[(int(round(x)),int(round(y))) for x,y in simp]
    if len(out) < 2:
        out=[(int(round(points[0][0])),int(round(points[0][1]))),(int(round(points[-1][0])),int(round(points[-1][1])))]
    return out


def skeleton_paths(mask: np.ndarray, min_area: int = 100, min_length: float = 55.0,
                   max_paths: int = 160, simplify_eps: float = 4.0) -> list[list[tuple[int,int]]]:
    clean=_clean_components(mask,min_area)
    sk=skeletonize(clean)
    ys,xs=np.nonzero(sk)
    pixels=set(zip(ys.tolist(),xs.tolist()))
    if not pixels: return []
    degree={p:len(_neighbors(p,pixels)) for p in pixels}
    nodes={p for p,d in degree.items() if d != 2}
    visited=set(); paths=[]

    def edge(a,b): return tuple(sorted((a,b)))
    for start in sorted(nodes):
        for nxt in _neighbors(start,pixels):
            e=edge(start,nxt)
            if e in visited: continue
            visited.add(e); seq=[start,nxt]; prev=start; cur=nxt
            guard=0
            while cur not in nodes and guard < 20000:
                guard+=1
                cand=[q for q in _neighbors(cur,pixels) if q != prev]
                if not cand: break
                q=cand[0]; visited.add(edge(cur,q)); seq.append(q); prev,cur=cur,q
            xy=[(float(x),float(y)) for y,x in seq]
            if _path_length(xy) >= min_length:
                paths.append(_simplify(xy,simplify_eps))

    # Retain long cycles that contain no degree!=2 node.
    remaining=[]
    for p in pixels:
        for q in _neighbors(p,pixels):
            if edge(p,q) not in visited:
                remaining.append((p,q)); break
    for start,nxt in remaining:
        if edge(start,nxt) in visited: continue
        visited.add(edge(start,nxt)); seq=[start,nxt]; prev=start; cur=nxt
        for _ in range(30000):
            cand=[q for q in _neighbors(cur,pixels) if q != prev and edge(cur,q) not in visited]
            if not cand: break
            q=cand[0]; visited.add(edge(cur,q)); seq.append(q); prev,cur=cur,q
            if cur == start: break
        xy=[(float(x),float(y)) for y,x in seq]
        if _path_length(xy) >= min_length:
            paths.append(_simplify(xy,simplify_eps))

    # Drop near-zero / duplicate traces, longest first.
    uniq=[]; seen=set()
    for p in sorted(paths,key=_path_length,reverse=True):
        key=(round(p[0][0]/10),round(p[0][1]/10),round(p[-1][0]/10),round(p[-1][1]/10),round(_path_length(p)/20))
        rkey=(key[2],key[3],key[0],key[1],key[4])
        if key in seen or rkey in seen: continue
        seen.add(key); uniq.append(p)
        if len(uniq)>=max_paths: break
    return uniq


def road_mask(img: np.ndarray) -> np.ndarray:
    r,g,b=[img[:,:,i].astype(np.int16) for i in range(3)]
    # Google-style major-road fill: desaturated blue/steel. Water is more cyan and excluded by b-g.
    mask=(b-r>12)&(b-g>3)&(r>65)&(r<195)&(g>80)&(g<215)&(b>105)&(b<235)
    m=(mask.astype(np.uint8)*255)
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8),iterations=1)
    m=cv2.morphologyEx(m,cv2.MORPH_OPEN,np.ones((2,2),np.uint8),iterations=1)
    return m>0


def local_road_mask(img: np.ndarray) -> np.ndarray:
    r,g,b=[img[:,:,i].astype(np.int16) for i in range(3)]
    # Pale local-street network used by the base map. This intentionally targets
    # thin cool-gray road lines and avoids cyan water / saturated park fills.
    mask=(r>175)&(r<238)&(g>185)&(g<244)&(b>190)&(b<249)&(b-r>4)&(b-g>=0)&(g-r>-2)
    mask &= ~((g-r>10)&(b-r>25))
    m=(mask.astype(np.uint8)*255)
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((2,2),np.uint8),iterations=1)
    return m>0


def traffic_mask(img: np.ndarray) -> np.ndarray:
    r,g,b=[img[:,:,i].astype(np.int16) for i in range(3)]
    # Live-traffic overlay: vivid green plus yellow/red/orange congestion segments.
    green=(g>145)&(g-r>18)&(g-b>5)&(b<190)
    warm=(r>170)&(g>70)&(g<220)&(b<125)
    m=((green|warm).astype(np.uint8)*255)
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8),iterations=2)
    return m>0


def biking_mask(img: np.ndarray) -> np.ndarray:
    r,g,b=[img[:,:,i].astype(np.int16) for i in range(3)]
    mask=(g>75)&(g-r>18)&(g-b>5)&(r<185)&(b<185)
    m=(mask.astype(np.uint8)*255)
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8),iterations=1)
    return m>0


def transit_mask(img: np.ndarray) -> np.ndarray:
    hsv=cv2.cvtColor(img,cv2.COLOR_RGB2HSV); H,S,V=cv2.split(hsv)
    # Saturated transit-line colors. Exclude cyan water and purple POI icons where possible.
    keep=((H<20)|((H>35)&(H<95))|((H>102)&(H<140))|(H>168))
    mask=(S>95)&(V>105)&keep
    m=(mask.astype(np.uint8)*255)
    m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8),iterations=1)
    return m>0


def terrain_masks(img: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    # Use hue/saturation to distinguish actual Google-map water from blue-gray
    # roads and terrain shading.  The earlier RGB rule admitted highway fills and
    # produced large triangular false-water polygons.
    hsv=cv2.cvtColor(img,cv2.COLOR_RGB2HSV); H,S,V=cv2.split(hsv)
    water=(H>=90)&(H<=103)&(S>=65)&(V>=180)
    green=(H>=42)&(H<=86)&(S>=22)&(V>=115)
    water=cv2.morphologyEx((water.astype(np.uint8)*255),cv2.MORPH_CLOSE,np.ones((9,9),np.uint8),iterations=2)
    water=cv2.morphologyEx(water,cv2.MORPH_OPEN,np.ones((3,3),np.uint8),iterations=1)>0
    green=cv2.morphologyEx((green.astype(np.uint8)*255),cv2.MORPH_OPEN,np.ones((3,3),np.uint8),iterations=1)>0
    return water,green


def contour_polygons(mask: np.ndarray, min_area: float, max_count: int) -> list[list[tuple[int,int]]]:
    contours,_=cv2.findContours((mask.astype(np.uint8)*255),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    out=[]
    for c in sorted(contours,key=cv2.contourArea,reverse=True):
        if cv2.contourArea(c)<min_area: continue
        eps=max(2.5,0.006*cv2.arcLength(c,True)); p=cv2.approxPolyDP(c,eps,True).reshape(-1,2)
        if len(p)>=3: out.append([(int(x),int(y)) for x,y in p])
        if len(out)>=max_count: break
    return out


def pts_str(p): return ';'.join(f'{x},{y}' for x,y in p)


def local_width(mask: np.ndarray, path: list[tuple[int,int]]) -> float:
    dist=cv2.distanceTransform(mask.astype(np.uint8),cv2.DIST_L2,5)
    vals=[]
    for x,y in path:
        if 0<=y<dist.shape[0] and 0<=x<dist.shape[1]: vals.append(float(dist[y,x]))
    return float(np.median(vals)) if vals else 2.0


def main():
    ap=argparse.ArgumentParser(description='Automatically derive deterministic trace layers from the five Open Night reference screenshots.')
    ap.add_argument('--preview',action='store_true')
    a=ap.parse_args()
    roads=_load('roads')
    aligned={}; alignment_rows=[]
    for name in ('traffic','terrain','transit','biking'):
        arr,meta=_align_layer_to_master(roads,_load(name),name);aligned[name]=arr;alignment_rows.append(meta)
        OUT.mkdir(parents=True,exist_ok=True);Image.fromarray(arr).save(OUT/f'aligned_{name}.png',optimize=True)
    _write(WORK/'reference_alignment.csv',['layer','method','source_w','source_h','master_w','master_h','uniform_scale','translate_x','translate_y','feature_matches','inliers','perspective_skew','anisotropic_scale'],alignment_rows)
    traffic=aligned['traffic']; terrain=aligned['terrain']; transit=aligned['transit']; biking=aligned['biking']

    rm=road_mask(roads); major_paths=skeleton_paths(rm,min_area=110,min_length=58,max_paths=135,simplify_eps=5.0)
    lm=local_road_mask(roads); local_paths=skeleton_paths(lm,min_area=14,min_length=26,max_paths=1000,simplify_eps=2.5)
    major_dil=cv2.dilate(rm.astype(np.uint8),np.ones((9,9),np.uint8),iterations=1)>0
    filtered_local=[]
    local_candidates=[]
    # Prioritize the playable Fort Lee -> GWB -> Washington Heights corridor.
    # Dense local streets are short, so a pure longest-first cap starves the core
    # while retaining long suburban/park outlines elsewhere in the regional image.
    core_boxes=[(500,330,815,625),(810,330,1070,690)]
    for p in local_paths:
        if len(p)<2:continue
        mx,my=p[len(p)//2]
        if 0<=my<major_dil.shape[0] and 0<=mx<major_dil.shape[1] and major_dil[my,mx]:continue
        in_core=any(x0<=mx<=x1 and y0<=my<=y1 for x0,y0,x1,y1 in core_boxes)
        local_candidates.append((0 if in_core else 1,-_path_length(p),p))
    for _,__,p in sorted(local_candidates,key=lambda z:(z[0],z[1])):
        filtered_local.append(p)
        if len(filtered_local)>=520:break
    rpaths=major_paths+filtered_local
    rr=[]
    for k,p in enumerate(rpaths,1):
        if k<=len(major_paths):
            half=local_width(rm,p)
            if half>=9: cls,lanes='motorway','6'
            elif half>=6: cls,lanes='trunk','4'
            elif half>=4: cls,lanes='primary','4'
            elif half>=2.8: cls,lanes='secondary','2'
            else: cls,lanes='local','2'
            note='auto-traced major road from roads screenshot'
        else:
            cls,lanes=('secondary','2') if _path_length(p)>190 else ('local','2')
            note='auto-traced local street from roads screenshot'
        rr.append({'road_id':f'road_{k:03d}','points_image_px':pts_str(p),'width_class':cls,'lane_hint':lanes,'direction':'both','notes':note})
    # The bridge deck is partially interrupted by labels/POI icons in the map screenshot.
    # Keep one explicit source-image-space connector so the playable map never loses
    # the defining Fort Lee <-> Manhattan crossing when color segmentation breaks.
    gwb=[(714,426),(760,437),(815,452),(870,468),(925,486),(985,501)]
    rr.append({'road_id':'gwb_upper_level','points_image_px':pts_str(gwb),'width_class':'motorway','lane_hint':'6','direction':'both','notes':'gwb mandatory bridge connector traced from roads screenshot'})
    _write(WORK/'roads_trace.csv',['road_id','points_image_px','width_class','lane_hint','direction','notes'],rr)

    tm=traffic_mask(traffic); tpaths=skeleton_paths(tm,min_area=90,min_length=90,max_paths=55,simplify_eps=5.5)
    tr=[]
    for k,p in enumerate(tpaths,1):
        # Sample original traffic overlay saturation/color along path to infer relative activity.
        vals=[]
        for x,y in p:
            if 0<=y<traffic.shape[0] and 0<=x<traffic.shape[1]:
                R,G,B=map(int,traffic[y,x]);
                if R>175 and G<180: vals.append(.95)
                elif R>175 and G>=150: vals.append(.75)
                elif G>R+20: vals.append(.45)
        density=float(np.mean(vals)) if vals else .5
        priority='arterial' if density>.82 else 'high' if density>.65 else 'normal' if density>.38 else 'low'
        tr.append({'flow_id':f'flow_{k:03d}','points_image_px':pts_str(p),'priority':priority,'relative_density':f'{density:.3f}','direction':'both','notes':'auto-traced from traffic screenshot'})
    tr.append({'flow_id':'gwb_flow','points_image_px':pts_str(gwb),'priority':'arterial','relative_density':'0.780','direction':'both','notes':'mandatory GWB traffic flow on explicit bridge connector'})
    _write(WORK/'traffic_trace.csv',['flow_id','points_image_px','priority','relative_density','direction','notes'],tr)

    bm=biking_mask(biking); bpaths=skeleton_paths(bm,min_area=55,min_length=65,max_paths=70,simplify_eps=4.5)
    br=[]
    for k,p in enumerate(bpaths,1):
        br.append({'bike_id':f'bike_{k:03d}','facility_type':'protected' if _path_length(p)>180 else 'lane','points_image_px':pts_str(p),'direction':'both','notes':'auto-traced from biking screenshot'})
    _write(WORK/'biking_trace.csv',['bike_id','facility_type','points_image_px','direction','notes'],br)

    xm=transit_mask(transit); xpaths=skeleton_paths(xm,min_area=30,min_length=65,max_paths=45,simplify_eps=4.0)
    xr=[]
    for k,p in enumerate(xpaths,1):
        xr.append({'transit_id':f'transit_{k:03d}','mode':'rail','points_image_px':pts_str(p),'station_name':'','notes':'auto-traced from transit screenshot'})
    _write(WORK/'transit_trace.csv',['transit_id','mode','points_image_px','station_name','notes'],xr)

    wm,gm=terrain_masks(terrain)
    wp=contour_polygons(wm,min_area=500,max_count=12); gp=contour_polygons(gm,min_area=280,max_count=35)
    ar=[]
    for k,p in enumerate(wp,1): ar.append({'area_id':f'water_{k:02d}','terrain_type':'water','polygon_image_px':pts_str(p),'notes':'auto-traced water'})
    for k,p in enumerate(gp,1): ar.append({'area_id':f'green_{k:02d}','terrain_type':'park','polygon_image_px':pts_str(p),'notes':'auto-traced green space'})
    _write(WORK/'terrain_trace.csv',['area_id','terrain_type','polygon_image_px','notes'],ar)

    print(f'[auto-trace] roads={len(rr)} traffic={len(tr)} terrain={len(ar)} transit={len(xr)} biking={len(br)}')

    if a.preview:
        out=Image.fromarray(roads.copy()); d=ImageDraw.Draw(out,'RGBA')
        palette=[(255,210,60,220),(255,70,70,210),(80,210,100,130),(90,130,255,210),(20,150,20,210)]
        for p in rpaths:d.line(p,fill=palette[0],width=2)
        for p in tpaths:d.line(p,fill=palette[1],width=2)
        for p in bpaths:d.line(p,fill=palette[4],width=2)
        for p in xpaths:d.line(p,fill=palette[3],width=2)
        OUT.mkdir(parents=True,exist_ok=True); out.save(OUT/'auto_trace_preview.png')
        print('[auto-trace] preview:',OUT/'auto_trace_preview.png')

if __name__=='__main__': main()
