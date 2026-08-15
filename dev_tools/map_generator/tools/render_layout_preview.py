from __future__ import annotations

import csv
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / 'mapfiles' / 'data' / 'map_001_gwb_corridor'
COS = ROOT / 'working_cosmetics'
OUT = ROOT / 'output'


def read(path):
    p = path if isinstance(path, Path) else MAP / path
    if not p.exists():
        return []
    with p.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def fv(r,k,d=0):
    try:return float(r.get(k,d) or d)
    except:return float(d)


def font(sz=16):
    try:return ImageFont.truetype('DejaVuSans-Bold.ttf',sz)
    except:return ImageFont.load_default()


def grouped_points(name,idf):
    out={}
    for r in read(name):
        out.setdefault(r[idf],[]).append((int(float(r.get('point_order',0) or 0)),fv(r,'x'),fv(r,'y')))
    return {k:[(x,y) for _,x,y in sorted(v)] for k,v in out.items()}


def render():
    W,H=1600,760
    roads=read('roads.csv'); rp=grouped_points('road_points.csv','road_id'); buildings=read('buildings.csv')
    xs=[];ys=[]
    for ps in rp.values():
        for x,y in ps:xs.append(x);ys.append(y)
    for b in buildings:
        x,y,w,h=(fv(b,k) for k in ('x','y','w','h'));xs.extend([x,x+w]);ys.extend([y,y+h])
    if not xs:raise SystemExit('No map geometry')
    minx,maxx=min(xs),max(xs);miny,maxy=min(ys),max(ys)
    pad=80; sx=(W-2*pad)/max(1,maxx-minx); sy=(H-2*pad)/max(1,maxy-miny); scale=min(sx,sy)
    ox=(W-(maxx-minx)*scale)/2;oy=(H-(maxy-miny)*scale)/2
    def T(x,y):return (ox+(x-minx)*scale,oy+(y-miny)*scale)
    im=Image.new('RGB',(W,H),(26,30,31));d=ImageDraw.Draw(im)
    # Buildings as dense urban masses.
    for b in buildings:
        x,y,w,h=(fv(b,k) for k in ('x','y','w','h'));a=T(x,y);c=T(x+w,y+h)
        d.rectangle((a[0],a[1],c[0],c[1]),fill=(74,75,70),outline=(101,98,88))
    # Roads: hierarchy first.
    widths={'motorway':10,'trunk':8,'primary':6,'secondary':5,'tertiary':4,'residential':3,'service':2}
    for r in roads:
        ps=[T(x,y) for x,y in rp.get(r['road_id'],[])]
        if len(ps)<2:continue
        hw=(r.get('highway') or 'residential').lower();ww=widths.get(hw,3)
        d.line(ps,fill=(185,183,167),width=ww,joint='curve')
        if hw in ('motorway','trunk'):
            d.line(ps,fill=(83,94,99),width=max(2,ww-3),joint='curve')
    # Cosmetic service cut-throughs from the GTA2-inspired authored-layout pass.
    for o in read(COS/'layout_overlays.csv'):
        if o.get('kind')!='service_alley':continue
        x,y,w,h=(fv(o,k) for k in ('x','y','w','h'));a=T(x,y);c=T(x+w,y+h)
        d.rectangle((a[0],a[1],c[0],c[1]),fill=(181,126,61),outline=(229,176,85))
    # Traffic routes show the existing gameplay loop structure without changing it.
    trp=grouped_points('traffic_route_points.csv','route_id')
    route_cols=[(79,173,222),(109,202,132),(234,165,68),(196,101,197),(226,93,85)]
    for idx,(rid,ps) in enumerate(sorted(trp.items())):
        q=[T(x,y) for x,y in ps]
        if len(q)>=2:d.line(q,fill=route_cols[idx%len(route_cols)],width=2,joint='curve')
    # Landmark anchors.
    for lm in read(COS/'landmark_anchors.csv'):
        x,y=T(fv(lm,'x'),fv(lm,'y'));d.ellipse((x-7,y-7,x+7,y+7),fill=(244,218,88),outline=(36,37,34),width=2)
    # District labels.
    for r in read('districts.csv'):
        x,y=T(fv(r,'x'),fv(r,'y'));name=r.get('name','')
        bb=d.textbbox((0,0),name,font=font(13));tw=bb[2]-bb[0];th=bb[3]-bb[1]
        d.rectangle((x-tw/2-5,y-th/2-4,x+tw/2+5,y+th/2+4),fill=(17,20,21))
        d.text((x-tw/2,y-th/2),name,font=font(13),fill=(238,236,218))
    d.rectangle((12,12,770,66),fill=(10,13,14))
    d.text((24,20),'v0.4 AUTHORED LAYOUT REVIEW — REAL NYC/GWB GEOGRAPHY + TOP-DOWN DESIGN PRINCIPLES',font=font(16),fill=(244,242,228))
    d.text((24,44),'gray=semantic streets/buildings  orange=cosmetic service cut-through cues  colored=existing traffic loops  yellow=landmarks',font=font(10),fill=(194,195,183))
    OUT.mkdir(exist_ok=True);p=OUT/'authored_layout_review.png';im.save(p);print(p)


if __name__=='__main__':render()
