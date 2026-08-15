from __future__ import annotations

import csv
import hashlib
import math
import struct
import zlib
from collections import OrderedDict
from pathlib import Path
from typing import Iterable

GRID_VERSION = 2
DEFAULT_CELL_SIZE = 32

LAND        = 1 << 0
WATER       = 1 << 1
GRASS       = 1 << 2
ROAD        = 1 << 3
CURB        = 1 << 4
FURNISHING  = 1 << 5
SIDEWALK    = 1 << 6
FRONTAGE    = 1 << 7
BUILDING    = 1 << 8
CROSSWALK   = 1 << 9
BIKE        = 1 << 10
PARKING     = 1 << 11
WALKABLE    = 1 << 12
DRIVABLE    = 1 << 13
CYCLABLE    = 1 << 14
BRIDGE      = 1 << 15

LAYER_NAMES = {
    LAND: "land", WATER: "water", GRASS: "grass", ROAD: "road", CURB: "curb",
    FURNISHING: "furnishing", SIDEWALK: "sidewalk", FRONTAGE: "frontage",
    BUILDING: "building", CROSSWALK: "crosswalk", BIKE: "bike", PARKING: "parking",
    WALKABLE: "walkable", DRIVABLE: "drivable", CYCLABLE: "cyclable", BRIDGE: "bridge",
}



def chunk_column_name(index: int) -> str:
    """Spreadsheet-style column label: 0->A, 25->Z, 26->AA."""
    n = max(0, int(index)) + 1
    chars: list[str] = []
    while n:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(ord("A") + rem))
    return "".join(reversed(chars))


def chunk_label(cx: int, cy: int) -> str:
    """Human-readable chunk ID used everywhere in v1.5.1 (A1 origin top-left)."""
    return f"{chunk_column_name(int(cx))}{int(cy) + 1}"


def parse_chunk_label(label: str) -> tuple[int, int]:
    """Inverse of :func:`chunk_label`. Raises ValueError for malformed labels."""
    raw = str(label).strip().upper()
    if not raw:
        raise ValueError("empty chunk label")
    split = 0
    while split < len(raw) and raw[split].isalpha():
        split += 1
    letters, digits = raw[:split], raw[split:]
    if not letters or not digits or not digits.isdigit() or int(digits) < 1:
        raise ValueError(f"invalid chunk label: {label!r}")
    cx = 0
    for ch in letters:
        if ch < "A" or ch > "Z":
            raise ValueError(f"invalid chunk label: {label!r}")
        cx = cx * 26 + (ord(ch) - ord("A") + 1)
    return cx - 1, int(digits) - 1


def world_to_chunk_label(x: float, y: float, chunk_size: int = 1024) -> str:
    size = max(1, int(chunk_size))
    cx = int(max(0.0, float(x)) // size)
    cy = int(max(0.0, float(y)) // size)
    return chunk_label(cx, cy)

SOURCE_FILES = (
    "map.csv", "roads.csv", "road_points.csv", "buildings.csv", "building_visuals.csv",
    "water_polygons.csv", "green_polygons.csv", "crosswalks.csv", "bike_lanes.csv",
    "bike_lane_points.csv", "street_props.csv", "points.csv",
)


def source_fingerprint(folder: Path) -> str:
    h = hashlib.sha256()
    for name in SOURCE_FILES:
        path = Path(folder) / name
        h.update(name.encode("utf-8"))
        if path.exists():
            h.update(path.read_bytes())
    return h.hexdigest()


def _point_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    vx, vy = bx - ax, by - ay
    vv = vx * vx + vy * vy
    if vv <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / vv))
    qx, qy = ax + t * vx, ay + t * vy
    return math.hypot(px - qx, py - qy)


def _point_in_poly(x: float, y: float, poly: list[list[float]]) -> bool:
    if len(poly) < 3:
        return False
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = float(poly[i][0]), float(poly[i][1])
        xj, yj = float(poly[j][0]), float(poly[j][1])
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _cells_for_bbox(min_x: float, min_y: float, max_x: float, max_y: float, cell: int, cols: int, rows: int):
    gx0 = max(0, min(cols - 1, int(math.floor(min_x / cell))))
    gy0 = max(0, min(rows - 1, int(math.floor(min_y / cell))))
    gx1 = max(0, min(cols - 1, int(math.floor(max_x / cell))))
    gy1 = max(0, min(rows - 1, int(math.floor(max_y / cell))))
    for gy in range(gy0, gy1 + 1):
        cy = (gy + 0.5) * cell
        for gx in range(gx0, gx1 + 1):
            cx = (gx + 0.5) * cell
            yield gx, gy, cx, cy


