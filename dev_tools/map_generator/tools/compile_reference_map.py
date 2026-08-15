from __future__ import annotations

import argparse
import csv
import hashlib
import math
import shutil
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
TRACE=ROOT/'working_reference'; BASE=ROOT/'mapfiles'/'data'/'map_001_gwb_corridor'; STAGE=TRACE/'compiled_map'


def rows(p):
    if not p.exists(): return []
    with p.open('r',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def write(p,fields,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)

def points(s):
    out=[]
    for pair in str(s or '').split(';'):
        if not pair.strip():continue
        x,y=pair.split(',',1);out.append((float(x),float(y)))
    return out

def dimensions():
    ref=ROOT/'references'/'street_map_reference.png'
    if not ref.exists():raise SystemExit('Import a reference image first.')
    with Image.open(ref) as im:return im.size

def settings():
    return {r['key']:r['value'] for r in rows(ROOT/'config'/'reference_map_settings.csv') if r.get('key')}

def geometry_settings():
    return {r['key']:r['value'] for r in rows(ROOT/'config'/'map_geometry_settings.csv') if r.get('key')}

def world():
    d=settings();return float(d.get('world_width_px',24576)),float(d.get('world_height_px',8192))

_ORTHO_CACHE = None

def _orth_error_deg(angle_deg, rotation_deg):
    a=(float(angle_deg)+float(rotation_deg))%90.0
    return min(a,90.0-a)

def orthogonalization_angle():
    """Return one rigid rotation for the *entire* screenshot-derived map.

    The angle is selected only when it materially reduces length-weighted deviation
    from an orthogonal street grid.  It never performs a perspective/homography warp;
    every semantic layer uses this same rigid rotation.
    """
    global _ORTHO_CACHE
    if _ORTHO_CACHE is not None:return _ORTHO_CACHE
    cfg=settings()
    enabled=str(cfg.get('global_orthogonalization','true')).lower() in {'1','true','yes','on'}
    if not enabled:
        _ORTHO_CACHE=(0.0,0.0,0.0);return _ORTHO_CACHE
    segs=[]
    for r in rows(TRACE/'roads_trace.csv'):
        ps=points(r.get('points_image_px'))
        for a,b in zip(ps,ps[1:]):
            dx=b[0]-a[0];dy=b[1]-a[1];L=math.hypot(dx,dy)
            if L<8:continue
            segs.append((math.degrees(math.atan2(dy,dx))%180.0,L))
    if not segs:
        _ORTHO_CACHE=(0.0,0.0,0.0);return _ORTHO_CACHE
    def score(rot):
        den=sum(w for _,w in segs) or 1.0
        return math.sqrt(sum(w*_orth_error_deg(a,rot)**2 for a,w in segs)/den)
    baseline=score(0.0)
    maxrot=max(0.0,min(44.0,float(cfg.get('orthogonalization_max_rotation_deg',35))))
    step=max(.05,float(cfg.get('orthogonalization_step_deg',.2)))
    count=int(round((2*maxrot)/step))
    candidates=[-maxrot+i*step for i in range(count+1)]
    best=min(candidates,key=score);best_score=score(best)
    improve=100.0*(baseline-best_score)/max(baseline,1e-9)
    minimum=float(cfg.get('orthogonalization_min_improvement_pct',8))
    if improve<minimum:best=0.0;best_score=baseline;improve=0.0
    _ORTHO_CACHE=(round(best,3),round(baseline,3),round(improve,2))
    return _ORTHO_CACHE

def _reference_transform_spec():
    iw,ih=dimensions();ww,wh=world();rot,_,_=orthogonalization_angle();th=math.radians(rot);c=math.cos(th);s=math.sin(th);cx=iw/2;cy=ih/2
    def rr(x,y):
        dx=x-cx;dy=y-cy
        return (dx*c-dy*s,dx*s+dy*c)
    corners=[rr(0,0),rr(iw,0),rr(iw,ih),rr(0,ih)]
    minx=min(x for x,_ in corners);maxx=max(x for x,_ in corners);miny=min(y for _,y in corners);maxy=max(y for _,y in corners)
    bw=maxx-minx;bh=maxy-miny;scale=min(ww/max(bw,1),wh/max(bh,1));ox=(ww-bw*scale)*.5;oy=(wh-bh*scale)*.5
    return rot,c,s,cx,cy,minx,miny,scale,ox,oy

def transform(ps):
    """Rigidly rotate then uniformly contain the reference map in world space.

    This preserves the full screenshot geography and strict GTA2-style orthographic
    projection.  There is no anisotropic scaling and no perspective skew.
    """
    rot,c,s,cx,cy,minx,miny,scale,ox,oy=_reference_transform_spec()
    out=[]
    for x,y in ps:
        dx=x-cx;dy=y-cy;rx=dx*c-dy*s;ry=dx*s+dy*c
        out.append((round(ox+(rx-minx)*scale,2),round(oy+(ry-miny)*scale,2)))
    return out

def road_spec(c,lane_hint):
    table={'motorway':(240,6,'motorway'),'trunk':(176,4,'trunk'),'primary':(144,4,'primary'),'secondary':(108,2,'secondary'),'local':(72,2,'residential'),'residential':(72,2,'residential'),'service':(52,1,'service')}
    w,l,h=table.get(str(c).lower(),table['local'])
    try:l=max(1,int(float(lane_hint)))
    except:pass
    # Keep the approved gameplay scale while capping literal screenshot ambiguity.
    l=min(l,6 if h in {'motorway','trunk'} else 4 if h in {'primary','secondary'} else 2)
    w=max(w,l*40)
    return w,l,h

def extend_boundary_roads(entries, ww, wh, cfg):
    """Carry outward-facing perimeter roads to the world edge and author portals.

    The reference screenshot is uniformly contained in the game world, so traced
    streets often stop a few hundred pixels before the actual collision boundary.
    Only outward-facing endpoints in the configurable perimeter band are extended.
    Co-located divided-road endpoints share one visible tunnel mouth.
    """
    max_extension=max(80.0,float(cfg.get('edge_tunnel_max_extension_px',1500)))
    min_outward=max(-1.0,min(1.0,float(cfg.get('edge_tunnel_min_outward_dot',.25))))
    inset=max(24.0,float(cfg.get('edge_tunnel_inset_px',54)))
    dedupe=max(24.0,float(cfg.get('edge_tunnel_dedupe_px',150)))
    candidates=[]
    bounds=(('west',inset,0.0),('east',ww-inset,0.0),('north',inset,1.0),('south',wh-inset,1.0))
    for entry in entries:
        ps=entry['points'];rd=entry['meta']
        if len(ps)<2:continue
        for end_name,idx,near_idx in (('start',0,1),('end',-1,-2)):
            x,y=ps[idx];nx,ny=ps[near_idx];dx,dy=_unit(x-nx,y-ny)
            hits=[]
            if dx < -1e-6:
                t=(inset-x)/dx
                if t>=0:hits.append((t,'west',inset,y+dy*t))
            if dx > 1e-6:
                t=(ww-inset-x)/dx
                if t>=0:hits.append((t,'east',ww-inset,y+dy*t))
            if dy < -1e-6:
                t=(inset-y)/dy
                if t>=0:hits.append((t,'north',x+dx*t,inset))
            if dy > 1e-6:
                t=(wh-inset-y)/dy
                if t>=0:hits.append((t,'south',x+dx*t,wh-inset))
            hits=[h for h in hits if inset-1<=h[2]<=ww-inset+1 and inset-1<=h[3]<=wh-inset+1]
            if not hits:continue
            distance,side,tx,ty=min(hits,key=lambda h:h[0])
            outward={'west':(-1,0),'east':(1,0),'north':(0,-1),'south':(0,1)}[side]
            if distance>max_extension or dx*outward[0]+dy*outward[1]<min_outward:continue
            ps[idx]=(round(tx,2),round(ty,2))
            candidates.append({'road_id':rd['road_id'],'side':side,'level':int(rd.get('level',0)),
                'x':round(tx,2),'y':round(ty,2),'angle':round(math.degrees(math.atan2(dy,dx)),1),
                'width':float(rd['width'])})
    tunnels=[]
    for item in sorted(candidates,key=lambda r:(r['side'],r['level'],r['x'],r['y'],r['road_id'])):
        existing=next((t for t in tunnels if t['side']==item['side'] and t['level']==item['level'] and math.hypot(t['x']-item['x'],t['y']-item['y'])<=dedupe),None)
        if existing is None:
            tunnels.append(item)
        elif item['width']>existing['width']:
            existing.update(item)
    return tunnels

def stable_int(text): return int(hashlib.sha256(str(text).encode()).hexdigest()[:12],16)

def seg_point_distance(p,a,b):
    px,py=p;ax,ay=a;bx,by=b;dx=bx-ax;dy=by-ay;den=dx*dx+dy*dy
    if den<=1e-9:return math.hypot(px-ax,py-ay)
    t=max(0,min(1,((px-ax)*dx+(py-ay)*dy)/den));qx=ax+t*dx;qy=ay+t*dy
    return math.hypot(px-qx,py-qy)

def nearest_road_point(p,road_defs):
    best=(1e30,None,None)
    for r,ps in road_defs:
        for a,b in zip(ps,ps[1:]):
            px,py=p;ax,ay=a;bx,by=b;dx=bx-ax;dy=by-ay;den=dx*dx+dy*dy
            if den<=1e-9:continue
            t=max(0,min(1,((px-ax)*dx+(py-ay)*dy)/den));q=(ax+t*dx,ay+t*dy);d=math.hypot(px-q[0],py-q[1])
            if d<best[0]:best=(d,q,r)
    return best

def rect_overlap(a,b,pad=0):
    ax,ay,aw,ah=a;bx,by,bw,bh=b
    return not (ax+aw+pad<=bx or bx+bw+pad<=ax or ay+ah+pad<=by or by+bh+pad<=ay)

def _segment_intersects_rect(a,b,rect):
    ax,ay=a;bx,by=b;x,y,w,h=rect;dx,dy=bx-ax,by-ay;t0,t1=0.0,1.0
    for pp,q in ((-dx,ax-x),(dx,x+w-ax),(-dy,ay-y),(dy,y+h-ay)):
        if abs(pp)<=1e-12:
            if q<0:return False
            continue
        t=q/pp
        if pp<0:
            if t>t1:return False
            t0=max(t0,t)
        else:
            if t<t0:return False
            t1=min(t1,t)
    return True

def _segment_rect_distance(a,b,rect):
    ax,ay=a;bx,by=b;x,y,w,h=rect
    if _segment_intersects_rect(a,b,rect):return 0.0
    def pr(px,py):
        dx=max(x-px,0.0,px-(x+w));dy=max(y-py,0.0,py-(y+h));return math.hypot(dx,dy)
    corners=((x,y),(x+w,y),(x+w,y+h),(x,y+h))
    return min(pr(ax,ay),pr(bx,by),*(seg_point_distance(c,a,b) for c in corners))

def rect_road_clear(rect,road_defs,extra_clearance=18.0):
    for r,ps in road_defs:
        sidewalk=float(r.get('sidewalk_width',0) or 0)
        furnishing=10.0 if sidewalk>=20 else 0.0
        frontage=8.0 if sidewalk>=20 else 0.0
        clearance=float(r['width'])/2+float(r['curb_width'])+sidewalk+furnishing+frontage+float(r['building_setback'])+float(extra_clearance)
        if min(_segment_rect_distance(a,b,rect) for a,b in zip(ps,ps[1:])) + 0.01 < clearance:return False
    return True

def point_in_poly(p,poly):
    x,y=p;inside=False
    if len(poly)<3:return False
    j=len(poly)-1
    for i in range(len(poly)):
        xi,yi=poly[i];xj,yj=poly[j]
        if ((yi>y)!=(yj>y)) and (x < (xj-xi)*(y-yi)/(yj-yi+1e-12)+xi):inside=not inside
        j=i
    return inside

def rect_poly_overlap(rect,poly,pad=0.0):
    """True when an axis-aligned rectangle touches/crosses a polygon.

    Building placement previously tested only the footprint centre against water,
    which allowed large buildings to straddle shorelines.  This full-footprint test
    checks rectangle corners, polygon vertices and polygon edges.  `pad` expands the
    rectangle to preserve a small readable shoreline margin for 2.5D roof depth.
    """
    if len(poly)<3:return False
    x,y,w,h=rect;x-=pad;y-=pad;w+=2*pad;h+=2*pad
    corners=((x,y),(x+w,y),(x+w,y+h),(x,y+h))
    if any(point_in_poly(c,poly) for c in corners):return True
    if any(x<=px<=x+w and y<=py<=y+h for px,py in poly):return True
    edges=list(zip(poly,poly[1:]+poly[:1]))
    return any(_segment_intersects_rect(a,b,(x,y,w,h)) for a,b in edges)

def segment_intersection(a,b,c,d):
    """Return line-segment intersection point or None."""
    ax,ay=a;bx,by=b;cx,cy=c;dx,dy=d
    r=(bx-ax,by-ay);q=(dx-cx,dy-cy);den=r[0]*q[1]-r[1]*q[0]
    if abs(den)<1e-9:return None
    u=((cx-ax)*r[1]-(cy-ay)*r[0])/den
    t=((cx-ax)*q[1]-(cy-ay)*q[0])/den
    if 0.04<=t<=0.96 and 0.04<=u<=0.96:return (ax+t*r[0],ay+t*r[1])
    return None


def crosswalk_angle_for_road(road_ps, near):
    """Pedestrian crossing direction normal to nearest road segment."""
    if len(road_ps)<2:return 0.0
    best=None
    for a,b in zip(road_ps,road_ps[1:]):
        d=seg_point_distance(near,a,b)
        if best is None or d<best[0]:best=(d,a,b)
    if best is None:return 0.0
    _,a,b=best; tang=math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))
    return round((tang+90.0)%180.0,1)

