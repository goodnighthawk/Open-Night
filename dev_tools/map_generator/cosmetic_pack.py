from __future__ import annotations

import csv
import hashlib
import math
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

ROOT = Path(__file__).resolve().parent
PACK_ID = 'nyc_gta2_callback'
PACK = ROOT / 'cosmetic_packs' / PACK_ID
SPRITES = PACK / 'sprites'
MATERIALS = PACK / 'materials'
SIGNS = PACK / 'signs'
LIGHTING = PACK / 'lighting'
CATALOG = PACK / 'object_catalog.csv'
ATLAS_INDEX = PACK / 'atlas_index.csv'
DAY_ATLAS = PACK / 'sprite_atlas_day.png'
NIGHT_ATLAS = PACK / 'sprite_atlas_night.png'
CELL = 128
GRID = 10

# Exactly 100 reusable environment archetypes. Surface materials are not object
# archetypes and therefore do not consume this budget.
BUDGET = [
    ('building', 28),
    ('sign_structure', 12),
    ('street_prop', 18),
    ('vegetation', 10),
    ('waterfront', 8),
    ('road_detail', 8),
    ('lighting_fixture', 12),
    ('landmark', 4),
]

FAMILIES = {
    'building': [
        'brick_midrise', 'brownstone_row', 'stone_midrise', 'painted_walkup',
        'commercial_corner', 'commercial_lowrise', 'industrial', 'warehouse',
        'concrete_tower', 'art_deco', 'parking_garage', 'waterfront_midrise',
    ],
    'sign_structure': [
        'highway_gantry', 'bridge_gantry', 'street_blade', 'speed_sign',
        'stop_sign', 'yield_sign', 'parking_sign', 'bus_sign', 'signal_mast',
    ],
    'street_prop': [
        'dumpster', 'hydrant', 'bench', 'mailbox', 'utility_box', 'cone',
        'barrier', 'chain_fence', 'bollard', 'bus_shelter', 'crate_cluster',
        'newspaper_box', 'planter', 'phone_box', 'construction_barrel',
    ],
    'vegetation': [
        'street_tree', 'park_tree', 'planter_tree', 'autumn_tree', 'shrub',
        'hedge', 'median_tree',
    ],
    'waterfront': [
        'retaining_wall', 'dock', 'pier', 'railing', 'service_fence',
        'seawall_ladder', 'mooring_post',
    ],
    'road_detail': [
        'crosswalk', 'lane_arrow', 'parking_bay', 'median', 'curb_corner',
        'stop_bar', 'bus_lane_mark', 'turn_box',
    ],
    'lighting_fixture': [
        'streetlamp', 'twin_streetlamp', 'neon_sign', 'shop_glow',
        'underpass_light', 'bridge_light', 'wall_light', 'bollard_light',
        'traffic_beacon',
    ],
    'landmark': ['gwb_tower','gwb_truss','gwb_pier','little_red_lighthouse'],
}

CATEGORY_TYPES = {
    'building': 'building|shop|warehouse|landmark_shell',
    'sign_structure': 'road_sign|traffic_signal|gantry|street_name',
    'street_prop': 'street_prop|furniture|barrier|utility',
    'vegetation': 'vegetation|tree|shrub',
    'waterfront': 'waterfront|dock|railing|retaining_wall',
    'road_detail': 'road|intersection|crosswalk|parking',
    'lighting_fixture': 'light_fixture|streetlamp|sign_light',
    'landmark': 'landmark|bridge|bridge_tower|lighthouse',
}

# Warm NYC architecture, dark asphalt, pale curbs, saturated vegetation and
# deep blue water are derived from the approved target. GTA2 influence is in
# strong silhouettes, contrast and night lighting, not direct copying.
PALETTES = {
    'building': [
        (145, 76, 54), (164, 91, 61), (128, 83, 62), (158, 132, 101),
        (132, 121, 106), (177, 119, 78), (104, 114, 116), (120, 91, 74),
    ],
    'sign_structure': [(39, 91, 64), (55, 74, 73), (136, 130, 108), (46, 91, 102)],
    'street_prop': [(77, 88, 85), (122, 88, 60), (63, 74, 75), (139, 126, 96), (85, 102, 101)],
    'vegetation': [(47, 91, 48), (64, 116, 57), (78, 132, 67), (145, 101, 42), (157, 68, 45)],
    'waterfront': [(101, 103, 99), (76, 91, 96), (127, 91, 57), (64, 84, 90)],
    'road_detail': [(48, 52, 55), (163, 158, 145), (228, 224, 207), (101, 103, 98)],
    'lighting_fixture': [(66, 76, 77), (114, 102, 76), (47, 69, 75), (112, 76, 95)],
    'landmark': [(111,119,121),(91,102,105),(132,126,112),(152,66,49)],
}
GLOW = [(255, 194, 94), (101, 173, 227), (226, 111, 162), (108, 197, 130)]


