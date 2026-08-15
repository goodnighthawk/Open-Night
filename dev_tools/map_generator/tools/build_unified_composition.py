from __future__ import annotations

import argparse
import csv
import hashlib
import math
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import render_callback_preview as callback

SOURCE = ROOT / "working_reference" / "compiled_map"
OUT = ROOT / "profiles" / "gwb_gameplay" / "unified_composition"
SEMANTIC = OUT / "semantic"
TILES = OUT / "tiles"
MASTER_W = 8192
MASTER_H = 4096
TILE_SIZE = 1024
PASS_ID = "recovery_pass_18"
ROAD_WIDTH_SCALE = 0.78
SIDEWALK_SCALE = 0.85
ATLAS_WORLD_UNITS_PER_PIXEL = 2.0
MIN_BUILDING_SPRITE_SCALE = 0.72
MAX_BUILDING_SPRITE_SCALE = 1.12
# Pass 16 preserves a legible block structure without forcing every street onto
# the same synthetic lattice. Authored points remain authoritative.
ORTHOGONAL_GRID_PX = 0.0
HUDSON_WEST_X = 4864.0
HUDSON_EAST_X = 10496.0

SEMANTIC_FILES = (
    "buildings.csv",
    "road_lanes.csv",
    "sidewalk_navigation.csv",
    "crossings.csv",
    "building_entrances.csv",
    "water_boundaries.csv",
    "green_boundaries.csv",
    "layer_transitions.csv",
    "building_layers.csv",
    "building_stairwells.csv",
    "building_sprite_scale_audit.csv",
    "urban_blocks.csv",
    "iterated_buildings.csv",
    "iterated_parcel_uses.csv",
    "iterated_vegetation.csv",
)


def selected_gameplay_roads():
    """Keep connected reference roads while removing synthetic support overlays."""
    point_rows = read_csv(SOURCE / 'road_points.csv')
    grouped = {}
    for row in point_rows:
        grouped.setdefault(row['road_id'], []).append(row)
    selected = set()
    stats = []
    for road in read_csv(SOURCE / 'roads.csv'):
        ordered = sorted(grouped.get(road['road_id'], []), key=lambda r: int(float(r['point_order'])))
        length = sum(((float(b['x'])-float(a['x']))**2 + (float(b['y'])-float(a['y']))**2)**.5
                     for a,b in zip(ordered, ordered[1:]))
        highway = (road.get('highway') or 'residential').lower()
        rid = road['road_id']
        keep = not rid.startswith('traffic_support_')
        if keep:
            selected.add(road['road_id'])
            stats.append({'road_id':road['road_id'],'highway':highway,'length':round(length,2),'selection_rule':'connected_reference_without_support_overlays_v1'})
    write_csv(SEMANTIC / 'selected_roads.csv', ('road_id','highway','length','selection_rule'), stats)
    return selected


def segment_intersection(a, b, c, d):
    """Return the intersection of two finite line segments, if one exists."""
    rx, ry = b[0]-a[0], b[1]-a[1]
    sx, sy = d[0]-c[0], d[1]-c[1]
    cross = rx*sy-ry*sx
    if abs(cross) < 1e-7:
        return None
    qx, qy = c[0]-a[0], c[1]-a[1]
    t = (qx*sy-qy*sx)/cross
    u = (qx*ry-qy*rx)/cross
    if -1e-7 <= t <= 1+1e-7 and -1e-7 <= u <= 1+1e-7:
        return a[0]+t*rx, a[1]+t*ry
    return None


def authored_crossings(roads, rp):
    """Derive compact approach crossings from final road geometry.

    Zebra bars run parallel to lane lines while the complete crossing spans the
    carriageway perpendicular to traffic. Grade-separated bridge hits are ignored.
    """
    crossings=[];seen_junctions=set();seen_crossings=set();serial=0
    weights={'primary':3,'secondary':2,'tertiary':1,'residential':0,'service':0}
    depth_by_class={'primary':30,'secondary':30,'tertiary':28,'residential':26,'service':24}
    def carriageway(road):
        n=max(1,int(float(road.get('lanes',1))))
        return max(38,n*38+10)*ROAD_WIDTH_SCALE
    def available_signs(road,hit):
        start=rp[road['road_id']][0];end=rp[road['road_id']][-1]
        if math.hypot(hit[0]-start[0],hit[1]-start[1])<2:return (1,)
        if math.hypot(hit[0]-end[0],hit[1]-end[1])<2:return (-1,)
        return (-1,1)
    for left_index,left in enumerate(roads):
        if left.get('bridge') == 'true':
            continue
        for right in roads[left_index+1:]:
            if right.get('bridge') == 'true':
                continue
            priority=max(weights.get(left.get('highway',''),0),weights.get(right.get('highway',''),0))
            if priority < 1:
                continue
            for a,b in zip(rp[left['road_id']],rp[left['road_id']][1:]):
                for c,d in zip(rp[right['road_id']],rp[right['road_id']][1:]):
                    hit=segment_intersection(a,b,c,d)
                    if hit is None:
                        continue
                    key=(left['road_id'],right['road_id'],round(hit[0]/12),round(hit[1]/12))
                    if key in seen_junctions:
                        continue
                    seen_junctions.add(key)
                    spatial_key=(round(hit[0]/24),round(hit[1]/24))
                    if priority==1 and (spatial_key[0]*7+spatial_key[1]*11)%3:
                        continue
                    for target,target_segment,other in ((left,(a,b),right),(right,(c,d),left)):
                        ta,tb=target_segment;dx,dy=tb[0]-ta[0],tb[1]-ta[1];length=math.hypot(dx,dy)
                        if length<1:continue
                        ux,uy=dx/length,dy/length
                        signs=available_signs(target,hit)
                        if priority<3 and len(signs)>1:
                            signs=(signs[(spatial_key[0]+spatial_key[1]+left_index)%2],)
                        depth=depth_by_class.get(target.get('highway','residential'),26)
                        span=carriageway(target)+2*float(target.get('curb_width',5))
                        approach=carriageway(other)*.5+depth*.72+14
                        for sign in signs:
                            x=hit[0]+ux*sign*approach;y=hit[1]+uy*sign*approach
                            crossing_key=(round(x/12),round(y/12),round(math.degrees(math.atan2(dy,dx))/5))
                            if crossing_key in seen_crossings:continue
                            seen_crossings.add(crossing_key);serial+=1
                            crossings.append({'id':f'cross_authored_{serial:03d}','road_id':target['road_id'],
                                              'x':round(x,2),'y':round(y,2),
                                              'angle':round(math.degrees(math.atan2(dy,dx)),2),
                                              'length':round(span,2),'width':depth,
                                              'stripe_width':'5','stripe_gap':'10','stop_bar_gap':'14'})
    # A crossing offset from a multi-segment approach can land closest to the
    # next curved segment. Snap to that final centerline and inherit its tangent
    # so every zebra remains visibly parallel to the lane markings it occupies.
    for crossing in crossings:
        px, py = float(crossing['x']), float(crossing['y'])
        best = None
        for a, b in zip(rp[crossing['road_id']], rp[crossing['road_id']][1:]):
            dx, dy = b[0]-a[0], b[1]-a[1]
            den = dx*dx + dy*dy
            t = 0.0 if den <= 1e-9 else max(0.0, min(1.0, ((px-a[0])*dx+(py-a[1])*dy)/den))
            qx, qy = a[0]+t*dx, a[1]+t*dy
            distance = math.hypot(px-qx, py-qy)
            if best is None or distance < best[0]:
                best = (distance, qx, qy, math.degrees(math.atan2(dy, dx)))
        if best is not None:
            _, qx, qy, angle = best
            crossing['x'], crossing['y'] = round(qx, 2), round(qy, 2)
            crossing['angle'] = round(angle, 2)
    return crossings


