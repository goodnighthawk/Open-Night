#!/usr/bin/env python3
"""Build deterministic 256px next-map pavement, road, sand, and water packs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PAVEMENT_SHEET = ROOT / "assets/generated_v4_pavement/source/v4_pavement_concept_sheet.png"
STYLE_MASTER = ROOT / "assets/generated_v4_surfaces/source/coordinated_surface_style_master.png"
OUT = ROOT / "assets/generated_v4_surfaces"
CATALOG = ROOT / "assets/grid_v100/generated_surface_tiles.json"
SIZE = 256
CURB_CENTER = 128
CURB_HALF = 10


def center_square(image: Image.Image) -> Image.Image:
    side = min(image.size)
    x = (image.width - side) // 2
    y = (image.height - side) // 2
    return image.crop((x, y, x + side, y + side))


def seamless(image: Image.Image, seed: str) -> Image.Image:
    """Create a deterministic mirrored tile whose opposing edge pixels match."""
    source = center_square(image.convert("RGB"))
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    side = max(96, min(source.size) * 3 // 4)
    max_x = max(0, source.width - side)
    max_y = max(0, source.height - side)
    x = digest[0] * max_x // 255 if max_x else 0
    y = digest[1] * max_y // 255 if max_y else 0
    quarter = source.crop((x, y, x + side, y + side)).resize((128, 128), Image.Resampling.LANCZOS)
    top = Image.new("RGB", (SIZE, 128))
    top.paste(quarter, (0, 0))
    top.paste(ImageOps.mirror(quarter), (128, 0))
    tile = Image.new("RGB", (SIZE, SIZE))
    tile.paste(top, (0, 0))
    tile.paste(ImageOps.flip(top), (0, 128))
    return tile


def lock_opposing_edges(image: Image.Image) -> Image.Image:
    """Make the last row/column byte-identical to the first after detail passes."""
    result = image.copy()
    for y in range(SIZE):
        result.putpixel((SIZE - 1, y), result.getpixel((0, y)))
    for x in range(SIZE):
        result.putpixel((x, SIZE - 1), result.getpixel((x, 0)))
    return result


def tint(image: Image.Image, color: tuple[int, int, int], strength: float = 0.35) -> Image.Image:
    grey = ImageOps.grayscale(image)
    colored = ImageOps.colorize(grey, black=tuple(max(0, c // 5) for c in color), white=color)
    return Image.blend(image.convert("RGB"), colored, strength)


def crop_grid(image: Image.Image, cols: int, rows: int, col: int, row: int, gutter_ratio: float = 0.012) -> Image.Image:
    gutter_x = max(4, int(image.width * gutter_ratio))
    gutter_y = max(4, int(image.height * gutter_ratio))
    cell_w = (image.width - gutter_x * (cols + 1)) // cols
    cell_h = (image.height - gutter_y * (rows + 1)) // rows
    x0 = gutter_x + col * (cell_w + gutter_x)
    y0 = gutter_y + row * (cell_h + gutter_y)
    return image.crop((x0, y0, x0 + cell_w, y0 + cell_h))


def worn_line(draw: ImageDraw.ImageDraw, points, fill, width: int, seed: str) -> None:
    draw.line(points, fill=fill, width=width)
    digest = hashlib.sha256(seed.encode("ascii")).digest()
    if len(points) == 4:
        x0, y0, x1, y1 = points
    else:
        (x0, y0), (x1, y1) = points
    for index in range(18):
        fraction = digest[index % len(digest)] / 255.0
        x = int(x0 + (x1 - x0) * fraction)
        y = int(y0 + (y1 - y0) * fraction)
        radius = 1 + digest[(index + 7) % len(digest)] % 3
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(0, 0, 0, 0))


def material_connector(a: Image.Image, b: Image.Image, vertical: bool, seed: str) -> Image.Image:
    result = a.convert("RGB").copy()
    pixels_a, pixels_b = a.load(), b.load()
    digest = hashlib.sha256(seed.encode("ascii")).digest()
    for y in range(SIZE):
        for x in range(SIZE):
            axis = x if vertical else y
            threshold = CURB_CENTER + (digest[(x * 7 + y * 13) % len(digest)] % 25) - 12
            if axis >= threshold:
                result.putpixel((x, y), pixels_b[x, y])
    return result


def curb_straight(pavement: Image.Image, asphalt: Image.Image) -> Image.Image:
    image = pavement.copy()
    image.paste(asphalt.crop((0, CURB_CENTER + CURB_HALF, SIZE, SIZE)), (0, CURB_CENTER + CURB_HALF))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, CURB_CENTER - CURB_HALF, SIZE, CURB_CENTER + CURB_HALF), fill=(91, 94, 91))
    draw.line((0, CURB_CENTER - CURB_HALF, SIZE, CURB_CENTER - CURB_HALF), fill=(157, 162, 158), width=3)
    draw.line((0, CURB_CENTER + CURB_HALF, SIZE, CURB_CENTER + CURB_HALF), fill=(24, 28, 30), width=3)
    for x in range(0, SIZE, 64):
        draw.line((x, CURB_CENTER - CURB_HALF, x, CURB_CENTER + CURB_HALF), fill=(58, 61, 60), width=2)
    return image


def curb_corner(
    pavement: Image.Image,
    asphalt: Image.Image,
    corner: str,
    inner: bool,
    *,
    shoreline: bool = False,
) -> Image.Image:
    """Build one correctly aligned quarter-round material boundary.

    The tile centre is the theoretical sharp corner.  Moving the curve centre
    half a radius into the selected quadrant makes its straight arms meet the
    20px curb band at exactly x/y=128.  The old implementation drew a 180-degree
    ring around the tile centre, which produced the anti-aligned circular caps
    visible at every workbench junction.
    """
    radius = 64
    cx = radius if corner.endswith("l") else SIZE - radius
    cy = radius if corner.startswith("t") else SIZE - radius
    mask = Image.new("L", (SIZE, SIZE), 0)
    draw_mask = ImageDraw.Draw(mask)

    if corner == "tl":
        draw_mask.rectangle((0, 0, cx, CURB_CENTER), fill=255)
        draw_mask.rectangle((0, 0, CURB_CENTER, cy), fill=255)
    elif corner == "tr":
        draw_mask.rectangle((cx, 0, SIZE, CURB_CENTER), fill=255)
        draw_mask.rectangle((CURB_CENTER, 0, SIZE, cy), fill=255)
    elif corner == "bl":
        draw_mask.rectangle((0, CURB_CENTER, cx, SIZE), fill=255)
        draw_mask.rectangle((0, cy, CURB_CENTER, SIZE), fill=255)
    else:
        draw_mask.rectangle((cx, CURB_CENTER, SIZE, SIZE), fill=255)
        draw_mask.rectangle((CURB_CENTER, cy, SIZE, SIZE), fill=255)
    circle = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw_mask.ellipse(circle, fill=255)

    image = Image.composite(asphalt, pavement, mask) if inner else Image.composite(pavement, asphalt, mask)
    draw = ImageDraw.Draw(image)
    arc_angles = {"tl": (0, 90), "tr": (90, 180), "bl": (270, 360), "br": (180, 270)}
    segments = {
        "tl": (((0, CURB_CENTER), (cx, CURB_CENTER)), ((CURB_CENTER, 0), (CURB_CENTER, cy))),
        "tr": (((cx, CURB_CENTER), (SIZE, CURB_CENTER)), ((CURB_CENTER, 0), (CURB_CENTER, cy))),
        "bl": (((0, CURB_CENTER), (cx, CURB_CENTER)), ((CURB_CENTER, cy), (CURB_CENTER, SIZE))),
        "br": (((cx, CURB_CENTER), (SIZE, CURB_CENTER)), ((CURB_CENTER, cy), (CURB_CENTER, SIZE))),
    }[corner]

    if shoreline:
        # A restrained broken foam edge, rather than a concrete curb, follows
        # the same corner grammar at the river boundary.
        edge = (175, 181, 158)
        for start, end in segments:
            draw.line((*start, *end), fill=edge, width=2)
        draw.arc(circle, *arc_angles[corner], fill=edge, width=2)
        return image

    # ImageDraw arcs grow inward from their bounding box, whereas straight
    # lines grow around their centre.  Expand the arc bounds by half the curb
    # width so the curve is centred on the same x/y=128 datum as both arms.
    curb_outer_radius = radius + CURB_HALF
    curb_circle = (
        cx - curb_outer_radius, cy - curb_outer_radius,
        cx + curb_outer_radius, cy + curb_outer_radius,
    )
    for start, end in segments:
        draw.line((*start, *end), fill=(91, 94, 91), width=CURB_HALF * 2 + 1)
    draw.arc(curb_circle, *arc_angles[corner], fill=(91, 94, 91), width=CURB_HALF * 2 + 1)

    outer_highlight_segments = {
        "tl": (((0, CURB_CENTER - CURB_HALF), (cx, CURB_CENTER - CURB_HALF)), ((CURB_CENTER - CURB_HALF, 0), (CURB_CENTER - CURB_HALF, cy))),
        "tr": (((cx, CURB_CENTER - CURB_HALF), (SIZE, CURB_CENTER - CURB_HALF)), ((CURB_CENTER + CURB_HALF, 0), (CURB_CENTER + CURB_HALF, cy))),
        "bl": (((0, CURB_CENTER + CURB_HALF), (cx, CURB_CENTER + CURB_HALF)), ((CURB_CENTER - CURB_HALF, cy), (CURB_CENTER - CURB_HALF, SIZE))),
        "br": (((cx, CURB_CENTER + CURB_HALF), (SIZE, CURB_CENTER + CURB_HALF)), ((CURB_CENTER + CURB_HALF, cy), (CURB_CENTER + CURB_HALF, SIZE))),
    }[corner]
    outer_road_segments = {
        "tl": (((0, CURB_CENTER + CURB_HALF), (cx, CURB_CENTER + CURB_HALF)), ((CURB_CENTER + CURB_HALF, 0), (CURB_CENTER + CURB_HALF, cy))),
        "tr": (((cx, CURB_CENTER + CURB_HALF), (SIZE, CURB_CENTER + CURB_HALF)), ((CURB_CENTER - CURB_HALF, 0), (CURB_CENTER - CURB_HALF, cy))),
        "bl": (((0, CURB_CENTER - CURB_HALF), (cx, CURB_CENTER - CURB_HALF)), ((CURB_CENTER + CURB_HALF, cy), (CURB_CENTER + CURB_HALF, SIZE))),
        "br": (((cx, CURB_CENTER - CURB_HALF), (SIZE, CURB_CENTER - CURB_HALF)), ((CURB_CENTER - CURB_HALF, cy), (CURB_CENTER - CURB_HALF, SIZE))),
    }[corner]
    highlight_segments, road_segments = (
        (outer_road_segments, outer_highlight_segments) if inner
        else (outer_highlight_segments, outer_road_segments)
    )
    for start, end in highlight_segments:
        draw.line((*start, *end), fill=(157, 162, 158), width=3)
    for start, end in road_segments:
        draw.line((*start, *end), fill=(24, 28, 30), width=3)

    pavement_radius = radius + CURB_HALF if inner else radius - CURB_HALF
    road_radius = radius - CURB_HALF if inner else radius + CURB_HALF
    pavement_circle = (cx - pavement_radius, cy - pavement_radius, cx + pavement_radius, cy + pavement_radius)
    road_circle = (cx - road_radius, cy - road_radius, cx + road_radius, cy + road_radius)
    draw.arc(pavement_circle, *arc_angles[corner], fill=(157, 162, 158), width=3)
    draw.arc(road_circle, *arc_angles[corner], fill=(24, 28, 30), width=3)
    return image


def curb_ramp(top: Image.Image) -> Image.Image:
    image = top.copy()
    draw = ImageDraw.Draw(image)
    draw.rectangle((74, 92, 182, 137), fill=(107, 88, 43))
    draw.rectangle((78, 96, 178, 133), outline=(169, 139, 58), width=3)
    for y in range(102, 130, 10):
        for x in range(84 + ((y // 10) % 2) * 5, 174, 10):
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(188, 151, 62))
    draw.rectangle((72, 125, 184, 142), fill=(74, 76, 74))
    draw.line((72, 142, 184, 142), fill=(24, 28, 30), width=3)
    return image


def marking(kind: str) -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    white = (211, 214, 207, 232)
    crossing_white = (181, 186, 180, 190)
    yellow = (194, 157, 58, 235)
    if kind == "white_crossing_piece":
        draw.rounded_rectangle((74, 12, 182, 244), radius=5, fill=crossing_white)
        digest = hashlib.sha256(kind.encode("ascii")).digest()
        for index in range(24):
            x = 80 + digest[index % len(digest)] % 96
            y = 18 + digest[(index + 9) % len(digest)] % 220
            radius = 1 + digest[(index + 17) % len(digest)] % 3
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(0, 0, 0, 0))
    elif kind in {"white_repeating_single", "white_single_short"}:
        worn_line(draw, (128, 58, 128, 198), white, 18, kind)
    elif kind in {"white_single_long", "white_thick_long", "white_thick_short"}:
        worn_line(draw, (128, 0, 128, 256), white, 24 if "thick" in kind else 16, kind)
    elif kind == "white_repeating_double":
        worn_line(draw, (112, 55, 112, 201), white, 12, kind + "a")
        worn_line(draw, (144, 55, 144, 201), white, 12, kind + "b")
    elif kind in {"yellow_repeating_single", "yellow_single_short"}:
        worn_line(draw, (128, 55, 128, 201), yellow, 14, kind)
    elif kind in {"yellow_single_long"}:
        worn_line(draw, (128, 0, 128, 256), yellow, 14, kind)
    elif kind == "yellow_repeating_double":
        worn_line(draw, (116, 0, 116, 256), yellow, 11, kind + "a")
        worn_line(draw, (140, 0, 140, 256), yellow, 11, kind + "b")
    elif kind in {"white_long_arrow", "white_short_arrow"}:
        y0 = 36 if "long" in kind else 68
        worn_line(draw, (128, 220, 128, y0 + 40), white, 20, kind)
        draw.polygon(((128, y0), (82, y0 + 62), (112, y0 + 54), (128, y0 + 30),
                      (144, y0 + 54), (174, y0 + 62)), fill=white)
    elif kind == "white_stop":
        worn_line(draw, (20, 128, 236, 128), white, 34, kind)
    else:
        raise KeyError(kind)
    return image


def save(image: Image.Image, relative: str) -> str:
    path = OUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    image.resize((SIZE, SIZE), Image.Resampling.LANCZOS).save(path)
    return f"assets/generated_v4_surfaces/{relative.replace('\\', '/')}"


def main() -> None:
    if not PAVEMENT_SHEET.is_file() or not STYLE_MASTER.is_file():
        raise FileNotFoundError("approved pavement sheet and coordinated surface master are required")
    pavement_sheet = Image.open(PAVEMENT_SHEET).convert("RGB")
    master = Image.open(STYLE_MASTER).convert("RGB")
    pavement_sources = [crop_grid(pavement_sheet, 3, 2, col, 0) for col in range(3)]
    master_sources = [crop_grid(master, 4, 2, col, row) for row in range(2) for col in range(4)]

    standard_variants = [seamless(pavement_sources[0], f"standard-{i}") for i in range(4)]
    patched_variants = [seamless(pavement_sources[1], f"patched-{i}") for i in range(4)]
    plaza_variants = [seamless(pavement_sources[2], f"plaza-{i}") for i in range(4)]
    asphalt_variants = [tint(seamless(master_sources[3], f"asphalt-{i}"), (45, 49, 51), .22) for i in range(4)]
    dry_sand = tint(seamless(master_sources[4], "sand-dry"), (202, 180, 137), .18)
    compact_sand = tint(seamless(master_sources[4], "sand-compact"), (169, 146, 106), .35)
    damp_sand = tint(seamless(master_sources[5], "sand-damp"), (122, 111, 88), .32)
    coarse_sand = ImageEnhance.Contrast(seamless(master_sources[5], "sand-coarse")).enhance(1.18)
    deep_water = tint(seamless(master_sources[6], "water-deep"), (17, 60, 78), .30)
    shallow_water = tint(seamless(master_sources[7], "water-shallow"), (34, 91, 94), .30)

    tiles: dict[str, dict] = {}
    objects: dict[str, dict] = {}

    def tile(tile_id: str, image: Image.Image, relative: str, collision: str, kind: str) -> None:
        tiles[tile_id] = {"image": save(image, relative), "collision": collision, "kind": kind, "layer": "ground", "z": 0}

    for i, image in enumerate(standard_variants):
        tile(f"pavement_standard_variant_{i}", image, f"pavement/standard_{i}.png", "sidewalk", "pavement")
    for i, image in enumerate(patched_variants):
        tile(f"pavement_patched_variant_{i}", image, f"pavement/patched_{i}.png", "sidewalk", "pavement")
    for i, image in enumerate(plaza_variants):
        tile(f"pavement_plaza_variant_{i}", image, f"pavement/plaza_{i}.png", "sidewalk", "plaza")
    # Existing IDs are explicit catalog overrides; source-pack files remain untouched.
    for existing in ("pavement_h", "pavement_v", "pavement_small"):
        tiles[existing] = {"image": tiles["pavement_standard_variant_0"]["image"], "collision": "sidewalk", "kind": "pavement", "layer": "ground", "z": 0}
    tiles["pavement_pattern"] = {"image": tiles["pavement_plaza_variant_0"]["image"], "collision": "sidewalk", "kind": "plaza", "layer": "ground", "z": 0}
    tile("pavement_patch_connector_h", material_connector(standard_variants[0], patched_variants[0], False, "patch-h"), "pavement/patch_connector_h.png", "sidewalk", "pavement_transition")
    tile("pavement_patch_connector_v", material_connector(standard_variants[0], patched_variants[0], True, "patch-v"), "pavement/patch_connector_v.png", "sidewalk", "pavement_transition")
    tile("pavement_plaza_connector_h", material_connector(standard_variants[0], plaza_variants[0], False, "plaza-h"), "pavement/plaza_connector_h.png", "sidewalk", "pavement_transition")
    tile("pavement_plaza_connector_v", material_connector(standard_variants[0], plaza_variants[0], True, "plaza-v"), "pavement/plaza_connector_v.png", "sidewalk", "pavement_transition")

    curb_top = curb_straight(standard_variants[0], asphalt_variants[0])
    rotations = {"top": 0, "right": 90, "bottom": 180, "left": 270}
    for side, angle in rotations.items():
        image = curb_top.rotate(-angle, resample=Image.Resampling.BICUBIC)
        tile(f"curb_{side}", image, f"pavement/curb_{side}.png", "sidewalk", "curb")
        ramp = curb_ramp(curb_top).rotate(-angle, resample=Image.Resampling.BICUBIC)
        tile(f"curb_ramp_{side}", ramp, f"pavement/curb_ramp_{side}.png", "sidewalk", "curb_ramp")
    for corner in ("tl", "tr", "bl", "br"):
        tile(f"curb_{corner}_outer", curb_corner(standard_variants[0], asphalt_variants[0], corner, False), f"pavement/curb_{corner}_outer.png", "sidewalk", "curb_corner")
        tile(f"curb_{corner}_inner", curb_corner(standard_variants[0], asphalt_variants[0], corner, True), f"pavement/curb_{corner}_inner.png", "sidewalk", "curb_corner")

    for i, image in enumerate(asphalt_variants):
        tile(f"road_asphalt_variant_{i}", image, f"road/asphalt_{i}.png", "road", "road_surface")
    tiles["road_fill"] = {"image": tiles["road_asphalt_variant_0"]["image"], "collision": "road", "kind": "road_surface", "layer": "ground", "z": 0}
    tile("road_patched", ImageEnhance.Contrast(asphalt_variants[1]).enhance(1.2), "road/asphalt_patched.png", "road", "road_surface")

    marking_names = (
        "white_crossing_piece", "white_long_arrow", "white_repeating_double", "white_repeating_single",
        "white_short_arrow", "white_single_long", "white_single_short", "white_stop",
        "white_thick_long", "white_thick_short", "yellow_repeating_double", "yellow_repeating_single",
        "yellow_single_long", "yellow_single_short",
    )
    for name in marking_names:
        object_id = f"mark_{name}"
        objects[object_id] = {
            "image": save(marking(name), f"road/markings/{name}.png"),
            "kind": "road_marking", "layer": "ground", "z": 130,
            "native_width_px": SIZE, "native_height_px": SIZE,
        }
    objects.update({
        "mark_stop_bar": objects["mark_white_stop"],
        "mark_direction_arrow": objects["mark_white_long_arrow"],
        "mark_zebra_crossing": objects["mark_white_crossing_piece"],
        "mark_double_yellow": objects["mark_yellow_repeating_double"],
        "mark_solid_white_edge": objects["mark_white_single_long"],
        "mark_dashed_white_lane": objects["mark_white_repeating_single"],
    })

    sand_materials = {
        "sand_dry": dry_sand, "sand_compacted": compact_sand,
        "sand_damp": damp_sand, "sand_coarse_urban": coarse_sand,
    }
    for tile_id, image in sand_materials.items():
        tile(tile_id, image, f"sand/{tile_id}.png", "sidewalk", "sand")
    tile("sand_dry_to_damp_h", material_connector(dry_sand, damp_sand, False, "sand-h"), "sand/dry_to_damp_h.png", "sidewalk", "sand_transition")
    tile("sand_dry_to_damp_v", material_connector(dry_sand, damp_sand, True, "sand-v"), "sand/dry_to_damp_v.png", "sidewalk", "sand_transition")

    for frame in range(3):
        shifted = ImageChops.offset(deep_water, frame * 17, frame * 9)
        draw = ImageDraw.Draw(shifted)
        for n in range(7):
            x = (31 + n * 43 + frame * 11) % SIZE
            y = (47 + n * 29 + frame * 7) % SIZE
            for wrap_x in (-SIZE, 0, SIZE):
                for wrap_y in (-SIZE, 0, SIZE):
                    draw.arc(
                        (x + wrap_x - 18, y + wrap_y - 5, x + wrap_x + 18, y + wrap_y + 5),
                        12, 168, fill=(63, 107, 119), width=1,
                    )
        tile(f"water_deep_ripple_{frame}", lock_opposing_edges(shifted), f"water/deep_ripple_{frame}.png", "wade", "water")
    tile("water_deep", deep_water, "water/deep.png", "wade", "water")
    tile("water_shallow", shallow_water, "water/shallow.png", "wade", "water")
    tile("water_deep_to_shallow_h", material_connector(deep_water, shallow_water, False, "water-h"), "water/deep_to_shallow_h.png", "wade", "water_transition")
    tile("water_deep_to_shallow_v", material_connector(deep_water, shallow_water, True, "water-v"), "water/deep_to_shallow_v.png", "wade", "water_transition")
    tile("water_wet_sand_h", material_connector(damp_sand, shallow_water, False, "wet-h"), "water/wet_sand_h.png", "wade", "shoreline_transition")
    tile("water_wet_sand_v", material_connector(damp_sand, shallow_water, True, "wet-v"), "water/wet_sand_v.png", "wade", "shoreline_transition")

    # Straight shoreline, outside corners, and inside corners share one semantic
    # naming grammar with the neighbor-aware selector in surface_autotile.py.
    shore_top = material_connector(damp_sand, shallow_water, False, "shore-top")
    draw = ImageDraw.Draw(shore_top)
    for x in range(0, SIZE, 31):
        draw.line((x, CURB_CENTER, min(SIZE - 1, x + 17), CURB_CENTER), fill=(175, 181, 158), width=2)
    for side, angle in rotations.items():
        tile(f"shoreline_{side}", shore_top.rotate(-angle), f"shoreline/{side}.png", "sidewalk", "shoreline")
    for corner in ("tl", "tr", "bl", "br"):
        outer = curb_corner(damp_sand, shallow_water, corner, False, shoreline=True)
        inner = curb_corner(damp_sand, shallow_water, corner, True, shoreline=True)
        tile(f"shoreline_{corner}_outer", outer, f"shoreline/{corner}_outer.png", "sidewalk", "shoreline")
        tile(f"shoreline_{corner}_inner", inner, f"shoreline/{corner}_inner.png", "sidewalk", "shoreline")

    CATALOG.write_text(json.dumps({
        "format": "open-night-generated-surface-catalog-v1",
        "tile_size_px": SIZE,
        "source_authority": str(PAVEMENT_SHEET.relative_to(ROOT)).replace("\\", "/"),
        "source_style_master": str(STYLE_MASTER.relative_to(ROOT)).replace("\\", "/"),
        "release_marker_changed": False,
        "tiles": tiles,
        "objects": objects,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"NEXT_MAP_SURFACE_PACK_BUILT tiles={len(tiles)} objects={len(objects)} size={SIZE}")


if __name__ == "__main__":
    main()
