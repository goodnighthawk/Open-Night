from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cosmetic_pack import load_catalog, stable_int

BASE = ROOT / 'mapfiles' / 'data' / 'map_001_gwb_corridor'
COS = ROOT / 'working_cosmetics'
OUT = ROOT / 'output'
PACK = ROOT / 'cosmetic_packs' / 'nyc_gta2_callback'
MAT = PACK / 'materials'
CAT = {r['archetype_id']: r for r in load_catalog()}
VIEW_SCALE = 1.0

DAY = {
    'land': (91, 95, 82), 'road': (48, 53, 57), 'sidewalk': (190, 182, 162),
    'curb': (226, 216, 190), 'water': (18, 93, 137), 'green': (61, 116, 61),
    'lane': (235, 231, 214), 'yellow': (229, 177, 46), 'shadow': (24, 27, 29),
    'alley': (61, 63, 60), 'plaza': (174, 164, 142),
}
NIGHT = {
    'land': (37, 43, 39), 'road': (26, 31, 35), 'sidewalk': (106, 103, 94),
    'curb': (145, 138, 120), 'water': (10, 52, 78), 'green': (31, 61, 36),
    'lane': (163, 161, 151), 'yellow': (163, 128, 42), 'shadow': (7, 9, 10),
    'alley': (31, 34, 33), 'plaza': (86, 82, 73),
}


def read(path):
    p = path if isinstance(path, Path) else BASE / path
    if not p.exists():
        return []
    with p.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def f(r, k, d=0):
    try:
        return float(r.get(k, d) or d)
    except Exception:
        return float(d)


def i(r, k, d=0):
    try:
        return int(float(r.get(k, d) or d))
    except Exception:
        return int(d)


def pts(name, idf):
    out = {}
    for r in read(name):
        out.setdefault(r[idf], []).append((i(r, 'point_order'), f(r, 'x'), f(r, 'y')))
    return {k: [(x, y) for _, x, y in sorted(v)] for k, v in out.items()}


def tf(p, cx, cy, w, h):
    return ((p[0] - cx) * VIEW_SCALE + w / 2, (p[1] - cy) * VIEW_SCALE + h / 2)


def sc(v, minimum=1):
    return max(minimum, int(round(v * VIEW_SCALE)))


def font(sz=16):
    try:
        return ImageFont.truetype('DejaVuSans-Bold.ttf', sz)
    except Exception:
        return ImageFont.load_default()


@lru_cache(maxsize=64)
def material(name: str):
    p = MAT / name
    if not p.exists():
        return None
    return Image.open(p).convert('RGB')


def tiled_texture(name: str, size, fallback):
    tex = material(name)
    if tex is None:
        return Image.new('RGB', size, fallback)
    out = Image.new('RGB', size, fallback)
    tw, th = tex.size
    for y in range(0, size[1], th):
        for x in range(0, size[0], tw):
            out.paste(tex, (x, y))
    return out


def apply_mask(im: Image.Image, mask: Image.Image, texture_name: str, fallback):
    tex = tiled_texture(texture_name, im.size, fallback)
    im.paste(tex, (0, 0), mask)


def line_dashed(d, a, b, fill, width, dash=24, gap=19):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L <= 1:
        return
    ux, uy = dx / L, dy / L
    t = 0
    dash *= VIEW_SCALE
    gap *= VIEW_SCALE
    while t < L:
        e = min(L, t + dash)
        d.line((a[0] + ux*t, a[1] + uy*t, a[0] + ux*e, a[1] + uy*e), fill=fill, width=max(1, sc(width)))
        t = e + gap


def offset(a, b, off):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy/L, dx/L
    off *= VIEW_SCALE
    return (a[0] + nx*off, a[1] + ny*off), (b[0] + nx*off, b[1] + ny*off)


def gta2_round_polyline(points, radius_px=48.0):
    """Cosmetic-only broad corner rounding inspired by GTA 2 road ribbons.

    This never changes semantic road points.  It replaces visible hard polyline
    elbows with tangent quadratic arcs that stay inside the local corner span.
    """
    if len(points) < 3:
        return list(points)
    clean=[points[0]]
    for p in points[1:]:
        if math.hypot(p[0]-clean[-1][0],p[1]-clean[-1][1]) >= 1.0:
            clean.append(p)
    if len(clean)<3:
        return clean
    out=[clean[0]]
    for idx in range(1,len(clean)-1):
        a=clean[idx-1]; p=clean[idx]; b=clean[idx+1]
        vin=(p[0]-a[0],p[1]-a[1]); vout=(b[0]-p[0],b[1]-p[1])
        lin=math.hypot(*vin); lout=math.hypot(*vout)
        if lin<2 or lout<2:
            out.append(p); continue
        uin=(vin[0]/lin,vin[1]/lin); uout=(vout[0]/lout,vout[1]/lout)
        dot=max(-1.0,min(1.0,uin[0]*uout[0]+uin[1]*uout[1]))
        turn=math.acos(dot)
        # Nearly straight segments should stay straight; near U-turns should not
        # balloon into loops.  Normal city corners get the largest visual radius.
        if turn < math.radians(6) or turn > math.radians(168):
            out.append(p); continue
        strength=max(.32,min(1.0,turn/math.radians(82)))
        cut=min(radius_px*strength,lin*.32,lout*.32)
        if cut<1.25:
            out.append(p); continue
        pin=(p[0]-uin[0]*cut,p[1]-uin[1]*cut)
        pout=(p[0]+uout[0]*cut,p[1]+uout[1]*cut)
        if math.hypot(pin[0]-out[-1][0],pin[1]-out[-1][1])>0.5:
            out.append(pin)
        steps=max(3,min(9,int(turn/math.radians(12))+2))
        for j in range(1,steps):
            t=j/steps; omt=1-t
            out.append((omt*omt*pin[0]+2*omt*t*p[0]+t*t*pout[0],
                        omt*omt*pin[1]+2*omt*t*p[1]+t*t*pout[1]))
        out.append(pout)
    out.append(clean[-1])
    return out


