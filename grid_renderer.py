from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path
import zipfile

import pygame

from grid_world import GridWorld

ROOT = Path(__file__).resolve().parent


class GridRenderer:
    """Direct renderer for the v1.0 authoritative 256 px grid.

    Ground art is loaded directly from the user-supplied ``city_block.zip`` via
    ``city_block://`` catalog URLs. This deliberately makes the original art pack
    the runtime tile/object vocabulary instead of extracting generic materials
    from it. Surface cells remain the collision authority; larger premade building
    sprites are grid-anchored objects over independently blocked footprint cells.
    """

    def __init__(self, world: GridWorld):
        self.world = world
        self._city_block_zip: zipfile.ZipFile | None = None
        self._city_block_zip_path: Path | None = None

    @staticmethod
    def city_block_zip_candidates() -> list[Path]:
        candidates: list[Path] = []
        configured = os.getenv("OPEN_NIGHT_CITY_BLOCK_ZIP", "").strip()
        if configured:
            candidates.append(Path(configured).expanduser())
        candidates.extend([
            ROOT / "city_block.zip",
            ROOT / "assets" / "grid_v100" / "city_block.zip",
            ROOT / "assets" / "source_packs" / "city_block.zip",
            ROOT.parent / "city_block.zip",
        ])
        # Preserve order while removing duplicates.
        unique: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = str(path.resolve()) if path.is_absolute() else str(path)
            if key not in seen:
                seen.add(key)
                unique.append(path)
        return unique

    def _open_city_block_zip(self) -> zipfile.ZipFile:
        if self._city_block_zip is not None:
            return self._city_block_zip
        for path in self.city_block_zip_candidates():
            if path.is_file():
                self._city_block_zip_path = path
                self._city_block_zip = zipfile.ZipFile(path, "r")
                return self._city_block_zip
        shown = "\n  - ".join(str(path) for path in self.city_block_zip_candidates())
        raise FileNotFoundError(
            "Open Night grid runtime requires the original city_block.zip. "
            "Place it in the game folder, assets/grid_v100/, or set "
            f"OPEN_NIGHT_CITY_BLOCK_ZIP. Checked:\n  - {shown}"
        )

    @lru_cache(maxsize=512)
    def _load_image(self, rel_path: str) -> pygame.Surface:
        if rel_path.startswith("city_block://"):
            member = rel_path[len("city_block://"):].lstrip("/")
            archive = self._open_city_block_zip()
            try:
                data = archive.read(member)
            except KeyError as exc:
                raise FileNotFoundError(
                    f"city_block.zip is missing runtime asset {member!r}"
                ) from exc
            # Name hint lets pygame/SDL_image choose the decoder without a temp file.
            return pygame.image.load(BytesIO(data), member).convert_alpha()

        path = ROOT / rel_path
        if not path.is_file():
            raise FileNotFoundError(f"grid asset missing image {path}")
        return pygame.image.load(str(path)).convert_alpha()

    @lru_cache(maxsize=256)
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

    @lru_cache(maxsize=512)
    def _scaled_object_surface(self, asset_id: str, width: int, height: int) -> pygame.Surface:
        definition = self.world.catalog.object(asset_id)
        image = self._load_image(definition.image)
        if image.get_size() != (width, height):
            image = pygame.transform.smoothscale(image, (max(1, width), max(1, height)))
        return image

    def _object_surface(self, asset_id: str, width: int, height: int, rotation: float = 0.0) -> pygame.Surface:
        image = self._scaled_object_surface(asset_id, width, height)
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
