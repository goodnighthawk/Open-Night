from __future__ import annotations

import math
import os
import random
import io
import zipfile
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pygame

from common import CHUNK_CACHE_LIMIT, CHUNK_SIZE, chunk_buildings
from art_style import load_art_style
from portable_paths import shared_assets_root


ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets", "environment")
LOCAL_ATLAS_PATH = os.path.join(ASSET_DIR, "gta2_1.tga")
_SHARED_ATLAS = shared_assets_root() / "environment" / "gta2_1.tga"
ATLAS_PATH = str(_SHARED_ATLAS) if _SHARED_ATLAS.exists() else LOCAL_ATLAS_PATH

APPROVED_LOCAL_DIR = Path(__file__).resolve().parent / "assets" / "environment" / "approved"
APPROVED_SHARED_DIR = shared_assets_root() / "environment" / "approved"
OPEN_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "open_source_import"
PREFER_LOCAL_ART = os.environ.get("PYMMO_ART_REVIEW_LOCAL", "").strip().lower() in {"1", "true", "yes", "on"}

@lru_cache(maxsize=24)
def _approved_env_tile(name: str) -> pygame.Surface | None:
    filename = name if name.endswith(".png") else f"{name}.png"
    shared = APPROVED_SHARED_DIR / filename
    local = APPROVED_LOCAL_DIR / filename
    path = local if PREFER_LOCAL_ART and local.exists() else (shared if shared.exists() else local)
    if not path.exists():
        return None
    try:
        return pygame.image.load(str(path)).convert()
    except (pygame.error, OSError):
        return None


# Coordinates are in the user-supplied 256 x 6784 prototype texture atlas.
# The renderer deliberately centralizes them here so the atlas can later be
# replaced by original production art without changing map/network code.
ATLAS_RECTS: dict[str, tuple[int, int, int, int]] = {
    # roof / industrial surfaces
    "roof_concrete": (0, 2944, 64, 64),
    "roof_white": (0, 3072, 64, 64),
    "roof_dark": (0, 3200, 64, 64),
    "hazard": (0, 3328, 64, 64),
    "factory_frame": (0, 3456, 64, 64),
    "warehouse_green": (0, 3584, 64, 64),
    "warehouse_brown": (0, 3648, 64, 64),
    "factory_grate": (0, 3712, 64, 64),
    "fan_round": (0, 3904, 64, 64),
    "fan_square": (0, 4032, 64, 64),
    "green_stone": (0, 4160, 64, 64),
    # timber / urban fabric
    "wood_green": (0, 4352, 64, 64),
    "wood_dark": (64, 4352, 64, 64),
    "sandbags": (128, 4352, 64, 64),
    "brick": (0, 4480, 64, 64),
    "wood_plank": (128, 4480, 64, 64),
    "crate_ammo": (0, 4608, 64, 64),
    "crate_cross": (128, 4608, 64, 64),
    "crate_plain": (64, 4672, 64, 64),
    "gravel": (0, 4800, 64, 64),
    "rust_wall": (0, 4864, 64, 64),
    "industrial_wall": (0, 4992, 64, 64),
    "urban_wall": (128, 5056, 64, 64),
    "urban_window": (64, 5184, 64, 64),
    "urban_panel": (128, 5248, 64, 64),
    "urban_door": (0, 5312, 64, 64),
    # transparent-ish sign crops (black is colorkeyed)
    "sign_diner": (0, 576, 128, 64),
    "sign_open": (0, 704, 64, 64),
    "sign_hospital": (128, 512, 64, 64),
    "sign_live": (0, 896, 128, 64),
    "sign_mart": (192, 896, 64, 64),
}

ROAD_COLOR = (38, 41, 41)
ROAD_GRAIN = (49, 52, 51)
LANE_COLOR = (165, 159, 130)
CURB_COLOR = (112, 112, 105)
SIDEWALK_COLOR = (78, 80, 77)
BUILDING_EDGE = (44, 45, 43)
LAND_COLOR = (66, 72, 66)
LAND_GRAIN = (76, 80, 72)
WATER_COLOR = (37, 58, 69)
WATER_LINE = (46, 70, 82)
PARK_COLOR = (70, 94, 68)
PARK_EDGE = (54, 77, 55)
CROSSWALK_COLOR = (217, 214, 202)
BUILDING_SHADOW_COLOR = (19, 20, 19)
ROOF_PALETTE = [(116,105,91),(102,105,101),(125,96,82),(91,100,93)]
ROOF_DETAIL_COLOR = (151,143,125)
TREE_DARK = (41,67,48)
TREE_MID = (59,91,62)
TREE_LIGHT = (84,112,77)
TREE_TRUNK = (85,67,49)
BRIDGE_EDGE = (139,139,129)
BRIDGE_TOWER = (111,115,111)
FRONTAGE_COLOR = (66, 67, 63)
FURNISHING_COLOR = (86, 87, 81)
PARKING_MARK_COLOR = (142, 142, 132)
ROOF_PROP_DENSITY = 4


def apply_art_style() -> dict:
    global ROAD_COLOR, ROAD_GRAIN, LANE_COLOR, CURB_COLOR, SIDEWALK_COLOR
    global BUILDING_EDGE, LAND_COLOR, LAND_GRAIN, WATER_COLOR, WATER_LINE
    global PARK_COLOR, PARK_EDGE, CROSSWALK_COLOR, BUILDING_SHADOW_COLOR, ROOF_PALETTE
    global ROOF_DETAIL_COLOR, TREE_DARK, TREE_MID, TREE_LIGHT, TREE_TRUNK, BRIDGE_EDGE, BRIDGE_TOWER, ROOF_PROP_DENSITY
    style = load_art_style()
    env = style.get("environment", {})
    ROAD_COLOR = tuple(env.get("road", ROAD_COLOR))
    ROAD_GRAIN = tuple(env.get("road_grain", ROAD_GRAIN))
    LANE_COLOR = tuple(env.get("lane", LANE_COLOR))
    CURB_COLOR = tuple(env.get("curb", CURB_COLOR))
    SIDEWALK_COLOR = tuple(env.get("sidewalk", SIDEWALK_COLOR))
    BUILDING_EDGE = tuple(env.get("building_edge", BUILDING_EDGE))
    BUILDING_SHADOW_COLOR = tuple(env.get("building_shadow", BUILDING_SHADOW_COLOR))
    LAND_COLOR = tuple(env.get("land", LAND_COLOR))
    LAND_GRAIN = tuple(env.get("land_grain", LAND_GRAIN))
    WATER_COLOR = tuple(env.get("water", WATER_COLOR))
    WATER_LINE = tuple(env.get("water_line", WATER_LINE))
    PARK_COLOR = tuple(env.get("park", PARK_COLOR))
    PARK_EDGE = tuple(env.get("park_dark", PARK_EDGE))
    CROSSWALK_COLOR = tuple(env.get("crosswalk", CROSSWALK_COLOR))
    ROOF_PALETTE = [tuple(env.get(f"roof_{i}", ROOF_PALETTE[i-1])) for i in range(1,5)]
    ROOF_DETAIL_COLOR = tuple(env.get("roof_detail", ROOF_DETAIL_COLOR))
    TREE_DARK = tuple(env.get("tree_dark", TREE_DARK))
    TREE_MID = tuple(env.get("tree_mid", TREE_MID))
    TREE_LIGHT = tuple(env.get("tree_light", TREE_LIGHT))
    TREE_TRUNK = tuple(env.get("tree_trunk", TREE_TRUNK))
    BRIDGE_EDGE = tuple(env.get("bridge_edge", BRIDGE_EDGE))
    BRIDGE_TOWER = tuple(env.get("bridge_tower", BRIDGE_TOWER))
    ROOF_PROP_DENSITY = max(1, min(8, int(env.get("roof_prop_density", ROOF_PROP_DENSITY))))
    return style


apply_art_style()


def _point_in_poly(x: float, y: float, poly: list[tuple[int, int]]) -> bool:
    inside = False
    if len(poly) < 3:
        return False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def _parallel_points(points: list[tuple[int,int]], offset: float) -> list[tuple[int,int]]:
    if len(points) < 2:
        return points[:]
    out=[]
    for i,(x,y) in enumerate(points):
        a = points[max(0, i-1)]
        b = points[min(len(points)-1, i+1)]
        dx, dy = b[0]-a[0], b[1]-a[1]
        mag = math.hypot(dx,dy) or 1.0
        nx, ny = -dy/mag, dx/mag
        out.append((int(round(x + nx*offset)), int(round(y + ny*offset))))
    return out


def _gta2_visual_road_points(points: list[tuple[int,int]], highway: str = "", width: float = 80.0) -> list[tuple[int,int]]:
    """Round visible road elbows without altering gameplay/collision centerlines."""
    if len(points)<3: return points[:]
    base={"motorway":92,"motorway_link":88,"trunk":82,"trunk_link":78,"primary":70,"secondary":60,"tertiary":54,"residential":46,"service":36}.get(str(highway).lower(),48)
    radius=max(20.0,min(float(base),float(width)*.85))
    clean=[(float(points[0][0]),float(points[0][1]))]
    for p in points[1:]:
        p=(float(p[0]),float(p[1]))
        if math.hypot(p[0]-clean[-1][0],p[1]-clean[-1][1])>=1.0: clean.append(p)
    if len(clean)<3:return [(int(round(x)),int(round(y))) for x,y in clean]
    out=[clean[0]]
    for idx in range(1,len(clean)-1):
        a,p,b=clean[idx-1],clean[idx],clean[idx+1]
        vin=(p[0]-a[0],p[1]-a[1]);vout=(b[0]-p[0],b[1]-p[1]);lin=math.hypot(*vin);lout=math.hypot(*vout)
        if lin<2 or lout<2:out.append(p);continue
        ui=(vin[0]/lin,vin[1]/lin);uo=(vout[0]/lout,vout[1]/lout);dot=max(-1,min(1,ui[0]*uo[0]+ui[1]*uo[1]));turn=math.acos(dot)
        if turn<math.radians(6) or turn>math.radians(168):out.append(p);continue
        cut=min(radius*max(.32,min(1.0,turn/math.radians(82))),lin*.32,lout*.32)
        if cut<1.25:out.append(p);continue
        pin=(p[0]-ui[0]*cut,p[1]-ui[1]*cut);pout=(p[0]+uo[0]*cut,p[1]+uo[1]*cut);out.append(pin)
        steps=max(3,min(9,int(turn/math.radians(12))+2))
        for j in range(1,steps):
            t=j/steps;o=1-t;out.append((o*o*pin[0]+2*o*t*p[0]+t*t*pout[0],o*o*pin[1]+2*o*t*p[1]+t*t*pout[1]))
        out.append(pout)
    out.append(clean[-1])
    return [(int(round(x)),int(round(y))) for x,y in out]