def authored_block_network():
    """Terrain-aware Fort Lee / Washington Heights street hierarchy.

    Local streets still form readable urban blocks, but their spacing, reach and
    angle vary. Long roads follow the shoreline/topography, minor streets end at
    real T-junctions, and only a few crosstown routes continue across a district.
    """
    roads=[];rp={}
    styles={
        'primary':('4','160','52'),
        'secondary':('3','128','44'),
        'tertiary':('2','108','40'),
        'residential':('2','92','36'),
        'service':('1','70','28'),
    }
    def add(rid,points,highway='residential',bridge=False):
        lanes,width,sidewalk=styles[highway]
        roads.append({'road_id':rid,'highway':highway,'lanes':lanes,'width':width,
                      'sidewalk_width':sidewalk,'curb_width':'5',
                      'level':'1' if bridge else '0','bridge':'true' if bridge else 'false'})
        rp[rid]=points

    # Fort Lee: broad approaches and winding bluff roads, with staggered local
    # streets instead of a full rectangular mesh.
    add('fl_west_avenue',[(512,2048),(576,2944),(512,3712),(576,4672),(576,6144),
                          (512,7040),(512,8128),(576,8960),(512,10240)],'secondary')
    add('fl_center_avenue',[(2240,2048),(2240,2880),(2304,3712),(2304,5184),(2304,6144),
                            (2368,7040),(2368,8128),(2304,9024),(2304,10240)],'primary')
    add('fl_sylvan_road',[(3264,2048),(3200,2880),(3328,3904),(3264,5184),(3264,6144),
                          (3392,7296),(3328,8320),(3456,8960),(3392,10240)],'tertiary')
    add('fl_hudson_terrace',[(4544,2048),(4480,2880),(4576,3904),(4512,5184),(4608,6144),
                             (4544,7296),(4608,8320),(4544,8960),(4608,10240)],'secondary')
    add('fl_north_boulevard',[(0,2816),(1024,2816),(2240,2880),(3200,2880),(4480,2880)],'primary')
    add('fl_gwb_approach',[(0,6144),(1152,6144),(2304,6144),(3264,6144),(4608,6144)],'primary')
    add('fl_south_boulevard',[(0,8960),(1152,8960),(2304,9024),(3456,8960),(4544,8960)],'primary')
    add('fl_northwest_local',[(576,3712),(1408,3648),(2304,3712)],'residential')
    add('fl_northeast_local',[(2304,3904),(3328,3904),(4576,3904)],'residential')
    add('fl_bluff_lane',[(0,4672),(576,4672),(1408,4736),(2304,4672)],'residential')
    add('fl_terrace_lane',[(2304,5184),(3264,5184),(4512,5184)],'residential')
    add('fl_southwest_local',[(0,7040),(512,7040),(1472,6976),(2368,7040)],'residential')
    add('fl_southeast_local',[(2368,7296),(3392,7296),(4544,7296)],'residential')
    add('fl_park_lane',[(512,8128),(1472,8192),(2368,8128),(3328,8320),(4608,8320)],'tertiary')
    add('fl_ridge_connector',[(1408,2816),(1408,3648),(1408,4736),(1472,6144)],'residential')
    add('fl_south_connector',[(1472,6144),(1472,6976),(1472,8192),(1536,8960)],'residential')

    # Washington Heights: denser and more continuous than Fort Lee, but with
    # Broadway-like diagonals, varied crosstown levels and selective superblocks.
    add('wh_riverside_drive',[(10752,2048),(10816,2752),(10752,3584),(10752,4608),(10816,6144),
                              (10752,6912),(10816,7680),(10752,9024),(10816,10240)],'secondary')
    add('wh_broadway',[(11904,2048),(12032,2816),(12096,3648),(12160,4672),(12288,6144),
                       (12352,6912),(12416,7680),(12544,9024),(12672,10240)],'primary')
    add('wh_amsterdam_avenue',[(13760,2048),(13760,2752),(13824,3712),(13824,4608),(13760,6144),
                               (13824,6912),(13888,7680),(13824,9024),(13952,10240)],'secondary')
    add('wh_east_avenue',[(15488,2048),(15424,2816),(15424,3776),(15552,4672),(15488,6144),
                          (15552,6912),(15616,7680),(15552,9024),(15616,10240)],'primary')
    add('wh_north_crosstown',[(10752,2752),(12032,2816),(13760,2752),(15424,2816),(16384,2752)],'primary')
    add('wh_181st_street',[(10752,4608),(12160,4672),(13824,4608),(15552,4672),(16384,4608)],'secondary')
    add('wh_gwb_crosstown',[(10752,6144),(12288,6144),(13760,6144),(15488,6144),(16384,6144)],'primary')
    add('wh_168th_street',[(10816,7680),(12416,7680),(13888,7680),(15616,7680),(16384,7616)],'secondary')
    add('wh_south_crosstown',[(10752,9024),(12544,9024),(13824,9024),(15552,9024),(16384,8960)],'primary')
    add('wh_northwest_local',[(10816,3584),(12096,3648),(13056,3584)],'residential')
    add('wh_northeast_local',[(13056,3776),(13824,3712),(15424,3776),(16384,3776)],'residential')
    add('wh_midtown_local',[(12160,5408),(13056,5344),(13824,5408),(15552,5312),(16384,5376)],'residential')
    add('wh_southwest_local',[(10752,6912),(12352,6912),(13824,6912)],'residential')
    add('wh_southeast_local',[(13824,7104),(15552,6912),(16384,6976)],'residential')
    add('wh_lower_local',[(10816,8384),(12480,8448),(13888,8384),(14720,8448)],'residential')
    add('wh_lower_east_local',[(14720,8256),(15552,8256),(16384,8320)],'residential')
    add('wh_pinehurst_avenue',[(11392,2752),(11456,3584),(11456,4608)],'residential')
    add('wh_north_connector',[(13056,2752),(13056,3584),(13056,3776),(13056,5344),(13120,6144)],'tertiary')
    add('wh_south_connector',[(13120,6144),(13120,6912),(13184,7680),(13184,8384),(13248,9024)],'residential')
    add('wh_east_connector',[(14656,2816),(14656,3776),(14720,4608),(14720,5408),(14720,6144)],'residential')
    add('wh_lower_connector',[(14720,6144),(14720,7104),(14720,7680),(14720,8256),(14784,9024)],'residential')

    add('gwb_authored',[(4608,6144),(10752,6144)],'primary',bridge=True)
    return roads,rp,authored_crossings(roads,rp)