def build_masks(map_config: dict, cell_size: int = DEFAULT_CELL_SIZE) -> tuple[int, int, list[int]]:
    world_w = int(map_config["world_w"])
    world_h = int(map_config["world_h"])
    cols = (world_w + cell_size - 1) // cell_size
    rows = (world_h + cell_size - 1) // cell_size
    cells = [LAND] * (cols * rows)

    def add(gx: int, gy: int, bit: int) -> None:
        cells[gy * cols + gx] |= bit

    # Water and vegetation are rasterized first; transport/structure layers may overlay them.
    for poly in map_config.get("water_polygons", []) or []:
        if len(poly) < 3:
            continue
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        for gx, gy, cx, cy in _cells_for_bbox(min(xs), min(ys), max(xs), max(ys), cell_size, cols, rows):
            if _point_in_poly(cx, cy, poly):
                add(gx, gy, WATER)
    for poly in map_config.get("green_polygons", []) or []:
        if len(poly) < 3:
            continue
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        for gx, gy, cx, cy in _cells_for_bbox(min(xs), min(ys), max(xs), max(ys), cell_size, cols, rows):
            if _point_in_poly(cx, cy, poly):
                add(gx, gy, GRASS)

    # Unified street bands. Lower-priority bands are resolved after all roads are unioned.
    for road in map_config.get("roads", []) or []:
        pts = road.get("points", []) or []
        if len(pts) < 2:
            continue
        width = max(12.0, float(road.get("width", 80.0)))
        pedestrian = str(road.get("highway", "")) in {"footway", "path", "cycleway", "steps", "pedestrian"}
        sidewalk = max(0.0, float(road.get("sidewalk_width", map_config.get("target_sidewalk_width_px", 30))))
        curb = max(0.0, float(road.get("curb_width", 5.0)))
        furnishing = 10.0 if sidewalk >= 20 else 0.0
        frontage = 8.0 if sidewalk >= 20 else 0.0
        road_r = width * 0.5
        curb_r = road_r + curb
        furnishing_r = curb_r + furnishing
        sidewalk_r = furnishing_r + (width * 0.5 if pedestrian else sidewalk)
        frontage_r = sidewalk_r + (6.0 if pedestrian else frontage)
        margin = frontage_r + cell_size
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        for gx, gy, cx, cy in _cells_for_bbox(min(xs)-margin, min(ys)-margin, max(xs)+margin, max(ys)+margin, cell_size, cols, rows):
            d = min(_point_segment_distance(cx, cy, a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:]))
            if pedestrian:
                if d <= sidewalk_r:
                    add(gx, gy, SIDEWALK)
                elif d <= frontage_r:
                    add(gx, gy, FRONTAGE)
                continue
            if d <= road_r:
                add(gx, gy, ROAD | (BRIDGE if road.get("bridge") else 0))
            elif d <= curb_r:
                add(gx, gy, CURB)
            elif d <= furnishing_r:
                add(gx, gy, FURNISHING)
            elif d <= sidewalk_r:
                add(gx, gy, SIDEWALK)
            elif d <= frontage_r:
                add(gx, gy, FRONTAGE)

    # Crosswalks are explicit sidewalk-to-sidewalk connectors.
    for crossing in map_config.get("crosswalks", []) or []:
        try:
            cx0, cy0 = map(float, crossing.get("pos", [0, 0]))
            angle = math.radians(float(crossing.get("angle", 0)))
            length = float(crossing.get("length", 96))
            width = float(crossing.get("width", 38))
        except (TypeError, ValueError):
            continue
        ux, uy = math.cos(angle), math.sin(angle)
        nx, ny = -uy, ux
        radius = max(length, width) * 0.75 + cell_size
        for gx, gy, px, py in _cells_for_bbox(cx0-radius, cy0-radius, cx0+radius, cy0+radius, cell_size, cols, rows):
            rx, ry = px - cx0, py - cy0
            along = rx * ux + ry * uy
            across = rx * nx + ry * ny
            if abs(along) <= length * 0.5 and abs(across) <= width * 0.5:
                add(gx, gy, CROSSWALK)

    # Bike-lane occupancy.
    for lane in map_config.get("bike_lanes", []) or []:
        pts = lane.get("points", []) or []
        if len(pts) < 2:
            continue
        radius = max(6.0, float(lane.get("width", 18.0)) * 0.5)
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        for gx, gy, cx, cy in _cells_for_bbox(min(xs)-radius-cell_size, min(ys)-radius-cell_size, max(xs)+radius+cell_size, max(ys)+radius+cell_size, cell_size, cols, rows):
            if min(_point_segment_distance(cx, cy, a[0], a[1], b[0], b[1]) for a,b in zip(pts,pts[1:])) <= radius:
                add(gx, gy, BIKE)

    # Building occupancy is fast because source buildings are rectangles.
    for rect in map_config.get("buildings", []) or []:
        try:
            x, y, w, h = map(float, rect)
        except (TypeError, ValueError):
            continue
        for gx, gy, cx, cy in _cells_for_bbox(x, y, x+w, y+h, cell_size, cols, rows):
            if x <= cx <= x+w and y <= cy <= y+h:
                add(gx, gy, BUILDING)

    # Resolve overlapping street bands globally so intersections are one geometry.
    for i, bits in enumerate(cells):
        if bits & ROAD:
            bits &= ~(CURB | FURNISHING | SIDEWALK | FRONTAGE)
        elif bits & CURB:
            bits &= ~(FURNISHING | SIDEWALK | FRONTAGE)
        elif bits & FURNISHING:
            bits &= ~(SIDEWALK | FRONTAGE)
        elif bits & SIDEWALK:
            bits &= ~FRONTAGE

        blocked = bool(bits & BUILDING) or (bool(bits & WATER) and not bool(bits & BRIDGE))
        if not blocked and (bits & (SIDEWALK | CROSSWALK | GRASS)):
            bits |= WALKABLE
        if not blocked and bits & ROAD:
            bits |= DRIVABLE
        if not blocked and (bits & (BIKE | ROAD)):
            bits |= CYCLABLE
        if blocked:
            bits &= ~(WALKABLE | DRIVABLE | CYCLABLE)
        cells[i] = bits & 0xFFFF
    return cols, rows, cells