@lru_cache(maxsize=8)
def _approved_prop(name: str, target_height: int) -> pygame.Surface | None:
    local = Path(__file__).resolve().parent / "assets" / "street_props" / f"{name}.png"
    shared = shared_assets_root() / "street_props" / f"{name}.png"
    path = local if PREFER_LOCAL_ART and local.exists() else (shared if shared.exists() else local)
    if not path.exists():
        return None
    source = pygame.image.load(str(path)).convert_alpha()
    height = max(12, int(target_height))
    width = max(8, round(source.get_width() * height / max(1, source.get_height())))
    return pygame.transform.smoothscale(source, (width, height))


@lru_cache(maxsize=12)
def _open_asset_building(camera_mode: str, target_height: int) -> pygame.Surface | None:
    mode = "isometric" if camera_mode == "isometric" else "topdown"
    path = OPEN_ASSET_DIR / "city" / f"city_building_01_{mode}.png"
    if not path.exists():
        return None
    try:
        source = pygame.image.load(str(path)).convert_alpha()
    except (pygame.error, OSError):
        return None
    height = max(18, int(target_height))
    width = max(12, round(source.get_width() * height / max(1, source.get_height())))
    return pygame.transform.smoothscale(source, (width, height))


class TextureAtlas:
    def __init__(self, path: str = ATLAS_PATH):
        self.path = path
        self.image: pygame.Surface | None = None
        self.cache: dict[tuple, pygame.Surface] = {}
        try:
            loaded = pygame.image.load(path)
            self.image = loaded.convert()
        except (pygame.error, FileNotFoundError, OSError):
            self.image = None

    @property
    def available(self) -> bool:
        return self.image is not None

    def get(self, name: str, *, scale: int = 1, colorkey: bool = False) -> pygame.Surface | None:
        key = (name, scale, colorkey)
        if key in self.cache:
            return self.cache[key]
        rect_data = ATLAS_RECTS.get(name)
        if self.image is None or rect_data is None:
            return None
        rect = pygame.Rect(*rect_data)
        surf = pygame.Surface(rect.size)
        surf.blit(self.image, (0, 0), rect)
        if colorkey:
            surf.set_colorkey((0, 0, 0))
        if scale != 1:
            surf = pygame.transform.scale(surf, (surf.get_width() * scale, surf.get_height() * scale))
            if colorkey:
                surf.set_colorkey((0, 0, 0))
        self.cache[key] = surf
        return surf


