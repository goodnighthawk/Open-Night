from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / 'mapfiles' / 'data' / 'map_001_gwb_corridor' / 'grid_v100' / 'ground_grid.json'

W, H = 64, 48
VERTICAL_ROADS = [(10, 12), (28, 30), (43, 45), (57, 59)]
HORIZONTAL_ROADS = [(8, 10), (23, 25), (38, 40)]

COLORS = [
    ('H','G','I','E','D','F','B','A','C'),
    ('Q','P','S','N','M','O','K','J','L'),
    ('a','Z','b','X','W','Y','U','T','V'),
    ('j','i','k','g','f','h','d','c','e'),
    ('s','r','t','p','o','q','m','l','n'),
]


def is_road(gx: int, gy: int) -> bool:
    return any(a <= gx <= b for a,b in VERTICAL_ROADS) or any(a <= gy <= b for a,b in HORIZONTAL_ROADS)


def stamp_rect(grid: list[list[str]], x0: int, y0: int, x1: int, y1: int, palette: tuple[str,...]) -> None:
    if x1 - x0 < 1 or y1 - y0 < 1:
        return
    tl, tc, tr, ml, fill, mr, bl, bc, br = palette
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if x == x0 and y == y0: ch = tl
            elif x == x1 and y == y0: ch = tr
            elif x == x0 and y == y1: ch = bl
            elif x == x1 and y == y1: ch = br
            elif y == y0: ch = tc
            elif y == y1: ch = bc
            elif x == x0: ch = ml
            elif x == x1: ch = mr
            else: ch = fill
            grid[y][x] = ch


def add_curbs(grid: list[list[str]]) -> None:
    # First lay road cells.
    for y in range(H):
        for x in range(W):
            if is_road(x, y):
                grid[y][x] = 'R'

    # Then put one-cell curb/sidewalk borders around roads.
    for y in range(H):
        for x in range(W):
            if is_road(x, y):
                continue
            left = x > 0 and is_road(x - 1, y)
            right = x + 1 < W and is_road(x + 1, y)
            up = y > 0 and is_road(x, y - 1)
            down = y + 1 < H and is_road(x, y + 1)
            # Corner codes chosen to match the existing city_block curb atlas.
            if right and down: grid[y][x] = '$'   # bottom-right outer
            elif left and down: grid[y][x] = '#'  # bottom-left outer
            elif right and up: grid[y][x] = '@'    # top-right outer
            elif left and up: grid[y][x] = '!'     # top-left outer
            elif right: grid[y][x] = '>'
            elif left: grid[y][x] = '<'
            elif down: grid[y][x] = 'v'
            elif up: grid[y][x] = '^'