def visual_road_points(r, rp, cx, cy, W, H):
    q=[tf(z,cx,cy,W,H) for z in rp.get(r['road_id'],[])]
    hw=(r.get('highway') or '').lower()
    base={'motorway':92,'trunk':82,'primary':70,'secondary':60,'tertiary':54,'residential':46,'service':36}.get(hw,48)
    return gta2_round_polyline(q,max(2.0,base*VIEW_SCALE))


def parallel_polyline(points, off_world):
    if len(points)<2: return list(points)
    off=off_world*VIEW_SCALE; out=[]
    for idx,(x,y) in enumerate(points):
        a=points[max(0,idx-1)]; b=points[min(len(points)-1,idx+1)]
        dx,dy=b[0]-a[0],b[1]-a[1]; L=math.hypot(dx,dy) or 1.0
        nx,ny=-dy/L,dx/L
        out.append((x+nx*off,y+ny*off))
    return out


def dashed_polyline(d, points, fill, width, dash=24, gap=19):
    if len(points)<2: return
    dash=max(1.0,dash*VIEW_SCALE); gap=max(1.0,gap*VIEW_SCALE); cycle=dash+gap
    segs=[];cum=[0.0];total=0.0
    for a,b in zip(points,points[1:]):
        L=math.hypot(b[0]-a[0],b[1]-a[1]);segs.append((a,b,L));total+=L;cum.append(total)
    if total<=1e-6:return
    def sample(dist):
        dist=max(0.0,min(total,dist))
        for idx,(a,b,L) in enumerate(segs):
            if dist<=cum[idx+1]+1e-9:
                if L<=1e-9:return a,idx
                t=(dist-cum[idx])/L;return (a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t),idx
        return points[-1],len(segs)-1
    pos=0.0
    while pos<total-1e-6:
        end=min(total,pos+dash);a,ia=sample(pos);b,ib=sample(end);sub=[a]
        for k in range(ia+1,ib+1):sub.append(points[k])
        if math.hypot(b[0]-sub[-1][0],b[1]-sub[-1][1])>1e-6:sub.append(b)
        if len(sub)>=2:d.line(sub,fill=fill,width=max(1,sc(width)),joint='curve')
        pos+=cycle



def lanes(r):
    base = max(1, i(r, 'lanes', 1))
    hw = (r.get('highway') or '').lower()
    cap = {'motorway':6,'motorway_link':6,'trunk':6,'trunk_link':6,'primary':4,'primary_link':4,
           'secondary':4,'secondary_link':4,'tertiary':3,'residential':2,'service':1,'unclassified':2}.get(hw,2)
    return min(base, cap)


def grouped_cosmetics():
    return {r['object_id']: r for r in read(COS / 'cosmetic_instances.csv')}


def grouped_massing():
    out = defaultdict(list)
    for r in read(COS / 'building_massing.csv'):
        out[r['building_id']].append(r)
    return out


def grouped_overlays():
    out = defaultdict(list)
    for r in read(COS / 'layout_overlays.csv'):
        out[r['kind']].append(r)
    return out


def family(aid):
    return CAT.get(aid, {}).get('family', 'brick_midrise')


def load_sprite(aid, night=False):
    r = CAT.get(aid)
    p = PACK / (r['night_sprite'] if night else r['day_sprite']) if r else None
    return Image.open(p).convert('RGBA') if p and p.exists() else None


def wall_color(fam, seed, night):
    groups = {
        'brick_midrise':[(159,78,54),(139,66,49),(172,91,60)],
        'brownstone_row':[(132,86,64),(151,96,67),(117,75,59)],
        'stone_midrise':[(162,144,116),(145,133,113),(173,150,117)],
        'painted_walkup':[(136,111,89),(151,120,91),(109,121,113)],
        'commercial_corner':[(164,83,58),(137,111,87),(155,129,99)],
        'commercial_lowrise':[(159,86,58),(137,115,91),(169,112,70)],
        'industrial':[(108,118,116),(91,107,109),(126,105,87)],
        'warehouse':[(112,108,94),(88,106,108),(133,91,67)],
        'concrete_tower':[(124,127,123),(145,136,117),(108,121,124)],
        'art_deco':[(166,145,115),(139,130,108),(173,153,125)],
        'parking_garage':[(108,115,114),(93,102,103),(127,120,108)],
        'waterfront_midrise':[(145,82,59),(154,101,69),(124,97,80)],
    }
    arr = groups.get(fam, groups['brick_midrise'])
    c = arr[seed % len(arr)]
    return tuple(int(v * (.50 if night else 1)) for v in c)


def draw_brick_face(d, box, base, night=False):
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return
    mortar = tuple(int(v * (.75 if not night else .58)) for v in base)
    step_y = max(4, sc(8))
    step_x = max(8, sc(18))
    yy = int(y0) + step_y
    row = 0
    while yy < y1:
        d.line((x0, yy, x1, yy), fill=mortar, width=1)
        shift = step_x // 2 if row % 2 else 0
        xx = int(x0) + shift
        while xx < x1:
            d.line((xx, yy-step_y, xx, yy), fill=mortar, width=1)
            xx += step_x
        row += 1
        yy += step_y


