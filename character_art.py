from __future__ import annotations

import csv
import math
from functools import lru_cache
from pathlib import Path

import pygame

from art_style import load_art_style
from character_catalog import (
    PART_SLOTS,
    catalog,
    matching_profile,
    normalize_character,
    pack_root,
    profile_parts,
)

DIRECTIONS = ("north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest")
DRAW_ORDER = ("body", "top", "bottom", "footwear", "head", "accessory")
CELL = 256
TARGET_BASE_HEIGHT = 31
WALK_FPS = 10.0
RUN_ANIMATION_RATE = 1.85
OUTLINE = (24, 23, 25)
SHADOW = (0, 0, 0)
SHADOW_ALPHA = 100
SPRINT_DUST_PATH = Path(__file__).resolve().parent / "assets" / "effects" / "sprint_dust_8.png"


def reload_character_style() -> None:
    global OUTLINE, SHADOW, SHADOW_ALPHA
    style = load_art_style().get("sprite", {})
    OUTLINE = tuple(style.get("outline", OUTLINE))
    SHADOW = tuple(style.get("shadow", SHADOW))
    SHADOW_ALPHA = max(0, min(220, int(style.get("shadow_alpha", SHADOW_ALPHA))))


reload_character_style()


def _direction_index(aim_radians: float) -> int:
    # Game convention: 0=east, +pi/2=south. The revision-3 master pack is
    # clockwise from north in exact 45-degree steps.
    angle = float(aim_radians) % (math.pi * 2.0)
    return int(round((angle + math.pi * 0.5) / (math.pi * 0.25))) % 8


@lru_cache(maxsize=256)
def _load_rel(relpath: str) -> pygame.Surface:
    return pygame.image.load(str(pack_root() / relpath)).convert_alpha()


def _crop_alpha(surface: pygame.Surface, pad: int = 2) -> pygame.Surface:
    try:
        rect = surface.get_bounding_rect(min_alpha=10)
    except TypeError:
        rect = surface.get_bounding_rect()
    if rect.width <= 0 or rect.height <= 0:
        return surface.copy()
    rect.inflate_ip(pad * 2, pad * 2)
    rect.clamp_ip(surface.get_rect())
    return surface.subsurface(rect).copy()


def _scaled(surface: pygame.Surface, scale: float) -> pygame.Surface:
    cropped = _crop_alpha(surface)
    target_h = max(22, int(round(TARGET_BASE_HEIGHT * max(0.5, float(scale)))))
    target_w = max(10, int(round(cropped.get_width() * target_h / max(1, cropped.get_height()))))
    return pygame.transform.scale(cropped, (target_w, target_h))


def _scaled_with_reference(surface: pygame.Surface, scale: float, reference_height: int) -> pygame.Surface:
    """Scale animation frames with one direction-wide factor so gait does not resize the torso."""
    cropped = _crop_alpha(surface)
    target_reference_h = max(22, int(round(TARGET_BASE_HEIGHT * max(0.5, float(scale)))))
    factor = target_reference_h / max(1, int(reference_height))
    target_w = max(1, int(round(cropped.get_width() * factor)))
    target_h = max(1, int(round(cropped.get_height() * factor)))
    return pygame.transform.scale(cropped, (target_w, target_h))


@lru_cache(maxsize=32)
def _sprint_dust_frame(frame: int, scale_key: int) -> pygame.Surface | None:
    if not SPRINT_DUST_PATH.exists():
        return None
    try:
        atlas = pygame.image.load(str(SPRINT_DUST_PATH)).convert_alpha()
    except (pygame.error, OSError):
        return None
    cell = 64
    raw = atlas.subsurface(pygame.Rect((int(frame) % 8) * cell, 0, cell, cell)).copy()
    scale = max(0.5, scale_key / 100.0)
    size = max(20, int(round(38 * scale)))
    return pygame.transform.smoothscale(raw, (size, size))


