from __future__ import annotations

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
    except NameError:
        pass


reload_vehicle_style()


def available_car_count() -> int:
    return len(load_vehicle_catalog())


@lru_cache(maxsize=192)
def _base_car(index: int, target_length: int | None = None) -> pygame.Surface | None:
    catalog = load_vehicle_catalog()
    if not catalog:
        return None
    meta = vehicle_meta(index)
    path = vehicle_asset_path(str(meta.get("file", "")))
    if not path.exists():
        return None
    source = pygame.image.load(str(path)).convert_alpha()
    if source.get_width() <= 0 or source.get_height() <= 0:
        return None

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
