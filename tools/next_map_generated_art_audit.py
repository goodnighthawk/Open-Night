#!/usr/bin/env python3
"""Audit and preview the next-map modular buildings and generated art overrides."""
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

from building_morphology import footprint_connected, footprint_for, role_for_cell
from grid_renderer import GridRenderer
from grid_runtime import load_ground_grid

BUILDING_CATALOG = ROOT / "assets/grid_v100/generated_building_tiles.json"
ART_CATALOG = ROOT / "assets/grid_v100/generated_art_tiles.json"
OUT_DIR = ROOT / "artifacts/next_map_generated_art"
FULL_MAP_OUT = OUT_DIR / "next_map_full_runtime.png"
CLOSEUP_OUT = OUT_DIR / "next_map_courtyard_closeup.png"
ROOF_OUT = OUT_DIR / "next_map_rooftop_closeup.png"
REPORT_OUT = OUT_DIR / "next_map_generated_art_audit.json"
EXPECTED_SHAPES = {"rectangle", "l_corner", "stepped_side", "recessed_edge", "courtyard"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def camera_for(world, center: tuple[float, float], size: tuple[int, int]) -> tuple[float, float]:
    width, height = size
    return (
        max(0.0, min(world.world_w - width, center[0] - width / 2)),
        max(0.0, min(world.world_h - height, center[1] - height / 2)),
    )


def render_previews(world, renderer: GridRenderer, courtyard: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    full = pygame.Surface((1920, 1080)).convert()
    renderer.draw_overview(full, "ground")
    pygame.image.save(full, str(FULL_MAP_OUT))

    x0, y0, x1, y1 = map(int, courtyard["rect"])
    center = world.cell_center((x0 + x1) // 2, (y0 + y1) // 2)
    virtual_size = (2560, 1664)
    camera = camera_for(world, center, virtual_size)

    ground_virtual = pygame.Surface(virtual_size).convert()
    renderer.draw_view(ground_virtual, camera, "ground")
    ground = pygame.transform.smoothscale(ground_virtual, (1600, 1040))
    pygame.image.save(ground, str(CLOSEUP_OUT))

    roof_virtual = pygame.Surface(virtual_size).convert()
    renderer.draw_rooftop_view(roof_virtual, camera)
    roof = pygame.transform.smoothscale(roof_virtual, (1600, 1040))
    pygame.image.save(roof, str(ROOF_OUT))


def main() -> int:
    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        load_ground_grid.cache_clear()
        world = load_ground_grid()
        renderer = GridRenderer(world)
        building_raw = json.loads(BUILDING_CATALOG.read_text(encoding="utf-8"))["tiles"]
        art_raw = json.loads(ART_CATALOG.read_text(encoding="utf-8"))["objects"]

        require(len(building_raw) == 65, f"expected 65 modular building tiles, got {len(building_raw)}")
        loaded_building_tiles = 0
        for tile_id, item in building_raw.items():
            require(tile_id in world.catalog.entries, f"building catalog override missing at runtime: {tile_id}")
            definition = world.catalog[tile_id]
            require(
                definition.image == item["image"] and definition.image.startswith("assets/generated_v4_buildings/"),
                f"legacy building artwork still owns {tile_id}: {definition.image}",
            )
            image = renderer._tile_surface(tile_id)
            require(image.get_size() == (256, 256), f"wrong modular tile size for {tile_id}: {image.get_size()}")
            loaded_building_tiles += 1

        buildings = list(world.data["building_synthesis"]["buildings"])
        shapes = Counter(str(building["shape_variant"]) for building in buildings)
        require(EXPECTED_SHAPES <= set(shapes), f"incomplete footprint grammar: {dict(shapes)}")
        building_ids = [str(building["building_id"]) for building in buildings]
        require(len(building_ids) == len(set(building_ids)), "generated building IDs are not unique")
        require(all(f"{bid}_east" in building_ids for bid in building_ids if not bid.endswith("_east")),
                "east-district housing/building identity pairing was not preserved")

        inner_role_cells = 0
        outer_role_cells = 0
        footprint_cells = 0
        seam_pairs = 0
        for building in buildings:
            rect = tuple(map(int, building["rect"]))
            footprint = footprint_for(rect, building.get("notch"))
            require(footprint_connected(footprint), f"disconnected footprint: {building['building_id']}")
            footprint_cells += len(footprint)
            for gx, gy in footprint:
                expected = f"bld_{building['theme']}_{role_for_cell(gx, gy, footprint)}"
                ground_tile = world.tile_id("ground", gx, gy)
                roof_tile = world.tile_id("roof", gx, gy)
                require(ground_tile == expected, f"wrong modular role at {(gx, gy)}: {ground_tile} != {expected}")
                require(roof_tile == ground_tile, f"roof registration mismatch at {(gx, gy)}")
                inner_role_cells += int("_inner" in ground_tile)
                outer_role_cells += int("_outer" in ground_tile)
                for dx, dy in ((1, 0), (0, 1)):
                    if (gx + dx, gy + dy) not in footprint:
                        continue
                    first = renderer._tile_surface(ground_tile)
                    second = renderer._tile_surface(world.tile_id("ground", gx + dx, gy + dy))
                    if dx:
                        matched = all(first.get_at((255, p)) == second.get_at((0, p)) for p in range(256))
                    else:
                        matched = all(first.get_at((p, 255)) == second.get_at((p, 0)) for p in range(256))
                    require(matched, f"visible modular seam at {(gx, gy)} -> {(gx + dx, gy + dy)}")
                    seam_pairs += 1
            x0, y0, x1, y1 = rect
            for gy in range(y0, y1 + 1):
                for gx in range(x0, x1 + 1):
                    if (gx, gy) not in footprint:
                        require(not world.tile_id("ground", gx, gy).startswith("bld_"),
                                f"removed footprint cell stayed blocked at {(gx, gy)}")
                        require(world.tile_id("roof", gx, gy) == "void",
                                f"roof extends into footprint opening at {(gx, gy)}")
        require(inner_role_cells > 0 and outer_role_cells > 0,
                "irregular buildings did not exercise both inner and outer corner grammar")

        by_asset: dict[str, list[dict]] = {}
        for item in world.objects:
            by_asset.setdefault(str(item["asset"]), []).append(item)
        expected_count = len(buildings)
        for asset in ("entrance_door", "fire_escape_ladder", "roof_access_door"):
            require(len(by_asset.get(asset, [])) == expected_count,
                    f"expected one {asset} per building, got {len(by_asset.get(asset, []))}/{expected_count}")

        for asset in ("entrance_door", "fire_escape_ladder"):
            for item in by_asset[asset]:
                gx, gy = int(item["gx"]), int(item["gy"])
                cx, cy = world.cell_center(gx, gy)
                require(world.walkable_at("ground", cx, cy), f"blocked {asset} approach at {(gx, gy)}")
                require(world.collision_at("ground", cx, cy) != "road", f"{asset} placed in road at {(gx, gy)}")
        for item in by_asset["roof_access_door"]:
            cx, cy = world.cell_center(int(item["gx"]), int(item["gy"]))
            require(world.roof_walkable_at(cx, cy), f"roof hatch left footprint: {item['building_id']}")
        for item in by_asset["fire_escape_ladder"]:
            ground = world.cell_center(int(item["gx"]), int(item["gy"]))
            upward = world.fire_escape_transition(*ground, 0)
            require(upward is not None and upward[0] == 1, f"unusable fire escape: {item['building_id']}")
            require(world.circle_roof_walkable(upward[1], upward[2], 18.0),
                    f"fire escape roof target is not walkable: {item['building_id']}")
            downward = world.fire_escape_transition(upward[1], upward[2], 1)
            require(downward is not None and downward[0] == 0, f"fire escape cannot return: {item['building_id']}")

        generated_street = [item for item in world.objects if str(item.get("art_pass", "")).startswith("v4_generated")]
        require(generated_street, "generated street artwork does not appear in the runtime")
        for item in generated_street:
            definition = world.catalog.object(str(item["asset"]))
            require(definition.image.startswith("assets/generated_v4_art/"),
                    f"street override escaped generated catalog: {definition.image}")
            gx, gy = int(item["gx"]), int(item["gy"])
            require(not world.tile_id("ground", gx, gy).startswith("bld_") and world.tile_id("ground", gx, gy) != "road_fill",
                    f"generated street object blocks road/building at {(gx, gy)}")
            require(float(item.get("collision_radius_px", -1)) == 0 and item.get("decorative_only") is True,
                    f"generated street art gained gameplay collision: {item['asset']}")

        generated_roof = [
            item for item in world.objects
            if world.catalog.object(str(item["asset"])).image.startswith("assets/generated_v4_rooftops/")
        ]
        require(generated_roof, "generated rooftop artwork does not appear in the runtime")
        generated_roof_assets = {str(item["asset"]) for item in generated_roof}
        for item in generated_roof:
            cx, cy = world.cell_center(int(item["gx"]), int(item["gy"]))
            require(world.roof_walkable_at(cx, cy), f"roof artwork left footprint: {item['asset']}")

        for object_id, item in art_raw.items():
            require(object_id in world.catalog.objects, f"generated object override not loaded: {object_id}")
            definition = world.catalog.object(object_id)
            if object_id in {"placeholder_street_door", "placeholder_fire_escape", "placeholder_roof_hatch"}:
                require(definition.image.startswith("assets/generated_v4_transitions/"),
                        f"approved transition override lost: {object_id}")
            else:
                require(definition.image == item["image"], f"generated object override lost: {object_id}")
            renderer._load_image(definition.image)

        courtyard = next(building for building in buildings if building["shape_variant"] == "courtyard" and not str(building["building_id"]).endswith("_east"))
        render_previews(world, renderer, courtyard)
        report = {
            "status": "PASS",
            "release_version_changed": False,
            "modular_building_tiles_loaded": loaded_building_tiles,
            "generated_art_catalog_objects_loaded": len(art_raw),
            "buildings": len(buildings),
            "shape_counts": dict(shapes),
            "footprint_cells": footprint_cells,
            "inner_corner_cells": inner_role_cells,
            "outer_corner_cells": outer_role_cells,
            "exact_shared_edge_pairs": seam_pairs,
            "street_art_instances": len(generated_street),
            "street_art_assets": sorted({str(item["asset"]) for item in generated_street}),
            "rooftop_art_instances": len(generated_roof),
            "rooftop_art_assets": sorted(generated_roof_assets),
            "doors": len(by_asset["entrance_door"]),
            "fire_escapes": len(by_asset["fire_escape_ladder"]),
            "roof_hatches": len(by_asset["roof_access_door"]),
            "roof_registration": "exact_generated_footprint",
            "decorative_collision": "independent_zero_radius",
            "previews": [str(FULL_MAP_OUT), str(CLOSEUP_OUT), str(ROOF_OUT)],
        }
        REPORT_OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            "NEXT_MAP_GENERATED_ART_AUDIT_OK",
            f"tiles={loaded_building_tiles}", f"buildings={len(buildings)}",
            f"shapes={dict(shapes)}", f"inner={inner_role_cells}", f"outer={outer_role_cells}",
            f"seams={seam_pairs}exact",
            f"street={len(generated_street)}", f"roof={len(generated_roof)}",
            f"access={expected_count}doors+{expected_count}fire+{expected_count}hatches",
        )
        return 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
