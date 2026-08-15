from __future__ import annotations

import argparse
import csv
import hashlib
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
PASS_ID = "recovery_pass_13"
ROAD_WIDTH_SCALE = 0.78
SIDEWALK_SCALE = 0.85
ORTHOGONAL_GRID_PX = 192.0
HUDSON_WEST_X = 4864.0
HUDSON_EAST_X = 10496.0

SEMANTIC_FILES = (
    "buildings.csv",
    "road_lanes.csv",
    "sidewalk_navigation.csv",
    "crossings.csv",
    "building_entrances.csv",
    "water_boundaries.csv",
    "layer_transitions.csv",
    "urban_blocks.csv",
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


def authored_block_network():
    roads=[]; rp={}; crossings=[]
    west_x=[640,1408,2240,3008,3904,4608]
    east_x=[10752,11584,12416,13120,14016,14784,15552]
    ys=[2176,2944,3712,4544,5248,6144,6976,7680,8576,9344,10112]
    def add(rid,points,major=False,bridge=False):
        roads.append({'road_id':rid,'highway':'primary' if major else 'residential',
                      'lanes':'4' if major else '2','width':'160' if major else '96',
                      'sidewalk_width':'52' if major else '38','curb_width':'5',
                      'level':'1' if bridge else '0','bridge':'true' if bridge else 'false'})
        rp[rid]=points
    for side,xs in (('west',west_x),('east',east_x)):
        for idx,x in enumerate(xs):
            y0=2048 if idx%3 else 2944
            y1=10240 if idx%4 else 9344
            add(f'block_{side}_v_{idx:02d}',[(x,y0),(x,y1)],major=idx in {2,5})
        for idx,y in enumerate(ys):
            if side=='west': x0,x1=(0 if idx%3 else 640),(4608 if idx%4 else 3904)
            else: x0,x1=(10752 if idx%4 else 11584),(16384 if idx%3 else 15552)
            add(f'block_{side}_h_{idx:02d}',[(x0,y),(x1,y)],major=idx in {2,5,8})
        for xi,x in enumerate(xs):
            for yi,y in enumerate(ys):
                if (xi+yi)%2:continue
                crossings.append({'id':f'cross_{side}_{xi:02d}_{yi:02d}','x':x,'y':y,'angle':'0',
                                  'length':'92','width':'34','stripe_width':'5','stripe_gap':'6','stop_bar_gap':'12'})
    add('gwb_authored',[(4608,6144),(10752,6144)],major=True,bridge=True)
    return roads,rp,crossings


def authored_surfaces():
    """One continuous Hudson plus a few compact, intentional neighborhood parks."""
    water=[[(4864,2048),(5120,2944),(4928,3712),(5184,4544),(4992,5248),(5056,6144),
            (4928,6976),(5184,7680),(4992,8576),(5120,9344),(4864,10240),
            (10240,10240),(10496,9344),(10240,8576),(10432,7680),(10240,6976),
            (10368,6144),(10176,5248),(10432,4544),(10240,3712),(10496,2944),(10240,2048)]]
    green=[[(1536,7680),(2048,7680),(2048,8320),(1536,8320)],
           [(13248,2944),(13760,2944),(13760,3456),(13248,3456)]]
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
    blocked = masks["road"].resize((256, 128), Image.Resampling.NEAREST)
    water = masks["water"].resize((256, 128), Image.Resampling.NEAREST)
    seen = set()
    blocks = []
    pixels_r = blocked.load(); pixels_w = water.load()
    for sy in range(128):
        for sx in range(256):
            if (sx, sy) in seen or pixels_r[sx, sy] or pixels_w[sx, sy]:
                continue
            queue = deque([(sx, sy)]); seen.add((sx, sy)); cells = []
            while queue:
                x, y = queue.popleft(); cells.append((x, y))
                for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                    if 0 <= nx < 256 and 0 <= ny < 128 and (nx, ny) not in seen and not pixels_r[nx, ny] and not pixels_w[nx, ny]:
                        seen.add((nx, ny)); queue.append((nx, ny))
            if len(cells) < 6:
                continue
            xs = [p[0] for p in cells]; ys = [p[1] for p in cells]
            blocks.append({"block_id": f"block_{len(blocks)+1:03d}", "x": min(xs)*32, "y": min(ys)*32,
                           "w": (max(xs)-min(xs)+1)*32, "h": (max(ys)-min(ys)+1)*32,
                           "sample_cells": len(cells), "owns_sidewalk_boundary": "true"})
    write_csv(SEMANTIC / "urban_blocks.csv", ("block_id", "x", "y", "w", "h", "sample_cells", "owns_sidewalk_boundary"), blocks)
    return len(blocks)


def generate_iterated_buildings(roads_override,rp_override):
    """Create deterministic block-responsive street-wall infill.

    This is intentionally coupled to the current road/water/green masks. A change
    to road geometry therefore regenerates legal building footprints instead of
    leaving an unrelated fixed sprite scatter behind.
    """
    block_rows=read_csv(SEMANTIC/'urban_blocks.csv')
    additions=[]
    families=('bui_brick_midrise_01','bui_brownstone_row_02','bui_stone_midrise_03',
              'bui_painted_walkup_04','bui_commercial_lowrise_06','bui_art_deco_10')
    for idx,block in enumerate(block_rows):
        x=float(block['x']);y=float(block['y']);w=float(block['w']);h=float(block['h']);cells=int(block['sample_cells'])
        if w<128 or h<128 or w>640 or h>640 or cells>420:
            continue
        margin=max(28,min(52,min(w,h)*.16))
        bw=w-2*margin;bh=h-2*margin
        if bw<80 or bh<80:continue
        base_x=x+margin;base_y=y+margin
        long=max(bw,bh)
        part_count=3 if long>=500 else (2 if long>=300 else 1)
        split_x=bw>=bh
        gap=20
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
            additions.append({'id':f'block_building_{len(additions)+1:04d}',
                              'x':round(building_left,2),'y':round(py*2+2048,2),
                              'w':round(pw*2,2),'h':round(ph*2,2),
                              'archetype_id':families[(idx+part*2)%len(families)],
                              'height_scale':round(.58+((idx*2+part)%6)*.08,2),
                              'generation_rule':'block_polygon_street_wall_subdivision_v3'})
    write_csv(SEMANTIC/'iterated_buildings.csv',
              ('id','x','y','w','h','archetype_id','height_scale','generation_rule'),additions)
    collision=[]
    for row in additions:
        x,y=world_to_master(row['x'],row['y'])
        collision.append({'building_id':row['id'],'x':x,'y':y,'w':round(float(row['w'])*.5,2),'h':round(float(row['h'])*.5,2)})
    write_csv(SEMANTIC/'buildings.csv',('building_id','x','y','w','h'),collision)
    return additions


def validate_hudson_exclusion(roads, road_points, buildings):
    """Fail generation if anything except the authored bridge enters the river."""
    violations=[]
    for road in roads:
        road_id=road['road_id']
        if road.get('bridge','false').lower() == 'true':
            continue
        for x,_ in road_points[road_id]:
            if HUDSON_WEST_X < float(x) < HUDSON_EAST_X:
                violations.append(f'road:{road_id}')
                break
    for building in buildings:
        left=float(building['x']); right=left+float(building['w'])
        if left < HUDSON_EAST_X and right > HUDSON_WEST_X:
            violations.append(f"building:{building['id']}")
    if violations:
        raise RuntimeError('Hudson exclusion audit failed: '+', '.join(violations[:12]))
    return len(violations)

def render_masters(additional_buildings, roads_override, rp_override, crossings_override):
    day = callback.render("unified_master", False, annotate=False, output_dir=OUT,
                          yellow_center_lines=False, additional_buildings=additional_buildings,
                          road_width_scale=ROAD_WIDTH_SCALE, sidewalk_scale=SIDEWALK_SCALE,
                          render_existing_buildings=False,roads_override=roads_override,rp_override=rp_override,
                          draw_source_crosswalks=False,crosswalks_override=crossings_override,surface_polygons_override=authored_surfaces())
    night = callback.render("unified_master", True, annotate=False, output_dir=OUT,
                            yellow_center_lines=False, additional_buildings=additional_buildings,
                            road_width_scale=ROAD_WIDTH_SCALE, sidewalk_scale=SIDEWALK_SCALE,
                            render_existing_buildings=False,roads_override=roads_override,rp_override=rp_override,
                            draw_source_crosswalks=False,crosswalks_override=crossings_override,surface_polygons_override=authored_surfaces())
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


def write_manifest(masters, block_count, tile_count, infill_count, road_count, hudson_violations):
    rows = [
        {"key": "pass_id", "value": PASS_ID},
        {"key": "generator_architecture", "value": "block_first_unified_composition_v1"},
        {"key": "source_commit", "value": git_source()},
        {"key": "art_pack", "value": "nyc_gta2_callback"},
        {"key": "master_size", "value": f"{MASTER_W}x{MASTER_H}"},
        {"key": "urban_blocks", "value": str(block_count)},
        {"key": "visual_tiles", "value": str(tile_count)},
        {"key": "semantic_csvs", "value": str(len(SEMANTIC_FILES))},
        {"key": "iterated_infill_buildings", "value": str(infill_count)},
        {"key": "selected_gameplay_roads", "value": str(road_count)},
        {"key": "road_selection_rule", "value": "authored_reference_anchor_block_grid_v1"},
        {"key": "hudson_exclusion_band_world", "value": f"{HUDSON_WEST_X:g}..{HUDSON_EAST_X:g}"},
        {"key": "hudson_allowed_crossing", "value": "gwb_authored"},
        {"key": "non_bridge_hudson_violations", "value": str(hudson_violations)},
        {"key": "road_width_scale", "value": str(ROAD_WIDTH_SCALE)},
        {"key": "sidewalk_scale", "value": str(SIDEWALK_SCALE)},
        {"key": "orthogonal_grid_px", "value": str(ORTHOGONAL_GRID_PX)},
        {"key": "legacy_scattered_buildings_rendered", "value": "false"},
        {"key": "sprite_map_iteration", "value": "block_mask_street_wall_v1"},
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
    export_semantics(roads,rp,crossings)
    block_count = derive_urban_blocks(roads,rp)
    infill = generate_iterated_buildings(roads,rp)
    hudson_violations = validate_hudson_exclusion(roads,rp,infill)
    masters = render_masters(infill,roads,rp,crossings)
    tile_count = tile_masters(masters)
    write_manifest(masters, block_count, tile_count, len(infill), len(roads), hudson_violations)
    print(f"PASS={PASS_ID} masters=2 tiles={tile_count} roads={len(roads)} blocks={block_count} infill={len(infill)} semantic_csvs={len(SEMANTIC_FILES)}")


if __name__ == "__main__":
    main()
