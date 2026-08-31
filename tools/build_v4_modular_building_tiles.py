"""Build seam-safe v4 roof/parapet autotiles from approved generated artwork."""

from __future__ import annotations

import json
from pathlib import Path
from shutil import copy2

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
GENERATED_SOURCE_FALLBACK = Path(
    r"C:\Users\Pepperoni\.codex\generated_images\01a04e1a-20bb-74f0-bb82-82da1b2b97fb"
    r"\exec-113b8d95-6cae-4ae4-b84a-ec8d3abfcbce.png"
)
OUT = ROOT / "assets" / "generated_v4_buildings"
SOURCE_OUT = OUT / "source"
PROJECT_SOURCE = SOURCE_OUT / "roof_membrane_source.png"
CATALOG_OUT = ROOT / "assets" / "grid_v100" / "generated_building_tiles.json"
REVIEW_OUT = ROOT / "art_review" / "sprite_inventory_2026-08-29" / "v4_modular_roof_tileset.png"

SIZE = 256
EDGE = 64
FAR_EDGE = SIZE - EDGE
ROLES = (
    "fill", "top_center", "bottom_center", "left", "right",
    "top_left_outer", "top_right_outer", "bottom_left_outer", "bottom_right_outer",
    "top_left_inner", "top_right_inner", "bottom_left_inner", "bottom_right_inner",
)
THEMES = {
    "blue": (49, 77, 94),
    "dark_green": (39, 66, 58),
    "green": (56, 88, 66),
    "red": (102, 55, 46),
    "yellow": (117, 91, 49),
}


def seamless_material(source: Image.Image) -> Image.Image:
    """Mirror a source crop so opposite edges match exactly."""
    side = min(source.size)
    left = (source.width - side) // 2
    top = (source.height - side) // 2
    square = source.crop((left, top, left + side, top + side)).resize((128, 128), Image.Resampling.LANCZOS)
    top_half = Image.new("RGB", (SIZE, 128))
    top_half.paste(square, (0, 0))
    top_half.paste(ImageOps.mirror(square), (128, 0))
    material = Image.new("RGB", (SIZE, SIZE))
    material.paste(top_half, (0, 0))
    material.paste(ImageOps.flip(top_half), (0, 128))
    return material


def tinted_material(base: Image.Image, tint: tuple[int, int, int]) -> Image.Image:
    grey = ImageOps.grayscale(base)
    colored = ImageOps.colorize(grey, black=(12, 16, 18), white=tint)
    return Image.blend(base, colored, 0.34)


def roof_mask(role: str) -> Image.Image:
    mask = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(mask)
    if role == "fill":
        draw.rectangle((0, 0, SIZE, SIZE), fill=255)
    elif role == "top_center":
        draw.rectangle((0, EDGE, SIZE, SIZE), fill=255)
    elif role == "bottom_center":
        draw.rectangle((0, 0, SIZE, FAR_EDGE), fill=255)
    elif role == "left":
        draw.rectangle((EDGE, 0, SIZE, SIZE), fill=255)
    elif role == "right":
        draw.rectangle((0, 0, FAR_EDGE, SIZE), fill=255)
    elif role == "top_left_outer":
        draw.rectangle((EDGE, EDGE, SIZE, SIZE), fill=255)
    elif role == "top_right_outer":
        draw.rectangle((0, EDGE, FAR_EDGE, SIZE), fill=255)
    elif role == "bottom_left_outer":
        draw.rectangle((EDGE, 0, SIZE, FAR_EDGE), fill=255)
    elif role == "bottom_right_outer":
        draw.rectangle((0, 0, FAR_EDGE, FAR_EDGE), fill=255)
    else:
        draw.rectangle((0, 0, SIZE, SIZE), fill=255)
        if role == "top_left_inner":
            draw.rectangle((0, 0, EDGE - 1, EDGE - 1), fill=0)
        elif role == "top_right_inner":
            draw.rectangle((FAR_EDGE + 1, 0, SIZE, EDGE - 1), fill=0)
        elif role == "bottom_left_inner":
            draw.rectangle((0, FAR_EDGE + 1, EDGE - 1, SIZE), fill=0)
        elif role == "bottom_right_inner":
            draw.rectangle((FAR_EDGE + 1, FAR_EDGE + 1, SIZE, SIZE), fill=0)
        else:
            raise KeyError(role)
    return mask