def polygon_area(points):
    return abs(sum(x*y2-y*x2 for (x,y),(x2,y2) in zip(points,points[1:]+points[:1])))*.5


def source_polygons(name):
    grouped={}
    for row in read_csv(SOURCE/name):
        grouped.setdefault(row['polygon_id'],[]).append(row)
    return {pid:[(float(r['x']),float(r['y'])) for r in sorted(rows,key=lambda r:int(float(r['point_order'])))]
            for pid,rows in grouped.items()}


def authored_surfaces():
    """Continuous Hudson plus filtered, meaningful reference-derived surfaces.

    The screenshot trace remains visible in the result, but tiny isolated water
    fragments and green slivers are rejected so they cannot consume whole blocks.
    """
    water=[[(4864,2048),(5120,2944),(4928,3712),(5184,4544),(4992,5248),(5056,6144),
            (4928,6976),(5184,7680),(4992,8576),(5120,9344),(4864,10240),
            (10240,10240),(10496,9344),(10240,8576),(10432,7680),(10240,6976),
            (10368,6144),(10176,5248),(10432,4544),(10240,3712),(10496,2944),(10240,2048)]]
    source_water=source_polygons('water_polygons.csv')
    # Preserve the single dominant source-traced Hudson polygon. Smaller traced
    # channels previously carved disconnected slivers and unusable land.
    if source_water:
        water.append(max(source_water.values(),key=polygon_area))

    green=[[(1536,7680),(2048,7680),(2048,8320),(1536,8320)],
           [(13248,2944),(13760,2944),(13760,3456),(13248,3456)]]
    west=[];east=[]
    for pid,poly in source_polygons('green_polygons.csv').items():
        xs=[x for x,_ in poly];ys=[y for _,y in poly];area=polygon_area(poly)
        cx=sum(xs)/len(xs);cy=sum(ys)/len(ys)
        if area<70000 or not (2048<=cy<=10240) or max(xs)-min(xs)<180 or max(ys)-min(ys)<180:
            continue
        if max(xs)<=HUDSON_WEST_X+64:
            west.append((area,pid,poly))
        elif min(xs)>=HUDSON_EAST_X-64:
            east.append((area,pid,poly))
    # District caps preserve the strongest reference parks without letting green
    # trace noise dominate developable land again.
    green.extend(poly for _,_,poly in sorted(west,reverse=True)[:3])
    green.extend(poly for _,_,poly in sorted(east,reverse=True)[:5])
    return {'water':water,'green':green}


