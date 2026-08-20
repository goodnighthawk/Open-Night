from __future__ import annotations

import base64
import io
import math
from functools import lru_cache
from pathlib import Path

import pygame

from art_style import load_art_style
from vehicle_catalog import load_vehicle_catalog, vehicle_meta, vehicle_asset_path

ASSET_DIR = Path(__file__).resolve().parent / "assets" / "cars"
VEHICLE_SHADOW_RGB = (0, 0, 0)
VEHICLE_OUTLINE_RGB = (24, 24, 22)
VEHICLE_OUTLINE_PX = 1
VEHICLE_SHADOW_ALPHA = 100
VEHICLE_PIXELATED = True


def reload_vehicle_style() -> None:
    global VEHICLE_SHADOW_RGB, VEHICLE_OUTLINE_RGB, VEHICLE_OUTLINE_PX, VEHICLE_SHADOW_ALPHA, VEHICLE_PIXELATED
    cfg = load_art_style().get("vehicle", {})
    VEHICLE_SHADOW_RGB = tuple(cfg.get("shadow", VEHICLE_SHADOW_RGB))
    VEHICLE_OUTLINE_RGB = tuple(cfg.get("outline", VEHICLE_OUTLINE_RGB))
    VEHICLE_OUTLINE_PX = max(0, min(3, int(cfg.get("outline_px", VEHICLE_OUTLINE_PX))))
    VEHICLE_SHADOW_ALPHA = max(0, min(220, int(cfg.get("shadow_alpha", VEHICLE_SHADOW_ALPHA))))
    VEHICLE_PIXELATED = bool(cfg.get("pixelated", True))
    try:
        _base_car.cache_clear()
        _sheet_surface.cache_clear()
    except NameError:
        pass


reload_vehicle_style()


def available_car_count() -> int:
    return len(load_vehicle_catalog())


def _load_surface_file(path: Path) -> pygame.Surface | None:
    if not path.exists():
        return None
    try:
        if path.name.lower().endswith(".b64"):
            raw = base64.b64decode(path.read_text(encoding="ascii"), validate=False)
            # Pygame/SDL_image can determine PNG/JPEG type from the byte stream.
            return pygame.image.load(io.BytesIO(raw), path.stem).convert_alpha()
        return pygame.image.load(str(path)).convert_alpha()
    except Exception:
        return None


@lru_cache(maxsize=16)
def _sheet_surface(filename: str) -> pygame.Surface | None:
    return _load_surface_file(vehicle_asset_path(filename))


def _sprite_from_sheet(meta: dict) -> pygame.Surface | None:
    sheet_name = str(meta.get("sheet_file", "")).strip()
    if not sheet_name:
        return None
    sheet = _sheet_surface(sheet_name)
    if sheet is None:
        return None
    try:
        x = int(meta.get("crop_x", 0))
        y = int(meta.get("crop_y", 0))
        w = int(meta.get("crop_w", 0))
        h = int(meta.get("crop_h", 0))
    except Exception:
        return None
    if w <= 0 or h <= 0:
        return None
    rect = pygame.Rect(x, y, w, h).clip(sheet.get_rect())
    if rect.width <= 0 or rect.height <= 0:
        return None
    source = sheet.subsurface(rect).copy().convert_alpha()

    # The submitted pixel-car sheets use white/near-white presentation
    # backgrounds, including JPEG compression gradients. Remove only neutral
    # background pixels connected to the crop border so enclosed pale vehicle
    # highlights remain intact.
    if source.get_width() and source.get_height():
        corner = source.get_at((0, 0))
        if corner.a > 240:
            width, height = source.get_size()
            pending = [(x, 0) for x in range(width)] + [(x, height - 1) for x in range(width)]
            pending += [(0, y) for y in range(1, height - 1)] + [(width - 1, y) for y in range(1, height - 1)]
            visited: set[tuple[int, int]] = set()
            while pending:
                x, y = pending.pop()
                if (x, y) in visited:
                    continue
                visited.add((x, y))
                pixel = source.get_at((x, y))
                close_to_corner = max(
                    abs(pixel.r - corner.r), abs(pixel.g - corner.g), abs(pixel.b - corner.b)
                ) <= 28
                if pixel.a < 24 or close_to_corner:
                    source.set_at((x, y), (pixel.r, pixel.g, pixel.b, 0))
                    if x:
                        pending.append((x - 1, y))
                    if x + 1 < width:
                        pending.append((x + 1, y))
                    if y:
                        pending.append((x, y - 1))
                    if y + 1 < height:
                        pending.append((x, y + 1))
    return source