def stable_int(text: str) -> int:
    return int(hashlib.sha256(text.encode('utf-8')).hexdigest()[:12], 16)


def _font(size=10):
    try:
        return ImageFont.truetype('DejaVuSans-Bold.ttf', size)
    except Exception:
        return ImageFont.load_default()


def _shade(c, scale):
    return tuple(max(0, min(255, int(x * scale))) for x in c)


def _mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


def _px_noise(d: ImageDraw.ImageDraw, box, base, seed, density=22, alpha=255):
    x0, y0, x1, y1 = map(int, box)
    d.rectangle((x0, y0, x1, y1), fill=(*base, alpha))
    for n in range(density):
        h = stable_int(f'{seed}:{n}')
        x = x0 + 2 + h % max(1, x1 - x0 - 3)
        y = y0 + 2 + (h >> 7) % max(1, y1 - y0 - 3)
        delta = ((h >> 13) % 17) - 8
        cc = tuple(max(0, min(255, v + delta)) for v in base)
        d.rectangle((x, y, x + 1, y + 1), fill=(*cc, alpha))


def _draw_windows_front(d, x0, y0, x1, y1, seed, night, cols=5, rows=2):
    if x1 - x0 < 25 or y1 - y0 < 10:
        return
    gapx = (x1 - x0) / (cols + 1)
    gapy = (y1 - y0) / (rows + 1)
    for r in range(rows):
        for c in range(cols):
            cx = x0 + gapx * (c + 1)
            cy = y0 + gapy * (r + 1)
            lit = night and (stable_int(f'w:{seed}:{r}:{c}') % 5 in (0, 1))
            fill = (226, 177, 93, 255) if lit else ((42, 58, 63, 255) if not night else (23, 34, 38, 255))
            outline = (175, 165, 139, 255) if not night else (83, 79, 70, 255)
            d.rectangle((cx - 4, cy - 4, cx + 4, cy + 3), fill=fill, outline=outline)


