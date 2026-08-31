from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any

GRID_CELL_PX = 256
BASE_GRID_W = 64
GRID_W = 128
GRID_H = 48
GRID_WORLD_W = GRID_W * GRID_CELL_PX
GRID_WORLD_H = GRID_H * GRID_CELL_PX

# Open Night proof/world axes are fixed and unambiguous:
#   North = screen up, East = screen right, South = screen down, West = screen left
#   +x = East, +y = South
#
# User-verified reference:
# - all four straight pieces (top/bottom/left/right) are correct and locked.
# - only the *_outer corner pieces require translation.
# - the pack corner art needs a left/right mirror relative to world corner IDs so
#   its pavement quadrant joins the already-correct straight edges around a block.
# No curb sprite is rotated at render time.
CURB_WORLD_TO_PACK_IMAGE = {
    "curb_left": "city_block://road_and_pavement_tileset/curb_right_edge.png",
    "curb_right": "city_block://road_and_pavement_tileset/curb_left_edge.png",
    "curb_top": "city_block://road_and_pavement_tileset/curb_bottom_center.png",
    "curb_bottom": "city_block://road_and_pavement_tileset/curb_top_center.png",
    # These native 256px corner cells match the grid exactly. The 512px
    # circle_* art is a two-cell plaza curve and must never be squeezed into a
    # single curb cell. Pack names identify the bright pavement quadrant after
    # the established left/right translation: TL world -> bottom-right art.
    "curb_tl_outer": "city_block://road_and_pavement_tileset/curb_top_right_outer.png",
    "curb_tr_outer": "city_block://road_and_pavement_tileset/curb_top_left_outer.png",
    "curb_bl_outer": "city_block://road_and_pavement_tileset/curb_bottom_right_outer.png",
    "curb_br_outer": "city_block://road_and_pavement_tileset/curb_bottom_left_outer.png",
}


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
        return self.collision in {"walk", "road", "sidewalk", "interior", "transition", "wade"}


@dataclass(frozen=True)
class ObjectDef:
    object_id: str
    image: str
    kind: str = "decoration"
    layer: str = "ground"
    z: int = 100
    native_width_px: int = 256
    native_height_px: int = 256
    pivot_x_px: int = 0
    pivot_y_px: int = 0
    optional: bool = False


class TileCatalog:
    def __init__(self, entries: dict[str, TileDef], objects: dict[str, ObjectDef] | None = None):
        self.entries = entries
        self.objects = objects or {}

    @classmethod
    def load(cls, path: str | Path) -> "TileCatalog":
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        # The modular 256 px building kit is kept in a companion catalog so the
        # main object catalog stays readable while still making city_block tiles
        # first-class collision/render cells.
        for extra_name in (
            "building_tiles.json",
            "generated_art_tiles.json",
            "generated_building_tiles.json",
            "generated_surface_tiles.json",
            "generated_transition_objects.json",
        ):
            extra_path = path.with_name(extra_name)
            if extra_path.is_file():
                extra = json.loads(extra_path.read_text(encoding="utf-8"))
                raw.setdefault("tiles", {}).update(extra.get("tiles", {}))
                raw.setdefault("objects", {}).update(extra.get("objects", {}))

        # Centralized orientation translation: map authors use world compass
        # semantics, while the pack image names are converted here exactly once.
        for tile_id, image in CURB_WORLD_TO_PACK_IMAGE.items():
            if (
                tile_id in raw.get("tiles", {})
                and str(raw["tiles"][tile_id].get("image", "")).startswith("city_block://")
            ):
                raw["tiles"][tile_id]["image"] = image

        entries = {
            tile_id: TileDef(
                tile_id=tile_id,
                image=str(item["image"]),
                collision=str(item.get("collision", "blocked")),
                kind=str(item.get("kind", "surface")),
                layer=str(item.get("layer", "ground")),
                z=int(item.get("z", 0)),
            )
            for tile_id, item in raw["tiles"].items()
        }
        objects = {
            object_id: ObjectDef(
                object_id=object_id,
                image=str(item["image"]),
                kind=str(item.get("kind", "decoration")),
                layer=str(item.get("layer", "ground")),
                z=int(item.get("z", 100)),
                native_width_px=int(item.get("native_width_px", GRID_CELL_PX)),
                native_height_px=int(item.get("native_height_px", GRID_CELL_PX)),
                pivot_x_px=int(item.get("pivot_x_px", 0)),
                pivot_y_px=int(item.get("pivot_y_px", 0)),
                optional=bool(item.get("optional", False)),
            )
            for object_id, item in raw.get("objects", {}).items()
        }
        return cls(entries, objects)

    def __getitem__(self, tile_id: str) -> TileDef:
        return self.entries[tile_id]

    def object(self, object_id: str) -> ObjectDef:
        return self.objects[object_id]


