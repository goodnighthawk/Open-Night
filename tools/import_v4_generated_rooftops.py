"""Split the approved generated v4 rooftop sheet into runtime-ready assets."""

from __future__ import annotations

from pathlib import Path
from shutil import copy2

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(
    r"C:\Users\Pepperoni\.codex\generated_images\01a04e1a-20bb-74f0-bb82-82da1b2b97fb"
    r"\exec-a32be589-7603-4e51-943d-24b0bfd9a0ce.png"
)
OUT = ROOT / "assets" / "generated_v4_rooftops"
SOURCE_OUT = OUT / "source"

# Bounds fall in the transparent gutters between the generated 3x3 cells.
CELLS = {
    "roof_hvac_bank": (0, 0, 460, 392),
    "roof_hvac_square": (460, 0, 836, 392),
    "roof_tar_blue": (836, 0, 1261, 392),
    "roof_tar_green": (0, 392, 460, 779),
    "roof_gravel_grey": (460, 392, 836, 779),
    "roof_tar_umber": (836, 392, 1261, 779),
    "roof_tank_rust": (0, 779, 460, 1247),
    "roof_tank_moss": (460, 779, 836, 1247),
    "roof_tank_red": (836, 779, 1261, 1247),
}


def crop_to_alpha(image: Image.Image, padding: int = 8) -> Image.Image:
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("generated rooftop cell has no visible pixels")
    left = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    right = min(image.width, bbox[2] + padding)
    bottom = min(image.height, bbox[3] + padding)
    return image.crop((left, top, right, bottom))


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)

    OUT.mkdir(parents=True, exist_ok=True)
    SOURCE_OUT.mkdir(parents=True, exist_ok=True)
    copy2(SOURCE, SOURCE_OUT / "v4_rooftop_sheet_rgba.png")

    sheet = Image.open(SOURCE).convert("RGBA")
    if sheet.getchannel("A").getextrema()[0] != 0:
        raise ValueError("rooftop sheet does not contain transparent pixels")

    for name, bounds in CELLS.items():
        crop_to_alpha(sheet.crop(bounds)).save(OUT / f"{name}.png")


if __name__ == "__main__":
    main()