def _draw_building(im, d, family, wall, seed, night):
    # Camera-neutral cosmetic proxy: top/roof texture plus a consistent down-right
    # extrusion cue. The actual game can still use camera-aware extrusion.
    x0, y0, x1, y1 = 17, 18, 101, 88
    ex, ey = 16, 28
    wall = _shade(wall, .50 if night else 1.0)
    roof_family = (126, 124, 113) if family not in ('warehouse', 'industrial', 'parking_garage') else (103, 111, 108)
    roof = _shade(_mix(roof_family, wall, .18), .54 if night else 1.0)
    front = _shade(wall, .82)
    right = _shade(wall, .62)
    outline = (22, 27, 28, 255)

    # large soft shadow with pixel-hard core, matching the approved 2.5D depth
    d.polygon([(x0 + 7, y0 + 10), (x1 + 17, y0 + 10), (x1 + 19, y1 + 22), (x0 + 9, y1 + 22)], fill=(8, 12, 13, 92))
    d.polygon([(x0, y1), (x1, y1), (x1 + ex, y1 + ey), (x0 + ex, y1 + ey)], fill=(*front, 255), outline=outline)
    d.polygon([(x1, y0), (x1 + ex, y0 + ey), (x1 + ex, y1 + ey), (x1, y1)], fill=(*right, 255), outline=outline)
    _px_noise(d, (x0, y0, x1, y1), roof, f'roof:{seed}', density=28)
    d.rectangle((x0, y0, x1, y1), outline=outline, width=2)
    # parapet
    parapet = _shade(roof, .75)
    d.line((x0 + 3, y0 + 4, x1 - 3, y0 + 4), fill=(*parapet, 255), width=2)
    d.line((x0 + 4, y0 + 4, x0 + 4, y1 - 4), fill=(*parapet, 255), width=2)

    # family-specific roof and facade vocabulary
    if family in ('brick_midrise', 'brownstone_row', 'painted_walkup', 'commercial_corner', 'waterfront_midrise'):
        brick = _shade(wall, .82)
        for xx in range(x0 + 4, x1 - 3, 12):
            d.line((xx, y1 + 2, xx + ex, y1 + ey - 2), fill=(*_shade(front, .72), 255), width=1)
        _draw_windows_front(d, x0 + 5, y1 + 2, x1 - 4, y1 + ey - 2, seed, night, cols=6 if family != 'brownstone_row' else 5, rows=2)
        # roof tar seams / skylights
        for yy in range(y0 + 13, y1 - 7, 18):
            d.line((x0 + 8, yy, x1 - 8, yy), fill=(*_shade(roof, .88), 255), width=1)
    elif family in ('stone_midrise', 'art_deco', 'concrete_tower'):
        for xx in range(x0 + 9, x1 - 5, 16):
            d.line((xx, y0 + 6, xx, y1 - 6), fill=(*_shade(roof, .86), 255), width=1)
        _draw_windows_front(d, x0 + 4, y1 + 2, x1 - 4, y1 + ey - 2, seed, night, cols=6, rows=2)
    elif family in ('industrial', 'warehouse', 'parking_garage'):
        for xx in range(x0 + 8, x1 - 6, 14):
            d.line((xx, y0 + 5, xx, y1 - 5), fill=(*_shade(roof, .79), 255), width=2)
        if family == 'parking_garage':
            for xx in range(x0 + 12, x1 - 7, 18):
                d.rectangle((xx, y1 + 2, xx + 11, y1 + ey - 3), fill=(35, 45, 48, 255), outline=(78, 86, 84, 255))

    # roof equipment: deterministic HVAC, vents, skylights, water tower
    detail = stable_int(f'roofdetail:{seed}:{family}')
    for n in range(2 + detail % 3):
        xx = x0 + 12 + ((detail >> (n * 5)) % 52)
        yy = y0 + 12 + ((detail >> (n * 7 + 3)) % 38)
        ww = 10 + ((detail >> (n * 3 + 2)) % 10)
        hh = 7 + ((detail >> (n * 4 + 1)) % 8)
        d.rectangle((xx + 2, yy + 3, xx + ww + 2, yy + hh + 3), fill=(24, 29, 30, 80))
        d.rectangle((xx, yy, xx + ww, yy + hh), fill=(104, 111, 108, 255), outline=(45, 51, 51, 255))
        d.line((xx + 3, yy + 3, xx + ww - 3, yy + 3), fill=(151, 155, 146, 255), width=1)
    if detail % 4 == 0 and family not in ('warehouse', 'parking_garage'):
        # classic rooftop water tower, an important target motif
        cx, cy = x0 + 61, y0 + 28
        d.line((cx - 8, cy + 10, cx - 11, cy + 22), fill=(60, 52, 41, 255), width=2)
        d.line((cx + 8, cy + 10, cx + 11, cy + 22), fill=(60, 52, 41, 255), width=2)
        d.ellipse((cx - 11, cy - 7, cx + 11, cy + 5), fill=(126, 91, 56, 255), outline=(59, 47, 36, 255))
        d.rectangle((cx - 10, cy - 1, cx + 10, cy + 10), fill=(113, 79, 50, 255), outline=(59, 47, 36, 255))
        d.ellipse((cx - 10, cy + 5, cx + 10, cy + 12), fill=(97, 69, 47, 255), outline=(59, 47, 36, 255))

    # storefront strips / corner accent
    if family in ('commercial_corner', 'commercial_lowrise'):
        board = (x0 + 9, y1 + 3, x1 - 8, y1 + ey - 2)
        d.rectangle(board, fill=(31, 72, 83, 255) if not night else (21, 47, 55, 255), outline=(193, 181, 150, 255))
        awning = (x0 + 12, y1 - 3, x1 - 12, y1 + 3)
        d.rectangle(awning, fill=(166, 54, 48, 255), outline=(76, 42, 37, 255))
        if night:
            glow = Image.new('RGBA', im.size, (0, 0, 0, 0)); gd = ImageDraw.Draw(glow, 'RGBA')
            gd.rectangle((x0 + 12, y1 + 1, x1 - 12, y1 + ey + 5), fill=(255, 169, 82, 45))
            im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(6)))


def _draw_sign(im, d, family, c, seed, night):
    metal = (89, 96, 95, 255) if not night else (49, 55, 56, 255)
    green = (34, 96, 65, 255) if not night else (22, 63, 44, 255)
    white = (239, 239, 224, 255)
    if family in ('highway_gantry', 'bridge_gantry'):
        left, right, top = 18, 110, 48
        d.line((left, 114, left, top), fill=metal, width=5)
        d.line((right, 114, right, top), fill=metal, width=5)
        d.line((left - 2, top, right + 2, top), fill=metal, width=5)
        board = (29, 17, 100, 55)
        d.rounded_rectangle(board, 3, fill=green, outline=(193, 198, 182, 255), width=2)
        label = 'GWB / NYC' if family == 'highway_gantry' else 'I-95 NORTH'
        d.text((37, 28), label, font=_font(11), fill=white)
        d.line((64, 55, 64, 65), fill=metal, width=2)
    elif family == 'signal_mast':
        d.line((28, 114, 28, 39), fill=metal, width=5)
        d.line((27, 40, 99, 40), fill=metal, width=5)
        d.rectangle((88, 31, 106, 63), fill=(28, 32, 31, 255), outline=(118, 122, 113, 255))
        for j, col in enumerate([(202, 55, 46), (220, 162, 49), (58, 160, 72)]):
            d.ellipse((93, 35 + j * 9, 101, 43 + j * 9), fill=(*col, 255))
    else:
        d.line((64, 115, 64, 46), fill=metal, width=4)
        fill = green if family in ('street_blade', 'bus_sign') else (230, 228, 212, 255)
        if family == 'stop_sign':
            pts = [(64, 18), (79, 24), (85, 39), (79, 54), (64, 60), (49, 54), (43, 39), (49, 24)]
            d.polygon(pts, fill=(190, 48, 42, 255), outline=(244, 235, 217, 255))
            d.text((50, 34), 'STOP', font=_font(9), fill=white)
            return
        d.rounded_rectangle((39, 20, 89, 50), 3, fill=fill, outline=(62, 67, 64, 255), width=2)
        label = {'street_blade': 'W 181 ST', 'speed_sign': '35', 'yield_sign': 'YIELD', 'parking_sign': 'P', 'bus_sign': 'BUS'}.get(family, 'SIGN')
        fg = white if fill[1] < 130 else (34, 37, 36, 255)
        bb = d.textbbox((0, 0), label, font=_font(8 if len(label) > 5 else 10))
        d.text((64 - (bb[2] - bb[0]) / 2, 34 - (bb[3] - bb[1]) / 2), label, font=_font(8 if len(label) > 5 else 10), fill=fg)