@lru_cache(maxsize=256)
def _base_car(index: int, target_length: int | None = None) -> pygame.Surface | None:
    catalog = load_vehicle_catalog()
    if not catalog:
        return None
    meta = vehicle_meta(index)

    source = _sprite_from_sheet(meta)
    if source is None:
        path = vehicle_asset_path(str(meta.get("file", "")))
        source = _load_surface_file(path)
    if source is None or source.get_width() <= 0 or source.get_height() <= 0:
        return None

    # Player-supplied sheets are allowed to contain a horizontal source sprite;
    # canonical runtime vehicle art always points nose-up before heading rotation.
    if source.get_width() > source.get_height():
        source = pygame.transform.rotate(source, 90)

    length = max(24, int(target_length or meta.get("render_length", 48)))
    width = max(12, int(round(length * source.get_width() / source.get_height())))
    return pygame.transform.scale(source, (width, length)) if VEHICLE_PIXELATED else pygame.transform.smoothscale(source, (width, length))


def _blit_outline(target: pygame.Surface, sprite: pygame.Surface, rect: pygame.Rect) -> None:
    if VEHICLE_OUTLINE_PX <= 0:
        return
    try:
        mask = pygame.mask.from_surface(sprite, 24)
        outline = mask.to_surface(setcolor=(*VEHICLE_OUTLINE_RGB,255), unsetcolor=(0,0,0,0))
        r=VEHICLE_OUTLINE_PX
        for oy in range(-r,r+1):
            for ox in range(-r,r+1):
                if ox == 0 and oy == 0:
                    continue
                if ox*ox + oy*oy <= r*r + 1:
                    target.blit(outline, rect.move(ox,oy))
    except Exception:
        pass


def _rotate_for_heading(surface: pygame.Surface, degrees: float) -> pygame.Surface:
    """Keep cardinal pixel art crisp; filter only genuinely diagonal rotations."""
    quarter_turn = abs((float(degrees) / 90.0) - round(float(degrees) / 90.0)) < 1e-4
    if quarter_turn:
        return pygame.transform.rotate(surface, degrees)
    return pygame.transform.rotozoom(surface, degrees, 1.0)


def draw_car(
    target: pygame.Surface,
    center: tuple[int, int],
    angle_radians: float,
    sprite_index: int,
    target_length: int | None = None,
    speed: float = 0.0,
) -> bool:
    """Draw a source sprite whose nose points upward in the PNG.

    Server headings are screen-space atan2(dy, dx): 0=east, +pi/2=south.
    An up-facing source sprite therefore needs -90 degrees at heading 0.
    """
    sprite = _base_car(int(sprite_index), target_length)
    if sprite is None:
        return False

    shadow = pygame.Surface((max(12, sprite.get_width() - 3), max(18, sprite.get_height() - 5)), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (*VEHICLE_SHADOW_RGB, VEHICLE_SHADOW_ALPHA), shadow.get_rect())
    rotation = -90.0 - math.degrees(angle_radians)
    shadow_rot = _rotate_for_heading(shadow, rotation)
    motion_offset = min(3, int(abs(speed) / 90.0))
    target.blit(shadow_rot, shadow_rot.get_rect(center=(center[0] + 2 + motion_offset, center[1] + 3 + motion_offset)))

    rotated = _rotate_for_heading(sprite, rotation)
    rect = rotated.get_rect(center=center)
    _blit_outline(target, rotated, rect)
    target.blit(rotated, rect)
    # A tiny moving specular glint makes traffic motion legible while retaining
    # the crisp art-bible sprite instead of deforming or blurring it.
    if abs(speed) > 12.0:
        phase = int(abs(speed) * 0.08) % 3
        glint = (211, 217, 211, 105)
        pygame.draw.circle(target, glint, (rect.centerx - 2 + phase, rect.centery - rect.height // 6), 1)
    return True
