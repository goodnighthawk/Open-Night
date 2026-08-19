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

        print(
            "V100_GROUND_ROOF_RUNTIME_PROOF_OK "
            f"size={W}x{H} review_zoom={REVIEW_ZOOM:.2f} cell={ground.cell_px} grid={ground.width}x{ground.height} "
            f"ground_objects={len(ground.objects)} roof_objects={len(roof.objects)} "
            f"overview_cell_px={ground_tile_px} overview_origin={ground_ox},{ground_oy} "
            f"roof_overview_cell_px={roof_tile_px} roof_origin={roof_ox},{roof_oy} "
            f"ground_night_mean={ground_luminance['mean']:.4f} "
            f"ground_night_spread={ground_luminance['p95_minus_p05']:.4f} "
            f"geometry_sha256={geometry_hash_after[:12]} "
            "roof_registration=exact_ground_building_footprint"
        )
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
