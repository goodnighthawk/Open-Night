from __future__ import annotations

import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / 'mapfiles' / 'data' / 'map_001_gwb_corridor'


def read(name: str):
    with (MAP / name).open('r', encoding='utf-8-sig', newline='') as fh:
        return list(csv.DictReader(fh))


def point_segment_distance(p, a, b):
    px, py = p; ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    den = dx * dx + dy * dy
    if den <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / den))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def segment_intersects_rect(a, b, rect):
    ax, ay = a; bx, by = b; x, y, w, h = rect
    dx, dy = bx - ax, by - ay
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, ax - x), (dx, x + w - ax), (-dy, ay - y), (dy, y + h - ay)):
        if abs(p) <= 1e-12:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return True


def segment_rect_distance(a, b, rect):
    if segment_intersects_rect(a, b, rect):
        return 0.0
    x, y, w, h = rect
    ax, ay = a; bx, by = b
    def point_rect(px, py):
        dx = max(x - px, 0.0, px - (x + w))
        dy = max(y - py, 0.0, py - (y + h))
        return math.hypot(dx, dy)
    corners = ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
    return min(point_rect(ax, ay), point_rect(bx, by), *(point_segment_distance(c, a, b) for c in corners))


def main():
    roads = read('roads.csv')
    points = read('road_points.csv')
    buildings = read('buildings.csv')
    by_road = {}
    for p in points:
        by_road.setdefault(p['road_id'], []).append((int(float(p['point_order'])), float(p['x']), float(p['y'])))
    by_road = {rid: [(x, y) for _, x, y in sorted(ps)] for rid, ps in by_road.items()}

    asphalt_conflicts = []
    corridor_conflicts = []
    for b in buildings:
        rect = tuple(float(b[k]) for k in ('x', 'y', 'w', 'h'))
        for r in roads:
            ps = by_road.get(r['road_id'], [])
            if len(ps) < 2:
                continue
            dist = min(segment_rect_distance(a, c, rect) for a, c in zip(ps, ps[1:]))
            asphalt = float(r['width']) / 2.0
            corridor = asphalt + float(r.get('curb_width') or 0) + float(r.get('sidewalk_width') or 0) + float(r.get('building_setback') or 0)
            if dist + 0.01 < asphalt:
                asphalt_conflicts.append((b['id'], r['road_id'], dist, asphalt))
                break
            if dist + 0.01 < corridor:
                corridor_conflicts.append((b['id'], r['road_id'], dist, corridor))
                break

    if asphalt_conflicts or corridor_conflicts:
        print('BUILDING/ROAD AUDIT: FAIL')
        for row in (asphalt_conflicts + corridor_conflicts)[:20]:
            print(' ', row)
        raise SystemExit(1)
    print(f'BUILDING/ROAD AUDIT: PASS — {len(buildings)} buildings; 0 asphalt overlaps; 0 road/curb/sidewalk/setback corridor overlaps.')


if __name__ == '__main__':
    main()
