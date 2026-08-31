#!/usr/bin/env python3
"""Standalone visual workbench for Open Night's city_block and v4 map data.

This intentionally starts no game client, server, networking, NPC simulation, or
gameplay systems.  It reads the same generated GridWorld data and authored v4
layout contracts that the game will eventually consume.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

ROOT = Path(__file__).resolve().parent
V4_LAYOUT_DIR = ROOT / "dev_tools" / "map_generator" / "working_cosmetics" / "approved_v4_layout"
GRID_DATA_DIR = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor" / "grid_v100"
CITY_BLOCK_DIR = ROOT / "assets" / "source_packs" / "city_block"
GENERATED_BUILDING_CATALOG = ROOT / "assets" / "grid_v100" / "generated_building_tiles.json"
GENERATED_ART_CATALOG = ROOT / "assets" / "grid_v100" / "generated_art_tiles.json"
GENERATED_SURFACE_CATALOG = ROOT / "assets" / "grid_v100" / "generated_surface_tiles.json"
GENERATED_TRANSITION_CATALOG = ROOT / "assets" / "grid_v100" / "generated_transition_objects.json"
SCREENSHOT_DIR = ROOT / "artifacts" / "map_workbench"
CITY_BLOCK_WORLD_SCALE = 0.5
CITY_BLOCK_TILE_WORLD = 128

PANEL_W = 330
BG = (12, 15, 20)
PANEL = (18, 23, 30)
PANEL_EDGE = (55, 69, 82)
TEXT = (225, 231, 235)
MUTED = (145, 158, 169)
ACCENT = (85, 210, 178)
YELLOW = (244, 203, 83)
WATER = (17, 60, 91)
ZONE_COLORS = {
    "medium": (58, 90, 66),
    "high": (84, 65, 67),
    "campus": (67, 74, 100),
    "water": WATER,
}
COLLISION_COLORS = {
    "blocked": (232, 74, 74, 100),
    "road": (83, 167, 255, 80),
    "sidewalk": (255, 208, 85, 75),
    "walk": (74, 220, 141, 70),
    "transition": (204, 98, 255, 100),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def watched_paths() -> list[Path]:
    files = [
        GRID_DATA_DIR / "ground_grid.json",
        GRID_DATA_DIR / "roof_grid.generated.json",
        GRID_DATA_DIR / "ground_generated_objects.json",
        ROOT / "assets" / "grid_v100" / "tile_catalog.json",
        ROOT / "assets" / "grid_v100" / "building_tiles.json",
        GENERATED_BUILDING_CATALOG,
        GENERATED_ART_CATALOG,
        GENERATED_SURFACE_CATALOG,
        GENERATED_TRANSITION_CATALOG,
        ROOT / "grid_renderer.py",
        ROOT / "grid_runtime.py",
    ]
    files.extend(V4_LAYOUT_DIR.glob("*.csv"))
    if CITY_BLOCK_DIR.is_dir():
        files.extend(path for path in CITY_BLOCK_DIR.rglob("*") if path.suffix.lower() in {".png", ".json"})
    return [path for path in files if path.is_file()]


def fingerprint() -> tuple[tuple[str, int, int], ...]:
    rows = []
    for path in watched_paths():
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        rows.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(rows))


@dataclass
class Camera:
    center_x: float = 0.0
    center_y: float = 0.0
    zoom: float = 0.1


class MapWorkbench:
    def __init__(self, *, start_mode: str = "layout", size: tuple[int, int] = (1440, 900)) -> None:
        pygame.init()
        pygame.display.set_caption("Open Night — Standalone Map Workbench")
        self.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("segoeui", 17)
        self.small = pygame.font.SysFont("segoeui", 14)
        self.title_font = pygame.font.SysFont("segoeui", 25, bold=True)
        self.mode = start_mode
        self.layer = "ground"
        self.camera = Camera()
        self.dragging = False
        self.drag_last = (0, 0)
        self.show_grid = False
        self.show_collision = False
        self.show_objects = False
        self.show_labels = True
        self.show_static_frontier = True
        self.show_transport = True
        self.show_population = True
        self.show_street_detail = True
        self.show_access = True
        self.auto_reload = True
        self.status = "Ready"
        self.status_color = ACCENT
        self.status_until = 0.0
        self.last_watch = 0.0
        self._fingerprint = fingerprint()
        self.world = None
        self.renderer = None
        self.layout: dict[str, list[dict[str, str]]] = {}
        self.layout_contract: dict[str, str] = {}
        self.catalog_tiles: dict[str, dict] = {}
        self.catalog_objects: dict[str, dict] = {}
        self._art_cache: dict[tuple[str, int, int, int], pygame.Surface] = {}
        self._clean_curb_sources: dict[str, pygame.Surface] = {}
        self.noise_frames = self._make_noise_frames()
        self.reload(reset_camera=True)

    @staticmethod
    def _make_noise_frames() -> list[pygame.Surface]:
        """Build a deterministic four-frame frontier loop without asset files."""
        frames = []
        palette = ((19, 22, 27), (34, 38, 44), (55, 58, 63), (81, 83, 86))
        for frame_index in range(4):
            rng = random.Random(0x0F3A_1100 + frame_index)
            surface = pygame.Surface((180, 112)).convert()
            for y in range(surface.get_height()):
                for x in range(surface.get_width()):
                    value = rng.random()
                    shade = palette[0 if value < 0.44 else 1 if value < 0.76 else 2 if value < 0.94 else 3]
                    surface.set_at((x, y), shade)
            frames.append(surface)
        return frames

    def draw_frontier(self, target: pygame.Surface) -> None:
        target.fill((9, 11, 15))
        if not self.show_static_frontier:
            return
        frame = self.noise_frames[int(time.monotonic() * 6) % len(self.noise_frames)]
        noise = pygame.transform.scale(frame, target.get_size())
        ww, wh = self.world_size
        tl = self.world_to_screen((0, 0))
        br = self.world_to_screen((ww, wh))
        world_rect = pygame.Rect(tl, (br[0] - tl[0], br[1] - tl[1]))
        bounds = target.get_rect()
        outside = (
            pygame.Rect(0, 0, bounds.width, max(0, min(bounds.height, world_rect.top))),
            pygame.Rect(0, max(0, world_rect.bottom), bounds.width, max(0, bounds.height - max(0, world_rect.bottom))),
            pygame.Rect(0, max(0, world_rect.top), max(0, min(bounds.width, world_rect.left)), max(0, min(bounds.height, world_rect.bottom) - max(0, world_rect.top))),
            pygame.Rect(max(0, world_rect.right), max(0, world_rect.top), max(0, bounds.width - max(0, world_rect.right)), max(0, min(bounds.height, world_rect.bottom) - max(0, world_rect.top))),
        )
        for rect in outside:
            rect = rect.clip(bounds)
            if rect.width and rect.height:
                target.blit(noise, rect.topleft, rect)

    @property
    def canvas_rect(self) -> pygame.Rect:
        return pygame.Rect(0, 0, max(1, self.screen.get_width() - PANEL_W), self.screen.get_height())

    @property
    def world_size(self) -> tuple[float, float]:
        if self.mode == "city" and self.world is not None:
            return float(self.world.world_w), float(self.world.world_h)
        return (
            float(self.layout_contract.get("world_width", 16384)),
            float(self.layout_contract.get("world_height", 10240)),
        )

    def set_status(self, message: str, color=ACCENT, seconds: float = 4.0) -> None:
        self.status = message
        self.status_color = color
        self.status_until = time.monotonic() + seconds
        print(f"[Map Workbench] {message}")

    def load_city(self) -> None:
        from grid_runtime import load_ground_grid, load_roof_grid
        from grid_renderer import GridRenderer

        load_ground_grid.cache_clear()
        load_roof_grid.cache_clear()
        self.world = load_ground_grid() if self.layer == "ground" else load_roof_grid()
        self.renderer = GridRenderer(self.world)

    def load_layout(self) -> None:
        if not (V4_LAYOUT_DIR / "streets.csv").is_file():
            from dev_tools.map_generator.tools.build_v4_approved_sprite_layout import build

            build()
        self.layout = {
            "streets": read_csv(V4_LAYOUT_DIR / "streets.csv"),
            "zones": read_csv(V4_LAYOUT_DIR / "district_zones.csv"),
            "houses": read_csv(V4_LAYOUT_DIR / "empty_houses.csv"),
            "slots": read_csv(V4_LAYOUT_DIR / "sprite_slots.csv"),
            "transport": read_csv(V4_LAYOUT_DIR / "transport.csv"),
            "population": read_csv(V4_LAYOUT_DIR / "population.csv"),
            "street_features": read_csv(V4_LAYOUT_DIR / "street_features.csv"),
            "access": read_csv(V4_LAYOUT_DIR / "building_access.csv"),
            "pavement_blocks": read_csv(V4_LAYOUT_DIR / "pavement_blocks.csv"),
        }
        contract_rows = read_csv(V4_LAYOUT_DIR / "layout_contract.csv")
        self.layout_contract = {row.get("key", ""): row.get("value", "") for row in contract_rows}
        self.catalog_tiles = {}
        self.catalog_objects = {}
        for catalog_path in (
            GENERATED_BUILDING_CATALOG,
            GENERATED_ART_CATALOG,
            GENERATED_SURFACE_CATALOG,
            GENERATED_TRANSITION_CATALOG,
        ):
            if not catalog_path.is_file():
                continue
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
            self.catalog_tiles.update(payload.get("tiles", {}))
            self.catalog_objects.update(payload.get("objects", {}))
        if not self.layout["streets"]:
            raise FileNotFoundError(
                f"Missing v4 layout data in {V4_LAYOUT_DIR}."
            )

    def reload(self, *, reset_camera: bool = False) -> None:
        try:
            self._art_cache.clear()
            self._clean_curb_sources.clear()
            self.load_layout()
            if self.mode == "city":
                self.load_city()
            self._fingerprint = fingerprint()
            if reset_camera:
                self.fit_world()
            self.set_status("Reloaded GWB map and generated art catalogs")
        except Exception as exc:
            self.set_status(f"Reload failed: {exc}", (255, 112, 112), 10.0)

    def regenerate(self) -> None:
        self.set_status("Regenerating Ground and Roof from city_block…", YELLOW, 30.0)
        pygame.display.flip()
        try:
            from dev_tools.map_generator.tools.build_v4_approved_sprite_layout import build as build_v4_layout
            from tools.generate_v100_ground_roof_layers import main as generate_layers

            build_v4_layout()
            generate_layers()
            self.reload()
            self.set_status("Regenerated Ground and Roof successfully")
        except Exception as exc:
            self.set_status(f"Regeneration failed: {exc}", (255, 112, 112), 12.0)

    def fit_world(self) -> None:
        ww, wh = self.world_size
        area = self.canvas_rect
        self.camera.center_x = ww / 2
        self.camera.center_y = wh / 2
        self.camera.zoom = max(0.015, min((area.width - 40) / ww, (area.height - 40) / wh))

    def camera_origin(self) -> tuple[float, float]:
        area = self.canvas_rect
        return (
            self.camera.center_x - area.width / (2 * self.camera.zoom),
            self.camera.center_y - area.height / (2 * self.camera.zoom),
        )

    def world_to_screen(self, point: tuple[float, float]) -> tuple[int, int]:
        ox, oy = self.camera_origin()
        return (
            int(round((point[0] - ox) * self.camera.zoom)),
            int(round((point[1] - oy) * self.camera.zoom)),
        )

    def screen_to_world(self, point: tuple[int, int]) -> tuple[float, float]:
        ox, oy = self.camera_origin()
        return (ox + point[0] / self.camera.zoom, oy + point[1] / self.camera.zoom)

    def zoom_at(self, screen_pos: tuple[int, int], factor: float) -> None:
        if not self.canvas_rect.collidepoint(screen_pos):
            return
        before = self.screen_to_world(screen_pos)
        self.camera.zoom = max(0.012, min(2.0, self.camera.zoom * factor))
        after = self.screen_to_world(screen_pos)
        self.camera.center_x += before[0] - after[0]
        self.camera.center_y += before[1] - after[1]

    def set_mode(self, mode: str) -> None:
        if mode == self.mode:
            return
        self.mode = mode
        self.reload(reset_camera=True)
        self.set_status("City Block runtime view" if mode == "city" else "Approved v4 layout view")

    def set_layer(self, layer: str) -> None:
        if layer == self.layer:
            return
        self.layer = layer
        if self.mode == "city":
            self.reload()
        self.set_status(f"Showing {layer.title()} layer")

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                return False
            if event.key == pygame.K_1:
                self.set_mode("layout")
            elif event.key == pygame.K_2:
                self.set_mode("city")
            elif event.key == pygame.K_g:
                self.set_layer("ground")
            elif event.key == pygame.K_r and not (event.mod & pygame.KMOD_CTRL):
                self.set_layer("roof")
            elif event.key == pygame.K_r and event.mod & pygame.KMOD_CTRL:
                self.regenerate()
            elif event.key == pygame.K_u:
                self.set_layer("underground")
            elif event.key == pygame.K_F5:
                self.reload()
            elif event.key == pygame.K_f:
                self.fit_world()
            elif event.key == pygame.K_c:
                self.show_collision = not self.show_collision
            elif event.key == pygame.K_i:
                self.show_grid = not self.show_grid
            elif event.key == pygame.K_o:
                self.show_objects = not self.show_objects
            elif event.key == pygame.K_l:
                self.show_labels = not self.show_labels
            elif event.key == pygame.K_n:
                self.show_static_frontier = not self.show_static_frontier
            elif event.key == pygame.K_t:
                self.show_transport = not self.show_transport
            elif event.key == pygame.K_y:
                self.show_population = not self.show_population
            elif event.key == pygame.K_d and event.mod & pygame.KMOD_CTRL:
                self.show_street_detail = not self.show_street_detail
            elif event.key == pygame.K_b:
                self.show_access = not self.show_access
            elif event.key == pygame.K_h:
                self.auto_reload = not self.auto_reload
                self.set_status(f"Hot reload {'on' if self.auto_reload else 'off'}")
            elif event.key == pygame.K_p:
                self.save_screenshot()
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.canvas_rect.collidepoint(event.pos):
                self.dragging = True
                self.drag_last = event.pos
            elif event.button == 4:
                self.zoom_at(event.pos, 1.18)
            elif event.button == 5:
                self.zoom_at(event.pos, 1 / 1.18)
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        if event.type == pygame.MOUSEMOTION and self.dragging:
            dx = event.pos[0] - self.drag_last[0]
            dy = event.pos[1] - self.drag_last[1]
            self.camera.center_x -= dx / self.camera.zoom
            self.camera.center_y -= dy / self.camera.zoom
            self.drag_last = event.pos
        if event.type == pygame.MOUSEWHEEL:
            self.zoom_at(pygame.mouse.get_pos(), 1.18 ** event.y)
        return True

    def update(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        speed = 850.0 / max(0.05, self.camera.zoom)
        if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
            speed *= 2.2
        self.camera.center_x += (keys[pygame.K_d] - keys[pygame.K_a]) * speed * dt
        self.camera.center_y += (keys[pygame.K_s] - keys[pygame.K_w]) * speed * dt

        now = time.monotonic()
        if self.auto_reload and now - self.last_watch > 1.0:
            self.last_watch = now
            current = fingerprint()
            if current != self._fingerprint:
                self.reload()

    def draw_city(self, target: pygame.Surface) -> None:
        if self.world is None or self.renderer is None:
            return
        self.draw_frontier(target)
        world = self.world
        renderer = self.renderer
        zoom = self.camera.zoom
        cam_x, cam_y = self.camera_origin()
        view_world_w = self.canvas_rect.width / zoom
        view_world_h = self.canvas_rect.height / zoom
        tile_px = max(1, int(round(world.cell_px * zoom)))

        for gx, gy in world.visible_cells(cam_x, cam_y, math.ceil(view_world_w), math.ceil(view_world_h)):
            tile_id = world.tile_id(self.layer, gx, gy)
            if tile_id == "void" and self.layer == "roof":
                continue
            image = renderer._tile_surface_scaled(renderer._visual_tile_id(tile_id, gx, gy), tile_px)
            sx = int(round((gx * world.cell_px - cam_x) * zoom))
            sy = int(round((gy * world.cell_px - cam_y) * zoom))
            target.blit(image, (sx, sy))

        object_layers = (self.layer,)
        if self.layer == "ground" and "roof" in world.layers:
            for gx, gy in world.visible_cells(cam_x, cam_y, math.ceil(view_world_w), math.ceil(view_world_h)):
                tile_id = world.tile_id("roof", gx, gy)
                if tile_id == "void":
                    continue
                image = renderer._tile_surface_scaled(renderer._visual_tile_id(tile_id, gx, gy), tile_px)
                sx = int(round((gx * world.cell_px - cam_x) * zoom))
                sy = int(round((gy * world.cell_px - cam_y) * zoom))
                target.blit(image, (sx, sy))
            object_layers = ("ground", "roof")

        for _z, asset_id, item, wx, wy, width, height in renderer._visible_objects_for_layers(
            (cam_x, cam_y), math.ceil(view_world_w), math.ceil(view_world_h), object_layers
        ):
            image = renderer._object_surface(asset_id, width, height, float(item.get("rotation", 0.0)))
            size = (max(1, int(round(image.get_width() * zoom))), max(1, int(round(image.get_height() * zoom))))
            image = pygame.transform.scale(image, size)
            target.blit(image, (int(round((wx - cam_x) * zoom)), int(round((wy - cam_y) * zoom))))

        if self.show_collision:
            overlay = pygame.Surface(target.get_size(), pygame.SRCALPHA)
            for gx, gy in world.visible_cells(cam_x, cam_y, math.ceil(view_world_w), math.ceil(view_world_h)):
                collision = world.tile(self.layer, gx, gy).collision
                color = COLLISION_COLORS.get(collision)
                if color:
                    x = int(round((gx * world.cell_px - cam_x) * zoom))
                    y = int(round((gy * world.cell_px - cam_y) * zoom))
                    pygame.draw.rect(overlay, color, (x, y, tile_px, tile_px))
            target.blit(overlay, (0, 0))

        if self.show_grid and tile_px >= 5:
            color = (235, 242, 247, 50)
            overlay = pygame.Surface(target.get_size(), pygame.SRCALPHA)
            for gx, gy in world.visible_cells(cam_x, cam_y, math.ceil(view_world_w), math.ceil(view_world_h)):
                x = int(round((gx * world.cell_px - cam_x) * zoom))
                y = int(round((gy * world.cell_px - cam_y) * zoom))
                pygame.draw.rect(overlay, color, (x, y, tile_px, tile_px), 1)
            target.blit(overlay, (0, 0))

        if self.show_objects:
            for item in world.objects:
                if str(item.get("layer", "ground")) not in object_layers:
                    continue
                wx = int(item.get("gx", 0)) * world.cell_px + float(item.get("offset_x_px", 0))
                wy = int(item.get("gy", 0)) * world.cell_px + float(item.get("offset_y_px", 0))
                w = float(item.get("width_px", world.cell_px))
                h = float(item.get("height_px", world.cell_px))
                rect = pygame.Rect(self.world_to_screen((wx, wy)), (max(1, int(w * zoom)), max(1, int(h * zoom))))
                pygame.draw.rect(target, (255, 94, 201), rect, 1)

    def _repo_art(self, relative: str, size: tuple[int, int], rotation: int = 0) -> pygame.Surface:
        """Load and scale one repository sprite with a screen-size cache."""
        width, height = max(1, int(size[0])), max(1, int(size[1]))
        key = (relative, width, height, int(rotation) % 360)
        cached = self._art_cache.get(key)
        if cached is not None:
            return cached
        source = ROOT / relative
        image = pygame.image.load(str(source)).convert_alpha()
        image = pygame.transform.smoothscale(image, (width, height))
        if rotation % 360:
            image = pygame.transform.rotate(image, -rotation)
        self._art_cache[key] = image
        return image

    def _art(self, relative: str, size: tuple[int, int], rotation: int = 0) -> pygame.Surface:
        return self._repo_art(f"assets/source_packs/city_block/{relative}", size, rotation)

    def _catalog_art(self, asset_id: str, size: tuple[int, int], rotation: int = 0) -> pygame.Surface:
        """Resolve generated artwork through the shared map catalogs."""
        definition = self.catalog_tiles.get(asset_id) or self.catalog_objects.get(asset_id)
        if not definition or not definition.get("image"):
            return pygame.Surface((max(1, size[0]), max(1, size[1])), pygame.SRCALPHA)
        try:
            return self._repo_art(str(definition["image"]), size, rotation)
        except (FileNotFoundError, pygame.error):
            if not definition.get("optional", False):
                raise
            return pygame.Surface((max(1, size[0]), max(1, size[1])), pygame.SRCALPHA)

    def _catalog_object_size(self, asset_id: str, world_height: float) -> tuple[int, int]:
        definition = self.catalog_objects.get(asset_id, {})
        native_w = max(1.0, float(definition.get("native_width_px", world_height)))
        native_h = max(1.0, float(definition.get("native_height_px", world_height)))
        height = max(2, int(round(world_height * self.camera.zoom)))
        return max(2, int(round(height * native_w / native_h))), height

    def _tile_catalog_region(
        self,
        target: pygame.Surface,
        asset_ids: tuple[str, ...],
        rect: pygame.Rect,
        *,
        world_tile: int = CITY_BLOCK_TILE_WORLD,
        seed: int = 0,
    ) -> None:
        """Tile deterministic generated variants over one projected region."""
        if not asset_ids:
            return
        tile_px = max(2, int(round(world_tile * self.camera.zoom)))
        clipped = rect.clip(target.get_rect())
        if not clipped.width or not clipped.height:
            return
        previous = target.get_clip()
        target.set_clip(clipped)
        start_x = math.floor(rect.left / tile_px) * tile_px
        start_y = math.floor(rect.top / tile_px) * tile_px
        for sy in range(start_y, rect.bottom, tile_px):
            for sx in range(start_x, rect.right, tile_px):
                tx, ty = sx // tile_px, sy // tile_px
                index = ((tx * 73856093) ^ (ty * 19349663) ^ seed) % len(asset_ids)
                image = self._catalog_art(asset_ids[index], (tile_px, tile_px))
                target.blit(image, (sx, sy))
        target.set_clip(previous)

    def _draw_textured_roads(
        self,
        target: pygame.Surface,
        road_draws: list[tuple[str, tuple[int, int], tuple[int, int], int, int]],
    ) -> None:
        """Mask seamless asphalt variants to the authored GWB road geometry."""
        texture = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        self._tile_catalog_region(
            texture,
            tuple(f"road_asphalt_variant_{index}" for index in range(4)),
            target.get_rect(),
            world_tile=256,
            seed=0xA54A,
        )
        mask = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        for _road_class, a, b, _outer, inner in road_draws:
            pygame.draw.line(mask, (255, 255, 255, 255), a, b, inner)
        texture.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        target.blit(texture, (0, 0))

    def _curb_art(self, relative: str, size: tuple[int, int], rotation: int = 0) -> pygame.Surface:
        """Render the native curb without its baked square grey road shoulder.

        The city_block curb PNGs include a mid-grey roadway field around the
        actual sidewalk and curb.  That field exposes every 256px module as a
        rectangular halo when it is placed over Open Night's darker asphalt.
        Masking only the low-saturation midtones keeps the pavement, curb face,
        black outline, and antialiased edge while allowing our asphalt to meet
        the curb directly.
        """
        width, height = max(1, int(size[0])), max(1, int(size[1]))
        cache_key = (f"clean-curb:{relative}", width, height, int(rotation) % 360)
        cached = self._art_cache.get(cache_key)
        if cached is not None:
            return cached
        source = self._clean_curb_sources.get(relative)
        if source is None:
            source = pygame.image.load(
                str(CITY_BLOCK_DIR / "road_and_pavement_tileset" / relative)
            ).convert_alpha()
            source = source.copy()
            for y in range(source.get_height()):
                for x in range(source.get_width()):
                    r, g, b, alpha = source.get_at((x, y))
                    average = (int(r) + int(g) + int(b)) / 3.0
                    chroma = max(r, g, b) - min(r, g, b)
                    if alpha and 48 <= average <= 128 and chroma <= 38:
                        source.set_at((x, y), (r, g, b, 0))
            self._clean_curb_sources[relative] = source
        image = pygame.transform.smoothscale(source, (width, height))
        if rotation % 360:
            image = pygame.transform.rotate(image, -rotation)
        self._art_cache[cache_key] = image
        return image

    def _tile_world_region(self, target: pygame.Surface, relative: str, rect: pygame.Rect, world_tile: int = CITY_BLOCK_TILE_WORLD) -> None:
        tile_px = max(2, int(round(world_tile * self.camera.zoom)))
        tile = self._art(relative, (tile_px, tile_px))
        clipped = rect.clip(target.get_rect())
        if not clipped.width or not clipped.height:
            return
        start_x = math.floor(clipped.left / tile_px) * tile_px
        start_y = math.floor(clipped.top / tile_px) * tile_px
        previous = target.get_clip()
        target.set_clip(clipped)
        for sy in range(start_y, clipped.bottom, tile_px):
            for sx in range(start_x, clipped.right, tile_px):
                target.blit(tile, (sx, sy))
        target.set_clip(previous)

    def _tile_repo_region(self, target: pygame.Surface, relative: str, rect: pygame.Rect, world_tile: int = 320) -> None:
        """Tile a repository texture over a projected world rectangle."""
        tile_px = max(2, int(round(world_tile * self.camera.zoom)))
        tile = self._repo_art(relative, (tile_px, tile_px))
        clipped = rect.clip(target.get_rect())
        if not clipped.width or not clipped.height:
            return
        previous = target.get_clip()
        target.set_clip(clipped)
        for sy in range(rect.top, rect.bottom, tile_px):
            for sx in range(rect.left, rect.right, tile_px):
                target.blit(tile, (sx, sy))
        target.set_clip(previous)

    @staticmethod
    def _distance_to_segment(px: float, py: float, road: dict) -> float:
        x1, y1, x2, y2 = (number(road, key) for key in ("x1", "y1", "x2", "y2"))
        dx, dy = x2 - x1, y2 - y1
        length_sq = max(1.0, dx * dx + dy * dy)
        fraction = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
        return math.hypot(px - (x1 + dx * fraction), py - (y1 + dy * fraction))

    def _draw_tiled_curbs(self, target: pygame.Surface, roads: list[dict], road_widths: dict[str, int]) -> None:
        """Render the coordinated generated curb grammar along GWB streets."""
        land_roads = [road for road in roads if road.get("road_class") != "bridge"]
        # Scale correction: one native 256px curb cell represents 128 world
        # units, matching the denser v3 visual scale without changing roads.
        tile_world = CITY_BLOCK_TILE_WORLD
        tile_px = max(4, int(round(tile_world * self.camera.zoom)))
        for road in land_roads:
            x1, y1, x2, y2 = (number(road, key) for key in ("x1", "y1", "x2", "y2"))
            dx, dy = x2 - x1, y2 - y1
            length = max(1.0, math.hypot(dx, dy))
            ux, uy = dx / length, dy / length
            nx, ny = -uy, ux
            half = road_widths.get(str(road.get("road_class")), 235) * 0.5
            samples = max(1, math.ceil(length / tile_world))
            angle = int(round(math.degrees(math.atan2(dy, dx)))) % 360
            for index in range(samples + 1):
                distance = min(length, index * tile_world)
                px, py = x1 + ux * distance, y1 + uy * distance
                if road.get("orientation") == "horizontal":
                    sides = ((-1, "curb_top", 0), (1, "curb_bottom", 0))
                elif abs(dx) < 1.0:
                    sides = ((1, "curb_left", 0), (-1, "curb_right", 0))
                else:
                    sides = ((-1, "curb_top", angle), (1, "curb_bottom", angle))
                for sign, asset, rotation in sides:
                    blocked = False
                    for other in land_roads:
                        if other is road or self._distance_to_segment(px, py, other) > road_widths.get(str(other.get("road_class")), 235) * 0.5 + tile_world * 0.25:
                            continue
                        if road.get("orientation") == "horizontal" and other.get("orientation") == "vertical":
                            junction_y = y1
                            blocked = (sign < 0 and junction_y > min(number(other, "y1"), number(other, "y2")) + 1) or (sign > 0 and junction_y < max(number(other, "y1"), number(other, "y2")) - 1)
                        elif road.get("orientation") == "vertical" and other.get("orientation") == "horizontal" and abs(dx) < 1.0:
                            junction_x = x1
                            blocked = (sign > 0 and junction_x > min(number(other, "x1"), number(other, "x2")) + 1) or (sign < 0 and junction_x < max(number(other, "x1"), number(other, "x2")) - 1)
                        else:
                            blocked = True
                        if blocked:
                            break
                    if blocked:
                        continue
                    center = self.world_to_screen((px + nx * half * sign, py + ny * half * sign))
                    image = self._catalog_art(asset, (tile_px, tile_px), rotation)
                    target.blit(image, image.get_rect(center=center))

        horizontal = [road for road in land_roads if road.get("orientation") == "horizontal"]
        vertical = [road for road in land_roads if road.get("orientation") == "vertical" and abs(number(road, "x2") - number(road, "x1")) < 1]
        corner_assets = (
            (-1, -1, "curb_br_inner"),
            (1, -1, "curb_bl_inner"),
            (-1, 1, "curb_tr_inner"),
            (1, 1, "curb_tl_inner"),
        )
        for hroad in horizontal:
            iy = number(hroad, "y1")
            hhalf = road_widths.get(str(hroad.get("road_class")), 235) * 0.5
            for vroad in vertical:
                ix = number(vroad, "x1")
                if not min(number(hroad, "x1"), number(hroad, "x2")) <= ix <= max(number(hroad, "x1"), number(hroad, "x2")):
                    continue
                if not min(number(vroad, "y1"), number(vroad, "y2")) <= iy <= max(number(vroad, "y1"), number(vroad, "y2")):
                    continue
                vhalf = road_widths.get(str(vroad.get("road_class")), 235) * 0.5
                for sx, sy, asset in corner_assets:
                    h_arm = ix > min(number(hroad, "x1"), number(hroad, "x2")) + 1 if sx < 0 else ix < max(number(hroad, "x1"), number(hroad, "x2")) - 1
                    v_arm = iy > min(number(vroad, "y1"), number(vroad, "y2")) + 1 if sy < 0 else iy < max(number(vroad, "y1"), number(vroad, "y2")) - 1
                    if not (h_arm and v_arm):
                        continue
                    center = self.world_to_screen((ix + sx * vhalf, iy + sy * hhalf))
                    image = self._catalog_art(asset, (tile_px, tile_px))
                    target.blit(image, image.get_rect(center=center))

    def _draw_lane_markings(self, target: pygame.Surface, roads: list[dict], road_widths: dict[str, int]) -> None:
        """White dashed separators: four regular lanes and nine GWB lanes."""
        regular_lanes = int(float(self.layout_contract.get("regular_lane_count", 4)))
        bridge_lanes = int(float(self.layout_contract.get("gwb_lane_count", 9)))
        marking_world = 128.0
        marking_px = max(4, int(round(marking_world * self.camera.zoom)))
        crossing_exclusions: dict[str, list[tuple[float, float]]] = {}
        for crossing in self.layout.get("street_features", []):
            if crossing.get("kind") != "crosswalk" or ":" not in str(crossing.get("group", "")):
                continue
            junction, approach = str(crossing["group"]).rsplit(":", 1)
            if "+" not in junction:
                continue
            horizontal_id, vertical_id = junction.split("+", 1)
            crossed_road = vertical_id if approach in {"north", "south"} else horizontal_id
            crossing_exclusions.setdefault(crossed_road, []).append((number(crossing, "x"), number(crossing, "y")))
        for road in roads:
            x1, y1, x2, y2 = (number(road, key) for key in ("x1", "y1", "x2", "y2"))
            dx, dy = x2 - x1, y2 - y1
            length = max(1.0, math.hypot(dx, dy))
            ux, uy = dx / length, dy / length
            nx, ny = -uy, ux
            road_class = str(road.get("road_class", "residential"))
            lanes = bridge_lanes if road_class == "bridge" else regular_lanes
            width_world = road_widths.get(road_class, 420)
            lane_width = width_world / lanes
            for divider in range(1, lanes):
                offset = -width_world * 0.5 + lane_width * divider
                distance = marking_world * 0.5
                while distance < length:
                    midpoint_x = x1 + ux * distance
                    midpoint_y = y1 + uy * distance
                    crosses_zebra = any(
                        math.hypot(midpoint_x - crossing_x, midpoint_y - crossing_y)
                        <= marking_world * 0.5 + 125
                        for crossing_x, crossing_y in crossing_exclusions.get(str(road.get("street_id", "")), [])
                    )
                    if any(
                        other is not road
                        and self._distance_to_segment(midpoint_x, midpoint_y, other)
                        <= road_widths.get(str(other.get("road_class")), 420) * 0.5 + marking_world * 0.5 + 70
                        for other in roads
                    ) or crosses_zebra:
                        distance += marking_world
                        continue
                    center = self.world_to_screen((midpoint_x + nx * offset, midpoint_y + ny * offset))
                    angle = int(round(math.degrees(math.atan2(dy, dx)))) % 360
                    image = self._catalog_art(
                        "mark_dashed_white_lane",
                        (marking_px, marking_px),
                        (90 - angle) % 360,
                    )
                    target.blit(image, image.get_rect(center=center))
                    distance += marking_world

    def _draw_modular_building(self, target: pygame.Surface, row: dict, *, player_house: bool = False) -> None:
        x, y, w, h = (number(row, key) for key in ("x", "y", "w", "h"))
        rect = pygame.Rect(
            self.world_to_screen((x, y)),
            (max(4, int(round(w * self.camera.zoom))), max(4, int(round(h * self.camera.zoom)))),
        )
        if not rect.colliderect(target.get_rect()):
            return
        identity = str(row.get("housing_id") or row.get("slot_id") or "building")
        themes = ("blue", "dark_green", "green", "red", "yellow")
        stable = sum((index + 1) * ord(char) for index, char in enumerate(identity))
        theme = themes[stable % len(themes)]
        nx = max(3, min(12, int(math.ceil(w / CITY_BLOCK_TILE_WORLD))))
        ny = max(3, min(12, int(math.ceil(h / CITY_BLOCK_TILE_WORLD))))
        cell_w = max(2, math.ceil(rect.width / nx))
        cell_h = max(2, math.ceil(rect.height / ny))

        occupied = {(gx, gy) for gy in range(ny) for gx in range(nx)}
        shape = str(row.get("shape", "rectangle"))
        notch_w = max(1, nx // 3)
        notch_h = max(1, ny // 3)
        if shape.startswith("notch_"):
            north = shape.endswith(("ne", "nw"))
            east = shape.endswith(("ne", "se"))
            xs = range(nx - notch_w, nx) if east else range(notch_w)
            ys = range(notch_h) if north else range(ny - notch_h, ny)
            occupied.difference_update((gx, gy) for gy in ys for gx in xs)
        elif shape == "courtyard" and nx >= 3 and ny >= 3:
            # A real open center, while retaining a one-tile street wall.
            occupied.difference_update(
                (gx, gy)
                for gy in range(1, ny - 1)
                for gx in range(1, nx - 1)
            )

        if self.layer == "ground":
            shadow_dx = max(1, int(24 * self.camera.zoom))
            shadow_dy = max(1, int(30 * self.camera.zoom))
            shadow_layer = pygame.Surface(
                (max(1, rect.width + shadow_dx), max(1, rect.height + shadow_dy)),
                pygame.SRCALPHA,
            )
            for gx, gy in occupied:
                cell = pygame.Rect(gx * cell_w + shadow_dx, gy * cell_h + shadow_dy, cell_w, cell_h)
                pygame.draw.rect(shadow_layer, (5, 7, 9, 22), cell)
            target.blit(shadow_layer, rect.topleft)

        for gy in range(ny):
            for gx in range(nx):
                if (gx, gy) not in occupied:
                    continue
                north = (gx, gy - 1) in occupied
                south = (gx, gy + 1) in occupied
                west = (gx - 1, gy) in occupied
                east = (gx + 1, gy) in occupied
                northwest = (gx - 1, gy - 1) in occupied
                northeast = (gx + 1, gy - 1) in occupied
                southwest = (gx - 1, gy + 1) in occupied
                southeast = (gx + 1, gy + 1) in occupied
                if north and south and west and east and not northwest:
                    role = "top_left_inner"
                elif north and south and west and east and not northeast:
                    role = "top_right_inner"
                elif north and south and west and east and not southwest:
                    role = "bottom_left_inner"
                elif north and south and west and east and not southeast:
                    role = "bottom_right_inner"
                elif not north and not west:
                    role = "top_left_outer"
                elif not north and not east:
                    role = "top_right_outer"
                elif not south and not west:
                    role = "bottom_left_outer"
                elif not south and not east:
                    role = "bottom_right_outer"
                elif not north:
                    role = "top_center"
                elif not south:
                    role = "bottom_center"
                elif not west:
                    role = "left"
                elif not east:
                    role = "right"
                else:
                    role = "fill"
                sprite = self._catalog_art(f"bld_{theme}_{role}", (cell_w, cell_h))
                target.blit(sprite, (rect.x + gx * cell_w, rect.y + gy * cell_h))

        # The modular parapets already describe the exact occupied footprint.
        # A second procedural perimeter stroke used to create conspicuous black
        # rectangles around both Ground buildings and Roof footprints.
        if not player_house and stable % 3 == 0 and rect.width >= 12 and rect.height >= 12:
            props = (
                "rooflayer_aircon",
                "rooflayer_aircon_large",
                "rooflayer_blue_roof",
                "rooflayer_green_roof",
                "rooflayer_grey_roof",
                "rooflayer_orange_roof",
                "rooflayer_water_brown",
                "rooflayer_water_green",
                "rooflayer_water_red",
            )
            prop = props[stable % len(props)]
            size = max(4, int(min(cell_w, cell_h) * 0.72))
            definition = self.catalog_objects.get(prop, {})
            native_w = max(1.0, float(definition.get("native_width_px", 1)))
            native_h = max(1.0, float(definition.get("native_height_px", 1)))
            prop_size = (max(3, int(size * native_w / native_h)), size)
            image = self._catalog_art(prop, prop_size)
            roof_cell = min(occupied, key=lambda point: abs(point[0] - (nx - 1) / 2) + abs(point[1] - (ny - 1) / 2))
            center = (rect.x + roof_cell[0] * cell_w + cell_w // 2, rect.y + roof_cell[1] * cell_h + cell_h // 2)
            target.blit(image, image.get_rect(center=center))
        if self.show_objects:
            pygame.draw.rect(target, (255, 94, 201), rect, 1)

    def _draw_buzzer(self, target: pygame.Surface, house: dict) -> None:
        if str(house.get("buzzer_enabled", "")).lower() != "true":
            return
        # Separate artwork and interaction placement: the small buzzer sits
        # beside the door but does not inherit its collision footprint.
        point = self.world_to_screen((number(house, "buzzer_x") + 48, number(house, "buzzer_y")))
        size = self._catalog_object_size("entrance_buzzer", 26)
        image = self._catalog_art("entrance_buzzer", size)
        target.blit(image, image.get_rect(midbottom=point))

    def _draw_street_features(self, target: pygame.Surface) -> None:
        if not self.show_street_detail:
            return
        for row in self.layout.get("street_features", []):
            kind = row.get("kind", "")
            p = self.world_to_screen((number(row, "x"), number(row, "y")))
            rotation = int(number(row, "rotation"))
            if kind == "crosswalk":
                # `rotation` is the pedestrian crossing axis. Zebra bars run
                # perpendicular to that axis (parallel to traffic), and repeat
                # across the full curb-to-curb span.
                span_world = number(row, "length", 360)
                pieces = max(5, int(round(span_world / 62)))
                stripe_canvas = max(6, int(150 * self.camera.zoom))
                span = max(8, int(span_world * self.camera.zoom))
                for index in range(pieces):
                    offset = -span / 2 + (index + 0.5) * span / pieces
                    if rotation % 180 == 90:
                        center = (p[0], round(p[1] + offset))
                        image = self._catalog_art("mark_zebra_crossing", (stripe_canvas, stripe_canvas), 90)
                    else:
                        center = (round(p[0] + offset), p[1])
                        image = self._catalog_art("mark_zebra_crossing", (stripe_canvas, stripe_canvas))
                    target.blit(image, image.get_rect(center=center))
                # Ramps are authored only at actual crossings, never scattered
                # randomly along a curb or on the river/beach side.
                ramp_px = max(5, int(CITY_BLOCK_TILE_WORLD * self.camera.zoom))
                if rotation % 180 == 90:
                    ramps = (
                        ((p[0], round(p[1] - span / 2)), "curb_ramp_top"),
                        ((p[0], round(p[1] + span / 2)), "curb_ramp_bottom"),
                    )
                else:
                    ramps = (
                        ((round(p[0] - span / 2), p[1]), "curb_ramp_left"),
                        ((round(p[0] + span / 2), p[1]), "curb_ramp_right"),
                    )
                for center, asset_id in ramps:
                    ramp = self._catalog_art(asset_id, (ramp_px, ramp_px))
                    target.blit(ramp, ramp.get_rect(center=center))
                continue
            if kind == "traffic_signal":
                states = (
                    "traffic_red_not_clear",
                    "traffic_yellow_not_clear",
                    "traffic_green_not_clear",
                    "traffic_red_clear",
                    "traffic_yellow_clear",
                    "traffic_green_clear",
                )
                group_seed = sum((index + 1) * ord(char) for index, char in enumerate(str(row.get("group", ""))))
                asset_id = states[(pygame.time.get_ticks() // 800 + group_seed) % len(states)]
                size = self._catalog_object_size(asset_id, 155)
                image = self._catalog_art(asset_id, size, rotation)
                target.blit(image, image.get_rect(center=p))
                continue
            paths = {
                "street_lamp": ("repo", "assets/street_props/curved_streetlamp.png", 150),
                "street_tree": ("catalog", "v4_art_tree", 185),
                "fire_hydrant": ("catalog", "v4_art_hydrant", 62),
                "telephone": ("catalog", "v4_art_phone_box", 78),
                "traffic_cone": ("catalog", "v4_art_cone", 46),
                "manhole": ("repo", "assets/source_packs/city_block/road_overlays/man_hole.png", 52),
            }
            if kind not in paths:
                continue
            source_kind, path, world_size = paths[kind]
            definition = self.catalog_objects.get(path, {}) if source_kind == "catalog" else {}
            native_w = max(1.0, float(definition.get("native_width_px", 1)))
            native_h = max(1.0, float(definition.get("native_height_px", 1)))
            height = max(4, int(world_size * self.camera.zoom))
            width = max(4, int(height * native_w / native_h)) if definition else height
            image = self._catalog_art(path, (width, height), rotation) if source_kind == "catalog" else self._repo_art(path, (width, height), rotation)
            target.blit(image, image.get_rect(center=p))

    def _draw_transport(self, target: pygame.Surface) -> None:
        if not self.show_transport:
            return
        for row in self.layout.get("transport", []):
            kind = row.get("kind", "")
            p = self.world_to_screen((number(row, "x"), number(row, "y")))
            rotation = int(number(row, "rotation"))
            if kind == "parking_space":
                w = max(5, int(105 * self.camera.zoom))
                h = max(8, int(220 * self.camera.zoom))
                rect = pygame.Rect(0, 0, w, h)
                rect.center = p
                pygame.draw.rect(target, (191, 196, 191), rect, 1)
                continue
            variant = int(number(row, "variant")) % 28
            width = max(5, int(105 * self.camera.zoom))
            height = max(9, int(230 * self.camera.zoom))
            image = self._repo_art(f"assets/source_packs/gen_vehicles/gen_vehicle_{variant:02d}.png", (width, height), rotation)
            target.blit(image, image.get_rect(center=p))

    def _draw_population(self, target: pygame.Surface) -> None:
        if not self.show_population:
            return
        for row in self.layout.get("population", []):
            kind = row.get("kind", "")
            level = int(number(row, "level"))
            if self.layer == "roof" and level != 1:
                continue
            if self.layer == "underground":
                continue
            p = self.world_to_screen((number(row, "x"), number(row, "y")))
            if kind in {"supplier", "buyer"}:
                color = (92, 224, 141) if kind == "supplier" else (244, 112, 96)
                radius = max(4, int(55 * self.camera.zoom))
                pygame.draw.polygon(target, color, ((p[0], p[1] - radius), (p[0] + radius, p[1]), (p[0], p[1] + radius), (p[0] - radius, p[1])))
            elif kind == "dog":
                pygame.draw.circle(target, (193, 144, 75), p, max(2, int(26 * self.camera.zoom)))
            else:
                color = (255, 210, 105) if kind == "dog_walker" else (103, 210, 232)
                pygame.draw.circle(target, color, p, max(2, int(22 * self.camera.zoom)))

        # Leashes make the three one-to-one pairs explicit at overview scale.
        pairs: dict[str, list[tuple[int, int]]] = {}
        for row in self.layout.get("population", []):
            if self.layer != "ground":
                continue
            role = row.get("role", "")
            if role.startswith("walker_pair_"):
                pairs.setdefault(role, []).append(self.world_to_screen((number(row, "x"), number(row, "y"))))
        for points in pairs.values():
            if len(points) == 2:
                pygame.draw.line(target, (224, 210, 171), points[0], points[1], 1)

    def _draw_access(self, target: pygame.Surface) -> None:
        if not self.show_access:
            return
        for row in self.layout.get("access", []):
            if self.layer == "underground":
                continue
            kind = str(row.get("kind", ""))
            if self.layer == "roof" and kind not in {"fire_escape", "roof_access_door"}:
                continue
            if self.layer == "ground" and kind == "roof_access_door":
                continue
            p = self.world_to_screen((number(row, "x"), number(row, "y")))
            asset_id, world_height, anchor = {
                "player_house_door": ("entrance_door", 78, "midbottom"),
                "public_door": ("entrance_door", 78, "midbottom"),
                "roof_access_door": ("roof_access_door", 74, "center"),
                "elevator_transition": ("elevator_transition", 78, "midbottom"),
                "fire_escape": ("fire_escape_ladder", 112, "center"),
            }.get(kind, ("", 0, "center"))
            if not asset_id:
                continue
            size = self._catalog_object_size(asset_id, world_height)
            image = self._catalog_art(asset_id, size, int(number(row, "rotation")))
            image_rect = image.get_rect()
            setattr(image_rect, anchor, p)
            target.blit(image, image_rect)

    def _draw_underground(self, target: pygame.Surface) -> None:
        self.draw_frontier(target)
        ww, wh = self.world_size
        tl = self.world_to_screen((0, 0))
        br = self.world_to_screen((ww, wh))
        world_rect = pygame.Rect(tl, (br[0] - tl[0], br[1] - tl[1]))
        pygame.draw.rect(target, (21, 23, 27), world_rect)
        for road in self.layout.get("streets", []):
            if road.get("road_class") not in {"primary", "secondary", "bridge"}:
                continue
            a = self.world_to_screen((number(road, "x1"), number(road, "y1")))
            b = self.world_to_screen((number(road, "x2"), number(road, "y2")))
            outer = max(4, int(250 * self.camera.zoom))
            inner = max(2, int(150 * self.camera.zoom))
            pygame.draw.line(target, (82, 79, 72), a, b, outer)
            pygame.draw.line(target, (35, 37, 40), a, b, inner)
            pygame.draw.line(target, (182, 149, 72), a, b, 1)
        for row in self.layout.get("street_features", []):
            if row.get("kind") != "manhole":
                continue
            p = self.world_to_screen((number(row, "x"), number(row, "y")))
            radius = max(4, int(90 * self.camera.zoom))
            pygame.draw.circle(target, (115, 101, 73), p, radius)
            pygame.draw.circle(target, (226, 191, 93), p, radius, 1)
        label = self.title_font.render("UNDERGROUND — MANHOLE / SERVICE NETWORK", True, (222, 193, 116))
        target.blit(label, (max(16, world_rect.left + 16), max(16, world_rect.top + 16)))

    def draw_layout(self, target: pygame.Surface) -> None:
        """Render the new art-first v4 preview from authored data and city_block."""
        if self.layer == "underground":
            self._draw_underground(target)
            return
        self.draw_frontier(target)
        ww, wh = self.world_size
        tl = self.world_to_screen((0, 0))
        br = self.world_to_screen((ww, wh))
        world_rect = pygame.Rect(tl, (br[0] - tl[0], br[1] - tl[1]))
        # Unassigned land is not sidewalk. The earlier global pavement tile was
        # the source of the large grey parcel boxes; pavement now comes only
        # from the road envelopes and native curb modules below.
        pygame.draw.rect(target, (31, 42, 34), world_rect)
        self._tile_repo_region(
            target,
            "assets/source_packs/free_assets/Grass/Grass_04/Grass_04_basecolor.png",
            world_rect,
            world_tile=512,
        )
        land_tone = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        pygame.draw.rect(land_tone, (10, 17, 16, 112), world_rect)
        target.blit(land_tone, (0, 0))

        # District tint remains subtle; generated catalog art is the visual authority.
        zone_overlay = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        river_rect = None
        for zone in self.layout.get("zones", []):
            x, y, w, h = (number(zone, key) for key in ("x", "y", "w", "h"))
            rect = pygame.Rect(self.world_to_screen((x, y)), (max(1, int(w * self.camera.zoom)), max(1, int(h * self.camera.zoom))))
            if zone.get("density") == "water":
                river_rect = rect
                frame = (pygame.time.get_ticks() // 450) % 3
                self._tile_catalog_region(
                    target,
                    (f"water_deep_ripple_{frame}",),
                    rect,
                    world_tile=256,
                    seed=0x71A7,
                )
                continue
            tint = ZONE_COLORS.get(zone.get("density", ""), (55, 65, 60))
            pygame.draw.rect(zone_overlay, (*tint, 40), rect)
        target.blit(zone_overlay, (0, 0))

        # Legal parcels receive coordinated generated pavement rather than exposing
        # the land-cover texture around every building. Service alleys and
        # genuinely unassigned parcels remain ground cover.
        for block in self.layout.get("pavement_blocks", []):
            block_rect = pygame.Rect(
                self.world_to_screen((number(block, "x"), number(block, "y"))),
                (max(1, int(number(block, "w") * self.camera.zoom)), max(1, int(number(block, "h") * self.camera.zoom))),
            )
            pavement_overlap = max(1, int(20 * self.camera.zoom))
            block_rect.inflate_ip(pavement_overlap * 2, pavement_overlap * 2)
            block_id = str(block.get("block_id", block.get("zone_id", "block")))
            stable = sum((index + 1) * ord(char) for index, char in enumerate(block_id))
            if "columbia" in block_id and stable % 3 == 0:
                family = tuple(f"pavement_plaza_variant_{index}" for index in range(4))
            elif stable % 5 == 0:
                family = tuple(f"pavement_patched_variant_{index}" for index in range(4))
            else:
                family = tuple(f"pavement_standard_variant_{index}" for index in range(4))
            self._tile_catalog_region(target, family, block_rect, seed=stable)

        if self.layer == "roof":
            roof_context = pygame.Surface(target.get_size(), pygame.SRCALPHA)
            pygame.draw.rect(roof_context, (21, 25, 34, 100), world_rect)
            target.blit(roof_context, (0, 0))

        # The Hudson is a real, uninterrupted 20%-wide geographic corridor.
        if river_rect is not None:
            clipped_river = river_rect.clip(target.get_rect())
            shallow_world = 320
            shallow_px = max(2, int(shallow_world * self.camera.zoom))
            west_shallow = pygame.Rect(clipped_river.left, clipped_river.top, shallow_px, clipped_river.height)
            east_shallow = pygame.Rect(clipped_river.right - shallow_px, clipped_river.top, shallow_px, clipped_river.height)
            self._tile_catalog_region(target, ("water_shallow",), west_shallow, world_tile=256, seed=1)
            self._tile_catalog_region(target, ("water_shallow",), east_shallow, world_tile=256, seed=2)

            transition_px = max(3, int(CITY_BLOCK_TILE_WORLD * self.camera.zoom))
            transition_world_px = max(2, int(256 * self.camera.zoom))
            for sx, rotation in ((river_rect.left, 0), (river_rect.right, 180)):
                for sy in range(clipped_river.top, clipped_river.bottom, transition_world_px):
                    image = self._catalog_art(
                        "water_wet_sand_v",
                        (transition_px, transition_world_px),
                        rotation,
                    )
                    target.blit(image, image.get_rect(center=(sx, sy + transition_world_px // 2)))

        regular_road_width = int(float(self.layout_contract.get("regular_road_width", 420)))
        bridge_road_width = int(float(self.layout_contract.get("gwb_road_width", 1050)))
        road_widths = {
            "bridge": bridge_road_width,
            "primary": regular_road_width,
            "secondary": regular_road_width,
            "residential": regular_road_width,
        }
        roads = sorted(self.layout.get("streets", []), key=lambda row: row.get("road_class") == "bridge")

        # The closest shoreline avenues terminate the street grid. Between
        # their curb envelopes and the Hudson is a continuous sandy waterfront,
        # so land roads never appear to pour directly into the water.
        if river_rect is not None:
            river_zone = next((zone for zone in self.layout.get("zones", []) if zone.get("density") == "water"), None)
            west_shore = next((road for road in roads if road.get("street_id") == "fl_hudson_terrace"), None)
            east_shore = next((road for road in roads if road.get("street_id") == "ny_riverside"), None)
            if river_zone and west_shore and east_shore:
                river_x0 = number(river_zone, "x")
                river_x1 = river_x0 + number(river_zone, "w")
                west_sand_x0 = number(west_shore, "x1") + road_widths[west_shore.get("road_class", "secondary")] * 0.5 + 75
                east_sand_x1 = number(east_shore, "x1") - road_widths[east_shore.get("road_class", "secondary")] * 0.5 - 75
                for sx0, sx1 in ((west_sand_x0, river_x0), (river_x1, east_sand_x1)):
                    sand_rect = pygame.Rect(
                        self.world_to_screen((sx0, 0)),
                        (max(1, int((sx1 - sx0) * self.camera.zoom)), max(1, int(wh * self.camera.zoom))),
                    )
                    self._tile_catalog_region(
                        target,
                        ("sand_dry", "sand_compacted", "sand_coarse_urban"),
                        sand_rect,
                        world_tile=256,
                        seed=int(sx0),
                    )
                    damp_width = max(2, int(160 * self.camera.zoom))
                    damp_rect = pygame.Rect(
                        sand_rect.right - damp_width if sx1 == river_x0 else sand_rect.left,
                        sand_rect.top,
                        damp_width,
                        sand_rect.height,
                    )
                    self._tile_catalog_region(target, ("sand_damp",), damp_rect, world_tile=256)

        road_draws = []
        for road in roads:
            a = self.world_to_screen((number(road, "x1"), number(road, "y1")))
            b = self.world_to_screen((number(road, "x2"), number(road, "y2")))
            road_class = road.get("road_class", "residential")
            width_world = road_widths.get(road_class, 235)
            outer = max(3, int((width_world + 150) * self.camera.zoom))
            inner = max(2, int(width_world * self.camera.zoom))
            road_draws.append((road_class, a, b, outer, inner))

        # v0.8/v3 road law: finish the complete sidewalk network first, then
        # stamp the complete asphalt network over it. Intersections therefore
        # stay open instead of being severed by the next road's sidewalk band.
        self._draw_textured_roads(target, road_draws)
        self._draw_tiled_curbs(target, roads, road_widths)
        self._draw_lane_markings(target, roads, road_widths)

        # Nine approved truss pieces restore the recognizable v3 GWB landmark.
        bridge_y = number(next((row for row in roads if row.get("road_class") == "bridge"), {}), "y1", 3560)
        for index in range(9):
            wx = 6460 + index * 410
            p = self.world_to_screen((wx, bridge_y))
            size = (max(8, int(410 * self.camera.zoom)), max(6, int(190 * self.camera.zoom)))
            image = self._repo_art("cosmetic_packs/nyc_gta2_callback/sprites/lan_gwb_truss_02_night.png", size)
            target.blit(image, image.get_rect(center=p))

        if self.layer == "ground":
            self._draw_street_features(target)

        # Public/NPC slots never get buzzers. Non-building infrastructure is
        # rendered with explicit editor symbols until its approved sprite lands.
        for slot in self.layout.get("slots", []):
            role = str(slot.get("sprite_role", ""))
            if role == "small_pier":
                x, y, w, h = (number(slot, key) for key in ("x", "y", "w", "h"))
                rect = pygame.Rect(self.world_to_screen((x, y)), (max(2, int(w * self.camera.zoom)), max(2, int(h * self.camera.zoom))))
                image = self._repo_art("cosmetic_packs/nyc_gta2_callback/sprites/lan_gwb_pier_03_night.png", rect.size)
                target.blit(image, rect)
            elif role == "athletic_field":
                x, y, w, h = (number(slot, key) for key in ("x", "y", "w", "h"))
                rect = pygame.Rect(self.world_to_screen((x, y)), (max(2, int(w * self.camera.zoom)), max(2, int(h * self.camera.zoom))))
                pygame.draw.rect(target, (55, 102, 68), rect)
                pygame.draw.rect(target, (218, 221, 188), rect, 1)
            elif role == "bridge_tower":
                x, y, w, h = (number(slot, key) for key in ("x", "y", "w", "h"))
                rect = pygame.Rect(self.world_to_screen((x, y)), (max(3, int(w * self.camera.zoom)), max(3, int(h * self.camera.zoom))))
                image = self._repo_art("cosmetic_packs/nyc_gta2_callback/sprites/lan_gwb_tower_01_night.png", rect.size)
                target.blit(image, rect)
            else:
                self._draw_modular_building(target, slot)

        for house in self.layout.get("houses", []):
            self._draw_modular_building(target, house, player_house=True)
            if self.layer == "ground":
                self._draw_buzzer(target, house)

        self._draw_access(target)
        if self.layer == "ground":
            self._draw_transport(target)
        self._draw_population(target)

        if self.show_labels:
            for zone in self.layout.get("zones", []):
                if zone.get("density") == "water":
                    continue
                p = self.world_to_screen((number(zone, "x") + 80, number(zone, "y") + 80))
                label = self.small.render(zone.get("name", ""), True, (230, 235, 225))
                target.blit(label, p)
            for road in roads:
                if road.get("road_class") not in {"primary", "bridge"}:
                    continue
                a = self.world_to_screen((number(road, "x1"), number(road, "y1")))
                b = self.world_to_screen((number(road, "x2"), number(road, "y2")))
                label = self.small.render(road.get("name", ""), True, TEXT)
                target.blit(label, ((a[0] + b[0]) // 2 + 5, (a[1] + b[1]) // 2 - 20))
            if river_rect:
                label = self.font.render("HUDSON RIVER", True, (140, 197, 219))
                target.blit(label, (river_rect.centerx - label.get_width() // 2, river_rect.top + 12))

        if self.show_collision:
            overlay = pygame.Surface(target.get_size(), pygame.SRCALPHA)
            for slot in self.layout.get("slots", []):
                x, y, w, h = (number(slot, key) for key in ("x", "y", "w", "h"))
                pygame.draw.rect(overlay, (230, 65, 65, 55), pygame.Rect(self.world_to_screen((x, y)), (max(2, int(w * self.camera.zoom)), max(2, int(h * self.camera.zoom)))))
            for house in self.layout.get("houses", []):
                x, y, w, h = (number(house, key) for key in ("x", "y", "w", "h"))
                pygame.draw.rect(overlay, (230, 65, 65, 55), pygame.Rect(self.world_to_screen((x, y)), (max(2, int(w * self.camera.zoom)), max(2, int(h * self.camera.zoom)))))
            target.blit(overlay, (0, 0))

        if self.show_grid:
            step = 1024
            for x in range(0, int(ww) + 1, step):
                pygame.draw.line(target, (78, 91, 92), self.world_to_screen((x, 0)), self.world_to_screen((x, wh)), 1)
            for y in range(0, int(wh) + 1, step):
                pygame.draw.line(target, (78, 91, 92), self.world_to_screen((0, y)), self.world_to_screen((ww, y)), 1)

    def hovered_detail(self) -> list[str]:
        mouse = pygame.mouse.get_pos()
        if not self.canvas_rect.collidepoint(mouse):
            return []
        wx, wy = self.screen_to_world(mouse)
        lines = [f"World: {wx:,.0f}, {wy:,.0f}"]
        if self.mode == "city" and self.world is not None:
            gx, gy = self.world.world_to_cell(wx, wy)
            tile_id = self.world.tile_id(self.layer, gx, gy)
            collision = self.world.tile(self.layer, gx, gy).collision
            lines.extend([f"Cell: {gx}, {gy}", f"Tile: {tile_id}", f"Collision: {collision}"])
        else:
            for house in self.layout.get("houses", []):
                x, y, w, h = (number(house, key) for key in ("x", "y", "w", "h"))
                if x <= wx <= x + w and y <= wy <= y + h:
                    lines.extend([f"House: {house.get('housing_id')}", f"Zone: {house.get('zone_id')}"])
                    break
            else:
                for slot in self.layout.get("slots", []):
                    x, y, w, h = (number(slot, key) for key in ("x", "y", "w", "h"))
                    if x <= wx <= x + w and y <= wy <= y + h:
                        lines.extend([f"Slot: {slot.get('slot_id')}", f"Role: {slot.get('sprite_role')}"])
                        break
        return lines

    def draw_panel(self) -> None:
        x = self.screen.get_width() - PANEL_W
        pygame.draw.rect(self.screen, PANEL, (x, 0, PANEL_W, self.screen.get_height()))
        pygame.draw.line(self.screen, PANEL_EDGE, (x, 0), (x, self.screen.get_height()), 1)
        self.screen.blit(self.title_font.render("MAP WORKBENCH", True, TEXT), (x + 20, 18))
        mode_name = "LEGACY GRID RUNTIME" if self.mode == "city" else "GWB NEXT-MAP WORKBENCH"
        self.screen.blit(self.small.render(mode_name, True, ACCENT), (x + 21, 54))

        y = 88
        sections = [
            ("VIEW", ["1  New v4 map", "2  Legacy runtime", "G  Ground", "R  Roof", "U  Underground", "F  Fit whole map"]),
            ("LAYERS", ["T  Traffic + parking", "Y  People + rooftop jobs", "Ctrl+D  Street detail", "B  Doors + roof access"]),
            ("INSPECT", ["Mouse wheel  Zoom", "Drag / WASD  Pan", "I  Cell/grid overlay", "C  Collision overlay", "O  Object bounds", "L  Labels", "N  Static frontier"]),
            ("WORKFLOW", ["F5  Reload files", "H  Toggle hot reload", "Ctrl+R  Regenerate layers", "P  Save screenshot", "Q / Esc  Close"]),
        ]
        for heading, rows in sections:
            self.screen.blit(self.small.render(heading, True, YELLOW), (x + 20, y))
            y += 25
            for row in rows:
                self.screen.blit(self.small.render(row, True, TEXT), (x + 25, y))
                y += 23
            y += 13

        y += 4
        self.screen.blit(self.small.render("UNDER CURSOR", True, YELLOW), (x + 20, y))
        y += 26
        footer_y = self.screen.get_height() - 98
        for row in self.hovered_detail():
            if y + 23 >= footer_y - 8:
                break
            rendered = self.small.render(row, True, TEXT)
            self.screen.blit(rendered, (x + 25, y))
            y += 23

        ww, wh = self.world_size
        stats = f"{int(ww):,} × {int(wh):,}  |  {self.camera.zoom:.3f}x"
        self.screen.blit(self.small.render(stats, True, MUTED), (x + 20, footer_y))
        hot = f"Hot reload: {'ON' if self.auto_reload else 'OFF'}"
        self.screen.blit(self.small.render(hot, True, ACCENT if self.auto_reload else MUTED), (x + 20, footer_y + 24))
        color = self.status_color if time.monotonic() <= self.status_until else MUTED
        status = self.status if len(self.status) <= 39 else self.status[:36] + "…"
        self.screen.blit(self.small.render(status, True, color), (x + 20, footer_y + 50))

    def draw(self) -> None:
        canvas = self.screen.subsurface(self.canvas_rect)
        if self.mode == "city":
            self.draw_city(canvas)
        else:
            self.draw_layout(canvas)
        self.draw_panel()
        pygame.display.flip()

    def save_screenshot(self, path: Path | None = None, *, map_only: bool = False) -> Path:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        if path is None:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = SCREENSHOT_DIR / f"{self.mode}_{self.layer}_{stamp}.png"
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.draw()
        surface = self.screen.subsurface(self.canvas_rect) if map_only else self.screen
        pygame.image.save(surface, str(path))
        self.set_status(f"Saved {path.name}")
        return path

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(30) / 1000.0
            for event in pygame.event.get():
                running = self.handle_event(event) and running
            self.update(dt)
            self.draw()
        pygame.quit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone Open Night city_block/v4 map workbench")
    parser.add_argument("--mode", choices=("city", "layout"), default="layout")
    parser.add_argument("--layer", choices=("ground", "roof", "underground"), default="ground")
    parser.add_argument("--screenshot", type=Path, help="render once to this PNG and exit")
    parser.add_argument("--map-only", action="store_true", help="omit the workbench panel from a screenshot")
    parser.add_argument("--size", default="1440x900", help="window or screenshot size, e.g. 1440x900")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        width, height = (int(value) for value in args.size.lower().split("x", 1))
    except (TypeError, ValueError):
        raise SystemExit("--size must look like 1440x900")
    app = MapWorkbench(start_mode=args.mode, size=(width, height))
    app.set_layer(args.layer)
    app.fit_world()
    if args.screenshot:
        app.save_screenshot(args.screenshot, map_only=args.map_only)
        pygame.quit()
        return 0
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
