from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path

from common import DEFAULT_MAP_ID

BG=(12,15,17); LAND=(29,35,33); ROAD=(49,53,57); ROAD_EDGE=(84,88,84); SIDE=(108,104,94); WATER=(13,55,78); GREEN=(36,67,42)
BUILDING=(72,66,61); BUILDING_EDGE=(111,98,83); YELLOW=(226,182,66); TRAFFIC=(214,76,62); BIKE=(74,183,101); TRANSIT=(102,139,226); DOOR=(244,207,80); LIGHT=(236,184,89); SHADOW=(0,0,0,72)
ROOT = Path(__file__).resolve().parent


def default_map_path() -> Path | None:
    """Resolve the portable export for the game's authoritative default map."""
    configured = os.getenv("OPEN_NIGHT_DEFAULT_MAP", "").strip()
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            ROOT / "dev_tools" / "map_generator" / "exports" / "Map_001_GWB.map",
            ROOT / "dev_tools" / "map_generator" / "exports" / f"{DEFAULT_MAP_ID}.map",
            ROOT / "mapfiles" / "exports" / f"{DEFAULT_MAP_ID}.map",
        ]
    )
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    return None


def choose_map() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk(); root.withdraw(); root.attributes('-topmost',True)
        name=filedialog.askopenfilename(title='Open Night — Open portable map',filetypes=[('Open Night map','*.map'),('JSON map','*.json'),('All files','*.*')])
        root.destroy(); return Path(name).resolve() if name else None
    except Exception:
        return None


def load_map(path: Path) -> dict:
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('format')!='PYMMO_PORTABLE_MAP':
        raise ValueError(f"Not an Open Night portable map: {data.get('format')!r}")
    return data


def keyed_points(rows,key='road_id'):
    out={}
    for r in rows:
        try: order=int(float(r.get('point_order',0))); x=float(r.get('x',0)); y=float(r.get('y',0))
        except: continue
        out.setdefault(str(r.get(key,'')),[]).append((order,x,y))
    return {k:[(x,y) for _,x,y in sorted(v)] for k,v in out.items()}


def polygons(rows):
    return list(keyed_points(rows,'polygon_id').values())


def gta2_visual_points(points, highway='', width=80.0):
    if len(points)<3:return list(points)
    base={'motorway':92,'motorway_link':88,'trunk':82,'trunk_link':78,'primary':70,'secondary':60,'tertiary':54,'residential':46,'service':36}.get(str(highway).lower(),48)
    radius=max(20.0,min(float(base),float(width)*.85));clean=[tuple(map(float,points[0]))]
    for q in points[1:]:
        q=tuple(map(float,q))
        if math.hypot(q[0]-clean[-1][0],q[1]-clean[-1][1])>=1:clean.append(q)
    if len(clean)<3:return clean
    out=[clean[0]]
    for idx in range(1,len(clean)-1):
        a,p,b=clean[idx-1],clean[idx],clean[idx+1];vi=(p[0]-a[0],p[1]-a[1]);vo=(b[0]-p[0],b[1]-p[1]);li=math.hypot(*vi);lo=math.hypot(*vo)
        if li<2 or lo<2:out.append(p);continue
        ui=(vi[0]/li,vi[1]/li);uo=(vo[0]/lo,vo[1]/lo);dot=max(-1,min(1,ui[0]*uo[0]+ui[1]*uo[1]));turn=math.acos(dot)
        if turn<math.radians(6) or turn>math.radians(168):out.append(p);continue
        cut=min(radius*max(.32,min(1,turn/math.radians(82))),li*.32,lo*.32);pin=(p[0]-ui[0]*cut,p[1]-ui[1]*cut);pout=(p[0]+uo[0]*cut,p[1]+uo[1]*cut);out.append(pin)
        steps=max(3,min(9,int(turn/math.radians(12))+2))
        for j in range(1,steps):t=j/steps;o=1-t;out.append((o*o*pin[0]+2*o*t*p[0]+t*t*pout[0],o*o*pin[1]+2*o*t*p[1]+t*t*pout[1]))
        out.append(pout)
    out.append(clean[-1]);return out


