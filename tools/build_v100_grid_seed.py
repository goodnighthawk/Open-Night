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

    density = [obj for obj in world.objects if obj.get("composition_pass") == "ground_density_v2"]
    road_wear = [obj for obj in density if obj.get("density_kind") == "road_wear"]
    curb_details = [obj for obj in density if obj.get("density_kind") == "curb_detail"]
    awnings = [obj for obj in density if obj.get("density_kind") == "street_edge_awning"]
    if (len(road_wear), len(curb_details), len(awnings)) != (36, 24, 18):
        raise SystemExit(
            "Ground density v2 count mismatch: "
            f"road_wear={len(road_wear)} curb_detail={len(curb_details)} awnings={len(awnings)}"
        )
    if any(world.tile_id("ground", int(obj["gx"]), int(obj["gy"])) != "road_fill" for obj in road_wear):
        raise SystemExit("Ground density v2 road wear escaped road collision cells")
    valid_curbs = {"curb_left", "curb_right", "curb_top", "curb_bottom"}
    if any(world.tile_id("ground", int(obj["gx"]), int(obj["gy"])) not in valid_curbs for obj in curb_details):
        raise SystemExit("Ground density v2 curb detail escaped curb semantics")
    for obj in awnings:
        gx, gy = int(obj["gx"]), int(obj["gy"])
        if not world.tile_id("ground", gx, gy).startswith("bld_"):
            raise SystemExit("Ground density v2 awning escaped its building frontage")
        if gy + 1 >= world.height or not world.catalog[world.tile_id("ground", gx, gy + 1)].walkable:
            raise SystemExit("Ground density v2 awning has no walkable street frontage")
    awning_assets = {str(obj["asset"]) for obj in awnings}
    if len(awning_assets) != 4:
        raise SystemExit(f"Ground density v2 did not use all four awning variants: {sorted(awning_assets)}")

    lamps = [obj for obj in world.objects if obj.get("composition_pass") == "street_lighting_v1"]
    if len(lamps) != 48:
        raise SystemExit(f"street lighting v1 expected 48 eligible curb segments, got {len(lamps)}")
    if len({str(obj.get("lighting_id")) for obj in lamps}) != len(lamps):
        raise SystemExit("street lighting v1 fixture/light authority IDs are not unique")
    expected = {
        "curb_top": ("north", 0, 93, 48),
        "curb_right": ("east", 90, 79, 93),
        "curb_bottom": ("south", 180, 34, 79),
        "curb_left": ("west", 270, 48, 34),
    }
    reserved = {
        (int(obj["gx"]), int(obj["gy"]))
        for obj in density if obj.get("density_kind") == "curb_detail"
    }
    for obj in lamps:
        gx, gy = int(obj["gx"]), int(obj["gy"])
        tile_id = world.tile_id("ground", gx, gy)
        if tile_id not in expected or world.catalog[tile_id].collision != "sidewalk":
            raise SystemExit(f"street lamp escaped sidewalk curb semantics at {(gx, gy)}: {tile_id}")
        direction, rotation, light_x, light_y = expected[tile_id]
        actual = (
            obj.get("road_direction"), int(obj.get("rotation", -1)),
            int(obj.get("light_offset_x_px", -1)), int(obj.get("light_offset_y_px", -1)),
        )
        if actual != (direction, rotation, light_x, light_y):
            raise SystemExit(f"street lamp fixture/emitter transform mismatch at {(gx, gy)}: {actual}")
        if not obj.get("emits_light") or obj.get("asset") != "street_lamp_10_night":
            raise SystemExit(f"street lamp is missing its same-record emitter at {(gx, gy)}")
        if (gx, gy) in reserved:
            raise SystemExit(f"street lamp overlaps a curb detail at {(gx, gy)}")
    if {obj.get("road_direction") for obj in lamps} != {"north", "east", "south", "west"}:
        raise SystemExit("street lighting v1 does not cover all four road orientations")

    silhouette = [obj for obj in world.objects if obj.get("composition_pass") == "building_silhouette_v1"]
    facade_breaks = [obj for obj in silhouette if obj.get("silhouette_kind") == "facade_break"]
    roof_masses = [obj for obj in silhouette if obj.get("silhouette_kind") == "roof_edge_mass"]
    if (len(facade_breaks), len(roof_masses)) != (7, 25):
        raise SystemExit(
            f"building silhouette v1 count mismatch: facade={len(facade_breaks)} roof={len(roof_masses)}"
        )
    rect_by_id = {str(building["building_id"]): list(map(int, building["rect"])) for building in buildings}
    if {str(obj.get("building_id")) for obj in roof_masses} != set(rect_by_id):
        raise SystemExit("building silhouette v1 does not cover every Roof footprint exactly once")
    roof_assets = {str(obj.get("asset")) for obj in roof_masses}
    if len(roof_assets) != 4:
        raise SystemExit(f"building silhouette v1 did not exercise four Roof masses: {sorted(roof_assets)}")
    for obj in silhouette:
        building_id = str(obj.get("building_id"))
        gx, gy = int(obj["gx"]), int(obj["gy"])
        x0, y0, x1, y1 = rect_by_id[building_id]
        if not (x0 <= gx <= x1 and y0 <= gy <= y1):
            raise SystemExit(f"building silhouette escaped footprint {building_id} at {(gx, gy)}")
        if not world.tile_id("ground", gx, gy).startswith("bld_"):
            raise SystemExit(f"building silhouette lost building-cell authority at {(gx, gy)}")
        if not obj.get("decorative_only"):
            raise SystemExit(f"building silhouette is not explicitly collision-neutral: {building_id}")
        if any(key in obj for key in ("collision", "future_transition", "emits_light")):
            raise SystemExit(f"building silhouette improperly carries gameplay authority: {building_id}")
    edge_vectors = {"north": (0, -1), "east": (1, 0), "south": (0, 1), "west": (-1, 0)}
    for obj in facade_breaks:
        gx, gy = int(obj["gx"]), int(obj["gy"])
        dx, dy = edge_vectors[str(obj["edge"])]
        outside = world.tile_id("ground", gx + dx, gy + dy)
        if not world.catalog[outside].walkable:
            raise SystemExit(f"facade break has no walkable frontage at {(gx, gy)}")
    if any(max(int(obj["width_px"]), int(obj["height_px"])) > 200 for obj in roof_masses):
        raise SystemExit("Roof edge mass exceeds one-cell containment budget")

    spawn = world.choose_spawn("ground", 18.0)
    print(
        "V100_GRID_MAP_OK",
        f"cells={world.width}x{world.height}",
        f"building_cells={building_cells}",
        f"modular_buildings={len(buildings)}",
        f"objects={len(world.objects)}",
        f"density_v2={len(road_wear)}road+{len(curb_details)}curb+{len(awnings)}awnings",
        f"street_lighting_v1={len(lamps)}same-record-lamps",
        f"silhouette_v1={len(facade_breaks)}facade+{len(roof_masses)}roof-edge",
        "orientation=filename_semantics_no_rotation",
        f"spawn={spawn}",
        f"map={GRID_MAP_PATH}",
    )


if __name__ == "__main__":
    main()
