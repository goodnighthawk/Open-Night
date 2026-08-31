"""Import the approved generated v4 art into a self-contained project pack."""

from __future__ import annotations

from pathlib import Path
from shutil import copy2

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
GENERATED = Path(r"C:\Users\Pepperoni\.codex\generated_images\01a04e1a-20bb-74f0-bb82-82da1b2b97fb")
OUT = ROOT / "assets" / "generated_v4_art"
SOURCE_OUT = OUT / "source"
CONCEPT = ROOT / "art_review" / "sprite_inventory_2026-08-29" / "missing_art_concept_source.png"

EASY = {
    "urban_bench": "exec-832506d4-fe7e-4bbc-bd20-f6fd216b7ea1.png",
    "street_mailbox": "exec-06d7ec11-43c7-44fe-b7ff-11db5f27deee.png",
    "alley_dumpster": "exec-8439c964-4fc3-493a-9f25-291307b9cdb8.png",
    "fire_hydrant": "exec-4b160ac2-e796-44a6-91be-5efd442ad1ba.png",
    "traffic_cone": "exec-e4753799-6aaa-4d44-880e-d42f86ad1432.png",
    "street_bollard": "exec-05e1f31e-bc91-41b4-a5ba-8f6a64cc0523.png",
    "bus_shelter": "exec-07995cca-490b-4905-9d46-0485af08103a.png",
    "phone_box": "exec-9f410232-dc81-49ec-bdf9-b671fe6b51ba.png",
    "stop_sign": "exec-6b76ae7f-6711-4bc3-b9ce-6751508b0eca.png",
    "parking_sign": "exec-e1b5de06-fbc1-473e-a25d-b6e27655b3ca.png",
    "street_tree": "exec-234dd4bc-01c5-4108-a615-7103b17e19a0.png",
    "chain_fence": "exec-66d9e3db-5394-4760-a215-e7171c9f6b1e.png",
}

CONCEPT_CELLS = {
    "transition_street_door": (0, 0),
    "concept_storefront_door": (1, 0),
    "transition_fire_escape": (2, 0),
    "transition_roof_hatch": (3, 0),
    "concept_subway_entry": (0, 1),
    "concept_service_drain": (1, 1),
    "concept_trash_cluster": (2, 1),
    "concept_stray_dog": (3, 1),
}


def crop_to_alpha(image: Image.Image, padding: int = 12) -> Image.Image:
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("generated art has no visible pixels")
    left = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    right = min(image.width, bbox[2] + padding)
    bottom = min(image.height, bbox[3] + padding)
    return image.crop((left, top, right, bottom))


def remove_near_white_background(image: Image.Image) -> Image.Image:
    """Remove the one generated mail-box canvas that arrived with a white checker."""
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            r, g, b, a = pixels[x, y]
            if a and r >= 230 and g >= 230 and b >= 230:
                pixels[x, y] = (r, g, b, 0)
    return image


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    SOURCE_OUT.mkdir(parents=True, exist_ok=True)

    for name, filename in EASY.items():
        source = GENERATED / filename
        if not source.is_file():
            raise FileNotFoundError(source)
        copy2(source, SOURCE_OUT / filename)
        image = Image.open(source).convert("RGBA")
        if name == "street_mailbox":
            image = remove_near_white_background(image)
        crop_to_alpha(image).save(OUT / f"{name}.png")

    copy2(CONCEPT, SOURCE_OUT / "missing_art_concept_source.png")
    concept = Image.open(CONCEPT).convert("RGBA")
    cell_w, cell_h = concept.width // 4, concept.height // 2
    for name, (column, row) in CONCEPT_CELLS.items():
        x0, y0 = column * cell_w, row * cell_h
        cell = concept.crop((x0, y0, x0 + cell_w, y0 + cell_h))
        crop_to_alpha(cell, padding=8).save(OUT / f"{name}.png")


if __name__ == "__main__":
    main()