def segments_for(role: str) -> tuple[tuple[str, int, int, int], ...]:
    mapping = {
        "fill": (),
        "top_center": (("h", EDGE, 0, SIZE),),
        "bottom_center": (("h", FAR_EDGE, 0, SIZE),),
        "left": (("v", EDGE, 0, SIZE),),
        "right": (("v", FAR_EDGE, 0, SIZE),),
        "top_left_outer": (("h", EDGE, EDGE, SIZE), ("v", EDGE, EDGE, SIZE)),
        "top_right_outer": (("h", EDGE, 0, FAR_EDGE), ("v", FAR_EDGE, EDGE, SIZE)),
        "bottom_left_outer": (("h", FAR_EDGE, EDGE, SIZE), ("v", EDGE, 0, FAR_EDGE)),
        "bottom_right_outer": (("h", FAR_EDGE, 0, FAR_EDGE), ("v", FAR_EDGE, 0, FAR_EDGE)),
        "top_left_inner": (("h", EDGE, 0, EDGE), ("v", EDGE, 0, EDGE)),
        "top_right_inner": (("h", EDGE, FAR_EDGE, SIZE), ("v", FAR_EDGE, 0, EDGE)),
        "bottom_left_inner": (("h", FAR_EDGE, 0, EDGE), ("v", EDGE, FAR_EDGE, SIZE)),
        "bottom_right_inner": (("h", FAR_EDGE, FAR_EDGE, SIZE), ("v", FAR_EDGE, FAR_EDGE, SIZE)),
    }
    return mapping[role]


