from __future__ import annotations

"""Focused behavioral release gate for player reports #126-#135."""

import copy
import json
import math
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

pygame.init()
pygame.display.set_mode((1, 1))

import client
from common import get_map
from grid_renderer import GridRenderer
import server
import v100_server
import v110_job_locations
import v110_grid_population
import v110_vehicle_proportions
from vehicle_art import SOURCE_NOSE_CORRECTIONS, _base_car
from vehicle_catalog import load_vehicle_catalog


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _visible_pixels(surface: pygame.Surface, alpha: int = 20) -> int:
    return sum(
        surface.get_at((x, y)).a > alpha
        for y in range(surface.get_height())
        for x in range(surface.get_width())
    )


def _vehicle_footprint_and_endcap_audit() -> dict:
    catalog = load_vehicle_catalog()
    measurements = []
    for index, raw in enumerate(catalog):
        if not raw.get("traffic_eligible"):
            continue
        meta = v110_vehicle_proportions.scaled_meta(raw)
        sprite = _base_car(index, int(meta["render_length"]))
        require(sprite is not None, f"vehicle {index} failed to render")
        rect = sprite.get_bounding_rect(min_alpha=10)
        require(rect.width > 0 and rect.height > 0, f"vehicle {index} rendered empty")
        length_ratio = float(meta["collision_length"]) * 1.18 / rect.height
        width_ratio = float(meta["collision_width"]) * 1.14 / rect.width
        require(0.98 <= length_ratio <= 1.20, f"vehicle {index} longitudinal footprint mismatch {length_ratio:.2f}")
        require(0.65 <= width_ratio <= 1.46, f"vehicle {index} lateral footprint mismatch {width_ratio:.2f}")
        measurements.append((index, length_ratio, width_ratio))

    reported = {}
    panels = pygame.Surface((1000, 260), pygame.SRCALPHA)
    panels.fill((38, 41, 48, 255))
    font = pygame.font.Font(None, 24)
    for column, index in enumerate((5, 8, 19, 22, 23, 24, 34)):
        meta = v110_vehicle_proportions.scaled_meta(catalog[index])
        sprite = _base_car(index, 180)
        require(sprite is not None, f"reported vehicle {index} failed to render")
        rect = sprite.get_bounding_rect(min_alpha=10)
        margins = (rect.left, rect.top, sprite.get_width() - rect.right, sprite.get_height() - rect.bottom)
        require(min(margins) >= 2, f"reported vehicle {index} still touches a clipped edge: {margins}")
        reported[index] = {"margins": margins, "category": meta.get("category", "")}
        center_x = 60 + column * 135
        panels.blit(sprite, sprite.get_rect(center=(center_x, 130)))
        panels.blit(font.render(str(index), True, (255, 255, 255)), (center_x - 10, 5))

    preview = ROOT / "work" / "v210_vehicle_endcaps_preview.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(panels, preview)
    for source_name in (
        "free-pixel-cars-link-in-comments-v0-fujphf59vg661.png#005",
        "free-pixel-cars-link-in-comments-v0-xs01xj2gvg661.webp#000",
    ):
        require(SOURCE_NOSE_CORRECTIONS.get(source_name) == "up", f"orientation correction missing for {source_name}")
    return {
        "vehicles": len(measurements),
        "length_ratio_range": [round(min(row[1] for row in measurements), 3), round(max(row[1] for row in measurements), 3)],
        "width_ratio_range": [round(min(row[2] for row in measurements), 3), round(max(row[2] for row in measurements), 3)],
        "reported_endcaps": reported,
        "preview": str(preview),
    }


