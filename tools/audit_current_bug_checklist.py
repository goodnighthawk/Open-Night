from __future__ import annotations

"""Behavioral release gate for current player reports #102-#111."""

from collections import Counter, defaultdict
import math
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

import v100_server
import server
from gameplay.radio import RadioPlayer
from grid_renderer import GridRenderer
from grid_world import CURB_WORLD_TO_PACK_IMAGE
from vehicle_art import SOURCE_NOSE_CORRECTIONS


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    scale_source = (ROOT / "v100_scale_normalization.py").read_text(encoding="utf-8")
    recovery_source = (ROOT / "v110_traffic_recovery.py").read_text(encoding="utf-8")
    renderer_source = (ROOT / "grid_renderer.py").read_text(encoding="utf-8")

    # 1-2: a playing stream is torn down off-car and both controls are live HUD UI.
    radio = RadioPlayer()
    radio.playing_index = 0
    radio.update(None)
    require(radio.playing_index is None, "radio did not stop when desired station became None")
    for token in (
        "desired_station = None", "self.radio.update(None)",
        "_draw_main_audio_icons", "handle_main_audio_click",
        "self.radio.toggle_muted()", "self.audio.toggle_muted()",
    ):
        require(token in client_source, f"main audio contract missing {token!r}")

    world = v100_server.load_ground_grid()

    # 3: rounded source-pack corners and multiple approved pavement variants.
    require(all("/circle_" in image for key, image in CURB_WORLD_TO_PACK_IMAGE.items() if "outer" in key),
            "sharp curb-corner assets remain")
    curb_tiles = Counter(tile for row in world.layers["ground"] for tile in row if tile.startswith("curb_"))
    require(sum(count for tile, count in curb_tiles.items() if "outer" in tile) >= 24,
            f"rounded curb corners were not installed in the live grid: {curb_tiles}")
    pavement = Counter(tile for row in world.layers["ground"] for tile in row if tile.startswith("pavement"))
    require(pavement["pavement_pattern"] >= 24 and pavement["pavement_v"] >= 100,
            f"pavement variation is too sparse: {pavement}")

    # 4: the exact reported gridcar002 crop overrides the sheet-wide direction.
    require(SOURCE_NOSE_CORRECTIONS.get(
        "free-pixel-cars-link-in-comments-v0-fujphf59vg661.png#001"
    ) == "up", "gridcar002 forward-direction correction missing")

    # 5: every fixture base is sidewalk-anchored and every shared light head is road-anchored.
    lamps = [item for item in world.objects if item.get("emits_light")]
    require(len(lamps) >= 80, f"too few synchronized street lamps: {len(lamps)}")
    for lamp in lamps:
        base = world.cell_center(int(lamp["gx"]), int(lamp["gy"]))
        require(world.collision_at("ground", *base) == "sidewalk", "lamp base left the sidewalk")
        world_x = int(lamp["gx"]) * world.cell_px + int(lamp.get("offset_x_px", 0))
        world_y = int(lamp["gy"]) * world.cell_px + int(lamp.get("offset_y_px", 0))
        light = (world_x + int(lamp["light_offset_x_px"]), world_y + int(lamp["light_offset_y_px"]))
        require(world.collision_at("ground", *light) == "road", "lamp head/light pool does not reach road")
    require("minimum: int | None = None" in scale_source, "signed placement offsets are still clamped")

    # 6: exterior-connected dark ink is actually removed by the runtime renderer.
    renderer = GridRenderer(world)
    tile_id = "bld_blue_top_center"
    raw = renderer._load_image(world.catalog[tile_id].image)
    raw = pygame.transform.scale(raw, (world.cell_px, world.cell_px))
    cleaned = renderer._tile_surface(tile_id)
    band = int(world.cell_px * 0.44)
    def dark_band_count(surface) -> int:
        return sum(
            renderer._is_dark_building_outline(surface.get_at((x, y)))
            for y in range(world.cell_px) for x in range(world.cell_px)
            if x < band or x >= world.cell_px - band or y < band or y >= world.cell_px - band
        )
    require(dark_band_count(raw) > 500 and dark_band_count(cleaned) == 0,
            "building perimeter-frame removal is not effective")
    require('target.blit(self._tile_surface("pavement_small"), position)' in renderer_source,
            "transparent building setbacks still expose the black framebuffer")

    # 7: sparse median objects and paired lane dividers are centered/symmetric.
    markings = [item for item in world.objects if item.get("street_marking")]
    require(len(markings) <= 500, f"road line object count remains excessive: {len(markings)}")
    groups: dict[tuple[str, int, int], list[float]] = defaultdict(list)
    for item in markings:
        marking = str(item["street_marking"])
        if marking.startswith("dashed_center_line_"):
            if marking.endswith("vertical"):
                actual = float(item.get("offset_x_px", 0)) + float(item["width_px"]) * 0.5
            else:
                actual = float(item.get("offset_y_px", 0)) + float(item["width_px"]) * 0.5
            require(abs(actual - world.cell_px * 0.5) <= 0.51, f"median is off center: {item}")
        elif marking.startswith("six_lane_divider_"):
            axis_offset = item.get("offset_x_px") if marking.endswith("vertical") else item.get("offset_y_px")
            groups[(marking, int(item["gx"]), int(item["gy"]))].append(
                float(axis_offset) + float(item["width_px"]) * 0.5 - world.cell_px * 0.5
            )
    require(groups, "lane divider groups missing")
    for offsets in groups.values():
        offsets.sort()
        require(len(offsets) == 4, f"incomplete six-lane divider group: {offsets}")
        require(abs(offsets[0] + offsets[3]) <= 1.01 and abs(offsets[1] + offsets[2]) <= 1.01,
                f"lane divider group is asymmetric: {offsets}")

    # 8: validation now builds the authoritative routes and visible fixture list.
    v100_server.install_v100_server()
    server.TRAFFIC_COUNT = 28
    errors = v100_server.validate_active_authority(server.ACTIVE_MAP)
    require(not errors, f"grid authority validation failed: {errors}")
    signals = server.ACTIVE_MAP.get("traffic_signals", [])
    routes = server.ACTIVE_MAP.get("traffic_routes", [])
    require(len(signals) >= 80, f"working junction fixtures were not published: {len(signals)}")
    require(routes and all(route.get("_runtime_signals") for route in routes), "AI routes lack stop phases")
    payload = server.network_map_payload(server.ACTIVE_MAP)
    require(len(payload.get("traffic_signals", [])) == len(signals),
            "chunked login payload does not deliver the generated signal fixtures")
    require('not bool(getattr(car, "red_light_waiting", False))' in recovery_source,
            "stall recovery can still move cars through a red light")

    # 9: every configured login spawn is walkable and well inside the map.
    inset = world.cell_px * 3.0
    for spawn_x, spawn_y in world.login_spawns:
        require(inset <= spawn_x <= world.world_w - inset and inset <= spawn_y <= world.world_h - inset,
                f"edge/corner login spawn remains: {(spawn_x, spawn_y)}")
        require(world.circle_spawnable("ground", spawn_x, spawn_y, server.PLAYER_RADIUS),
                f"unsafe login spawn remains: {(spawn_x, spawn_y)}")

    # 10: one stationary jump reaches a traversable roof and the same escape returns to Ground.
    fire = next(item for item in world.objects if item.get("asset") == "placeholder_fire_escape")
    ground = world.cell_center(int(fire["gx"]), int(fire["gy"]))
    upward = world.fire_escape_transition(*ground, 0)
    require(upward is not None and upward[0] == 1, "fire escape has no Ground-to-roof endpoint")
    require(world.circle_roof_walkable(upward[1], upward[2], server.PLAYER_RADIUS),
            "fire escape roof endpoint is not traversable")
    downward = world.fire_escape_transition(upward[1], upward[2], 1)
    require(downward is not None and downward[0] == 0, "fire escape has no roof-to-Ground endpoint")
    require(math.hypot(downward[1] - ground[0], downward[2] - ground[1]) < 1.0,
            "fire escape return endpoint moved away from its base")
    player = server.PlayerState("fire-audit", "FireAudit", ground[0], ground[1])
    session = server.ClientSession(None, player, "5550000198", [])
    server.GRID_RUNTIME_ACTIVE = True
    server.GRID_WORLD = world
    require(server.request_grid_fire_escape(session) == "roof" and player.level == 1,
            "authoritative server did not apply the upward fire-escape transition")
    require(server.request_grid_fire_escape(session) == "ground" and player.level == 0,
            "authoritative server did not apply the return fire-escape transition")

    print("CURRENT BUG CHECKLIST AUDIT: PASS")
    print(
        f"  reports=#102-#111 lamps={len(lamps)} markings={len(markings)} "
        f"signals={len(signals)} routes={len(routes)} pavement_variants="
        f"{pavement['pavement_pattern'] + pavement['pavement_v']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
