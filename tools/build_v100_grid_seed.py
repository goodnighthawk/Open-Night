#!/usr/bin/env python3
"""Compatibility validator for the committed v1.0 playable grid map.

The old implementation generated a sparse throw-away seed into ground_grid.json.
That behavior is intentionally retired: the JSON file itself is now the authored
playable map and this command only validates it for older workflows/launchers that
still invoke the historical script name.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grid_runtime import GRID_MAP_PATH, load_ground_grid


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
    if len(world.objects) < 150:
        raise SystemExit(f"playable map has too few authored detail objects: {len(world.objects)}")
    spawn = world.choose_spawn("ground", 18.0)
    print(
        "V100_GRID_MAP_OK",
        f"cells={world.width}x{world.height}",
        f"building_cells={building_cells}",
        f"objects={len(world.objects)}",
        f"spawn={spawn}",
        f"map={GRID_MAP_PATH}",
    )


if __name__ == "__main__":
    main()
