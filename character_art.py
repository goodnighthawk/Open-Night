from __future__ import annotations

"""Runtime renderer for the grungy three-layer 90-degree character pack."""

from functools import lru_cache
import math
from pathlib import Path

import pygame

from art_style import load_art_style
from character_catalog import normalize_character, pack_root


TARGET_BASE_HEIGHT = 31
OUTLINE = (24, 23, 25)
SHADOW = (0, 0, 0)
SHADOW_ALPHA = 100
SPRINT_DUST_PATH = Path(__file__).resolve().parent / "assets" / "effects" / "sprint_dust_8.png"

ANIMATION_ROWS = {
    "idle": "idle", "walk_left": "walk_left", "walk_right": "walk_right",
    "run_left": "run_left", "run_right": "run_right", "jump": "jump",
    "crouch": "crouch", "prone": "prone",
}
HEAD_SHIFT_Y = {
    "idle": -29, "walk_left": -27, "walk_right": -27,
    "run_left": -24, "run_right": -24, "jump": -18,
    "crouch": -15, "prone": 0,
}


def reload_character_style() -> None:
    global OUTLINE, SHADOW, SHADOW_ALPHA
    style = load_art_style().get("sprite", {})
    OUTLINE = tuple(style.get("outline", OUTLINE))
    SHADOW = tuple(style.get("shadow", SHADOW))
    SHADOW_ALPHA = max(0, min(220, int(style.get("shadow_alpha", SHADOW_ALPHA))))
    _composed_frame.cache_clear()


def _part_index(part_id: str, prefix: str) -> int:
    try:
        value = int(str(part_id).removeprefix(prefix + "_"))
    except (TypeError, ValueError):
        return 1
    return max(1, min(8, value))


@lru_cache(maxsize=256)
def _load_part(relative: str) -> pygame.Surface:
    path = pack_root() / relative
    if not path.is_file():
        # Missing replacement art is deliberately visible; never fall back to
        # the retired master_dual_camera pack.
        missing = pygame.Surface((160, 128), pygame.SRCALPHA)
        pygame.draw.rect(missing, (255, 0, 255), pygame.Rect(58, 42, 44, 44), width=5)
        pygame.draw.line(missing, (255, 0, 255), (58, 42), (102, 86), 5)
        pygame.draw.line(missing, (255, 0, 255), (102, 42), (58, 86), 5)
        return missing
    return pygame.image.load(str(path)).convert_alpha()


def _body_state(animation: str, anim_time: float) -> str:
    animation = str(animation or "idle").lower()
    if animation == "walk":
        phase = int(float(anim_time) * 8.0) % 4
        return ("walk_left", "idle", "walk_right", "idle")[phase]
    if animation == "run":
        return ("run_left", "run_right")[int(float(anim_time) * 10.0) % 2]
    return animation if animation in ANIMATION_ROWS else "idle"


@lru_cache(maxsize=1024)
def _composed_frame(hat: str, head: str, body: str, state: str) -> pygame.Surface:
    body_index = _part_index(body, "body")
    head_index = _part_index(head, "head")
    canvas = pygame.Surface((160, 128), pygame.SRCALPHA)
    canvas.blit(_load_part(f"bodies/body_{body_index:02d}_{state}.png"), (0, 0))
    shift_y = HEAD_SHIFT_Y.get(state, HEAD_SHIFT_Y["idle"])
    canvas.blit(_load_part(f"heads/head_{head_index:02d}.png"), (0, shift_y))
    if hat != "none":
        hat_index = _part_index(hat, "hat")
        canvas.blit(_load_part(f"hats/hat_{hat_index:02d}.png"), (0, shift_y))
    return canvas


reload_character_style()


def _crop_alpha(surface: pygame.Surface, pad: int = 2) -> pygame.Surface:
    try:
        rect = surface.get_bounding_rect(min_alpha=10)
    except TypeError:
        rect = surface.get_bounding_rect()
    if rect.width <= 0 or rect.height <= 0:
        return surface.copy()
    rect.inflate_ip(pad * 2, pad * 2)
    rect = rect.clip(surface.get_rect())
    return surface.subsurface(rect).copy()


def _scale_nearest(surface: pygame.Surface, scale: float) -> pygame.Surface:
    cropped = _crop_alpha(surface)
    target_h = max(22, int(round(TARGET_BASE_HEIGHT * max(0.5, float(scale)))))
    target_w = max(10, int(round(cropped.get_width() * target_h / max(1, cropped.get_height()))))
    return pygame.transform.scale(cropped, (target_w, target_h))


def build_character_surface(
    appearance: dict | None,
    *,
    mode: str = "topdown",
    aim_radians: float = 0.0,
    scale: float = 1.0,
    animation: str = "idle",
    anim_time: float = 0.0,
) -> pygame.Surface:
    del mode  # Only the approved 90-degree pack exists.
    selected = normalize_character(appearance)
    state = _body_state(animation, anim_time)
    assembled = _scale_nearest(
        _composed_frame(selected["hat"], selected["head"], selected["body"], state).copy(),
        scale,
    )
    # Source art faces north. Game aim 0 points east and +pi/2 points south.
    degrees = -math.degrees(float(aim_radians)) - 90.0
    quarter = abs(degrees / 90.0 - round(degrees / 90.0)) < 1e-4
    return pygame.transform.rotate(assembled, degrees) if quarter else pygame.transform.rotozoom(assembled, degrees, 1.0)


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
    del action, phase, weapon_id
    # No retired punch/gun sheets are allowed into the replacement renderer.
    return build_character_surface(appearance, mode=mode, aim_radians=aim_radians, scale=scale)


@lru_cache(maxsize=32)
def _sprint_dust_frame(frame: int, scale_key: int) -> pygame.Surface | None:
    if not SPRINT_DUST_PATH.exists():
        return None
    try:
        atlas = pygame.image.load(str(SPRINT_DUST_PATH)).convert_alpha()
    except (pygame.error, OSError):
        return None
    raw = atlas.subsurface(pygame.Rect((int(frame) % 8) * 64, 0, 64, 64)).copy()
    size = max(20, int(round(38 * max(0.5, scale_key / 100.0))))
    return pygame.transform.scale(raw, (size, size))


def _outline(target: pygame.Surface, sprite: pygame.Surface, rect: pygame.Rect) -> None:
    try:
        mask = pygame.mask.from_surface(sprite, 32)
        outline = mask.to_surface(setcolor=(*OUTLINE, 255), unsetcolor=(0, 0, 0, 0))
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
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
            appearance, mode=mode, aim_radians=aim_radians, scale=scale,
            animation=animation or ("walk" if moving else "idle"), anim_time=anim_time,
        )
    rect = sprite.get_rect(center=center)
    if (animation or "") == "run":
        dust = _sprint_dust_frame(int(float(anim_time) * 18.0) % 8, max(50, min(800, int(round(float(scale) * 100.0)))))
        if dust is not None:
            target.blit(dust, dust.get_rect(midbottom=(center[0], center[1] + int(18 * max(0.5, float(scale))))))
    shadow = pygame.Surface((max(10, int(sprite.get_width() * 0.72)), max(4, int(4 * max(0.5, float(scale))))), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (*SHADOW, SHADOW_ALPHA), shadow.get_rect())
    target.blit(shadow, shadow.get_rect(center=(center[0] + 1, center[1] + int(12 * max(0.5, float(scale))))))
    if local_ring is not None:
        pygame.draw.circle(target, local_ring, center, max(16, int(18 * max(0.5, float(scale)))), width=2)
    _outline(target, sprite, rect)
    target.blit(sprite, rect)
    return rect
