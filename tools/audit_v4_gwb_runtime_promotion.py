#!/usr/bin/env python3
"""Release gate for promoting the approved GWB workbench into v4.0 gameplay."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

import common
from grid_renderer import GridRenderer
from grid_runtime import load_ground_grid, load_roof_grid
from versioning import GAME_VERSION


MAP_ID = "map_001_gwb_corridor"
MAP_DIR = ROOT / "mapfiles" / "data" / MAP_ID
PROOF = ROOT / "artifacts" / "map_workbench" / "gwb_v4_playable_runtime.png"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    require(GAME_VERSION == "4.0", f"runtime version is {GAME_VERSION}, expected 4.0")
    require((ROOT / "VERSION.txt").read_text(encoding="utf-8").strip() == "4.0", "VERSION.txt is not 4.0")
    require(common.DEFAULT_MAP_ID == MAP_ID, "GWB corridor is not the default map")
    map_dirs = sorted(path.name for path in (ROOT / "mapfiles" / "data").iterdir() if path.is_dir())
    require(map_dirs == [MAP_ID], f"obsolete selectable map directories remain: {map_dirs}")
    require(set(common.MAPS) == {MAP_ID}, f"normal map roster is not singular: {set(common.MAPS)}")

    load_ground_grid.cache_clear()
    load_roof_grid.cache_clear()
    ground = load_ground_grid()
    roof = load_roof_grid()
    require((ground.width, ground.height, ground.cell_px) == (128, 80, 128), "promoted runtime grid geometry changed")
    require((ground.world_w, ground.world_h) == (16384, 10240), "promoted runtime world extent changed")
    require(bool((ground.data.get("runtime") or {}).get("workbench_layout_authority")), "old runtime synthesis is still authoritative")
    require(ground.layers["ground"] == roof.layers["ground"], "Ground parity differs between runtime layer files")
    require(ground.layers["roof"] == roof.layers["roof"], "Roof parity differs between runtime layer files")

    buildings = list((ground.data.get("building_synthesis") or {}).get("buildings") or [])
    require(len(buildings) == 95, f"expected 95 approved buildings, got {len(buildings)}")
    building_cells = {
        (int(cell[0]), int(cell[1]))
        for building in buildings
        for cell in building.get("footprint_cells", [])
    }
    roof_cells = {
        (gx, gy)
        for gy, row in enumerate(ground.layers["roof"])
        for gx, tile_id in enumerate(row)
        if tile_id != "void"
    }
    require(building_cells == roof_cells, "roof walkability does not exactly match building footprints")
    require(all(ground.layers["ground"][gy][gx].startswith("bld_") for gx, gy in building_cells),
            "ground building collision does not match a generated footprint")
    require(all(ground.layers["roof"][gy][gx].startswith("bld_") for gx, gy in roof_cells),
            "roof registration contains a non-building tile")
    shapes = {str(building.get("shape")) for building in buildings}
    require({"rectangle", "courtyard"} <= shapes and len({shape for shape in shapes if shape.startswith("notch_")}) >= 3,
            "approved rectangular, recessed/L-shaped, and courtyard morphology is not represented")

    building_catalog = json.loads((ROOT / "assets" / "grid_v100" / "generated_building_tiles.json").read_text(encoding="utf-8"))["tiles"]
    require(len(building_catalog) == 65, f"modular building catalog has {len(building_catalog)} tiles")
    require(all(ground.catalog[tile_id].image.startswith("assets/generated_v4_buildings/") for tile_id in building_catalog),
            "a modular building tile escaped the approved catalog override")

    signals = list(ground.data.get("traffic_signals") or [])
    require(len(signals) == 382, f"expected 382 directional signals, got {len(signals)}")
    require(all(signal.get("visual_facing") == "south" and int(signal.get("rotation", -1)) == 0 for signal in signals),
            "traffic-signal art is not consistently south-facing")
    require({int(signal.get("semantic_rotation", -1)) for signal in signals} == {0, 90, 180, 270},
            "traffic controller approaches lost their independent direction data")

    perspective_objects = [item for item in ground.objects if not item.get("geometry_rotation")]
    require(perspective_objects, "promoted runtime has no perspective-bearing objects")
    require(all(item.get("visual_facing") == "south" and int(item.get("rotation", -1)) == 0
                for item in perspective_objects), "doors, trees, or street entities are not consistently south-facing")
    interactions = [item for item in ground.objects if item.get("interaction_kind")]
    require(interactions and all(float(item.get("collision_radius_px", -1)) == 0 for item in interactions),
            "interaction art gained gameplay collision")
    require(all(float(item.get("interaction_radius_px", 0)) > 0 for item in interactions),
            "an interaction is missing its independent activation zone")
    player_doors = [item for item in interactions if item.get("interaction_kind") == "player_house_door"]
    buzzers = [item for item in interactions if item.get("interaction_kind") == "entrance_buzzer"]
    require(len(player_doors) == 32 and len(buzzers) == 32, "player entrances and buzzers are not one-to-one")
    require(all(item.get("target_interior_id") for item in player_doors), "a player door has no interior destination")

    require(len(ground.login_spawns) == 8, "safe outdoor recovery spawn pool changed")
    require(all(ground.circle_walkable("ground", float(x), float(y), 18.0) for x, y in ground.login_spawns),
            "a recovery spawn is blocked")
    require(all(ground.collision_at("ground", float(x), float(y)) != "road" for x, y in ground.login_spawns),
            "a recovery spawn is in traffic")

    water_cells = [(gx, gy) for gy, row in enumerate(ground.layers["ground"])
                   for gx, tile_id in enumerate(row) if tile_id.startswith("water_")]
    require(water_cells, "Hudson water surface is missing")
    wx, wy = ground.cell_center(*water_cells[len(water_cells) // 2])
    require(ground.collision_at("ground", wx, wy) == "wade", "pedestrian water-wading collision changed")
    require(not ground.vehicle_drivable_at(wx, wy), "vehicles can enter river water")

    # Streets must meet the appropriate map edge; the bridge must span both shores.
    road = ground.layers["ground"]
    require(any(tile.startswith("road_") for tile in road[0]), "northbound streets stop before the north edge")
    require(any(tile.startswith("road_") for tile in road[-1]), "southbound streets stop before the south edge")
    require(any(row[0].startswith("road_") for row in road), "westbound streets stop before the west edge")
    require(any(row[-1].startswith("road_") for row in road), "eastbound streets stop before the east edge")
    bridge_row = int(3560 // ground.cell_px)
    require(all(road[bridge_row][gx].startswith("road_") for gx in range(int(6100 // 128), int(10250 // 128) + 1)),
            "GWB road surface does not connect both shores")

    pygame.init()
    pygame.display.set_mode((1, 1))
    PROOF.parent.mkdir(parents=True, exist_ok=True)
    surface = pygame.Surface((2560, 1600))
    tile_px, _ox, _oy = GridRenderer(ground).draw_overview(surface, "ground")
    require(tile_px == 20, "full-map proof is not a pixel-aligned runtime render")
    pygame.image.save(surface, str(PROOF))
    print(
        "V4_GWB_RUNTIME_PROMOTION_OK "
        f"map={MAP_ID} grid=128x80@128 world=16384x10240 buildings={len(buildings)} "
        f"objects={len(ground.objects)} signals={len(signals)} recovery_spawns={len(ground.login_spawns)} "
        "roof_registration=exact visual_facing=south selectable_maps=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