def _draw_prop(im, d, family, c, seed, night):
    outline = (35, 42, 41, 255)
    c = _shade(c, .62 if night else 1.0)
    if family == 'cone':
        d.polygon([(64, 29), (49, 94), (79, 94)], fill=(225, 110, 48, 255), outline=(80, 55, 38, 255))
        d.rectangle((44, 91, 84, 100), fill=(222, 211, 180, 255), outline=(80, 61, 43, 255))
        d.rectangle((55, 63, 73, 69), fill=(238, 229, 203, 255))
    elif family in ('chain_fence',):
        d.line((15, 94, 113, 94), fill=(105, 113, 111, 255), width=4)
        d.line((18, 35, 18, 103), fill=(96, 104, 103, 255), width=4)
        d.line((110, 35, 110, 103), fill=(96, 104, 103, 255), width=4)
        for x in range(20, 102, 14):
            d.line((x, 38, x + 40, 90), fill=(154, 164, 159, 255), width=1)
            d.line((x + 40, 38, x, 90), fill=(154, 164, 159, 255), width=1)
    elif family == 'hydrant':
        d.rectangle((56, 53, 72, 94), fill=(184, 54, 41, 255), outline=(74, 39, 34, 255))
        d.ellipse((51, 43, 77, 61), fill=(205, 67, 49, 255), outline=(74, 39, 34, 255))
        d.rectangle((47, 61, 81, 71), fill=(158, 45, 35, 255), outline=(74, 39, 34, 255))
    elif family == 'bench':
        d.rectangle((27, 60, 101, 73), fill=(132, 91, 55, 255), outline=(61, 46, 34, 255))
        d.rectangle((30, 43, 98, 56), fill=(142, 99, 60, 255), outline=(61, 46, 34, 255))
        d.line((35, 73, 31, 99), fill=(69, 74, 71, 255), width=5)
        d.line((93, 73, 97, 99), fill=(69, 74, 71, 255), width=5)
    elif family == 'bus_shelter':
        d.rectangle((19, 38, 109, 96), fill=(35, 53, 58, 75), outline=(125, 137, 132, 255), width=3)
        d.line((20, 39, 108, 39), fill=(73, 88, 89, 255), width=7)
        d.rectangle((34, 77, 95, 84), fill=(123, 82, 52, 255))
        d.rectangle((83, 45, 102, 72), fill=(44, 87, 95, 255), outline=(144, 155, 146, 255))
    elif family == 'construction_barrel':
        d.rounded_rectangle((50, 37, 78, 99), 5, fill=(221, 108, 43, 255), outline=(82, 55, 38, 255), width=2)
        d.rectangle((50, 56, 78, 63), fill=(230, 222, 198, 255))
        d.rectangle((50, 78, 78, 85), fill=(230, 222, 198, 255))
    elif family == 'planter':
        d.rectangle((42, 72, 86, 99), fill=(121, 113, 96, 255), outline=outline)
        for dx, dy, rr in [(-12, 0, 15), (8, -7, 18), (19, 3, 13)]:
            d.ellipse((64 + dx - rr, 61 + dy - rr, 64 + dx + rr, 61 + dy + rr), fill=(56, 105, 52, 255), outline=(32, 67, 35, 255))
    elif family == 'phone_box':
        d.rectangle((45, 38, 83, 100), fill=(36, 74, 87, 255), outline=(31, 44, 46, 255), width=3)
        d.rectangle((50, 45, 78, 69), fill=(47, 62, 66, 255), outline=(151, 158, 147, 255))
        d.text((51, 75), 'TEL', font=_font(8), fill=(224, 225, 210, 255))
    else:
        d.rectangle((36, 50, 92, 98), fill=(*c, 255), outline=outline, width=3)
        d.rectangle((40, 43, 88, 55), fill=(*_shade(c, 1.13), 255), outline=outline)
        if family == 'mailbox':
            d.rounded_rectangle((48, 34, 80, 98), 9, fill=(*c, 255), outline=outline, width=3)
        elif family == 'bollard':
            d.rounded_rectangle((58, 36, 70, 100), 4, fill=(*c, 255), outline=outline, width=2)
        elif family == 'newspaper_box':
            d.rectangle((46, 41, 82, 96), fill=(60, 104, 126, 255), outline=outline, width=3)
            d.rectangle((51, 48, 77, 70), fill=(222, 215, 185, 255), outline=(48, 53, 52, 255))