def draw_building_volume(im, d, parent, mass, cr, cx, cy, W, H, P, night):
    x, y, w, h = (f(mass, k, f(parent, k)) for k in ('x','y','w','h'))
    x0, y0 = tf((x, y), cx, cy, W, H)
    x1, y1 = tf((x+w, y+h), cx, cy, W, H)
    if x1 < -80 or y1 < -80 or x0 > W+80 or y0 > H+80:
        return
    seed = stable_int(f"{cr.get('archetype_id', parent['id'])}:{mass.get('massing_id','')}")
    fam = family(cr.get('archetype_id', ''))
    wall = wall_color(fam, seed, night)
    roof = (142, 137, 121) if fam not in ('industrial','warehouse','parking_garage') else (108, 118, 116)
    if night:
        roof = tuple(int(v*.52) for v in roof)
    hs = f(mass, 'height_scale', 1.0)
    ex = sc(12 * hs)
    ey = sc(22 * hs)
    # Pass 18 shadow contract: the map/preview only carries restrained contact AO.
    # Large directional cast shadows belong to the runtime/viewer so they remain
    # correct when the outdoor camera rotates and when elevated levels overlap.
    ao = max(1, sc(3))
    d.rectangle((x0+ao, y0+ao, x1+ao, y1+ao), fill=P['shadow'])
    front = tuple(int(v*.82) for v in wall)
    right = tuple(int(v*.65) for v in wall)
    d.polygon([(x0,y1),(x1,y1),(x1+ex,y1+ey),(x0+ex,y1+ey)], fill=front, outline=P['shadow'])
    d.polygon([(x1,y0),(x1+ex,y0+ey),(x1+ex,y1+ey),(x1,y1)], fill=right, outline=P['shadow'])
    # Roof texture clipped to volume.
    rw, rh = max(1, int(x1-x0)), max(1, int(y1-y0))
    if rw > 1 and rh > 1:
        rooftex = material('roof_tar_night.png' if night else 'roof_tar_day.png')
        if rooftex:
            patch = Image.new('RGB', (rw, rh), roof)
            tw, th = rooftex.size
            for ty in range(0, rh, th):
                for tx in range(0, rw, tw):
                    patch.paste(rooftex, (tx, ty))
            im.paste(patch, (int(x0), int(y0)))
            d = ImageDraw.Draw(im)
        else:
            d.rectangle((x0,y0,x1,y1), fill=roof)
    d.rectangle((x0,y0,x1,y1), outline=P['shadow'], width=max(1,sc(2)))
    inset = sc(6)
    if rw > sc(40) and rh > sc(38):
        d.rectangle((x0+inset,y0+inset,x1-inset,y1-inset), outline=tuple(int(v*.75) for v in roof), width=max(1,sc(2)))
    # Brick/stone facade texture and multi-row windows.
    if fam in ('brick_midrise','brownstone_row','painted_walkup','commercial_corner','commercial_lowrise','waterfront_midrise'):
        draw_brick_face(d, (x0, y1, x1, y1+ey), front, night)
    win_dark = (36,54,62) if not night else (18,30,36)
    win_lit = (236,184,89)
    cols = max(2, min(12, int(max(1,(x1-x0))/sc(38))))
    rows = 2 if ey >= sc(20) else 1
    for rr in range(rows):
        for cc in range(cols):
            xx = x0 + (cc+1)*(x1-x0)/(cols+1)
            yy = y1 + (rr+1)*ey/(rows+1)
            lit = night and stable_int(f"win:{parent['id']}:{mass.get('massing_id')}:{rr}:{cc}") % 5 in (0,1)
            wc = win_lit if lit else win_dark
            ww = max(2, sc(4)); hh = max(2, sc(4))
            d.rectangle((xx-ww,yy-hh,xx+ww,yy+hh), fill=wc, outline=(177,162,132) if not night else (78,72,61))
    # Rooftop HVAC/skylights/water tower.
    n = max(1, min(10, int((w*h)/32000)+1))
    for k in range(n):
        z = stable_int(f"roof:{parent['id']}:{mass.get('massing_id')}:{k}")
        bw = sc(10 + z%20); bh = sc(7 + (z>>5)%14)
        maxx = max(1, int((x1-x0)-bw-sc(22))); maxy = max(1, int((y1-y0)-bh-sc(22)))
        xx = x0 + sc(10) + (z>>9)%maxx; yy = y0 + sc(10) + (z>>17)%maxy
        d.rectangle((xx+sc(3),yy+sc(3),xx+bw+sc(3),yy+bh+sc(3)), fill=(36,40,41))
        d.rectangle((xx,yy,xx+bw,yy+bh), fill=(116,122,118) if not night else (57,63,62), outline=(46,51,50))
        if bw>sc(16): d.line((xx+sc(3),yy+sc(3),xx+bw-sc(3),yy+sc(3)), fill=(166,168,156) if not night else (83,84,78), width=1)
    if seed % 5 == 0 and w > 86 and h > 86:
        tx = x0 + (x1-x0)*.68; ty = y0 + (y1-y0)*.28
        d.line((tx-sc(6),ty+sc(8),tx-sc(10),ty+sc(24)),fill=(67,54,40),width=max(1,sc(2)))
        d.line((tx+sc(6),ty+sc(8),tx+sc(10),ty+sc(24)),fill=(67,54,40),width=max(1,sc(2)))
        d.ellipse((tx-sc(12),ty-sc(8),tx+sc(12),ty+sc(5)),fill=(139,91,51),outline=(62,48,36))
        d.rectangle((tx-sc(11),ty-sc(1),tx+sc(11),ty+sc(10)),fill=(121,78,47),outline=(62,48,36))
    if fam in ('commercial_corner','commercial_lowrise') and (x1-x0)>sc(75):
        d.rectangle((x0+sc(10),y1-sc(4),min(x1-sc(10),x0+sc(155)),y1+sc(3)),fill=(187,57,47),outline=(78,43,38))


