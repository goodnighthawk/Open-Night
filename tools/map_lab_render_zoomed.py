#!/usr/bin/env python3
"""Building-scale Map Lab renderer.

The authoritative runtime remains 256 px/cell. Map Lab detail proofs deliberately
render at 0.25x screen scale so a 1280x720 proof shows about 20x11 world cells,
which is appropriate for judging several buildings, sidewalks, and roads together.
"""
from __future__ import annotations

import math
from pathlib import Path

import pygame

import map_lab_render as base
from grid_renderer import GridRenderer

DETAIL_ZOOM = 0.25


def _draw_zoomed_layer(
    renderer: GridRenderer,
    world,
    target: pygame.Surface,
    camera: tuple[float, float],
    layer: str,
    *,
    skip_void: bool = False,
) -> None:
    cam_x, cam_y = camera
    cell = world.cell_px
    view_world_w = target.get_width() / DETAIL_ZOOM
    view_world_h = target.get_height() / DETAIL_ZOOM
    tile_px = int(round(cell * DETAIL_ZOOM))

    for gx, gy in world.visible_cells(cam_x, cam_y, math.ceil(view_world_w), math.ceil(view_world_h)):
        tile_id = world.tile_id(layer, gx, gy)
        if skip_void and tile_id == "void":
            continue
        image = renderer._tile_surface_scaled(tile_id, tile_px)
        sx = int(round((gx * cell - cam_x) * DETAIL_ZOOM))
        sy = int(round((gy * cell - cam_y) * DETAIL_ZOOM))
        target.blit(image, (sx, sy))


def _save_detail(
    renderer: GridRenderer,
    world,
    layer: str,
    center: tuple[float, float],
    path: Path,
) -> None:
    frame = pygame.Surface(base.DETAIL_SIZE).convert()
    frame.fill((12, 12, 14))

    view_world_size = (
        base.DETAIL_SIZE[0] / DETAIL_ZOOM,
        base.DETAIL_SIZE[1] / DETAIL_ZOOM,
    )
    camera = base._camera_for(world, center[0], center[1], view_world_size)
    cam_x, cam_y = camera

    _draw_zoomed_layer(renderer, world, frame, camera, layer)

    object_layers = (layer,)
    if layer == "ground" and "roof" in world.layers:
        _draw_zoomed_layer(renderer, world, frame, camera, "roof", skip_void=True)
        object_layers = ("ground", "roof")

    for _z, asset_id, item, world_x, world_y, width, height in renderer._visible_objects_for_layers(
        camera,
        math.ceil(view_world_size[0]),
        math.ceil(view_world_size[1]),
        object_layers,
    ):
        rotation = float(item.get("rotation", 0.0))
        image = renderer._object_surface(asset_id, width, height, rotation)
        sw = max(1, int(round(image.get_width() * DETAIL_ZOOM)))
        sh = max(1, int(round(image.get_height() * DETAIL_ZOOM)))
        image = pygame.transform.scale(image, (sw, sh))
        sx = int(round((world_x - cam_x) * DETAIL_ZOOM))
        sy = int(round((world_y - cam_y) * DETAIL_ZOOM))
        frame.blit(image, (sx, sy))

    renderer._draw_proof_compass(frame)

    font = pygame.font.Font(None, 24)
    label = font.render(
        f"Map Lab preview: {DETAIL_ZOOM:.2f}x  |  ~{base.DETAIL_SIZE[0] / (world.cell_px * DETAIL_ZOOM):.0f} cells across",
        True,
        (245, 247, 250),
    )
    panel = pygame.Surface((label.get_width() + 18, label.get_height() + 12), pygame.SRCALPHA)
    panel.fill((14, 17, 22, 210))
    panel.blit(label, (9, 6))
    frame.blit(panel, (12, frame.get_height() - panel.get_height() - 12))

    pygame.image.save(frame, str(path))


def main() -> None:
    # Make the first thing in the browser a useful gameplay-scale Ground proof,
    # rather than the entire-map overview or an unscaled 1:1 crop.
    base.PROOFS = (
        ("Ground — gameplay scale / building cluster", "GROUND_BUILDING.png"),
        ("Ground — gameplay scale / intersection", "GROUND_INTERSECTION.png"),
        ("Ground — full map overview", "GROUND_FULL.png"),
        ("Roof — same building cluster", "ROOF_BUILDING.png"),
        ("Roof — full map overview", "ROOF_FULL.png"),
        ("Tile orientation test", "TILE_ORIENTATION_TEST.png"),
        ("Previous/current difference", "GROUND_DIFF.png"),
    )
    base._save_detail = _save_detail
    base.main()


if __name__ == "__main__":
    main()
