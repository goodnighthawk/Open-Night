from __future__ import annotations

"""Regression gate for the player-visible v1.2/v1.3 corrective report batches."""

import copy
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame

import v100_runtime_refinement
v100_runtime_refinement.install()
import v100_scale_normalization
v100_scale_normalization.install()
from common import get_map
from grid_renderer import GridRenderer
from grid_runtime import load_ground_grid
import v110_grid_population
import v110_job_locations
import v110_pedestrian_connectivity


def main() -> None:
    pygame.init()
    pygame.display.set_mode((8, 8))
    world = load_ground_grid()
    config = copy.deepcopy(get_map())
    v110_job_locations.normalize(config, world)
    signals = config.get("traffic_signals", [])
    assert len(signals) >= 24, "GridWorld traffic signals were not restored"
    assert {int(row["phase"]) for row in signals} == {0, 1}
    for key in v110_job_locations.JOB_KEYS:
        assert world.collision_at("ground", *config[key]) in {"walk", "sidewalk"}, f"{key} is still on the road"
    jobs = config.get("job_locations", [])
    assert len(jobs) == 20 and sum(row["role"] == "supplier" for row in jobs) == 10
    assert sum(row["role"] == "buyer" for row in jobs) == 10
    assert all(row.get("authoritative_npc") for row in jobs)
    roof_decals = [row for row in world.objects if row.get("composition_pass") == "roof_palette_v1"]
    assert roof_decals and all(int(row.get("width_px", 0)) >= 64 and int(row.get("height_px", 0)) >= 64
                               and str(row.get("placement_policy", "")).startswith("centered_")
                               and int(row.get("offset_x_px", 0)) >= 12 and int(row.get("offset_y_px", 0)) >= 12
                               for row in roof_decals), "roof decals are not large, centered, and inboard"
    lamps = [row for row in world.objects if row.get("lighting_kind") == "sidewalk_lamp"]
    assert len(lamps) == 90
    lamp_cells = {(int(row["gx"]), int(row["gy"])) for row in lamps}
    assert len(lamp_cells) == len(lamps), "streetlamps overlap after road expansion"
    assert all(world.collision_at("ground", *world.cell_center(int(row["gx"]), int(row["gy"]))) == "sidewalk"
               and row.get("placement_policy") == "half_scale_inset_sidewalk_base_v22"
               and int(row.get("sidewalk_inset_px", 0)) == 52
               and row.get("asset") == "street_item_lamp"
               and row.get("light_registration") == "cardinal_transform_shared_anchors_report60"
               and row.get("road_overhang_direction") in {"north", "east", "south", "west"}
               and int(row.get("width_px", 0)) >= 51
               and int(row.get("height_px", 0)) >= 192
               and int(row.get("light_radius_px", 0)) >= 180 for row in lamps), \
        "streetlamps were not relocated from the expanded road onto sidewalks"
    street_items = [row for row in world.objects if row.get("street_item_kind")]
    assert sum(row.get("street_item_kind") == "telephone_box" for row in street_items) == 16
    cones = [row for row in street_items if row.get("street_item_kind") == "traffic_cone"]
    closures = {str(row.get("road_closure_id", "")) for row in cones if row.get("road_closure_id")}
    assert (len(cones) == 24 and not closures) or (len(cones) == 15 and len(closures) == 3), \
        "traffic-cone baseline or grouped v2.5 closure contract failed"
    for asset, filename in {
        "street_item_lamp": "street_lamp.png",
        "street_item_telephone_box": "telephone_box.png",
        "street_item_traffic_cone": "traffic_cone.png",
    }.items():
        definition = world.catalog.object(asset)
        assert definition.image == f"city_block://street_decorations/{filename}"
        path = ROOT / "assets" / "source_packs" / "city_block" / "street_decorations" / filename
        loaded = pygame.image.load(str(path))
        assert loaded.get_width() > 32 and loaded.get_height() > 32 and loaded.get_flags() & pygame.SRCALPHA
    connectivity = v110_pedestrian_connectivity.apply(world)
    assert connectivity["sidewalk_infill_asset"] == "pavement_small"
    assert connectivity["visual_style"] == "open_night_grunge_neon"
    zebra_art = [row for row in world.objects if str(row.get("street_marking", "")).startswith("zebra_")]
    assert zebra_art and len(zebra_art) < 120, "zebra-crossing art is still visually overpopulated"
    assert all(row.get("street_marking") == "zebra_midblock" for row in zebra_art)
    assert connectivity["pedestrian_crosswalk_count"] >= 100, "routing crossings were removed with visual art"
    centerlines = [row for row in world.objects if str(row.get("street_marking", "")).startswith("dashed_center_line_")]
    assert centerlines and all(row.get("registration_policy") == "road_cell_center_v12" for row in centerlines)
    for row in centerlines:
        width, height = int(row["width_px"]), int(row["height_px"])
        if int(row.get("rotation", 0)) == 90:
            width, height = height, width
        cx = int(row.get("offset_x_px", 0)) + width / 2.0
        cy = int(row.get("offset_y_px", 0)) + height / 2.0
        assert abs(cx - world.cell_px / 2.0) <= 1.0 and abs(cy - world.cell_px / 2.0) <= 1.0, row
    lane_dividers = [row for row in world.objects if str(row.get("street_marking", "")).startswith("six_lane_divider_")]
    normal_dividers = [row for row in lane_dividers if not row.get("highway_lane_network")]
    highway_dividers = [row for row in lane_dividers if row.get("highway_lane_network")]
    normal_centerlines = [row for row in centerlines if not (str(row.get("street_marking", "")).endswith("horizontal") and int(row.get("gy", -1)) == 24)]
    highway_centerlines = [row for row in centerlines if str(row.get("street_marking", "")).endswith("horizontal") and int(row.get("gy", -1)) == 24]
    assert len(normal_dividers) == len(normal_centerlines) * 4, "primary six-lane dividers are incomplete"
    assert len(highway_dividers) == len(highway_centerlines) * 4, "highway dividers are incomplete"
    assert lane_dividers and len(lane_dividers) == len(centerlines) * 4, "six-lane markings are incomplete"
    horizontal, vertical = v110_pedestrian_connectivity.road_bands(world)
    junctions = {(gx, gy) for h in horizontal for v in vertical
                 for gx in range(v.start, v.end + 1) for gy in range(h.start, h.end + 1)}
    assert all((int(row["gx"]), int(row["gy"])) not in junctions for row in centerlines), \
        "center/lane art still stacks through junctions"
    morphology = world.data.get("road_morphology", {})
    assert morphology.get("physical_primary_road_width_cells") == 5, "six-lane primary roads lack physical clearance"
    assert morphology.get("physical_central_highway_width_cells") == 7, "central highway is not physically wider"
    buildings = world.data.get("building_synthesis", {}).get("buildings", [])
    infill = [row for row in buildings if row.get("infill_policy")]
    assert len(buildings) == 28 or (len(buildings) == 30 and len(infill) == 2), \
        "building density baseline or v2.5 two-block infill contract failed"
    assert all(row.get("asset") == "mark_white_repeating_single" for row in lane_dividers), "lane lines do not use city-block art"
    assert world.width * world.height == 6144 and world.data.get("playable_area_multiplier") == 2, "playable map area is not exact 2x"
    routes = v110_grid_population._build_traffic_routes(world)
    lane_pairs = {(row.get("lane_direction"), int(row.get("lane_index", 0))) for row in routes}
    assert lane_pairs == {(direction, lane) for direction in ("cw", "ccw") for lane in (1, 2, 3)}
    assert v110_pedestrian_connectivity.SIDEWALK_APRON_FRACTION >= 0.36, "sidewalk apron area was not doubled"

    pavement = next((gx, gy) for gy in range(world.height) for gx in range(world.width)
                    if world.collision_at("ground", *world.cell_center(gx, gy)) in {"walk", "sidewalk"})
    px, py = world.cell_center(*pavement)
    ai_car = SimpleNamespace(collision_length=20.0, collision_width=12.0, controlled_by="")
    player_car = SimpleNamespace(collision_length=20.0, collision_width=12.0, controlled_by="player")
    assert v110_grid_population._grid_vehicle_blocked(world, ai_car, px, py, 0.0)
    assert not v110_grid_population._grid_vehicle_blocked(world, player_car, px, py, 0.0)

    sample = pygame.Surface((16, 16), pygame.SRCALPHA)
    sample.fill((0, 0, 0, 0))
    pygame.draw.rect(sample, (20, 20, 20, 255), (2, 2, 12, 12), width=2)
    pygame.draw.rect(sample, (90, 110, 120, 255), (4, 4, 8, 8))
    pygame.draw.rect(sample, (20, 20, 20, 255), (7, 7, 2, 2))
    cleaned = GridRenderer._suppress_building_perimeter_outline(sample)
    assert not GridRenderer._is_dark_building_outline(cleaned.get_at((2, 2))), \
        "exterior building frame remains visible"
    assert cleaned.get_at((7, 7)).a == 255 and GridRenderer._is_dark_building_outline(cleaned.get_at((7, 7))), \
        "interior rooftop detail was erased"

    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    updater_source = (ROOT / "UPDATE_OPEN_NIGHT.bat").read_text(encoding="utf-8")
    assert 'self.pause_page == "controls"' in client_source
    assert 'self.font.render("GAME PAUSED"' in client_source and client_source.count('"WASD / arrows') == 1
    assert 'draw_character(self.screen, (sx, sy)' in client_source
    assert 'pygame.draw.circle(self.screen, color, (sx, sy), 28' in client_source, "supplier NPC lacks final-space visibility halo"
    assert 'target_len = int(max(24, car.render_length))' in client_source and 'npc_scale = max(2' in client_source
    assert 'car.render_length * 1.65' not in client_source, "legacy oversized car multiplier returned"
    server_source = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "_traffic_should_yield_to_pedestrian" in server_source and '"horn": time.monotonic() < self.horn_until' in server_source
    assert "moved_aside" in server_source and 'allowed = {"walk", "sidewalk"}' in server_source
    assert "fleeing_horn" in server_source and "npc.stuck_time" in server_source
    assert "ambient pedestrians are non-blocking to one another" in server_source
    assert "Install: %CD%" in updater_source and "Commit: !LOCAL_SHA!" in updater_source
    print(f"V120_PLAYER_REPORTS_OK signals={len(signals)} roof_decals={len(roof_decals)} centerlines={len(centerlines)} lane_dividers={len(lane_dividers)} zebras={len(zebra_art)} street_items={len(street_items)+len(lamps)} sidewalk_apron={v110_pedestrian_connectivity.SIDEWALK_APRON_FRACTION:.2f} sidewalk_drive=yes job_npcs=yes controls_tab=yes frames_removed=yes")


if __name__ == "__main__":
    main()