def draw_arrow(d, a, b, P):
    dx, dy = b[0]-a[0], b[1]-a[1]
    L = math.hypot(dx,dy)
    if L < sc(150):
        return
    ux,uy=dx/L,dy/L; mx=a[0]+ux*L*.56; my=a[1]+uy*L*.56; vx,vy=-uy,ux
    tail=(mx-ux*sc(18),my-uy*sc(18)); tip=(mx+ux*sc(18),my+uy*sc(18))
    d.line((tail,tip),fill=P['lane'],width=max(2,sc(4)))
    d.polygon([(tip[0]+ux*sc(9),tip[1]+uy*sc(9)),(tip[0]-ux*sc(5)+vx*sc(8),tip[1]-uy*sc(5)+vy*sc(8)),(tip[0]-ux*sc(5)-vx*sc(8),tip[1]-uy*sc(5)-vy*sc(8))],fill=P['lane'])


def surface_masks(W,H,cx,cy,P,night):
    masks = {k: Image.new('L',(W,H),0) for k in ('water','green','sidewalk','curb','road','alley')}
    for fn,key in [('water_polygons.csv','water'),('green_polygons.csv','green')]:
        md=ImageDraw.Draw(masks[key])
        for poly in pts(fn,'polygon_id').values():
            q=[tf(z,cx,cy,W,H) for z in poly]
            if len(q)>=3: md.polygon(q,fill=255)
    roads=read('roads.csv'); rp=pts('road_points.csv','road_id')
    for layer in ('sidewalk','curb','road'):
        md=ImageDraw.Draw(masks[layer])
        for r in roads:
            q=visual_road_points(r,rp,cx,cy,W,H)
            if len(q)<2: continue
            n=lanes(r); rw=max(38,n*38+10); hw=(r.get('highway') or '').lower(); sw=0 if hw.startswith('motorway') else max(28,f(r,'sidewalk_width',28)); cw=max(4,f(r,'curb_width',4))
            width={'sidewalk':rw+2*(sw+cw),'curb':rw+2*cw,'road':rw}[layer]
            md.line(q,fill=255,width=max(1,sc(width)),joint='curve')
    md=ImageDraw.Draw(masks['alley'])
    for o in read(COS/'layout_overlays.csv'):
        if o.get('kind')!='service_alley': continue
        x0,y0=tf((f(o,'x'),f(o,'y')),cx,cy,W,H); x1,y1=tf((f(o,'x')+f(o,'w'),f(o,'y')+f(o,'h')),cx,cy,W,H)
        md.rectangle((x0,y0,x1,y1),fill=220)
    return masks



def draw_street_edge_accents(d, roads, rp, cx, cy, W, H, P, night):
    """Cosmetic-only street-edge definition for GTA2-style top-down readability.

    Geometry stays authoritative in the road/sidewalk masks.  These thin seams
    simply make the asphalt -> curb -> sidewalk sequence readable at night.
    """
    inner = (176, 166, 143) if night else (239, 229, 204)
    outer = (62, 62, 58) if night else (132, 126, 113)
    for r in roads:
        hw=(r.get('highway') or '').lower()
        if hw.startswith('motorway'):
            continue
        q=visual_road_points(r,rp,cx,cy,W,H)
        if len(q)<2:
            continue
        n=lanes(r); rw=max(38,n*38+10)
        sw=max(28,f(r,'sidewalk_width',28)); cw=max(4,f(r,'curb_width',4))
        # Asphalt/curb seam and outside sidewalk seam. Segment-by-segment keeps
        # the pass completely cosmetic and avoids changing semantic road points.
        for sign in (-1,1):
            inner_q=parallel_polyline(q,sign*(rw*.5+cw*.42))
            outer_q=parallel_polyline(q,sign*(rw*.5+cw+sw))
            d.line(inner_q,fill=inner,width=max(1,sc(2)),joint='curve')
            d.line(outer_q,fill=outer,width=max(1,sc(1)),joint='curve')



def _seg_intersection(a,b,c,d):
    """Return world-space segment intersection or None."""
    x1,y1=a; x2,y2=b; x3,y3=c; x4,y4=d
    den=(x1-x2)*(y3-y4)-(y1-y2)*(x3-x4)
    if abs(den)<1e-8:
        return None
    t=((x1-x3)*(y3-y4)-(y1-y3)*(x3-x4))/den
    u=-((x1-x2)*(y1-y3)-(y1-y2)*(x1-x3))/den
    if -1e-6 <= t <= 1+1e-6 and -1e-6 <= u <= 1+1e-6:
        return (x1+t*(x2-x1), y1+t*(y2-y1))
    return None


@lru_cache(maxsize=1)
def same_level_junctions():
    """Geometric junction cores for drivable roads sharing an elevation level."""
    roads=read('roads.csv'); rp=pts('road_points.csv','road_id')
    pedestrian={'footway','path','cycleway','steps','pedestrian'}
    rr=[]
    for r in roads:
        if (r.get('highway') or '').lower() in pedestrian:
            continue
        q=rp.get(r['road_id'],[])
        if len(q)<2: continue
        rr.append((r,q,i(r,'level',0),max(38,lanes(r)*38+10)))
    raw=[]
    for ai in range(len(rr)):
        ra,qa,la,wa=rr[ai]
        ax=[p[0] for p in qa]; ay=[p[1] for p in qa]
        ab=(min(ax),min(ay),max(ax),max(ay))
        for bi in range(ai+1,len(rr)):
            rb,qb,lb,wb=rr[bi]
            if la!=lb: continue
            bx=[p[0] for p in qb]; by=[p[1] for p in qb]
            bb=(min(bx),min(by),max(bx),max(by))
            pad=max(wa,wb)*.55+12
            if ab[2]+pad<bb[0] or bb[2]+pad<ab[0] or ab[3]+pad<bb[1] or bb[3]+pad<ab[1]:
                continue
            for a,b in zip(qa,qa[1:]):
                for c,d in zip(qb,qb[1:]):
                    hit=_seg_intersection(a,b,c,d)
                    if hit is not None:
                        raw.append((hit[0],hit[1],min(190,max(42,max(wa,wb)*.72+26))))
    # Merge near-duplicate segment hits around the same junction.
    merged=[]
    for x,y,r in raw:
        found=False
        for idx,(mx,my,mr,n) in enumerate(merged):
            if math.hypot(x-mx,y-my) <= max(26,min(r,mr)*.6):
                merged[idx]=((mx*n+x)/(n+1),(my*n+y)/(n+1),max(mr,r),n+1)
                found=True; break
        if not found: merged.append((x,y,r,1))
    return [(x,y,r) for x,y,r,_ in merged]

