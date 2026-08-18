from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pygame

from grid_world import GridWorld

ROOT = Path(__file__).resolve().parent


class GridRenderer:
    """Direct renderer for the v1.0 authoritative 256 px grid.

    One-cell surface tiles are drawn at native grid scale. Larger city-block assets
    (premade buildings, roof decorations, markings) are grid-anchored objects and
    retain their authored pixel dimensions unless an explicit size is supplied.
    """

    def __init__(self, world: GridWorld):
        self.world = world

    @lru_cache(maxsize=256)
    def _load_image(self, rel_path: str) -> pygame.Surface:
        path = ROOT / rel_path
        if not path.is_file():
            raise FileNotFoundError(f"grid asset missing image {path}")
        return pygame.image.load(str(path)).convert_alpha()

    @lru_cache(maxsize=128)
    def _tile_surface(self, tile_id: str) -> pygame.Surface:
        tile = self.world.catalog[tile_id]
        if not tile.image:
            surf = pygame.Surface((self.world.cell_px, self.world.cell_px)).convert()
            surf.fill((12, 12, 14))
            return surf
        image = self._load_image(tile.image)
        if image.get_size() != (self.world.cell_px, self.world.cell_px):
            image = pygame.transform.smoothscale(image, (self.world.cell_px, self.world.cell_px))
        return image

    def _object_surface(self, asset_id: str, width: int, height: int, rotation: float = 0.0) -> pygame.Surface:
        definition = self.world.catalog.object(asset_id)
        image = self._load_image(definition.image)
        if image.get_size() != (width, height):
            image = pygame.transform.smoothscale(image, (max(1, width), max(1, height)))
        if abs(float(rotation)) > 0.001:
            image = pygame.transform.rotate(image, -float(rotation))
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

        for _z, asset_id, item, world_x, world_y, width, height in self.world.visible_objects(
            cam_x, cam_y, target.get_width(), target.get_height(), layer
        ):
            rotation = float(item.get("rotation", 0.0))
            image = self._object_surface(asset_id, width, height, rotation)
            target.blit(image, (int(world_x - cam_x), int(world_y - cam_y)))

    def collision_at(self, layer: str, world_x: float, world_y: float) -> str:
        return self.world.collision_at(layer, world_x, world_y)

    def walkable_at(self, layer: str, world_x: float, world_y: float) -> bool:
        return self.world.walkable_at(layer, world_x, world_y)
