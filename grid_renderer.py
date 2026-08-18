from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pygame

from grid_world import GridWorld

ROOT = Path(__file__).resolve().parent


class GridRenderer:
    """Direct tile renderer for the v1.0 authoritative 256 px grid."""

    def __init__(self, world: GridWorld):
        self.world = world

    @lru_cache(maxsize=128)
    def _tile_surface(self, tile_id: str) -> pygame.Surface:
        tile = self.world.catalog[tile_id]
        if not tile.image:
            surf = pygame.Surface((self.world.cell_px, self.world.cell_px)).convert()
            surf.fill((12, 12, 14))
            return surf
        path = ROOT / tile.image
        if not path.is_file():
            raise FileNotFoundError(f"grid tile {tile_id!r} missing image {path}")
        image = pygame.image.load(str(path)).convert_alpha()
        if image.get_size() != (self.world.cell_px, self.world.cell_px):
            image = pygame.transform.smoothscale(image, (self.world.cell_px, self.world.cell_px))
        return image

    def draw_view(self, target: pygame.Surface, camera: tuple[float, float], layer: str = "ground") -> None:
        cam_x, cam_y = map(float, camera)
        target.fill((12, 12, 14))
        cell = self.world.cell_px
        for gx, gy in self.world.visible_cells(cam_x, cam_y, target.get_width(), target.get_height()):
            tile_id = self.world.tile_id(layer, gx, gy)
            image = self._tile_surface(tile_id)
            sx = int(gx * cell - cam_x)
            sy = int(gy * cell - cam_y)
            target.blit(image, (sx, sy))

    def collision_at(self, layer: str, world_x: float, world_y: float) -> str:
        return self.world.collision_at(layer, world_x, world_y)

    def walkable_at(self, layer: str, world_x: float, world_y: float) -> bool:
        return self.world.walkable_at(layer, world_x, world_y)