class EnvironmentRenderer:
    """Chunk-streamed renderer for the single authoritative Map 001 world.

    Nearby 1024x1024 chunks are cached so world dimensions do not scale video
    memory usage linearly with total map area.
    """

    def __init__(self, map_config: dict):
        self.atlas = TextureAtlas()
        self.map_id = ""
        self.world: pygame.Surface | None = None
        self.map_config: dict = {}
        self.chunked = False
        self.chunk_size = CHUNK_SIZE
        self.chunk_cache_limit = CHUNK_CACHE_LIMIT
        self.chunk_cache: OrderedDict[tuple[int, int, int], pygame.Surface] = OrderedDict()
        self._road_index = {}
        self._water_index = {}
        self._green_index = {}
        self.view_rotation_degrees = 0.0
        self._junction_cores: list[tuple[float, float, float]] = []
        self._junction_exclusions: dict[str, list[tuple[float, float, float]]] = {}
        self._portable_image_cache: dict[tuple[str,int], pygame.Surface] = {}
        self._composition_tile_cache: OrderedDict[tuple[str, int, int], pygame.Surface] = OrderedDict()
        self._composition_zip: zipfile.ZipFile | None = None
        self._composition_zip_path = ""
        self.set_map(map_config)

    @staticmethod
    def _dashed_line(surface: pygame.Surface, color, start, end, dash: int = 26, gap: int = 22, width: int = 2, exclude_circles=()) -> None:
        x1, y1 = start
        x2, y2 = end
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length <= 1:
            return
        ux, uy = dx / length, dy / length
        pos = 0.0
        while pos < length:
            end_pos = min(length, pos + dash)
            mid = (pos + end_pos) * 0.5
            mx, my = x1 + ux * mid, y1 + uy * mid
            if not any((mx-cx)*(mx-cx) + (my-cy)*(my-cy) <= rr*rr for cx,cy,rr in exclude_circles):
                a = (int(x1 + ux * pos), int(y1 + uy * pos))
                b = (int(x1 + ux * end_pos), int(y1 + uy * end_pos))
                pygame.draw.line(surface, color, a, b, width)
            pos += dash + gap

    @staticmethod
    def _tile(surface: pygame.Surface, tile: pygame.Surface | None, rect: pygame.Rect, fallback: tuple[int, int, int]) -> None:
        pygame.draw.rect(surface, fallback, rect)
        if tile is None:
            return
        old = surface.get_clip()
        surface.set_clip(rect)
        for y in range(rect.top, rect.bottom, tile.get_height()):
            for x in range(rect.left, rect.right, tile.get_width()):
                surface.blit(tile, (x, y))
        surface.set_clip(old)

    @staticmethod
    def _texture_masked_polyline(surface: pygame.Surface, points: list[tuple[int,int]], width: int, tile: pygame.Surface | None, fallback) -> None:
        if len(points) < 2:
            return
        width = max(1, int(width))
        pygame.draw.lines(surface, fallback, False, points, width)
        radius = max(1, width // 2)
        for x, y in points:
            pygame.draw.circle(surface, fallback, (x, y), radius)
        if tile is None:
            return
        xs=[p[0] for p in points]; ys=[p[1] for p in points]
        bbox=pygame.Rect(min(xs)-radius-2, min(ys)-radius-2, max(xs)-min(xs)+2*radius+5, max(ys)-min(ys)+2*radius+5)
        bbox=bbox.clip(surface.get_rect())
        if bbox.width <= 0 or bbox.height <= 0:
            return
        mask=pygame.Surface(bbox.size, pygame.SRCALPHA)
        local=[(x-bbox.x,y-bbox.y) for x,y in points]
        pygame.draw.lines(mask,(255,255,255,255),False,local,width)
        for x,y in local:
            pygame.draw.circle(mask,(255,255,255,255),(x,y),radius)
        tex=pygame.Surface(bbox.size, pygame.SRCALPHA)
        tw,th=tile.get_size()
        start_x=-(bbox.x % tw); start_y=-(bbox.y % th)
        for yy in range(start_y,bbox.height,th):
            for xx in range(start_x,bbox.width,tw):
                tex.blit(tile,(xx,yy))
        tex.blit(mask,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(tex,bbox.topleft)

    @staticmethod
    def _texture_masked_polygon(surface: pygame.Surface, points: list[tuple[int,int]], tile: pygame.Surface | None, fallback) -> None:
        if len(points) < 3:
            return
        pygame.draw.polygon(surface,fallback,points)
        if tile is None:
            return
        xs=[p[0] for p in points]; ys=[p[1] for p in points]
        bbox=pygame.Rect(min(xs),min(ys),max(xs)-min(xs)+1,max(ys)-min(ys)+1).clip(surface.get_rect())
        if bbox.width <= 0 or bbox.height <= 0:
            return
        mask=pygame.Surface(bbox.size,pygame.SRCALPHA)
        local=[(x-bbox.x,y-bbox.y) for x,y in points]
        pygame.draw.polygon(mask,(255,255,255,255),local)
        tex=pygame.Surface(bbox.size,pygame.SRCALPHA)
        tw,th=tile.get_size(); start_x=-(bbox.x % tw); start_y=-(bbox.y % th)
        for yy in range(start_y,bbox.height,th):
            for xx in range(start_x,bbox.width,tw):
                tex.blit(tile,(xx,yy))
        tex.blit(mask,(0,0),special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(tex,bbox.topleft)

    @staticmethod
    def _draw_corridor_mask(mask: pygame.Surface, points: list[tuple[int, int]], width: int) -> None:
        """Union one buffered centerline into an RGBA geometry mask.

        Drawing every street into the same mask is deliberate: intersections become
        one continuous geometry instead of a stack of per-road ribbons.
        """
        if len(points) < 2 or width <= 0:
            return
        width = max(1, int(width))
        radius = max(1, width // 2)
        pygame.draw.lines(mask, (255, 255, 255, 255), False, points, width)
        for x, y in points:
            pygame.draw.circle(mask, (255, 255, 255, 255), (int(x), int(y)), radius)

    @staticmethod
    def _subtract_geometry(outer: pygame.Surface, inner: pygame.Surface) -> pygame.Surface:
        """Return outer - inner for binary white/transparent geometry masks."""
        result = outer.copy()
        result.blit(inner, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        return result

    @staticmethod
    def _paint_geometry_mask(surface: pygame.Surface, mask: pygame.Surface, tile: pygame.Surface | None, fallback) -> None:
        """Paint a complete merged geometry mask with a seamless world tile."""
        layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        if len(fallback) == 3:
            layer.fill((*fallback, 255))
        else:
            layer.fill(fallback)
        if tile is not None:
            tw, th = tile.get_size()
            if tw > 0 and th > 0:
                # Chunk surfaces are world-aligned by construction, so tiling from
                # (0,0) remains deterministic and visually continuous at boundaries.
                for yy in range(0, layer.get_height(), th):
                    for xx in range(0, layer.get_width(), tw):
                        layer.blit(tile, (xx, yy))
        layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(layer, (0, 0))

    @staticmethod
    def _segment_intersection(a, b, c, d):
        """Return an inclusive finite centerline intersection, including T-junction endpoints."""
        x1,y1=map(float,a); x2,y2=map(float,b); x3,y3=map(float,c); x4,y4=map(float,d)
        den=(x1-x2)*(y3-y4)-(y1-y2)*(x3-x4)
        if abs(den) < 1e-7:
            return None
        t=((x1-x3)*(y3-y4)-(y1-y3)*(x3-x4))/den
        u=-((x1-x2)*(y1-y3)-(y1-y2)*(x1-x3))/den
        eps=1e-5
        if -eps <= t <= 1.0+eps and -eps <= u <= 1.0+eps:
            return (x1+t*(x2-x1), y1+t*(y2-y1))
        return None

    @staticmethod
    def _road_corridor_key(road: dict) -> str:
        """Return the stable semantic road ID used by the reference-image map."""
        return str(road.get("id", road.get("road_id", "")))

    def _rebuild_junction_cores(self) -> None:
        """Build scalable, road-specific marking exclusions from final topology.

        A lane line on road A must be suppressed by roughly half the width of
        crossing road B, while road B needs the converse distance. Keeping these
        exclusions per corridor avoids both the old line-grid artifact and huge
        unnecessary blank gaps when a narrow street crosses a wide arterial.
        """
        roads = list(self.map_config.get("roads", []) or [])
        clearance=max(24.0,float(self.map_config.get("junction_marking_clearance_px",72.0)))
        cell=max(256.0,float(self.map_config.get("junction_index_cell_px",512.0)))
        segments=[]
        buckets={}
        for road_i,road in enumerate(roads):
            pts=road.get("points",[]) or []
            if len(pts)<2:
                continue
            group=self._road_corridor_key(road)
            for seg_i,(a,b) in enumerate(zip(pts,pts[1:])):
                idx=len(segments)
                segments.append((road_i,seg_i,road,group,a,b))
                minx,miny=min(a[0],b[0]),min(a[1],b[1]); maxx,maxy=max(a[0],b[0]),max(a[1],b[1])
                for gy in range(int(miny//cell),int(maxy//cell)+1):
                    for gx in range(int(minx//cell),int(maxx//cell)+1):
                        buckets.setdefault((gx,gy),[]).append(idx)
        cores=[]; exclusions={}; seen_pairs=set()

        def add_exclusion(group, q, radius):
            arr=exclusions.setdefault(group,[])
            for i,(x,y,r) in enumerate(arr):
                if (q[0]-x)**2+(q[1]-y)**2 < (0.35*max(radius,r))**2:
                    if radius>r:
                        arr[i]=(x,y,radius)
                    return
            arr.append((q[0],q[1],radius))

        for ids in buckets.values():
            for ii,aidx in enumerate(ids):
                rai,sai,ra,ga,a,b=segments[aidx]
                for bidx in ids[ii+1:]:
                    rbi,sbi,rb,gb,c,d=segments[bidx]
                    if rai==rbi or ga==gb:
                        continue
                    pair=(min(aidx,bidx),max(aidx,bidx))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    if bool(ra.get("bridge")) != bool(rb.get("bridge")):
                        continue
                    q=self._segment_intersection(a,b,c,d)
                    if q is None:
                        continue
                    wa=float(ra.get("width",60)); wb=float(rb.get("width",60))
                    add_exclusion(ga,q,max(48.0,0.5*wb+clearance))
                    add_exclusion(gb,q,max(48.0,0.5*wa+clearance))
                    radius=max(48.0,0.5*max(wa,wb)+clearance)
                    merged=False
                    for ci,(x,y,r) in enumerate(cores):
                        if (q[0]-x)**2+(q[1]-y)**2 < (0.42*max(radius,r))**2:
                            if radius>r:
                                cores[ci]=(x,y,radius)
                            merged=True
                            break
                    if not merged:
                        cores.append((q[0],q[1],radius))
        self._junction_cores=cores
        self._junction_exclusions=exclusions

    def set_view_rotation(self, degrees: float) -> None:
        """Select a coarse camera-aware 2.5D extrusion bucket.

        The old implementation cleared every streamed chunk each few degrees of
        middle-mouse movement, which caused severe camera-rotation stalls. v2.4
        keeps per-angle chunk variants in the normal LRU and uses 30-degree art
        buckets. The client also defers bucket changes while actively dragging.
        """
        bucket=(round(float(degrees)/30.0)*30.0)%360.0
        if abs(((bucket-self.view_rotation_degrees+180.0)%360.0)-180.0) < 0.01:
            return
        self.view_rotation_degrees=bucket
        if not self.chunked and self.map_config:
            cfg=dict(self.map_config); self._signature=None; self.set_map(cfg)

    def _style(self) -> tuple[list[str], list[str]]:
        # v1.2 ships one exterior art family. Keeping this selector centralized
        # still makes a future licensed/original atlas swap straightforward.
        return (["roof_concrete", "urban_wall", "urban_panel", "brick", "industrial_wall", "roof_dark"], ["fan_round", "fan_square"])

    @staticmethod
    def _lerp_point(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    def _draw_roof_modules(self, surface: pygame.Surface, rect: pygame.Rect, inner: pygame.Rect, index: int, elevated_25d: bool, module_count: int | None = None) -> None:
        """Add deterministic roof modules so simple collision rectangles render as denser city blocks."""
        # Parapet/highlight lines are a cheap way to sell the approved 2.5D read.
        pygame.draw.line(surface, (178, 171, 153), (rect.left + 2, rect.top + 2), (rect.right - 4, rect.top + 2), 2)
        pygame.draw.line(surface, (168, 161, 144), (rect.left + 2, rect.top + 2), (rect.left + 2, rect.bottom - 4), 2)
        area = inner.width * inner.height
        if area <= 0:
            return
        # Deterministically seed a subset of larger roofs with the converted
        # user-authored voxel building. It behaves as a 2.5D rooftop tower and
        # remains baked into the same rotated chunk surface as other geometry.
        if elevated_25d and index % 13 == 0 and inner.width >= 72 and inner.height >= 62:
            imported = _open_asset_building("isometric", min(92, max(48, inner.height - 8)))
            if imported is not None:
                anchor = imported.get_rect(midbottom=(inner.centerx, inner.bottom - 3))
                pygame.draw.ellipse(surface, BUILDING_SHADOW_COLOR, anchor.inflate(8, -max(1, anchor.height // 2)).move(5, max(3, anchor.height // 3)))
                surface.blit(imported, anchor)
        if inner.width > 58 and inner.height > 54:
            seam_x = inner.centerx + ((index * 7) % 15) - 7
            pygame.draw.line(surface, BUILDING_EDGE, (seam_x, inner.top + 4), (seam_x, inner.bottom - 4), 1)
        if inner.width > 110 and inner.height > 70:
            seam_y = inner.centery + ((index * 11) % 13) - 6
            pygame.draw.line(surface, BUILDING_EDGE, (inner.left + 4, seam_y), (inner.right - 4, seam_y), 1)

        count = 1
        if area > 5200:
            count = 2
        if area > 10500:
            count = 3
        if area > 18500:
            count = 4
        if module_count is not None:
            count = max(0, min(5, int(module_count)))
        for module_i in range(count):
            seed = (index * 92821 + module_i * 68917) & 0x7FFFFFFF
            mw = max(10, min(inner.width - 10, 16 + seed % max(8, inner.width // 3)))
            mh = max(9, min(inner.height - 10, 12 + (seed // 13) % max(7, inner.height // 3)))
            span_x = max(1, inner.width - mw - 8)
            span_y = max(1, inner.height - mh - 8)
            mx = inner.x + 4 + (seed // 97) % span_x
            my = inner.y + 4 + (seed // 193) % span_y
            shade = ROOF_DETAIL_COLOR if module_i % 2 == 0 else ROOF_PALETTE[(index + module_i + 1) % len(ROOF_PALETTE)]
            pygame.draw.rect(surface, BUILDING_SHADOW_COLOR, (mx + 3, my + 4, mw, mh), border_radius=2)
            pygame.draw.rect(surface, shade, (mx, my, mw, mh), border_radius=2)
            pygame.draw.rect(surface, BUILDING_EDGE, (mx, my, mw, mh), width=1, border_radius=2)
            pygame.draw.line(surface, (190, 182, 163), (mx + 2, my + 2), (mx + mw - 3, my + 2), 1)

        # Mechanical details / vents / skylights.
        detail_count = max(2, min(9, area // 2500 + 1)) if elevated_25d else max(1, min(5, area // 4200 + 1))
        for prop_i in range(detail_count):
            seed = (index * 12553 + prop_i * 41771) & 0x7FFFFFFF
            vw = 5 + seed % 8
            vh = 4 + (seed // 13) % 7
            span_x = max(1, inner.width - vw - 10)
            span_y = max(1, inner.height - vh - 10)
            vx = inner.x + 5 + (seed // 97) % span_x
            vy = inner.y + 5 + (seed // 193) % span_y
            pygame.draw.rect(surface, BUILDING_SHADOW_COLOR, (vx + 2, vy + 3, vw, vh), border_radius=1)
            pygame.draw.rect(surface, ROOF_DETAIL_COLOR, (vx, vy, vw, vh), border_radius=1)
            pygame.draw.rect(surface, BUILDING_EDGE, (vx, vy, vw, vh), width=1, border_radius=1)

        if area > 10000:
            # Circular tanks/HVAC units help break rectangular repetition.
            r = max(5, min(11, min(inner.width, inner.height) // 10))
            wx = inner.right - r - 8
            wy = inner.y + r + 8
            pygame.draw.circle(surface, BUILDING_SHADOW_COLOR, (wx + 3, wy + 4), r + 1)
            pygame.draw.circle(surface, ROOF_DETAIL_COLOR, (wx, wy), r)
            pygame.draw.circle(surface, BUILDING_EDGE, (wx, wy), r, width=1)

    def _draw_gwb_landmark(self, surface: pygame.Surface, points: list[tuple[int, int]], width: int) -> None:
        """Overlay GWB-specific bridge art on top of the generic road deck."""
        if len(points) < 2:
            return
        a = points[0]; b = points[-1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        mag = math.hypot(dx, dy) or 1.0
        ux, uy = dx / mag, dy / mag
        nx, ny = -uy, ux
        deck_half = max(26, int(width * 0.55))
        # Elevated/bridge cast shadow is runtime-owned. It can be projected onto
        # lower map levels and remains independent of the baked deck material.
        edge_a = _parallel_points(points, deck_half + 12)
        edge_b = _parallel_points(points, -(deck_half + 12))
        if bool(self.map_config.get('runtime_elevated_shadows', True)):
            shadow_a = [(x + 7, y + 8) for x, y in edge_a]
            shadow_b = [(x + 7, y + 8) for x, y in edge_b]
            pygame.draw.lines(surface, BUILDING_SHADOW_COLOR, False, shadow_a, 8)
            pygame.draw.lines(surface, BUILDING_SHADOW_COLOR, False, shadow_b, 8)
        # steel deck edges
        pygame.draw.lines(surface, BRIDGE_EDGE, False, edge_a, 6)
        pygame.draw.lines(surface, BRIDGE_EDGE, False, edge_b, 6)
        pygame.draw.lines(surface, (182, 182, 172), False, _parallel_points(points, deck_half + 5), 2)
        pygame.draw.lines(surface, (182, 182, 172), False, _parallel_points(points, -(deck_half + 5)), 2)

        tower_depth = max(18, int(width * 0.20))
        tower_half = max(34, int(width * 0.46))
        for frac in (0.31, 0.69):
            tx, ty = self._lerp_point(a, b, frac)
            tx = int(tx); ty = int(ty)
            p1 = (int(tx + nx * tower_half), int(ty + ny * tower_half))
            p2 = (int(tx - nx * tower_half), int(ty - ny * tower_half))
            pygame.draw.line(surface, BUILDING_SHADOW_COLOR, (p1[0] + 5, p1[1] + 6), (p2[0] + 5, p2[1] + 6), tower_depth + 8)
            pygame.draw.line(surface, BRIDGE_TOWER, p1, p2, tower_depth)
            pygame.draw.line(surface, BUILDING_EDGE, p1, p2, 3)
            # tower caps
            cap1 = (int(p1[0] + ux * 8), int(p1[1] + uy * 8))
            cap2 = (int(p2[0] + ux * 8), int(p2[1] + uy * 8))
            pygame.draw.line(surface, (188, 188, 181), cap1, cap2, 2)
            # suspension/cable hints
            for off in (-0.22, -0.08, 0.08, 0.22):
                anchor = self._lerp_point(a, b, frac + off)
                left_anchor = (int(anchor[0] + nx * (deck_half + 2)), int(anchor[1] + ny * (deck_half + 2)))
                right_anchor = (int(anchor[0] - nx * (deck_half + 2)), int(anchor[1] - ny * (deck_half + 2)))
                pygame.draw.line(surface, (164, 164, 156), p1, left_anchor, 1)
                pygame.draw.line(surface, (164, 164, 156), p2, right_anchor, 1)

        # walkway / gantry hints near the middle of the span
        mid = self._lerp_point(a, b, 0.5)
        for sign in (-1, 1):
            c = (int(mid[0] + nx * sign * (deck_half - 4)), int(mid[1] + ny * sign * (deck_half - 4)))
            pygame.draw.circle(surface, (160, 160, 152), c, 3)

    def _portable_image(self, path: str, target_height: int = 0) -> pygame.Surface | None:
        if not path:
            return None
        key=(str(path),int(target_height))
        if key in self._portable_image_cache: return self._portable_image_cache[key]
        try:
            img=pygame.image.load(str(path))
            img=img.convert_alpha() if img.get_alpha() is not None else img.convert()
            if target_height:
                h=max(8,int(target_height)); w=max(8,round(img.get_width()*h/max(1,img.get_height())))
                img=pygame.transform.smoothscale(img,(w,h))
            self._portable_image_cache[key]=img
            return img
        except (pygame.error,OSError):
            return None

    def _map_material(self, key: str, fallback: pygame.Surface | None = None) -> pygame.Surface | None:
        path=str((self.map_config.get("portable_materials",{}) or {}).get(key,""))
        return self._portable_image(path) if path else fallback

    def _composition_archive_path(self) -> Path | None:
        raw = str(self.map_config.get("baked_composition_archive", "")).strip()
        if not raw:
            return None
        requested = Path(raw)
        candidates = [requested] if requested.is_absolute() else [Path(__file__).resolve().parent / requested]
        if not requested.is_absolute():
            parts = requested.parts[1:] if requested.parts and requested.parts[0] == "assets" else requested.parts
            candidates.append(shared_assets_root().joinpath(*parts))
        return next((path for path in candidates if path.is_file()), None)

    def _composition_tile(self, mode: str, tile_x: int, tile_y: int) -> pygame.Surface | None:
        key = (mode, int(tile_x), int(tile_y))
        cached = self._composition_tile_cache.get(key)
        if cached is not None:
            self._composition_tile_cache.move_to_end(key)
            return cached
        archive_path = self._composition_archive_path()
        if archive_path is None:
            return None
        try:
            if self._composition_zip is None or self._composition_zip_path != str(archive_path):
                if self._composition_zip is not None:
                    self._composition_zip.close()
                self._composition_zip = zipfile.ZipFile(archive_path, "r")
                self._composition_zip_path = str(archive_path)
            name = f"{mode}/tile_{tile_x:02d}_{tile_y:02d}.png"
            payload = self._composition_zip.read(name)
            tile = pygame.image.load(io.BytesIO(payload), name).convert()
        except (OSError, KeyError, zipfile.BadZipFile, pygame.error):
            return None
        self._composition_tile_cache[key] = tile
        self._composition_tile_cache.move_to_end(key)
        while len(self._composition_tile_cache) > 8:
            self._composition_tile_cache.popitem(last=False)
        return tile

    def _draw_baked_composition(self, surface: pygame.Surface, cx: int, cy: int) -> bool:
        """Draw the reviewed master art without reinterpreting its geometry."""
        if not bool(self.map_config.get("baked_composition", False)):
            return False
        scale = max(0.01, float(self.map_config.get("baked_composition_source_scale", 0.5)))
        world_y0 = float(self.map_config.get("baked_composition_world_y", 2048.0))
        source_x = cx * self.chunk_size * scale
        source_y = (cy * self.chunk_size - world_y0) * scale
        source_span = int(round(self.chunk_size * scale))
        if source_x < 0 or source_y < 0:
            return True
        tile_size = 1024
        tile_x = int(source_x // tile_size)
        tile_y = int(source_y // tile_size)
        tile = self._composition_tile(str(self.map_config.get("default_render_mode", "night")).lower(), tile_x, tile_y)
        if tile is None:
            return True
        local_x = int(round(source_x - tile_x * tile_size))
        local_y = int(round(source_y - tile_y * tile_size))
        crop = pygame.Rect(local_x, local_y, source_span, source_span)
        if not tile.get_rect().contains(crop):
            return True
        source = tile.subsurface(crop)
        if source.get_size() != surface.get_size():
            source = pygame.transform.smoothscale(source, surface.get_size())
        surface.blit(source, (0, 0))
        return True

    def _draw_asphalt(self, surface: pygame.Surface, rng: random.Random) -> None:
        surface.fill(ROAD_COLOR)
        w, h = surface.get_size()
        for _ in range(max(700, (w * h) // 3800)):
            x = rng.randrange(0, w)
            y = rng.randrange(0, h)
            surface.set_at((x, y), ROAD_GRAIN if rng.random() < 0.8 else (31, 33, 33))

    def _draw_land_base(self, surface: pygame.Surface, rng: random.Random) -> None:
        surface.fill(LAND_COLOR)
        land_tile=self._map_material("land")
        if land_tile is not None:
            self._tile(surface, land_tile, surface.get_rect(), LAND_COLOR)
        w, h = surface.get_size()
        for _ in range(max(180, (w * h) // 9500)):
            x = rng.randrange(0, w)
            y = rng.randrange(0, h)
            surface.set_at((x, y), LAND_GRAIN if rng.random() < 0.72 else (57, 63, 58))

    def _draw_building(self, surface: pygame.Surface, raw_rect: Iterable[int], index: int, rng: random.Random) -> None:
        x, y, rw, rh = map(int, raw_rect)
        rect = pygame.Rect(x, y, rw, rh)
        render_style = str(self.map_config.get("render_style", ""))
        elevated_style = render_style in {"isometric_nyc_topdown", "approved_topdown_v1", "approved_25d_v1", "approved_25d_v2"}
        approved_25d = render_style in {"approved_25d_v1", "approved_25d_v2"}

        bid = str(self.map_config.get("building_id_by_rect", {}).get(tuple((x, y, rw, rh)), index))
        visual = dict(self.map_config.get("building_visuals", {}).get(bid, {}))
        profile = str(visual.get("profile", "brick_midrise"))
        shadow_scale = float(visual.get("shadow_scale", 1.0))

        if not elevated_style:
            pavement = rect.inflate(38, 38)
            pygame.draw.rect(surface, CURB_COLOR, pavement.inflate(4, 4), border_radius=4)
            pygame.draw.rect(surface, SIDEWALK_COLOR, pavement, border_radius=3)

        depth = 0
        if elevated_style:
            default_depth = 9 if not approved_25d else max(10, min(22, 8 + min(rect.width, rect.height) // 18))
            depth = int(round(float(visual.get("height_px", default_depth)))) if approved_25d else default_depth
            depth = max(6, min(36, depth))

        # v1.5.1 uses the recent approved-derived 2.5D City Texture Pack
        # material crops as its primary facade family. The older compact
        # facades remain shipped as fallbacks/source compatibility.
        wall_styles = {
            "brick_midrise": ((72, 52, 44), (88, 63, 50), "city_red_brick_64"),
            "concrete_midrise": ((68, 69, 66), (83, 83, 77), "city_concrete_64"),
            "commercial_lowrise": ((82, 75, 62), (96, 86, 69), "city_beige_stone_64"),
            "industrial": ((60, 52, 46), (72, 61, 52), "city_brown_brick_64"),
            "tower": ((57, 65, 68), (68, 76, 77), "city_gray_stone_64"),
        }
        right_color, bottom_color, facade_name = wall_styles.get(profile, wall_styles["brick_midrise"])

        # Keep the fake vertical extrusion in a stable southeast screen direction.
        # The world itself is rotated later, so counter-rotate the extrusion vector
        # here. This prevents facades from appearing to switch sides as the camera turns.
        theta=math.radians(float(getattr(self,"view_rotation_degrees",0.0)))
        c,sn=math.cos(theta),math.sin(theta)
        ex=int(round(depth*(c-sn))) if elevated_style else 0
        ey=int(round(depth*(sn+c))) if elevated_style else 0
        # Pass 18: directional building shadows are viewer/runtime-owned.
        # Their screen direction follows camera rotation rather than being baked
        # into map textures. A map may disable them, but Open Night defaults on.
        if bool(self.map_config.get('runtime_building_shadows', True)):
            shadow_len=(4.0+depth*0.55)*shadow_scale
            shx=int(round(shadow_len*(c-sn))); shy=int(round(shadow_len*(sn+c)))
            if abs(shx)+abs(shy) < 2: shx,shy=4,5
            pygame.draw.rect(surface, BUILDING_SHADOW_COLOR, rect.move(shx, shy), border_radius=2)
        elif bool(self.map_config.get('baked_contact_ao', True)):
            pygame.draw.rect(surface, BUILDING_SHADOW_COLOR, rect.move(2, 2), width=2, border_radius=2)

        if elevated_style and rect.width > 28 and rect.height > 28 and (ex or ey):
            facade_tile = _approved_env_tile(facade_name) if approved_25d else None
            vx=rect.right if ex >= 0 else rect.left
            vertical=[(vx,rect.top),(vx,rect.bottom),(vx+ex,rect.bottom+ey),(vx+ex,rect.top+ey)]
            hy=rect.bottom if ey >= 0 else rect.top
            horizontal=[(rect.left,hy),(rect.right,hy),(rect.right+ex,hy+ey),(rect.left+ex,hy+ey)]
            self._texture_masked_polygon(surface, vertical, facade_tile, right_color)
            self._texture_masked_polygon(surface, horizontal, facade_tile, bottom_color)
            pygame.draw.lines(surface, BUILDING_EDGE, True, vertical, 1)
            pygame.draw.lines(surface, BUILDING_EDGE, True, horizontal, 1)

        styles, props = self._style()
        style_name = styles[index % len(styles)]
        if render_style in {"approved_topdown_v1", "approved_25d_v1", "approved_25d_v2"}:
            roof_style = str(visual.get("roof_style", "auto"))
            roof_map = {
                "light":"city_roof_concrete_64",
                "dark":"city_roof_tar_64",
                "brown":"city_roof_gravel_64",
                "tan":"city_roof_metal_gray_64",
            }
            approved_roofs = [
                "city_roof_tar_64", "city_roof_gravel_64",
                "city_roof_concrete_64", "city_roof_metal_gray_64",
                "city_roof_metal_green_64",
            ]
            tile = _approved_env_tile(roof_map.get(roof_style, approved_roofs[index % len(approved_roofs)]))
        else:
            tile = None if elevated_style else self.atlas.get(style_name)
        tile = self._map_material("roof", tile)
        self._tile(surface, tile, rect, ROOF_PALETTE[index % len(ROOF_PALETTE)])
        pygame.draw.rect(surface, BUILDING_EDGE, rect, width=3 if elevated_style else 5, border_radius=2)

        base_inset = 7 if elevated_style else 10
        extra_inset = int(round(float(visual.get("roof_inset", 0.0)))) if approved_25d else 0
        inner = rect.inflate(-2 * (base_inset + extra_inset), -2 * (base_inset + extra_inset))
        if inner.width > 35 and inner.height > 35:
            pygame.draw.rect(surface, BUILDING_EDGE, inner, width=1 if elevated_style else 2)
        if elevated_style and inner.width > 42 and inner.height > 36:
            self._draw_roof_modules(surface, rect, inner, index, approved_25d, int(visual.get("penthouses", 0)) or None)
        elif inner.width > 105 and inner.height > 90:
            prop = self.atlas.get(props[index % len(props)])
            if prop is not None:
                px = inner.x + 14 + ((index * 97) % max(1, inner.width - 80))
                py = inner.y + 12 + ((index * 53) % max(1, inner.height - 78))
                surface.blit(prop, (px, py))

    def _draw_lane_markings(self, surface: pygame.Surface) -> None:
        for route in self.map_config.get("traffic_routes", []):
            points = route.get("waypoints", [])
            for i, a in enumerate(points):
                if not points:
                    break
                b = points[(i + 1) % len(points)]
                self._dashed_line(surface, LANE_COLOR, (a[0], a[1]), (b[0], b[1]))

    def _draw_pixel_tree(self, surface: pygame.Surface, x: int, y: int, size: int = 8) -> None:
        size = max(5, int(size))
        approved = _approved_prop("street_tree", max(28, size * 4))
        if approved is not None:
            surface.blit(approved, approved.get_rect(midbottom=(x, y + size * 2)))
            return
        pygame.draw.rect(surface, TREE_TRUNK, (x-1, y+1, 3, max(3, size//2)))
        pygame.draw.circle(surface, BUILDING_SHADOW_COLOR, (x+2, y+3), size+1)
        pygame.draw.circle(surface, TREE_DARK, (x, y), size)
        pygame.draw.circle(surface, TREE_MID, (x-2, y-2), max(3, size-2))
        pygame.draw.circle(surface, TREE_LIGHT, (x-3, y-4), max(2, size//3))

    def _draw_chunk_green(self, surface: pygame.Surface, cx: int, cy: int, ox: int, oy: int) -> None:
        for poly_i, poly in enumerate(self._green_index.get((cx, cy), ())):
            local = [(int(p[0] - ox), int(p[1] - oy)) for p in poly]
            if len(local) >= 3:
                pygame.draw.polygon(surface, PARK_COLOR, local)
                pygame.draw.lines(surface, PARK_EDGE, True, local, 2)
                xs=[p[0] for p in local]; ys=[p[1] for p in local]
                left,right=max(-20,min(xs)),min(self.chunk_size+20,max(xs))
                top,bottom=max(-20,min(ys)),min(self.chunk_size+20,max(ys))
                area=max(0,(right-left)*(bottom-top))
                count=max(0,min(22,area//18000))
                rng=random.Random(f"trees:{self.map_id}:{cx}:{cy}:{poly_i}")
                placed=0
                for _ in range(int(count)*8 + 8):
                    if placed >= count:
                        break
                    tx=rng.randint(int(left),int(right)) if right>left else int(left)
                    ty=rng.randint(int(top),int(bottom)) if bottom>top else int(top)
                    if _point_in_poly(tx,ty,local):
                        self._draw_pixel_tree(surface,tx,ty,rng.randint(6,10))
                        placed += 1

    def _draw_chunk_water(self, surface: pygame.Surface, cx: int, cy: int, ox: int, oy: int) -> None:
        for poly in self._water_index.get((cx, cy), ()):
            local = [(int(p[0] - ox), int(p[1] - oy)) for p in poly]
            if len(local) >= 3:
                self._texture_masked_polygon(surface, local, self._map_material("water", _approved_env_tile("water_64")), WATER_COLOR)
                pygame.draw.lines(surface, WATER_LINE, True, local, 2)

    @staticmethod
    def _oriented_rect(center: tuple[float, float], along: tuple[float, float], half_along: float, half_across: float) -> list[tuple[int,int]]:
        """Rectangle whose long axis follows *along* (a unit vector)."""
        cx, cy = center
        dx, dy = along
        nx, ny = -dy, dx
        return [
            (int(round(cx + dx*half_along + nx*half_across)), int(round(cy + dy*half_along + ny*half_across))),
            (int(round(cx + dx*half_along - nx*half_across)), int(round(cy + dy*half_along - ny*half_across))),
            (int(round(cx - dx*half_along - nx*half_across)), int(round(cy - dy*half_along - ny*half_across))),
            (int(round(cx - dx*half_along + nx*half_across)), int(round(cy - dy*half_along + ny*half_across))),
        ]

    def _carve_crosswalk_curb_cuts(self, furnishing_union: pygame.Surface, curb_union: pygame.Surface, cx: int, cy: int, ox: int, oy: int) -> None:
        """Open the curb/furnishing rings where authored zebras meet sidewalks.

        Road asphalt is not modified. Because sidewalks are derived as
        sidewalk_union - furnishing_union, these openings let the sidewalk ramp
        naturally reach the curb edge without painting a second sidewalk ribbon.
        """
        for crossing in self._crosswalk_index.get((cx, cy), ()):
            try:
                wx, wy = map(float, crossing.get("pos", [0, 0]))
                angle = math.radians(float(crossing.get("angle", 0.0)))
                length = float(crossing.get("length", 96.0))
                zwidth = float(crossing.get("width", 38.0))
                depth = float(crossing.get("curb_cut_depth", 16.0))
            except (TypeError, ValueError):
                continue
            if depth <= 0:
                continue
            dx, dy = math.cos(angle), math.sin(angle)
            local=(wx-ox, wy-oy)
            for sign in (-1.0, 1.0):
                ex=local[0] + dx*sign*(length*0.5)
                ey=local[1] + dy*sign*(length*0.5)
                # Center the opening just outside the asphalt edge, elongated in
                # the pedestrian travel direction and slightly wider than zebra.
                cxr=ex + dx*sign*(depth*0.30)
                cyr=ey + dy*sign*(depth*0.30)
                poly=self._oriented_rect((cxr,cyr),(dx,dy),depth*0.72,zwidth*0.56)
                pygame.draw.polygon(furnishing_union,(0,0,0,0),poly)
                pygame.draw.polygon(curb_union,(0,0,0,0),poly)

    def _draw_chunk_roads(self, surface: pygame.Surface, cx: int, cy: int, ox: int, oy: int) -> None:
        """Render all streets in a chunk as one merged, non-overlapping geometry.

        Earlier v1.2 builds painted each road corridor independently. At a junction,
        the sidewalk ribbon belonging to road A could therefore be painted across
        the asphalt of road B. This pass first unions every road into shared masks,
        then derives disjoint frontage/sidewalk/furnishing/curb/asphalt regions.

        Geometry invariant (outside -> inside):
            frontage = frontage_union - sidewalk_union
            sidewalk  = sidewalk_union  - furnishing_union
            furnishing= furnishing_union- curb_union
            curb      = curb_union      - road_union
            road      = road_union

        The result is one continuous road surface and one continuous sidewalk
        network per chunk. Intersections are therefore cut once, not once per road.
        """
        size = surface.get_size()
        road_union = pygame.Surface(size, pygame.SRCALPHA)
        curb_union = pygame.Surface(size, pygame.SRCALPHA)
        furnishing_union = pygame.Surface(size, pygame.SRCALPHA)
        sidewalk_union = pygame.Surface(size, pygame.SRCALPHA)
        frontage_union = pygame.Surface(size, pygame.SRCALPHA)

        drivable_roads: list[tuple[dict, list[tuple[int, int]], int, str]] = []
        pedestrian_roads: list[tuple[dict, list[tuple[int, int]], int]] = []

        for road in self._road_index.get((cx, cy), ()):
            # Ground roads are unioned only with other ground roads.  Elevated
            # roads are composited afterwards by level, so a bridge crossing a
            # Level-0 street remains an overpass instead of becoming a junction.
            try:
                road_level = int(float(road.get("level", 0) or 0))
            except (TypeError, ValueError):
                road_level = 0
            if road_level != 0:
                continue
            points = [(int(p[0] - ox), int(p[1] - oy)) for p in road.get("points", [])]
            if len(points) < 2:
                continue
            width = max(12, int(float(road.get("width", 80))))
            highway = str(road.get("highway", ""))
            pedestrian = highway in {"footway", "path", "cycleway", "steps", "pedestrian"}
            if not pedestrian and str(self.map_config.get("road_visual_style", "gta2_rounded")).lower() == "gta2_rounded":
                points = _gta2_visual_road_points(points, highway, width)
            if pedestrian:
                pedestrian_roads.append((road, points, width))
                # Pedestrian-only paths join the sidewalk union but never claim
                # asphalt. Crossing a vehicle road is automatically clipped by the
                # later sidewalk - furnishing subtraction.
                self._draw_corridor_mask(frontage_union, points, max(12, width + 12))
                self._draw_corridor_mask(sidewalk_union, points, max(8, width))
                continue

            sidewalk_side = max(0, int(float(road.get("sidewalk_width", self.map_config.get("target_sidewalk_width_px", 30)))))
            curb_side = max(0, int(float(road.get("curb_width", 5))))
            # Pass 19: keep the furnishing strip compact so sidewalks visually
            # hug ordinary roads while preserving the semantic pedestrian corridor.
            furnishing_side = 6 if sidewalk_side >= 20 else 0
            frontage_side = 5 if sidewalk_side >= 20 else 0

            curb_w = width + curb_side * 2
            furnishing_w = curb_w + furnishing_side * 2
            sidewalk_w = furnishing_w + sidewalk_side * 2
            frontage_w = sidewalk_w + frontage_side * 2

            drivable_roads.append((road, points, width, highway))
            self._draw_corridor_mask(road_union, points, width)
            self._draw_corridor_mask(curb_union, points, curb_w)
            self._draw_corridor_mask(furnishing_union, points, furnishing_w)
            self._draw_corridor_mask(sidewalk_union, points, sidewalk_w)
            self._draw_corridor_mask(frontage_union, points, frontage_w)

            if road.get("bridge") and bool(self.map_config.get("runtime_elevated_shadows", True)):
                shadow = [(x + 10, y + 12) for x, y in points]
                pygame.draw.lines(surface, BUILDING_SHADOW_COLOR, False, shadow, frontage_w + 12)

        # Crosswalk curb cuts modify the shared curb/furnishing unions before
        # disjoint surfaces are derived, so the result is true geometry rather
        # than a decorative ramp painted over the street.
        self._carve_crosswalk_curb_cuts(furnishing_union, curb_union, cx, cy, ox, oy)

        # Convert nested corridor unions into mutually exclusive final surfaces.
        frontage_geom = self._subtract_geometry(frontage_union, sidewalk_union)
        sidewalk_geom = self._subtract_geometry(sidewalk_union, furnishing_union)
        furnishing_geom = self._subtract_geometry(furnishing_union, curb_union)
        curb_geom = self._subtract_geometry(curb_union, road_union)

        self._paint_geometry_mask(surface, frontage_geom, _approved_env_tile("roof_dark_64"), FRONTAGE_COLOR)
        self._paint_geometry_mask(surface, sidewalk_geom, self._map_material("sidewalk", _approved_env_tile("sidewalk_64")), SIDEWALK_COLOR)
        self._paint_geometry_mask(surface, furnishing_geom, None, FURNISHING_COLOR)
        self._paint_geometry_mask(surface, curb_geom, None, CURB_COLOR)
        self._paint_geometry_mask(surface, road_union, self._map_material("road", _approved_env_tile("asphalt_64")), ROAD_COLOR)

        # Pass 19 cosmetic street-edge seams.  These do not affect collisions or
        # walkability; they only make road -> curb -> sidewalk legible at night.
        curb_hi = tuple(min(255, int(v * 1.22 + 8)) for v in CURB_COLOR)
        walk_seam = tuple(max(0, int(v * 0.72)) for v in SIDEWALK_COLOR)
        for road, points, width, highway in drivable_roads:
            if highway in {"motorway", "motorway_link"}:
                continue
            sidewalk_side = max(0, int(float(road.get("sidewalk_width", self.map_config.get("target_sidewalk_width_px", 30)))))
            if sidewalk_side <= 0:
                continue
            curb_side = max(0, int(float(road.get("curb_width", 5))))
            furnishing_side = 6 if sidewalk_side >= 20 else 0
            corridor_key=self._road_corridor_key(road)
            local_junctions=[
                (jx-ox,jy-oy,r)
                for jx,jy,r in self._junction_exclusions.get(corridor_key,())
                if ox-r-40 <= jx <= ox+self.chunk_size+r+40 and oy-r-40 <= jy <= oy+self.chunk_size+r+40
            ]
            for sign in (-1.0, 1.0):
                curb_line = _parallel_points(points, sign*(width*0.5 + max(1.0, curb_side*0.45)))
                sidewalk_line = _parallel_points(points, sign*(width*0.5 + curb_side + furnishing_side + sidewalk_side))
                for a,b in zip(curb_line,curb_line[1:]):
                    self._dashed_line(surface, curb_hi, a, b, dash=100000, gap=1, width=2, exclude_circles=local_junctions)
                for a,b in zip(sidewalk_line,sidewalk_line[1:]):
                    self._dashed_line(surface, walk_seam, a, b, dash=100000, gap=1, width=1, exclude_circles=local_junctions)

        # Markings are clipped out of junction cores so lane/parking stripes do not
        # continue through crossings as a pile of intersecting lines.
        for road, points, width, highway in drivable_roads:
            corridor_key=self._road_corridor_key(road)
            local_junctions=[
                (jx-ox,jy-oy,r)
                for jx,jy,r in self._junction_exclusions.get(corridor_key,())
                if ox-r-40 <= jx <= ox+self.chunk_size+r+40 and oy-r-40 <= jy <= oy+self.chunk_size+r+40
            ]
            # v2.4: lane markings are derived from the authored lane count instead
            # of assuming every wide road has the same two dashed offsets. This
            # keeps six-lane motorways, four-lane arterials and two-lane streets
            # visually distinct while preserving the shared junction-core mask.
            lanes = max(1, int(road.get("lanes", 2)))
            if lanes >= 2 and width >= 48:
                lane_width = float(width) / float(lanes)
                boundaries = [(-width * 0.5) + lane_width * i for i in range(1, lanes)]
                for off in boundaries:
                    if abs(off) <= lane_width * 0.18:
                        continue
                    else:
                        line_pts = _parallel_points(points, off)
                        for a, b in zip(line_pts, line_pts[1:]):
                            self._dashed_line(surface, CROSSWALK_COLOR, a, b, dash=54, gap=48, width=3, exclude_circles=local_junctions)

            if not road.get("bridge") and width >= 50:
                bay_off = max(14.0, width * 0.5 - 10.0)
                for off in (-bay_off, bay_off):
                    bay = _parallel_points(points, off)
                    for a, b in zip(bay, bay[1:]):
                        self._dashed_line(surface, PARKING_MARK_COLOR, a, b, dash=24, gap=58, width=2, exclude_circles=local_junctions)

            if road.get("bridge"):
                edge_off = max(8, width * 0.5 + 10)
                edge_a = _parallel_points(points, edge_off)
                edge_b = _parallel_points(points, -edge_off)
                pygame.draw.lines(surface, BRIDGE_EDGE, False, edge_a, 5)
                pygame.draw.lines(surface, BRIDGE_EDGE, False, edge_b, 5)
                if "george washington" in str(road.get("name", "")).lower() and len(points) >= 2:
                    self._draw_gwb_landmark(surface, points, width)

        # Positive map levels are drawn after the ground-level union.  This is
        # deliberately a separate compositing pass: different levels may cross in
        # XY without sharing curbs, sidewalks, lane masks, or junction markings.
        self._draw_chunk_elevated_roads(surface, cx, cy, ox, oy)

    def _draw_chunk_elevated_roads(self, surface: pygame.Surface, cx: int, cy: int, ox: int, oy: int) -> None:
        roads_by_level: dict[int, list[dict]] = {}
        for road in self._road_index.get((cx, cy), ()):
            try:
                level = int(float(road.get("level", 0) or 0))
            except (TypeError, ValueError):
                level = 0
            if level > 0:
                roads_by_level.setdefault(level, []).append(road)
        if not roads_by_level:
            return

        size = surface.get_size()
        for level in sorted(roads_by_level):
            road_union = pygame.Surface(size, pygame.SRCALPHA)
            curb_union = pygame.Surface(size, pygame.SRCALPHA)
            sidewalk_union = pygame.Surface(size, pygame.SRCALPHA)
            rendered: list[tuple[dict, list[tuple[int,int]], int, str]] = []

            # Viewer-owned cast shadows are represented here as a light deck
            # occlusion cue.  The full camera-aware shadow remains a runtime layer.
            if bool(self.map_config.get("runtime_elevated_shadows", True)):
                for road in roads_by_level[level]:
                    pts=[(int(p[0]-ox),int(p[1]-oy)) for p in road.get("points",[]) or []]
                    if len(pts)<2: continue
                    width=max(12,int(float(road.get("width",80))))
                    highway=str(road.get("highway",""))
                    if str(self.map_config.get("road_visual_style","gta2_rounded")).lower()=="gta2_rounded":
                        pts=_gta2_visual_road_points(pts,highway,width)
                    side=max(0,int(float(road.get("sidewalk_width",0) or 0)))
                    curb=max(0,int(float(road.get("curb_width",5) or 0)))
                    shadow_pts=[(x+7+level*3,y+9+level*3) for x,y in pts]
                    pygame.draw.lines(surface,BUILDING_SHADOW_COLOR,False,shadow_pts,width+2*(side+curb)+12)

            for road in roads_by_level[level]:
                points=[(int(p[0]-ox),int(p[1]-oy)) for p in road.get("points",[]) or []]
                if len(points)<2: continue
                width=max(12,int(float(road.get("width",80))))
                highway=str(road.get("highway",""))
                if str(self.map_config.get("road_visual_style","gta2_rounded")).lower()=="gta2_rounded":
                    points=_gta2_visual_road_points(points,highway,width)
                side=max(0,int(float(road.get("sidewalk_width",0) or 0)))
                curb=max(0,int(float(road.get("curb_width",5) or 0)))
                self._draw_corridor_mask(road_union,points,width)
                self._draw_corridor_mask(curb_union,points,width+curb*2)
                self._draw_corridor_mask(sidewalk_union,points,width+2*(curb+side))
                rendered.append((road,points,width,highway))

            sidewalk_geom=self._subtract_geometry(sidewalk_union,curb_union)
            curb_geom=self._subtract_geometry(curb_union,road_union)
            self._paint_geometry_mask(surface,sidewalk_geom,self._map_material("sidewalk",_approved_env_tile("sidewalk_64")),SIDEWALK_COLOR)
            self._paint_geometry_mask(surface,curb_geom,None,CURB_COLOR)
            self._paint_geometry_mask(surface,road_union,self._map_material("road",_approved_env_tile("asphalt_64")),ROAD_COLOR)

            for road,points,width,highway in rendered:
                lanes=max(1,int(road.get("lanes",2) or 2))
                if lanes>=2 and width>=48:
                    lane_width=float(width)/float(lanes)
                    for i in range(1,lanes):
                        off=(-width*.5)+lane_width*i
                        col=LANE_COLOR if abs(off)<=lane_width*.18 else CROSSWALK_COLOR
                        dashed=abs(off)>lane_width*.18
                        for a,b in zip(_parallel_points(points,off),_parallel_points(points,off)[1:]):
                            self._dashed_line(surface,col,a,b,dash=54 if dashed else 100000,gap=48 if dashed else 1,width=3)
                edge_off=max(8,width*.5+10)
                pygame.draw.lines(surface,BRIDGE_EDGE,False,_parallel_points(points,edge_off),5)
                pygame.draw.lines(surface,BRIDGE_EDGE,False,_parallel_points(points,-edge_off),5)
                if "gwb" in str(road.get("id","")).lower() or "george washington" in str(road.get("name","")).lower():
                    self._draw_gwb_landmark(surface,points,width)

    def _draw_chunk_street_props(self, surface: pygame.Surface, cx: int, cy: int, ox: int, oy: int) -> None:
        """Draw explicitly authored approved-art street furniture for this chunk."""
        target_heights = {
            "street_tree": 84,
            "curved_streetlamp": 78,
            "fire_hydrant": 37,
            "bicycle_rack": 50,
            "traffic_signal": 72,
        }
        for prop in self._street_prop_index.get((cx, cy), ()):
            try:
                wx, wy = map(float, prop.get("pos", [0, 0]))
            except (TypeError, ValueError):
                continue
            kind = str(prop.get("kind", ""))
            if kind == "edge_tunnel":
                # A compact strict-top-down continuation portal. Its scale is the
                # associated road width / 80, so local streets and motorways receive
                # proportionate mouths without needing a separate bitmap per class.
                scale = max(0.75, float(prop.get("scale", 1.0)))
                road_width = max(46, int(round(80.0 * scale)))
                length = max(68, int(round(46.0 + road_width * 0.22)))
                portal = pygame.Surface((length, road_width + 34), pygame.SRCALPHA)
                center_y = portal.get_height() // 2
                pygame.draw.rect(portal, (8, 10, 11), (8, 12, length - 5, road_width + 10), border_radius=8)
                pygame.draw.rect(portal, (48, 51, 50), (5, 4, 18, road_width + 26), border_radius=7)
                pygame.draw.rect(portal, (126, 123, 111), (10, 8, 8, road_width + 18), border_radius=3)
                pygame.draw.line(portal, (211, 179, 65), (20, center_y - road_width//2 + 7), (20, center_y + road_width//2 - 7), 3)
                pygame.draw.line(portal, (3, 4, 5), (31, center_y - road_width//2 + 5), (length - 3, center_y - road_width//2 + 5), 4)
                pygame.draw.line(portal, (3, 4, 5), (31, center_y + road_width//2 - 5), (length - 3, center_y + road_width//2 - 5), 4)
                rotation = float(prop.get("rotation", 0.0))
                portal = pygame.transform.rotate(portal, -rotation)
                x, y = int(wx - ox), int(wy - oy)
                surface.blit(portal, portal.get_rect(center=(x, y)))
                continue
            base_h = target_heights.get(kind)
            if base_h is None:
                continue
            scale = max(0.25, float(prop.get("scale", 1.0)))
            portable_path = str((self.map_config.get("portable_prop_sprites", {}) or {}).get(str(prop.get("id", "")), ""))
            sprite = self._portable_image(portable_path, max(12, int(round(base_h * scale)))) if portable_path else _approved_prop(kind, max(12, int(round(base_h * scale))))
            if sprite is None:
                continue
            rotation = float(prop.get("rotation", 0.0))
            if abs(rotation) > 0.01:
                sprite = pygame.transform.rotate(sprite, -rotation)
            x, y = int(wx - ox), int(wy - oy)
            # Asset ground-contact point is bottom center. This yields stable
            # sidewalk alignment across chunks and camera rotation.
            surface.blit(sprite, sprite.get_rect(midbottom=(x, y)))

    def _draw_chunk_crosswalks(self, surface: pygame.Surface, cx: int, cy: int, ox: int, oy: int) -> None:
        """Draw authored curb-to-curb zebras and stop bars.

        ``angle`` is the lane/zebra-bar direction in world degrees. Individual
        bars run parallel to lane lines and repeat along the curb-to-curb normal.
        """
        for crossing in self._crosswalk_index.get((cx, cy), ()):
            try:
                wx, wy = map(float, crossing.get("pos", [0, 0]))
                angle = math.radians(float(crossing.get("angle", 0.0)))
                length = float(crossing.get("length", 96.0))
                zwidth = float(crossing.get("width", 38.0))
                stripe = float(crossing.get("stripe_width", 7.0))
                gap = float(crossing.get("stripe_gap", 7.0))
                stop_gap = float(crossing.get("stop_bar_gap", 12.0))
            except (TypeError, ValueError):
                continue
            dx, dy = math.cos(angle), math.sin(angle)
            nx, ny = -dy, dx
            center=(wx-ox, wy-oy)
            pitch=max(4.0,stripe+gap)
            count=max(1,int(math.floor((length + gap)/pitch)))
            used=(count-1)*pitch
            for idx in range(count):
                along=-used*0.5 + idx*pitch
                c=(center[0]+nx*along, center[1]+ny*along)
                poly=self._oriented_rect(c,(dx,dy),zwidth*0.5,stripe*0.5)
                pygame.draw.polygon(surface,CROSSWALK_COLOR,poly)
            # Two stop bars sit just outside the zebra in the vehicle-flow
            # direction. They are thinner/dimmer than the zebra itself.
            stop_color=tuple(max(0,int(v*0.82)) for v in CROSSWALK_COLOR)
            for sign in (-1.0,1.0):
                off=zwidth*0.5 + stop_gap
                c=(center[0]+dx*sign*off, center[1]+dy*sign*off)
                p1=(int(c[0]-nx*length*0.46),int(c[1]-ny*length*0.46))
                p2=(int(c[0]+nx*length*0.46),int(c[1]+ny*length*0.46))
                pygame.draw.line(surface,stop_color,p1,p2,3)


    def _draw_portable_layout_overlays(self, surface: pygame.Surface, cx: int, cy: int, ox: int, oy: int, stage: str) -> None:
        """Render cosmetic-only alleys/courtyards from a distributed .map.

        These never alter collision.  Ground alleys are painted before semantic
        buildings; roof courtyards are painted after them.
        """
        for item in self._portable_overlay_index.get((cx,cy),()):
            kind=str(item.get("kind", ""))
            if stage == "ground" and kind != "service_alley": continue
            if stage == "roof" and kind != "roof_courtyard": continue
            try:
                x=int(float(item.get("x",0))-ox); y=int(float(item.get("y",0))-oy)
                w=max(1,int(float(item.get("w",0)))); h=max(1,int(float(item.get("h",0))))
            except (TypeError,ValueError): continue
            rect=pygame.Rect(x,y,w,h)
            if not rect.colliderect(surface.get_rect()): continue
            if kind == "service_alley":
                tile=self._map_material("road")
                self._tile(surface,tile,rect,(39,42,42))
                pygame.draw.rect(surface,(84,84,78),rect,width=1)
            else:
                pygame.draw.rect(surface,(23,27,28),rect)
                inner=rect.inflate(-8,-8)
                if inner.width>5 and inner.height>5:
                    pygame.draw.rect(surface,(57,59,56),inner,width=2)

    def _draw_portable_street_dressing(self, surface: pygame.Surface, cx: int, cy: int, ox: int, oy: int) -> None:
        sprites=self.map_config.get("portable_archetype_sprites", {}) or {}
        for item in self._portable_dressing_index.get((cx,cy),()):
            aid=str(item.get("archetype_id", "")); path=str(sprites.get(aid, ""))
            if not path: continue
            kind=str(item.get("kind", ""))
            try:
                wx=float(item.get("x",0)); wy=float(item.get("y",0)); scale=max(.2,float(item.get("scale",.6)))
            except (TypeError,ValueError): continue
            base=96 if kind=="tree" else 48
            sprite=self._portable_image(path,max(12,int(base*scale)))
            if sprite is None: continue
            x=int(wx-ox); y=int(wy-oy)
            if -100 <= x <= surface.get_width()+100 and -100 <= y <= surface.get_height()+100:
                surface.blit(sprite,sprite.get_rect(midbottom=(x,y)))

    def _draw_chunk_interior_entrances(self, surface: pygame.Surface, cx: int, cy: int, ox: int, oy: int) -> None:
        """Render subtle exterior thresholds for enterable isometric interiors."""
        for item in self._interior_index.get((cx, cy), ()):
            try:
                entry = item.get("entry", [0, 0])
                wx, wy = float(entry[0]), float(entry[1])
                x, y = int(wx - ox), int(wy - oy)
            except (TypeError, ValueError, IndexError):
                continue
            kind = str(item.get("kind", "interior")).lower()
            edge = (235, 186, 82) if kind in {"shop", "diner", "club"} else (205, 171, 82)
            pygame.draw.rect(surface, (72, 46, 32), pygame.Rect(x - 8, y - 7, 16, 14), border_radius=2)
            pygame.draw.rect(surface, edge, pygame.Rect(x - 8, y - 7, 16, 14), 2, border_radius=2)
            if str(self.map_config.get("default_render_mode", "day")).lower() == "night":
                pygame.draw.circle(surface, (255, 210, 105), (x, y - 10), 3)

    def _draw_portable_night_lighting(self, surface: pygame.Surface, cx: int, cy: int, ox: int, oy: int) -> None:
        if str(self.map_config.get("default_render_mode", "day")).lower() != "night": return
        shade=pygame.Surface(surface.get_size(),pygame.SRCALPHA); shade.fill((5,9,15,105)); surface.blit(shade,(0,0))
        glow=pygame.Surface(surface.get_size(),pygame.SRCALPHA)
        colors={"warm":(255,184,82),"cool":(94,157,216),"amber":(247,159,70),"green":(94,180,109)}
        for light in self._portable_light_index.get((cx,cy),()):
            if str(light.get("source_type")) not in {"streetlamp","bridge_lamp"}: continue
            if not self.map_config.get("street_lamps_enabled",True) and str(light.get("source_type"))=="streetlamp": continue
            try:
                x=int(float(light.get("x",0))-ox); y=int(float(light.get("y",0))-oy); r=max(18,int(float(light.get("radius_px",120))*0.72)); strength=max(.1,min(1.3,float(light.get("intensity",.5))))
            except (TypeError,ValueError): continue
            col=colors.get(str(light.get("color_tag","warm")),(238,176,90))
            for frac,alpha in ((1.0,18),(.62,26),(.32,38)):
                pygame.draw.circle(glow,(*col,int(alpha*strength)),(x,y),max(5,int(r*frac)))
        surface.blit(glow,(0,0),special_flags=pygame.BLEND_RGBA_ADD)

    def _render_chunk(self, cx: int, cy: int) -> pygame.Surface:
        key = (cx, cy, int(round(self.view_rotation_degrees)) % 360)
        cached = self.chunk_cache.get(key)
        if cached is not None:
            self.chunk_cache.move_to_end(key)
            return cached

        size = self.chunk_size
        surf = pygame.Surface((size, size)).convert()
        rng = random.Random(f"pymmo-v010-art:{self.map_id}:{cx}:{cy}")
        self._draw_land_base(surf, rng)
        ox, oy = cx * size, cy * size
        if self._draw_baked_composition(surf, cx, cy):
            self.chunk_cache[key] = surf
            self.chunk_cache.move_to_end(key)
            while len(self.chunk_cache) > self.chunk_cache_limit:
                self.chunk_cache.popitem(last=False)
            return surf
        self._draw_chunk_green(surf, cx, cy, ox, oy)
        self._draw_chunk_water(surf, cx, cy, ox, oy)
        self._draw_chunk_roads(surf, cx, cy, ox, oy)
        self._draw_chunk_crosswalks(surf, cx, cy, ox, oy)
        self._draw_portable_layout_overlays(surf, cx, cy, ox, oy, "ground")

        for idx, raw in enumerate(chunk_buildings(self.map_config, cx, cy)):
            local_rect = [int(raw[0] - ox), int(raw[1] - oy), int(raw[2]), int(raw[3])]
            stable_index = (cy * max(1, int(self.map_config.get("chunk_cols", 1))) + cx) * 17 + idx
            self._draw_building(surf, local_rect, stable_index, rng)

        # Buildings are collision-cleared from roads by the map validator, but their
        # 2.5D facade/shadow extrusion can extend beyond the roof footprint. Repaint
        # authoritative transport surfaces after buildings so visual extrusion never
        # appears in the middle of a road or crossing.
        self._draw_chunk_roads(surf, cx, cy, ox, oy)
        self._draw_chunk_crosswalks(surf, cx, cy, ox, oy)

        self._draw_portable_layout_overlays(surf, cx, cy, ox, oy, "roof")
        # Portable maps can declare night as their default; darkening and local
        # street-light pools are cosmetic only and never affect collision.
        self._draw_portable_night_lighting(surf, cx, cy, ox, oy)
        self._draw_chunk_interior_entrances(surf, cx, cy, ox, oy)
        # Street furniture/dressing are authored after buildings so lamps, trees
        # and storefront clutter remain crisp and readable at GTA2-style zoom.
        self._draw_chunk_street_props(surf, cx, cy, ox, oy)
        self._draw_portable_street_dressing(surf, cx, cy, ox, oy)

        self.chunk_cache[key] = surf
        self.chunk_cache.move_to_end(key)
        while len(self.chunk_cache) > self.chunk_cache_limit:
            self.chunk_cache.popitem(last=False)
        return surf

    def _index_points_feature(self, index: dict, feature, points, margin: float = 0.0) -> None:
        if not points:
            return
        xs = [float(p[0]) for p in points]; ys = [float(p[1]) for p in points]
        size = max(1, self.chunk_size)
        cols = max(1, int(self.map_config.get("chunk_cols", 1)))
        rows = max(1, int(self.map_config.get("chunk_rows", 1)))
        cx0 = max(0, min(cols - 1, int((min(xs) - margin) // size)))
        cy0 = max(0, min(rows - 1, int((min(ys) - margin) // size)))
        cx1 = max(0, min(cols - 1, int((max(xs) + margin) // size)))
        cy1 = max(0, min(rows - 1, int((max(ys) + margin) // size)))
        for cy in range(cy0, cy1 + 1):
            for cx in range(cx0, cx1 + 1):
                index.setdefault((cx, cy), []).append(feature)

    def _build_feature_indices(self) -> None:
        self._road_index: dict[tuple[int,int], list[dict]] = {}
        self._water_index: dict[tuple[int,int], list[list]] = {}
        self._green_index: dict[tuple[int,int], list[list]] = {}
        self._signal_index: dict[tuple[int,int], list[dict]] = {}
        self._crosswalk_index: dict[tuple[int,int], list[dict]] = {}
        self._street_prop_index: dict[tuple[int,int], list[dict]] = {}
        self._portable_light_index: dict[tuple[int,int], list[dict]] = {}
        self._portable_dressing_index: dict[tuple[int,int], list[dict]] = {}
        self._portable_overlay_index: dict[tuple[int,int], list[dict]] = {}
        self._interior_index: dict[tuple[int,int], list[dict]] = {}
        if not self.chunked:
            return
        for road in self.map_config.get("roads", []) or []:
            points = road.get("points", []) or []
            margin = max(32.0, float(road.get("width", 40.0)) * 0.5 + 64.0)
            self._index_points_feature(self._road_index, road, points, margin)
        for poly in self.map_config.get("water_polygons", []) or []:
            self._index_points_feature(self._water_index, poly, poly, 4.0)
        for poly in self.map_config.get("green_polygons", []) or []:
            self._index_points_feature(self._green_index, poly, poly, 4.0)
        for signal in self.map_config.get("traffic_signals", []) or []:
            pos=signal.get("pos", []) or []
            if len(pos) >= 2:
                self._index_points_feature(self._signal_index, signal, [pos], 30.0)
        for crossing in self.map_config.get("crosswalks", []) or []:
            pos=crossing.get("pos", []) or []
            if len(pos) >= 2:
                margin=max(80.0, float(crossing.get("length",96.0))*0.75)
                self._index_points_feature(self._crosswalk_index, crossing, [pos], margin)
        for prop in self.map_config.get("street_props", []) or []:
            pos=prop.get("pos", []) or []
            if len(pos) >= 2:
                self._index_points_feature(self._street_prop_index, prop, [pos], 96.0)
        for item in self.map_config.get("interiors", []) or []:
            pos = item.get("entry", []) or []
            if len(pos) >= 2:
                self._index_points_feature(self._interior_index, item, [pos], 24.0)
        for light in self.map_config.get("portable_light_emitters", []) or []:
            try: pos=[float(light.get("x",0)),float(light.get("y",0))]
            except (TypeError,ValueError): continue
            self._index_points_feature(self._portable_light_index, light, [pos], float(light.get("radius_px",150) or 150))
        cosmetics=self.map_config.get("portable_cosmetics", {}) or {}
        for item in cosmetics.get("street_dressing", []) or []:
            try: pos=[float(item.get("x",0)),float(item.get("y",0))]
            except (TypeError,ValueError): continue
            self._index_points_feature(self._portable_dressing_index,item,[pos],110.0)
        for item in cosmetics.get("layout_overlays", []) or []:
            try:
                x=float(item.get("x",0)); y=float(item.get("y",0)); w=float(item.get("w",0)); h=float(item.get("h",0))
            except (TypeError,ValueError): continue
            pts=[[x,y],[x+w,y+h]]
            self._index_points_feature(self._portable_overlay_index,item,pts,16.0)

    def set_map(self, map_config: dict) -> None:
        map_id = str(map_config.get("id", "downtown"))
        signature = (map_id, int(map_config.get("world_w", 1)), int(map_config.get("world_h", 1)), bool(map_config.get("chunked")), str(map_config.get("map_build_id","")), str(map_config.get("default_render_mode","day")))
        current = getattr(self, "_signature", None)
        self.map_config = map_config
        if current == signature:
            return
        self._signature = signature
        self.map_id = map_id
        self.chunked = bool(map_config.get("chunked"))
        self.chunk_size = int(map_config.get("chunk_size", CHUNK_SIZE))
        self.chunk_cache_limit = int(map_config.get("chunk_cache_limit", CHUNK_CACHE_LIMIT))
        self.chunk_cache.clear()
        self._portable_image_cache.clear()
        self._composition_tile_cache.clear()
        if self._composition_zip is not None:
            self._composition_zip.close()
        self._composition_zip = None
        self._composition_zip_path = ""
        self.world = None
        self._build_feature_indices()
        self._rebuild_junction_cores()

        if self.chunked:
            return

        w = int(map_config["world_w"])
        h = int(map_config["world_h"])
        self.world = pygame.Surface((w, h)).convert()
        rng = random.Random(f"pymmo-v010:{map_id}")
        self._draw_asphalt(self.world, rng)
        self._draw_lane_markings(self.world)
        for index, rect in enumerate(map_config.get("buildings", [])):
            self._draw_building(self.world, rect, index, rng)

    def draw_view(self, target: pygame.Surface, camera: tuple[float, float]) -> None:
        cam_x, cam_y = camera
        target.fill(ROAD_COLOR)
        if not self.chunked:
            if self.world is not None:
                viewport = pygame.Rect(int(cam_x), int(cam_y), target.get_width(), target.get_height())
                target.blit(self.world, (0, 0), viewport)
            return

        size = self.chunk_size
        world_w = int(self.map_config["world_w"])
        world_h = int(self.map_config["world_h"])
        min_cx = max(0, int(cam_x) // size)
        min_cy = max(0, int(cam_y) // size)
        max_cx = min((world_w - 1) // size, int(cam_x + target.get_width()) // size)
        max_cy = min((world_h - 1) // size, int(cam_y + target.get_height()) // size)
        for cy in range(min_cy, max_cy + 1):
            for cx in range(min_cx, max_cx + 1):
                chunk = self._render_chunk(cx, cy)
                target.blit(chunk, (int(cx * size - cam_x), int(cy * size - cam_y)))

    def draw_elevated_overlay(self, target: pygame.Surface, camera: tuple[float, float], level: int) -> None:
        """Redraw one positive road level above lower-level dynamic entities.

        Chunk art already contains the deck.  This lightweight second draw is an
        occlusion layer used after Level-0 cars/players/NPCs and before players on
        the requested elevated level.  It keeps grade-separated crossings visually
        correct without baking dynamic entities into chunk textures.
        """
        level=int(level)
        if level<=0:
            return
        cam_x,cam_y=map(float,camera)
        for road in self.map_config.get("roads",[]) or []:
            try: road_level=int(float(road.get("level",0) or 0))
            except (TypeError,ValueError): road_level=0
            if road_level!=level:
                continue
            pts=[(int(float(p[0])-cam_x),int(float(p[1])-cam_y)) for p in road.get("points",[]) or []]
            if len(pts)<2:
                continue
            width=max(12,int(float(road.get("width",80))))
            highway=str(road.get("highway",""))
            if str(self.map_config.get("road_visual_style","gta2_rounded")).lower()=="gta2_rounded":
                pts=_gta2_visual_road_points(pts,highway,width)
            side=max(0,int(float(road.get("sidewalk_width",0) or 0)))
            curb=max(0,int(float(road.get("curb_width",5) or 0)))
            # Draw broad outer-to-inner ribbons. Rounded point caps preserve the
            # GTA2-style curve language at connector and bend vertices.
            for color,line_w in ((SIDEWALK_COLOR,width+2*(side+curb)),(CURB_COLOR,width+2*curb),(ROAD_COLOR,width)):
                pygame.draw.lines(target,color,False,pts,max(1,line_w))
                rad=max(1,line_w//2)
                for q in pts:
                    pygame.draw.circle(target,color,q,rad)
            lanes=max(1,int(road.get("lanes",2) or 2))
            if lanes>=2 and width>=48:
                lane_width=float(width)/lanes
                for i in range(1,lanes):
                    off=(-width*.5)+lane_width*i
                    line=_parallel_points(pts,off)
                    col=LANE_COLOR if abs(off)<=lane_width*.18 else CROSSWALK_COLOR
                    for a,b in zip(line,line[1:]):
                        self._dashed_line(target,col,a,b,dash=100000 if col==LANE_COLOR else 54,gap=1 if col==LANE_COLOR else 48,width=3)
            edge_off=max(8,width*.5+10)
            pygame.draw.lines(target,BRIDGE_EDGE,False,_parallel_points(pts,edge_off),5)
            pygame.draw.lines(target,BRIDGE_EDGE,False,_parallel_points(pts,-edge_off),5)

    def reload_style(self) -> None:
        apply_art_style()
        self.chunk_cache.clear()
        if not self.chunked:
            # Rebuild small legacy maps immediately.
            cfg = dict(self.map_config)
            self._signature = None
            self.set_map(cfg)

    def invalidate_chunk(self, cx: int, cy: int) -> None:
        cx, cy = int(cx), int(cy)
        for key in [k for k in self.chunk_cache if k[0] == cx and k[1] == cy]:
            self.chunk_cache.pop(key, None)

    def invalidate_near(self, cx: int, cy: int, radius: int = 1) -> None:
        x0,x1=int(cx)-radius,int(cx)+radius; y0,y1=int(cy)-radius,int(cy)+radius
        for key in [k for k in self.chunk_cache if x0 <= k[0] <= x1 and y0 <= k[1] <= y1]:
            self.chunk_cache.pop(key, None)

    def invalidate_all(self) -> None:
        self.chunk_cache.clear()

    def status_text(self) -> str:
        atlas = "loaded" if self.atlas.available else "fallback"
        if self.chunked:
            return f"Approved target tiles + vehicle atlas: {atlas} • streamed chunks: {len(self.chunk_cache)}/{self.chunk_cache_limit}"
        return f"Environment atlas: {atlas}"