def _draw_tree(im, d, family, c, seed, night):
    trunk = (87, 62, 41, 255) if not night else (48, 38, 29, 255)
    d.ellipse((57, 74, 72, 113), fill=trunk, outline=(48, 37, 28, 255))
    autumn = family == 'autumn_tree' or (seed % 7 == 0 and family in ('park_tree', 'street_tree'))
    if autumn:
        cols = [(173, 91, 43), (195, 125, 43), (145, 65, 42)]
    else:
        cols = [c, _shade(c, 1.12), _mix(c, (42, 74, 42), .35)]
    if night:
        cols = [_shade(z, .50) for z in cols]
    clusters = [(-22, -3, 23), (8, -8, 25), (-7, -27, 30), (23, -30, 20), (-29, -30, 20), (2, -47, 21)]
    for j, (dx, dy, rr) in enumerate(clusters):
        cc = cols[j % len(cols)]
        d.ellipse((64 + dx - rr, 64 + dy - rr, 64 + dx + rr, 64 + dy + rr), fill=(*cc, 255), outline=(*_shade(cc, .56), 255))
    # little highlight patches improve readability at gameplay zoom
    for j in range(5):
        h = stable_int(f'leaf:{seed}:{j}')
        x = 35 + h % 58; y = 16 + (h >> 6) % 52
        d.ellipse((x, y, x + 5, y + 4), fill=(*_shade(cols[j % len(cols)], 1.16), 220))


def _draw_waterfront(im, d, family, c, seed, night):
    c = _shade(c, .58 if night else 1.0)
    if family in ('dock', 'pier'):
        d.rectangle((19, 30, 109, 103), fill=(128, 91, 56, 255), outline=(54, 43, 33, 255), width=3)
        for x in range(24, 106, 11):
            d.line((x, 33, x, 100), fill=(82, 62, 43, 255), width=2)
        for x in (23, 105):
            d.ellipse((x - 5, 91, x + 5, 118), fill=(83, 68, 51, 255), outline=(49, 41, 33, 255))
    elif family == 'railing':
        d.line((15, 90, 113, 90), fill=(118, 128, 126, 255), width=4)
        d.line((15, 49, 113, 49), fill=(118, 128, 126, 255), width=4)
        for x in range(19, 114, 14):
            d.line((x, 49, x, 94), fill=(118, 128, 126, 255), width=3)
    elif family == 'seawall_ladder':
        d.rectangle((24, 45, 104, 103), fill=(107, 108, 103, 255), outline=(54, 59, 58, 255), width=3)
        for y in range(53, 98, 11):
            d.line((57, y, 81, y), fill=(142, 151, 148, 255), width=3)
        d.line((57, 45, 57, 104), fill=(142, 151, 148, 255), width=3)
        d.line((81, 45, 81, 104), fill=(142, 151, 148, 255), width=3)
    elif family == 'mooring_post':
        d.ellipse((48, 40, 80, 57), fill=(94, 74, 51, 255), outline=(49, 43, 36, 255))
        d.rectangle((51, 48, 77, 103), fill=(102, 79, 53, 255), outline=(49, 43, 36, 255))
    else:
        _px_noise(d, (12, 38, 116, 102), c, f'waterfront:{seed}', density=20)
        d.rectangle((12, 38, 116, 102), outline=(51, 58, 57, 255), width=3)
        for x in range(20, 112, 17):
            d.line((x, 42, x, 98), fill=(*_shade(c, .72), 255), width=2)