def add_parapet(image: Image.Image, role: str, tint: tuple[int, int, int]) -> None:
    draw = ImageDraw.Draw(image)
    dark = tuple(max(0, c - 37) for c in tint)
    mid = tuple(min(255, c + 18) for c in tint)
    light = tuple(min(255, c + 55) for c in tint)
    for axis, position, start, end in segments_for(role):
        if axis == "h":
            draw.rectangle((start, position - 13, end, position + 13), fill=(7, 10, 12, 255))
            draw.rectangle((start, position - 10, end, position + 9), fill=dark + (255,))
            draw.line((start, position - 7, end, position - 7), fill=light + (255,), width=3)
            draw.line((start, position + 6, end, position + 6), fill=mid + (255,), width=2)
            for x in range(max(64, ((start + 63) // 64) * 64), end, 64):
                draw.line((x, position - 9, x, position + 8), fill=(19, 22, 23, 255), width=2)
                draw.ellipse((x - 2, position - 4, x + 2, position), fill=(139, 116, 83, 255))
        else:
            draw.rectangle((position - 13, start, position + 13, end), fill=(7, 10, 12, 255))
            draw.rectangle((position - 10, start, position + 9, end), fill=dark + (255,))
            draw.line((position - 7, start, position - 7, end), fill=light + (255,), width=3)
            draw.line((position + 6, start, position + 6, end), fill=mid + (255,), width=2)
            for y in range(max(64, ((start + 63) // 64) * 64), end, 64):
                draw.line((position - 9, y, position + 8, y), fill=(19, 22, 23, 255), width=2)
                draw.ellipse((position - 4, y - 2, position, y + 2), fill=(139, 116, 83, 255))

    # Reinforce every bend with a small rusted cap plate.
    if "left" in role or "right" in role:
        x = EDGE if "left" in role else FAR_EDGE
        y = EDGE if role.startswith("top") else FAR_EDGE
        draw.rectangle((x - 14, y - 14, x + 14, y + 14), fill=(35, 28, 24, 255))
        draw.rectangle((x - 10, y - 10, x + 10, y + 10), fill=mid + (255,))
        for bx, by in ((x - 7, y - 7), (x + 7, y - 7), (x - 7, y + 7), (x + 7, y + 7)):
            draw.ellipse((bx - 1, by - 1, bx + 1, by + 1), fill=(170, 126, 77, 255))


def build_tile(base: Image.Image, role: str, tint: tuple[int, int, int]) -> Image.Image:
    roof = tinted_material(base, tint).convert("RGBA")
    # Exterior pixels are genuinely transparent.  The first production pass
    # used a nearly black material here, which exposed every 256px sprite
    # canvas as a box around irregular buildings in the map workbench.
    outside = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    mask = roof_mask(role)
    result = Image.composite(roof, outside, mask)
    add_parapet(result, role, tint)
    missing = {
        "fill": set(),
        "top_center": {"top"}, "bottom_center": {"bottom"},
        "left": {"left"}, "right": {"right"},
        "top_left_outer": {"top", "left"}, "top_right_outer": {"top", "right"},
        "bottom_left_outer": {"bottom", "left"}, "bottom_right_outer": {"bottom", "right"},
        # Inner corners retain every cardinal neighbor; only a diagonal is open.
        "top_left_inner": set(), "top_right_inner": set(),
        "bottom_left_inner": set(), "bottom_right_inner": set(),
    }[role]
    # Every occupied-neighbor edge is copied from the same seamless roof base.
    # This makes shared Ground/Roof cell borders byte-identical, including the
    # otherwise troublesome joins into concave courtyard corners.
    result_px, roof_px = result.load(), roof.load()
    if "left" not in missing:
        for y in range(SIZE):
            result_px[0, y] = roof_px[0, y]
    if "right" not in missing:
        for y in range(SIZE):
            result_px[SIZE - 1, y] = roof_px[SIZE - 1, y]
    if "top" not in missing:
        for x in range(SIZE):
            result_px[x, 0] = roof_px[x, 0]
    if "bottom" not in missing:
        for x in range(SIZE):
            result_px[x, SIZE - 1] = roof_px[x, SIZE - 1]
    return result


def build_review(tiles: dict[tuple[str, str], Image.Image]) -> None:
    order = (
        "fill", "top_center", "bottom_center", "left",
        "right", "top_left_outer", "top_right_outer", "bottom_left_outer",
        "bottom_right_outer", "top_left_inner", "top_right_inner", "bottom_left_inner",
        "bottom_right_inner",
    )
    thumb = 150
    margin = 26
    header = 86
    canvas = Image.new("RGB", (margin * 2 + thumb * 4, header + margin + thumb * 4), (11, 17, 22))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((margin, 22), "V4 MODULAR ROOF AUTOTILES - BLUE THEME", fill=(231, 238, 236), font=font)
    draw.text((margin, 46), "fill / edges / outer corners / inner corners", fill=(105, 193, 207), font=font)
    for index, role in enumerate(order):
        x = margin + (index % 4) * thumb
        y = header + (index // 4) * thumb
        image = tiles[("blue", role)].resize((thumb - 6, thumb - 6), Image.Resampling.LANCZOS)
        canvas.paste(image.convert("RGB"), (x, y))
        draw.rectangle((x, y, x + thumb - 6, y + thumb - 6), outline=(72, 100, 115), width=1)
        draw.text((x + 5, y + 5), role, fill=(225, 235, 235), font=font, stroke_width=2, stroke_fill=(8, 12, 15))
    REVIEW_OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(REVIEW_OUT)


def main() -> None:
    source_path = PROJECT_SOURCE if PROJECT_SOURCE.is_file() else GENERATED_SOURCE_FALLBACK
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    OUT.mkdir(parents=True, exist_ok=True)
    SOURCE_OUT.mkdir(parents=True, exist_ok=True)
    if source_path != PROJECT_SOURCE:
        copy2(source_path, PROJECT_SOURCE)

    source = Image.open(PROJECT_SOURCE).convert("RGB")
    base = seamless_material(source)
    tiles: dict[tuple[str, str], Image.Image] = {}
    catalog = {"tiles": {}}
    for theme, tint in THEMES.items():
        theme_dir = OUT / theme
        theme_dir.mkdir(parents=True, exist_ok=True)
        for role in ROLES:
            tile = build_tile(base, role, tint)
            tile.save(theme_dir / f"{role}.png")
            tiles[(theme, role)] = tile
            catalog["tiles"][f"bld_{theme}_{role}"] = {
                "image": f"assets/generated_v4_buildings/{theme}/{role}.png",
                "collision": "blocked",
                "kind": "building_tile",
                "layer": "ground",
                "z": 40,
            }

    CATALOG_OUT.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    build_review(tiles)


if __name__ == "__main__":
    main()
