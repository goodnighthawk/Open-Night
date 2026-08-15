from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw

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
PASS_ID = "recovery_pass_06"
ROAD_WIDTH_SCALE = 0.78
SIDEWALK_SCALE = 0.85

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


def export_semantics(road_ids):
    buildings = []
    for row in read_csv(SOURCE / "buildings.csv"):
        x, y = world_to_master(row["x"], row["y"])
        buildings.append({"building_id": row["id"], "x": x, "y": y,
                          "w": round(float(row["w"]) * 0.5, 2),
                          "h": round(float(row["h"]) * 0.5, 2)})
    write_csv(SEMANTIC / "buildings.csv", ("building_id", "x", "y", "w", "h"), buildings)

    points = {}
    for row in read_csv(SOURCE / "road_points.csv"):
        points.setdefault(row["road_id"], []).append(row)
    roads = {row["road_id"]: row for row in read_csv(SOURCE / "roads.csv") if row['road_id'] in road_ids}
    lanes = []
    walks = []
    for road_id, rows in points.items():
        if road_id not in road_ids:
            continue
        road = roads.get(road_id, {})
        for row in rows:
            x, y = world_to_master(row["x"], row["y"])
            base = {"road_id": road_id, "point_order": row["point_order"], "x": x, "y": y,
                    "level": road.get("level", "0")}
            lanes.append(dict(base, width=round(float(road.get("width", 0)) * 0.5, 2),
                              lanes=road.get("lanes", "1")))
            if float(road.get("sidewalk_width", 0) or 0) > 0:
                walks.append(dict(base, sidewalk_width=round(float(road["sidewalk_width"]) * 0.5, 2)))
    write_csv(SEMANTIC / "road_lanes.csv", ("road_id", "point_order", "x", "y", "level", "width", "lanes"), lanes)
    write_csv(SEMANTIC / "sidewalk_navigation.csv", ("road_id", "point_order", "x", "y", "level", "sidewalk_width"), walks)

    crossings = []
    for row in read_csv(SOURCE / "crosswalks.csv"):
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

    export_polygons("water_polygons.csv", "water_boundaries.csv")
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


def derive_urban_blocks(road_ids):
    old_scale = callback.VIEW_SCALE
    callback.VIEW_SCALE = 0.0625
    masks = callback.surface_masks(1024, 512, 8192, 6144, callback.DAY, False, road_ids=road_ids, road_width_scale=ROAD_WIDTH_SCALE, sidewalk_scale=SIDEWALK_SCALE)
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


