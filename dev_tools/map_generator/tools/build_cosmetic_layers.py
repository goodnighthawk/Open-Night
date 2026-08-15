from __future__ import annotations
import csv, hashlib, math, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from cosmetic_pack import build_pack, load_catalog, stable_int

MAP=ROOT/'mapfiles'/'data'/'map_001_gwb_corridor'
OUT=ROOT/'working_cosmetics'
PACK_ID='nyc_gta2_callback'

def read(name):
    p=MAP/name
    if not p.exists(): return []
    with p.open('r',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def write(path,rows,fields=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    if fields is None: fields=list(rows[0]) if rows else []
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def fval(r,k,d=0):
    try:return float(r.get(k,d) or d)
    except:return float(d)

def grouped_points():
    out={}
    for r in read('road_points.csv'):
        out.setdefault(r['road_id'],[]).append((int(float(r.get('point_order',0))),fval(r,'x'),fval(r,'y')))
    return {k:[(x,y) for _,x,y in sorted(v)] for k,v in out.items()}

def midpoint(points):
    if not points:return (0,0,0)
    seg=[]; total=0
    for a,b in zip(points,points[1:]):
        L=math.hypot(b[0]-a[0],b[1]-a[1]); seg.append((a,b,L)); total+=L
    if total<=0:return (*points[0],0)
    t=total/2
    for a,b,L in seg:
        if t<=L:
            u=t/L; x=a[0]+u*(b[0]-a[0]); y=a[1]+u*(b[1]-a[1]); ang=math.degrees(math.atan2(b[1]-a[1],b[0]-a[0])); return x,y,ang
        t-=L
    a,b,L=seg[-1];return b[0],b[1],math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))


def point_seg_distance(px,py,a,b):
    ax,ay=a; bx,by=b; dx=bx-ax; dy=by-ay
    den=dx*dx+dy*dy
    if den<=1e-9:return math.hypot(px-ax,py-ay)
    t=max(0.0,min(1.0,((px-ax)*dx+(py-ay)*dy)/den))
    qx=ax+t*dx; qy=ay+t*dy
    return math.hypot(px-qx,py-qy)

def point_poly_distance(px,py,points):
    if len(points)<2:return 1e9
    return min(point_seg_distance(px,py,a,b) for a,b in zip(points,points[1:]))

def point_at_fraction(points, frac):
    if len(points)<2:return (*points[0],1.0,0.0) if points else (0,0,1,0)
    seg=[]; total=0.0
    for a,b in zip(points,points[1:]):
        dx=b[0]-a[0]; dy=b[1]-a[1]; L=math.hypot(dx,dy)
        if L>1e-6:seg.append((a,b,L,dx/L,dy/L)); total+=L
    target=max(0,min(total,total*frac))
    for a,b,L,ux,uy in seg:
        if target<=L:
            t=target/L;return a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,ux,uy
        target-=L
    a,b,L,ux,uy=seg[-1];return b[0],b[1],ux,uy

def legal_sign_anchor(x,y,ux,uy,board_w,source_road,roads_by_id,points,crossings):
    level=int(float(source_road.get('level',0) or 0))
    # Test both support bases, not just the sign centre.
    probes=[(x,y),(x-ux*board_w*.5,y-uy*board_w*.5),(x+ux*board_w*.5,y+uy*board_w*.5)]
    for r in roads_by_id.values():
        if int(float(r.get('level',0) or 0))!=level:continue
        q=points.get(r['road_id'],[])
        half=float(r.get('width',80) or 80)*.5+8
        if any(point_poly_distance(px,py,q)<half for px,py in probes):return False
    for c in crossings:
        cx=float(c.get('x',0) or 0);cy=float(c.get('y',0) or 0)
        radius=max(float(c.get('length',90) or 90)*.55,float(c.get('width',26) or 26)*.75)+18
        if any(math.hypot(px-cx,py-cy)<radius for px,py in probes):return False
    return True

