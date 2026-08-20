#!/usr/bin/env python3
"""Structural QA for v1.0 multilayer art overlays."""
from __future__ import annotations
import csv
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "mapfiles/data/map_001_gwb_corridor"
OUT = ROOT / "assets/environment/approved/map_001_gwb_corridor/v100_layers"
MANIFEST = ROOT / "config/art_overlay_layers.csv"
TILE = 1024


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    cfg = {r["key"]: r["value"] for r in read_csv(MAP / "map.csv")}
    layers = read_csv(MANIFEST)
    assert [r["layer_id"] for r in layers] == ["hell","underground","ground","first_floor","second_floor","roof","clouds","hud_space"]
    cols = (int(cfg["world_w"]) + TILE - 1) // TILE
    rows = (int(cfg["world_h"]) + TILE - 1) // TILE
    expected = cols * rows
    failures = []
    for row in layers:
        layer = row["layer_id"]
        for mode in ("day", "night"):
            folder = OUT / layer / mode
            tiles = sorted(folder.glob("tile_*.png")) if folder.exists() else []
            if len(tiles) != expected:
                failures.append(f"{layer}/{mode}: expected {expected} tiles, got {len(tiles)}")
                continue
            for p in tiles:
                with Image.open(p) as im:
                    if im.size != (TILE, TILE) or im.mode != "RGBA":
                        failures.append(f"{p}: expected RGBA {TILE}x{TILE}, got {im.mode} {im.size}")
    # Functional contract checks: art sources required by the builder must exist.
    for name in ("roads.csv", "road_points.csv", "buildings.csv", "building_layers.csv"):
        if not (MAP / name).exists():
            failures.append(f"missing authoritative semantic source: {name}")
    if failures:
        raise SystemExit("V100_ART_OVERLAY_AUDIT_FAIL\n" + "\n".join(failures[:50]))
    print(f"V100_ART_OVERLAY_AUDIT_OK layers={len(layers)} variants=2 tiles_per_variant={expected}")


if __name__ == "__main__":
    main()
