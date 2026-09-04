#!/usr/bin/env python3
"""Focused data/asset parity gate for the standalone v4 map workbench."""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dev_tools" / "map_generator" / "working_cosmetics" / "approved_v4_layout"
GENERATOR_TOOLS = ROOT / "dev_tools" / "map_generator" / "tools"
sys.path.insert(0, str(GENERATOR_TOOLS))
import build_v4_approved_sprite_layout as layout_builder  # noqa: E402
sys.path.insert(0, str(ROOT))
from map_workbench import crossing_curb_offset_world, pavement_asset_for_block  # noqa: E402


def rows(name: str) -> list[dict[str, str]]:
    with (DATA / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def count(items: list[dict[str, str]], key: str, *values: str) -> int:
    return sum(item.get(key) in values for item in items)


def main() -> None:
    houses = rows("empty_houses.csv")
    slots = rows("sprite_slots.csv")
    streets = rows("streets.csv")
    transport = rows("transport.csv")
    population = rows("population.csv")
    features = rows("street_features.csv")
    access = rows("building_access.csv")
    pavement_blocks = rows("pavement_blocks.csv")
    contract = {row["key"]: row["value"] for row in rows("layout_contract.csv")}

    assert len(houses) == 32
    assert contract["hudson_width"] == "3277"
    assert contract["city_block_world_scale"] == "0.5"
    assert contract["vehicle_width"] == "105"
    assert contract["regular_road_width"] == "420"
    assert contract["gwb_road_width"] == "1050"
    assert contract["regular_lane_count"] == "4"
    assert contract["gwb_lane_count"] == "9"
    assert all(
        layout_builder.ROAD_WIDTHS[road["road_class"]]
        == (layout_builder.GWB_ROAD_WIDTH if road["road_class"] == "bridge" else layout_builder.REGULAR_ROAD_WIDTH)
        for road in streets
    )
    assert count(transport, "kind", "moving_vehicle") == 28
    assert count(transport, "kind", "parked_vehicle") >= 10
    assert count(population, "kind", "pedestrian", "dog_walker") == 108
    assert count(population, "kind", "dog") == 3
    assert count(population, "kind", "supplier") == 10
    assert count(population, "kind", "buyer") == 10
    assert {"street_lamp", "street_tree", "fire_hydrant", "telephone", "crosswalk", "traffic_signal", "traffic_cone", "manhole"} <= {row["kind"] for row in features}
    assert count(access, "kind", "player_house_door") == 32
    assert all(row["buzzer_enabled"] == "true" for row in access if row["kind"] == "player_house_door")
    assert all(row["buzzer_enabled"] == "false" for row in access if row["kind"] != "player_house_door")
    assert count(access, "kind", "public_door") == 30
    assert count(access, "kind", "fire_escape") >= 15
    assert count(access, "kind", "roof_access_door") == 1
    assert count(access, "kind", "elevator_transition") == 1
    assert all(float(row["collision_radius"]) == 0 for row in access)
    assert all(float(row["interaction_radius"]) > 0 for row in access)
    assert all(float(row["buzzer_collision_radius"]) == 0 for row in houses)
    assert all(float(row["buzzer_interaction_radius"]) > 0 for row in houses)
    assert count(slots, "sprite_role", "bridge_tower") == 2
    assert count(slots, "sprite_role", "small_pier") >= 10

    crossings = [row for row in features if row["kind"] == "crosswalk"]
    signals = [row for row in features if row["kind"] == "traffic_signal"]
    assert all(row["asset_id"] == "traffic_signal_dynamic" for row in signals)
    assert all(row["controller"] == row["group"] for row in signals)
    assert all(len(row["cycle_states"].split("|")) == 6 for row in signals)
    crossing_groups: dict[str, set[str]] = defaultdict(set)
    road_by_id = {road["street_id"]: road for road in streets}
    road_widths = {
        "bridge": float(contract["gwb_road_width"]),
        "primary": float(contract["regular_road_width"]),
        "secondary": float(contract["regular_road_width"]),
        "residential": float(contract["regular_road_width"]),
    }
    for crossing in crossings:
        junction, approach = crossing["group"].rsplit(":", 1)
        crossing_groups[junction].add(approach)
        assert float(crossing["length"]) >= 550
        # The authored stripe envelope contains 65 units of legacy overrun on
        # both ends; visible bars and tactile ramps must stop on the true curb.
        assert crossing_curb_offset_world(
            crossing,
            road_by_id,
            road_widths,
            float(contract["regular_road_width"]),
        ) == float(contract["regular_road_width"]) / 2
    assert crossing_groups
    # Pole arms point out from the corner; inward rotations make the two
    # direction-specific assemblies converge into one glitched metal cluster.
    signal_rotation = {"north": "0", "south": "180", "west": "270", "east": "90"}
    rotation_signal = {value: key for key, value in signal_rotation.items()}
    signal_groups: dict[str, set[str]] = defaultdict(set)
    for signal in signals:
        signal_groups[signal["group"]].add(rotation_signal[signal["rotation"]])
    assert crossing_groups.keys() == signal_groups.keys()
    assert all(len(approaches) in {3, 4} for approaches in signal_groups.values())
    crossing_by_group = {row["group"]: row for row in crossings}
    for signal in signals:
        approach = rotation_signal[signal["rotation"]]
        crossing = crossing_by_group.get(f"{signal['group']}:{approach}")
        if crossing is None:
            # Shoreline junctions intentionally suppress the crossing that
            # would lead into sand/water while retaining road-facing signals.
            continue
        axis = "y" if approach in {"north", "south"} else "x"
        assert abs(float(signal[axis]) - float(crossing[axis])) >= 90
    assert Counter(row["group"] for row in signals) == Counter({junction: len(approaches) * 2 for junction, approaches in signal_groups.items()})
    signal_spacing = min(
        math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))
        for index, a in enumerate(signals)
        for b in signals[index + 1:]
        if a["group"] == b["group"]
    )
    assert signal_spacing >= 90, f"directional traffic-signal assemblies overlap: {signal_spacing:.1f}"
    assert all(
        crossing_groups[junction] == ({"west"} if "fl_hudson_terrace" in junction else {"east"} if "ny_riverside" in junction else approaches)
        for junction, approaches in signal_groups.items()
    )

    # Recovered v0.8/v3 city laws: a continuous full-width road network,
    # road-bounded parcels, dense street walls, varied morphology, and exact
    # Ground/Roof footprint registration.
    buildings = houses + [row for row in slots if row["sprite_role"] not in {"small_pier", "bridge_tower", "athletic_field"}]
    assert len(buildings) >= 62
    assert min(float(row["parcel_occupancy"]) for row in buildings) >= 0.60
    assert min(float(row["w"]) for row in buildings) >= 340
    assert min(float(row["h"]) for row in buildings) >= 340
    assert all(row["ground_roof_registration"] == "exact" for row in buildings)
    shapes = {row["shape"] for row in buildings}
    assert "rectangle" in shapes and "courtyard" in shapes
    assert any(shape.startswith("notch_") for shape in shapes)
    assert all(
        not layout_builder._building_overlaps_road(building, road)
        for building in buildings
        for road in streets
    )
    assert pavement_blocks
    assert all(pavement_asset_for_block(block).startswith("pavement_") for block in pavement_blocks)
    assert all(float(block["x"]) + float(block["w"]) <= layout_builder.RIVER_X0 or float(block["x"]) >= layout_builder.RIVER_X1 for block in pavement_blocks)
    athletic_field = next(row for row in slots if row["sprite_role"] == "athletic_field")
    fx, fy, fw, fh = (float(athletic_field[key]) for key in ("x", "y", "w", "h"))
    assert any(
        float(block["x"]) <= fx
        and float(block["y"]) <= fy
        and float(block["x"]) + float(block["w"]) >= fx + fw
        and float(block["y"]) + float(block["h"]) >= fy + fh
        for block in pavement_blocks
    ), "athletic field escaped its pavement block"
    assert not any(layout_builder._overlaps_reserved_field(building) for building in buildings)
    assert all(not layout_builder._building_overlaps_road(athletic_field, road) for road in streets)
    for road in streets:
        if road["orientation"] == "vertical":
            assert float(road["y1"]) == 0 and float(road["y2"]) == layout_builder.WORLD_H
        elif road["side"] == "west":
            assert float(road["x1"]) == 0 and float(road["x2"]) == 6100
        elif road["side"] == "east":
            assert float(road["x1"]) == 10250 and float(road["x2"]) == layout_builder.WORLD_W
        else:
            assert road["road_class"] == "bridge"
            assert float(road["x1"]) == 6100 and float(road["x2"]) == 10250

    required_assets = (
        "assets/source_packs/city_block/road_and_pavement_tileset/road_fill.png",
        "assets/source_packs/city_block/road_and_pavement_tileset/curb_bottom_center.png",
        "assets/source_packs/city_block/road_and_pavement_tileset/curb_top_center.png",
        "assets/source_packs/city_block/road_and_pavement_tileset/curb_left_edge.png",
        "assets/source_packs/city_block/road_and_pavement_tileset/curb_right_edge.png",
        "assets/source_packs/city_block/small_tile_pavement_tiles/center.png",
        "assets/source_packs/free_assets/Sand/Sand_04/Sand_04_basecolor.png",
        "assets/source_packs/city_block/street_decorations/traffic_cone.png",
        "assets/street_props/traffic_signal.png",
        "assets/street_props/street_tree.png",
        "cosmetic_packs/nyc_gta2_callback/sprites/lan_gwb_truss_02_night.png",
        "cosmetic_packs/nyc_gta2_callback/sprites/lan_gwb_tower_01_night.png",
        "assets/grid_v100/generated_building_tiles.json",
        "assets/grid_v100/generated_art_tiles.json",
        "assets/grid_v100/generated_surface_tiles.json",
        "assets/grid_v100/generated_transition_objects.json",
    )
    assert all((ROOT / name).is_file() for name in required_assets)

    building_catalog = json.loads((ROOT / "assets/grid_v100/generated_building_tiles.json").read_text(encoding="utf-8"))["tiles"]
    surface_catalog = json.loads((ROOT / "assets/grid_v100/generated_surface_tiles.json").read_text(encoding="utf-8"))
    transition_catalog = json.loads((ROOT / "assets/grid_v100/generated_transition_objects.json").read_text(encoding="utf-8"))["objects"]
    assert len(building_catalog) == 65
    assert {item["image"] for item in building_catalog.values()} == {
        f"assets/generated_v4_buildings/{theme}/{role}.png"
        for theme in ("blue", "dark_green", "green", "red", "yellow")
        for role in (
            "fill", "top_center", "bottom_center", "left", "right",
            "top_left_outer", "top_right_outer", "bottom_left_outer", "bottom_right_outer",
            "top_left_inner", "top_right_inner", "bottom_left_inner", "bottom_right_inner",
        )
    }
    for tile_id, definition in building_catalog.items():
        image = Image.open(ROOT / definition["image"]).convert("RGBA")
        assert image.size == (256, 256)
        if not tile_id.endswith("_fill"):
            assert image.getchannel("A").getextrema()[0] == 0, f"opaque exterior box: {tile_id}"
    assert {f"water_deep_ripple_{index}" for index in range(3)} <= surface_catalog["tiles"].keys()
    assert {"mark_dashed_white_lane", "mark_zebra_crossing"} <= surface_catalog["objects"].keys()
    crossing_art = Image.open(ROOT / surface_catalog["objects"]["mark_zebra_crossing"]["image"]).convert("RGBA")
    crossing_alpha = crossing_art.getchannel("A")
    assert crossing_alpha.getextrema()[1] <= 190, "zebra marking reverted to an opaque white slab"
    assert sum(crossing_alpha.histogram()[1:]) < 256 * 256 // 2

    pavement = Image.open(ROOT / surface_catalog["tiles"]["pavement_standard_variant_0"]["image"]).convert("RGB")
    asphalt = Image.open(ROOT / surface_catalog["tiles"]["road_asphalt_variant_0"]["image"]).convert("RGB")
    corner_samples = {
        "tl": ((90, 90), (224, 224), (124, 124)),
        "tr": ((166, 90), (32, 224), (132, 124)),
        "bl": ((90, 166), (224, 32), (124, 132)),
        "br": ((166, 166), (32, 32), (132, 132)),
    }
    for corner, (pavement_point, asphalt_point, rounded_cutout) in corner_samples.items():
        image = Image.open(ROOT / surface_catalog["tiles"][f"curb_{corner}_outer"]["image"]).convert("RGB")
        assert image.getpixel(pavement_point) == pavement.getpixel(pavement_point)
        assert image.getpixel(asphalt_point) == asphalt.getpixel(asphalt_point)
        assert image.getpixel(rounded_cutout) == asphalt.getpixel(rounded_cutout), f"curb_{corner}_outer is not quarter-round"
    assert {
        "entrance_door", "entrance_buzzer", "roof_access_door", "elevator_transition",
        "fire_escape_ladder", "traffic_red_not_clear", "traffic_yellow_not_clear",
        "traffic_green_not_clear", "traffic_red_clear", "traffic_yellow_clear", "traffic_green_clear",
    } <= transition_catalog.keys()
    print(
        "V4_MAP_WORKBENCH_AUDIT_OK "
        f"houses=32 traffic=28 pedestrians=108 dogs=3 jobs=20 "
        f"street_features={len(features)} buildings={len(buildings)} "
        f"public_doors=30 buzzers=32 city_laws=ok waterfront_sand=ok "
        f"junctions={len(crossing_groups)} crossings={len(crossings)} signals={len(signals)} "
        f"city_block_scale=0.5 roads=4cars/4lanes gwb=10cars/9lanes "
        f"pavement_blocks={len(pavement_blocks)} generated_building_tiles=65 "
        f"opaque_exterior_boxes=0 transitions=approved"
    )


if __name__ == "__main__":
    main()