def place_roadside_sign(r,ps,roads_by_id,points,crossings,board_w):
    road_w=float(r.get('width',80) or 80); curb=float(r.get('curb_width',5) or 5); sidewalk=float(r.get('sidewalk_width',0) or 0)
    # Furnishing strip / verge: outside the drivable ribbon, usually within the outer sidewalk half.
    extra=(max(18,min(34,sidewalk*.62)) if sidewalk>0 else 24)
    offset=road_w*.5+curb+extra
    for frac in (.50,.36,.64,.24,.76):
        bx,by,ux,uy=point_at_fraction(ps,frac); nx,ny=-uy,ux
        for side in (1,-1):
            x=bx+nx*offset*side;y=by+ny*offset*side
            if legal_sign_anchor(x,y,ux,uy,board_w,r,roads_by_id,points,crossings):
                return x,y,math.degrees(math.atan2(uy,ux))
    return None

def sample_polyline(points, spacing=260.0):
    """Return evenly-spaced (x,y,ux,uy) samples along a polyline."""
    seg=[]; total=0.0
    for a,b in zip(points,points[1:]):
        dx=b[0]-a[0]; dy=b[1]-a[1]; L=math.hypot(dx,dy)
        if L>1e-6:
            seg.append((a,b,L,dx/L,dy/L,total)); total+=L
    if not seg:return []
    out=[]; d=spacing*.55
    while d<total-spacing*.35:
        for a,b,L,ux,uy,start in seg:
            if start <= d <= start+L:
                t=(d-start)/L; out.append((a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,ux,uy)); break
        d+=spacing
    return out

def nearest_zone(x,y):
    zones=[]
    for r in read('districts.csv'):
        zones.append((math.hypot(x-fval(r,'x'),y-fval(r,'y')),r['name']))
    name=min(zones)[1] if zones else 'CITY'
    return {'FORT LEE':'commercial','GWB PLAZA':'bridge_highway','WASHINGTON HEIGHTS':'dense_urban','WEST EXPANSION':'residential','EAST EXPANSION':'dense_urban','NORTH EDGE':'industrial','SOUTH EDGE':'waterfront'}.get(name,'dense_urban')

def choose(catalog,category,key,families=None):
    rows=[r for r in catalog if r['category']==category and (not families or r['family'] in families)]
    return rows[stable_int(key)%len(rows)]['archetype_id'] if rows else ''