def _prop_and_building_audit(world) -> dict:
    cones = [row for row in world.objects if row.get("street_item_kind") == "traffic_cone"]
    trees = [row for row in world.objects if row.get("collision_kind") == "tree"]
    closures = {str(row.get("road_closure_id", "")) for row in cones if row.get("road_closure_id")}
    require((len(cones) == 24 and not closures) or (len(cones) == 15 and len(closures) == 3),
            f"traffic-cone baseline/grouped closure count failed: {len(cones)}, {closures}")
    require(trees, "no collidable round shrubs/trees were populated")
    for row in cones + trees:
        definition = world.catalog.object(str(row["asset"]))
        width = float(row.get("width_px", definition.native_width_px))
        height = float(row.get("height_px", definition.native_height_px))
        cx = int(row["gx"]) * world.cell_px + float(row.get("offset_x_px", 0.0)) + width * 0.5
        cy = int(row["gy"]) * world.cell_px + float(row.get("offset_y_px", 0.0)) + height * 0.5
        require(float(row.get("collision_radius_px", 0.0)) >= 11.0, f"undersized prop collision: {row.get('asset')}")
        require(world.object_collision_at(cx, cy), f"prop does not participate in collision: {row.get('asset')}")
        player_car = SimpleNamespace(collision_length=90.0, collision_width=44.0, controlled_by="audit-player")
        require(v110_grid_population._grid_vehicle_blocked(world, player_car, cx, cy, 0.0),
                f"player vehicle ignores prop collision: {row.get('asset')}")
    require(all(int(row["width_px"]) >= 42 and int(row["height_px"]) >= 60 for row in cones), "cones are still undersized")
    require(all(int(row["width_px"]) >= 112 and int(row["height_px"]) >= 120 for row in trees), "trees are still undersized")

    renderer = GridRenderer(world)
    tile_id = "bld_blue_top_center"
    tile = world.catalog[tile_id]
    before = renderer._load_image(tile.image)
    before = pygame.transform.scale(before, (world.cell_px, world.cell_px))
    before = renderer._suppress_building_perimeter_outline(before)
    after = renderer._tile_surface(tile_id)
    before_pixels, after_pixels = _visible_pixels(before), _visible_pixels(after)
    require(after_pixels > before_pixels, "building visual coverage did not increase")
    require(after.get_size() == (world.cell_px, world.cell_px), "building expansion escaped its collision cell")
    comparison = pygame.Surface((world.cell_px * 2 + 24, world.cell_px + 36), pygame.SRCALPHA)
    comparison.fill((29, 32, 39, 255))
    comparison.blit(before, (0, 36))
    comparison.blit(after, (world.cell_px + 24, 36))
    label = pygame.font.Font(None, 24)
    comparison.blit(label.render("before", True, (240, 240, 240)), (8, 8))
    comparison.blit(label.render("runtime", True, (240, 240, 240)), (world.cell_px + 32, 8))
    building_preview = ROOT / "work" / "v210_building_coverage_preview.png"
    pygame.image.save(comparison, building_preview)
    return {
        "cones": len(cones), "trees": len(trees),
        "building_visible_pixels": [before_pixels, after_pixels],
        "building_preview": str(building_preview),
    }


def _world_map_audit(world) -> dict:
    config = copy.deepcopy(get_map())
    v110_job_locations.normalize(config, world)
    jobs = config.get("job_locations", [])
    require(len(jobs) == 20, f"expected 20 global job destinations, got {len(jobs)}")
    require(sum(row.get("role") == "supplier" for row in jobs) == 10, "supplier population incomplete")
    require(sum(row.get("role") == "buyer" for row in jobs) == 10, "buyer population incomplete")
    payload = server.network_map_payload(config)
    require(len(payload.get("job_locations", [])) == len(jobs), "chunk map payload discarded off-interest jobs")
    portable = copy.deepcopy(config)
    portable["_portable_map_hash"] = "audit-portable-map"
    portable_payload = server.network_map_payload(portable)
    require(len(portable_payload.get("job_locations", [])) == len(jobs),
            "portable map payload discarded global jobs")
    return {
        "suppliers": 10, "buyers": 10,
        "payload_jobs": len(payload["job_locations"]),
        "portable_payload_jobs": len(portable_payload["job_locations"]),
    }