def read_csv(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def world_to_master(x, y):
    return round(float(x) * 0.5, 2), round((float(y) - 2048.0) * 0.5, 2)


def export_semantics(roads_override,rp_override,crossings_override):
    write_csv(SEMANTIC / "buildings.csv", ("building_id", "x", "y", "w", "h"), [])

    points = {rid:[{'point_order':idx,'x':x,'y':y} for idx,(x,y) in enumerate(values)] for rid,values in rp_override.items()}
    roads = {row["road_id"]: row for row in roads_override}
    lanes = []
    walks = []
    for road_id, rows in points.items():
        road = roads.get(road_id, {})
        ordered=sorted(rows,key=lambda r:int(float(r['point_order'])))
        world_points=callback.orthogonal_world_points([(float(r['x']),float(r['y'])) for r in ordered],ORTHOGONAL_GRID_PX)
        for order,(wx,wy) in enumerate(world_points):
            x, y = world_to_master(wx, wy)
            base = {"road_id": road_id, "point_order": order, "x": x, "y": y,
                    "level": road.get("level", "0")}
            lanes.append(dict(base, width=round(float(road.get("width", 0)) * 0.5, 2),
                              lanes=road.get("lanes", "1")))
            if float(road.get("sidewalk_width", 0) or 0) > 0:
                walks.append(dict(base, sidewalk_width=round(float(road["sidewalk_width"]) * 0.5, 2)))
    write_csv(SEMANTIC / "road_lanes.csv", ("road_id", "point_order", "x", "y", "level", "width", "lanes"), lanes)
    write_csv(SEMANTIC / "sidewalk_navigation.csv", ("road_id", "point_order", "x", "y", "level", "sidewalk_width"), walks)

    crossings = []
    for row in crossings_override:
        x, y = world_to_master(row["x"], row["y"])
        crossings.append({"crossing_id": row.get("id", row.get("crosswalk_id", "")), "x": x, "y": y,
                          "angle": row.get("angle", "0"), "length": round(float(row.get("length", 0)) * 0.5, 2),
                          "width": round(float(row.get("width", 0)) * 0.5, 2)})
    write_csv(SEMANTIC / "crossings.csv", ("crossing_id", "x", "y", "angle", "length", "width"), crossings)

    entrances = []
    for row in read_csv(SOURCE / "interiors.csv"):
        x, y = world_to_master(row["entry_x"], row["entry_y"])
        entrances.append({"interior_id": row.get("id", ""), "x": x, "y": y, "kind": row.get("kind", "")})
    write_csv(SEMANTIC / "building_entrances.csv", ("interior_id", "x", "y", "kind"), entrances)

    water_rows=[]
    for polygon_index,polygon in enumerate(authored_surfaces()['water'],1):
        for order,(wx,wy) in enumerate(polygon):
            x,y=world_to_master(wx,wy)
            water_rows.append({'polygon_id':f'hudson_{polygon_index:02d}','point_order':order,'x':x,'y':y})
    write_csv(SEMANTIC/'water_boundaries.csv',('polygon_id','point_order','x','y'),water_rows)
    green_rows=[]
    for polygon_index,polygon in enumerate(authored_surfaces()['green'],1):
        for order,(wx,wy) in enumerate(polygon):
            x,y=world_to_master(wx,wy)
            green_rows.append({'polygon_id':f'green_{polygon_index:02d}','point_order':order,'x':x,'y':y})
    write_csv(SEMANTIC/'green_boundaries.csv',('polygon_id','point_order','x','y'),green_rows)
    connectors = []
    for row in read_csv(SOURCE / "level_connectors.csv"):
        converted = dict(row)
        for xkey, ykey in (("x", "y"), ("start_x", "start_y"), ("end_x", "end_y")):
            if row.get(xkey) and row.get(ykey):
                converted[xkey], converted[ykey] = world_to_master(row[xkey], row[ykey])
        connectors.append(converted)
    fields = list(connectors[0]) if connectors else ("connector_id", "x", "y", "from_level", "to_level")
    write_csv(SEMANTIC / "layer_transitions.csv", fields, connectors)


def export_polygons(source_name, target_name):
    rows = []
    for row in read_csv(SOURCE / source_name.replace("water_boundaries", "water_polygons")):
        converted = dict(row)
        if row.get("x") and row.get("y"):
            converted["x"], converted["y"] = world_to_master(row["x"], row["y"])
        rows.append(converted)
    fields = list(rows[0]) if rows else ("polygon_id", "point_order", "x", "y")
    write_csv(SEMANTIC / target_name, fields, rows)


def derive_urban_blocks(roads_override,rp_override):
    old_scale = callback.VIEW_SCALE
    callback.VIEW_SCALE = 0.0625; callback.ORTHOGONAL_GRID_PX = ORTHOGONAL_GRID_PX
    masks = callback.surface_masks(1024, 512, 8192, 6144, callback.DAY, False, road_width_scale=ROAD_WIDTH_SCALE, sidewalk_scale=SIDEWALK_SCALE,roads_override=roads_override,rp_override=rp_override,surface_polygons_override=authored_surfaces())
    callback.VIEW_SCALE = old_scale
    # Conservative max-like downsampling: if any high-resolution pixel in a
    # sample cell is occupied, the coarse block solver treats it as occupied.
    # Nearest-neighbor sampling could miss a narrow diagonal road entirely.
    def conservative(mask):
        return mask.resize((256,128),Image.Resampling.BOX).point(lambda value:255 if value>0 else 0)
    blocked = conservative(masks["road"])
    water = conservative(masks["water"])
    green = conservative(masks["green"])
    seen = set()
    blocks = []
    pixels_r = blocked.load(); pixels_w = water.load(); pixels_g = green.load()
    def largest_inside_rectangle(cells):
        """Largest axis-aligned rectangle wholly contained in one road-bounded face."""
        cell_set=set(cells);min_x=min(x for x,_ in cells);max_x=max(x for x,_ in cells)
        min_y=min(y for _,y in cells);max_y=max(y for _,y in cells)
        heights=[0]*(max_x-min_x+1);best=(0,min_x,min_y,0,0)
        for y in range(min_y,max_y+1):
            for col,x in enumerate(range(min_x,max_x+1)):
                heights[col]=heights[col]+1 if (x,y) in cell_set else 0
            stack=[]
            for col,height in enumerate(heights+[0]):
                start=col
                while stack and stack[-1][1] > height:
                    left,h=stack.pop();area=h*(col-left)
                    if area>best[0]:
                        best=(area,min_x+left,y-h+1,col-left,h)
                    start=left
                if not stack or stack[-1][1] < height:
                    stack.append((start,height))
        return best[1],best[2],best[3],best[4]
    for sy in range(128):
        for sx in range(256):
            if (sx, sy) in seen or pixels_r[sx, sy] or pixels_w[sx, sy] or pixels_g[sx,sy]:
                continue
            queue = deque([(sx, sy)]); seen.add((sx, sy)); cells = []
            while queue:
                x, y = queue.popleft(); cells.append((x, y))
                for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                    if (0 <= nx < 256 and 0 <= ny < 128 and (nx, ny) not in seen
                            and not pixels_r[nx, ny] and not pixels_w[nx, ny] and not pixels_g[nx,ny]):
                        seen.add((nx, ny)); queue.append((nx, ny))
            if len(cells) < 6:
                continue
            rx,ry,rw,rh=largest_inside_rectangle(cells)
            if rw*rh < 6:
                continue
            blocks.append({"block_id": f"block_{len(blocks)+1:03d}", "x": rx*32, "y": ry*32,
                           "w": rw*32, "h": rh*32, "sample_cells": rw*rh,
                           "source_component_cells":len(cells),"fit_rule":"largest_safe_rectangle_v1",
                           "owns_sidewalk_boundary": "true"})
    write_csv(SEMANTIC / "urban_blocks.csv", ("block_id", "x", "y", "w", "h", "sample_cells",
              "source_component_cells","fit_rule","owns_sidewalk_boundary"), blocks)
    return len(blocks)


def building_atlas_metrics(atlas_name):
    audit = ROOT / "cosmetic_packs" / "nyc_gta2_callback" / "building_atlases" / f"{Path(atlas_name).stem}_scale_audit.csv"
    rows = read_csv(audit)
    if len(rows) != 16:
        raise RuntimeError(f"Building atlas scale audit missing or incomplete: {audit}")
    return {int(row["cell"]): (float(row["bbox_w"]), float(row["bbox_h"])) for row in rows}


def choose_building_sprite(district, width, height, sequence, landmark=False):
    """Select native-size art instead of stretching one block across every lot."""
    fort_atlas = "fort_lee_blocks_v1.png"
    heights_atlas = "washington_heights_blocks_v1.png"
    compact_atlas = "compact_lot_blocks_v1.png"
    metrics = {
        fort_atlas: building_atlas_metrics(fort_atlas),
        heights_atlas: building_atlas_metrics(heights_atlas),
        compact_atlas: building_atlas_metrics(compact_atlas),
    }
    if district == "fort_lee":
        candidates = [(fort_atlas, cell) for cell in range(16)]
        candidates += [(compact_atlas, cell) for cell in range(8)]
    elif landmark:
        # Three roof-plan church/parish complexes in the Washington Heights
        # sheet plus the compact-lot church in the companion sheet.
        candidates = [(heights_atlas, cell) for cell in (7, 12, 14)] + [(compact_atlas, 15)]
    else:
        candidates = [(heights_atlas, cell) for cell in range(16) if cell not in {7, 12, 14}]
        candidates += [(compact_atlas, cell) for cell in range(8, 15)]

    scored = []
    preferred = sequence % max(1, len(candidates))
    for candidate_index, (atlas_name, cell) in enumerate(candidates):
        source_width, source_height = metrics[atlas_name][cell]
        fit_ratio = min(
            width / (source_width * ATLAS_WORLD_UNITS_PER_PIXEL),
            height / (source_height * ATLAS_WORLD_UNITS_PER_PIXEL),
        )
        # Prefer scale 1.0, heavily penalize an asset that must leave the
        # accepted component-size band, and retain deterministic visual variety.
        bounded_error = abs(1.0 - min(MAX_BUILDING_SPRITE_SCALE, max(MIN_BUILDING_SPRITE_SCALE, fit_ratio)))
        outlier = max(0.0, MIN_BUILDING_SPRITE_SCALE - fit_ratio) * 8.0
        oversize = max(0.0, fit_ratio - MAX_BUILDING_SPRITE_SCALE) * 0.35
        aspect_error = abs(math.log(max(0.05, width / height) / max(0.05, source_width / source_height))) * 0.12
        variety = abs(candidate_index - preferred) * 0.0015
        scored.append((bounded_error + outlier + oversize + aspect_error + variety,
                       atlas_name, cell, source_width, source_height, fit_ratio))
    _, atlas_name, cell, source_width, source_height, fit_ratio = min(scored)
    render_ratio = min(MAX_BUILDING_SPRITE_SCALE, fit_ratio)
    status = "pass" if fit_ratio >= MIN_BUILDING_SPRITE_SCALE else "undersized_lot"
    return {
        "cosmetic_atlas": atlas_name,
        "cosmetic_cell": cell,
        "cosmetic_source_bbox_w": round(source_width, 2),
        "cosmetic_source_bbox_h": round(source_height, 2),
        "cosmetic_fit_scale_ratio": round(fit_ratio, 4),
        "cosmetic_render_scale_ratio": round(render_ratio, 4),
        "cosmetic_scale_status": status,
    }


def generate_iterated_buildings(roads_override,rp_override):
    """Create deterministic block-responsive street-wall infill.

    This is intentionally coupled to the current road/water/green masks. A change
    to road geometry therefore regenerates legal building footprints instead of
    leaving an unrelated fixed sprite scatter behind.
    """
    block_rows=read_csv(SEMANTIC/'urban_blocks.csv')
    additions=[];parcel_uses=[];parking_count=0;plaza_count=0
    district_sequences={"fort_lee":0,"washington_heights":0}
    fort_lee_families=('bui_painted_walkup_04','bui_stone_midrise_15','bui_commercial_lowrise_18',
                       'bui_concrete_tower_21','bui_warehouse_20','bui_waterfront_midrise_24')
    manhattan_families=('bui_brick_midrise_01','bui_brownstone_row_14','bui_art_deco_22',
                        'bui_concrete_tower_09','bui_commercial_corner_17','bui_painted_walkup_28')
    for idx,block in enumerate(block_rows):
        x=float(block['x']);y=float(block['y']);w=float(block['w']);h=float(block['h']);cells=int(block['sample_cells'])
        district='fort_lee' if x+w <= HUDSON_WEST_X*.5 else 'washington_heights'
        # A small fixed number of suitably sized blocks become intentional open
        # destinations. Everything else receives one or more cosmetic complexes.
        if w>=260 and h>=220 and parking_count<4 and (idx*7+3)%19 in (2,5):
            margin=max(18,min(34,min(w,h)*.08))
            parcel_uses.append({'id':f'parking_{parking_count+1:02d}','kind':'parking','district':district,
                                'x':round((x+margin)*2,2),'y':round((y+margin)*2+2048,2),
                                'w':round((w-2*margin)*2,2),'h':round((h-2*margin)*2,2),
                                'generation_rule':'intentional_parcel_destination_v1'})
            parking_count+=1
            continue
        if w>=176 and h>=160 and plaza_count<3 and (idx*11+5)%23 in (4,9):
            margin=max(16,min(30,min(w,h)*.08))
            parcel_uses.append({'id':f'plaza_{plaza_count+1:02d}','kind':'plaza','district':district,
                                'x':round((x+margin)*2,2),'y':round((y+margin)*2+2048,2),
                                'w':round((w-2*margin)*2,2),'h':round((h-2*margin)*2,2),
                                'generation_rule':'intentional_parcel_destination_v1'})
            plaza_count+=1
            continue
        if w<112 or h<112 or cells>1600:
            # Narrow residual faces are marked as plazas instead of being left as
            # unexplained empty dirt or receiving illegibly tiny building art.
            if w>=80 and h>=80:
                margin=12
                parcel_uses.append({'id':f'plaza_residual_{idx+1:03d}','kind':'plaza','district':district,
                                    'x':round((x+margin)*2,2),'y':round((y+margin)*2+2048,2),
                                    'w':round((w-2*margin)*2,2),'h':round((h-2*margin)*2,2),
                                    'generation_rule':'residual_face_plaza_v1'})
            continue
        margin=max(16,min(30,min(w,h)*.10))
        bw=w-2*margin;bh=h-2*margin
        if bw<80 or bh<80:continue
        base_x=x+margin;base_y=y+margin
        # Only genuinely oversized parcels split. Each part remains large enough
        # to read as one detailed courtyard/perimeter complex from the approved atlas.
        split_x=bw>=bh
        long_span=bw if split_x else bh
        short_span=bh if split_x else bw
        part_count=min(3,max(1,int(math.ceil(long_span/610)))) if short_span>=145 else 1
        while part_count>1 and (long_span-24*(part_count-1))/part_count < 150:
            part_count-=1
        gap=24
        span=(bw if split_x else bh)-gap*(part_count-1)
        part_span=span/part_count
        for part in range(part_count):
            px=base_x+(part_span+gap)*part if split_x else base_x
            py=base_y if split_x else base_y+(part_span+gap)*part
            pw=part_span if split_x else bw
            ph=bh if split_x else part_span
            # Alternating shallow setbacks break the repeated roof-line silhouette.
            setback=12 if (idx+part)%3==1 else 0
            if split_x: py+=setback;ph-=setback
            else: px+=setback;pw-=setback
            building_left=px*2;building_right=(px+pw)*2
            if building_left < HUDSON_EAST_X and building_right > HUDSON_WEST_X:
                continue
            district_families=fort_lee_families if building_right <= HUDSON_WEST_X else manhattan_families
            height_base=.48 if district_families is fort_lee_families else .68
            sequence=district_sequences[district]
            landmark=district=='washington_heights' and sequence in {5,21,37}
            sprite=choose_building_sprite(district,pw*2,ph*2,sequence,landmark=landmark)
            if sprite['cosmetic_scale_status']!='pass':
                # A single very narrow residual face cannot carry a full building
                # without miniaturizing every window and wall. Give it an explicit
                # service/parking use instead of weakening the art-scale contract.
                parcel_uses.append({'id':f'parking_scale_safe_{len(parcel_uses)+1:03d}','kind':'parking','district':district,
                                    'x':round(building_left,2),'y':round(py*2+2048,2),
                                    'w':round(pw*2,2),'h':round(ph*2,2),
                                    'generation_rule':'scale_safe_narrow_service_yard_v1'})
                continue
            district_sequences[district]+=1
            additions.append({'id':f'block_building_{len(additions)+1:04d}',
                              'x':round(building_left,2),'y':round(py*2+2048,2),
                              'w':round(pw*2,2),'h':round(ph*2,2),
                              'district':district,
                              'building_kind':'church_landmark' if landmark else 'urban_block',
                              'archetype_id':district_families[(idx+part*2)%len(district_families)],
                              'height_scale':round(height_base+((idx*2+part)%6)*.09,2),
                              'generation_rule':'terrain_aware_block_street_wall_v6_scale_locked',
                              'cosmetic_world_units_per_pixel':ATLAS_WORLD_UNITS_PER_PIXEL,
                              **sprite,
                              'render_mode':'late_cosmetic_sprite_v2_scale_locked'})

    layers=[];stairwells=[];scale_audit=[]
    layer_specs=((0,'ground',0),(1,'upper',10),(2,'roof',20))
    sides=('north','east','south','west')
    for building_index,row in enumerate(additions):
        for level_id,layer_kind,z_order in layer_specs:
            layers.append({'building_id':row['id'],'level_id':level_id,'layer_kind':layer_kind,
                           'z_order':z_order,'walkable':'true','visual_role':'top_layer' if layer_kind=='roof' else 'intermediate_layer',
                           'transition_policy':'attached_stairwell_v1'})
        side=sides[(building_index*3+int(row['cosmetic_cell']))%len(sides)]
        x=float(row['x']);y=float(row['y']);w=float(row['w']);h=float(row['h']);offset=18
        if side=='north':stair_x,stair_y=x+w*.5,y-offset
        elif side=='south':stair_x,stair_y=x+w*.5,y+h+offset
        elif side=='west':stair_x,stair_y=x-offset,y+h*.5
        else:stair_x,stair_y=x+w+offset,y+h*.5
        row.update({'layer_count':3,'roof_level':2,'stair_side':side,
                    'stair_x':round(stair_x,2),'stair_y':round(stair_y,2),'interaction_keys':'SPACE;C'})
        stairwells.append({'stairwell_id':f"stair_{building_index+1:04d}",'building_id':row['id'],
                           'kind':'exterior_fire_stair','side':side,'x':round(stair_x,2),'y':round(stair_y,2),
                           'from_level':0,'intermediate_level':1,'to_level':2,'interaction_keys':'SPACE;C',
                           'transition_mode':'authored_manual_stairwell_v1'})
        scale_audit.append({'building_id':row['id'],'district':row['district'],'building_kind':row['building_kind'],
                            'target_w':row['w'],'target_h':row['h'],'cosmetic_atlas':row['cosmetic_atlas'],
                            'cosmetic_cell':row['cosmetic_cell'],'source_bbox_w':row['cosmetic_source_bbox_w'],
                            'source_bbox_h':row['cosmetic_source_bbox_h'],'fit_scale_ratio':row['cosmetic_fit_scale_ratio'],
                            'render_scale_ratio':row['cosmetic_render_scale_ratio'],'status':row['cosmetic_scale_status']})
    undersized=[row for row in scale_audit if row['status']!='pass']
    if undersized:
        sample=', '.join(f"{row['building_id']}({row['target_w']}x{row['target_h']} ratio={row['fit_scale_ratio']})" for row in undersized[:8])
        raise RuntimeError(f'Building sprite scale audit failed for {len(undersized)} lots: {sample}')
    write_csv(SEMANTIC/'iterated_buildings.csv',
              ('id','x','y','w','h','district','building_kind','archetype_id','height_scale','generation_rule',
               'cosmetic_atlas','cosmetic_cell','cosmetic_world_units_per_pixel','cosmetic_source_bbox_w',
               'cosmetic_source_bbox_h','cosmetic_fit_scale_ratio','cosmetic_render_scale_ratio','cosmetic_scale_status',
               'layer_count','roof_level','stair_side','stair_x','stair_y','interaction_keys','render_mode'),additions)
    write_csv(SEMANTIC/'building_layers.csv',
              ('building_id','level_id','layer_kind','z_order','walkable','visual_role','transition_policy'),layers)
    write_csv(SEMANTIC/'building_stairwells.csv',
              ('stairwell_id','building_id','kind','side','x','y','from_level','intermediate_level','to_level','interaction_keys','transition_mode'),stairwells)
    write_csv(SEMANTIC/'building_sprite_scale_audit.csv',
              ('building_id','district','building_kind','target_w','target_h','cosmetic_atlas','cosmetic_cell',
               'source_bbox_w','source_bbox_h','fit_scale_ratio','render_scale_ratio','status'),scale_audit)
    write_csv(SEMANTIC/'iterated_parcel_uses.csv',
              ('id','kind','district','x','y','w','h','generation_rule'),parcel_uses)
    collision=[]
    for row in additions:
        x,y=world_to_master(row['x'],row['y'])
        collision.append({'building_id':row['id'],'x':x,'y':y,'w':round(float(row['w'])*.5,2),'h':round(float(row['h'])*.5,2)})
    write_csv(SEMANTIC/'buildings.csv',('building_id','x','y','w','h'),collision)
    return additions,parcel_uses


def point_in_polygon(point, polygon):
    x,y=point;inside=False
    for (x1,y1),(x2,y2) in zip(polygon,polygon[1:]+polygon[:1]):
        if (y1>y)!=(y2>y):
            at_x=(x2-x1)*(y-y1)/(y2-y1)+x1
            if x<at_x:inside=not inside
    return inside


def generate_iterated_vegetation(roads,road_points,crossings,buildings,parcel_uses):
    """Place approved trees from final sidewalks and retained green geometry."""
    trees=[];water=authored_surfaces()['water'];green=authored_surfaces()['green']
    junctions=[(float(c['x']),float(c['y'])) for c in crossings]
    building_boxes=[(float(b['x'])-20,float(b['y'])-20,float(b['x'])+float(b['w'])+20,
                     float(b['y'])+float(b['h'])+20) for b in buildings]
    use_boxes=[(float(u['x'])-16,float(u['y'])-16,float(u['x'])+float(u['w'])+16,
                float(u['y'])+float(u['h'])+16) for u in parcel_uses]
    road_segments=[]
    for road in roads:
        n=max(1,int(float(road.get('lanes',1))))
        half=max(38,n*38+10)*ROAD_WIDTH_SCALE*.5
        for a,b in zip(road_points[road['road_id']],road_points[road['road_id']][1:]):
            road_segments.append((a,b,half))
    def segment_distance(p,a,b):
        dx,dy=b[0]-a[0],b[1]-a[1];den=dx*dx+dy*dy
        if den<=1e-9:return math.hypot(p[0]-a[0],p[1]-a[1])
        t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den))
        return math.hypot(p[0]-(a[0]+t*dx),p[1]-(a[1]+t*dy))
    def legal(p,allow_parcel=False,allow_road_edge=False):
        x,y=p
        if not (80<x<16304 and 2128<y<10160):return False
        if any(point_in_polygon(p,poly) for poly in water):return False
        if any(x0<x<x1 and y0<y<y1 for x0,y0,x1,y1 in building_boxes):return False
        if not allow_parcel and any(x0<x<x1 and y0<y<y1 for x0,y0,x1,y1 in use_boxes):return False
        if any(math.hypot(x-jx,y-jy)<150 for jx,jy in junctions):return False
        if not allow_road_edge and any(segment_distance(p,a,b)<half+12 for a,b,half in road_segments):return False
        return True
    def add_tree(x,y,cell,size,district,rule):
        trees.append({'id':f'tree_{len(trees)+1:04d}','x':round(x,2),'y':round(y,2),
                      'size':round(size,2),'district':district,'cosmetic_atlas':'approved_sidewalk_trees_v1.png',
                      'cosmetic_cell':cell%16,'placement_rule':rule})

    for road_index,road in enumerate(roads):
        if road.get('bridge')=='true':continue
        n=max(1,int(float(road.get('lanes',1))))
        carriageway=max(38,n*38+10)*ROAD_WIDTH_SCALE
        sidewalk=max(28,float(road.get('sidewalk_width',28)))*SIDEWALK_SCALE
        curb=max(4,float(road.get('curb_width',4)))
        offset=carriageway*.5+curb+sidewalk*.58
        district='fort_lee' if max(x for x,_ in road_points[road['road_id']])<=HUDSON_WEST_X else 'washington_heights'
        spacing=700 if district=='fort_lee' else 560
        for segment_index,(a,b) in enumerate(zip(road_points[road['road_id']],road_points[road['road_id']][1:])):
            dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
            if length<260:continue
            ux,uy=dx/length,dy/length;nx,ny=-uy,ux
            count=max(1,int(length/spacing))
            for sample in range(count):
                t=(sample+1)/(count+1)
                side=-1 if (road_index+segment_index+sample)%2 else 1
                x=a[0]+dx*t+nx*side*offset;y=a[1]+dy*t+ny*side*offset
                if legal((x,y),allow_road_edge=True):
                    cell=road_index*5+segment_index*3+sample
                    size=142+((cell*7)%4)*14
                    add_tree(x,y,cell,size,district,'final_sidewalk_tree_pit_v1')

    # Retained parks get small authored clusters using the same approved atlas.
    for poly_index,poly in enumerate(green):
        cx=sum(x for x,_ in poly)/len(poly);cy=sum(y for _,y in poly)/len(poly)
        district='fort_lee' if cx<HUDSON_WEST_X else 'washington_heights'
        candidates=[(cx,cy)]
        step=max(1,len(poly)//4)
        candidates.extend(((cx*2+poly[i][0])/3,(cy*2+poly[i][1])/3) for i in range(0,len(poly),step))
        for candidate_index,(x,y) in enumerate(candidates[:5]):
            if point_in_polygon((x,y),poly) and legal((x,y)):
                add_tree(x,y,poly_index*7+candidate_index,156+(candidate_index%3)*18,district,'retained_park_cluster_v1')

    for use_index,use in enumerate(parcel_uses):
        if use.get('kind')!='plaza':continue
        x=float(use['x']);y=float(use['y']);w=float(use['w']);h=float(use['h'])
        inset=min(90,max(44,min(w,h)*.14))
        candidates=((x+inset,y+inset),(x+w-inset,y+inset),(x+inset,y+h-inset),(x+w-inset,y+h-inset))
        for candidate_index,(tx,ty) in enumerate(candidates):
            if legal((tx,ty),allow_parcel=True):
                add_tree(tx,ty,use_index*9+candidate_index,150+(candidate_index%2)*18,use['district'],'intentional_plaza_planter_v1')

    write_csv(SEMANTIC/'iterated_vegetation.csv',
              ('id','x','y','size','district','cosmetic_atlas','cosmetic_cell','placement_rule'),trees)
    return trees


def validate_hudson_exclusion(roads, road_points, buildings):
    """Fail generation if anything except the authored bridge enters the river."""
    violations=[]
    for road in roads:
        road_id=road['road_id']
        if road.get('bridge','false').lower() == 'true':
            continue
        for a,b in zip(road_points[road_id],road_points[road_id][1:]):
            samples=max(2,int(math.hypot(b[0]-a[0],b[1]-a[1])/96)+1)
            if any(HUDSON_WEST_X < a[0]+(b[0]-a[0])*j/samples < HUDSON_EAST_X
                   for j in range(samples+1)):
                violations.append(f'road:{road_id}')
                break
    for building in buildings:
        left=float(building['x']); right=left+float(building['w'])
        if left < HUDSON_EAST_X and right > HUDSON_WEST_X:
            violations.append(f"building:{building['id']}")
    if violations:
        raise RuntimeError('Hudson exclusion audit failed: '+', '.join(violations[:12]))
    return len(violations)


def road_network_metrics(roads, road_points):
    """Audit the hierarchy so a regular checkerboard cannot regress in."""
    segments=[]
    for road in roads:
        for a,b in zip(road_points[road['road_id']],road_points[road['road_id']][1:]):
            segments.append((road['road_id'],a,b))
    angled=sum(1 for _,a,b in segments if abs(a[0]-b[0])>1 and abs(a[1]-b[1])>1)
    intersections=set();t_junctions=0
    for idx,(rid,a,b) in enumerate(segments):
        for other_id,c,d in segments[idx+1:]:
            if rid==other_id:
                continue
            hit=segment_intersection(a,b,c,d)
            if hit is None:
                continue
            intersections.add((round(hit[0]),round(hit[1])))
            endpoint_ab=min(math.hypot(hit[0]-p[0],hit[1]-p[1]) for p in (a,b))<2
            endpoint_cd=min(math.hypot(hit[0]-p[0],hit[1]-p[1]) for p in (c,d))<2
            if endpoint_ab != endpoint_cd:
                t_junctions+=1
    orphans=[]
    def point_segment_distance(p,a,b):
        dx,dy=b[0]-a[0],b[1]-a[1];den=dx*dx+dy*dy
        if den<=1e-9:return math.hypot(p[0]-a[0],p[1]-a[1])
        t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den))
        return math.hypot(p[0]-(a[0]+t*dx),p[1]-(a[1]+t*dy))
    for road in roads:
        rid=road['road_id']
        for p in (road_points[rid][0],road_points[rid][-1]):
            if p[0]<=1 or p[0]>=16383 or p[1]<=2049 or p[1]>=10239:
                continue
            if not any(other_id!=rid and point_segment_distance(p,a,b)<=96
                       for other_id,a,b in segments):
                orphans.append(f'{rid}@{round(p[0])},{round(p[1])}')
    if orphans:
        raise RuntimeError('Road topology audit found orphan ends: '+', '.join(orphans[:12]))
    return {'segments':len(segments),'angled_segments':angled,
            'angled_segment_share':round(angled/max(1,len(segments)),3),
            'junctions':len(intersections),'t_junctions':t_junctions,'orphan_ends':len(orphans)}

