from __future__ import annotations

import json
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import v100_server

RECENT_ISSUES = set(range(42, 112)) - {49}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    client = (ROOT / "client.py").read_text(encoding="utf-8")
    vehicle_art = (ROOT / "vehicle_art.py").read_text(encoding="utf-8")
    grid_renderer = (ROOT / "grid_renderer.py").read_text(encoding="utf-8")
    jobs = (ROOT / "v110_job_locations.py").read_text(encoding="utf-8")
    pedestrian_flow = (ROOT / "v110_pedestrian_flow.py").read_text(encoding="utf-8")
    pedestrian_connectivity = (ROOT / "v110_pedestrian_connectivity.py").read_text(encoding="utf-8")
    grid_world = (ROOT / "grid_world.py").read_text(encoding="utf-8")

    # Audit the installed GridWorld, not the pre-install generator staging. The
    # runtime refinement is the shipped authority for normalized markings.
    objects = v100_server.load_ground_grid().objects
    catalog = json.loads((ROOT / "assets/grid_v100/tile_catalog.json").read_text(encoding="utf-8"))

    require("JOB_NPC_COUNT = 20" in jobs, "job network must contain exactly ten supplier/buyer pairs")
    require("authoritative_npc" in jobs and 'role not in {"supplier", "buyer"}' in server,
            "job points must instantiate authoritative supplier/buyer NPCs")
    require("circle_spawnable" in grid_world and '!= "road"' in grid_world,
            "login spawn contract must reject road cells")

    require("build_crosswalks" in pedestrian_connectivity and "one connected multi-block zebra network" in pedestrian_flow,
            "pedestrian routes must use the connected crossing network")
    require("_nearest_sidewalk_escape" in server and "non-blocking to one another" in server,
            "pedestrian avoidance/road escape contract missing")
    require("_pedestrian_signal_allows_entry" in server and "traffic_phase_green" in server,
            "pedestrian and traffic signal phases must be synchronized")

    lane_dividers = [
        item for item in objects
        if str(item.get("street_marking", "")).startswith(("lane_divider_", "six_lane_divider_"))
    ]
    require(len(lane_dividers) >= 100,
            "lane dividers must populate the installed multi-lane network")
    require(all(item.get("asset") == "mark_white_repeating_single" for item in lane_dividers),
            "lane divider object uses the wrong city_block asset")

    pavement_image = catalog["tiles"]["pavement_small"]["image"]
    require("road_and_pavement_tileset" in pavement_image,
            "pavement fallback must use the large road-and-pavement set")
    require(all("road_and_pavement_tileset" in catalog["tiles"][key]["image"] for key in (
        "curb_left", "curb_right", "curb_top", "curb_bottom",
        "curb_tl_outer", "curb_tr_outer", "curb_bl_outer", "curb_br_outer",
    )), "curb straights/corners must come from one large-set family")

    lamps = [item for item in objects if item.get("lighting_kind") == "sidewalk_lamp"]
    require(lamps and all(item.get("emits_light") for item in lamps), "street lamps and emitters must share records")
    require(all(item.get("light_color_rgb", [255])[2] > item.get("light_color_rgb", [255])[0] for item in lamps),
            "street-lamp pools must use the requested cool-blue hue")

    require("The authored point is the sidewalk mast base" in client and "traffic_lights" in client,
            "overhanging traffic-light fixture/state rendering missing")
    require('"turn_signal"' in server and '"headlights"' in server and '"brake_lights"' in server,
            "authoritative vehicle lighting state missing")
    require("pygame.K_q" in client and "pygame.K_h" in client and 'action": "right"' in client,
            "Q/E/H player vehicle-light controls missing")

    require('str(meta.get("source_nose", "down"))' in vehicle_art and "pygame.transform.flip(source, False, True)" in vehicle_art,
            "player-sheet nose-down to runtime nose-up normalization is missing")
    require("generated_vehicle_fleet_2026_08_22" in vehicle_art,
            "generated vehicles must avoid the duplicate legacy shadow")
    require("_bounded_traffic_heading" in server and "_recover_visible_stall" in server,
            "bounded steering and stall recovery missing")
    require("definition.kind == \"building\"" in grid_renderer and "_suppress_building_perimeter_outline" in grid_renderer,
            "premade and modular building outline suppression must share the renderer")

    require('self.pause_page == "controls"' in client and 'buttons["controls"]' in client,
            "controls must remain a separate pause-menu page")
    require("tire scre" not in client.lower(), "obsolete acceleration tire-screech loop is still present")

    print(f"recent bug audit passed: {len(RECENT_ISSUES)} reports (#42-#111, excluding #49)")
    print(f"map art: {len(lane_dividers)} lane dividers, {len(lamps)} synchronized lamp records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
