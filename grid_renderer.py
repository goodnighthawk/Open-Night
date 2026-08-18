from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path
import zipfile

import pygame

from grid_world import GridWorld

ROOT = Path(__file__).resolve().parent
CITY_BLOCK_DIR = ROOT / "assets" / "source_packs" / "city_block"


class GridRenderer:
    """Direct renderer for the authoritative 256 px grid.

    Ground/exterior rendering automatically composites the registered Roof layer
    over building cells using the exact same grid coordinates and camera transform.
    Collision remains Ground-authoritative.
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
            "Open Night grid runtime could not find a repo-resident city_block asset "
            "or the original city_block.zip fallback. Checked:\n  - " + shown
        )

    @lru_cache(maxsize=512)
    def _load_image(self, rel_path: str) -> pygame.Surface:
        if rel_path.startswith("city_block://"):
            member = rel_path[len("city_block://"):].lstrip("/")
            loose_path = CITY_BLOCK_DIR / member
            if loose_path.is_file():
                return pygame.image.load(str(loose_path)).convert_alpha()
            archive = self._open_city_block_zip()
            try:
                data = archive.read(member)
            except KeyError as exc:
                raise FileNotFoundError(f"city_block source is missing runtime asset {member!r}") from exc
            return pygame.image.load(BytesIO(data), member).convert_alpha()

        path = ROOT / rel_path
        if not path.is_file():
            raise FileNotFoundError(f"grid asset missing image {path}")
        image = pygame.image.load(str(path)).convert_alpha()
        if path.suffix.lower() == ".ppm":
            image.set_colorkey((255, 0, 255))
        return image

    @staticmethod
    def _is_dark_building_outline(color: pygame.Color) -> bool:
        return color.a > 160 and max(color.r, color.g, color.b) < 70

    @classmethod
    def _suppress_building_perimeter_outline(cls, source: pygame.Surface) -> pygame.Surface:
        """Remove only the long near-black perimeter strokes from modular building tiles.

        The city_block modular floor pieces contain thick dark guide/perimeter lines.
        They become visually dominant when many pieces are synthesized into large
        rectangles.  Detect only dark rows/columns spanning >55% of a tile and
        inpaint those pixels from their nearest coloured neighbours. Short line art,
        wall seams, roof texture and props remain untouched.
        """
        image = source.copy()
        original = source.copy()
        width, height = image.get_size()
        dark_rows: list[list[bool]] = []
        row_counts: list[int] = []
        col_counts = [0] * width

        for y in range(height):
            row: list[bool] = []
            count = 0
            for x in range(width):
                is_dark = cls._is_dark_building_outline(original.get_at((x, y)))
                row.append(is_dark)
                if is_dark:
                    count += 1
                    col_counts[x] += 1
            dark_rows.append(row)
            row_counts.append(count)

        long_rows = {y for y, count in enumerate(row_counts) if count >= int(width * 0.55)}
        long_cols = {x for x, count in enumerate(col_counts) if count >= int(height * 0.55)}
        if not long_rows and not long_cols:
            return image

        max_search = max(12, int(max(width, height) * 0.08))
        for y in range(height):
            for x in range(width):
                if not dark_rows[y][x] or (y not in long_rows and x not in long_cols):
                    continue

                neighbours: list[pygame.Color] = []
                if y in long_rows:
                    for direction in (-1, 1):
                        for distance in range(1, max_search + 1):
                            yy = y + direction * distance
                            if not 0 <= yy < height:
                                break
                            candidate = original.get_at((x, yy))
                            if candidate.a > 160 and not cls._is_dark_building_outline(candidate):
                                neighbours.append(candidate)
                                break
                if x in long_cols:
                    for direction in (-1, 1):
                        for distance in range(1, max_search + 1):
                            xx = x + direction * distance
                            if not 0 <= xx < width:
                                break
                            candidate = original.get_at((xx, y))
                            if candidate.a > 160 and not cls._is_dark_building_outline(candidate):
                                neighbours.append(candidate)
                                break

                if neighbours:
                    count = len(neighbours)
                    image.set_at(
                        (x, y),
                        (
                            sum(c.r for c in neighbours) // count,
                            sum(c.g for c in neighbours) // count,
                            sum(c.b for c in neighbours) // count,
                            original.get_at((x, y)).a,
                        ),
                    )
        return image

    @lru_cache(maxsize=256)
    def _tile_surface(self, tile_id: str) -> pygame.Surface:
        tile = self.world.catalog[tile_id]
        if not tile.image:
            surf = pygame.Surface((self.world.cell_px, self.world.cell_px)).convert()
            surf.fill((12, 12, 14))
            return surf
        image = self._load_image(tile.image)
        if image.get_size() != (self.world.cell_px, self.world.cell_px):
            image = pygame.transform.scale(image, (self.world.cell_px, self.world.cell_px))
        if tile_id.startswith("bld_") and not tile_id.endswith("_fill"):
            image = self._suppress_building_perimeter_outline(image)
        return image

    @lru_cache(maxsize=1024)
    def _tile_surface_scaled(self, tile_id: str, size: int) -> pygame.Surface:
        image = self._tile_surface(tile_id)
        if image.get_size() == (size, size):
            return image
        return pygame.transform.scale(image, (max(1, size), max(1, size)))

    @lru_cache(maxsize=512)
    def _scaled_object_surface(self, asset_id: str, width: int, height: int) -> pygame.Surface:
        definition = self.world.catalog.object(asset_id)
        image = self._load_image(definition.image)
        if image.get_size() != (width, height):
            image = pygame.transform.scale(image, (max(1, width), max(1, height)))
        return image

    def _object_surface(self, asset_id: str, width: int, height: int, rotation: float = 0.0) -> pygame.Surface:
        image = self._scaled_object_surface(asset_id, width, height)
        if abs(float(rotation)) > 0.001:
            image = pygame.transform.rotate(image, -float(rotation))
        return image

    def _draw_cells(
        self,
        target: pygame.Surface,
        camera: tuple[float, float],
        layer: str,
        *,
        skip_void: bool = False,
    ) -> None:
        cam_x, cam_y = map(float, camera)
        cell = self.world.cell_px
        for gx, gy in self.world.visible_cells(cam_x, cam_y, target.get_width(), target.get_height()):
            tile_id = self.world.tile_id(layer, gx, gy)
            if skip_void and tile_id == "void":
                continue
            image = self._tile_surface(tile_id)
            target.blit(image, (int(gx * cell - cam_x), int(gy * cell - cam_y)))

    def _visible_objects_for_layers(
        self,
        camera: tuple[float, float],
        width: int,
        height: int,
        layers: tuple[str, ...],
    ):
        cam_x, cam_y = map(float, camera)
        rows = []
        for layer in layers:
            rows.extend(self.world.visible_objects(cam_x, cam_y, width, height, layer))
        rows.sort(key=lambda row: row[0])
        return rows

    def draw_view(self, target: pygame.Surface, camera: tuple[float, float], layer: str = "ground") -> None:
        """Draw a normal 1:1 gameplay framebuffer."""
        cam_x, cam_y = map(float, camera)
        target.fill((12, 12, 14))
        self._draw_cells(target, (cam_x, cam_y), layer)

        object_layers = (layer,)
        if layer == "ground" and "roof" in self.world.layers:
            # Roof is the visible top of every exterior building. It is never
            # independently positioned: only non-void roof cells are composited.
            self._draw_cells(target, (cam_x, cam_y), "roof", skip_void=True)
            object_layers = ("ground", "roof")

        for _z, asset_id, item, world_x, world_y, width, height in self._visible_objects_for_layers(
            (cam_x, cam_y), target.get_width(), target.get_height(), object_layers
        ):
            rotation = float(item.get("rotation", 0.0))
            image = self._object_surface(asset_id, width, height, rotation)
            target.blit(image, (int(world_x - cam_x), int(world_y - cam_y)))

    def draw_overview(self, target: pygame.Surface, layer: str = "ground") -> tuple[int, int, int]:
        """Render the entire map with integer-size preview cells.

        This is still the runtime renderer and source assets; it simply maps each
        authoritative cell to an integer number of preview pixels so the whole
        64x48 map is visible without fractional seams.
        """
        target.fill((12, 12, 14))
        tile_px = max(1, min(target.get_width() // self.world.width, target.get_height() // self.world.height))
        map_w = self.world.width * tile_px
        map_h = self.world.height * tile_px
        ox = (target.get_width() - map_w) // 2
        oy = (target.get_height() - map_h) // 2
        scale = tile_px / float(self.world.cell_px)

        def draw_layer_cells(name: str, skip_void: bool = False) -> None:
            for gy in range(self.world.height):
                for gx in range(self.world.width):
                    tile_id = self.world.tile_id(name, gx, gy)
                    if skip_void and tile_id == "void":
                        continue
                    target.blit(self._tile_surface_scaled(tile_id, tile_px), (ox + gx * tile_px, oy + gy * tile_px))

        draw_layer_cells(layer)
        object_layers = (layer,)
        if layer == "ground" and "roof" in self.world.layers:
            draw_layer_cells("roof", skip_void=True)
            object_layers = ("ground", "roof")

        for _z, asset_id, item, world_x, world_y, width, height in self._visible_objects_for_layers(
            (0.0, 0.0), self.world.world_w, self.world.world_h, object_layers
        ):
            rotation = float(item.get("rotation", 0.0))
            image = self._object_surface(asset_id, width, height, rotation)
            sw = max(1, int(round(image.get_width() * scale)))
            sh = max(1, int(round(image.get_height() * scale)))
            image = pygame.transform.scale(image, (sw, sh))
            sx = ox + int(round(world_x * scale))
            sy = oy + int(round(world_y * scale))
            target.blit(image, (sx, sy))

        return tile_px, ox, oy

    def collision_at(self, layer: str, world_x: float, world_y: float) -> str:
        return self.world.collision_at(layer, world_x, world_y)

    def walkable_at(self, layer: str, world_x: float, world_y: float) -> bool:
        return self.world.walkable_at(layer, world_x, world_y)