def render_masters(additional_buildings, parcel_uses, vegetation, roads_override, rp_override, crossings_override):
    day = callback.render("unified_master", False, annotate=False, output_dir=OUT,
                          yellow_center_lines=False, additional_buildings=additional_buildings,
                          road_width_scale=ROAD_WIDTH_SCALE, sidewalk_scale=SIDEWALK_SCALE,
                          render_existing_buildings=False,roads_override=roads_override,rp_override=rp_override,
                          draw_source_crosswalks=False,crosswalks_override=crossings_override,
                          surface_polygons_override=authored_surfaces(),parcel_uses_override=parcel_uses,
                          vegetation_override=vegetation)
    night = callback.render("unified_master", True, annotate=False, output_dir=OUT,
                            yellow_center_lines=False, additional_buildings=additional_buildings,
                            road_width_scale=ROAD_WIDTH_SCALE, sidewalk_scale=SIDEWALK_SCALE,
                            render_existing_buildings=False,roads_override=roads_override,rp_override=rp_override,
                            draw_source_crosswalks=False,crosswalks_override=crossings_override,
                            surface_polygons_override=authored_surfaces(),parcel_uses_override=parcel_uses,
                            vegetation_override=vegetation)
    targets = []
    for source, final in ((day, OUT / "unified_composition_day.png"),
                          (night, OUT / "unified_composition_night.png")):
        Path(source).replace(final)
        targets.append(final)
    return targets