def compiled_dir_for(folder: Path) -> Path:
    folder = Path(folder)
    # mapfiles/data/<map_id> -> mapfiles/compiled/<map_id>
    return folder.parents[1] / "compiled" / folder.name


def write_compiled_grid(folder: Path, map_config: dict, cell_size: int = DEFAULT_CELL_SIZE) -> Path:
    folder = Path(folder)
    out = compiled_dir_for(folder)
    out.mkdir(parents=True, exist_ok=True)
    cols, rows, cells = build_masks(map_config, cell_size)
    chunk_size = int(map_config.get("chunk_size", 1024))
    if chunk_size % cell_size:
        raise ValueError(f"chunk_size {chunk_size} must be divisible by cell_size {cell_size}")
    cpc = chunk_size // cell_size
    chunk_cols = (cols + cpc - 1) // cpc
    chunk_rows = (rows + cpc - 1) // cpc

    for cy in range(chunk_rows):
        for cx in range(chunk_cols):
            values = []
            for ly in range(cpc):
                gy = cy * cpc + ly
                for lx in range(cpc):
                    gx = cx * cpc + lx
                    values.append(cells[gy * cols + gx] if gx < cols and gy < rows else 0)
            raw = struct.pack(f"<{len(values)}H", *values)
            payload = b"PMGR15\0" + zlib.compress(raw, 9)
            human_id = chunk_label(cx, cy)
            (out / f"{human_id}.grid").write_bytes(payload)

    with (out / "chunk_index.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["chunk_id", "chunk_x", "chunk_y", "filename", "world_x", "world_y", "world_w", "world_h"])
        for cy in range(chunk_rows):
            for cx in range(chunk_cols):
                human_id = chunk_label(cx, cy)
                w.writerow([human_id, cx, cy, f"{human_id}.grid", cx * chunk_size, cy * chunk_size, chunk_size, chunk_size])

    with (out / "grid_manifest.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "value"])
        for key, value in (
            ("grid_version", GRID_VERSION), ("cell_size", cell_size), ("chunk_size", chunk_size),
            ("cells_per_chunk", cpc), ("grid_cols", cols), ("grid_rows", rows),
            ("chunk_cols", chunk_cols), ("chunk_rows", chunk_rows),
            ("source_fingerprint", source_fingerprint(folder)),
        ):
            w.writerow([key, value])
    with (out / "grid_layers.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["bit", "mask", "name"])
        for mask, name in sorted(LAYER_NAMES.items()):
            w.writerow([int(math.log2(mask)), mask, name])
    return out


class CompiledGrid:
    def __init__(self, folder: Path, *, cache_limit: int = 20):
        self.folder = Path(folder)
        manifest = {}
        with (self.folder / "grid_manifest.csv").open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                manifest[str(row["key"])] = str(row["value"])
        self.cell_size = int(manifest["cell_size"])
        self.chunk_size = int(manifest["chunk_size"])
        self.cells_per_chunk = int(manifest["cells_per_chunk"])
        self.grid_cols = int(manifest["grid_cols"])
        self.grid_rows = int(manifest["grid_rows"])
        self.chunk_cols = int(manifest["chunk_cols"])
        self.chunk_rows = int(manifest["chunk_rows"])
        self.source_fingerprint = manifest.get("source_fingerprint", "")
        self.cache_limit = max(4, int(cache_limit))
        self._cache: OrderedDict[tuple[int,int], tuple[int,...]] = OrderedDict()

    def _load_chunk(self, cx: int, cy: int) -> tuple[int,...] | None:
        key = (cx, cy)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        if cx < 0 or cy < 0 or cx >= self.chunk_cols or cy >= self.chunk_rows:
            return None
        path = self.folder / f"{chunk_label(cx, cy)}.grid"
        if not path.exists():
            # Backward compatibility with v1.5 numeric caches.
            path = self.folder / f"chunk_{cx:02d}_{cy:02d}.grid"
        try:
            payload = path.read_bytes()
            if not payload.startswith(b"PMGR15\0"):
                return None
            raw = zlib.decompress(payload[7:])
            count = self.cells_per_chunk * self.cells_per_chunk
            values = struct.unpack(f"<{count}H", raw)
        except (OSError, zlib.error, struct.error):
            return None
        self._cache[key] = values
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_limit:
            self._cache.popitem(last=False)
        return values

    def bits_at(self, x: float, y: float) -> int:
        gx = int(math.floor(float(x) / self.cell_size))
        gy = int(math.floor(float(y) / self.cell_size))
        if gx < 0 or gy < 0 or gx >= self.grid_cols or gy >= self.grid_rows:
            return 0
        cpc = self.cells_per_chunk
        cx, cy = gx // cpc, gy // cpc
        chunk = self._load_chunk(cx, cy)
        if chunk is None:
            return 0
        lx, ly = gx % cpc, gy % cpc
        return int(chunk[ly * cpc + lx])

    def any_bits_near(self, x: float, y: float, radius: float, mask: int) -> bool:
        cell = self.cell_size
        gx0 = max(0, int(math.floor((x - radius) / cell)))
        gy0 = max(0, int(math.floor((y - radius) / cell)))
        gx1 = min(self.grid_cols - 1, int(math.floor((x + radius) / cell)))
        gy1 = min(self.grid_rows - 1, int(math.floor((y + radius) / cell)))
        rr = float(radius) + cell * 0.72
        rr2 = rr * rr
        for gy in range(gy0, gy1 + 1):
            cy = (gy + 0.5) * cell
            for gx in range(gx0, gx1 + 1):
                cx = (gx + 0.5) * cell
                if (cx-x)*(cx-x) + (cy-y)*(cy-y) > rr2:
                    continue
                if self.bits_at(cx, cy) & mask:
                    return True
        return False


def try_load_compiled_grid(map_folder: Path, *, cache_limit: int = 20) -> CompiledGrid | None:
    out = compiled_dir_for(map_folder)
    manifest = out / "grid_manifest.csv"
    if not manifest.exists():
        return None
    try:
        grid = CompiledGrid(out, cache_limit=cache_limit)
    except (OSError, KeyError, ValueError):
        return None
    if grid.source_fingerprint != source_fingerprint(map_folder):
        return None
    return grid
