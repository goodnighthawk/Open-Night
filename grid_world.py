from __future__ import annotations

from dataclasses import dataclass
import json
import math
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


@dataclass(frozen=True)
class ObjectDef:
    object_id: str
    image: str
    kind: str = "decoration"
    layer: str = "ground"
    z: int = 100
    native_width_px: int = 256
    native_height_px: int = 256


class TileCatalog:
    def __init__(self, entries: dict[str, TileDef], objects: dict[str, ObjectDef] | None = None):
        self.entries = entries
        self.objects = objects or {}

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
        objects: dict[str, ObjectDef] = {}
        for object_id, item in raw.get("objects", {}).items():
            objects[object_id] = ObjectDef(
                object_id=object_id,
                image=str(item["image"]),
                kind=str(item.get("kind", "decoration")),
                layer=str(item.get("layer", "ground")),
                z=int(item.get("z", 100)),
                native_width_px=int(item.get("native_width_px", GRID_CELL_PX)),
                native_height_px=int(item.get("native_height_px", GRID_CELL_PX)),
            )
        return cls(entries, objects)

    def __getitem__(self, tile_id: str) -> TileDef:
        return self.entries[tile_id]

    def object(self, object_id: str) -> ObjectDef:
        return self.objects[object_id]


class GridWorld:
    """Authoritative 256 px tile world shared by rendering and gameplay.

    Large visual objects are anchored to grid cells but never define collision:
    gameplay reads the surface cell beneath the object. This keeps the supplied
    city-block art and the server's collision contract in exactly one coordinate
    system without treating arbitrary image alpha as gameplay geometry.
    """

    def __init__(self, data: dict[str, Any], catalog: TileCatalog):
        self.data = data
        self.catalog = catalog
        self.cell_px = int(data.get("cell_px", GRID_CELL_PX))
        self.width = int(data.get("width", GRID_W))
        self.height = int(data.get("height", GRID_H))
        self.world_w = self.width * self.cell_px
        self.world_h = self.height * self.cell_px
        self.layers: dict[str, list[list[str]]] = data.get("layers", {})
        self.objects: list[dict[str, Any]] = list(data.get("objects", []))
        self.login_spawns: list[list[float]] = list(data.get("login_spawns", []))
        if self.cell_px != GRID_CELL_PX:
            raise ValueError(f"v1.0 grid requires {GRID_CELL_PX}px cells, got {self.cell_px}")
        if self.width != GRID_W or self.height != GRID_H:
            raise ValueError(f"v1.0 grid requires {GRID_W}x{GRID_H} cells, got {self.width}x{self.height}")
        for name, rows in self.layers.items():
            if len(rows) != self.height or any(len(row) != self.width for row in rows):
                raise ValueError(f"layer {name!r} is not {self.width}x{self.height}")
            for row in rows:
                for tile_id in row:
                    if tile_id not in self.catalog.entries:
                        raise ValueError(f"layer {name!r} references unknown tile {tile_id!r}")
        for obj in self.objects:
            oid = str(obj.get("asset", ""))
            if oid not in self.catalog.objects:
                raise ValueError(f"grid object references unknown asset {oid!r}")
            gx, gy = int(obj.get("gx", -1)), int(obj.get("gy", -1))
            if not self.in_bounds(gx, gy):
                raise ValueError(f"grid object {oid!r} anchor outside world: {(gx, gy)}")

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

    def cell_center(self, gx: int, gy: int) -> tuple[float, float]:
        return (gx + 0.5) * self.cell_px, (gy + 0.5) * self.cell_px

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

    def circle_walkable(self, layer: str, x: float, y: float, radius: float) -> bool:
        """Conservative player/collision probe against authoritative grid cells."""
        radius = max(0.0, float(radius))
        margin = 0.5
        if x - radius < margin or y - radius < margin or x + radius >= self.world_w - margin or y + radius >= self.world_h - margin:
            return False
        if not self.walkable_at(layer, x, y):
            return False
        if radius <= 0.0:
            return True
        # Cardinal + diagonal probes keep a circular player from clipping a blocked
        # building cell even though the cell center itself remains on pavement.
        diag = radius * 0.7071067811865476
        probes = (
            (radius, 0.0), (-radius, 0.0), (0.0, radius), (0.0, -radius),
            (diag, diag), (diag, -diag), (-diag, diag), (-diag, -diag),
        )
        return all(self.walkable_at(layer, x + ox, y + oy) for ox, oy in probes)

    def move_circle(
        self,
        layer: str,
        x: float,
        y: float,
        dx: float,
        dy: float,
        radius: float,
        *,
        max_step: float | None = None,
    ) -> tuple[float, float]:
        """Substepped axis-separated movement using the same cells as rendering."""
        x, y, dx, dy = map(float, (x, y, dx, dy))
        distance = max(abs(dx), abs(dy))
        step_limit = max(8.0, min(self.cell_px / 4.0, float(max_step or self.cell_px / 4.0)))
        steps = max(1, int(math.ceil(distance / step_limit)))
        sx, sy = dx / steps, dy / steps
        for _ in range(steps):
            nx = x + sx
            if self.circle_walkable(layer, nx, y, radius):
                x = nx
            ny = y + sy
            if self.circle_walkable(layer, x, ny, radius):
                y = ny
        return x, y

    def nearest_walkable(self, layer: str, x: float, y: float, radius: float) -> tuple[float, float]:
        if self.circle_walkable(layer, x, y, radius):
            return float(x), float(y)
        start_gx, start_gy = self.world_to_cell(x, y)
        max_ring = max(self.width, self.height)
        for ring in range(max_ring + 1):
            candidates: list[tuple[int, int]] = []
            for gx in range(start_gx - ring, start_gx + ring + 1):
                candidates.append((gx, start_gy - ring))
                candidates.append((gx, start_gy + ring))
            for gy in range(start_gy - ring + 1, start_gy + ring):
                candidates.append((start_gx - ring, gy))
                candidates.append((start_gx + ring, gy))
            for gx, gy in candidates:
                if not self.in_bounds(gx, gy):
                    continue
                cx, cy = self.cell_center(gx, gy)
                if self.circle_walkable(layer, cx, cy, radius):
                    return cx, cy
        raise RuntimeError("grid map contains no walkable spawn cell")

    def choose_spawn(self, layer: str = "ground", radius: float = 18.0) -> tuple[float, float]:
        for raw in self.login_spawns:
            try:
                x, y = float(raw[0]), float(raw[1])
            except (TypeError, ValueError, IndexError):
                continue
            if self.circle_walkable(layer, x, y, radius):
                return x, y
        cx, cy = self.cell_center(self.width // 2, self.height // 2)
        return self.nearest_walkable(layer, cx, cy, radius)

    def visible_cells(self, camera_x: float, camera_y: float, width_px: int, height_px: int):
        gx0 = max(0, int(camera_x // self.cell_px))
        gy0 = max(0, int(camera_y // self.cell_px))
        gx1 = min(self.width - 1, int((camera_x + width_px) // self.cell_px))
        gy1 = min(self.height - 1, int((camera_y + height_px) // self.cell_px))
        for gy in range(gy0, gy1 + 1):
            for gx in range(gx0, gx1 + 1):
                yield gx, gy

    def visible_objects(self, camera_x: float, camera_y: float, width_px: int, height_px: int, layer: str):
        left, top = float(camera_x), float(camera_y)
        right, bottom = left + width_px, top + height_px
        visible = []
        for item in self.objects:
            asset_id = str(item["asset"])
            definition = self.catalog.object(asset_id)
            if definition.layer != layer:
                continue
            x, y = self.cell_to_world(int(item["gx"]), int(item["gy"]))
            width = int(item.get("width_px", definition.native_width_px))
            height = int(item.get("height_px", definition.native_height_px))
            if x < right and y < bottom and x + width > left and y + height > top:
                visible.append((definition.z, asset_id, item, x, y, width, height))
        visible.sort(key=lambda row: row[0])
        return visible
