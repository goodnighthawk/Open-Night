from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "art_review" / "sprite_inventory_2026-08-29"

BG = (13, 18, 23, 255)
PANEL = (23, 31, 39, 255)
EDGE = (55, 75, 88, 255)
TEXT = (231, 237, 231, 255)
MUTED = (151, 171, 178, 255)
AMBER = (236, 177, 63, 255)
CYAN = (85, 199, 218, 255)


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    windows = Path("C:/Windows/Fonts")
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    try:
        return ImageFont.truetype(str(windows / name), size)
    except OSError:
        return ImageFont.load_default()


def open_asset(relative: str) -> Image.Image:
    path = ROOT / relative
    if path.suffix == ".b64":
        raw = base64.b64decode(path.read_text(encoding="utf-8"))
        return Image.open(io.BytesIO(raw)).convert("RGBA")
    return Image.open(path).convert("RGBA")


def first_frame(image: Image.Image, frame: int = 256) -> Image.Image:
    for y in range(0, image.height, frame):
        for x in range(0, image.width, frame):
            crop = image.crop((x, y, min(x + frame, image.width), min(y + frame, image.height)))
            if crop.getbbox():
                return crop
    return image


def fit(image: Image.Image, width: int, height: int) -> Image.Image:
    image = image.copy()
    bbox = image.getbbox()
    if bbox:
        image = image.crop(bbox)
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    return image