def _safe_sheet_cell(sheet: pygame.Surface, col: int, row: int) -> pygame.Surface | None:
    """Return a full grid cell without ever requesting a rectangle off-sheet."""
    columns = max(0, int(sheet.get_width()) // CELL)
    rows = max(0, int(sheet.get_height()) // CELL)
    if columns < 1 or rows < 1:
        return None
    safe_col = int(col) % columns
    safe_row = int(row) % rows
    rect = pygame.Rect(safe_col * CELL, safe_row * CELL, CELL, CELL)
    return sheet.subsurface(rect).copy()


def _frame_from_sheet(sheet: pygame.Surface, col: int, row: int) -> pygame.Surface:
    frame = _safe_sheet_cell(sheet, col, row)
    return frame if frame is not None else pygame.Surface((CELL, CELL), pygame.SRCALPHA)


def _paper_doll_frame(mode: str, appearance: dict, direction: int, animation: str, anim_time: float) -> pygame.Surface:
    cat = catalog()
    anim = cat["animations"].get(animation) or cat["animations"].get("idle") or {"row_sequence": "0", "fps": "2"}
    sequence = [int(x) for x in str(anim.get("row_sequence", "0")).split(";") if str(x).strip()]
    if not sequence:
        sequence = [0]
    try:
        fps = max(0.1, float(anim.get("fps", 2.0)))
    except (TypeError, ValueError):
        fps = 2.0
    row = sequence[int(float(anim_time) * fps) % len(sequence)]
    target = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
    for slot in DRAW_ORDER:
        part_id = appearance.get(slot, "none") or "none"
        if part_id == "none":
            continue
        rel = cat["part_sheets"].get((mode, slot, part_id))
        if not rel:
            continue
        target.blit(_load_rel(rel), (0, 0), pygame.Rect(direction * CELL, row * CELL, CELL, CELL))
    return target


def _fluid_frame(mode: str, profile: str, direction: int, animation: str, anim_time: float) -> pygame.Surface | None:
    row = catalog()["fluid"].get((mode, profile, animation))
    if not row:
        return None
    rel = row.get("sheet", "")
    if not rel:
        return None
    sheet = _load_rel(rel)
    try:
        frames = max(1, int(row.get("frame_count", row.get("frames", 1))))
        fps = max(0.1, float(row.get("fps", WALK_FPS)))
    except (TypeError, ValueError):
        frames, fps = 1, WALK_FPS
    frame = int(float(anim_time) * fps) % frames
    # Fluid sheets are frames across columns and directions down rows. The final
    # crop is guarded because external/modded packs may disagree with their CSV.
    return _safe_sheet_cell(sheet, frame, direction)


@lru_cache(maxsize=4096)
def _paper_frame_cached(
    mode: str, body: str, head: str, top: str, bottom: str, footwear: str, accessory: str,
    direction: int, head_direction: int, row: int, scale_key: int,
) -> pygame.Surface:
    appearance = {
        "body": body, "head": head, "top": top, "bottom": bottom,
        "footwear": footwear, "accessory": accessory,
    }
    target = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
    cat = catalog()
    for slot in DRAW_ORDER:
        part_id = appearance.get(slot, "none") or "none"
        if part_id == "none":
            continue
        rel = cat["part_sheets"].get((mode, slot, part_id))
        if rel:
            layer_direction = head_direction if slot in {"head", "accessory"} else direction
            target.blit(_load_rel(rel), (0, 0), pygame.Rect(layer_direction * CELL, row * CELL, CELL, CELL))
    return _scaled(target, scale_key / 100.0)


@lru_cache(maxsize=4096)
def _fluid_reference_height(mode: str, profile: str, direction: int, animation: str) -> int:
    row = catalog()["fluid"].get((mode, profile, animation))
    if not row or not row.get("sheet"):
        return CELL
    sheet = _load_rel(row["sheet"])
    columns = max(0, int(sheet.get_width()) // CELL)
    rows = max(0, int(sheet.get_height()) // CELL)
    if columns < 1 or rows < 1:
        return CELL
    try:
        declared_frames = max(1, int(row.get("frame_count", row.get("frames", 1))))
    except (TypeError, ValueError):
        declared_frames = 1
    heights = []
    for index in range(min(declared_frames, columns)):
        sample = _safe_sheet_cell(sheet, index, int(direction) % rows)
        if sample is None:
            continue
        try:
            bounds = sample.get_bounding_rect(min_alpha=10)
        except TypeError:
            bounds = sample.get_bounding_rect()
        if bounds.height:
            heights.append(bounds.height)
    return sorted(heights)[len(heights) // 2] if heights else CELL


@lru_cache(maxsize=4096)
def _fluid_frame_cached(mode: str, profile: str, direction: int, animation: str, frame: int, scale_key: int) -> pygame.Surface:
    row = catalog()["fluid"].get((mode, profile, animation))
    if not row or not row.get("sheet"):
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    sheet = _load_rel(row["sheet"])
    raw = _safe_sheet_cell(sheet, frame, direction)
    if raw is None:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    return _scaled_with_reference(raw, scale_key / 100.0, _fluid_reference_height(mode, profile, direction, animation))


def _wide_gait_fallback(sprite: pygame.Surface, frame: int, mode: str) -> pygame.Surface:
    """Give modular-only outfits a wider run stance without changing their walk."""
    if sprite.get_width() < 2 or sprite.get_height() < 4:
        return sprite
    amplitude = (1.02, 1.10, 1.26, 1.10, 1.02, 1.10, 1.26, 1.10)[int(frame) % 8]
    if mode == "topdown":
        amplitude = 1.0 + (amplitude - 1.0) * 0.55
        split = int(sprite.get_height() * 0.72)
    else:
        split = int(sprite.get_height() * 0.55)
    split = max(1, min(sprite.get_height() - 1, split))
    lower = sprite.subsurface(pygame.Rect(0, split, sprite.get_width(), sprite.get_height() - split)).copy()
    lower_w = max(sprite.get_width(), int(round(sprite.get_width() * amplitude)))
    widened = pygame.transform.smoothscale(lower, (lower_w, lower.get_height()))
    result = pygame.Surface((lower_w, sprite.get_height()), pygame.SRCALPHA)
    result.blit(sprite, ((lower_w - sprite.get_width()) // 2, 0))
    result.fill((0, 0, 0, 0), pygame.Rect(0, split, lower_w, result.get_height() - split))
    result.blit(widened, widened.get_rect(midtop=(lower_w // 2, split)))
    return result


def build_character_surface(
    appearance: dict | None,
    *,
    mode: str = "topdown",
    aim_radians: float = 0.0,
    scale: float = 1.0,
    animation: str = "idle",
    anim_time: float = 0.0,
) -> pygame.Surface:
    appearance = normalize_character(appearance)
    direction = _direction_index(aim_radians)
    head_direction = direction
    scale_key = max(50, min(800, int(round(float(scale) * 100.0))))
    profile = matching_profile(appearance, mode)
    fluid_name = {
        "walk": "walk_8",
        "run": "run_wide_8",
        "jump": "jump_9",
        "crouch": "crouch_3",
        "prone": "prone_3",
    }.get(animation, animation)
    playback_time = float(anim_time) * (RUN_ANIMATION_RATE if animation == "run" else 1.0)
    fluid_row = catalog()["fluid"].get((mode, profile, fluid_name)) if profile else None
    if fluid_row and head_direction == direction:
        try:
            frames = max(1, int(fluid_row.get("frame_count", fluid_row.get("frames", 1))))
            fps = max(0.1, float(fluid_row.get("fps", WALK_FPS)))
        except (TypeError, ValueError):
            frames, fps = 1, WALK_FPS
        frame = int(playback_time * fps) % frames
        return _fluid_frame_cached(mode, profile, direction, fluid_name, frame, scale_key).copy()

    base_animation = "walk" if animation == "run" else animation
    anim = catalog()["animations"].get(base_animation) or catalog()["animations"].get("idle") or {"row_sequence": "0", "fps": "2"}
    sequence = [int(x) for x in str(anim.get("row_sequence", "0")).split(";") if str(x).strip()] or [0]
    try:
        fps = max(0.1, float(anim.get("fps", 2.0)))
    except (TypeError, ValueError):
        fps = 2.0
    row = sequence[int(playback_time * fps) % len(sequence)]
    fallback = _paper_frame_cached(
        mode, appearance["body"], appearance["head"], appearance["top"], appearance["bottom"],
        appearance["footwear"], appearance["accessory"], direction, head_direction, row, scale_key,
    ).copy()
    return _wide_gait_fallback(fallback, int(playback_time * fps), mode) if animation == "run" else fallback


def build_action_surface(
    appearance: dict | None,
    action: str,
    *,
    mode: str = "topdown",
    aim_radians: float = 0.0,
    phase: int = 0,
    scale: float = 1.0,
    weapon_id: str | None = None,
) -> pygame.Surface:
    appearance = normalize_character(appearance)
    direction = _direction_index(aim_radians)
    # Start from the registered action-pose body supplied by the approved pack.
    action_row = catalog()["actions"].get((mode, action))
    if action_row and action_row.get("sheet"):
        sheet = _load_rel(action_row["sheet"])
        pose = _frame_from_sheet(sheet, direction, max(0, min(3, int(phase))))
    else:
        pose = _paper_doll_frame(mode, appearance, direction, "idle", 0.0)
    if weapon_id:
        weapon = catalog()["weapons"].get(str(weapon_id))
        if weapon and weapon.get("directional_sheet"):
            overlay_sheet = _load_rel(weapon["directional_sheet"])
            pose.blit(_frame_from_sheet(overlay_sheet, direction, 0), (0, 0))
    return _scaled(pose, scale)


def _outline(target: pygame.Surface, sprite: pygame.Surface, rect: pygame.Rect) -> None:
    try:
        mask = pygame.mask.from_surface(sprite, 32)
        outline = mask.to_surface(setcolor=(*OUTLINE, 255), unsetcolor=(0, 0, 0, 0))
        for ox, oy in ((-1,0),(1,0),(0,-1),(0,1)):
            target.blit(outline, rect.move(ox, oy))
    except Exception:
        pass


def draw_character(
    target: pygame.Surface,
    center: tuple[int, int],
    aim_radians: float,
    appearance: dict | None,
    scale: float = 1.0,
    local_ring: tuple[int, int, int] | None = None,
    moving: bool = False,
    animation: str | None = None,
    anim_time: float = 0.0,
    *,
    mode: str = "topdown",
    action: str | None = None,
    action_phase: int = 0,
    weapon_id: str | None = None,
) -> pygame.Rect:
    if action:
        sprite = build_action_surface(appearance, action, mode=mode, aim_radians=aim_radians, phase=action_phase, scale=scale, weapon_id=weapon_id)
    else:
        sprite = build_character_surface(
            appearance,
            mode=mode,
            aim_radians=aim_radians,
            scale=scale,
            animation=animation or ("walk" if moving else "idle"),
            anim_time=anim_time,
        )
    rect = sprite.get_rect(center=center)
    if (animation or "") == "run":
        dust = _sprint_dust_frame(int(float(anim_time) * 18.0) % 8, max(50, min(800, int(round(float(scale) * 100.0)))))
        if dust is not None:
            dust_rect = dust.get_rect(midbottom=(center[0], center[1] + int(18 * max(0.5, float(scale)))))
            target.blit(dust, dust_rect)
    shadow_w = max(10, int(sprite.get_width() * 0.72))
    shadow_h = max(4, int(4 * max(0.5, float(scale))))
    shadow = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (*SHADOW, SHADOW_ALPHA), shadow.get_rect())
    target.blit(shadow, shadow.get_rect(center=(center[0] + 1, center[1] + int(12 * max(0.5, float(scale))))))
    if local_ring is not None:
        pygame.draw.circle(target, local_ring, center, max(16, int(18 * max(0.5, float(scale)))), width=2)
    _outline(target, sprite, rect)
    target.blit(sprite, rect)
    return rect