def capsule_loop(ps,offset=34):
    """Create a smooth closed two-side loop around a traced corridor.

    Semicircular end caps avoid the near-90-degree kink of the earlier three-point
    cap and materially reduce deterministic vehicle U-turn stalls.
    """
    if len(ps)<2:return ps
    left=[];right=[]
    for idx,p in enumerate(ps):
        if idx==0:a,b=ps[0],ps[1]
        elif idx==len(ps)-1:a,b=ps[-2],ps[-1]
        else:a,b=ps[idx-1],ps[idx+1]
        dx=b[0]-a[0];dy=b[1]-a[1];L=math.hypot(dx,dy) or 1;nx=-dy/L;ny=dx/L
        left.append((p[0]+nx*offset,p[1]+ny*offset));right.append((p[0]-nx*offset,p[1]-ny*offset))
    # end cap left -> right, bulging forward along terminal tangent
    a,b=ps[-2],ps[-1];dx=b[0]-a[0];dy=b[1]-a[1];L=math.hypot(dx,dy) or 1;tx,ty=dx/L,dy/L;nx,ny=-ty,tx
    endcap=[]
    for j in range(1,6):
        th=math.pi*j/6
        endcap.append((b[0]+nx*offset*math.cos(th)+tx*offset*1.15*math.sin(th),b[1]+ny*offset*math.cos(th)+ty*offset*1.15*math.sin(th)))
    # start cap right -> left, bulging backward
    a,b=ps[0],ps[1];dx=b[0]-a[0];dy=b[1]-a[1];L=math.hypot(dx,dy) or 1;tx,ty=dx/L,dy/L;nx,ny=-ty,tx
    startcap=[]
    for j in range(1,6):
        th=math.pi*j/6
        startcap.append((a[0]-nx*offset*math.cos(th)-tx*offset*1.15*math.sin(th),a[1]-ny*offset*math.cos(th)-ty*offset*1.15*math.sin(th)))
    return left + endcap + list(reversed(right)) + startcap

def route_length(ps):
    return sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(ps,ps[1:]))


def road_level(row):
    text=' '.join(str(row.get(k,'')) for k in ('road_id','notes','width_class')).lower()
    if any(tag in text for tag in ('level=1','level 1','elevated','overpass','viaduct','bridge','gwb')):
        return 1
    return 0

def _unit(vx,vy):
    L=math.hypot(vx,vy) or 1.0
    return vx/L,vy/L

def round_polyline(ps, radius=72.0):
    """Soften abrupt polyline corners without changing endpoints/topology."""
    if len(ps)<3:return list(ps)
    out=[ps[0]]
    for i in range(1,len(ps)-1):
        a,b,c=ps[i-1],ps[i],ps[i+1]
        u1=_unit(a[0]-b[0],a[1]-b[1]); u2=_unit(c[0]-b[0],c[1]-b[1])
        l1=math.hypot(a[0]-b[0],a[1]-b[1]); l2=math.hypot(c[0]-b[0],c[1]-b[1])
        r=min(float(radius),l1*.34,l2*.34)
        if r<8:
            out.append(b);continue
        p0=(b[0]+u1[0]*r,b[1]+u1[1]*r); p2=(b[0]+u2[0]*r,b[1]+u2[1]*r)
        out.append(p0)
        for j in range(1,4):
            t=j/4.0; omt=1-t
            out.append((omt*omt*p0[0]+2*omt*t*b[0]+t*t*p2[0],omt*omt*p0[1]+2*omt*t*b[1]+t*t*p2[1]))
        out.append(p2)
    out.append(ps[-1])
    return out

def _project_to_segment(p,a,b):
    ax,ay=a; bx,by=b; px,py=p; dx=bx-ax; dy=by-ay; den=dx*dx+dy*dy
    if den<=1e-9:return a,0.0
    t=max(0.0,min(1.0,((px-ax)*dx+(py-ay)*dy)/den))
    return (ax+t*dx,ay+t*dy),t

def simplify_near_junctions(entries, snap_distance=115.0):
    """Snap almost-junctions only on the same elevation level.

    Near-parallel motorway/trunk corridors are intentionally not merged, preserving
    legitimate divided highways and ramps. Cross-level crossings are never snapped.
    """
    for i,e in enumerate(entries):
        ps=e['points']; rd=e['meta']; lvl=int(rd.get('level',0))
        if len(ps)<2:continue
        for end_idx,adj_idx in ((0,1),(-1,-2)):
            p0=ps[end_idx]; pa=ps[adj_idx]; approach=_unit(p0[0]-pa[0],p0[1]-pa[1])
            best=None
            for j,o in enumerate(entries):
                if i==j or int(o['meta'].get('level',0))!=lvl:continue
                ops=o['points']; oh=str(o['meta'].get('highway','')); rh=str(rd.get('highway',''))
                for a,b in zip(ops,ops[1:]):
                    q,t=_project_to_segment(p0,a,b); d=math.hypot(p0[0]-q[0],p0[1]-q[1])
                    if d>snap_distance:continue
                    seg=_unit(b[0]-a[0],b[1]-a[1]); parallel=abs(approach[0]*seg[0]+approach[1]*seg[1])>.93
                    if parallel and rh in {'motorway','trunk'} and oh in {'motorway','trunk'}:continue
                    if parallel and .12<t<.88:continue
                    score=d+(45 if parallel else 0)
                    if best is None or score<best[0]:best=(score,q)
            if best is not None:
                ps[end_idx]=best[1]
    # Co-located endpoints become one shared node, again only on same level.
    refs=[]
    for e in entries:
        if len(e['points'])>=2:
            refs += [(e,0),(e,-1)]
    for n,(e,idx) in enumerate(refs):
        p=e['points'][idx]; lvl=int(e['meta'].get('level',0))
        cluster=[(e,idx)]
        for o,oidx in refs[n+1:]:
            if int(o['meta'].get('level',0))!=lvl:continue
            q=o['points'][oidx]
            if math.hypot(p[0]-q[0],p[1]-q[1])<=snap_distance*.72:cluster.append((o,oidx))
        if len(cluster)>1:
            x=sum(a['points'][ii][0] for a,ii in cluster)/len(cluster); y=sum(a['points'][ii][1] for a,ii in cluster)/len(cluster)
            for a,ii in cluster:a['points'][ii]=(x,y)
    return entries

def clean_stale(folder):
    for n in ['buildings.csv','building_visuals.csv','crosswalks.csv','street_props.csv','traffic_signals.csv','traffic_route_signals.csv','parked_vehicles.csv','parked_bicycles.csv','npc_routes.csv','npc_routes_points.csv','npc_starts.csv','interiors.csv']:
        p=folder/n
        if p.exists():p.unlink()



def _point_building_distance(p, building):
    """Distance from a point to the outside of an axis-aligned building footprint."""
    px,py=p
    x=float(building['x']);y=float(building['y']);w=float(building['w']);h=float(building['h'])
    dx=max(x-px,0.0,px-(x+w));dy=max(y-py,0.0,py-(y+h))
    return math.hypot(dx,dy)

def _road_tangent_near(road_ps, near):
    if len(road_ps)<2:return (1.0,0.0)
    best=None
    for a,b in zip(road_ps,road_ps[1:]):
        d=seg_point_distance(near,a,b)
        if best is None or d<best[0]:best=(d,a,b)
    _,a,b=best
    return _unit(b[0]-a[0],b[1]-a[1])

def _nearest_point_on_polyline(p, road_ps):
    if len(road_ps)<2:return p
    px,py=p;best=None
    for a,b in zip(road_ps,road_ps[1:]):
        ax,ay=a;bx,by=b;dx=bx-ax;dy=by-ay;den=dx*dx+dy*dy
        if den<=1e-9:continue
        t=max(0.0,min(1.0,((px-ax)*dx+(py-ay)*dy)/den))
        q=(ax+t*dx,ay+t*dy);d=math.hypot(px-q[0],py-q[1])
        if best is None or d<best[0]:best=(d,q)
    return best[1] if best else p

