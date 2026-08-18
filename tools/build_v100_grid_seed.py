#!/usr/bin/env python3
"""Compatibility validator for the v1.0 playable deterministic grid map.

The historical sparse seed generator is retired. The command now validates the
Ground map produced by the filename-driven modular building synthesizer.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grid_runtime import GRID_MAP_PATH, load_ground_grid


def expected_rect_tile(theme: str, x: int, y: int, rect: list[int]) -> str:
    x0, y0, x1, y1 = map(int, rect)
    if x0 == x1 or y0 == y1:
        role = "fill"
    elif y == y0:
        role = "top_left_outer" if x == x0 else "top_right_outer" if x == x1 else "top_center"
    elif y == y1:
        role = "bottom_left_outer" if x == x0 else "bottom_right_outer" if x == x1 else "bottom_center"
    elif x == x0:
        role = "left"
    elif x == x1:
        role = "right"
    else:
        role = "fill"
    return f"bld_{theme}_{role}"


def main() -> None:
    world = load_ground_grid()
    if world.data.get("authority") != "grid":
        raise SystemExit("ground_grid.json is not grid-authoritative")
    if world.data.get("source_pack") != "city_block.zip":
        raise SystemExit("ground_grid.json does not bind city_block.zip")

    building_cells = sum(
        1 for row in world.layers.get("ground", []) for tile_id in row
        if tile_id.startswith("bld_")
    )
    if building_cells < 250:
        raise SystemExit(f"playable map has too few authored building cells: {building_cells}")

    synth = world.data.get("building_synthesis") or {}
    if synth.get("orientation_authority") != "filename_semantics":
        raise SystemExit("Ground buildings are not filename-semantics authoritative")
    if synth.get("random_rotation") is not False:
        raise SystemExit("random building rotation must remain disabled")
    buildings = list(synth.get("buildings") or [])
    if len(buildings) < 20:
        raise SystemExit(f"too few deterministic modular buildings: {len(buildings)}")

    for building in buildings:
        theme = str(building["theme"])
        rect = list(building["rect"])
        x0, y0, x1, y1 = map(int, rect)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                expected = expected_rect_tile(theme, x, y, rect)
                actual = world.tile_id("ground", x, y)
                if actual != expected:
                    raise SystemExit(
                        f"modular seam/orientation mismatch building={building.get('building_id')} "
                        f"cell={(x, y)} expected={expected} actual={actual}"
                    )

    premade_overlays = [
        obj for obj in world.objects
        if str(obj.get("asset", "")).startswith("building_")
    ]
    if premade_overlays:
        raise SystemExit(f"premade building overlays must be disabled: {len(premade_overlays)} found")

    # The old >=150-object count was tied to the rejected premade overlay pass.
    # Keep only a modest density sanity gate for street/roof/transition detail.
    if len(world.objects) < 120:
        raise SystemExit(f"playable map has too few authored detail objects: {len(world.objects)}")

    spawn = world.choose_spawn("ground", 18.0)
    print(
        "V100_GRID_MAP_OK",
        f"cells={world.width}x{world.height}",
        f"building_cells={building_cells}",
        f"modular_buildings={len(buildings)}",
        f"objects={len(world.objects)}",
        "orientation=filename_semantics_no_rotation",
        f"spawn={spawn}",
        f"map={GRID_MAP_PATH}",
    )


if __name__ == "__main__":
    main()