def _draw_road_detail(im, d, family, c, seed, night):
    asphalt = (48, 52, 55, 255) if not night else (25, 30, 33, 255)
    white = (229, 226, 211, 255) if not night else (158, 157, 149, 255)
    yellow = (224, 177, 56, 255) if not night else (158, 126, 47, 255)
    d.rectangle((5, 12, 123, 116), fill=asphalt)
    for n in range(20):
        h = stable_int(f'asphalt:{seed}:{n}')
        x = 9 + h % 110; y = 16 + (h >> 7) % 95
        d.point((x, y), fill=(66, 70, 71, 255) if not night else (38, 43, 44, 255))
    if family == 'crosswalk':
        for x in range(14, 118, 13): d.rectangle((x, 23, x + 7, 105), fill=white)
    elif family == 'lane_arrow':
        d.line((64, 104, 64, 49), fill=white, width=8); d.polygon([(64, 27), (43, 55), (85, 55)], fill=white)
    elif family == 'parking_bay':
        for x in range(14, 112, 29): d.rectangle((x, 28, x + 21, 98), outline=white, width=3)
    elif family == 'median':
        d.rounded_rectangle((48, 19, 80, 109), 9, fill=(137, 130, 108, 255), outline=(197, 189, 159, 255), width=2)
        d.rectangle((60, 19, 68, 109), fill=(73, 105, 61, 255))
    elif family == 'curb_corner':
        d.pieslice((17, 20, 111, 114), 180, 270, fill=(183, 177, 160, 255)); d.pieslice((32, 35, 96, 99), 180, 270, fill=asphalt)
    elif family == 'bus_lane_mark':
        d.text((26, 52), 'BUS', font=_font(24), fill=white)
    elif family == 'turn_box':
        d.rectangle((27, 29, 101, 101), outline=yellow, width=4)
        for k in range(-20, 80, 18): d.line((25 + k, 101, 101 + k, 29), fill=yellow, width=2)
    else:
        d.rectangle((17, 58, 111, 69), fill=white)


def _draw_light(im, d, family, c, seed, night):
    glow = GLOW[seed % len(GLOW)]
    metal = (72, 82, 82, 255) if not night else (42, 49, 50, 255)
    if family in ('streetlamp', 'twin_streetlamp'):
        d.line((61, 114, 61, 35), fill=metal, width=4)
        d.arc((60, 28, 96, 60), 188, 310, fill=metal, width=4)
        d.ellipse((86, 42, 99, 51), fill=(*glow, 255))
        if family == 'twin_streetlamp':
            d.arc((26, 28, 62, 60), 230, 352, fill=metal, width=4)
            d.ellipse((25, 42, 38, 51), fill=(*glow, 255))
    elif family == 'neon_sign':
        d.rectangle((17, 37, 111, 83), fill=(24, 31, 33, 255), outline=(100, 111, 108, 255), width=2)
        d.text((28, 50), 'OPEN', font=_font(18), fill=(*glow, 255))
    elif family == 'shop_glow':
        d.rectangle((19, 29, 109, 97), fill=(63, 61, 55, 255), outline=(134, 131, 113, 255), width=3)
        d.rectangle((31, 43, 97, 84), fill=(*_shade(glow, .70), 255))
        d.line((64, 43, 64, 84), fill=(52, 56, 55, 255), width=3)
    elif family == 'traffic_beacon':
        d.line((64, 114, 64, 50), fill=metal, width=4)
        d.ellipse((54, 35, 74, 55), fill=(230, 157, 52, 255), outline=(83, 69, 48, 255))
    elif family == 'bollard_light':
        d.rounded_rectangle((56, 55, 72, 108), 4, fill=metal, outline=(35, 43, 43, 255))
        d.rectangle((58, 59, 70, 72), fill=(*glow, 255))
    else:
        d.rectangle((25, 48, 103, 69), fill=metal, outline=(34, 40, 40, 255))
        for x in range(34, 101, 18): d.ellipse((x, 54, x + 8, 62), fill=(*glow, 255))


def _draw_landmark(im, d, family, c, seed, night):
    steel=(104,115,118,255) if not night else (52,62,66,255)
    edge=(39,47,50,255)
    if family=='gwb_tower':
        # compact suspension-tower icon with open arch and cross bracing
        d.rectangle((35,16,51,112),fill=steel,outline=edge,width=2);d.rectangle((77,16,93,112),fill=steel,outline=edge,width=2)
        for y in (28,49,70,91):d.line((48,y,80,y),fill=steel,width=5)
        d.arc((47,27,81,83),180,360,fill=(170,178,173,255),width=3)
        d.line((39,25,89,103),fill=(145,153,151,255),width=2);d.line((89,25,39,103),fill=(145,153,151,255),width=2)
        d.line((18,34,37,25),fill=(115,124,125,255),width=2);d.line((91,25,112,34),fill=(115,124,125,255),width=2)
    elif family=='gwb_truss':
        d.rectangle((10,47,118,83),outline=steel,width=5)
        for x in range(14,112,18):
            d.line((x,79,x+18,51),fill=steel,width=3);d.line((x,51,x+18,79),fill=steel,width=3)
        d.line((10,42,118,42),fill=(160,165,158,255),width=3)
    elif family=='gwb_pier':
        d.polygon([(42,30),(86,30),(94,108),(34,108)],fill=(117,118,109,255),outline=(55,58,56,255))
        for y in range(43,100,14):d.line((39,y,90,y),fill=(82,86,83,255),width=2)
    else:
        d.rectangle((57,45,72,109),fill=(164,55,43,255),outline=(76,41,35,255),width=2);d.rectangle((48,38,81,50),fill=(204,211,203,255),outline=(76,81,79,255),width=2);d.polygon([(47,38),(64,22),(82,38)],fill=(151,47,40,255),outline=(76,41,35,255));d.ellipse((59,31,69,41),fill=(245,205,99,255) if night else (93,122,127,255))