def generate_final_frontage_crosswalks(road_defs, buildings, interiors, traffic_points, props, ww, wh, polish_pass):
    """Create zebra crossings only after the iteration's geometry is final.

    Crossings are selected from real same-level junction candidates, then moved onto
    a legal road approach and biased toward the nearest building/door frontage.  This
    avoids early-pass zebras becoming stranded in open space after buildings, roads,
    parking regions, or level geometry move later in the generation pass.
    """
    junctions=[]
    endpoint_cells={}
    for rd,ps in road_defs:
        if len(ps)<2:continue
        for pt in (ps[0],ps[-1]):
            key=(int(rd.get('level',0)),round(pt[0]/190),round(pt[1]/190))
            endpoint_cells.setdefault(key,[]).append((pt,rd,ps))
    for key,items in endpoint_cells.items():
        if len(items)<3:continue
        x=sum(pt[0] for pt,_,_ in items)/len(items);y=sum(pt[1] for pt,_,_ in items)/len(items)
        junctions.append(((x,y),[(rd,ps) for _,rd,ps in items],'endpoint'))

    if polish_pass>=3:
        for i,(r1,p1) in enumerate(road_defs):
            for j in range(i+1,len(road_defs)):
                r2,p2=road_defs[j]
                if int(r1.get('level',0))!=int(r2.get('level',0)):continue
                hit=None
                for a,b in zip(p1,p1[1:]):
                    for c,d in zip(p2,p2[1:]):
                        hit=segment_intersection(a,b,c,d)
                        if hit is not None:break
                    if hit is not None:break
                if hit is not None:junctions.append((hit,[(r1,p1),(r2,p2)],'cross'))

    if polish_pass>=5:
        for i,(r1,p1) in enumerate(road_defs):
            if len(p1)<2:continue
            for endpoint in (p1[0],p1[-1]):
                best=None
                for j,(r2,p2) in enumerate(road_defs):
                    if i==j or int(r1.get('level',0))!=int(r2.get('level',0)):continue
                    for a,b in zip(p2,p2[1:]):
                        d=seg_point_distance(endpoint,a,b)
                        if best is None or d<best[0]:best=(d,r2,p2)
                if best and best[0]<=92:
                    junctions.append((endpoint,[(r1,p1),(best[1],best[2])],'tee'))

    # Convert junction centers into building-facing approach crossings.
    placements=[]
    door_pts=[(float(r['entry_x']),float(r['entry_y'])) for r in interiors]
    for center,arms,kind in junctions:
        cx,cy=center
        if not (0<cx<ww and 0<cy<wh):continue
        for rd,ps in arms:
            highway=str(rd.get('highway','')).lower()
            # Normal building-frontage zebras belong on ground-level pedestrian streets,
            # not on motorways, trunk links, or grade-separated elevated decks.
            if int(rd.get('level',0))!=0 or highway in {'motorway','trunk'}:continue
            if float(rd.get('sidewalk_width',0))<18:continue
            tx,ty=_road_tangent_near(ps,center)
            # Move beyond the complete intersection core, including the widest arm,
            # then snap back to this exact road centerline. This guarantees the zebra
            # is on a drivable approach rather than floating near an averaged junction.
            core_half=max(float(ar['width'])/2+float(ar.get('curb_width',0)) for ar,_ in arms)
            offset=max(74.0,core_half+52.0,float(rd['width'])*0.62+38.0)
            for sign in (-1.0,1.0):
                intended=(cx+tx*offset*sign,cy+ty*offset*sign)
                x,y=_nearest_point_on_polyline(intended,ps)
                if math.hypot(x-cx,y-cy)<max(46.0,core_half*0.72):continue
                if math.hypot(x-intended[0],y-intended[1])>72:continue
                if not (20<x<ww-20 and 20<y<wh-20):continue
                bd=min((_point_building_distance((x,y),b) for b in buildings),default=1e9)
                dd=min((math.hypot(x-dx,y-dy) for dx,dy in door_pts),default=1e9)
                # A crossing must serve actual urban frontage.  Door proximity is a bonus,
                # but ordinary building frontage is sufficient.
                if bd>430 and dd>520:continue
                score=bd+min(dd,700)*0.24
                if highway=='service':score+=80
                placements.append((score,x,y,rd,ps,bd,dd,kind,tx,ty))

    placements.sort(key=lambda z:z[0])
    cross=[];signals=[];seen=[]
    limit=55 if polish_pass>=5 else 45
    for score,x,y,rd,ps,bd,dd,kind,tx,ty in placements:
        if len(cross)>=limit:break
        if any(math.hypot(x-u,y-v)<175 for u,v in seen):continue
        width=float(rd['width']);curb=float(rd.get('curb_width',0))
        cid=f'xwalk_{len(cross):03d}'
        priority='final_door_frontage' if dd<240 else 'final_building_frontage'
        zebra_depth = 28 if highway == 'primary' else (26 if highway == 'secondary' else 22)
        cross.append({'id':cid,'x':round(x,1),'y':round(y,1),
            # angle is pedestrian travel direction (road normal); renderer draws each
            # zebra bar perpendicular to this, therefore parallel to lane markings.
            'angle':crosswalk_angle_for_road(ps,(x,y)),'length':round(width+2*curb+18,1),
            'width':str(zebra_depth),'stripe_width':'4','stripe_gap':'5','curb_cut_depth':'16',
            'stop_bar_gap':'12','priority':priority})
        # Put the signal at the curb-side corner rather than in the lane center.
        nx,ny=-ty,tx
        side=-1.0 if stable_int(cid)%2 else 1.0
        soff=width/2+float(rd.get('curb_width',8))+16
        signal_pos=None
        for tangent_shift in (0,24,-24,48,-48,72,-72,96,-96):
            for candidate_side in (side,-side):
                sx=x+nx*soff*candidate_side+tx*tangent_shift
                sy=y+ny*soff*candidate_side+ty*tangent_shift
                if not (12<sx<ww-12 and 12<sy<wh-12):continue
                if any(seg_point_distance((sx,sy),a,b)<float(other['width'])*.5-8 for other,ops in road_defs for a,b in zip(ops,ops[1:])):continue
                if any(_point_building_distance((sx,sy),building)<8 for building in buildings):continue
                signal_pos=(sx,sy);break
            if signal_pos is not None:break
        if signal_pos is not None:
            signals.append({'id':f'sig_{len(signals):03d}','x':round(signal_pos[0],1),
                'y':round(signal_pos[1],1),'phase':len(signals)%2,'orientation':'v'})
        seen.append((x,y))

    route_signal_rows=[]
    if polish_pass>=3 and signals:
        by_route={}
        for r in traffic_points:by_route.setdefault(r['route_id'],[]).append(r)
        for rid,pts_rows in by_route.items():
            pts_rows=sorted(pts_rows,key=lambda z:int(float(z['point_order'])))
            used=set()
            for sig in signals:
                sx,sy=float(sig['x']),float(sig['y']);best=None
                for pr in pts_rows:
                    qx,qy=float(pr['x']),float(pr['y']);dist=math.hypot(qx-sx,qy-sy)
                    if best is None or dist<best[0]:best=(dist,int(float(pr['point_order'])))
                if best and best[0]<175 and best[1] not in used:
                    route_signal_rows.append({'route_id':rid,'waypoint_index':best[1],'phase':int(sig['phase'])});used.add(best[1])

    # Resolve dense-junction ties against the actual nearest asphalt centerline.
    # This finalizes zebra orientation after every road width and intersection is
    # known, preventing an intended arm from losing a sub-pixel distance tie to
    # the crossing street beneath it.
    for crossing in cross:
        x,y=float(crossing['x']),float(crossing['y']);nearest=None
        for road,ops in road_defs:
            if len(ops)<2:continue
            distance=min(seg_point_distance((x,y),a,b) for a,b in zip(ops,ops[1:]))
            if nearest is None or distance<nearest[0]:nearest=(distance,road,ops)
        if nearest is not None:
            _,road,ops=nearest
            crossing['angle']=crosswalk_angle_for_road(ops,(x,y))
            crossing['length']=round(float(road['width'])+2*float(road.get('curb_width',0) or 0)+18,1)

    # Because zebras are deliberately late, clear normal street furniture out of their
    # immediate footprint now, then add the final curb-side traffic-signal props.
    clean_props=[]
    for prop in props:
        px,py=float(prop['x']),float(prop['y'])
        kind=str(prop.get('kind',''))
        if kind=='edge_tunnel':
            clean_props.append(prop);continue
        clearance=18.0 if kind=='street_tree' else 8.0
        if any(_point_building_distance((px,py),building)<clearance for building in buildings):continue
        nearest=None
        for road,ops in road_defs:
            if len(ops)<2:continue
            distance=min(seg_point_distance((px,py),a,b) for a,b in zip(ops,ops[1:]))
            if nearest is None or distance<nearest[0]:nearest=(distance,road)
        if nearest is None:continue
        distance,road=nearest;sidewalk=float(road.get('sidewalk_width',0) or 0);half=float(road['width'])*.5;curb=float(road.get('curb_width',0) or 0)
        furnishing=10.0 if sidewalk>=20 else 0.0
        if sidewalk<12 or distance<half+curb-2 or distance>half+curb+furnishing+sidewalk+8:continue
        crosses=False
        for crossing in cross:
            angle=math.radians(float(crossing['angle']));dx,dy=math.cos(angle),math.sin(angle);rx,ry=px-float(crossing['x']),py-float(crossing['y'])
            along=abs(rx*dx+ry*dy);across=abs(-rx*dy+ry*dx)
            protected_along=float(crossing['length'])*.5+(26 if kind=='street_tree' else 14)
            protected_across=float(crossing['width'])*.5+18
            if along<=protected_along and across<=protected_across:crosses=True;break
        if crosses:continue
        clean_props.append(prop)
    for sig in signals:
        clean_props.append({'id':f'p{len(clean_props):04d}','kind':'traffic_signal',
            'x':sig['x'],'y':sig['y'],'scale':'0.92','rotation':'0'})
    return cross,signals,route_signal_rows,clean_props