class GridWorld:
    """Authoritative 256 px tile world shared by rendering and gameplay.

    The map may store layers either as explicit tile-id matrices or compact ASCII
    rows plus a legend. Large visual objects are anchored to grid cells but never
    define collision: gameplay reads the surface cell beneath each object.
    """

    def __init__(self, data: dict[str, Any], catalog: TileCatalog):
        self.data = data
        self.catalog = catalog
        self.cell_px = int(data.get("cell_px", GRID_CELL_PX))
        self.width = int(data.get("width", GRID_W))
        self.height = int(data.get("height", GRID_H))
        self.world_w = self.width * self.cell_px
        self.world_h = self.height * self.cell_px
        self.layers = self._decode_layers(data)
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

    def _decode_layers(self, data: dict[str, Any]) -> dict[str, list[list[str]]]:
        explicit = data.get("layers")
        if explicit:
            return {str(name): [list(row) for row in rows] for name, rows in explicit.items()}
        ascii_layers = data.get("layers_ascii") or {}
        legend = {str(code): str(tile_id) for code, tile_id in (data.get("tile_legend") or {}).items()}
        if not ascii_layers:
            return {}
        if not legend:
            raise ValueError("layers_ascii requires tile_legend")
        layers: dict[str, list[list[str]]] = {}
        for name, source_rows in ascii_layers.items():
            rows: list[list[str]] = []
            for source in source_rows:
                text = str(source)
                if len(text) != self.width:
                    raise ValueError(f"ASCII layer {name!r} row has width {len(text)}, expected {self.width}")
                try:
                    rows.append([legend[ch] for ch in text])
                except KeyError as exc:
                    raise ValueError(f"ASCII layer {name!r} uses unknown tile code {exc.args[0]!r}") from exc
            layers[str(name)] = rows
        return layers

    @classmethod
    def load(cls, map_path: str | Path, catalog_path: str | Path) -> "GridWorld":
        return cls(json.loads(Path(map_path).read_text(encoding="utf-8")), TileCatalog.load(catalog_path))

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
        return "void" if rows is None else rows[gy][gx]

    def tile(self, layer: str, gx: int, gy: int) -> TileDef:
        return self.catalog[self.tile_id(layer, gx, gy)]

    def collision_at(self, layer: str, x: float, y: float) -> str:
        gx, gy = self.world_to_cell(x, y)
        return self.tile(layer, gx, gy).collision

    def walkable_at(self, layer: str, x: float, y: float) -> bool:
        gx, gy = self.world_to_cell(x, y)
        return self.tile(layer, gx, gy).walkable

    def vehicle_drivable_at(self, x: float, y: float) -> bool:
        """Vehicles remain restricted to authored road collision cells."""
        return self.collision_at("ground", x, y) == "road"

    def circle_walkable(self, layer: str, x: float, y: float, radius: float) -> bool:
        radius = max(0.0, float(radius))
        margin = 0.5
        if x - radius < margin or y - radius < margin or x + radius >= self.world_w - margin or y + radius >= self.world_h - margin:
            return False
        if not self.walkable_at(layer, x, y):
            return False
        if layer == "ground" and self.object_collision_at(x, y, radius):
            return False
        if radius <= 0.0:
            return True
        diag = radius * 0.7071067811865476
        probes = ((radius,0.0),(-radius,0.0),(0.0,radius),(0.0,-radius),(diag,diag),(diag,-diag),(-diag,diag),(-diag,-diag))
        return all(self.walkable_at(layer, x + ox, y + oy) for ox, oy in probes)

    def object_collision_circles(self) -> tuple[tuple[float, float, float, str], ...]:
        """Return current collision-enabled prop circles in world coordinates."""
        cached = getattr(self, "_object_collision_cache", None)
        if cached is not None and getattr(self, "_object_collision_cache_count", -1) == len(self.objects):
            return cached
        circles = []
        for item in self.objects:
            radius = max(0.0, float(item.get("collision_radius_px", 0.0)))
            if radius <= 0.0:
                continue
            definition = self.catalog.object(str(item["asset"]))
            width = float(item.get("width_px", definition.native_width_px))
            height = float(item.get("height_px", definition.native_height_px))
            x = int(item["gx"]) * self.cell_px + float(item.get("offset_x_px", 0.0)) + width * 0.5
            y = int(item["gy"]) * self.cell_px + float(item.get("offset_y_px", 0.0)) + height * 0.5
            circles.append((x, y, radius, str(item.get("collision_kind", item.get("asset", "prop")))))
        result = tuple(circles)
        self._object_collision_cache = result
        self._object_collision_cache_count = len(self.objects)
        return result

    def object_collision_at(self, x: float, y: float, radius: float = 0.0) -> bool:
        radius = max(0.0, float(radius))
        return any(
            (float(x) - cx) ** 2 + (float(y) - cy) ** 2 < (radius + prop_radius) ** 2
            for cx, cy, prop_radius, _kind in self.object_collision_circles()
        )

    def object_interaction_point(self, item: dict[str, Any]) -> tuple[float, float]:
        """Resolve an interaction zone independently from art and collision."""
        definition = self.catalog.object(str(item["asset"]))
        width = float(item.get("width_px", definition.native_width_px))
        height = float(item.get("height_px", definition.native_height_px))
        left = int(item["gx"]) * self.cell_px + float(item.get("offset_x_px", 0.0))
        top = int(item["gy"]) * self.cell_px + float(item.get("offset_y_px", 0.0))
        return (
            left + float(item.get("interaction_offset_x_px", width * 0.5)),
            top + float(item.get("interaction_offset_y_px", height * 0.5)),
        )

    def nearest_interaction(
        self,
        x: float,
        y: float,
        level: int,
        *,
        kinds: set[str] | None = None,
        max_distance: float | None = None,
    ) -> dict[str, Any] | None:
        """Return the nearest active data-authored trigger on the current level."""
        best: tuple[float, dict[str, Any]] | None = None
        for item in self.objects:
            kind = str(item.get("interaction_kind", "")).strip()
            if not kind or (kinds is not None and kind not in kinds):
                continue
            if int(item.get("interaction_level", 0)) != int(level):
                continue
            if not bool(item.get("interaction_active", True)):
                continue
            radius = float(item.get("interaction_radius_px", 72.0))
            if max_distance is not None:
                radius = min(radius, float(max_distance))
            ix, iy = self.object_interaction_point(item)
            distance = math.hypot(float(x) - ix, float(y) - iy)
            candidate = (distance, item)
            if distance <= radius and (best is None or distance < best[0]):
                best = candidate
        return None if best is None else best[1]

    def circle_spawnable(self, layer: str, x: float, y: float, radius: float) -> bool:
        """Accept safe login surfaces while rejecting roads and wading water."""
        if not self.circle_walkable(layer, x, y, radius):
            return False
        probes = ((0.0, 0.0), (radius, 0.0), (-radius, 0.0), (0.0, radius), (0.0, -radius))
        return all(self.collision_at(layer, x + ox, y + oy) not in {"road", "wade"} for ox, oy in probes)

    def move_circle(self, layer: str, x: float, y: float, dx: float, dy: float, radius: float, *, max_step: float | None = None) -> tuple[float, float]:
        x, y, dx, dy = map(float, (x, y, dx, dy))
        if layer == "ground" and (
            self.collision_at(layer, x, y) == "wade"
            or self.collision_at(layer, x + dx, y + dy) == "wade"
        ):
            dx *= 0.55
            dy *= 0.55
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
        for ring in range(max(self.width, self.height) + 1):
            candidates: list[tuple[int, int]] = []
            for gx in range(start_gx - ring, start_gx + ring + 1):
                candidates.extend(((gx, start_gy - ring), (gx, start_gy + ring)))
            for gy in range(start_gy - ring + 1, start_gy + ring):
                candidates.extend(((start_gx - ring, gy), (start_gx + ring, gy)))
            for gx, gy in candidates:
                if not self.in_bounds(gx, gy):
                    continue
                cx, cy = self.cell_center(gx, gy)
                if self.circle_walkable(layer, cx, cy, radius):
                    return cx, cy
        raise RuntimeError("grid map contains no walkable spawn cell")

    def choose_spawn(self, layer: str = "ground", radius: float = 18.0) -> tuple[float, float]:
        # A technically walkable corner is still a bad login location: it hides
        # the city in two directions and was the exact position in report #90.
        minimum_inset = self.cell_px * 3.0

        def away_from_world_edge(x: float, y: float) -> bool:
            return (
                minimum_inset <= x <= self.world_w - minimum_inset
                and minimum_inset <= y <= self.world_h - minimum_inset
            )

        for raw in self.login_spawns:
            try:
                x, y = float(raw[0]), float(raw[1])
            except (TypeError, ValueError, IndexError):
                continue
            if away_from_world_edge(x, y) and self.circle_spawnable(layer, x, y, radius):
                return x, y
        # Prefer the nearest authored sidewalk/pavement cell instead of falling
        # back to the center of a broad road band.
        inset_cells = 3
        for gy in range(inset_cells, self.height - inset_cells):
            for gx in range(inset_cells, self.width - inset_cells):
                cx, cy = self.cell_center(gx, gy)
                if self.circle_spawnable(layer, cx, cy, radius):
                    return cx, cy
        raise RuntimeError("grid map contains no non-road walkable spawn cell")

    def roof_walkable_at(self, x: float, y: float) -> bool:
        gx, gy = self.world_to_cell(x, y)
        return self.in_bounds(gx, gy) and self.tile_id("roof", gx, gy).startswith("bld_")

    def circle_roof_walkable(self, x: float, y: float, radius: float) -> bool:
        radius = max(0.0, float(radius))
        if x - radius < 0.5 or y - radius < 0.5 or x + radius >= self.world_w - 0.5 or y + radius >= self.world_h - 0.5:
            return False
        diag = radius * 0.7071067811865476
        probes = ((0.0, 0.0), (radius, 0.0), (-radius, 0.0), (0.0, radius), (0.0, -radius),
                  (diag, diag), (diag, -diag), (-diag, diag), (-diag, -diag))
        return all(self.roof_walkable_at(x + ox, y + oy) for ox, oy in probes)

    def move_circle_roof(self, x: float, y: float, dx: float, dy: float, radius: float) -> tuple[float, float]:
        x, y, dx, dy = map(float, (x, y, dx, dy))
        steps = max(1, int(math.ceil(max(abs(dx), abs(dy)) / max(8.0, self.cell_px / 4.0))))
        sx, sy = dx / steps, dy / steps
        for _ in range(steps):
            if self.circle_roof_walkable(x + sx, y, radius):
                x += sx
            if self.circle_roof_walkable(x, y + sy, radius):
                y += sy
        return x, y

    def fire_escape_transition(
        self, x: float, y: float, current_level: int, max_distance: float | None = None,
    ) -> tuple[int, float, float] | None:
        """Return the opposite endpoint of a nearby functional fire escape."""
        distance_limit = float(max_distance or max(72.0, self.cell_px * 0.82))
        best: tuple[float, int, float, float] | None = None
        edge_to_roof_delta = {
            "east": (-1, 0), "west": (1, 0), "south": (0, -1), "north": (0, 1),
        }
        for item in self.objects:
            if (
                str(item.get("asset", "")) not in {"placeholder_fire_escape", "fire_escape_ladder"}
                and str(item.get("interaction_kind", "")) != "fire_escape_ladder"
            ):
                continue
            gx, gy = int(item["gx"]), int(item["gy"])
            ground_x, ground_y = self.cell_center(gx, gy)
            dx, dy = edge_to_roof_delta.get(str(item.get("edge", "east")), (-1, 0))
            roof_gx, roof_gy = gx + dx, gy + dy
            if not self.tile_id("roof", roof_gx, roof_gy).startswith("bld_"):
                adjacent = [
                    (nx, ny) for nx, ny in ((gx - 1, gy), (gx + 1, gy), (gx, gy - 1), (gx, gy + 1))
                    if self.tile_id("roof", nx, ny).startswith("bld_")
                ]
                if not adjacent:
                    continue
                roof_gx, roof_gy = adjacent[0]
            roof_x, roof_y = self.cell_center(roof_gx, roof_gy)
            if int(current_level) == 0:
                distance = math.hypot(float(x) - ground_x, float(y) - ground_y)
                candidate = (distance, 1, roof_x, roof_y)
            elif int(current_level) == 1:
                distance = math.hypot(float(x) - roof_x, float(y) - roof_y)
                candidate = (distance, 0, ground_x, ground_y)
            else:
                continue
            if distance <= distance_limit and (best is None or candidate < best):
                best = candidate
        if best is None:
            return None
        _distance, next_level, target_x, target_y = best
        return next_level, target_x, target_y

    def visible_cells(self, camera_x: float, camera_y: float, width_px: int, height_px: int):
        gx0 = max(0, int(camera_x // self.cell_px)); gy0 = max(0, int(camera_y // self.cell_px))
        gx1 = min(self.width - 1, int((camera_x + width_px) // self.cell_px)); gy1 = min(self.height - 1, int((camera_y + height_px) // self.cell_px))
        for gy in range(gy0, gy1 + 1):
            for gx in range(gx0, gx1 + 1):
                yield gx, gy

    def visible_objects(self, camera_x: float, camera_y: float, width_px: int, height_px: int, layer: str):
        left, top = float(camera_x), float(camera_y); right, bottom = left + width_px, top + height_px
        visible = []
        for item in self.objects:
            asset_id = str(item["asset"]); definition = self.catalog.object(asset_id)
            if str(item.get("layer", definition.layer)) != layer:
                continue
            x, y = self.cell_to_world(int(item["gx"]), int(item["gy"]))
            # Grid anchors keep authored objects registered to collision cells,
            # while pixel offsets allow repeated details (notably zebra stripes)
            # to be positioned inside a 256 px cell without inventing fake tiles.
            x += int(item.get("offset_x_px", 0))
            y += int(item.get("offset_y_px", 0))
            width = int(item.get("width_px", definition.native_width_px)); height = int(item.get("height_px", definition.native_height_px))
            rotation = int(item.get("rotation", 0)) % 360
            visible_width, visible_height = (height, width) if rotation in {90, 270} else (width, height)
            if x < right and y < bottom and x + visible_width > left and y + visible_height > top:
                visible.append((definition.z, asset_id, item, x, y, width, height))
        visible.sort(key=lambda row: row[0])
        return visible
