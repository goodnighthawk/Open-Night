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


def _decode_ground(data: dict) -> list[list[str]]:
    explicit = data.get("layers", {}).get("ground")
    if explicit:
        return [list(row) for row in explicit]
    legend = data.get("tile_legend") or {}
    source = (data.get("layers_ascii") or {}).get("ground") or []
    return [[str(legend[ch]) for ch in str(row)] for row in source]


def _fallback_roof_data(ground_data: dict) -> dict:
    """Exact registered fallback used if generated Roof support is absent."""
    ground = _decode_ground(ground_data)
    roof = [[tile_id if tile_id.startswith("bld_") else "void" for tile_id in row] for row in ground]
    return {
        "format": "open-night-grid-v1",
        "authority": "grid",
        "cell_px": ground_data.get("cell_px", 256),
        "width": ground_data.get("width", 64),
        "height": ground_data.get("height", 48),
        "world_w": ground_data.get("world_w", 16384),
        "world_h": ground_data.get("world_h", 12288),
        "source_pack": "city_block",
        "generation_scope": ["ground", "roof"],
        "layers": {"roof": roof},
        "objects": [],
        "login_spawns": [],
        "fallback_exact_ground_registration": True,
    }


def _load_roof_data(ground_data: dict) -> dict:
    if GRID_ROOF_PATH.is_file():
        return json.loads(GRID_ROOF_PATH.read_text(encoding="utf-8"))
    return _fallback_roof_data(ground_data)


def _assert_exact_roof_registration(ground_rows: list[list[str]], roof_rows: list[list[str]]) -> None:
    if len(ground_rows) != len(roof_rows):
        raise ValueError("Roof/Ground row count mismatch")
    for y, ground_row in enumerate(ground_rows):
        if len(ground_row) != len(roof_rows[y]):
            raise ValueError(f"Roof/Ground width mismatch at row {y}")
        for x, ground_tile in enumerate(ground_row):
            roof_tile = roof_rows[y][x]
            is_building = ground_tile.startswith("bld_")
            if is_building and roof_tile != ground_tile:
                raise ValueError(
                    f"Roof registration mismatch at {(x, y)}: ground={ground_tile} roof={roof_tile}"
                )
            if not is_building and roof_tile != "void":
                raise ValueError(
                    f"Roof extends outside Ground building footprint at {(x, y)}: roof={roof_tile}"
                )


@lru_cache(maxsize=1)
def load_ground_grid() -> GridWorld:
    data = json.loads(GRID_MAP_PATH.read_text(encoding="utf-8"))
    generated_ground_count = _merge_objects(data, GRID_GENERATED_OBJECTS_PATH)

    roof_data = _load_roof_data(data)
    ground_rows = _decode_ground(data)
    roof_rows = [list(row) for row in roof_data["layers"]["roof"]]
    _assert_exact_roof_registration(ground_rows, roof_rows)

    # One coordinate system is authoritative for the exterior: Ground is the
    # collision surface; Roof is a visual layer registered cell-for-cell over
    # building footprints and uses the exact same camera transform.
    data["layers"] = {"ground": ground_rows, "roof": roof_rows}
    data.pop("layers_ascii", None)
    roof_objects = list(roof_data.get("objects", []))
    data.setdefault("objects", []).extend(roof_objects)

    data["generation_scope"] = ["ground", "roof"]
    data["external_ground_roof_composite"] = True
    data["external_composite_object_count"] = len(roof_objects)
    data["generated_ground_object_count"] = generated_ground_count
    data["roof_registration"] = "exact_ground_building_footprint"
    runtime = data.setdefault("runtime", {})
    runtime["external_roofs_visible_on_ground"] = True
    runtime["roof_collision_authority"] = "ground"
    return GridWorld(data, TileCatalog.load(GRID_CATALOG_PATH))


@lru_cache(maxsize=1)
def load_roof_grid() -> GridWorld:
    ground_data = json.loads(GRID_MAP_PATH.read_text(encoding="utf-8"))
    roof_data = _load_roof_data(ground_data)
    _assert_exact_roof_registration(_decode_ground(ground_data), roof_data["layers"]["roof"])
    return GridWorld(roof_data, TileCatalog.load(GRID_CATALOG_PATH))


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
        "external_ground_roof_composite": True,
        "roof_registration": "exact_ground_building_footprint",
        "external_composite_object_count": int(world.data.get("external_composite_object_count", 0)),
        "generated_ground_object_count": int(world.data.get("generated_ground_object_count", 0)),
    }