def meta_map(tables):
    return {r.get('key',''):r.get('value','') for r in tables.get('map',[]) if r.get('key')}


class Viewer:
    def __init__(self,path:Path,data:dict):
        pygame.init(); self.path=path; self.data=data; self.tables=data.get('tables',{}); self.cos=data.get('cosmetics',{})
        self.meta=meta_map(self.tables); self.ww=float(self.meta.get('world_w',24576)); self.wh=float(self.meta.get('world_h',8192))
        self.screen=pygame.display.set_mode((1280,800),pygame.RESIZABLE); pygame.display.set_caption(f"Open Night Map Viewer — {data.get('display_name',path.name)}")
        self.clock=pygame.time.Clock(); self.font=pygame.font.SysFont('consolas',16); self.small=pygame.font.SysFont('consolas',13); self.big=pygame.font.SysFont('consolas',24,bold=True)
        self.zoom=min(1100/self.ww,650/self.wh); self.zoom=max(self.zoom,.02); self.cx=self.ww/2; self.cy=self.wh/2; self.drag=False; self.last=(0,0)
        self.show={'roads':True,'buildings':True,'traffic':True,'bike':True,'transit':True,'lights':True,'interiors':True,'connectors':True,'shadows':True}; self.level_filter=-1
        self.levels=[]
        for raw in self.tables.get('levels',[]) or []:
            try: level_id=int(float(raw.get('level_id',raw.get('id',0)) or 0))
            except (TypeError,ValueError): continue
            self.levels.append((level_id,str(raw.get('name',f'Level {level_id}'))))
        if not self.levels:
            seen=sorted({int(float(r.get('level',0) or 0)) for r in self.tables.get('roads',[]) or []})
            self.levels=[(v,'Ground' if v==0 else f'Level {v}') for v in seen] or [(0,'Ground')]
        self.levels=sorted(dict(self.levels).items())
        self.roads=keyed_points(self.tables.get('road_points',[]),'road_id'); self.traffic=keyed_points(self.tables.get('traffic_route_points',[]),'route_id')
        self.bikes=keyed_points(self.tables.get('bike_lane_points',[]),'lane_id'); self.transit=keyed_points(self.tables.get('transit_route_points',[]),'route_id')
        self.water=polygons(self.tables.get('water_polygons',[])); self.green=polygons(self.tables.get('green_polygons',[]))
        self.road_meta={str(r.get('road_id')):r for r in self.tables.get('roads',[])}
        self.building_visuals={str(r.get('building_id')):r for r in self.tables.get('building_visuals',[])}
        self.render_contract={str(r.get('key')):str(r.get('value')) for r in self.tables.get('render_contract',[])}
        self.light_rows=self.cos.get('light_emitters',[])
        self.parking_rows=self.tables.get('parking_regions',[])
        self.parked_rows=self.tables.get('parked_vehicles',[])
    def w2s(self,p):
        sw,sh=self.screen.get_size(); return (int(sw/2+(p[0]-self.cx)*self.zoom),int(sh/2+(p[1]-self.cy)*self.zoom))
    def draw_poly(self,pts,color):
        pp=[self.w2s(p) for p in pts]
        if len(pp)>=3: pygame.draw.polygon(self.screen,color,pp)
    def draw_line(self,pts,color,width=1):
        if len(pts)>=2: pygame.draw.lines(self.screen,color,False,[self.w2s(p) for p in pts],max(1,int(width*self.zoom)))
    def reset(self): self.zoom=min((self.screen.get_width()-80)/self.ww,(self.screen.get_height()-130)/self.wh);self.cx=self.ww/2;self.cy=self.wh/2
    def handle(self,e):
        if e.type==pygame.QUIT:return False
        if e.type==pygame.KEYDOWN:
            if e.key in (pygame.K_ESCAPE,pygame.K_q):return False
            if e.key==pygame.K_r:self.reset()
            keys=[('roads',pygame.K_1),('buildings',pygame.K_2),('traffic',pygame.K_3),('bike',pygame.K_4),('transit',pygame.K_5),('lights',pygame.K_6),('interiors',pygame.K_7),('connectors',pygame.K_8),('shadows',pygame.K_9)]
            for name,key in keys:
                if e.key==key:self.show[name]=not self.show[name]
            if e.key==pygame.K_0:self.level_filter=-1
            if e.key==pygame.K_g:self.level_filter=0
            if e.key==pygame.K_e and any(level_id==1 for level_id,_ in self.levels):self.level_filter=1
            if e.key in (pygame.K_LEFTBRACKET,pygame.K_RIGHTBRACKET):
                ids=[-1]+[level_id for level_id,_ in self.levels]
                try: idx=ids.index(self.level_filter)
                except ValueError: idx=0
                step=-1 if e.key==pygame.K_LEFTBRACKET else 1
                self.level_filter=ids[(idx+step)%len(ids)]
        if e.type==pygame.MOUSEBUTTONDOWN:
            if e.button==1:self.drag=True;self.last=e.pos
            elif e.button in (4,5):
                factor=1.18 if e.button==4 else 1/1.18;mx,my=e.pos
                before=self.screen_to_world((mx,my));self.zoom=max(.01,min(2.5,self.zoom*factor));after=self.screen_to_world((mx,my));self.cx+=before[0]-after[0];self.cy+=before[1]-after[1]
        if e.type==pygame.MOUSEBUTTONUP and e.button==1:self.drag=False
        if e.type==pygame.MOUSEMOTION and self.drag:
            dx=e.pos[0]-self.last[0];dy=e.pos[1]-self.last[1];self.cx-=dx/self.zoom;self.cy-=dy/self.zoom;self.last=e.pos
        if e.type==pygame.MOUSEWHEEL:
            mx,my=pygame.mouse.get_pos(); before=self.screen_to_world((mx,my)); self.zoom=max(.01,min(2.5,self.zoom*(1.18**e.y)));after=self.screen_to_world((mx,my));self.cx+=before[0]-after[0];self.cy+=before[1]-after[1]
        return True
    def screen_to_world(self,p):
        sw,sh=self.screen.get_size();return (self.cx+(p[0]-sw/2)/self.zoom,self.cy+(p[1]-sh/2)/self.zoom)
    def draw(self):
        self.screen.fill(BG)
        # world rectangle
        tl=self.w2s((0,0));br=self.w2s((self.ww,self.wh)); pygame.draw.rect(self.screen,LAND,pygame.Rect(tl,(br[0]-tl[0],br[1]-tl[1])))
        for p in self.water:self.draw_poly(p,WATER)
        for p in self.green:self.draw_poly(p,GREEN)
        # Intentional car parks are map destinations, not accidental dead ends.
        for lot in self.parking_rows:
            try:
                x,y,w,h=map(float,(lot.get('x',0),lot.get('y',0),lot.get('w',0),lot.get('h',0)))
            except: continue
            a=self.w2s((x,y)); c=self.w2s((x+w,y+h)); rect=pygame.Rect(a,(c[0]-a[0],c[1]-a[1]))
            pygame.draw.rect(self.screen,(39,43,44),rect); pygame.draw.rect(self.screen,ROAD_EDGE,rect,max(1,int(2*self.zoom)))

        # Pass 18: cast shadows are viewer-owned, not baked into the portable map.
        # The overview viewer shows building/elevated-road shadows on an alpha layer.
        if self.show['shadows']:
            shadow_layer=pygame.Surface(self.screen.get_size(),pygame.SRCALPHA)
            # Elevated road decks project onto lower levels when all levels are visible.
            if self.level_filter<0 and self.render_contract.get('runtime_elevated_shadows','true').lower()!='false':
                for rid,pts in self.roads.items():
                    r=self.road_meta.get(rid,{})
                    pts=gta2_visual_points(pts,r.get('highway',''),float(r.get('width',80) or 80))
                    lvl=int(float(r.get('level',0) or 0))
                    if lvl<=0 or len(pts)<2: continue
                    off=max(3,5*lvl); pp=[(x+off,y+off) for x,y in [self.w2s(q) for q in pts]]
                    width=max(2,int(float(r.get('width',80))*self.zoom))
                    pygame.draw.lines(shadow_layer,SHADOW,False,pp,width)
            if self.show['buildings'] and self.render_contract.get('runtime_building_shadows','true').lower()!='false':
                for idx,b in enumerate(self.tables.get('buildings',[])):
                    try:x,y,w,h=map(float,(b['x'],b['y'],b['w'],b['h']))
                    except:continue
                    vis=self.building_visuals.get(str(b.get('id',idx)),{})
                    try:height=float(vis.get('height_px',18) or 18)
                    except:height=18
                    off=max(2,int((4+height*.35)*max(.35,min(1.0,self.zoom))))
                    a=self.w2s((x,y));c=self.w2s((x+w,y+h));rect=pygame.Rect(a[0]+off,a[1]+off,c[0]-a[0],c[1]-a[1])
                    pygame.draw.rect(shadow_layer,SHADOW,rect,border_radius=2)
            self.screen.blit(shadow_layer,(0,0))

        if self.show['roads']:
            for rid,pts in self.roads.items():
                r=self.road_meta.get(rid,{}); pts=gta2_visual_points(pts,r.get('highway',''),float(r.get('width',80) or 80)); lvl=int(float(r.get('level',0) or 0))
                if self.level_filter>=0 and lvl!=self.level_filter: continue
                w=float(r.get('width',80));sw=float(r.get('sidewalk_width',0));cw=float(r.get('curb_width',0))
                if sw>0:self.draw_line(pts,SIDE,w+2*(sw+cw))
                road_col=(58,62,67) if lvl==0 else (91,88,78)
                edge_col=ROAD_EDGE if lvl==0 else YELLOW
                self.draw_line(pts,road_col,w)
                self.draw_line(pts,edge_col,max(2,w*.03))
        if self.show['buildings']:
            for b in self.tables.get('buildings',[]):
                try:x,y,w,h=map(float,(b['x'],b['y'],b['w'],b['h']))
                except:continue
                a=self.w2s((x,y));c=self.w2s((x+w,y+h));rect=pygame.Rect(a,(c[0]-a[0],c[1]-a[1]));pygame.draw.rect(self.screen,BUILDING,rect);pygame.draw.rect(self.screen,BUILDING_EDGE,rect,1)
        if self.show['traffic']:
            for car in self.parked_rows:
                try:
                    x,y,ang=float(car.get('x',0)),float(car.get('y',0)),math.radians(float(car.get('angle',0)))
                except: continue
                p=self.w2s((x,y)); length=max(5,int(28*self.zoom)); width=max(3,int(13*self.zoom))
                ux,uy=math.cos(ang),math.sin(ang); vx,vy=-uy,ux
                poly=[(p[0]+ux*length+vx*width,p[1]+uy*length+vy*width),(p[0]+ux*length-vx*width,p[1]+uy*length-vy*width),(p[0]-ux*length-vx*width,p[1]-uy*length-vy*width),(p[0]-ux*length+vx*width,p[1]-uy*length+vy*width)]
                pygame.draw.polygon(self.screen,(112,104,91),poly);pygame.draw.polygon(self.screen,(32,35,36),poly,1)
            for pts in self.traffic.values():self.draw_line(pts,TRAFFIC,3)
        if self.show['bike']:
            for pts in self.bikes.values():self.draw_line(pts,BIKE,3)
        if self.show['transit']:
            for pts in self.transit.values():self.draw_line(pts,TRANSIT,3)
        if self.show['lights']:
            for l in self.light_rows:
                try:p=self.w2s((float(l.get('x',0)),float(l.get('y',0))));rad=max(2,int(float(l.get('radius_px',100))*self.zoom*.11))
                except:continue
                pygame.draw.circle(self.screen,LIGHT,p,rad,1)
        if self.show['interiors']:
            for d in self.tables.get('interiors',[]):
                try:p=self.w2s((float(d.get('entry_x',0)),float(d.get('entry_y',0))))
                except:continue
                pygame.draw.circle(self.screen,DOOR,p,6);pygame.draw.circle(self.screen,(35,30,22),p,6,2)
        if self.show['connectors']:
            for c in self.tables.get('level_connectors',[]):
                try:a=(float(c.get('x0',0)),float(c.get('y0',0))); b=(float(c.get('x1',0)),float(c.get('y1',0)))
                except:continue
                self.draw_line([a,b],YELLOW,max(3,float(c.get('width',80))*.12))
                pygame.draw.circle(self.screen,YELLOW,self.w2s(a),4);pygame.draw.circle(self.screen,YELLOW,self.w2s(b),4)
        # HUD
        pygame.draw.rect(self.screen,(7,9,10),(0,0,self.screen.get_width(),82))
        title=self.big.render(str(self.data.get('display_name','OPEN NIGHT MAP')),True,(238,232,207));self.screen.blit(title,(18,12))
        info=f"{self.path.name}  •  {int(self.ww)}×{int(self.wh)} world px  •  projection={self.meta.get('camera_projection','topdown')}  •  zoom={self.zoom:.3f}"
        self.screen.blit(self.small.render(info,True,(166,171,158)),(20,45))
        level_names={level_id:name for level_id,name in self.levels}
        level_name='ALL LEVELS' if self.level_filter<0 else f'L{self.level_filter} {level_names.get(self.level_filter,f"Level {self.level_filter}").upper()}'
        toggles=f'1 Roads  2 Buildings  3 Traffic  4 Bikes  5 Transit  6 Lights  7 Doors  8 Ramps  9 Shadows  •  0 All / [ ] cycle levels / G Ground / E L1 [{level_name}]  •  wheel zoom  •  drag pan  •  R fit'
        self.screen.blit(self.small.render(toggles,True,(207,179,74)),(20,64))
        pygame.display.flip()
    def run(self):
        running=True
        while running:
            for e in pygame.event.get():running=self.handle(e)
            self.draw();self.clock.tick(60)
        pygame.quit()


def main():
    global pygame
    ap=argparse.ArgumentParser(description='Open Night portable .map viewer')
    ap.add_argument('map_file',nargs='?')
    ap.add_argument('--choose',action='store_true',help='open the portable-map file picker instead of the default game map')
    ap.add_argument('--print-default',action='store_true',help='print the resolved default map path and exit')
    a=ap.parse_args()
    p=(
        Path(a.map_file).expanduser().resolve()
        if a.map_file
        else (choose_map() if a.choose else default_map_path())
    )
    if a.print_default:
        if p:
            print(p)
            return 0
        print(f'Default portable map for {DEFAULT_MAP_ID} was not found')
        return 2
    if not p:
        print(f'Default portable map for {DEFAULT_MAP_ID} was not found. Use --choose to browse manually.')
        return 2
    try:
        import pygame
    except ImportError:
        print('Map Viewer requires Pygame. Run START_OPEN_NIGHT.bat once to install the game requirements.')
        return 2
    try:data=load_map(p)
    except Exception as exc:
        print('Could not open map:',exc);return 2
    Viewer(p,data).run();return 0
if __name__=='__main__':raise SystemExit(main())
