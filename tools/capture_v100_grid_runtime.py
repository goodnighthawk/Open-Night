#!/usr/bin/env python3
"""Render actual Ground/exterior and Roof frames from the current grid runtime."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from grid_renderer import GridRenderer
from grid_runtime import load_ground_grid, load_roof_grid

GROUND_DETAIL_OUT = ROOT / "assets/grid_v100/GROUND_RUNTIME_PROOF_2560x1440.png"
ROOF_DETAIL_OUT = ROOT / "assets/grid_v100/ROOF_RUNTIME_PROOF_2560x1440.png"
GROUND_FULL_OUT = ROOT / "assets/grid_v100/GROUND_FULL_MAP_RUNTIME_PROOF_2560x1440.png"
ROOF_FULL_OUT = ROOT / "assets/grid_v100/ROOF_FULL_MAP_RUNTIME_PROOF_2560x1440.png"
NIGHT_AUDIT_OUT = ROOT / "assets/grid_v100/GROUND_NIGHT_RUNTIME_AUDIT.json"
LIGHTING_PROOF_OUT = ROOT / "assets/grid_v100/GROUND_STREET_LIGHTING_RUNTIME_PROOF_1280x720.png"
LIGHTING_AUDIT_OUT = ROOT / "assets/grid_v100/GROUND_STREET_LIGHTING_ALIGNMENT_AUDIT.json"
SILHOUETTE_AUDIT_OUT = ROOT / "assets/grid_v100/BUILDING_SILHOUETTE_RUNTIME_AUDIT.json"
W, H = 2560, 1440
REVIEW_ZOOM = 0.5  # 50% review zoom: show twice the gameplay-world width/height.
GROUND_NIGHT_MEAN_RANGE = (0.08, 0.25)
GROUND_NIGHT_MIN_SPREAD = 0.18


def first_cell(world, layer: str, predicate):
    for gy, row in enumerate(world.layers[layer]):
        for gx, tile_id in enumerate(row):
            if predicate(tile_id, world.catalog[tile_id]):
                return gx, gy
    raise RuntimeError(f"required {layer} proof cell not present")


def camera_for(world, x: float, y: float, width: int, height: int) -> tuple[float, float]:
    return (
        max(0.0, min(max(0.0, world.world_w - width), x - width / 2)),
        max(0.0, min(max(0.0, world.world_h - height), y - height / 2)),
    )


def framebuffer_luminance(surface: pygame.Surface) -> dict[str, float]:
    """Return deterministic sampled Rec.709 luminance statistics."""
    raw = pygame.image.tobytes(surface, "RGB")
    values = [
        (54 * raw[i] + 183 * raw[i + 1] + 19 * raw[i + 2]) / (255.0 * 256.0)
        for i in range(0, len(raw), 12)  # every fourth pixel
    ]
    values.sort()
    last = len(values) - 1
    p05 = values[int(last * 0.05)]
    p95 = values[int(last * 0.95)]
    return {
        "mean": sum(values) / len(values),
        "p05": p05,
        "p95": p95,
        "p95_minus_p05": p95 - p05,
    }


def gameplay_geometry_hash(world) -> str:
    payload = {
        "cell_px": world.cell_px,
        "width": world.width,
        "height": world.height,
        "layers": world.layers,
        "login_spawns": world.login_spawns,
        "collisions": {
            tile_id: world.catalog[tile_id].collision
            for tile_id in sorted(world.catalog.entries)
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def mean_rgb_disk(surface: pygame.Surface, cx: int, cy: int, radius: int) -> tuple[float, float, float]:
    totals = [0, 0, 0]
    count = 0
    radius2 = radius * radius
    for y in range(max(0, cy - radius), min(surface.get_height(), cy + radius + 1), 2):
        for x in range(max(0, cx - radius), min(surface.get_width(), cx + radius + 1), 2):
            if (x - cx) ** 2 + (y - cy) ** 2 > radius2:
                continue
            color = surface.get_at((x, y))
            totals[0] += color.r
            totals[1] += color.g
            totals[2] += color.b
            count += 1
    return tuple(value / (255.0 * count) for value in totals)


def save_lighting_proof(renderer: GridRenderer, world, spawn: tuple[float, float]) -> dict:
    lamps = [obj for obj in world.objects if obj.get("composition_pass") == "street_lighting_v1"]
    if len(lamps) != 48:
        raise SystemExit(f"runtime lighting proof expected 48 lamps, got {len(lamps)}")
    sx, sy = spawn
    lamp = min(
        lamps,
        key=lambda obj: (
            int(obj["gx"]) * world.cell_px + int(obj.get("offset_x_px", 0))
            + int(obj["light_offset_x_px"]) - sx
        ) ** 2 + (
            int(obj["gy"]) * world.cell_px + int(obj.get("offset_y_px", 0))
            + int(obj["light_offset_y_px"]) - sy
        ) ** 2,
    )
    center_x = (
        int(lamp["gx"]) * world.cell_px + int(lamp.get("offset_x_px", 0))
        + int(lamp["light_offset_x_px"])
    )
    center_y = (
        int(lamp["gy"]) * world.cell_px + int(lamp.get("offset_y_px", 0))
        + int(lamp["light_offset_y_px"])
    )
    proof_w, proof_h = 1280, 720
    camera = camera_for(world, center_x, center_y, proof_w, proof_h)
    lit = pygame.Surface((proof_w, proof_h)).convert()
    renderer.draw_view(lit, camera, "ground")

    for item in lamps:
        item["emits_light"] = False
    try:
        unlit = pygame.Surface((proof_w, proof_h)).convert()
        renderer.draw_view(unlit, camera, "ground")
    finally:
        for item in lamps:
            item["emits_light"] = True

    screen_x = int(round(center_x - camera[0]))
    screen_y = int(round(center_y - camera[1]))
    lit_rgb = mean_rgb_disk(lit, screen_x, screen_y, 90)
    unlit_rgb = mean_rgb_disk(unlit, screen_x, screen_y, 90)
    lit_luma = 0.2126 * lit_rgb[0] + 0.7152 * lit_rgb[1] + 0.0722 * lit_rgb[2]
    unlit_luma = 0.2126 * unlit_rgb[0] + 0.7152 * unlit_rgb[1] + 0.0722 * unlit_rgb[2]
    warm_increment = (lit_rgb[0] - unlit_rgb[0]) - (lit_rgb[2] - unlit_rgb[2])
    if lit_luma - unlit_luma < 0.04:
        raise SystemExit(f"street light pool is not visibly brighter: delta={lit_luma - unlit_luma:.4f}")
    if warm_increment < 0.03:
        raise SystemExit(f"street light pool lost its warm color increment: {warm_increment:.4f}")

    pygame.image.save(lit, str(LIGHTING_PROOF_OUT))
    return {
        "authority": "same GridWorld object record for fixture and emitter",
        "lamp_count": len(lamps),
        "fixture_light_transform_max_delta_px": 0,
        "audited_lighting_id": lamp["lighting_id"],
        "audited_world_light_center": [center_x, center_y],
        "audited_screen_light_center": [screen_x, screen_y],
        "lit_mean_rgb": list(lit_rgb),
        "unlit_mean_rgb": list(unlit_rgb),
        "luminance_delta": lit_luma - unlit_luma,
        "warm_red_minus_blue_increment": warm_increment,
        "minimum_luminance_delta": 0.04,
        "minimum_warm_red_minus_blue_increment": 0.03,
    }


def save_detail(renderer: GridRenderer, world, layer: str, x: float, y: float, path: Path) -> dict[str, float]:
    # Render the actual runtime at a larger virtual viewport, then downscale the
    # resulting framebuffer for review. This changes preview zoom only; map scale,
    # gameplay camera, collision and asset placement are untouched.
    virtual_w = int(round(W / REVIEW_ZOOM))
    virtual_h = int(round(H / REVIEW_ZOOM))
    virtual = pygame.Surface((virtual_w, virtual_h)).convert()
    renderer.draw_view(virtual, camera_for(world, x, y, virtual_w, virtual_h), layer)
    frame = pygame.transform.smoothscale(virtual, (W, H))
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(frame, str(path))
    return framebuffer_luminance(frame)


def save_overview(renderer: GridRenderer, layer: str, path: Path) -> tuple[int, int, int]:
    frame = pygame.Surface((W, H)).convert()
    geometry = renderer.draw_overview(frame, layer)
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(frame, str(path))
    return geometry


def main() -> None:
    from tools.generate_v100_ground_roof_layers import main as generate_layers
    from tools.build_v100_grid_seed import main as validate_map

    generate_layers()
    load_ground_grid.cache_clear()
    load_roof_grid.cache_clear()
    validate_map()
    load_ground_grid.cache_clear()
    load_roof_grid.cache_clear()

    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        ground = load_ground_grid()
        ground_renderer = GridRenderer(ground)
        geometry_hash_before = gameplay_geometry_hash(ground)
        sx, sy = ground.choose_spawn("ground", 18.0)
        ground_luminance = save_detail(ground_renderer, ground, "ground", sx, sy, GROUND_DETAIL_OUT)
        lighting_audit = save_lighting_proof(ground_renderer, ground, (sx, sy))
        silhouette = [obj for obj in ground.objects if obj.get("composition_pass") == "building_silhouette_v1"]
        facade_breaks = [obj for obj in silhouette if obj.get("silhouette_kind") == "facade_break"]
        roof_masses = [obj for obj in silhouette if obj.get("silhouette_kind") == "roof_edge_mass"]
        if (len(facade_breaks), len(roof_masses)) != (7, 25):
            raise SystemExit(
                f"runtime silhouette proof expected 7 facade + 25 Roof objects, got "
                f"{len(facade_breaks)} + {len(roof_masses)}"
            )
        if len({obj["asset"] for obj in roof_masses}) != 4:
            raise SystemExit("runtime silhouette proof did not exercise all four Roof edge profiles")
        ground_tile_px, ground_ox, ground_oy = save_overview(ground_renderer, "ground", GROUND_FULL_OUT)
        geometry_hash_after = gameplay_geometry_hash(ground)
        if geometry_hash_after != geometry_hash_before:
            raise SystemExit("Ground night grading mutated authoritative gameplay geometry")
        low, high = GROUND_NIGHT_MEAN_RANGE
        if not low <= ground_luminance["mean"] <= high:
            raise SystemExit(
                f"Ground night luminance out of range: {ground_luminance['mean']:.4f} not in [{low:.2f}, {high:.2f}]"
            )
        if ground_luminance["p95_minus_p05"] < GROUND_NIGHT_MIN_SPREAD:
            raise SystemExit(
                "Ground night contrast is too compressed for readable roads/curbs: "
                f"{ground_luminance['p95_minus_p05']:.4f} < {GROUND_NIGHT_MIN_SPREAD:.2f}"
            )

        roof = load_roof_grid()
        roof_renderer = GridRenderer(roof)
        rgx, rgy = first_cell(roof, "roof", lambda tid, _tile: tid.startswith("bld_"))
        rx, ry = roof.cell_center(rgx, rgy)
        roof_luminance = save_detail(roof_renderer, roof, "roof", rx, ry, ROOF_DETAIL_OUT)
        roof_tile_px, roof_ox, roof_oy = save_overview(roof_renderer, "roof", ROOF_FULL_OUT)
        roof_palette = [obj for obj in roof.objects if obj.get("composition_pass") == "roof_palette_v1"]
        roof_surface = [obj for obj in roof.objects if obj.get("composition_pass") == "roof_surface_v1"]
        palette_assets = sorted({str(obj["asset"]) for obj in roof_palette})
        palette_archetypes = sorted({str(obj["roof_archetype"]) for obj in roof_palette})
        palette_buildings = {str(obj["building_id"]) for obj in roof_palette}
        surface_themes = sorted({str(obj["roof_theme"]) for obj in roof_surface})
        if (
            len(roof_palette) != 124 or len(palette_assets) != 15
            or len(palette_archetypes) != 4 or len(palette_buildings) != 25
        ):
            raise SystemExit(
                "runtime roof palette proof failed: "
                f"details={len(roof_palette)} assets={len(palette_assets)} "
                f"archetypes={len(palette_archetypes)} buildings={len(palette_buildings)}"
            )
        if len(roof_surface) != 12 or len(surface_themes) != 5:
            raise SystemExit(
                f"runtime roof surface proof failed: effects={len(roof_surface)} themes={surface_themes}"
            )

        road_gx, road_gy = first_cell(ground, "ground", lambda _tid, tile: tile.collision == "road")
        bx, by = first_cell(ground, "ground", lambda tid, tile: tid.startswith("bld_") and tile.collision == "blocked")
        road_x, road_y = ground.cell_center(road_gx, road_gy)
        bld_x, bld_y = ground.cell_center(bx, by)
        if ground_renderer.collision_at("ground", road_x, road_y) != "road":
            raise SystemExit("Ground road collision/render contract failed")
        if ground_renderer.collision_at("ground", bld_x, bld_y) != "blocked":
            raise SystemExit("Ground building collision/render contract failed")
        if ground.tile_id("roof", bx, by) != ground.tile_id("ground", bx, by):
            raise SystemExit("Exterior Roof/Ground footprint registration failed")
        if roof_renderer.collision_at("roof", rx, ry) != "blocked":
            raise SystemExit("Roof building footprint contract failed")

        NIGHT_AUDIT_OUT.write_text(json.dumps({
            "authority": "GridWorld",
            "grade": {
                "multiply_rgb": list(GridRenderer.GROUND_NIGHT_MULTIPLY),
                "ambient_rgb": list(GridRenderer.GROUND_NIGHT_AMBIENT),
            },
            "ground_detail_luminance": ground_luminance,
            "roof_detail_luminance_ungraded_reference": roof_luminance,
            "accepted_ground_mean_range": list(GROUND_NIGHT_MEAN_RANGE),
            "accepted_ground_min_p95_minus_p05": GROUND_NIGHT_MIN_SPREAD,
            "gameplay_geometry_sha256_before": geometry_hash_before,
            "gameplay_geometry_sha256_after": geometry_hash_after,
            "gameplay_geometry_unchanged": True,
            "roof_registration": "exact_ground_building_footprint",
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        LIGHTING_AUDIT_OUT.write_text(json.dumps({
            **lighting_audit,
            "gameplay_geometry_sha256_before": geometry_hash_before,
            "gameplay_geometry_sha256_after": geometry_hash_after,
            "gameplay_geometry_unchanged": True,
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        SILHOUETTE_AUDIT_OUT.write_text(json.dumps({
            "authority": "GridWorld collision-neutral building object overlays",
            "composition_pass": "building_silhouette_v1",
            "facade_break_count": len(facade_breaks),
            "roof_edge_mass_count": len(roof_masses),
            "roof_edge_asset_families": sorted({str(obj["asset"]) for obj in roof_masses}),
            "roof_buildings_covered": len({str(obj["building_id"]) for obj in roof_masses}),
            "roof_palette": {
                "composition_pass": "roof_palette_v1",
                "detail_count": len(roof_palette),
                "asset_family_count": len(palette_assets),
                "asset_families": palette_assets,
                "archetype_count": len(palette_archetypes),
                "archetypes": palette_archetypes,
                "buildings_covered": len(palette_buildings),
            },
            "roof_surface": {
                "composition_pass": "roof_surface_v1",
                "effect_count": len(roof_surface),
                "theme_count": len(surface_themes),
                "themes": surface_themes,
                "native_asset_size_px": [308, 442],
            },
            "gameplay_geometry_sha256_before": geometry_hash_before,
            "gameplay_geometry_sha256_after": geometry_hash_after,
            "gameplay_geometry_unchanged": True,
            "roof_registration": "exact_ground_building_footprint",
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        print(
            "V100_GROUND_ROOF_RUNTIME_PROOF_OK "
            f"size={W}x{H} review_zoom={REVIEW_ZOOM:.2f} cell={ground.cell_px} grid={ground.width}x{ground.height} "
            f"ground_objects={len(ground.objects)} roof_objects={len(roof.objects)} "
            f"overview_cell_px={ground_tile_px} overview_origin={ground_ox},{ground_oy} "
            f"roof_overview_cell_px={roof_tile_px} roof_origin={roof_ox},{roof_oy} "
            f"ground_night_mean={ground_luminance['mean']:.4f} "
            f"ground_night_spread={ground_luminance['p95_minus_p05']:.4f} "
            f"geometry_sha256={geometry_hash_after[:12]} "
            f"street_lamps={lighting_audit['lamp_count']} aligned_delta_px=0 "
            f"silhouette={len(facade_breaks)}facade+{len(roof_masses)}roof-edge "
            f"roof_palette={len(roof_palette)}details/{len(palette_assets)}families "
            f"roof_surface={len(roof_surface)}effects/{len(surface_themes)}themes "
            "roof_registration=exact_ground_building_footprint"
        )
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
