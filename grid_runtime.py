from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from grid_world import GridWorld, TileCatalog

ROOT = Path(__file__).resolve().parent
GRID_MAP_PATH = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor" / "grid_v100" / "ground_grid.json"
GRID_EXTERNAL_OBJECTS_PATH = GRID_MAP_PATH.with_name("ground_external_objects.json")
GRID_GENERATED_OBJECTS_PATH = GRID_MAP_PATH.with_name("ground_generated_objects.json")
GRID_ROOF_PATH = GRID_MAP_PATH.with_name("roof_grid.generated.json")
GRID_CATALOG_PATH = ROOT / "assets" / "grid_v100" / "tile_catalog.json"
GRID_MAP_ID = "map_001_gwb_corridor"


def _merge_objects(data: dict, path: Path) -> int:
    if not path.is_file():
        return 0
    extra = json.loads(path.read_text(encoding="utf-8"))
    extra_objects = list(extra.get("objects", []))
    data.setdefault("objects", []).extend(extra_objects)
    return len(extra_objects)


@lru_cache(maxsize=1)
def load_ground_grid() -> GridWorld:
    data = json.loads(GRID_MAP_PATH.read_text(encoding="utf-8"))
    external_count = _merge_objects(data, GRID_EXTERNAL_OBJECTS_PATH)
    generated_count = _merge_objects(data, GRID_GENERATED_OBJECTS_PATH)
    data["external_ground_roof_composite"] = bool(external_count)
    data["external_composite_object_count"] = external_count
    data["generated_ground_object_count"] = generated_count
    data["generation_scope"] = ["ground", "roof"]
    data.setdefault("runtime", {})["external_roofs_visible_on_ground"] = bool(external_count)
    return GridWorld(data, TileCatalog.load(GRID_CATALOG_PATH))


@lru_cache(maxsize=1)
def load_roof_grid() -> GridWorld:
    if not GRID_ROOF_PATH.is_file():
        raise FileNotFoundError(
            f"Roof layer has not been generated yet: {GRID_ROOF_PATH}. "
            "Run tools/generate_v100_ground_roof_layers.py first."
        )
    data = json.loads(GRID_ROOF_PATH.read_text(encoding="utf-8"))
    return GridWorld(data, TileCatalog.load(GRID_CATALOG_PATH))


def ground_grid_enabled(map_config: dict[str, Any] | None = None) -> bool:
    if not GRID_MAP_PATH.is_file() or not GRID_CATALOG_PATH.is_file():
        return False
    if map_config is None:
        return True
    map_id = str(map_config.get("id", ""))
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
        "grid_source_pack": str(world.data.get("source_pack", "city_block")),
        "generated_layers": ["ground", "roof"],
        "blank_layers": ["underground", "first_floor", "second_floor", "hell", "clouds", "hud_space"],
        "legacy_surface_entities": bool(world.data.get("runtime", {}).get("legacy_surface_entities", False)),
        "external_ground_roof_composite": bool(world.data.get("external_ground_roof_composite", False)),
        "external_composite_object_count": int(world.data.get("external_composite_object_count", 0)),
        "generated_ground_object_count": int(world.data.get("generated_ground_object_count", 0)),
    }