def tile_masters(masters):
    count = 0
    for master in masters:
        mode = "night" if "night" in master.name else "day"
        target = TILES / mode
        target.mkdir(parents=True, exist_ok=True)
        with Image.open(master) as image:
            assert image.size == (MASTER_W, MASTER_H)
            for row in range(MASTER_H // TILE_SIZE):
                for col in range(MASTER_W // TILE_SIZE):
                    image.crop((col*TILE_SIZE, row*TILE_SIZE, (col+1)*TILE_SIZE, (row+1)*TILE_SIZE)).save(target / f"tile_{col:02d}_{row:02d}.png")
                    count += 1
    return count


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_source():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def write_manifest(masters, block_count, tile_count, infill_count, road_count, hudson_violations, road_metrics,
                   crossing_count,parcel_uses,vegetation):
    surfaces=authored_surfaces()
    rows = [
        {"key": "pass_id", "value": PASS_ID},
        {"key": "generator_architecture", "value": "block_first_unified_composition_v1"},
        {"key": "source_commit", "value": git_source()},
        {"key": "art_pack", "value": "nyc_gta2_callback"},
        {"key": "master_size", "value": f"{MASTER_W}x{MASTER_H}"},
        {"key": "urban_blocks", "value": str(block_count)},
        {"key": "intentional_parking_parcels", "value": str(sum(u['kind']=='parking' for u in parcel_uses))},
        {"key": "intentional_plaza_parcels", "value": str(sum(u['kind']=='plaza' for u in parcel_uses))},
        {"key": "visual_tiles", "value": str(tile_count)},
        {"key": "semantic_csvs", "value": str(len(SEMANTIC_FILES))},
        {"key": "iterated_infill_buildings", "value": str(infill_count)},
        {"key": "selected_gameplay_roads", "value": str(road_count)},
        {"key": "road_selection_rule", "value": "terrain_aware_hierarchy_with_staggered_locals_v2"},
        {"key": "road_segments", "value": str(road_metrics['segments'])},
        {"key": "angled_road_segments", "value": str(road_metrics['angled_segments'])},
        {"key": "angled_road_segment_share", "value": str(road_metrics['angled_segment_share'])},
        {"key": "road_junctions", "value": str(road_metrics['junctions'])},
        {"key": "t_junctions", "value": str(road_metrics['t_junctions'])},
        {"key": "orphan_road_ends", "value": str(road_metrics['orphan_ends'])},
        {"key": "compact_approach_crossings", "value": str(crossing_count)},
        {"key": "zebra_bar_orientation", "value": "parallel_to_lane_lines_v1"},
        {"key": "zebra_span_rule", "value": "curb_to_curb_perpendicular_to_traffic_v1"},
        {"key": "hudson_exclusion_band_world", "value": f"{HUDSON_WEST_X:g}..{HUDSON_EAST_X:g}"},
        {"key": "hudson_allowed_crossing", "value": "gwb_authored"},
        {"key": "non_bridge_hudson_violations", "value": str(hudson_violations)},
        {"key": "road_width_scale", "value": str(ROAD_WIDTH_SCALE)},
        {"key": "sidewalk_scale", "value": str(SIDEWALK_SCALE)},
        {"key": "orthogonal_grid_px", "value": str(ORTHOGONAL_GRID_PX)},
        {"key": "legacy_scattered_buildings_rendered", "value": "false"},
        {"key": "retained_water_polygons", "value": str(len(surfaces['water']))},
        {"key": "retained_green_polygons", "value": str(len(surfaces['green']))},
        {"key": "source_surface_preservation", "value": "filtered_reference_polygons_with_district_caps_v1"},
        {"key": "sprite_map_iteration", "value": "terrain_aware_block_mask_street_wall_v2"},
        {"key": "late_building_cosmetic_pass", "value": "true"},
        {"key": "fort_lee_building_atlas", "value": "fort_lee_blocks_v1.png"},
        {"key": "washington_heights_building_atlas", "value": "washington_heights_blocks_v1.png"},
        {"key": "compact_lot_building_atlas", "value": "compact_lot_blocks_v1.png"},
        {"key": "building_cosmetic_assignment", "value": "district_and_native_footprint_match_v2"},
        {"key": "building_sprite_world_units_per_source_pixel", "value": str(ATLAS_WORLD_UNITS_PER_PIXEL)},
        {"key": "building_sprite_scale_band", "value": f"{MIN_BUILDING_SPRITE_SCALE:.2f}..{MAX_BUILDING_SPRITE_SCALE:.2f}"},
        {"key": "building_sprite_scale_outliers", "value": "0"},
        {"key": "building_layer_rows", "value": str(infill_count*3)},
        {"key": "building_stairwells", "value": str(infill_count)},
        {"key": "building_layer_model", "value": "ground_upper_roof_v1"},
        {"key": "building_stair_interaction_keys", "value": "SPACE;C"},
        {"key": "late_vegetation_cosmetic_pass", "value": "true"},
        {"key": "vegetation_cosmetic_atlas", "value": "approved_sidewalk_trees_v1.png"},
        {"key": "iterated_vegetation", "value": str(len(vegetation))},
        {"key": "vegetation_placement_rule", "value": "final_sidewalk_tree_pits_and_retained_parks_v1"},
        {"key": "yellow_center_lines", "value": "false"},
    ]
    for master in masters:
        rows.append({"key": f"sha256_{master.stem}", "value": sha256(master)})
    write_csv(OUT / "composition_manifest.csv", ("key", "value"), rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    if args.clean and OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    roads,rp,crossings=authored_block_network()
    road_metrics=road_network_metrics(roads,rp)
    export_semantics(roads,rp,crossings)
    block_count = derive_urban_blocks(roads,rp)
    infill,parcel_uses = generate_iterated_buildings(roads,rp)
    vegetation=generate_iterated_vegetation(roads,rp,crossings,infill,parcel_uses)
    hudson_violations = validate_hudson_exclusion(roads,rp,infill)
    masters = render_masters(infill,parcel_uses,vegetation,roads,rp,crossings)
    tile_count = tile_masters(masters)
    write_manifest(masters, block_count, tile_count, len(infill), len(roads), hudson_violations, road_metrics,
                   len(crossings),parcel_uses,vegetation)
    print(f"PASS={PASS_ID} masters=2 tiles={tile_count} roads={len(roads)} segments={road_metrics['segments']} "
          f"angled={road_metrics['angled_segments']} t_junctions={road_metrics['t_junctions']} "
          f"crossings={len(crossings)} blocks={block_count} infill={len(infill)} "
          f"parcel_uses={len(parcel_uses)} trees={len(vegetation)} semantic_csvs={len(SEMANTIC_FILES)}")


if __name__ == "__main__":
    main()