def clear_junction_markings(im, masks, cx, cy, W, H, P, night):
    """Repaint only asphalt inside crossing/junction approach cores.

    This removes lane-line spaghetti from complex intersections without touching
    sidewalks/curbs or changing the semantic road graph. Crosswalks and stop bars
    are drawn afterward on the cleaned asphalt.
    """
    clean=Image.new('L',(W,H),0)
    cd=ImageDraw.Draw(clean)
    count=0
    for c in read('crosswalks.csv'):
        sx,sy=tf((f(c,'x'),f(c,'y')),cx,cy,W,H)
        if sx < -120 or sy < -120 or sx > W+120 or sy > H+120:
            continue
        length=max(96,f(c,'length',96))*VIEW_SCALE
        width=max(34,f(c,'width',38))*VIEW_SCALE
        rad=max(sc(38), min(sc(150), max(width*1.02,length*.27)+sc(16)))
        cd.ellipse((sx-rad,sy-rad,sx+rad,sy+rad),fill=255)
        count+=1
    # Also clear true same-level road intersections. Grade-separated crossings
    # are deliberately excluded by the level equality test.
    for wx,wy,wr in same_level_junctions():
        sx,sy=tf((wx,wy),cx,cy,W,H); rad=max(sc(30),wr*VIEW_SCALE)
        if sx < -rad or sy < -rad or sx > W+rad or sy > H+rad: continue
        cd.ellipse((sx-rad,sy-rad,sx+rad,sy+rad),fill=255); count+=1
    if not count:
        return
    road_only=ImageChops.multiply(clean,masks['road'])
    apply_mask(im,road_only,'asphalt_night.png' if night else 'asphalt_day.png',P['road'])


def draw_interior_entrances(im, cx, cy, W, H, night):
    """Small exterior door thresholds for the ten enterable isometric interiors."""
    d=ImageDraw.Draw(im)
    for it in read('interiors.csv'):
        x,y=tf((f(it,'entry_x'),f(it,'entry_y')),cx,cy,W,H)
        if not (-30<x<W+30 and -30<y<H+30): continue
        kind=(it.get('kind') or '').lower()
        edge=(224,190,87) if night else (174,118,48)
        fill=(83,49,31) if night else (117,72,43)
        if kind in {'shop','diner','club'}: edge=(238,176,74) if night else (194,113,42)
        rr=max(3,sc(5)); ww=max(5,sc(9)); hh=max(4,sc(7))
        d.rectangle((x-ww,y-hh,x+ww,y+hh),fill=fill,outline=edge,width=max(1,sc(2)))
        if night:
            d.ellipse((x-rr,y-hh-rr*2,x+rr,y-hh),fill=(255,205,100))


def draw_parked_vehicle_silhouettes(d, cx, cy, W, H, night):
    palette=[(97,102,105),(126,69,58),(55,74,91),(119,112,85),(72,79,69)]
    for car in read('parked_vehicles.csv'):
        x,y=tf((f(car,'x'),f(car,'y')),cx,cy,W,H)
        if not (-40<x<W+40 and -40<y<H+40): continue
        ang=math.radians(f(car,'angle',0)); ux,uy=math.cos(ang),math.sin(ang); vx,vy=-uy,ux
        hl=max(5,sc(13)); hw=max(3,sc(6))
        poly=[(x+ux*hl+vx*hw,y+uy*hl+vy*hw),(x+ux*hl-vx*hw,y+uy*hl-vy*hw),(x-ux*hl-vx*hw,y-uy*hl-vy*hw),(x-ux*hl+vx*hw,y-uy*hl+vy*hw)]
        col=palette[stable_int('parked:'+str(car.get('id')))%len(palette)]
        if night: col=tuple(int(v*.72) for v in col)
        d.polygon(poly,fill=col,outline=(24,27,28))
        # windshield cue keeps tiny silhouettes readable as top-down cars.
        wx=x+ux*hl*.34; wy=y+uy*hl*.34
        d.line((wx-vx*hw*.65,wy-vy*hw*.65,wx+vx*hw*.65,wy+vy*hw*.65),fill=(111,132,139) if not night else (55,72,79),width=max(1,sc(2)))

def draw_waterfront_edges(d,cx,cy,W,H,night):
    base=(48,55,57) if night else (89,94,91)
    hi=(116,122,116) if night else (161,158,145)
    for e in read(COS/'waterfront_edges.csv'):
        a=tf((f(e,'x1'),f(e,'y1')),cx,cy,W,H); b=tf((f(e,'x2'),f(e,'y2')),cx,cy,W,H)
        if max(a[0],b[0])<-40 or max(a[1],b[1])<-40 or min(a[0],b[0])>W+40 or min(a[1],b[1])>H+40:continue
        d.line((a,b),fill=base,width=max(2,sc(7)))
        d.line((a,b),fill=hi,width=max(1,sc(2)))
        dx=b[0]-a[0];dy=b[1]-a[1];L=math.hypot(dx,dy)
        if L<12:continue
        ux,uy=dx/L,dy/L;nx,ny=-uy,ux; spacing=max(18,sc(f(e,'railing_spacing_px',96)))
        t=spacing*.5
        while t<L-spacing*.25:
            x=a[0]+ux*t;y=a[1]+uy*t
            d.line((x-nx*sc(3),y-ny*sc(3),x+nx*sc(3),y+ny*sc(3)),fill=hi,width=max(1,sc(1)))
            t+=spacing