def draw_archetype(category, family, color, seed, night=False):
    im = Image.new('RGBA', (CELL, CELL), (0, 0, 0, 0))
    d = ImageDraw.Draw(im, 'RGBA')
    if category == 'building': _draw_building(im, d, family, color, seed, night)
    elif category == 'sign_structure': _draw_sign(im, d, family, color, seed, night)
    elif category == 'street_prop': _draw_prop(im, d, family, color, seed, night)
    elif category == 'vegetation': _draw_tree(im, d, family, color, seed, night)
    elif category == 'waterfront': _draw_waterfront(im, d, family, color, seed, night)
    elif category == 'road_detail': _draw_road_detail(im, d, family, color, seed, night)
    elif category == 'lighting_fixture': _draw_light(im, d, family, color, seed, night)
    elif category == 'landmark': _draw_landmark(im, d, family, color, seed, night)
    if night and category in ('lighting_fixture', 'sign_structure'):
        # local glow is intentionally separate from the map lighting layer, but a
        # tiny sprite-local bloom improves readability of emissive fixtures.
        bloom = im.filter(ImageFilter.GaussianBlur(5))
        im = Image.alpha_composite(bloom.putalpha(55) if False else Image.new('RGBA', im.size, (0,0,0,0)), im)
    return im


def _make_material(path: Path, base, seed: str, kind: str, size=64):
    im = Image.new('RGB', (size, size), base); d = ImageDraw.Draw(im)
    for n in range(120):
        h = stable_int(f'{seed}:{n}')
        x = h % size; y = (h >> 7) % size; delta = ((h >> 13) % 17) - 8
        c = tuple(max(0, min(255, v + delta)) for v in base)
        d.point((x, y), fill=c)
    if kind == 'sidewalk':
        for x in range(0, size, 16): d.line((x, 0, x, size), fill=_shade(base, .88))
        for y in range(0, size, 16): d.line((0, y, size, y), fill=_shade(base, .88))
    elif kind == 'water':
        for y in range(5, size, 11): d.line((0, y, size, y + 2), fill=_shade(base, 1.15), width=1)
    elif kind == 'grass':
        for n in range(30):
            h = stable_int(f'grass:{seed}:{n}'); x=h%size; y=(h>>5)%size
            d.line((x, y, x+2, y-3), fill=_shade(base, .72), width=1)
    elif kind == 'brick':
        for y in range(0, size, 10):
            d.line((0,y,size,y), fill=_shade(base,.76))
            shift = 5 if (y//10)%2 else 0
            for x in range(shift,size,16): d.line((x,y,x,y+10),fill=_shade(base,.78))
    elif kind == 'roof':
        for x in range(0,size,18): d.line((x,0,x,size),fill=_shade(base,.90))
    path.parent.mkdir(parents=True, exist_ok=True); im.save(path)


def build_materials():
    if MATERIALS.exists(): shutil.rmtree(MATERIALS)
    MATERIALS.mkdir(parents=True, exist_ok=True)
    specs = {
        'land_day.png': ((92, 96, 82), 'grass'),
        'land_night.png': ((37, 43, 39), 'grass'),
        'asphalt_day.png': ((49, 54, 58), 'asphalt'),
        'asphalt_night.png': ((27, 32, 36), 'asphalt'),
        'sidewalk_day.png': ((190, 182, 162), 'sidewalk'),
        'sidewalk_night.png': ((94, 91, 83), 'sidewalk'),
        'curb_day.png': ((226, 216, 190), 'sidewalk'),
        'curb_night.png': ((125, 119, 104), 'sidewalk'),
        'water_day.png': ((18, 93, 137), 'water'),
        'water_night.png': ((10, 52, 78), 'water'),
        'grass_day.png': ((61, 116, 61), 'grass'),
        'grass_night.png': ((31, 61, 36), 'grass'),
        'plaza_day.png': ((174, 164, 142), 'sidewalk'),
        'plaza_night.png': ((86, 82, 73), 'sidewalk'),
        'roof_tar_day.png': ((92, 91, 84), 'roof'),
        'roof_tar_night.png': ((46, 48, 47), 'roof'),
        'brick_red.png': ((151, 79, 55), 'brick'),
        'brick_red_night.png': ((78, 43, 36), 'brick'),
        'stone_warm.png': ((158, 142, 116), 'brick'),
        'stone_warm_night.png': ((79, 73, 64), 'brick'),
        'bridge_deck.png': ((75, 81, 83), 'asphalt'),
        'bridge_deck_night.png': ((35, 42, 46), 'asphalt'),
    }
    for name, (base, kind) in specs.items(): _make_material(MATERIALS/name, base, name, kind)


def build_sign_textures():
    if SIGNS.exists(): shutil.rmtree(SIGNS)
    SIGNS.mkdir(parents=True, exist_ok=True)
    panels = [
        ('gwb_nyc.png', 'GWB / NYC', 'I-95 NORTH'),
        ('washington_heights.png', 'WASHINGTON HTS', 'W 181 ST'),
        ('fort_lee.png', 'FORT LEE', 'HUDSON TERRACE'),
    ]
    for fn, a, b in panels:
        im=Image.new('RGBA',(256,96),(0,0,0,0)); d=ImageDraw.Draw(im)
        d.rounded_rectangle((4,4,252,92),7,fill=(32,91,62,255),outline=(227,229,212,255),width=4)
        d.text((18,18),a,font=_font(23),fill=(244,245,229,255)); d.text((18,54),b,font=_font(16),fill=(232,235,221,255))
        im.save(SIGNS/fn)


def build_lighting_textures():
    if LIGHTING.exists(): shutil.rmtree(LIGHTING)
    LIGHTING.mkdir(parents=True, exist_ok=True)
    for name, col in [('warm',(255,186,83)),('cool',(94,161,224)),('amber',(249,149,69)),('red',(226,68,65)),('blue',(74,113,238))]:
        s=256; im=Image.new('RGBA',(s,s),(0,0,0,0)); px=im.load(); cx=cy=s/2
        for y in range(s):
            for x in range(s):
                r=math.hypot(x-cx,y-cy)/(s/2)
                if r>=1: continue
                a=int(105*(1-r)**2)
                px[x,y]=(*col,a)
        im.save(LIGHTING/f'glow_{name}.png')


def build_pack():
    if PACK.exists(): shutil.rmtree(PACK)
    SPRITES.mkdir(parents=True, exist_ok=True)
    rows=[]; index=[]; idx=0
    prefix={'building':'bui','sign_structure':'sig','street_prop':'pro','vegetation':'veg','waterfront':'wat','road_detail':'roa','lighting_fixture':'lig','landmark':'lan'}
    for category, count in BUDGET:
        fams=FAMILIES[category]; pals=PALETTES[category]
        for j in range(count):
            family=fams[j%len(fams)]; color=pals[(j//len(fams)+j)%len(pals)]
            aid=f'{prefix[category]}_{family}_{j+1:02d}'
            seed=stable_int(aid)
            day=draw_archetype(category,family,color,seed,False); night=draw_archetype(category,family,color,seed,True)
            day_rel=f'sprites/{aid}_day.png'; night_rel=f'sprites/{aid}_night.png'
            day.save(PACK/day_rel); night.save(PACK/night_rel)
            rows.append({
                'archetype_id':aid,'category':category,'family':family,'render_mode':'2.5d' if category in ('building','sign_structure','street_prop','vegetation','waterfront','lighting_fixture','landmark') else 'surface_overlay',
                'base_w_px':CELL,'base_h_px':CELL,'height_px':70 if category=='landmark' else (34 if category=='building' else (62 if category=='sign_structure' else 20)),
                'supports_night':'true','compatible_game_types':CATEGORY_TYPES[category],
                'day_sprite':day_rel,'night_sprite':night_rel,
                'notes':'Approved NYC/GWB cosmetic archetype with GTA2-inspired readability; gameplay semantics are external.'
            })
            x=(idx%GRID)*CELL;y=(idx//GRID)*CELL;index.append({'archetype_id':aid,'cell_index':idx,'x':x,'y':y,'w':CELL,'h':CELL});idx+=1
    assert len(rows)==100, len(rows)
    with CATALOG.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with ATLAS_INDEX.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(index[0]));w.writeheader();w.writerows(index)
    for night,path in [(False,DAY_ATLAS),(True,NIGHT_ATLAS)]:
        atlas=Image.new('RGBA',(CELL*GRID,CELL*GRID),(18,22,23,255) if night else (236,233,220,255))
        for row,cell in zip(rows,index):
            sp=Image.open(PACK/(row['night_sprite'] if night else row['day_sprite'])).convert('RGBA')
            atlas.alpha_composite(sp,(int(cell['x']),int(cell['y'])))
        atlas.save(path)
    build_materials(); build_sign_textures(); build_lighting_textures()
    return rows


def load_catalog():
    if not CATALOG.exists(): build_pack()
    with CATALOG.open('r',encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))


if __name__=='__main__':
    print(f'Built {len(build_pack())} environment archetypes in {PACK}')
