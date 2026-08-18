from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

GRID_CELL_PX = 256
GRID_W = 64
GRID_H = 48
GRID_WORLD_W = GRID_W * GRID_CELL_PX
GRID_WORLD_H = GRID_H * GRID_CELL_PX


@dataclass(frozen=True)
class TileDef:
    tile_id: str
    image: str
    collision: str = "blocked"
    kind: str = "surface"
    layer: str = "ground"
    z: int = 0

    @property
    def walkable(self) -> bool:
        return self.collision in {"walk", "road", "sidewalk", "interior", "transition"}


class TileCatalog:
    def __init__(self, entries: dict[str, TileDef]):
        self.entries = entries

    @classmethod
    def load(cls, path: str | Path) -> "TileCatalog":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        entries: dict[str, TileDef] = {}
        for tile_id, item in raw["tiles"].items():
            entries[tile_id] = TileDef(
                tile_id=tile_id,
                image=str(item["image"]),
                collision=str(item.get("collision", "blocked")),
                kind=str(item.get("kind", "surface")),
                layer=str(item.get("layer", "ground")),
                z=int(item.get("z", 0)),
            )
        return cls(entries)

    def __getitem__(self, tile_id: str) -> TileDef:
        return self.entries[tile_id]


class GridWorld:
    """Authoritative 256 px tile world.

    Rendering and gameplay query the same cell records. The old vector map may be
    used by migration tools but is not consulted by this class at runtime.
    """

    def __init__(self, data: dict[str, Any], catalog: TileCatalog):
        self.data = data
        self.catalog = catalog
        self.cell_px = int(data.get("cell_px", GRID_CELL_PX))
        self.width = int(data.get("width", GRID_W))
        self.height = int(data.get("height", GRID_H))
        self.layers: dict[str, list[list[str]]] = data.get("layers", {})
        self.objects: list[dict[str, Any]] = list(data.get("objects", []))
        if self.cell_px != GRID_CELL_PX:
            raise ValueError(f"v1.0 grid requires {GRID_CELL_PX}px cells, got {self.cell_px}")
        if self.width != GRID_W or self.height != GRID_H:
            raise ValueError(f"v1.0 grid requires {GRID_W}x{GRID_H} cells, got {self.width}x{self.height}")
        for name, rows in self.layers.items():
            if len(rows) != self.height or any(len(row) != self.width for row in rows):
                raise ValueError(f"layer {name!r} is not {self.width}x{self.height}")

    @classmethod
    def load(cls, map_path: str | Path, catalog_path: str | Path) -> "GridWorld":
        return cls(
            json.loads(Path(map_path).read_text(encoding="utf-8")),
            TileCatalog.load(catalog_path),
        )

    def in_bounds(self, gx: int, gy: int) -> bool:
        return 0 <= gx < self.width and 0 <= gy < self.height

    def world_to_cell(self, x: float, y: float) -> tuple[int, int]:
        return int(x // self.cell_px), int(y // self.cell_px)

    def cell_to_world(self, gx: int, gy: int) -> tuple[int, int]:
        return gx * self.cell_px, gy * self.cell_px

    def tile_id(self, layer: str, gx: int, gy: int) -> str:
        if not self.in_bounds(gx, gy):
            return "void"
        rows = self.layers.get(layer)
        if rows is None:
            return "void"
        return rows[gy][gx]

    def tile(self, layer: str, gx: int, gy: int) -> TileDef:
        return self.catalog[self.tile_id(layer, gx, gy)]

    def collision_at(self, layer: str, x: float, y: float) -> str:
        gx, gy = self.world_to_cell(x, y)
        return self.tile(layer, gx, gy).collision

    def walkable_at(self, layer: str, x: float, y: float) -> bool:
        gx, gy = self.world_to_cell(x, y)
        return self.tile(layer, gx, gy).walkable

    def visible_cells(self, camera_x: float, camera_y: float, width_px: int, height_px: int):
        gx0 = max(0, int(camera_x // self.cell_px))
        gy0 = max(0, int(camera_y // self.cell_px))
        gx1 = min(self.width - 1, int((camera_x + width_px) // self.cell_px))
        gy1 = min(self.height - 1, int((camera_y + height_px) // self.cell_px))
        for gy in range(gy0, gy1 + 1):
            for gx in range(gx0, gx1 + 1):
                yield gx, gy