def build_dense_blocks(grid: list[list[str]]) -> None:
    x_blocks = [(0,9), (13,27), (31,42), (46,56), (60,63)]
    y_blocks = [(0,7), (11,22), (26,37), (41,47)]
    color_i = 0
    for by, (ya,yb) in enumerate(y_blocks):
        for bx, (xa,xb) in enumerate(x_blocks):
            # One tile of curb/sidewalk is reserved at road-facing edges; buildings
            # occupy most of the remaining parcel, with narrow 1-cell alleys.
            ix0 = xa + (1 if xa == 0 else 0)
            ix1 = xb - (1 if xb == W-1 else 0)
            iy0 = ya + (1 if ya == 0 else 0)
            iy1 = yb - (1 if yb == H-1 else 0)
            width = ix1 - ix0 + 1
            height = iy1 - iy0 + 1
            if width < 2 or height < 2:
                continue
            pal = COLORS[color_i % len(COLORS)]
            color_i += 1
            # Larger parcels are split to avoid monolithic rectangles and create
            # narrow alleys without restoring giant sidewalk plazas.
            if width >= 11:
                gap = 1
                left_w = max(4, (width - gap) // 2)
                right_x0 = ix0 + left_w + gap
                stamp_rect(grid, ix0, iy0, ix0 + left_w - 1, iy1, pal)
                stamp_rect(grid, right_x0, iy0 + (by % 2), ix1, iy1, COLORS[color_i % len(COLORS)])
                color_i += 1
            else:
                # Slight setbacks vary by block but never exceed one extra cell.
                sx = 1 if (bx + by) % 3 == 0 and width >= 5 else 0
                sy = 1 if (bx * 2 + by) % 4 == 0 and height >= 5 else 0
                stamp_rect(grid, ix0 + sx, iy0 + sy, ix1, iy1, pal)


def rebuild_objects() -> list[dict]:
    objs: list[dict] = []
    # Clean crossing pieces at every arterial intersection, aligned to the 3-cell roads.
    for vx0, vx1 in VERTICAL_ROADS:
        cx = (vx0 + vx1) // 2
        for hy0, hy1 in HORIZONTAL_ROADS:
            cy = (hy0 + hy1) // 2
            objs.extend([
                {'asset':'mark_white_crossing_piece','gx':vx0,'gy':hy0-1,'width_px':110,'height_px':430,'rotation':90},
                {'asset':'mark_white_crossing_piece','gx':vx1,'gy':hy1+1,'width_px':110,'height_px':430,'rotation':90},
                {'asset':'mark_white_crossing_piece','gx':vx0-1,'gy':hy0,'width_px':110,'height_px':430},
                {'asset':'mark_white_crossing_piece','gx':vx1+1,'gy':hy1,'width_px':110,'height_px':430},
                {'asset':'mark_white_stop','gx':cx,'gy':max(0,hy0-2),'width_px':210,'height_px':116},
                {'asset':'mark_white_stop','gx':min(W-1,cx+1),'gy':min(H-1,hy1+1),'width_px':210,'height_px':116,'rotation':180},
            ])
    # Sparse, aligned road wear only on guaranteed road cells.
    wear = ['overlay_man_hole','overlay_pot_hole','overlay_road_cracks','overlay_oil_splash','overlay_road_puddle']
    road_points = [(11,4),(29,15),(44,33),(58,18),(20,24),(51,39),(43,6),(11,31)]
    for i,(gx,gy) in enumerate(road_points):
        objs.append({'asset':wear[i % len(wear)],'gx':gx,'gy':gy,'width_px':140,'height_px':160,'rotation':(i%4)*90})
    return objs


def main() -> None:
    data = json.loads(MAP.read_text(encoding='utf-8'))
    grid = [['.' for _ in range(W)] for _ in range(H)]
    add_curbs(grid)
    build_dense_blocks(grid)
    # Re-apply roads and curbs after buildings so no building can overwrite an arterial edge.
    add_curbs(grid)
    data['layers_ascii']['ground'] = [''.join(row) for row in grid]
    data['objects'] = rebuild_objects()
    data['login_spawns'] = [
        [(29.5)*256, (24.5)*256],
        [(44.5)*256, (9.5)*256],
        [(11.5)*256, (39.5)*256],
    ]
    data['map_goal'] = 'approved_city_block_dense_aligned_narrow_sidewalks'
    data['ground_alignment_repair'] = 1
    data['sidewalk_target_cells'] = 1
    data['road_width_cells'] = 3
    data.setdefault('runtime', {})['ground_playable'] = True
    data['runtime']['legacy_surface_entities'] = False
    MAP.write_text(json.dumps(data, separators=(',',':')), encoding='utf-8')

    # Structural assertions before CI/runtime validation.
    assert len(grid) == H and all(len(r) == W for r in grid)
    for x0,x1 in VERTICAL_ROADS:
        for x in range(x0,x1+1):
            assert all(grid[y][x] == 'R' for y in range(H))
    for y0,y1 in HORIZONTAL_ROADS:
        for y in range(y0,y1+1):
            assert all(grid[y][x] == 'R' for x in range(W))
    print('Rebuilt Ground: continuous 3-cell roads, aligned curbs, one-cell sidewalk target, denser parcels.')

if __name__ == '__main__':
    main()