def make_sheet(title: str, subtitle: str, items: list[tuple[str, str, str]], output: Path) -> None:
    cols = 4
    cell_w, cell_h = 330, 285
    header_h = 150
    rows = (len(items) + cols - 1) // cols
    canvas = Image.new("RGBA", (cols * cell_w, header_h + rows * cell_h), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((34, 24), title, font=font(34, True), fill=TEXT)
    draw.text((35, 75), subtitle, font=font(19), fill=MUTED)
    draw.line((34, 118, canvas.width - 34, 118), fill=EDGE, width=2)

    for index, (label, detail, source) in enumerate(items):
        col, row = index % cols, index // cols
        x, y = col * cell_w, header_h + row * cell_h
        panel = (x + 14, y + 8, x + cell_w - 14, y + cell_h - 14)
        draw.rounded_rectangle(panel, radius=10, fill=PANEL, outline=EDGE, width=2)
        image = open_asset(source)
        if "master_dual_camera" in source:
            image = first_frame(image)
        image = fit(image, 250, 178)
        ix = x + (cell_w - image.width) // 2
        iy = y + 24 + (174 - image.height) // 2
        canvas.alpha_composite(image, (ix, iy))
        draw.text((x + 30, y + 207), label, font=font(19, True), fill=TEXT)
        draw.text((x + 30, y + 237), detail, font=font(15), fill=AMBER if "placed" in detail else CYAN)

    canvas.convert("RGB").save(output, quality=95)


def wrap_concept(source: Path, output: Path) -> None:
    concept = Image.open(source).convert("RGBA")
    concept.thumbnail((1320, 880), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (1380, 1030), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((34, 24), "MISSING ART — CONCEPT DIRECTIONS", font=font(34, True), fill=TEXT)
    draw.text((35, 75), "New artwork required; concept only, not sliced or runtime-ready", font=font(19), fill=MUTED)
    draw.line((34, 118, canvas.width - 34, 118), fill=EDGE, width=2)
    x = (canvas.width - concept.width) // 2
    canvas.alpha_composite(concept, (x, 135))
    labels = "Apartment door  •  Storefront door  •  Fire escape  •  Roof hatch  •  Subway entry  •  Service drain  •  Trash cluster  •  Stray dog"
    draw.text((42, 990), labels, font=font(16), fill=AMBER)
    canvas.convert("RGB").save(output, quality=95)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    implemented = [
        ("Street lighting", "45 lamps placed", "cosmetic_packs/nyc_gta2_callback/sprites/lig_streetlamp_10_night.png"),
        ("Road center lines", "116 yellow pieces placed", "assets/source_packs/city_block/road_markings/yellow_repeating_single.png"),
        ("Crosswalks", "384 crossing pieces placed", "assets/source_packs/city_block/road_markings/white_crossing_piece.png"),
        ("Curb drains", "31 drains placed", "assets/source_packs/city_block/road_overlays/curb_drain.png"),
        ("Manholes", "4 overlays placed", "assets/source_packs/city_block/road_overlays/man_hole.png"),
        ("Road wear", "29 decals placed", "assets/source_packs/city_block/road_overlays/road_cracks.png"),
        ("Facade awnings", "25 awnings placed", "assets/source_packs/city_block/roof_top_decorations/awning_blue.png"),
        ("Roof HVAC", "21 roof units placed", "assets/source_packs/city_block/roof_top_decorations/aircon_unit.png"),
        ("Roof pipework", "52+ roof details placed", "assets/source_packs/city_block/roof_top_decorations/pipe_work_04.png"),
        ("Building tile family", "25 enterable buildings", "assets/source_packs/city_block/premade_buildings/red_building_01.png"),
        ("Player/NPC identity", "runtime animated sprite", "assets/characters/master_dual_camera/topdown/fluid/tshirt_blue_curly/walk_8_8dir.png"),
        ("Player vehicles", "runtime animated sheet", "assets/cars/player_sheets/player_sheet_01.png.b64"),
    ]
    easy = [
        ("Fire hydrant", "art ready; not placed", "cosmetic_packs/nyc_gta2_callback/sprites/pro_hydrant_17_night.png"),
        ("Bench", "art ready; not placed", "cosmetic_packs/nyc_gta2_callback/sprites/pro_bench_03_night.png"),
        ("Mailbox", "art ready; not placed", "cosmetic_packs/nyc_gta2_callback/sprites/pro_mailbox_04_night.png"),
        ("Dumpster", "art ready; not placed", "cosmetic_packs/nyc_gta2_callback/sprites/pro_dumpster_16_night.png"),
        ("Traffic cone", "art ready; not placed", "cosmetic_packs/nyc_gta2_callback/sprites/pro_cone_06_night.png"),
        ("Bollard", "art ready; not placed", "cosmetic_packs/nyc_gta2_callback/sprites/pro_bollard_09_night.png"),
        ("Bus shelter", "art ready; not placed", "cosmetic_packs/nyc_gta2_callback/sprites/pro_bus_shelter_10_night.png"),
        ("Phone box", "art ready; not placed", "cosmetic_packs/nyc_gta2_callback/sprites/pro_phone_box_14_night.png"),
        ("Stop sign", "art ready; not placed", "cosmetic_packs/nyc_gta2_callback/sprites/sig_stop_sign_05_night.png"),
        ("Parking sign", "art ready; not placed", "cosmetic_packs/nyc_gta2_callback/sprites/sig_parking_sign_07_night.png"),
        ("Tree variants", "art ready; not placed", "cosmetic_packs/nyc_gta2_callback/sprites/veg_street_tree_08_night.png"),
        ("Chain fence", "art ready; not placed", "cosmetic_packs/nyc_gta2_callback/sprites/pro_chain_fence_08_night.png"),
    ]

    make_sheet(
        "CURRENTLY IMPLEMENTED — MAP 001",
        "Representative sprites verified in the v4 grid map or active runtime",
        implemented,
        OUT / "01_currently_implemented_examples.png",
    )
    make_sheet(
        "EASY NEXT ADDS — ART ALREADY EXISTS",
        "Matching night sprites are present; they mainly need catalog entries and safe authored placement",
        easy,
        OUT / "02_easy_unimplemented_examples.png",
    )

    generated = OUT / "missing_art_concept_source.png"
    if generated.exists():
        wrap_concept(generated, OUT / "03_missing_art_concepts.png")


if __name__ == "__main__":
    main()
