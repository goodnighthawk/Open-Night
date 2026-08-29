#!/usr/bin/env python3
"""Standalone visual workbench for Open Night's city_block and v4 map data.

This intentionally starts no game client, server, networking, NPC simulation, or
gameplay systems.  It reads the same generated GridWorld data and authored v4
layout contracts that the game will eventually consume.
"""
from __future__ import annotations

import argparse
import csv
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
SCREENSHOT_DIR = ROOT / "artifacts" / "map_workbench"

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
    def __init__(self, *, start_mode: str = "city", size: tuple[int, int] = (1440, 900)) -> None:
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
        if not self.show_static_frontier:
            target.fill((9, 11, 15))
            return
        frame = self.noise_frames[int(time.monotonic() * 6) % len(self.noise_frames)]
        target.blit(pygame.transform.scale(frame, target.get_size()), (0, 0))

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
        }
        contract_rows = read_csv(V4_LAYOUT_DIR / "layout_contract.csv")
        self.layout_contract = {row.get("key", ""): row.get("value", "") for row in contract_rows}
        if not self.layout["streets"]:
            raise FileNotFoundError(
                f"Missing v4 layout data in {V4_LAYOUT_DIR}."
            )

    def reload(self, *, reset_camera: bool = False) -> None:
        try:
            self.load_layout()
            if self.mode == "city":
                self.load_city()
            self._fingerprint = fingerprint()
            if reset_camera:
                self.fit_world()
            self.set_status("Reloaded map data and city_block art")
        except Exception as exc:
            self.set_status(f"Reload failed: {exc}", (255, 112, 112), 10.0)

    def regenerate(self) -> None:
        self.set_status("Regenerating Ground and Roof from city_block…", YELLOW, 30.0)
        pygame.display.flip()
        try:
            from tools.generate_v100_ground_roof_layers import main as generate_layers

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
                self.set_mode("city")
            elif event.key == pygame.K_2:
                self.set_mode("layout")
            elif event.key == pygame.K_g:
                self.set_layer("ground")
            elif event.key == pygame.K_r and not (event.mod & pygame.KMOD_CTRL):
                self.set_layer("roof")
            elif event.key == pygame.K_r and event.mod & pygame.KMOD_CTRL:
                self.regenerate()
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
            image = renderer._tile_surface_scaled(tile_id, tile_px)
            sx = int(round((gx * world.cell_px - cam_x) * zoom))
            sy = int(round((gy * world.cell_px - cam_y) * zoom))
            target.blit(image, (sx, sy))

        object_layers = (self.layer,)
        if self.layer == "ground" and "roof" in world.layers:
            for gx, gy in world.visible_cells(cam_x, cam_y, math.ceil(view_world_w), math.ceil(view_world_h)):
                tile_id = world.tile_id("roof", gx, gy)
                if tile_id == "void":
                    continue
                image = renderer._tile_surface_scaled(tile_id, tile_px)
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

    def draw_layout(self, target: pygame.Surface) -> None:
        self.draw_frontier(target)
        ww, wh = self.world_size
        tl = self.world_to_screen((0, 0))
        br = self.world_to_screen((ww, wh))
        pygame.draw.rect(target, (27, 35, 34), pygame.Rect(tl, (br[0] - tl[0], br[1] - tl[1])))

        for zone in self.layout.get("zones", []):
            x, y, w, h = (number(zone, key) for key in ("x", "y", "w", "h"))
            a = self.world_to_screen((x, y))
            rect = pygame.Rect(a, (max(1, int(w * self.camera.zoom)), max(1, int(h * self.camera.zoom))))
            pygame.draw.rect(target, ZONE_COLORS.get(zone.get("density", ""), (55, 65, 60)), rect)
            pygame.draw.rect(target, (104, 124, 113), rect, 1)
            if self.show_labels and rect.width > 100:
                target.blit(self.small.render(zone.get("name", ""), True, (185, 199, 190)), (rect.x + 7, rect.y + 5))

        road_colors = {"bridge": YELLOW, "primary": (230, 226, 207), "secondary": (190, 200, 190), "residential": (145, 158, 151)}
        for road in self.layout.get("streets", []):
            a = self.world_to_screen((number(road, "x1"), number(road, "y1")))
            b = self.world_to_screen((number(road, "x2"), number(road, "y2")))
            road_class = road.get("road_class", "residential")
            width = 7 if road_class == "bridge" else 4 if road_class == "primary" else 2
            pygame.draw.line(target, road_colors.get(road_class, road_colors["residential"]), a, b, width)
            if self.show_labels and self.camera.zoom > 0.07:
                label = self.small.render(road.get("name", ""), True, TEXT)
                target.blit(label, ((a[0] + b[0]) // 2 + 4, (a[1] + b[1]) // 2 - 18))

        for slot in self.layout.get("slots", []):
            x, y, w, h = (number(slot, key) for key in ("x", "y", "w", "h"))
            rect = pygame.Rect(self.world_to_screen((x, y)), (max(2, int(w * self.camera.zoom)), max(2, int(h * self.camera.zoom))))
            pygame.draw.rect(target, (171, 112, 214), rect, 1)

        for house in self.layout.get("houses", []):
            x, y, w, h = (number(house, key) for key in ("x", "y", "w", "h"))
            rect = pygame.Rect(self.world_to_screen((x, y)), (max(4, int(w * self.camera.zoom)), max(4, int(h * self.camera.zoom))))
            pygame.draw.rect(target, (255, 194, 73), rect)
            pygame.draw.rect(target, (70, 49, 20), rect, 1)

        if self.show_grid:
            step = 1024
            for x in range(0, int(ww) + 1, step):
                pygame.draw.line(target, (55, 68, 70), self.world_to_screen((x, 0)), self.world_to_screen((x, wh)), 1)
            for y in range(0, int(wh) + 1, step):
                pygame.draw.line(target, (55, 68, 70), self.world_to_screen((0, y)), self.world_to_screen((ww, y)), 1)

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
        mode_name = "CITY BLOCK RUNTIME" if self.mode == "city" else "V4 APPROVED LAYOUT"
        self.screen.blit(self.small.render(mode_name, True, ACCENT), (x + 21, 54))

        y = 88
        sections = [
            ("VIEW", ["1  City Block runtime", "2  V4 layout plan", "G  Ground layer", "R  Roof layer", "F  Fit whole map"]),
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

    def save_screenshot(self, path: Path | None = None) -> Path:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        if path is None:
            stamp = time.strftime("%Y%m%d_%H%M%S")
            path = SCREENSHOT_DIR / f"{self.mode}_{self.layer}_{stamp}.png"
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.draw()
        pygame.image.save(self.screen, str(path))
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
    parser.add_argument("--mode", choices=("city", "layout"), default="city")
    parser.add_argument("--screenshot", type=Path, help="render once to this PNG and exit")
    parser.add_argument("--size", default="1440x900", help="window or screenshot size, e.g. 1440x900")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        width, height = (int(value) for value in args.size.lower().split("x", 1))
    except (TypeError, ValueError):
        raise SystemExit("--size must look like 1440x900")
    app = MapWorkbench(start_mode=args.mode, size=(width, height))
    if args.screenshot:
        app.save_screenshot(args.screenshot)
        pygame.quit()
        return 0
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