def _player_impact_audit() -> dict:
    now = time.monotonic()
    player = SimpleNamespace(x=12.0, y=0.0, interior_id="", level=0)
    session = SimpleNamespace(
        player=player, driving_vehicle_id="", passenger_vehicle_id="", riding_bicycle_id="",
        collision_disabled_until=0.0, forced_prone_until=0.0, prone=False, crouching=True,
        crouch_requested=False, crouch_cancel_latched=False, stand_delay_remaining=1.0,
        jump_kind="jump", jump_until=now + 1.0, jump_velocity_x=10.0, jump_velocity_y=0.0, boost=True,
    )
    car = server.TrafficVehicle("impact-audit", 0, 1, 0.0, 0.0, 0.0, 100.0, 0, 0,
                                collision_length=120.0, collision_width=56.0)
    previous = list(server.traffic_vehicles)
    try:
        server.traffic_vehicles[:] = [car]
        server.update_player_vehicle_impacts([session], now)
        require(session.prone and not session.crouching and not session.jump_kind, "vehicle impact did not force prone state")
        require(session.forced_prone_until >= now + 1.0, "forced prone interval is too short")
        require(session.collision_disabled_until > session.forced_prone_until, "traffic-blocking collision was not disabled long enough")
        require(not server._traffic_should_yield_to_player(car, (100.0, 0.0), [session]),
                "striking car still blocks on the temporarily non-colliding player")
    finally:
        server.traffic_vehicles[:] = previous
    return {
        "forced_prone_seconds": round(session.forced_prone_until - now, 2),
        "collision_disabled_seconds": round(session.collision_disabled_until - now, 2),
    }


def _vehicle_light_audit() -> dict:
    base = client.RemoteVehicle({
        "id": "light-audit", "x": 0.0, "y": 0.0, "angle": 0.0, "speed": 0.0,
        "sprite": 36, "render_length": 165, "collision_width": 68.0,
    })
    lit = client.RemoteVehicle({
        "id": "light-audit", "x": 0.0, "y": 0.0, "angle": 0.0, "speed": 0.0,
        "sprite": 36, "render_length": 165, "collision_width": 68.0,
        "headlights": True, "brake_lights": True, "turn_signal": 1,
    })
    panels = []
    original_monotonic = client.time.monotonic
    try:
        client.time.monotonic = lambda: 0.0
        for car in (base, lit):
            game = object.__new__(client.Game)
            game.screen = pygame.Surface((600, 320), pygame.SRCALPHA)
            game.screen.fill((21, 23, 29, 255))
            game.world_to_screen = lambda _x, _y: (300, 160)
            game.tiny_font = pygame.font.Font(None, 18)
            client.Game.draw_vehicle(game, car)
            panels.append(game.screen)
    finally:
        client.time.monotonic = original_monotonic
    different = sum(
        panels[0].get_at((x, y)) != panels[1].get_at((x, y))
        for y in range(320) for x in range(600)
    )
    require(different >= 1000, f"vehicle lamp treatment is not visibly readable: {different} changed pixels")
    preview = pygame.Surface((1200, 320), pygame.SRCALPHA)
    preview.blit(panels[0], (0, 0))
    preview.blit(panels[1], (600, 0))
    light_preview = ROOT / "work" / "v210_vehicle_lights_preview.png"
    pygame.image.save(preview, light_preview)
    return {"changed_pixels": different, "preview": str(light_preview)}


def main() -> int:
    world = v100_server.load_ground_grid()
    results = {
        "reports": "#126-#135",
        "vehicle": _vehicle_footprint_and_endcap_audit(),
        "props_and_buildings": _prop_and_building_audit(world),
        "world_map": _world_map_audit(world),
        "player_impact": _player_impact_audit(),
        "vehicle_lights": _vehicle_light_audit(),
        "release_status": "authorized_v2.1",
    }
    print("V2.1 CURRENT REPORTS AUDIT: PASS")
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