def generate_iterated_buildings(road_ids):
    """Create deterministic block-responsive street-wall infill.

    This is intentionally coupled to the current road/water/green masks. A change
    to road geometry therefore regenerates legal building footprints instead of
    leaving an unrelated fixed sprite scatter behind.
    """
    old_scale = callback.VIEW_SCALE
    callback.VIEW_SCALE = 0.125
    masks = callback.surface_masks(2048, 1024, 8192, 6144, callback.DAY, False, road_ids=road_ids, road_width_scale=ROAD_WIDTH_SCALE, sidewalk_scale=SIDEWALK_SCALE)
    callback.VIEW_SCALE = old_scale
    forbidden = Image.new('L', masks['road'].size, 0)
    for key in ('road', 'water', 'green'):
        forbidden = ImageChops.lighter(forbidden, masks[key])
    # Reference-driven frontage band: infill may only appear near an existing
    # street, never in arbitrary undeveloped land. At this sampling scale the
    # 81px dilation reaches roughly 320 world pixels from the asphalt edge.
    road_pixels = np.asarray(masks['road'], dtype=np.uint8) > 0
    road_integral = road_pixels.cumsum(axis=0).cumsum(axis=1)
    def has_road_near(x, y, radius=40):
        x0=max(0,x-radius); y0=max(0,y-radius); x1=min(2047,x+radius); y1=min(1023,y+radius)
        total=int(road_integral[y1,x1])
        if x0: total-=int(road_integral[y1,x0-1])
        if y0: total-=int(road_integral[y0-1,x1])
        if x0 and y0: total+=int(road_integral[y0-1,x0-1])
        return total>0
    occupancy = Image.new('L', forbidden.size, 0)
    od = ImageDraw.Draw(occupancy)
    existing = read_csv(SOURCE / 'buildings.csv')
    for row in existing:
        x0 = int(float(row['x']) * .125); y0 = int((float(row['y']) - 2048) * .125)
        x1 = int((float(row['x']) + float(row['w'])) * .125); y1 = int((float(row['y']) + float(row['h']) - 2048) * .125)
        od.rectangle((x0-4, y0-4, x1+4, y1+4), fill=255)
    fp = forbidden.load(); op = occupancy.load()
    additions = []
    families = ('bui_brick_midrise_01', 'bui_brownstone_row_02', 'bui_stone_midrise_03',
                'bui_painted_walkup_04', 'bui_commercial_lowrise_06', 'bui_art_deco_10')
    # 32 master px = 64 world px. Candidate modules combine into long street walls.
    candidates = ((48, 28), (40, 28), (28, 40), (32, 28), (24, 28), (24, 24))
    for gy in range(12, 1012, 20):
        for gx in range(12, 2036, 20):
            if len(additions) >= 500:
                break
            if fp[gx, gy] or op[gx, gy] or not has_road_near(gx, gy):
                continue
            shape = candidates[(gx * 17 + gy * 31) % len(candidates)]
            w, h = shape
            x0, y0 = gx - w//2, gy - h//2; x1, y1 = gx + w//2, gy + h//2
            if x0 < 2 or y0 < 2 or x1 >= 2046 or y1 >= 1022:
                continue
            # Corners plus a regular interior sample prevent roads/water/parks
            # from crossing large candidate footprints.
            legal = True
            for yy in range(y0, y1+1, 6):
                for xx in range(x0, x1+1, 6):
                    if fp[xx, yy] or op[xx, yy]:
                        legal = False; break
                if not legal: break
            if not legal:
                continue
            idx = len(additions)
            family = families[(gx//20 + 3*(gy//20)) % len(families)]
            row = {'id': f'infill_{idx+1:04d}', 'x': round(x0/0.125, 2),
                   'y': round(y0/0.125 + 2048, 2), 'w': round((x1-x0)/0.125, 2),
                   'h': round((y1-y0)/0.125, 2), 'archetype_id': family,
                   'height_scale': round(.55 + ((gx+gy) % 5)*.08, 2),
                   'generation_rule': 'block_mask_street_wall_v1'}
            additions.append(row)
            od.rectangle((x0-5, y0-5, x1+5, y1+5), fill=255)
    write_csv(SEMANTIC / 'iterated_buildings.csv',
              ('id','x','y','w','h','archetype_id','height_scale','generation_rule'), additions)
    return additions


def render_masters(additional_buildings, road_ids):
    day = callback.render("unified_master", False, annotate=False, output_dir=OUT,
                          yellow_center_lines=False, additional_buildings=additional_buildings, road_ids=road_ids,
                          road_width_scale=ROAD_WIDTH_SCALE, sidewalk_scale=SIDEWALK_SCALE)
    night = callback.render("unified_master", True, annotate=False, output_dir=OUT,
                            yellow_center_lines=False, additional_buildings=additional_buildings, road_ids=road_ids,
                            road_width_scale=ROAD_WIDTH_SCALE, sidewalk_scale=SIDEWALK_SCALE)
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


def write_manifest(masters, block_count, tile_count, infill_count, road_count):
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
        {"key": "road_selection_rule", "value": "connected_reference_without_support_overlays_v1"},
        {"key": "road_width_scale", "value": str(ROAD_WIDTH_SCALE)},
        {"key": "sidewalk_scale", "value": str(SIDEWALK_SCALE)},
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
    road_ids = selected_gameplay_roads()
    export_semantics(road_ids)
    block_count = derive_urban_blocks(road_ids)
    infill = generate_iterated_buildings(road_ids)
    masters = render_masters(infill, road_ids)
    tile_count = tile_masters(masters)
    write_manifest(masters, block_count, tile_count, len(infill), len(road_ids))
    print(f"PASS={PASS_ID} masters=2 tiles={tile_count} roads={len(road_ids)} blocks={block_count} infill={len(infill)} semantic_csvs={len(SEMANTIC_FILES)}")


if __name__ == "__main__":
    main()
