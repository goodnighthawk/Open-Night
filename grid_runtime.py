from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from grid_world import GridWorld

ROOT = Path(__file__).resolve().parent
GRID_MAP_PATH = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor" / "grid_v100" / "ground_grid.json"
GRID_CATALOG_PATH = ROOT / "assets" / "grid_v100" / "tile_catalog.json"
GRID_MAP_ID = "map_001_gwb_corridor"


@lru_cache(maxsize=1)
def load_ground_grid() -> GridWorld:
    return GridWorld.load(GRID_MAP_PATH, GRID_CATALOG_PATH)


def ground_grid_enabled(map_config: dict[str, Any] | None = None) -> bool:
    if not GRID_MAP_PATH.is_file() or not GRID_CATALOG_PATH.is_file():
        return False
    if map_config is None:
        return True
    map_id = str(map_config.get("id", ""))
    # The project historically used both the long folder id and compact map id;
    # map 001 is the only playable v1.0 map during the migration.
    return map_id in {GRID_MAP_ID, "001", "map_001", "gwb_corridor"} or "gwb" in map_id.lower()


def grid_network_metadata(map_config: dict[str, Any]) -> dict[str, Any]:
    if not ground_grid_enabled(map_config):
        return {}
    world = load_ground_grid()
    return {
        "grid_runtime": True,
        "grid_format": str(world.data.get("format", "open-night-grid-v1")),
        "grid_cell_px": world.cell_px,
        "grid_width": world.width,
        "grid_height": world.height,
        "world_w": world.world_w,
        "world_h": world.world_h,
        "grid_source_pack": str(world.data.get("source_pack", "city_block.zip")),
        "legacy_surface_entities": bool(world.data.get("runtime", {}).get("legacy_surface_entities", False)),
    }
