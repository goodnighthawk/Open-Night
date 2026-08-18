from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from grid_world import GridWorld, TileCatalog

ROOT = Path(__file__).resolve().parent
GRID_MAP_PATH = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor" / "grid_v100" / "ground_grid.json"
GRID_EXTERNAL_OBJECTS_PATH = GRID_MAP_PATH.with_name("ground_external_objects.json")
GRID_CATALOG_PATH = ROOT / "assets" / "grid_v100" / "tile_catalog.json"
GRID_MAP_ID = "map_001_gwb_corridor"


@lru_cache(maxsize=1)
def load_ground_grid() -> GridWorld:
    data = json.loads(GRID_MAP_PATH.read_text(encoding="utf-8"))
    if GRID_EXTERNAL_OBJECTS_PATH.is_file():
        extra = json.loads(GRID_EXTERNAL_OBJECTS_PATH.read_text(encoding="utf-8"))
        extra_objects = list(extra.get("objects", []))
        data.setdefault("objects", []).extend(extra_objects)
        data["external_ground_roof_composite"] = bool(extra_objects)
        data["external_composite_object_count"] = len(extra_objects)
        data.setdefault("runtime", {})["external_roofs_visible_on_ground"] = bool(extra_objects)
    return GridWorld(data, TileCatalog.load(GRID_CATALOG_PATH))


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
        "external_ground_roof_composite": bool(world.data.get("external_ground_roof_composite", False)),
        "external_composite_object_count": int(world.data.get("external_composite_object_count", 0)),
    }