def compile_stage():
    if STAGE.exists():shutil.rmtree(STAGE)
    shutil.copytree(BASE,STAGE);clean_stale(STAGE)
    ww,wh=world()
    cfg=settings()
    geom=geometry_settings()
    road_width_multiplier=max(1.0,float(geom.get('road_width_multiplier',2.0)))
    try: polish_pass=max(1,int(float(cfg.get('polish_pass','1'))))
    except: polish_pass=1

    # Roads: semantic geometry is derived from screenshot traces but rendered orthographically.
    # Pass 8 adds explicit elevation levels, rounded bends and same-level near-junction simplification.
    rm=[];rp=[];road_defs=[];entries=[]
    for r in rows(TRACE/'roads_trace.csv'):
        ps=transform(points(r.get('points_image_px')))
        if len(ps)<2:continue
        rid=r['road_id'];base_w,l,h=road_spec(r.get('width_class'),r.get('lane_hint'));w=round(base_w*road_width_multiplier,2);ordinary=h not in {'motorway','trunk'}
        if polish_pass>=12:
            # Sidewalk-first contract: ordinary roads reserve a clearly readable pedestrian
            # band on both sides before any building frontage is considered. Pass 23
            # extends a narrower pedestrian edge to walkable trunk corridors; true
            # motorways remain the explicit no-sidewalk exception.
            if polish_pass>=23 and h=='trunk':
                sidewalk = 14
                curb = 5
                setback = 4
            else:
                sidewalk = 0 if not ordinary else 34 if h in {'residential','service','living_street'} else 44 if h in {'secondary','tertiary'} else 56
                curb = 0 if not ordinary else 5
                setback = 4 if h in {'residential','service','living_street'} else 6 if h in {'secondary','tertiary'} else 9
        else:
            sidewalk = 0 if not ordinary else 24 if h in {'residential','service'} else 38 if h=='secondary' else 52
            curb = 0 if not ordinary else 4 if h in {'residential','service'} else 5
            setback = 2 if h in {'residential','service'} else 6 if h=='secondary' else 10
        lvl=road_level(r); bridge=lvl>0
        radius=118 if h in {'motorway','trunk'} else 82 if h in {'primary','secondary'} else 54
        ps=round_polyline(ps,radius)
        rd={'road_id':rid,'name':rid.replace('_',' ').title(),'base_width':base_w,'width':w,'lanes':l,'sidewalk_width':sidewalk,'curb_width':curb,'building_setback':setback,'bridge':str(bridge).lower(),'map_label':'false','highway':h,'level':lvl,'walkable':'true'}
        entries.append({'meta':rd,'points':ps})
    simplify_near_junctions(entries,155.0 if polish_pass>=9 else 115.0 if polish_pass>=8 else 82.0)
    for e in entries:
        rd=e['meta'];ps=e['points'];rid=rd['road_id'];rm.append(rd);rp += [{'road_id':rid,'point_order':i,'x':round(x,2),'y':round(y,2)} for i,(x,y) in enumerate(ps)];road_defs.append((rd,ps))
    if not rm:raise SystemExit('No roads traced. Run auto_trace_reference.py or the Trace Studio first.')

    # Pass 2+: add a road surface beneath traffic corridors missed by pale-road
    # screenshot tracing.  This prevents floating traffic and makes the generated
    # network visually continuous without inventing random streets.
    if polish_pass>=2:
        for idx,trow in enumerate(rows(TRACE/'traffic_trace.csv')):
            ps=transform(points(trow.get('points_image_px')))
            if len(ps)<2:continue
            samples=ps[::max(1,len(ps)//5)]
            dists=[nearest_road_point(q,road_defs)[0] for q in samples]
            if dists and sum(dists)/len(dists) < 115:continue
            pri=str(trow.get('priority') or 'normal').lower(); cls='primary' if pri in {'arterial','high'} else 'secondary'
            base_w,l,h=road_spec(cls,'4' if cls=='primary' else '2');w=round(base_w*road_width_multiplier,2);rid=f'traffic_support_{idx:03d}'
            rd={'road_id':rid,'name':f'Traffic Support {idx+1}','base_width':base_w,'width':w,'lanes':l,'sidewalk_width':(44 if polish_pass>=12 else 38),'curb_width':5,'building_setback':6,'bridge':'false','map_label':'false','highway':h,'level':0,'walkable':'true'}
            rm.append(rd);rp += [{'road_id':rid,'point_order':i,'x':x,'y':y} for i,(x,y) in enumerate(ps)];road_defs.append((rd,ps))

    # Pass 19 source traces are connectivity-repaired. Snap the comparatively small
    # set of traffic-support corridors into that repaired same-level network too.
    if polish_pass>=19:
        combined=[{'meta':rd,'points':ps} for rd,ps in road_defs]
        simplify_near_junctions(combined,150.0)
        rm=[];rp=[];road_defs=[]
        for e in combined:
            rd=e['meta'];ps=e['points'];rid=rd['road_id'];rm.append(rd);road_defs.append((rd,ps))
            rp += [{'road_id':rid,'point_order':i,'x':round(x,2),'y':round(y,2)} for i,(x,y) in enumerate(ps)]

    edge_tunnels=extend_boundary_roads([{'meta':rd,'points':ps} for rd,ps in road_defs],ww,wh,geom)
    rp=[]
    for rd,ps in road_defs:
        rp += [{'road_id':rd['road_id'],'point_order':i,'x':round(x,2),'y':round(y,2)} for i,(x,y) in enumerate(ps)]

    write(STAGE/'roads.csv',['road_id','name','base_width','width','lanes','sidewalk_width','curb_width','building_setback','bridge','map_label','highway','level','walkable'],rm);write(STAGE/'road_points.csv',['road_id','point_order','x','y'],rp)

    # Explicit sidewalk semantics for the viewer/runtime. Rendering still uses the road
    # envelope, but this table makes the walkability contract inspectable and testable.
    sidewalks=[]
    for rd in rm:
        sw=float(rd.get('sidewalk_width',0) or 0)
        if sw<=0: continue
        for side in ('left','right'):
            sidewalks.append({'sidewalk_id':f"{rd['road_id']}_{side}",'road_id':rd['road_id'],'side':side,'level':rd.get('level',0),'width':sw,'continuous':'true','walkable':'true'})
    write(STAGE/'sidewalks.csv',['sidewalk_id','road_id','side','level','width','continuous','walkable'],sidewalks)

    # Two-level outdoor world contract. Ground is unrestricted walkable land; elevated
    # level 1 is carried by explicit road/bridge decks. Ramps connect levels without
    # turning cross-level geometric crossings into junctions.
    write(STAGE/'levels.csv',['level_id','name','z_order','walkable'],[
        {'level_id':'0','name':'Ground','z_order':'0','walkable':'true'},
        {'level_id':'1','name':'Elevated','z_order':'1','walkable':'true'}])
    connectors=[]; ground=[(r,ps) for r,ps in road_defs if int(r.get('level',0))==0]
    for r,ps in [(r,ps) for r,ps in road_defs if int(r.get('level',0))==1]:
        for end_name,p0 in (('start',ps[0]),('end',ps[-1])):
            d,q,gr=nearest_road_point(p0,ground)
            if q is None or d>460:continue
            connectors.append({'connector_id':f"{r['road_id']}_{end_name}_ramp",'kind':'ramp','from_level':'0','to_level':'1','x0':round(q[0],2),'y0':round(q[1],2),'x1':round(p0[0],2),'y1':round(p0[1],2),'width':max(70,min(160,float(r['width'])*.58))})
    write(STAGE/'level_connectors.csv',['connector_id','kind','from_level','to_level','x0','y0','x1','y1','width'],connectors)

    # Terrain.
    water=[];green=[];other=[];water_polys=[];green_polys=[]
    for r in rows(TRACE/'terrain_trace.csv'):
        ps=transform(points(r.get('polygon_image_px')));typ=str(r.get('terrain_type','')).lower();aid=r['area_id']
        if len(ps)<3:continue
        if typ in {'water','river','lake'}:water_polys.append(ps);target=water
        elif typ in {'green','park','forest','grass'}:green_polys.append(ps);target=green
        else:target=other
        target += [{'polygon_id':aid,'point_order':i,'x':x,'y':y} for i,(x,y) in enumerate(ps)]
    write(STAGE/'water_polygons.csv',['polygon_id','point_order','x','y'],water);write(STAGE/'green_polygons.csv',['polygon_id','point_order','x','y'],green)
    if other:write(STAGE/'terrain_polygons.csv',['polygon_id','point_order','x','y','terrain_type'],[dict(r,terrain_type='other') for r in other])

    # Deterministic traffic. Each screenshot trace becomes a local capsule loop.
    tr=[];tp=[];starts=[]
    traffic_source=rows(TRACE/'traffic_trace.csv')
    for idx,r in enumerate(traffic_source):
        raw=transform(points(r.get('points_image_px')))
        if len(raw)<2:continue
        ps=[(max(2,min(ww-2,x)),max(2,min(wh-2,y))) for x,y in capsule_loop(raw,36)];rid=r['flow_id'];density=max(0.0,min(1.0,float(r.get('relative_density') or .5)));priority=str(r.get('priority') or 'normal').lower();speed={'low':82,'normal':102,'high':116,'arterial':126}.get(priority,102)
        if polish_pass>=25:
            # Geometry-only traffic gate: reject screenshot loops that stray far away
            # from every drivable road. This avoids retaining impossible loops for
            # the later server traffic AI to repair at runtime.
            gaps=[]
            for p0 in ps:
                d0,q0,rd0=nearest_road_point(p0,road_defs)
                if rd0 is None: gaps.append(1e9); continue
                gaps.append(max(0.0,d0-float(rd0['width'])*.5-float(rd0.get('curb_width',0) or 0)))
            if gaps and max(gaps)>220.0:
                continue
        tr.append({'route_id':rid,'name':rid.replace('_',' ').title(),'speed_limit':speed,'loop':'True','lane_offset':'0','axis':'mixed','direction':'loop','turn_radius':'44'})
        tp += [{'route_id':rid,'point_order':i,'x':round(x,2),'y':round(y,2)} for i,(x,y) in enumerate(ps)]
        desired=max(2,min(10,round(2+density*7)))
        # Keep initial gaps generous; a pretty traffic overlay is useless if a short
        # loop starts nose-to-tail and immediately deadlocks.
        capacity=max(2,int(route_length(ps)//460))
        count=min(desired,capacity)
        for j in range(count):starts.append({'spawn_id':f'car_{idx:02d}_{j:03d}','route_id':rid,'start_fraction':f'{(j+.5)/count:.6f}','asset_index':(idx*5+j)%81,'speed_scale':f'{0.92+((idx+j)%7)*.014:.3f}'})
    # CSV row order controls which fixed slots are active. Interleave routes so
    # low/default traffic counts populate the whole map instead of saturating the
    # first few traced corridors. This remains fully deterministic.
    def _start_order(row):
        bits=str(row.get('spawn_id','')).split('_')
        try:return (int(bits[-1]),int(bits[-2]))
        except:return (9999,9999)
    starts.sort(key=_start_order)
    write(STAGE/'traffic_routes.csv',['route_id','name','speed_limit','loop','lane_offset','axis','direction','turn_radius'],tr);write(STAGE/'traffic_route_points.csv',['route_id','point_order','x','y'],tp);write(STAGE/'traffic_starts.csv',['spawn_id','route_id','start_fraction','asset_index','speed_scale'],starts)

    # Bicycle network.
    bl=[];bp=[];br=[];brp=[];bs=[]
    rejected_water_bike_routes=0
    for idx,r in enumerate(rows(TRACE/'biking_trace.csv')):
        raw=transform(points(r.get('points_image_px')))
        if len(raw)<2:continue
        rid=r['bike_id'];facility=str(r.get('facility_type') or 'lane').lower();protected=facility in {'protected','path','greenway'}; ps=[(max(2,min(ww-2,x)),max(2,min(wh-2,y))) for x,y in capsule_loop(raw,13)]
        unsafe=False
        for a,b in zip(ps,ps[1:]):
            samples=max(1,int(math.hypot(b[0]-a[0],b[1]-a[1])//14))
            for sample in range(samples+1):
                t=sample/samples;p=(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t)
                if not any(point_in_poly(p,poly) for poly in water_polys):continue
                d,q,nearest=nearest_road_point(p,road_defs)
                if nearest is None or not str(nearest.get('bridge','')).lower()=='true' or d>float(nearest['width'])*.5:
                    unsafe=True;break
            if unsafe:break
        if unsafe:
            rejected_water_bike_routes+=1
            continue
        bl.append({'lane_id':rid,'name':rid.replace('_',' ').title(),'width':20,'protected':str(protected).lower(),'direction':'both'})
        bp += [{'lane_id':rid,'point_order':i,'x':x,'y':y} for i,(x,y) in enumerate(raw)]
        br.append({'route_id':rid,'name':rid.replace('_',' ').title(),'speed':112,'loop':'true','lane_offset':0,'axis':'mixed','direction':'loop','turn_radius':18})
        brp += [{'route_id':rid,'point_order':i,'x':round(x,2),'y':round(y,2)} for i,(x,y) in enumerate(ps)]
        for j in range(2):bs.append({'spawn_id':f'bike_{idx:02d}_{j:02d}','route_id':rid,'start_fraction':f'{(j+.5)/2:.6f}','appearance_index':j,'speed_scale':'1.0'})
    write(STAGE/'bike_lanes.csv',['lane_id','name','width','protected','direction'],bl);write(STAGE/'bike_lane_points.csv',['lane_id','point_order','x','y'],bp);write(STAGE/'bicycle_routes.csv',['route_id','name','speed','loop','lane_offset','axis','direction','turn_radius'],br);write(STAGE/'bicycle_routes_points.csv',['route_id','point_order','x','y'],brp);write(STAGE/'bicycle_starts.csv',['spawn_id','route_id','start_fraction','appearance_index','speed_scale'],bs)

    # Transit semantic overlay.
    tm=[];tpp=[];st=[]
    for r in rows(TRACE/'transit_trace.csv'):
        ps=transform(points(r.get('points_image_px')))
        if len(ps)<2:continue
        rid=r['transit_id'];tm.append({'route_id':rid,'mode':r.get('mode') or 'rail','name':rid.replace('_',' ').title()});tpp += [{'route_id':rid,'point_order':i,'x':x,'y':y} for i,(x,y) in enumerate(ps)]
        if r.get('station_name') and ps:st.append({'stop_id':rid+'_stop','route_id':rid,'name':r['station_name'],'x':ps[len(ps)//2][0],'y':ps[len(ps)//2][1]})
    write(STAGE/'transit_routes.csv',['route_id','mode','name'],tm);write(STAGE/'transit_route_points.csv',['route_id','point_order','x','y'],tpp);write(STAGE/'transit_stops.csv',['stop_id','route_id','name','x','y'],st)

    # Five small intentional car-park regions. Dead-end access is acceptable here;
    # elsewhere the near-junction repair remains topology-first. Parking lots are
    # reserved before building generation so no footprint blocks their entrances.
    parking_regions=[];parking_rects=[]
    if polish_pass>=8:
        target_px=[(430,520),(610,590),(760,590),(1040,600),(1280,565)]
        def parking_candidate(wx,wy,n):
            cand=[]
            # First search locally around the intended regional anchor.
            for rad in range(0,1001,100):
                for ang_i in range(16):
                    a=math.radians(ang_i*22.5);cx=wx+math.cos(a)*rad;cy=wy+math.sin(a)*rad
                    if not (260<cx<ww-260 and 210<cy<wh-210):continue
                    if any(point_in_poly((cx,cy),p) for p in water_polys):continue
                    if any(point_in_poly((cx,cy),p) for p in green_polys) and (n+ang_i)%3:continue
                    d,q,rd=nearest_road_point((cx,cy),road_defs)
                    if rd is None or int(rd.get('level',0))!=0 or d<115 or d>430:continue
                    bw=300+(n%2)*55;bh=195+((n+1)%2)*45;rect=(cx-bw/2,cy-bh/2,bw,bh)
                    # Small lots may sit tight to a local street but never cover its centerline.
                    minroad=min((_segment_rect_distance(a0,b0,rect) for rr,pps in road_defs if int(rr.get('level',0))==0 for a0,b0 in zip(pps,pps[1:])),default=9999)
                    if minroad<28:continue
                    if any(rect_overlap(rect,o,95) for o in parking_rects):continue
                    cand.append((math.hypot(cx-wx,cy-wy)+abs(d-205)*.5,rect,q,rd))
                if cand:return min(cand,key=lambda z:z[0])
            return None
        for n,(tx,ty) in enumerate(target_px):
            wx,wy=transform([(tx,ty)])[0];best=parking_candidate(wx,wy,n)
            if best is None:
                # Deterministic regional fallback: scan the whole map, still respecting land/roads.
                global_c=[]
                for gy in range(420,int(wh-420),360):
                    for gx in range(420,int(ww-420),420):
                        if any(point_in_poly((gx,gy),p) for p in water_polys):continue
                        d,q,rd=nearest_road_point((gx,gy),road_defs)
                        if rd is None or int(rd.get('level',0))!=0 or not (120<=d<=390):continue
                        bw=285+(n%2)*45;bh=190+((n+1)%2)*35;rect=(gx-bw/2,gy-bh/2,bw,bh)
                        minroad=min((_segment_rect_distance(a0,b0,rect) for rr,pps in road_defs if int(rr.get('level',0))==0 for a0,b0 in zip(pps,pps[1:])),default=9999)
                        if minroad<24 or any(rect_overlap(rect,o,110) for o in parking_rects):continue
                        global_c.append((math.hypot(gx-wx,gy-wy),rect,q,rd))
                best=min(global_c,key=lambda z:z[0]) if global_c else None
            if best is None:continue
            _,rect,q,rd=best;x,y,bw,bh=rect;parking_rects.append(rect)
            parking_regions.append({'parking_id':f'carpark_{n+1:02d}','name':f'Small Car Park {n+1}','x':round(x,1),'y':round(y,1),'w':round(bw,1),'h':round(bh,1),'level':'0','access_road_id':rd['road_id'],'access_x':round(q[0],1),'access_y':round(q[1],1),'dead_end_allowed':'true'})
    write(STAGE/'parking_regions.csv',['parking_id','name','x','y','w','h','level','access_road_id','access_x','access_y','dead_end_allowed'],parking_regions)

    # Building field.  Pass 1 used a broad grid; pass 2+ deliberately builds
    # street walls from traced road frontages, which is much closer to the approved
    # top-down urban target while preserving simple axis-aligned collision boxes.
    buildings=[];visuals=[];rects=[]
    profiles=['brick_midrise','concrete_midrise','commercial_lowrise','brick_midrise','stone_midrise','industrial']
    bid=0
    max_buildings=430 if polish_pass<=1 else 560 if polish_pass==2 else 900 if polish_pass==3 else 1200 if polish_pass==4 else 1500 if polish_pass==5 else 1750 if polish_pass==6 else 2100 if polish_pass<=8 else 2450 if polish_pass==9 else 2850 if polish_pass>=15 else 2300 if polish_pass>=13 else 2600 if polish_pass>=12 else 3200

    def try_build(cx,cy,bw,bh,seed):
        nonlocal bid
        if bid>=max_buildings:return False
        x=max(25,min(ww-bw-25,cx-bw/2));y=max(25,min(wh-bh-25,cy-bh/2));rect=(x,y,bw,bh)
        # HARD placement rule: the entire footprint must remain on land.  A small
        # shoreline margin also prevents the cosmetic roof/facade depth cue from
        # reading as a building floating over water in the top-down view.
        water_margin=24 if polish_pass>=11 else 10
        if any(rect_poly_overlap(rect,p,water_margin) for p in water_polys):return False
        # Green space is less absolute than water, but use footprint rather than centre
        # so dense infill cannot swallow whole parks.
        if any(rect_poly_overlap(rect,p,4) for p in green_polys) and seed%8:return False
        if any(rect_overlap(rect,o,28) for o in parking_rects):return False
        road_margin=4 if polish_pass>=15 else 6 if polish_pass>=13 else 16 if polish_pass>=11 else 18 if polish_pass<=3 else 3 if polish_pass==4 else 0
        if not rect_road_clear(rect,road_defs,road_margin):return False
        gap=12 if polish_pass==3 else 3 if polish_pass==4 else 4 if polish_pass>=12 else 1 if polish_pass>=5 else 18
        if any(rect_overlap(rect,o,gap) for o in rects):return False
        rects.append(rect);buildings.append({'id':str(bid),'x':round(x,1),'y':round(y,1),'w':round(bw,1),'h':round(bh,1)})
        prof=profiles[seed%len(profiles)];visuals.append({'building_id':str(bid),'profile':prof,'height_px':16+(seed>>31)%21,'roof_style':['tan','dark','light','brown'][seed%4],'roof_inset':2+(seed>>37)%7,'penthouses':1+(seed>>41)%3,'shadow_scale':f'{0.9+(seed%5)*.1:.1f}'})
        bid+=1;return True

    if polish_pass>=2:
        for ridx,(rd,ps) in enumerate(road_defs):
            if str(rd.get('highway','')).lower() in {'motorway','trunk'}:continue
            for sidx,(a,b) in enumerate(zip(ps,ps[1:])):
                dx=b[0]-a[0];dy=b[1]-a[1];L=math.hypot(dx,dy)
                if L<150:continue
                ux,uy=dx/L,dy/L;nx,ny=-uy,ux
                spacing=300 if polish_pass==2 else 210 if polish_pass==3 else 175 if polish_pass==4 else 245 if polish_pass>=13 else 205 if polish_pass>=12 else 145 if polish_pass>=10 else 225
                n=max(1,min(10,int(L//spacing)))
                for j in range(n):
                    t=(j+.5)/n;px=a[0]+dx*t;py=a[1]+dy*t
                    for side in (-1,1):
                        seed=stable_int(f'frontage:{ridx}:{sidx}:{j}:{side}:{polish_pass}')
                        horiz=abs(dx)>=abs(dy)
                        if polish_pass>=13:
                            # Pass 13: longer continuous street-wall masses sit close to the *outer*
                            # sidewalk edge. The sidewalk envelope itself remains protected.
                            if horiz:bw=235+(seed%155);bh=58+((seed>>9)%34);depth=bh
                            else:bw=58+(seed%34);bh=235+((seed>>9)%155);depth=bw
                            extra=0
                        elif polish_pass>=12:
                            # Pass 12 consolidation: longer frontage, shallower depth. This visually
                            # reads as one urban street wall while freeing a stronger sidewalk band.
                            if horiz:bw=190+(seed%125);bh=58+((seed>>9)%31);depth=bh
                            else:bw=58+(seed%31);bh=190+((seed>>9)%125);depth=bw
                            extra=2
                        elif polish_pass>=10:
                            # Tight urban street walls: shallow building depth lets dense local grids
                            # keep readable sidewalks without creating the sparse-block failure.
                            if horiz:bw=145+(seed%105);bh=72+((seed>>9)%42);depth=bh
                            else:bw=72+(seed%42);bh=145+((seed>>9)%105);depth=bw
                            extra=0
                        elif polish_pass>=5:
                            # Convergence pass: longer frontage masses and shallow depths create
                            # coherent urban street walls like the approved top-down target instead
                            # of hundreds of isolated tiny boxes. Collision remains rectangular and
                            # orthographic; only footprint cadence changes.
                            if horiz:bw=190+(seed%145);bh=96+((seed>>9)%62);depth=bh
                            else:bw=96+(seed%62);bh=190+((seed>>9)%145);depth=bw
                            extra=1
                        elif polish_pass>=4:
                            if horiz:bw=125+(seed%105);bh=92+((seed>>9)%60);depth=bh
                            else:bw=92+(seed%60);bh=125+((seed>>9)%105);depth=bw
                            extra=4
                        elif polish_pass>=3:
                            if horiz:bw=145+(seed%115);bh=105+((seed>>9)%70);depth=bh
                            else:bw=105+(seed%70);bh=145+((seed>>9)%115);depth=bw
                            extra=10
                        else:
                            if horiz:bw=185+(seed%125);bh=135+((seed>>9)%85);depth=bh
                            else:bw=135+(seed%85);bh=185+((seed>>9)%125);depth=bw
                            extra=18
                        off=float(rd['width'])/2+float(rd['curb_width'])+float(rd['sidewalk_width'])+float(rd['building_setback'])+depth/2+extra
                        try_build(px+nx*off*side,py+ny*off*side,bw,bh,seed)
                        if bid>=max_buildings:break
                    if bid>=max_buildings:break
                if bid>=max_buildings:break
            if bid>=max_buildings:break

    # Fill larger gaps deterministically, especially away from the densest traced streets.
    step_x,step_y=(390,340) if polish_pass<=1 else (470,410) if polish_pass<=3 else (235,215) if polish_pass==4 else (205,186) if polish_pass>=13 else (182,166) if polish_pass>=12 else (145,132) if polish_pass>=10 else (190,175)
    for gy in range(100,int(wh-300),step_y):
        for gx in range(100,int(ww-300),step_x):
            if bid>=max_buildings:break
            seed=stable_int(f'building:{gx}:{gy}:{polish_pass}');jx=(seed%95)-47;jy=((seed>>8)%85)-42;cx=gx+jx;cy=gy+jy
            d,q,nearest=nearest_road_point((cx,cy),road_defs)
            if nearest is None or d<(82 if polish_pass>=10 else 115 if polish_pass>=4 else 150) or d>(470 if polish_pass>=10 else 560 if polish_pass>=4 else 650 if polish_pass>=2 else 720):continue
            if polish_pass>=13:
                bw=105+(seed>>14)%95;bh=82+(seed>>23)%82
            elif polish_pass>=12:
                bw=88+(seed>>14)%78;bh=76+(seed>>23)%72
            elif polish_pass>=10:
                bw=92+(seed>>14)%92;bh=82+(seed>>23)%84
            elif polish_pass>=5:
                bw=135+(seed>>14)%115;bh=115+(seed>>23)%105
            elif polish_pass>=4:
                bw=105+(seed>>14)%95;bh=95+(seed>>23)%85
            else:
                bw=165+(seed>>14)%145;bh=140+(seed>>23)%135
            try_build(cx,cy,bw,bh,seed)
        if bid>=max_buildings:break

    # Pass 5+: explicitly strengthen the two visually important dense cores.
    # The screenshot traces are sparse/occluded around labels and highways; this
    # deterministic infill fills genuine land parcels near Fort Lee and Washington
    # Heights without changing road geometry or introducing perspective skew.
    if polish_pass>=5 and bid<max_buildings:
        core_refs=[(680,450,2600,2100,'fortlee'),(900,545,2500,2050,'heights')]
        for rx,ry,spanx,spany,label in core_refs:
            ccx,ccy=transform([(rx,ry)])[0]
            for gy in range(int(ccy-spany/2),int(ccy+spany/2),155):
                for gx in range(int(ccx-spanx/2),int(ccx+spanx/2),170):
                    if bid>=max_buildings:break
                    seed=stable_int(f'core:{label}:{gx}:{gy}')
                    cx=gx+(seed%55)-27;cy=gy+((seed>>7)%51)-25
                    d,q,nearest=nearest_road_point((cx,cy),road_defs)
                    if nearest is None or d<118 or d>500:continue
                    # Long-ish urban footprints; cosmetics split these into roof volumes.
                    bw=145+((seed>>13)%120);bh=125+((seed>>22)%105)
                    if polish_pass>=12: bw*=0.88; bh*=0.88
                    try_build(cx,cy,bw,bh,seed)
                if bid>=max_buildings:break
            if bid>=max_buildings:break

    if polish_pass>=6 and bid<max_buildings:
        # Largest-first parcel infill creates the broad connected roof masses visible
        # in the approved Fort Lee target. Candidates still obey every road/water/
        # green-space exclusion; the outdoor projection remains axis-aligned top-down.
        for rx,ry,spanx,spany,label in [(680,450,3300,2600,'fortlee_big'),(920,535,3000,2450,'heights_big')]:
            ccx,ccy=transform([(rx,ry)])[0]
            for gy in range(int(ccy-spany/2),int(ccy+spany/2),185):
                for gx in range(int(ccx-spanx/2),int(ccx+spanx/2),195):
                    if bid>=max_buildings:break
                    seed=stable_int(f'parcel:{label}:{gx}:{gy}')
                    cx=gx+(seed%45)-22;cy=gy+((seed>>7)%45)-22
                    d,q,nearest=nearest_road_point((cx,cy),road_defs)
                    if nearest is None or d<125 or d>560:continue
                    sizes=[(430,310),(360,280),(300,235),(245,205),(205,175)]
                    rot=seed%len(sizes);sizes=sizes[rot:]+sizes[:rot]
                    for bw,bh in sizes:
                        if polish_pass>=12: bw*=0.86; bh*=0.86
                        # Swap orientation deterministically for variety.
                        if (seed>>9)&1:bw,bh=bh,bw
                        before=bid
                        if try_build(cx,cy,bw,bh,seed):break
                        if bid!=before:break
                if bid>=max_buildings:break
            if bid>=max_buildings:break

    if polish_pass>=10 and bid<max_buildings:
        # Regional urban infill. The approved art is a style target, not the map extent:
        # dense cores receive continuous roof massing while parks/suburbs remain open.
        urban_zones=[
            (610,410,250,230,'fortlee_core',1.00),
            (990,500,310,360,'upper_manhattan',1.00),
            (1240,430,360,390,'bronx_core',0.82),
            (470,270,300,240,'hackensack_englewood',0.46),
        ]
        for rx,ry,sw,sh,label,density in urban_zones:
            corners=transform([(rx-sw/2,ry-sh/2),(rx+sw/2,ry+sh/2)])
            x0=min(corners[0][0],corners[1][0]);x1=max(corners[0][0],corners[1][0]);y0=min(corners[0][1],corners[1][1]);y1=max(corners[0][1],corners[1][1])
            stride=max(105,int(152/density));
            for gy in range(int(y0),int(y1),stride):
                for gx in range(int(x0),int(x1),stride):
                    if bid>=max_buildings:break
                    seed=stable_int(f'urban10:{label}:{gx}:{gy}')
                    if (seed%1000)/1000.0>density:continue
                    cx=gx+(seed%31)-15;cy=gy+((seed>>7)%31)-15
                    d,q,nearest=nearest_road_point((cx,cy),road_defs)
                    if nearest is None or d<78 or d>390:continue
                    # Compact rectangular volumes pack tightly into actual street blocks.
                    choices=[(154,104),(132,112),(112,148),(96,126),(178,92)]
                    bw,bh=choices[seed%len(choices)]
                    try_build(cx,cy,bw,bh,seed)
                if bid>=max_buildings:break
            if bid>=max_buildings:break

    # PASS 16 BACK-LOT CONSOLIDATION. Preserve each building's road-facing edge and
    # extend only away from the nearest road into otherwise unused block interior.
    # This makes dense urban blocks without consuming the protected sidewalk band.
    backlot_expanded=0
    if polish_pass>=16 and buildings:
        # Work from a stable snapshot because each accepted expansion updates the footprint.
        for bi,b in enumerate(buildings):
            x=float(b['x']);y=float(b['y']);bw=float(b['w']);bh=float(b['h']);cx=x+bw/2;cy=y+bh/2
            d,q,rd=nearest_road_point((cx,cy),road_defs)
            if q is None or rd is None or str(rd.get('highway','')).lower() in {'motorway','trunk'}: continue
            vx=cx-q[0];vy=cy-q[1]
            original=(x,y,bw,bh)
            accepted=None
            for factor in (1.32,1.22,1.14):
                if abs(vx)>=abs(vy):
                    grow=bw*(factor-1)
                    rect=(x,y,bw+grow,bh) if vx>=0 else (x-grow,y,bw+grow,bh)
                else:
                    grow=bh*(factor-1)
                    rect=(x,y,bw,bh+grow) if vy>=0 else (x,y-grow,bw,bh+grow)
                rx,ry,rw,rh=rect
                if rx<25 or ry<25 or rx+rw>ww-25 or ry+rh>wh-25: continue
                if any(rect_poly_overlap(rect,p,24) for p in water_polys): continue
                if any(rect_poly_overlap(rect,p,4) for p in green_polys): continue
                if any(rect_overlap(rect,o,20) for o in parking_rects): continue
                if not rect_road_clear(rect,road_defs,4): continue
                conflict=False
                for oi,ob in enumerate(buildings):
                    if oi==bi: continue
                    orect=(float(ob['x']),float(ob['y']),float(ob['w']),float(ob['h']))
                    if rect_overlap(rect,orect,2): conflict=True;break
                if conflict: continue
                accepted=rect;break
            if accepted is not None:
                rx,ry,rw,rh=accepted;b.update({'x':round(rx,1),'y':round(ry,1),'w':round(rw,1),'h':round(rh,1)});backlot_expanded+=1
        rects=[(float(b['x']),float(b['y']),float(b['w']),float(b['h'])) for b in buildings]

    # PASS 15 FRONTAGE SATURATION. Sample every eligible sidewalk edge and fill only
    # genuinely empty frontage with long/shallow masses. This is deterministic and
    # preserves the road+curb+sidewalk envelope through try_build().
    frontage_saturation_added=0
    if polish_pass>=15 and bid<max_buildings:
        for ridx,(rd,ps) in enumerate(road_defs):
            hw=str(rd.get('highway','')).lower()
            if hw in {'motorway','trunk'} or float(rd.get('sidewalk_width',0) or 0)<=0: continue
            for sidx,(a,bp0) in enumerate(zip(ps,ps[1:])):
                dx=bp0[0]-a[0];dy=bp0[1]-a[1];L=math.hypot(dx,dy)
                if L<220: continue
                ux,uy=dx/L,dy/L;nx,ny=-uy,ux; horiz=abs(dx)>=abs(dy)
                n=max(1,min(12,int(L//300)))
                for j in range(n):
                    t=(j+.5)/n;px=a[0]+dx*t;py=a[1]+dy*t
                    for side in (-1,1):
                        seed=stable_int(f'saturation15:{ridx}:{sidx}:{j}:{side}')
                        if horiz:
                            bw=260+(seed%150); bh=62+((seed>>9)%30); depth=bh
                        else:
                            bw=62+(seed%30); bh=260+((seed>>9)%150); depth=bw
                        off=float(rd['width'])/2+float(rd['curb_width'])+float(rd['sidewalk_width'])+float(rd['building_setback'])+depth/2+4
                        cx=px+nx*off*side;cy=py+ny*off*side
                        # Skip frontage already served by a nearby building center.
                        if any(math.hypot((float(ob['x'])+float(ob['w'])/2)-cx,(float(ob['y'])+float(ob['h'])/2)-cy)<190 for ob in buildings):
                            continue
                        before=bid
                        if try_build(cx,cy,bw,bh,seed): frontage_saturation_added+=1
                        if bid>=max_buildings: break
                    if bid>=max_buildings: break
                if bid>=max_buildings: break
            if bid>=max_buildings: break

    # PASS 14 BLOCK CONSOLIDATION. Merge nearby aligned building boxes into larger
    # street-wall masses, but only when the merged footprint remains legal. This reduces
    # visual fragmentation without stealing road or sidewalk space.
    consolidation_merges=0
    if polish_pass>=14 and len(buildings)>1:
        def _bbox(b): return (float(b['x']),float(b['y']),float(b['w']),float(b['h']))
        def _safe_merged(rect, skip_ids):
            if any(rect_poly_overlap(rect,p,24) for p in water_polys): return False
            if any(rect_poly_overlap(rect,p,4) for p in green_polys): return False
            if any(rect_overlap(rect,o,20) for o in parking_rects): return False
            if not rect_road_clear(rect,road_defs,6): return False
            for ob in buildings:
                if ob['id'] in skip_ids: continue
                if rect_overlap(rect,_bbox(ob),1): return False
            return True
        passes=0
        changed=True
        while changed and passes<4 and consolidation_merges<220:
            changed=False;passes+=1
            n=len(buildings)
            for i in range(n):
                if i>=len(buildings): break
                a=buildings[i]; ax,ay,aw,ah=_bbox(a); ar=ax+aw; ab=ay+ah
                best=None
                for j in range(i+1,len(buildings)):
                    b=buildings[j]; bx,by,bw,bh=_bbox(b); b_right=bx+bw; b_bottom=by+bh
                    ovy=max(0,min(ab,b_bottom)-max(ay,by)); ovx=max(0,min(ar,b_right)-max(ax,bx))
                    gapx=max(0,max(ax,bx)-min(ar,b_right)); gapy=max(0,max(ay,by)-min(ab,b_bottom))
                    horiz=ovy>=0.68*min(ah,bh) and gapx<=52
                    vert=ovx>=0.68*min(aw,bw) and gapy<=52
                    if not (horiz or vert): continue
                    nx=min(ax,bx);ny=min(ay,by);nr=max(ar,b_right);nb=max(ab,b_bottom);nw=nr-nx;nh=nb-ny
                    # Favor long/shallow urban masses, not giant monolithic squares.
                    if max(nw,nh)>540 or min(nw,nh)>260: continue
                    rect=(nx,ny,nw,nh)
                    if not _safe_merged(rect,{a['id'],b['id']}): continue
                    score=(gapx+gapy)+0.02*(nw*nh-aw*ah-bw*bh)
                    if best is None or score<best[0]: best=(score,j,rect)
                if best is None: continue
                _,j,rect=best; b=buildings[j]; nx,ny,nw,nh=rect
                # Keep the first building's visual family and absorb the neighbor.
                a.update({'x':round(nx,1),'y':round(ny,1),'w':round(nw,1),'h':round(nh,1)})
                removed_id=b['id']; buildings.pop(j)
                visuals=[v for v in visuals if v.get('building_id')!=removed_id]
                consolidation_merges+=1; changed=True
                break
        # Renumber after merging so downstream interior/cosmetic tables stay compact.
        old_to_new={}
        for ni,b in enumerate(buildings): old_to_new[b['id']]=str(ni); b['id']=str(ni)
        for v in visuals:
            if v.get('building_id') in old_to_new: v['building_id']=old_to_new[v['building_id']]
        rects=[_bbox(b) for b in buildings]

    # WALKABILITY GATE: every walkable road except true motorways exposes sidewalks
    # on both sides from Pass 23 onward. Earlier passes also excluded trunk roads.
    sidewalk_exceptions={'motorway'} if polish_pass>=23 else {'motorway','trunk'}
    eligible=[rd for rd in rm if str(rd.get('highway','')).lower() not in sidewalk_exceptions and str(rd.get('walkable','true')).lower()=='true']
    sidewalk_ids={s['road_id'] for s in sidewalks}
    missing=[rd['road_id'] for rd in eligible if float(rd.get('sidewalk_width',0) or 0)<=0 or rd['road_id'] not in sidewalk_ids]
    if polish_pass>=12 and missing:
        raise RuntimeError(f"SIDEWALK HARD GATE FAILED: {len(missing)} ordinary roads lack sidewalk semantics: {', '.join(missing[:12])}")
    sidewalk_coverage_pct=100.0 if not eligible else 100.0*(len(eligible)-len(missing))/len(eligible)

    # HARD INVARIANTS: no semantic building footprint may overlap water or a road corridor.
    building_water_conflicts=[]
    for b in buildings:
        rect=(float(b['x']),float(b['y']),float(b['w']),float(b['h']))
        if any(rect_poly_overlap(rect,p,0) for p in water_polys):
            building_water_conflicts.append(b['id'])
    if building_water_conflicts:
        raise RuntimeError(f"BUILDING-WATER HARD GATE FAILED: {len(building_water_conflicts)} conflicts. IDs: {', '.join(building_water_conflicts[:12])}")

    # HARD INVARIANT: no semantic building footprint may overlap a road corridor.
    # This is deliberately rechecked after *all* infill passes so a later density
    # pass cannot accidentally bypass the same road/curb/sidewalk envelope used
    # during initial placement.  Any violation rejects the generation pass.
    building_road_conflicts=[]
    for b in buildings:
        rect=(float(b['x']),float(b['y']),float(b['w']),float(b['h']))
        for rd,ps in road_defs:
            if len(ps)<2:continue
            sidewalk=float(rd.get('sidewalk_width',0) or 0);furnishing=10.0 if sidewalk>=20 else 0.0;frontage=8.0 if sidewalk>=20 else 0.0
            clearance=float(rd['width'])/2+float(rd['curb_width'])+sidewalk+furnishing+frontage+float(rd['building_setback'])+(4 if polish_pass>=15 else 6 if polish_pass>=13 else 16 if polish_pass>=11 else 0)
            distance=min(_segment_rect_distance(a,c,rect) for a,c in zip(ps,ps[1:]))
            # CSV geometry is rounded to tenths/hundredths. A quarter-pixel epsilon
            # prevents an otherwise exact tangent from failing on float round-off.
            if distance+0.25 < clearance:
                building_road_conflicts.append((b['id'],rd['road_id'],round(distance,2),round(clearance,2)))
                break
    if building_road_conflicts:
        sample=', '.join(f"building {b} / {r} ({d} < {c})" for b,r,d,c in building_road_conflicts[:8])
        raise RuntimeError(f"BUILDING-ROAD HARD GATE FAILED: {len(building_road_conflicts)} conflicts. {sample}")

    write(STAGE/'buildings.csv',['id','x','y','w','h'],buildings);write(STAGE/'building_visuals.csv',['building_id','profile','height_px','roof_style','roof_inset','penthouses','shadow_scale'],visuals)

    # Zebra crossings are intentionally deferred until the FINAL iteration cleanup,
    # after buildings, doors, parking and all road/level geometry are settled.
    cross=[];signals=[];route_signal_rows=[]

    # Street lamps/trees/hydrants generated deterministically from walkable roads.
    props=[{'id':f'edge_tunnel_{i:03d}','kind':'edge_tunnel','x':round(t['x'],1),'y':round(t['y'],1),
        'scale':round(max(.75,float(t['width'])/80.0),3),'rotation':t['angle']} for i,t in enumerate(edge_tunnels)]
    for ridx,(rd,ps) in enumerate(road_defs):
        if float(rd['sidewalk_width'])<20:continue
        for sidx,(a,b) in enumerate(zip(ps,ps[1:])):
            L=math.hypot(b[0]-a[0],b[1]-a[1])
            if L<180:continue
            divisor=520 if polish_pass<=1 else 430 if polish_pass==2 else 340 if polish_pass<=6 else 300
            n=min(6,max(1,int(L//divisor)));dx=(b[0]-a[0])/L;dy=(b[1]-a[1])/L;nx=-dy;ny=dx;off=float(rd['width'])/2+float(rd['curb_width'])+float(rd['sidewalk_width'])*.55
            for j in range(n):
                t=(j+.5)/n;cx=a[0]+(b[0]-a[0])*t;cy=a[1]+(b[1]-a[1])*t
                side=-1 if (ridx+sidx+j)%2 else 1;x=cx+nx*off*side;y=cy+ny*off*side
                if not (10<x<ww-10 and 10<y<wh-10):continue
                kind='curved_streetlamp' if (ridx+sidx+j)%3!=1 else 'street_tree'
                props.append({'id':f'p{len(props):04d}','kind':kind,'x':round(x,1),'y':round(y,1),'scale':'0.9','rotation':round(math.degrees(math.atan2(dy,dx))+90,1)})
                if kind=='curved_streetlamp' and len(props)%5==0:
                    props.append({'id':f'p{len(props):04d}','kind':'fire_hydrant','x':round(x+dx*24,1),'y':round(y+dy*24,1),'scale':'0.8','rotation':'0'})
                if len(props)>=(360 if polish_pass<=1 else 480 if polish_pass==2 else 620 if polish_pass<=6 else 780):break
            if len(props)>=(360 if polish_pass<=1 else 480 if polish_pass==2 else 620 if polish_pass<=6 else 780):break
        if len(props)>=(360 if polish_pass<=1 else 480 if polish_pass==2 else 620 if polish_pass<=6 else 780):break
    # Traffic-signal props are also deferred with the final zebra pass.
    write(STAGE/'street_props.csv',['id','kind','x','y','scale','rotation'],props)

    # Ten enterable locations. Outdoor doors are top-down frontage markers; the
    # existing interior scene remains fixed-isometric after transition. Pass 5
    # deliberately places all ten around the main playable Fort Lee/GWB/Heights
    # corridor instead of spreading them across the full regional screenshot.
    interior_specs=[
        ('starter_apartment','Starter Apartment','apartment'),('corner_shop','Bridge Corner Store','shop'),('night_diner','Open Night Diner','diner'),
        ('pharmacy','Hudson Pharmacy','shop'),('laundromat','24 Hour Laundromat','shop'),('pawn_shop','Pawn & Exchange','shop'),
        ('garage','Riverside Garage','garage'),('nightclub','After Hours Club','club'),('warehouse_office','Warehouse Office','office'),('rooftop_loft','Washington Heights Loft','apartment')]
    candidates=[]
    for b in buildings:
        x,y,w,h=map(float,(b['x'],b['y'],b['w'],b['h']));cx=x+w/2;cy=y+h/2;d,q,rd=nearest_road_point((cx,cy),road_defs)
        if rd is None or d>620:continue
        vx=q[0]-cx;vy=q[1]-cy
        if abs(vx/max(w,1))>abs(vy/max(h,1)):
            ex=x-18 if vx<0 else x+w+18; ey=max(y+20,min(y+h-20,cy+(vy/(abs(vx)+1e-9))*w/2))
        else:
            ey=y-18 if vy<0 else y+h+18; ex=max(x+20,min(x+w-20,cx+(vx/(abs(vy)+1e-9))*h/2))
        candidates.append((d,float(cx),float(cy),b,ex,ey))
    chosen=[]
    if candidates and polish_pass>=5:
        # Pixel anchors correspond to plausible dense blocks visible around Fort Lee,
        # the bridge approaches and Washington Heights on the master roads image.
        targets_px=[(640,438),(675,470),(705,425),(735,485),(780,455),(865,500),(900,535),(940,515),(990,560),(1035,505)]
        for tx,ty in targets_px:
            wx,wy=transform([(tx,ty)])[0]
            pool=[z for z in candidates if z not in chosen]
            if not pool:break
            pick=min(pool,key=lambda z:math.hypot(z[1]-wx,z[2]-wy)+z[0]*1.4)
            chosen.append(pick)
    elif candidates:
        candidates.sort(key=lambda z:z[1])
        for n in range(10):
            target=(n+.5)/10;idx=min(len(candidates)-1,round(target*(len(candidates)-1)));pool=candidates[max(0,idx-8):min(len(candidates),idx+9)]
            pick=min(pool,key=lambda z:z[0]+sum(max(0,850-math.hypot(z[1]-c[1],z[2]-c[2]))*4 for c in chosen))
            if pick in chosen:pick=next((z for z in candidates if z not in chosen),pick)
            chosen.append(pick)
    interiors=[]
    for spec,pick in zip(interior_specs,chosen):
        iid,name,kind=spec;_,cx,cy,b,ex,ey=pick
        interiors.append({'id':iid,'name':name,'kind':kind,'entry_x':round(ex,1),'entry_y':round(ey,1),'building_id':b['id'],'door_hint':'nearest_road_frontage'})
    write(STAGE/'interiors.csv',['id','name','kind','entry_x','entry_y','building_id','door_hint'],interiors)

    # Pedestrians: reuse several bike/traffic corridors as safe looped walking routes.
    nr=[];nrp=[];ns=[]
    walk_sources=[transform(points(r.get('points_image_px'))) for r in rows(TRACE/'roads_trace.csv') if str(r.get('width_class','')).lower() not in {'motorway','trunk'}]
    for idx,raw in enumerate(walk_sources[:8]):
        if len(raw)<2:continue
        ps=[(max(2,min(ww-2,x)),max(2,min(wh-2,y))) for x,y in capsule_loop(raw,70)];rid=f'walk_{idx:02d}';nr.append({'route_id':rid,'name':f'Pedestrian loop {idx+1}','speed':'55','loop':'true','lane_offset':'0','axis':'mixed','direction':'loop','turn_radius':'12'})
        nrp += [{'route_id':rid,'point_order':i,'x':round(x,2),'y':round(y,2)} for i,(x,y) in enumerate(ps)]
        for j in range(3):ns.append({'spawn_id':f'npc_{idx:02d}_{j:02d}','route_id':rid,'start_fraction':f'{(j+.25)/3:.6f}','appearance_index':(idx*3+j)%10,'speed_scale':'1.0'})
    write(STAGE/'npc_routes.csv',['route_id','name','speed','loop','lane_offset','axis','direction','turn_radius'],nr);write(STAGE/'npc_routes_points.csv',['route_id','point_order','x','y'],nrp);write(STAGE/'npc_starts.csv',['spawn_id','route_id','start_fraction','appearance_index','speed_scale'],ns)

    # A handful of parked vehicles/bikes placed beside building-frontage roads.
    parked=[];pb=[]
    for lot_i,lot in enumerate(parking_regions):
        lx,ly,lw,lh=map(float,(lot['x'],lot['y'],lot['w'],lot['h']))
        for j in range(4):
            px=lx+lw*(.18+.21*j);py=ly+lh*(.42 if lot_i%2==0 else .58)
            parked.append({'id':f'lot{lot_i}_{j}','x':round(px,1),'y':round(py,1),'angle':'0'})
    base_parked=len(parked)
    for idx,pick in enumerate(candidates[:max(0,36-base_parked)]):
        _,cx,cy,b,ex,ey=pick;d,q,rd=nearest_road_point((ex,ey),road_defs)
        if q:
            parked.append({'id':str(idx),'x':round((q[0]+ex)*.5,1),'y':round((q[1]+ey)*.5,1),'angle':'0'})
    for idx,r in enumerate(br[:24]):
        p=next((x for x in brp if x['route_id']==r['route_id']),None)
        if p:pb.append({'id':str(idx),'x':p['x'],'y':p['y'],'angle':'0'})
    write(STAGE/'parked_vehicles.csv',['id','x','y','angle'],parked);write(STAGE/'parked_bicycles.csv',['id','x','y','angle'],pb)

    # Player/economy spawns near the most central enterable frontage rather than in water/roads.
    if interiors:
        if polish_pass>=5:
            target_spawn=transform([(680,450)])[0]
            center=min(interiors,key=lambda r:math.hypot(float(r['entry_x'])-target_spawn[0],float(r['entry_y'])-target_spawn[1]))
        else:
            center=min(interiors,key=lambda r:abs(float(r['entry_x'])-ww/2)+abs(float(r['entry_y'])-wh/2))
        sx=float(center['entry_x']);sy=float(center['entry_y'])
    else:sx,sy=ww/2,wh/2
    write(STAGE/'points.csv',['group','id','x','y'],[
        {'group':'spawn','id':'0','x':sx-90,'y':sy},{'group':'spawn','id':'1','x':sx+90,'y':sy},
        {'group':'login_spawn','id':'0','x':sx,'y':sy},{'group':'supplier','id':'0','x':sx-260,'y':sy+80},{'group':'customer','id':'0','x':sx+260,'y':sy-80}])

    # Reference-derived district/landmark anchors. These are semantic labels, not perspective transforms.
    def refpt(x,y): return transform([(x,y)])[0]
    fl=refpt(680,450); plaza=refpt(710,430); gwb=refpt(820,450); whpt=refpt(900,545); lr=refpt(855,452)
    districts=[
        {'name':'FORT LEE','x':round(fl[0],1),'y':round(fl[1],1)},
        {'name':'GWB PLAZA','x':round(plaza[0],1),'y':round(plaza[1],1)},
        {'name':'WASHINGTON HEIGHTS','x':round(whpt[0],1),'y':round(whpt[1],1)},
        {'name':'WEST EXPANSION','x':round(ww*.22,1),'y':round(wh*.55,1)},
        {'name':'EAST EXPANSION','x':round(ww*.78,1),'y':round(wh*.55,1)},
        {'name':'NORTH EDGE','x':round(ww*.50,1),'y':round(wh*.16,1)},
        {'name':'SOUTH EDGE','x':round(ww*.50,1),'y':round(wh*.84,1)},
    ]
    write(STAGE/'districts.csv',['name','x','y'],districts)
    landmarks=[
        {'id':'gwb','name':'George Washington Bridge','kind':'bridge','x':round(gwb[0],1),'y':round(gwb[1],1)},
        {'id':'fort_lee','name':'Fort Lee','kind':'district','x':round(fl[0],1),'y':round(fl[1],1)},
        {'id':'bridge_plaza','name':'GWB Plaza','kind':'district','x':round(plaza[0],1),'y':round(plaza[1],1)},
        {'id':'little_red','name':'Little Red Lighthouse','kind':'landmark','x':round(lr[0],1),'y':round(lr[1],1)},
    ]
    write(STAGE/'landmarks.csv',['id','name','kind','x','y'],landmarks)

    if polish_pass>=25:
        # Final traffic-route hard gate after buildings are known. A route segment
        # that cuts through a semantic building is removed entirely; fewer valid
        # deterministic routes are preferable to a guaranteed stuck-traffic path.
        building_rects=[(float(b['x']),float(b['y']),float(b['w']),float(b['h'])) for b in buildings]
        route_groups={}
        for row in tp:
            route_groups.setdefault(row['route_id'],[]).append((int(float(row.get('point_order',0))),float(row['x']),float(row['y'])))
        bad_routes=set()
        for rid,rr in route_groups.items():
            q=[(x,y) for _,x,y in sorted(rr)]
            if any(_segment_intersects_rect(a,b,rect) for a,b in zip(q,q[1:]) for rect in building_rects):
                bad_routes.add(rid)
        if bad_routes:
            tr=[r for r in tr if r['route_id'] not in bad_routes]
            tp=[r for r in tp if r['route_id'] not in bad_routes]
            starts=[r for r in starts if r['route_id'] not in bad_routes]
            write(STAGE/'traffic_routes.csv',['route_id','name','speed_limit','loop','lane_offset','axis','direction','turn_radius'],tr)
            write(STAGE/'traffic_route_points.csv',['route_id','point_order','x','y'],tp)
            write(STAGE/'traffic_starts.csv',['spawn_id','route_id','start_fraction','asset_index','speed_scale'],starts)

    # FINAL ITERATION CLEANUP: generate pedestrian crossings only now, when the road
    # graph, buildings, doorway frontages, parking regions and elevation levels are fixed.
    cross,signals,route_signal_rows,props=generate_final_frontage_crosswalks(
        road_defs,buildings,interiors,tp,props,ww,wh,polish_pass)
    write(STAGE/'crosswalks.csv',['id','x','y','angle','length','width','stripe_width','stripe_gap','curb_cut_depth','stop_bar_gap','priority'],cross)
    write(STAGE/'traffic_signals.csv',['id','x','y','phase','orientation'],signals)
    write(STAGE/'traffic_route_signals.csv',['route_id','waypoint_index','phase'],route_signal_rows)
    write(STAGE/'street_props.csv',['id','kind','x','y','scale','rotation'],props)

    # Identify source, projection and provenance. Outdoor projection is a hard contract.
    maprows=rows(STAGE/'map.csv');by={r.get('key'):r for r in maprows}
    updates={
        'name':('Open Night — reference-image default playable map','str'),
        'description':('Screenshot-derived Fort Lee/GWB/Upper Manhattan region; orthographic GTA2-style outdoor projection with separate isometric interiors.','str'),
        'world_w':(str(int(ww)),'int'),'world_h':(str(int(wh)),'int'),
        'chunk_cols':(str(max(1,math.ceil(ww/1024))),'int'),'chunk_rows':(str(max(1,math.ceil(wh/1024))),'int'),
        'camera_projection':('orthographic_topdown','str'),'outdoor_perspective_skew':('0','float'),
        'global_map_rotation_deg':(str(orthogonalization_angle()[0]),'float'),'orthogonalization_improvement_pct':(str(orthogonalization_angle()[2]),'float'),
        'reference_fit_mode':('contain_no_skew','str'),'default_render_mode':('night','str'),
        'street_lamps_enabled':('true','bool'),'source_mode':('reference_image_set','str'),
        'procedural_buildings':('false','bool'),'polish_pass':(str(polish_pass),'int'),
        'outdoor_level_count':('2','int'),'default_player_level':('0','int'),'elevation_crossings_are_junctions':('false','bool'),
        'sidewalk_coverage_pct':(f'{sidewalk_coverage_pct:.2f}','float'),'sidewalk_first_layout':('true' if polish_pass>=12 else 'false','bool'),
        'building_consolidation_merges':(str(consolidation_merges),'int'),'frontage_saturation_added':(str(frontage_saturation_added),'int'),'backlot_expanded':(str(backlot_expanded),'int'),'road_trace_fragment_repair':('true' if polish_pass>=19 else 'false','bool'),
        'traffic_geometry_preflight':('true' if polish_pass>=25 else 'false','bool')}
    updates.update({
        'road_width_multiplier':(str(road_width_multiplier),'float'),
        'bicycle_render_scale':(str(max(.25,float(geom.get('bicycle_render_scale',.72)))),'float'),
        'edge_tunnel_count':(str(len(edge_tunnels)),'int'),
        'unsafe_bicycle_routes_rejected':(str(rejected_water_bike_routes),'int'),
        'map_build_id':('open_night_v0_7_0_wide_road_tunnel_iteration','str'),
    })
    for k,(v,t) in updates.items():
        if k in by:by[k]['value']=v;by[k]['type']=t
        else:maprows.append({'key':k,'value':v,'type':t})
    write(STAGE/'map.csv',['key','value','type'],maprows)
    write(STAGE/'render_contract.csv',['key','value','type'],[
        {'key':'shadow_authority','value':'viewer_runtime_primary','type':'str'},
        {'key':'runtime_building_shadows','value':'true','type':'bool'},
        {'key':'runtime_elevated_shadows','value':'true','type':'bool'},
        {'key':'runtime_dynamic_object_shadows','value':'true','type':'bool'},
        {'key':'shadow_direction_tracks_camera','value':'true','type':'bool'},
        {'key':'level_shadow_projection','value':'true','type':'bool'},
        {'key':'baked_directional_shadows','value':'false','type':'bool'},
        {'key':'baked_contact_ao','value':'true','type':'bool'},
        {'key':'baked_contact_ao_radius_px','value':'3','type':'int'},
        {'key':'render_pass','value':'18','type':'int'},
    ])
    write(STAGE/'source_provenance.csv',['key','value'],[
        {'key':'source_mode','value':'reference_image_set'},{'key':'compiler','value':'Open Night deterministic screenshot compiler v2'},
        {'key':'gis_required','value':'false'},{'key':'projection','value':'orthographic_topdown'},{'key':'perspective_skew','value':'0'},
        {'key':'reference_transform','value':'single rigid rotation + uniform contain/letterbox; no anisotropic stretch'},
        {'key':'global_map_rotation_deg','value':str(orthogonalization_angle()[0])},{'key':'orthogonalization_improvement_pct','value':str(orthogonalization_angle()[2])},
        {'key':'parking_regions','value':str(len(parking_regions))},{'key':'full_reference_extent_preserved','value':'true'},
        {'key':'polish_pass','value':str(polish_pass)},{'key':'road_trace_fragment_repair','value':str(polish_pass>=19).lower()},
        {'key':'sidewalk_coverage_pct','value':f'{sidewalk_coverage_pct:.2f}'},{'key':'sidewalk_first_layout','value':str(polish_pass>=12).lower()},
        {'key':'building_consolidation_merges','value':str(consolidation_merges)},{'key':'frontage_saturation_added','value':str(frontage_saturation_added)},{'key':'backlot_expanded','value':str(backlot_expanded)},
        {'key':'outdoor_levels','value':'0=ground;1=elevated'},{'key':'cross_level_intersections','value':'grade_separated_not_junctions'}])
    print(f'Compiled staging semantic map: {STAGE}')
    print(f'  polish_pass={polish_pass} rotation={orthogonalization_angle()[0]}deg improve={orthogonalization_angle()[2]}% roads={len(rm)} width_multiplier={road_width_multiplier:g} edge_tunnels={len(edge_tunnels)} sidewalks={len(sidewalks)} sidewalk_coverage={sidewalk_coverage_pct:.1f}% backlot={backlot_expanded} saturation={frontage_saturation_added} merges={consolidation_merges} buildings={len(buildings)} carparks={len(parking_regions)} crosswalks={len(cross)} interiors={len(interiors)} traffic_routes={len(tr)} traffic_slots={len(starts)} bike_water_rejected={rejected_water_bike_routes}')
    return STAGE


def install():
    if not STAGE.exists():compile_stage()
    backup=ROOT/'working_reference'/'pre_reference_install_backup'
    if backup.exists():shutil.rmtree(backup)
    shutil.copytree(BASE,backup);shutil.rmtree(BASE);shutil.copytree(STAGE,BASE)
    print('Installed compiled reference map. Backup:',backup)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--install',action='store_true');a=ap.parse_args();compile_stage();
    if a.install:install()
if __name__=='__main__':main()
