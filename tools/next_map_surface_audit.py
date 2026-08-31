#!/usr/bin/env python3
"""Verify next-map surface catalogs, collision semantics, parity, and previews."""
from __future__ import annotations

from collections import Counter
import json
import math
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

from grid_renderer import GridRenderer
from grid_runtime import GRID_CATALOG_PATH, load_ground_grid
from grid_world import GridWorld, TileCatalog
from road_morphology import road_components
from surface_autotile import autotile_ids, road_topology_role

CATALOG_PATH = ROOT / "assets/grid_v100/generated_surface_tiles.json"
OUT_DIR = ROOT / "artifacts/next_map_generated_art"
PREVIEW_OUT = OUT_DIR / "next_map_surface_pack_closeup.png"
REPORT_OUT = OUT_DIR / "next_map_surface_audit.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def exact_opposing_edges(surface: pygame.Surface) -> bool:
    width, height = surface.get_size()
    return (
        all(surface.get_at((0, y)) == surface.get_at((width - 1, y)) for y in range(height))
        and all(surface.get_at((x, 0)) == surface.get_at((x, height - 1)) for x in range(width))
    )


def render_surface_preview(world, renderer: GridRenderer) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    frame = pygame.Surface((1920, 1080)).convert()
    frame.fill((11, 15, 19))
    title = pygame.font.Font(None, 42)
    label = pygame.font.Font(None, 25)
    small = pygame.font.Font(None, 20)
    frame.blit(title.render("NEXT MAP SURFACE PACK — RUNTIME ART", True, (225, 232, 234)), (38, 20))

    def tile(tile_id: str, x: int, y: int, size: int = 210) -> None:
        image = renderer._tile_surface(tile_id)
        frame.blit(pygame.transform.smoothscale(image, (size, size)), (x, y))

    def object_art(object_id: str, x: int, y: int, rotation: float = 0.0, size: int = 210) -> None:
        image = renderer._object_surface(object_id, 256, 256, rotation)
        frame.blit(pygame.transform.smoothscale(image, (size, size)), (x, y))

    frame.blit(label.render("SIDEWALK / PLAZA / CURB", True, (102, 194, 205)), (38, 72))
    top_ids = (
        ("pavement_standard_variant_0", "standard"),
        ("pavement_patched_variant_1", "patched utility"),
        ("pavement_plaza_variant_2", "plaza pavers"),
        ("pavement_patch_connector_h", "connector"),
        ("curb_top", "straight curb"),
        ("curb_ramp_top", "tactile ramp"),
    )
    for index, (tile_id, text) in enumerate(top_ids):
        x = 38 + index * 214
        tile(tile_id, x, 103)
        frame.blit(small.render(text, True, (213, 220, 220)), (x + 5, 318))

    frame.blit(label.render("MULTILANE ASPHALT + INDEPENDENT MARKING OVERLAYS", True, (102, 194, 205)), (38, 352))
    road_x, road_y, cell = 38, 386, 210
    for row in range(2):
        for col in range(6):
            tile(f"road_asphalt_variant_{(row * 2 + col) % 4}", road_x + col * cell, road_y + row * cell, cell)
            if row == 0:
                object_art("mark_dashed_white_lane", road_x + col * cell, road_y + row * cell, 90, cell)
            else:
                object_art("mark_double_yellow", road_x + col * cell, road_y + row * cell, 90, cell)
    # One complete crossing column, with two opposing ramps outside the road.
    crossing_x = road_x + 3 * cell
    for row in range(2):
        for stripe in range(4):
            art = renderer._object_surface("mark_zebra_crossing", 44, 176, 90)
            frame.blit(art, (crossing_x + 17, road_y + row * cell + 18 + stripe * 46))
    tile("curb_ramp_bottom", crossing_x, road_y - cell, cell)
    tile("curb_ramp_top", crossing_x, road_y + 2 * cell, cell)
    frame.blit(small.render("zebra + ramps", True, (230, 218, 163)), (crossing_x + 40, road_y + 185))

    shore_x = 1360
    frame.blit(label.render("BEACH / SHORELINE / WATER", True, (102, 194, 205)), (shore_x, 72))
    shore_tiles = (
        ("sand_dry", "dry sand"), ("sand_coarse_urban", "urban riverbank"),
        ("sand_dry_to_damp_h", "dry → damp"), ("shoreline_top", "straight shore"),
        ("water_shallow", "shallow water"), ("water_deep_ripple_1", "deep + ripple"),
        ("shoreline_tl_outer", "outside corner"), ("shoreline_br_inner", "inside corner"),
    )
    for index, (tile_id, text) in enumerate(shore_tiles):
        x = shore_x + (index % 2) * 244
        y = 103 + (index // 2) * 232
        tile(tile_id, x, y, 224)
        frame.blit(small.render(text, True, (219, 224, 220)), (x + 6, y + 202))

    pygame.image.save(frame, str(PREVIEW_OUT))


def main() -> int:
    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        catalog = TileCatalog.load(GRID_CATALOG_PATH)
        load_ground_grid.cache_clear()
        world = load_ground_grid()
        renderer = GridRenderer(world)
        generated_paths = []
        for tile_id, item in raw["tiles"].items():
            require(tile_id in catalog.entries, f"surface tile missing from runtime catalog: {tile_id}")
            definition = catalog[tile_id]
            require(definition.image == item["image"], f"surface tile override lost: {tile_id}")
            image = renderer._load_image(definition.image)
            require(image.get_size() == (256, 256), f"surface tile is not 256px: {tile_id}={image.get_size()}")
            generated_paths.append(definition.image)
        for object_id, item in raw["objects"].items():
            require(object_id in catalog.objects, f"surface object missing from runtime catalog: {object_id}")
            definition = catalog.object(object_id)
            require(definition.image == item["image"], f"surface object override lost: {object_id}")
            image = renderer._load_image(definition.image)
            require(image.get_size() == (256, 256), f"road overlay is not 256px: {object_id}")
            require(image.get_at((0, 0)).a == 0, f"road marking is not a transparent overlay: {object_id}")
            generated_paths.append(definition.image)

        for tile_id in ("pavement_h", "pavement_v", "pavement_small", "pavement_pattern", "road_fill"):
            require(catalog[tile_id].image.startswith("assets/generated_v4_surfaces/"),
                    f"flat city_block surface remains active: {tile_id}")
        for tile_id in (
            "curb_left", "curb_right", "curb_top", "curb_bottom",
            "curb_tl_outer", "curb_tr_outer", "curb_bl_outer", "curb_br_outer",
        ):
            require(catalog[tile_id].image.startswith("assets/generated_v4_surfaces/"),
                    f"city_block curb remains active: {tile_id}")

        seamless_ids = [
            tile_id for tile_id in raw["tiles"]
            if any(token in tile_id for token in (
                "pavement_standard_variant", "pavement_patched_variant", "pavement_plaza_variant",
                "road_asphalt_variant", "sand_dry", "sand_compacted", "sand_damp",
                "sand_coarse", "water_deep_ripple",
            )) and "to_" not in tile_id
        ]
        for tile_id in seamless_ids:
            require(exact_opposing_edges(renderer._load_image(catalog[tile_id].image)),
                    f"opposing edges do not match: {tile_id}")

        collision_counts = Counter(item["collision"] for item in raw["tiles"].values())
        require(all(raw["tiles"][tile_id]["collision"] == "sidewalk" for tile_id in raw["tiles"] if tile_id.startswith("sand_")),
                "sand stopped being pedestrian-walkable")
        require(all(raw["tiles"][tile_id]["collision"] == "wade" for tile_id in raw["tiles"] if tile_id.startswith("water_")),
                "water lost wading collision semantics")
        require(not world.vehicle_drivable_at(*world.cell_center(0, 0)), "non-road surface became vehicle-drivable")

        # Isolate movement semantics in a full-size lightweight world so the
        # GridWorld's production dimension contract remains exercised.
        rows = [["pavement_small" for _ in range(128)] for _ in range(48)]
        rows[10][10] = "water_deep"
        test_data = {"cell_px": 256, "width": 128, "height": 48, "layers": {"ground": rows}, "objects": []}
        water_world = GridWorld(test_data, catalog)
        wx, wy = water_world.cell_center(10, 10)
        require(water_world.walkable_at("ground", wx, wy), "pedestrians cannot enter wading water")
        require(not water_world.vehicle_drivable_at(wx, wy), "vehicles can drive on water")
        moved_x, _ = water_world.move_circle("ground", wx, wy, 100, 0, 18)
        require(math.isclose(moved_x - wx, 55.0, abs_tol=0.01), "wading did not apply the 0.55 speed multiplier")

        # A concave shoreline blob must invoke both diagonal inner-corner and
        # cardinal outer-corner selections.
        shoreline_cells = {(x, y) for y in range(6) for x in range(7)}
        shoreline_cells.difference_update({(3, 2), (3, 3), (6, 0), (6, 1)})
        shoreline_ids = autotile_ids(shoreline_cells, "shoreline", "sand_damp")
        require(any("_inner" in tile_id for tile_id in shoreline_ids.values()), "shoreline autotiler missed inner corners")
        require(any("_outer" in tile_id for tile_id in shoreline_ids.values()), "shoreline autotiler missed outside corners")
        require(all(tile_id in catalog.entries for tile_id in shoreline_ids.values()), "shoreline autotiler produced missing tile IDs")

        topology_sample = {
            (1, 0), (0, 1), (1, 1), (2, 1), (1, 2),  # intersection
            (5, 0), (5, 1), (6, 1), (5, 2),           # T
            (9, 0), (9, 1), (10, 1),                  # turn
            (13, 0), (13, 1), (13, 2),                # straight
        }
        topology_roles = {road_topology_role(x, y, topology_sample) for x, y in topology_sample}
        require(
            "intersection" in topology_roles
            and any(role.startswith("t_missing_") for role in topology_roles)
            and any(role.startswith("turn_") for role in topology_roles)
            and any(role.startswith("straight_") for role in topology_roles),
            f"road overlay planner missed topology families: {sorted(topology_roles)}",
        )

        require(len(road_components(world.layers["ground"])) == 1, "road network lost connectivity")
        access = [item for item in world.objects if item["asset"] in {"entrance_door", "fire_escape_ladder"}]
        require(access and all(
            world.walkable_at("ground", *world.cell_center(int(item["gx"]), int(item["gy"])))
            and world.collision_at("ground", *world.cell_center(int(item["gx"]), int(item["gy"]))) != "road"
            for item in access
        ), "surface pass blocked an entrance or fire escape")
        ramps = sum(tile_id.startswith("curb_ramp_") for row in world.layers["ground"] for tile_id in row)
        crossings = [item for item in world.objects if str(item.get("street_marking", "")).startswith("zebra_")]
        require(ramps > 0 and crossings, "crossings did not receive authored curb ramps")
        require(all(world.tile_id("ground", int(item["gx"]), int(item["gy"])) == "road_fill" for item in crossings),
                "crossing marking escaped road geometry")

        client_source = (ROOT / "client.py").read_text(encoding="utf-8")
        server_source = (ROOT / "server.py").read_text(encoding="utf-8")
        require("load_ground_grid" in client_source and "load_ground_grid" in server_source,
                "desktop/server no longer share the GridWorld loader")
        render_surface_preview(world, renderer)
        report = {
            "status": "PASS", "release_marker_changed": False,
            "tile_size_px": 256, "surface_tiles": len(raw["tiles"]),
            "road_overlay_objects": len(raw["objects"]),
            "loaded_images": len(generated_paths), "seamless_edge_audits": len(seamless_ids),
            "collision_counts": dict(collision_counts), "road_components": 1,
            "crossing_ramps": ramps, "zebra_overlay_instances": len(crossings),
            "wade_speed_multiplier": 0.55, "vehicle_water_drivable": False,
            "desktop_server_loader": "shared grid_runtime.load_ground_grid",
            "preview": str(PREVIEW_OUT),
        }
        REPORT_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            "NEXT_MAP_SURFACE_AUDIT_OK",
            f"tiles={len(raw['tiles'])}", f"overlays={len(raw['objects'])}",
            f"seams={len(seamless_ids)}", f"ramps={ramps}", f"zebras={len(crossings)}",
            "roads=connected", "sand=walkable", "water=wade55", "vehicles=blocked", "parity=shared-loader",
        )
        return 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
