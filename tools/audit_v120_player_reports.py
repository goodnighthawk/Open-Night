from __future__ import annotations

"""Regression gate for the player-visible v1.2 corrective report batch."""

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
               and row.get("placement_policy") == "nearest_free_sidewalk_cell_v12" for row in lamps), \
        "streetlamps were not relocated from the expanded road onto sidewalks"
    connectivity = v110_pedestrian_connectivity.apply(world)
    zebra_art = [row for row in world.objects if str(row.get("street_marking", "")).startswith("zebra_")]
    assert zebra_art and len(zebra_art) < 600, "zebra-crossing art is still visually overpopulated"
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
    assert len(highway_dividers) == len(highway_centerlines) * 6, "eight-lane highway dividers are incomplete"
    assert len(centerlines) == 384 and len(lane_dividers) == 1664, "scaled wide-road markings are incomplete"
    morphology = world.data.get("road_morphology", {})
    assert morphology.get("physical_primary_road_width_cells") == 7, "primary roads are not physically wide"
    assert morphology.get("physical_central_highway_width_cells") == 11, "central highway is not physically wider"
    assert len(world.data.get("building_synthesis", {}).get("buildings", [])) == 28, "building density was not reduced"
    assert all(row.get("asset") == "mark_white_repeating_single" for row in lane_dividers), "lane lines do not use city-block art"
    assert sum(bool(row.get("highway_lane_network")) for row in lane_dividers) == 384, "highway dividers were not rescaled"
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
    assert cleaned.get_at((2, 2)).a == 0, "exterior building frame remains visible"
    assert cleaned.get_at((7, 7)).a == 255, "interior rooftop detail was erased"

    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    updater_source = (ROOT / "UPDATE_OPEN_NIGHT.bat").read_text(encoding="utf-8")
    assert 'self.pause_page == "controls"' in client_source
    assert 'draw_character(self.screen, (sx, sy)' in client_source
    assert 'pygame.draw.circle(self.screen, color, (sx, sy), 28' in client_source, "supplier NPC lacks final-space visibility halo"
    assert 'car.render_length * 1.65' in client_source and 'npc_scale = max(2' in client_source
    server_source = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "_traffic_should_yield_to_pedestrian" in server_source and '"horn": time.monotonic() < self.horn_until' in server_source
    assert "moved_aside" in server_source and 'allow_road = npc.kind == "pedestrian"' in server_source
    assert "Install: %CD%" in updater_source and "Commit: !LOCAL_SHA!" in updater_source
    print(f"V120_PLAYER_REPORTS_OK signals={len(signals)} roof_decals={len(roof_decals)} centerlines={len(centerlines)} lane_dividers={len(lane_dividers)} sidewalk_apron={v110_pedestrian_connectivity.SIDEWALK_APRON_FRACTION:.2f} sidewalk_drive=yes job_npcs=yes controls_tab=yes frames_removed=yes")


if __name__ == "__main__":
    main()
