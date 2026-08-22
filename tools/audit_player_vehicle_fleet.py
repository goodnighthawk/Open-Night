#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CARS = ROOT / "assets" / "cars"
MANIFEST = CARS / "player_vehicle_manifest.csv"
REPLACED_PASSENGER_TYPES = {"sedan", "compact", "sports"}


def fail(message: str) -> None:
    raise SystemExit(f"PLAYER_FLEET_RELEASE_BLOCKER: {message}")


def main() -> None:
    if not MANIFEST.exists():
        fail("player_vehicle_manifest.csv is not present; the five approved player car sheets have not been ingested yet")

    with MANIFEST.open("r", encoding="utf-8-sig", newline="") as f:
        rows = [dict(row) for row in csv.DictReader(f)]
    if not rows:
        fail("player vehicle manifest is empty")

    new_rows = [row for row in rows if str(row.get("legacy_fallback", "")).strip().lower() not in {"1", "true", "yes", "y", "on"}]
    fallback_rows = [row for row in rows if row not in new_rows]
    if len(new_rows) < 12:
        fail(f"only {len(new_rows)} player-approved vehicles detected; expected at least 12")

    fallback_categories = {str(row.get("category", "")).strip().lower() for row in fallback_rows}
    illegal = sorted(REPLACED_PASSENGER_TYPES & fallback_categories)
    if illegal:
        fail(f"old civilian art still survives for replaced categories: {illegal}")

    new_categories = {str(row.get("category", "")).strip().lower() for row in new_rows}
    if not REPLACED_PASSENGER_TYPES <= new_categories:
        fail(f"submitted fleet must cover sedan/compact/sports; detected {sorted(new_categories)}")

    referenced_sheets: set[str] = set()
    for row in new_rows:
        if str(row.get("art_set", "")) != "player_pixel_fleet_2026_08_20":
            fail(f"new vehicle row has unexpected art_set: {row}")
        if str(row.get("file", "")).startswith("approved_fleet_"):
            fail(f"legacy civilian PNG referenced by player row: {row}")
        sheet = str(row.get("sheet_file", "")).strip()
        if not sheet:
            fail(f"player vehicle row has no sheet_file: {row}")
        referenced_sheets.add(sheet)
        try:
            crop = tuple(int(float(row[name])) for name in ("crop_x", "crop_y", "crop_w", "crop_h"))
        except Exception:
            fail(f"invalid crop metadata: {row}")
        if crop[2] <= 0 or crop[3] <= 0:
            fail(f"empty crop metadata: {row}")

    for sheet in referenced_sheets:
        path = CARS / sheet
        if not path.is_file():
            fail(f"referenced player sheet is missing: {sheet}")
        if not path.name.lower().endswith(".b64"):
            fail(f"player sheet should be repository-safe base64 text: {sheet}")

    # Exercise the actual runtime loader so the release cannot pass with a
    # manifest that looks correct but fails to decode/crop in Pygame.
    import pygame
    pygame.init()
    pygame.display.set_mode((1, 1))
    import vehicle_catalog
    import vehicle_art

    source = (ROOT / "vehicle_art.py").read_text(encoding="utf-8")
    if 'meta.get("sheet_file")' not in source or 'pygame.transform.flip(source, False, True)' not in source:
        fail("player sheet nose-down orientation is not normalized before heading rotation")

    vehicle_catalog.reload_vehicle_catalog()
    vehicle_art._base_car.cache_clear()
    vehicle_art._sheet_surface.cache_clear()
    catalog = vehicle_catalog.load_vehicle_catalog()
    if len(catalog) != len(rows):
        fail(f"runtime catalog did not select player manifest: {len(catalog)} != {len(rows)}")
    for index, row in enumerate(catalog):
        if str(row.get("legacy_fallback", "")).strip().lower() in {"1", "true", "yes", "y", "on"}:
            continue
        sprite = vehicle_art._base_car(index, int(float(row.get("render_length", 48))))
        if sprite is None or sprite.get_width() < 8 or sprite.get_height() < 16:
            fail(f"runtime could not decode player vehicle index {index}: {row}")

    print(
        "player pixel fleet audit passed: "
        f"{len(new_rows)} new vehicles, fallback types={sorted(fallback_categories)}, "
        f"sheets={len(referenced_sheets)}"
    )


if __name__ == "__main__":
    main()
