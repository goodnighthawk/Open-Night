#!/usr/bin/env python3
from __future__ import annotations

"""Import player-approved top-down pixel-car sheets into Open Night.

The importer intentionally does *not* copy the historical civilian fleet forward.
It replaces passenger categories represented by the submitted sheets and retains
legacy rows only for vehicle categories with no replacement (emergency, bus,
truck, utility, etc.).  Sheet images are stored as base64 text so the GitHub
contents workflow can carry the approved binary art without one file per car.
"""

import argparse
import base64
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CARS = ROOT / "assets" / "cars"
LEGACY_MANIFEST = CARS / "vehicle_manifest.csv"
PLAYER_MANIFEST = CARS / "player_vehicle_manifest.csv"
SHEET_DIR = CARS / "player_sheets"

DEFAULT_REPLACED_CATEGORIES = {"sedan", "compact", "sports"}


@dataclass(frozen=True)
class Crop:
    x: int
    y: int
    w: int
    h: int


def _runs(values: list[bool], min_gap: int = 2) -> list[tuple[int, int]]:
    raw: list[tuple[int, int]] = []
    start = None
    for i, on in enumerate(values + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            raw.append((start, i))
            start = None
    if not raw:
        return []
    merged = [raw[0]]
    for a, b in raw[1:]:
        pa, pb = merged[-1]
        if a - pb <= min_gap:
            merged[-1] = (pa, b)
        else:
            merged.append((a, b))
    return merged


def _foreground_mask(image: Image.Image) -> list[list[bool]]:
    rgba = image.convert("RGBA")
    w, h = rgba.size
    corners = [rgba.getpixel((0, 0)), rgba.getpixel((w - 1, 0)), rgba.getpixel((0, h - 1)), rgba.getpixel((w - 1, h - 1))]
    bg = max(corners, key=corners.count)
    transparent_bg = bg[3] < 32
    mask: list[list[bool]] = []
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b, a = rgba.getpixel((x, y))
            if a < 24:
                row.append(False)
                continue
            if transparent_bg:
                row.append(True)
                continue
            # Treat white/near-white presentation backgrounds as empty while
            # preserving pale highlights within the car body by also requiring
            # proximity to the sampled corner colour.
            close_bg = max(abs(r - bg[0]), abs(g - bg[1]), abs(b - bg[2])) <= 12
            near_white = min(r, g, b) >= 244 and min(bg[0], bg[1], bg[2]) >= 244
            row.append(not (close_bg or near_white))
        mask.append(row)
    return mask


def detect_crops(path: Path) -> list[Crop]:
    image = Image.open(path).convert("RGBA")
    w, h = image.size
    mask = _foreground_mask(image)
    row_threshold = max(2, int(w * 0.004))
    col_threshold = max(2, int(h * 0.004))
    row_on = [sum(mask[y]) >= row_threshold for y in range(h)]
    col_on = [sum(1 for y in range(h) if mask[y][x]) >= col_threshold for x in range(w)]
    rows = [(a, b) for a, b in _runs(row_on, 3) if b - a >= 8]
    cols = [(a, b) for a, b in _runs(col_on, 3) if b - a >= 8]

    crops: list[Crop] = []
    for y0, y1 in rows:
        for x0, x1 in cols:
            points = [(x, y) for y in range(y0, y1) for x in range(x0, x1) if mask[y][x]]
            if len(points) < 80:
                continue
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            bx0, bx1 = max(0, min(xs) - 2), min(w, max(xs) + 3)
            by0, by1 = max(0, min(ys) - 2), min(h, max(ys) + 3)
            cw, ch = bx1 - bx0, by1 - by0
            if cw < 8 or ch < 12:
                continue
            # Top-down vehicle sources are expected to be taller than wide; a
            # horizontal sheet cell remains valid because runtime rotates it.
            ratio = max(cw, ch) / max(1, min(cw, ch))
            if ratio < 1.15 or ratio > 5.0:
                continue
            crops.append(Crop(bx0, by0, cw, ch))

    # De-duplicate identical boxes that can arise when projection bands merge.
    unique = sorted(set(crops), key=lambda c: (c.y, c.x, c.h, c.w))
    return unique


def infer_category(crop: Crop, source_name: str = "") -> str:
    normalized_source = source_name.lower().replace("-", "").replace("_", "")
    sports_markers = (
        "mclaren", "lotuselise", "porsche911", "audir8",
        "lamborghini", "ferrari458",
    )
    if any(marker in normalized_source for marker in sports_markers):
        return "sports"
    length = max(crop.w, crop.h)
    width = min(crop.w, crop.h)
    ratio = length / max(1, width)
    if ratio <= 1.72:
        return "sports"
    if ratio <= 2.02:
        return "compact"
    return "sedan"


def base_dimensions(category: str) -> tuple[int, int, float, float, float, float]:
    if category == "compact":
        return (44, 21, 38.0, 17.0, 1.05, 10.0)
    if category == "sports":
        return (52, 24, 46.0, 20.0, 1.08, 8.0)
    return (48, 24, 42.0, 20.0, 1.0, 12.0)


def load_legacy() -> list[dict[str, str]]:
    with LEGACY_MANIFEST.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def encode_sheet(src: Path, number: int) -> str:
    SHEET_DIR.mkdir(parents=True, exist_ok=True)
    dest = SHEET_DIR / f"player_sheet_{number:02d}.png.b64"
    dest.write_text(base64.b64encode(src.read_bytes()).decode("ascii"), encoding="ascii")
    return str(dest.relative_to(CARS)).replace("\\", "/")


def build_manifest(inputs: Iterable[Path], replaced_categories: set[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    new_categories: set[str] = set()
    next_index = 0

    for sheet_no, src in enumerate(inputs, start=1):
        crops = detect_crops(src)
        if not crops:
            raise RuntimeError(f"No vehicle sprites detected in {src}")
        sheet_file = encode_sheet(src, sheet_no)
        for slot, crop in enumerate(crops):
            category = infer_category(crop, src.name)
            new_categories.add(category)
            render_length, render_width, collision_length, collision_width, speed_factor, spawn_weight = base_dimensions(category)
            rows.append({
                "index": next_index,
                "file": "",
                "sheet_file": sheet_file,
                "crop_x": crop.x,
                "crop_y": crop.y,
                "crop_w": crop.w,
                "crop_h": crop.h,
                "source_name": f"{src.name}#{slot:03d}",
                "category": category,
                "source_width": crop.w,
                "source_height": crop.h,
                "render_length": render_length,
                "render_width": render_width,
                "collision_length": collision_length,
                "collision_width": collision_width,
                "speed_factor": speed_factor,
                "spawn_weight": spawn_weight,
                "traffic_eligible": True,
                "art_set": "player_pixel_fleet_2026_08_20",
                "legacy_fallback": False,
            })
            next_index += 1

    # The user's instruction is replacement-by-type. Passenger categories are
    # explicitly replaced by this fleet; any other category is retained only
    # because the submitted sheets do not provide that vehicle type.
    effective_replaced = set(replaced_categories) | new_categories
    for old in load_legacy():
        category = str(old.get("category", "")).strip().lower()
        if category in effective_replaced:
            continue
        row: dict[str, object] = dict(old)
        row["index"] = next_index
        row.update({
            "sheet_file": "",
            "crop_x": "",
            "crop_y": "",
            "crop_w": "",
            "crop_h": "",
            "art_set": "legacy_unmatched_vehicle_type",
            "legacy_fallback": True,
        })
        rows.append(row)
        next_index += 1
    return rows


def write_manifest(rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "index", "file", "sheet_file", "crop_x", "crop_y", "crop_w", "crop_h",
        "source_name", "category", "source_width", "source_height", "render_length", "render_width",
        "collision_length", "collision_width", "speed_factor", "spawn_weight", "traffic_eligible",
        "art_set", "legacy_fallback",
    ]
    with PLAYER_MANIFEST.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("sheets", nargs="+", type=Path, help="Player-approved PNG/JPEG sprite sheets")
    parser.add_argument(
        "--replace-category", action="append", default=[],
        help="Additional legacy category represented by the new sheets (repeatable)",
    )
    args = parser.parse_args()
    inputs = [p.resolve() for p in args.sheets]
    for path in inputs:
        if not path.is_file():
            raise SystemExit(f"Missing sheet: {path}")
    replaced = set(DEFAULT_REPLACED_CATEGORIES) | {str(v).strip().lower() for v in args.replace_category if str(v).strip()}
    rows = build_manifest(inputs, replaced)
    write_manifest(rows)
    new_count = sum(1 for row in rows if not bool(row.get("legacy_fallback")))
    fallback_categories = sorted({str(row.get("category")) for row in rows if bool(row.get("legacy_fallback"))})
    print(f"Imported {new_count} player-approved cars from {len(inputs)} sheets")
    print(f"Legacy art retained only for unmatched types: {', '.join(fallback_categories) or 'none'}")
    print(PLAYER_MANIFEST.relative_to(ROOT))


if __name__ == "__main__":
    main()