def build():
    catalog=build_pack()
    OUT.mkdir(exist_ok=True)
    instances=[]
    visuals={r['building_id']:r for r in read('building_visuals.csv')}
    for b in read('buildings.csv'):
        x,y,w,h=map(lambda k:fval(b,k),('x','y','w','h')); bid=b['id']; zone=nearest_zone(x+w/2,y+h/2)
        prof=(visuals.get(bid,{}).get('profile') or '').lower()
        fams=['brick_midrise','stone_midrise','painted_walkup','commercial_lowrise']
        if 'industrial' in prof:fams=['industrial','warehouse']
        elif 'tower' in prof:fams=['concrete_tower']
        elif 'commercial' in prof:fams=['commercial_lowrise','corner_store','stone_midrise']
        aid=choose(catalog,'building',f'building:{bid}:{zone}',fams)
        instances.append({'object_id':f'building:{bid}','game_type':'building','semantic_subtype':prof or 'generic','cosmetic_pack':PACK_ID,'archetype_id':aid,'style_zone':zone,'x':x,'y':y,'w':w,'h':h,'rotation':0,'z_layer':20,'source':'buildings.csv'})
    kind_fams={'street_tree':['street_tree','planter_tree'],'curved_streetlamp':['streetlamp'],'fire_hydrant':['hydrant'],'traffic_signal':['signal_mast'],'bicycle_rack':['bollard'],'bench':['bench'],'dumpster':['dumpster']}
    for p in read('street_props.csv'):
        x,y=fval(p,'x'),fval(p,'y'); kind=p.get('kind','street_prop'); zone=nearest_zone(x,y)
        if kind=='edge_tunnel':
            # Rendered procedurally by EnvironmentRenderer at the exact road scale.
            continue
        if kind=='curved_streetlamp': cat='lighting_fixture'; fams=['streetlamp']
        elif kind=='street_tree': cat='vegetation'; fams=kind_fams[kind]
        elif kind=='traffic_signal': cat='sign_structure'; fams=['signal_mast']
        else: cat='street_prop'; fams=kind_fams.get(kind)
        aid=choose(catalog,cat,f'prop:{p.get("id")}:{zone}',fams)
        instances.append({'object_id':f'prop:{p.get("id")}','game_type':'street_prop','semantic_subtype':kind,'cosmetic_pack':PACK_ID,'archetype_id':aid,'style_zone':zone,'x':x,'y':y,'w':'','h':'','rotation':fval(p,'rotation'),'z_layer':30,'source':'street_props.csv'})
    # Roads keep their semantic geometry. The cosmetic assignment only selects surface/detail language.
    for r in read('roads.csv'):
        hw=(r.get('highway') or 'road').lower(); fams=['median','parking_bay'] if hw in ('motorway','trunk') else ['curb_corner','stop_bar','lane_arrow','parking_bay']
        aid=choose(catalog,'road_detail',f'road:{r["road_id"]}:{hw}',fams)
        instances.append({'object_id':f'road:{r["road_id"]}','game_type':'road','semantic_subtype':hw,'cosmetic_pack':PACK_ID,'archetype_id':aid,'style_zone':'road_network','x':'','y':'','w':'','h':'','rotation':'','z_layer':5,'source':'roads.csv'})
    fields=['object_id','game_type','semantic_subtype','cosmetic_pack','archetype_id','style_zone','x','y','w','h','rotation','z_layer','source']
    write(OUT/'cosmetic_instances.csv',instances,fields)

    # Derived cosmetic-only 2.5D road signs. No gameplay/collision semantics are changed.
    points=grouped_points(); signs=[]; sign_i=0
    major={'motorway','trunk','primary','secondary'}
    roads_all=read('roads.csv'); roads_by_id={r['road_id']:r for r in roads_all}; crossings=read('crosswalks.csv')
    for r in roads_all:
        hw=(r.get('highway') or '').lower(); name=(r.get('name') or '').strip(); ps=points.get(r['road_id'],[])
        if hw not in major or not name or len(ps)<2: continue
        generated_name=name.lower().startswith('road ') or name.lower().startswith('traffic support') or name.lower().startswith('network link')
        # Autotraced IDs are useful semantically but make terrible world signage. Keep
        # structures only on limited-access roads; suppress generic local/arterial labels.
        if generated_name and hw not in ('motorway','trunk'): continue
        board_w=150 if hw in ('motorway','trunk') else 68
        placed=place_roadside_sign(r,ps,roads_by_id,points,crossings,board_w)
        if placed is None: continue  # omission is safer than a sign in a travel lane
        x,y,ang=placed; zone=nearest_zone(x,y)
        fams=['highway_gantry'] if hw in ('motorway','trunk') else ['street_blade','speed_sign']
        aid=choose(catalog,'sign_structure',f'sign:{r["road_id"]}',fams)
        visible_label='' if generated_name else name[:36]
        signs.append({'sign_id':f's{sign_i:03d}','source_road_id':r['road_id'],'semantic_type':'directional' if hw in ('motorway','trunk') else 'street_name','archetype_id':aid,'x':round(x,2),'y':round(y,2),'rotation':round(ang,2),'height_px':58 if hw in ('motorway','trunk') else 36,'width_px':board_w,'depth_px':7,'label':visible_label,'style_zone':zone})
        sign_i+=1
        if sign_i>=120: break
    write(OUT/'road_sign_anchors.csv',signs)

    # Pass 34: cosmetic retaining-wall / railing segments on the largest water bodies.
    # This never changes water collision or walkability; it only makes waterfront edges read
    # as authored city infrastructure rather than empty polygon boundaries.
    water_groups={}
    for row in read('water_polygons.csv'):
        water_groups.setdefault(row['polygon_id'],[]).append((int(fval(row,'point_order')),fval(row,'x'),fval(row,'y')))
    waterfront=[]; edge_i=0
    for pid,vals in water_groups.items():
        q=[(x,y) for _,x,y in sorted(vals)]
        if len(q)<3: continue
        area=abs(sum(q[j][0]*q[(j+1)%len(q)][1]-q[(j+1)%len(q)][0]*q[j][1] for j in range(len(q)))*.5)
        if area < 500000: continue
        for a,b in zip(q,q[1:]+q[:1]):
            L=math.hypot(b[0]-a[0],b[1]-a[1])
            if L<70: continue
            waterfront.append({'edge_id':f'we{edge_i:03d}','polygon_id':pid,'x1':round(a[0],2),'y1':round(a[1],2),'x2':round(b[0],2),'y2':round(b[1],2),'kind':'retaining_rail','railing_spacing_px':96,'z_layer':9})
            edge_i+=1
    write(OUT/'waterfront_edges.csv',waterfront,['edge_id','polygon_id','x1','y1','x2','y2','kind','railing_spacing_px','z_layer'])

    # Bespoke cosmetic-only landmark anchors. Gameplay bridge geometry remains authoritative.
    landmark_anchors=[]
    lm_rows={r.get('id'):r for r in read('landmarks.csv')}
    gwb=lm_rows.get('gwb',{})
    def landmark_aid(key,fam): return choose(catalog,'landmark',key,[fam])
    gx=fval(gwb,'x',12707); gy=fval(gwb,'y',4838)
    # Orthographic top-down landmark treatment: towers are separated along the
    # bridge deck but never projected through a perspective transform.
    landmark_anchors.extend([
        {'landmark_visual_id':'gwb_tower_w','source_landmark_id':'gwb','archetype_id':landmark_aid('gwb:tower:w','gwb_tower'),'x':gx-520,'y':gy-14,'rotation':0,'scale':1.55,'z_layer':44,'notes':'West GWB suspension tower cosmetic.'},
        {'landmark_visual_id':'gwb_tower_e','source_landmark_id':'gwb','archetype_id':landmark_aid('gwb:tower:e','gwb_tower'),'x':gx+520,'y':gy+14,'rotation':0,'scale':1.55,'z_layer':44,'notes':'East GWB suspension tower cosmetic.'},
        {'landmark_visual_id':'gwb_truss_mid','source_landmark_id':'gwb','archetype_id':landmark_aid('gwb:truss','gwb_truss'),'x':gx,'y':gy,'rotation':0,'scale':2.15,'z_layer':41,'notes':'Bridge steel/truss visual over semantic deck.'},
        {'landmark_visual_id':'gwb_pier_w','source_landmark_id':'gwb','archetype_id':landmark_aid('gwb:pier:w','gwb_pier'),'x':gx-870,'y':gy,'rotation':0,'scale':1.7,'z_layer':39,'notes':'Bridge approach/pier visual.'},
        {'landmark_visual_id':'gwb_pier_e','source_landmark_id':'gwb','archetype_id':landmark_aid('gwb:pier:e','gwb_pier'),'x':gx+870,'y':gy,'rotation':0,'scale':1.7,'z_layer':39,'notes':'Bridge approach/pier visual.'},
    ])

    lr=lm_rows.get('little_red')
    if lr:
        landmark_anchors.append({'landmark_visual_id':'little_red_lighthouse','source_landmark_id':'little_red','archetype_id':landmark_aid('little:red','little_red_lighthouse'),'x':fval(lr,'x'),'y':fval(lr,'y'),'rotation':0,'scale':1.2,'z_layer':38,'notes':'Little Red Lighthouse visual anchor.'})
    write(OUT/'landmark_anchors.csv',landmark_anchors)
    # Procedural cable/suspender instructions remain cosmetic geometry and can be disabled/replaced by another art pack.
    bridge_cables=[
        {'cable_id':'gwb_north_main','source_landmark_id':'gwb','x1':gx-520,'y1':gy-65,'x2':gx+520,'y2':gy-52,'sag_px':38,'suspender_spacing_px':92,'line_width_px':3,'style':'steel_main'},
        {'cable_id':'gwb_south_main','source_landmark_id':'gwb','x1':gx-520,'y1':gy+65,'x2':gx+520,'y2':gy+52,'sag_px':38,'suspender_spacing_px':92,'line_width_px':3,'style':'steel_main'},
        {'cable_id':'gwb_west_north','source_landmark_id':'gwb','x1':gx-980,'y1':gy-35,'x2':gx-520,'y2':gy-65,'sag_px':24,'suspender_spacing_px':92,'line_width_px':2,'style':'steel_side'},
        {'cable_id':'gwb_east_north','source_landmark_id':'gwb','x1':gx+520,'y1':gy-52,'x2':gx+980,'y2':gy-20,'sag_px':24,'suspender_spacing_px':92,'line_width_px':2,'style':'steel_side'},
    ]
    write(OUT/'bridge_cables.csv',bridge_cables)

    # Independent lighting layer: lamps + signs + selected building/window pools.
    lights=[]; li=0
    for p in read('street_props.csv'):
        if p.get('kind')!='curved_streetlamp':continue
        x,y=fval(p,'x'),fval(p,'y'); lights.append({'light_id':f'l{li:04d}','source_type':'streetlamp','source_id':p.get('id'),'x':x,'y':y,'radius_px':108,'intensity':0.66,'color_tag':'warm','height_px':34});li+=1
    for s in signs:
        lights.append({'light_id':f'l{li:04d}','source_type':'road_sign','source_id':s['sign_id'],'x':s['x'],'y':s['y'],'radius_px':125,'intensity':0.38,'color_tag':'cool','height_px':s['height_px']});li+=1
    # Pass 21: bridge-edge lighting is derived from semantic bridge geometry so it
    # survives map regeneration and remains aligned with elevated decks. It is
    # inserted before building-window ambience; the existing 450-light cap is
    # therefore preserved rather than expanded.
    road_points=grouped_points()
    for r in read('roads.csv'):
        if str(r.get('bridge','')).lower()!='true': continue
        q=road_points.get(r.get('road_id',''),[])
        if len(q)<2: continue
        half=max(40.0,fval(r,'width',100)*.5+12.0)
        for sample_i,(x,y,ux,uy) in enumerate(sample_polyline(q,260.0)):
            nx,ny=-uy,ux
            for side in (-1.0,1.0):
                bx=x+nx*half*side; by=y+ny*half*side
                lights.append({'light_id':f'l{li:04d}','source_type':'bridge_lamp','source_id':f"{r.get('road_id')}_{sample_i}_{'L' if side<0 else 'R'}",'x':round(bx,2),'y':round(by,2),'radius_px':125,'intensity':0.62,'color_tag':'warm','height_px':42});li+=1
    write(OUT/'light_emitters.csv',lights)

    # Stable semantic-to-cosmetic contract for game integration.
    bindings=[
        {'game_type':'building','semantic_subtype':'*','visual_source':'cosmetic_instances.csv','collision_from':'game map','notes':'Skin can change without changing building ID or footprint.'},
        {'game_type':'road','semantic_subtype':'*','visual_source':'cosmetic_instances.csv + road geometry','collision_from':'game map','notes':'Road surface/marking look is independent from road graph.'},
        {'game_type':'street_prop','semantic_subtype':'*','visual_source':'cosmetic_instances.csv','collision_from':'game map or none','notes':'Reusable props; deterministic skin selection.'},
        {'game_type':'road_sign','semantic_subtype':'*','visual_source':'road_sign_anchors.csv + sign archetype','collision_from':'none by default','notes':'2.5D cosmetic structures generated from road semantics.'},
        {'game_type':'landmark','semantic_subtype':'*','visual_source':'landmark_anchors.csv + landmark archetype','collision_from':'game map landmark/bridge geometry','notes':'Bespoke GWB/lighthouse visuals remain cosmetic and replaceable.'},
        {'game_type':'bridge_cable','semantic_subtype':'*','visual_source':'bridge_cables.csv','collision_from':'none','notes':'Procedural suspension cables/suspenders are cosmetic-only and style-pack replaceable.'},
        {'game_type':'lighting','semantic_subtype':'*','visual_source':'light_emitters.csv','collision_from':'none','notes':'Lighting is an independent cosmetic/effects layer.'},
    ]
    write(OUT/'cosmetic_binding_contract.csv',bindings)
    print(f'[cosmetics] {len(catalog)} archetypes, {len(instances)} object skins, {len(signs)} 3D sign anchors, {len(landmark_anchors)} landmark anchors, {len(lights)} light emitters')

if __name__=='__main__': build()