def draw_bridge_edge_barriers(d,roads,rp,cx,cy,W,H,night):
    base=(39,45,47) if night else (91,94,90); hi=(121,127,124) if night else (177,174,159)
    for r in roads:
        if str(r.get('bridge','')).lower() not in {'1','true','yes'}:continue
        q=visual_road_points(r,rp,cx,cy,W,H)
        if len(q)<2:continue
        off=max(sc(14),f(r,'width',120)*VIEW_SCALE*.5-sc(4))
        for side in (-1,1):
            edge=parallel_polyline(q,off*side)
            d.line(edge,fill=base,width=max(2,sc(7)),joint='curve')
            d.line(edge,fill=hi,width=max(1,sc(2)),joint='curve')

def render(view, night=False, *, annotate=True, output_dir=None, yellow_center_lines=True,
           additional_buildings=None):
    global VIEW_SCALE
    views={r['view_id']:r for r in read(ROOT/'config'/'preview_views.csv')}
    v=views[view]; W=i(v,'width',1280); H=i(v,'height',720); cx=f(v,'center_x'); cy=f(v,'center_y'); VIEW_SCALE=f(v,'scale',1.0); P=NIGHT if night else DAY
    im=tiled_texture('land_night.png' if night else 'land_day.png',(W,H),P['land'])
    masks=surface_masks(W,H,cx,cy,P,night)
    apply_mask(im,masks['water'],'water_night.png' if night else 'water_day.png',P['water'])
    apply_mask(im,masks['green'],'grass_night.png' if night else 'grass_day.png',P['green'])
    apply_mask(im,masks['sidewalk'],'sidewalk_night.png' if night else 'sidewalk_day.png',P['sidewalk'])
    apply_mask(im,masks['curb'],'curb_night.png' if night else 'curb_day.png',P['curb'])
    apply_mask(im,masks['road'],'asphalt_night.png' if night else 'asphalt_day.png',P['road'])
    apply_mask(im,masks['alley'],'asphalt_night.png' if night else 'asphalt_day.png',P['alley'])
    d=ImageDraw.Draw(im)
    # Five intentional small car parks are semantic destinations, not accidental dead ends.
    for lot in read('parking_regions.csv'):
        x0,y0=tf((f(lot,'x'),f(lot,'y')),cx,cy,W,H);x1,y1=tf((f(lot,'x')+f(lot,'w'),f(lot,'y')+f(lot,'h')),cx,cy,W,H)
        if x1<0 or y1<0 or x0>W or y0>H:continue
        d.rectangle((x0,y0,x1,y1),fill=(31,35,37) if night else (60,64,65),outline=P['curb'],width=max(1,sc(4)))
        # simple orthographic bay markings
        bay=max(sc(28),1);margin=sc(14);xx=x0+margin
        while xx<x1-margin:
            d.line((xx,y0+margin,xx,y1-margin),fill=P['lane'],width=max(1,sc(2)));xx+=bay
    # Parking/service courts and plazas from layout overlays.
    for o in read(COS/'layout_overlays.csv'):
        if o.get('kind') not in {'roof_courtyard'}: continue
        # roof courtyards are drawn after building volumes; skip here
        pass
    roads=read('roads.csv'); rp=pts('road_points.csv','road_id')
    for r in roads:
        q=visual_road_points(r,rp,cx,cy,W,H)
        if len(q)<2: continue
        n=lanes(r); lw=38
        if n>=2 and yellow_center_lines:
            for off0 in (-3,3):
                qq=parallel_polyline(q,off0); d.line(qq,fill=P['yellow'],width=max(1,sc(2)),joint='curve')
        for k in range(1,n):
            off0=(k-n/2)*lw
            if abs(off0)<lw*.28: continue
            dashed_polyline(d,parallel_polyline(q,off0),P['lane'],2)
        if n>=3:
            # Keep sparse arrows on the semantic direction while the visible ribbon is rounded.
            for a,b in zip(q[::max(1,len(q)//4)],q[1::max(1,len(q)//4)]): draw_arrow(d,a,b,P)
    cos=grouped_cosmetics(); mass=grouped_massing(); buildings={b['id']:b for b in read('buildings.csv')}
    for bid,b in buildings.items():
        volumes=mass.get(bid) or [dict(b, massing_id=f'm_{bid}_0',height_scale=1)]
        for m in volumes:
            draw_building_volume(im,ImageDraw.Draw(im),b,m,cos.get(f'building:{bid}',{}),cx,cy,W,H,P,night)
    for b in additional_buildings or []:
        draw_building_volume(im, ImageDraw.Draw(im), b,
                             dict(b, massing_id=f"iterated_{b['id']}", height_scale=b.get('height_scale', 1)),
                             {'archetype_id': b.get('archetype_id', '')}, cx, cy, W, H, P, night)

    # GTA2-style top-down readability gate: 2.5D facade/shadow extrusion is cosmetic
    # and must never paint over a traversable street. Re-apply the authoritative
    # sidewalk/curb/asphalt masks after buildings, then restore lane markings.
    apply_mask(im,masks['sidewalk'],'sidewalk_night.png' if night else 'sidewalk_day.png',P['sidewalk'])
    apply_mask(im,masks['curb'],'curb_night.png' if night else 'curb_day.png',P['curb'])
    apply_mask(im,masks['road'],'asphalt_night.png' if night else 'asphalt_day.png',P['road'])
    apply_mask(im,masks['alley'],'asphalt_night.png' if night else 'asphalt_day.png',P['alley'])
    d=ImageDraw.Draw(im)
    draw_street_edge_accents(d, roads, rp, cx, cy, W, H, P, night)
    for r in roads:
        q=visual_road_points(r,rp,cx,cy,W,H)
        if len(q)<2: continue
        n=lanes(r); lw=38
        if n>=2 and yellow_center_lines:
            for off0 in (-3,3):
                qq=parallel_polyline(q,off0); d.line(qq,fill=P['yellow'],width=max(1,sc(2)),joint='curve')
        for k in range(1,n):
            off0=(k-n/2)*lw
            if abs(off0)<lw*.28: continue
            dashed_polyline(d,parallel_polyline(q,off0),P['lane'],2)
        if n>=3:
            # Keep sparse arrows on the semantic direction while the visible ribbon is rounded.
            for a,b in zip(q[::max(1,len(q)//4)],q[1::max(1,len(q)//4)]): draw_arrow(d,a,b,P)

    # Pass 20: clean markings out of complex junction/crossing cores, then draw
    # authored crossing geometry on top. This is cosmetic-only.
    clear_junction_markings(im, masks, cx, cy, W, H, P, night)
    d=ImageDraw.Draw(im)
    # Roof courtyards/lightwells are explicitly cosmetic and stay inside parent footprints.
    for o in read(COS/'layout_overlays.csv'):
        if o.get('kind')!='roof_courtyard': continue
        x0,y0=tf((f(o,'x'),f(o,'y')),cx,cy,W,H);x1,y1=tf((f(o,'x')+f(o,'w'),f(o,'y')+f(o,'h')),cx,cy,W,H)
        if x1<0 or y1<0 or x0>W or y0>H: continue
        d.rectangle((x0,y0,x1,y1),fill=(57,60,58) if not night else (27,31,31),outline=(29,33,33) if not night else (12,15,15),width=max(1,sc(2)))
        d.rectangle((x0+sc(5),y0+sc(5),x1-sc(5),y1-sc(5)),outline=(114,113,103) if not night else (55,57,54),width=1)
    # Authored crosswalks.
    for c in read('crosswalks.csv'):
        x,y=f(c,'x'),f(c,'y');ang=math.radians(f(c,'angle'));sx,sy=tf((x,y),cx,cy,W,H);length=max(78,f(c,'length'));width=max(18,f(c,'width'));stripe=max(3,f(c,'stripe_width',4));gap=max(4,f(c,'stripe_gap',5));ux,uy=math.cos(ang),math.sin(ang);vx,vy=-uy,ux;n=max(3,int(math.ceil((width+gap)/(stripe+gap))))
        for j in range(n):
            oo=(j-(n-1)/2)*(stripe+gap)*VIEW_SCALE;mx=sx+ux*oo;my=sy+uy*oo;p1=(mx-vx*length*VIEW_SCALE/2,my-vy*length*VIEW_SCALE/2);p2=(mx+vx*length*VIEW_SCALE/2,my+vy*length*VIEW_SCALE/2);d.line((p1,p2),fill=P['lane'],width=max(2,sc(stripe)))
        # Thin stop bars just outside the zebra improve junction approach readability.
        stop_gap=max(10,f(c,'stop_bar_gap',12)); stop_col=tuple(max(0,int(v*.80)) for v in P['lane'])
        for sign in (-1,1):
            off=(width*.5+stop_gap)*VIEW_SCALE; mx=sx+vx*sign*off; my=sy+vy*sign*off
            p1=(mx-ux*length*VIEW_SCALE*.46,my-uy*length*VIEW_SCALE*.46);p2=(mx+ux*length*VIEW_SCALE*.46,my+uy*length*VIEW_SCALE*.46)
            d.line((p1,p2),fill=stop_col,width=max(2,sc(3)))
    # Pass 34: fixed waterfront retaining rails + elevated bridge deck barriers.
    draw_waterfront_edges(d,cx,cy,W,H,night)
    draw_bridge_edge_barriers(d,roads,rp,cx,cy,W,H,night)
    # Semantic props + denser cosmetic-only dressing, both reuse the 100-object pack.
    def paste_prop(aid,x,y,size):
        sp=load_sprite(aid,night)
        if sp is None:return
        size=max(12,int(size*VIEW_SCALE));sp=sp.resize((size,size),Image.Resampling.NEAREST);im.paste(sp,(int(x-size/2),int(y-size*.72)),sp)
    for p in read('street_props.csv'):
        x,y=tf((f(p,'x'),f(p,'y')),cx,cy,W,H)
        if not (-90<x<W+90 and -90<y<H+90):continue
        cr=cos.get(f'prop:{p.get("id")}',{});kind=p.get('kind','')
        if kind=='edge_tunnel':
            angle=math.radians(f(p,'rotation'));ux,uy=math.cos(angle),math.sin(angle);nx,ny=-uy,ux
            width=max(46,80*f(p,'scale',1))*VIEW_SCALE;length=max(68,46+width*.22)*VIEW_SCALE
            def corner(along,across):return (x+ux*along+nx*across,y+uy*along+ny*across)
            d.polygon([corner(-length*.5,-width*.62),corner(length*.5,-width*.62),corner(length*.5,width*.62),corner(-length*.5,width*.62)],fill=(7,9,10))
            d.line((corner(-length*.34,-width*.62),corner(-length*.34,width*.62)),fill=(126,123,111),width=max(3,sc(8)))
            d.line((corner(-length*.25,-width*.5),corner(-length*.25,width*.5)),fill=(211,179,65),width=max(2,sc(3)))
            continue
        size=72 if kind=='street_tree' else (58 if kind=='curved_streetlamp' else (32 if kind=='fire_hydrant' else 46));paste_prop(cr.get('archetype_id',''),x,y,size)
    for p in read(COS/'street_dressing.csv'):
        x,y=tf((f(p,'x'),f(p,'y')),cx,cy,W,H)
        if not (-90<x<W+90 and -90<y<H+90):continue
        base=96 if p.get('kind')=='tree' else 48;paste_prop(p.get('archetype_id',''),x,y,base*f(p,'scale',.5))
    d=ImageDraw.Draw(im)
    # 2.5D sign anchors.
    for s in read(COS/'road_sign_anchors.csv'):
        x,y=tf((f(s,'x'),f(s,'y')),cx,cy,W,H)
        if not (-130<x<W+130 and -130<y<H+130):continue
        h=sc(f(s,'height_px',40));ww=sc(98 if s['semantic_type']=='directional' else 60);metal=(93,101,100) if not night else (49,55,56);green=(30,100,65) if not night else (19,64,43)
        # Sign anchors are now roadside/verge points. Keep both physical support feet
        # tightly around that legal anchor instead of spanning the road surface.
        post_sep=max(sc(4),min(sc(8),ww*.09))
        d.line((x-post_sep,y,x-post_sep,y-h),fill=metal,width=max(2,sc(4)));d.line((x+post_sep,y,x+post_sep,y-h),fill=metal,width=max(2,sc(4)));board=(x-ww/2-sc(3),y-h-sc(22),x+ww/2+sc(3),y-h+sc(4));d.rectangle(board,fill=green,outline=(211,213,193),width=max(1,sc(2)));label=(s.get('label') or '')[:18];
        if label: d.text((x-ww/2+sc(4),y-h-sc(18)),label,font=font(max(7,sc(9))),fill=(245,245,228))
    # GWB cables.
    cable_col=(145,154,154) if not night else (73,84,87)
    for cb in read(COS/'bridge_cables.csv'):
        p1=tf((f(cb,'x1'),f(cb,'y1')),cx,cy,W,H);p2=tf((f(cb,'x2'),f(cb,'y2')),cx,cy,W,H);avg_world=(f(cb,'y1')+f(cb,'y2'))*.5;sag=f(cb,'sag_px',60)*VIEW_SCALE;curve=[]
        for j in range(33):
            t=j/32;x=p1[0]*(1-t)+p2[0]*t;basey=p1[1]*(1-t)+p2[1]*t;y=basey+sag*4*t*(1-t);curve.append((x,y))
        d.line(curve,fill=cable_col,width=max(1,sc(f(cb,'line_width_px',2))))
        spacing=max(65,f(cb,'suspender_spacing_px',95));worldL=math.hypot(f(cb,'x2')-f(cb,'x1'),f(cb,'y2')-f(cb,'y1'));count=max(2,int(worldL/spacing))
        for j in range(1,count):
            t=j/count;x=p1[0]*(1-t)+p2[0]*t;basey=p1[1]*(1-t)+p2[1]*t;y=basey+sag*4*t*(1-t);deck_y=tf((0,3925 if avg_world<3964 else 4004),cx,cy,W,H)[1];d.line((x,y,x,deck_y),fill=cable_col,width=max(1,sc(1)))
    for lm in read(COS/'landmark_anchors.csv'):
        x,y=tf((f(lm,'x'),f(lm,'y')),cx,cy,W,H)
        if not (-300<x<W+300 and -300<y<H+300):continue
        sp=load_sprite(lm.get('archetype_id',''),night)
        if sp is None:continue
        size=max(40,int(128*f(lm,'scale',1)*VIEW_SCALE));sp=sp.resize((size,size),Image.Resampling.NEAREST);im.paste(sp,(int(x-size/2),int(y-size*.72)),sp)
    # Night atmosphere and local pools of light remain independent from all geometry/cosmetics.
    if night:
        im=Image.alpha_composite(im.convert('RGBA'),Image.new('RGBA',(W,H),(5,9,14,72)))
        lights=Image.new('RGBA',(W,H),(0,0,0,0));ld=ImageDraw.Draw(lights,'RGBA');colors={'warm':(255,184,82),'cool':(94,157,216),'amber':(247,159,70),'green':(94,180,109),'red':(226,68,65),'blue':(74,113,238)}
        for l in read(COS/'light_emitters.csv'):
            x,y=tf((f(l,'x'),f(l,'y')),cx,cy,W,H);rad=f(l,'radius_px',130)*VIEW_SCALE
            if x+rad<0 or y+rad<0 or x-rad>W or y-rad>H:continue
            col=colors.get(l.get('color_tag'),(235,176,90));alpha=int(72*min(1.25,max(.1,f(l,'intensity',.5))));ld.ellipse((x-rad,y-rad,x+rad,y+rad),fill=(*col,alpha))
        lights=lights.filter(ImageFilter.GaussianBlur(max(12,sc(34))));im=Image.alpha_composite(im,lights).convert('RGB')
    if annotate:
        dd=ImageDraw.Draw(im);dd.rectangle((12,12,520,54),fill=(10,13,14));dd.text((23,20),f'{view.upper()} — {"NIGHT" if night else "DAY"} — APPROVED NYC / GTA2 CALLBACK',font=font(15),fill=(244,242,228))
    target = Path(output_dir) if output_dir else OUT
    target.mkdir(parents=True, exist_ok=True)
    p=target/f'{view}_callback_{"night" if night else "day"}.png';im.save(p);return p


def sheet(view):
    day=Image.open(render(view,False)).convert('RGB');night=Image.open(render(view,True)).convert('RGB');W,H=day.size;out=Image.new('RGB',(W,H*2+62),(24,25,24));out.paste(day,(0,31));out.paste(night,(0,H+62));d=ImageDraw.Draw(out);d.text((14,6),'SAME GAME STRUCTURE — SWAPPABLE COSMETICS + EDITABLE TEXTURES + INDEPENDENT LIGHTING',font=font(16),fill=(238,237,226));p=OUT/f'{view}_qualitative_style_sheet.png';out.save(p);return p


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--view',action='append')
    ap.add_argument('--mode',choices=['night','day','both'],default='night',help='OPEN NIGHT defaults to night with authored street-lamp lighting')
    a=ap.parse_args();vs=a.view or ['fortlee','gwb','washington_heights']
    for v in vs:
        if a.mode == 'both': print(sheet(v))
        elif a.mode == 'day': print(render(v,False))
        else: print(render(v,True))


if __name__=='__main__':main()
