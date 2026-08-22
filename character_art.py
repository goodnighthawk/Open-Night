from __future__ import annotations

"""Runtime renderer for the grungy three-layer 90-degree character pack."""

from functools import lru_cache
import math
from pathlib import Path
import re

import pygame

from art_style import load_art_style
from character_catalog import normalize_character, pack_root


TARGET_BASE_HEIGHT = 31
MASTER_CELL_WIDTH = 160
MASTER_CELL_HEIGHT = 128
MASTER_CELL_PAD_X = 12
COMPOSITE_SIZE = 224
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
    "idle": -24, "walk_left": -28, "walk_right": -34,
    "run_left": -44, "run_right": -44, "jump": -52,
    "crouch": -58, "prone": -60,
}
# Keep head registration intact while moving the authored hat crown farther
# north over the top-down head in every animation state.
HAT_SHIFT_Y = -8

MASTER_BODY_ROWS = {
    "idle": 2,
    "walk_left": 3,
    "walk_right": 4,
    "run_left": 5,
    "run_right": 6,
    "jump": 7,
    "crouch": 8,
    "prone": 9,
}


def reload_character_style() -> None:
    global OUTLINE, SHADOW, SHADOW_ALPHA
    style = load_art_style().get("sprite", {})
    OUTLINE = tuple(style.get("outline", OUTLINE))
    SHADOW = tuple(style.get("shadow", SHADOW))
    SHADOW_ALPHA = max(0, min(220, int(style.get("shadow_alpha", SHADOW_ALPHA))))
    _composed_frame.cache_clear()
    _load_part.cache_clear()
    _master_surface.cache_clear()


def _part_index(part_id: str, prefix: str) -> int:
    try:
        value = int(str(part_id).removeprefix(prefix + "_"))
    except (TypeError, ValueError):
        return 1
    return max(1, min(8, value))


@lru_cache(maxsize=1)
def _master_surface() -> pygame.Surface | None:
    path = pack_root() / "master_8x10_v2_clean.png"
    if not path.is_file():
        return None
    try:
        return pygame.image.load(str(path)).convert_alpha()
    except (pygame.error, OSError):
        return None


def _sanitize_part(source: pygame.Surface) -> pygame.Surface:
    """Remove transparent-white bleed and isolated extraction artifacts."""
    clean = source.copy().convert_alpha()
    width, height = clean.get_size()
    if width <= 0 or height <= 0:
        return clean

    # Flood through the transparent exterior and consume only neutral near-white
    # pixels attached to it. Enclosed pale art details remain untouched.
    pending = [(x, 0) for x in range(width)] + [(x, height - 1) for x in range(width)]
    pending += [(0, y) for y in range(1, height - 1)] + [(width - 1, y) for y in range(1, height - 1)]
    exterior: set[tuple[int, int]] = set()
    while pending:
        x, y = pending.pop()
        if (x, y) in exterior:
            continue
        pixel = clean.get_at((x, y))
        # The source export flattened its antialias edge against a light gray
        # presentation canvas, so the unwanted fringe ranges well below pure
        # white. Restrict removal to neutral pixels reachable from the exterior.
        pale_neutral = min(pixel.r, pixel.g, pixel.b) >= 175 and max(pixel.r, pixel.g, pixel.b) - min(pixel.r, pixel.g, pixel.b) <= 30
        if pixel.a > 16 and not pale_neutral:
            continue
        exterior.add((x, y))
        clean.set_at((x, y), (0, 0, 0, 0))
        if x:
            pending.append((x - 1, y))
        if x + 1 < width:
            pending.append((x + 1, y))
        if y:
            pending.append((x, y - 1))
        if y + 1 < height:
            pending.append((x, y + 1))

    # The clean master contains a handful of one-pixel guide fragments. They are
    # disconnected from the character and should never become visible at 4x zoom.
    seen: set[tuple[int, int]] = set()
    components: list[list[tuple[int, int]]] = []
    for start_y in range(height):
        for start_x in range(width):
            if (start_x, start_y) in seen or clean.get_at((start_x, start_y)).a <= 16:
                continue
            component: list[tuple[int, int]] = []
            component_pending = [(start_x, start_y)]
            while component_pending:
                x, y = component_pending.pop()
                if (x, y) in seen or clean.get_at((x, y)).a <= 16:
                    continue
                seen.add((x, y))
                component.append((x, y))
                if x:
                    component_pending.append((x - 1, y))
                if x + 1 < width:
                    component_pending.append((x + 1, y))
                if y:
                    component_pending.append((x, y - 1))
                if y + 1 < height:
                    component_pending.append((x, y + 1))
            components.append(component)
    # Logical cells can overrun horizontally by a few pixels, but padding may
    # also catch a disconnected sliver from the neighboring column. Every layer
    # is authored as one connected silhouette, so retain only that main component.
    if components:
        main_component = max(components, key=len)
        for component in components:
            if component is main_component:
                continue
            for x, y in component:
                clean.set_at((x, y), (0, 0, 0, 0))
    return clean


def _master_part(relative: str) -> pygame.Surface | None:
    normalized = str(relative).replace("\\", "/")
    row = None
    match = re.search(r"hats/hat_(\d{2})\.png$", normalized)
    if match:
        column, row = int(match.group(1)) - 1, 0
    else:
        match = re.search(r"heads/head_(\d{2})\.png$", normalized)
        if match:
            column, row = int(match.group(1)) - 1, 1
        else:
            match = re.search(r"bodies/body_(\d{2})_([a-z_]+)\.png$", normalized)
            if not match or match.group(2) not in MASTER_BODY_ROWS:
                return None
            column, row = int(match.group(1)) - 1, MASTER_BODY_ROWS[match.group(2)]
    master = _master_surface()
    if master is None or not (0 <= column < 8):
        return None
    origin_x = column * MASTER_CELL_WIDTH - MASTER_CELL_PAD_X
    origin_y = row * MASTER_CELL_HEIGHT
    size = (MASTER_CELL_WIDTH + MASTER_CELL_PAD_X * 2, MASTER_CELL_HEIGHT)
    part = pygame.Surface(size, pygame.SRCALPHA)
    clipped = pygame.Rect(origin_x, origin_y, *size).clip(master.get_rect())
    if clipped.width <= 0 or clipped.height <= 0:
        return None
    part.blit(master, (clipped.x - origin_x, clipped.y - origin_y), clipped)
    return _sanitize_part(part)


@lru_cache(maxsize=256)
def _load_part(relative: str) -> pygame.Surface:
    master_part = _master_part(relative)
    if master_part is not None:
        return master_part
    path = pack_root() / relative
    if path.is_file():
        return _sanitize_part(pygame.image.load(str(path)).convert_alpha())
    # Missing replacement art is deliberately visible; never fall back to
    # the retired master_dual_camera pack.
    missing = pygame.Surface((MASTER_CELL_WIDTH, MASTER_CELL_HEIGHT), pygame.SRCALPHA)
    pygame.draw.rect(missing, (255, 0, 255), pygame.Rect(58, 42, 44, 44), width=5)
    pygame.draw.line(missing, (255, 0, 255), (58, 42), (102, 86), 5)
    pygame.draw.line(missing, (255, 0, 255), (102, 42), (58, 86), 5)
    return missing


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
    canvas = pygame.Surface((COMPOSITE_SIZE, COMPOSITE_SIZE), pygame.SRCALPHA)
    body_surface = _load_part(f"bodies/body_{body_index:02d}_{state}.png")
    head_surface = _load_part(f"heads/head_{head_index:02d}.png")
    origin_x, origin_y = 20, 60
    body_rect = body_surface.get_bounding_rect(min_alpha=10)
    head_rect = head_surface.get_bounding_rect(min_alpha=10)
    body_center_x = body_rect.centerx if body_rect.width else body_surface.get_width() // 2
    head_center_x = head_rect.centerx if head_rect.width else head_surface.get_width() // 2
    canvas.blit(body_surface, (origin_x, origin_y))
    shift_y = HEAD_SHIFT_Y.get(state, HEAD_SHIFT_Y["idle"])
    canvas.blit(head_surface, (origin_x + body_center_x - head_center_x, origin_y + shift_y))
    if hat != "none":
        hat_index = _part_index(hat, "hat")
        hat_surface = _load_part(f"hats/hat_{hat_index:02d}.png")
        hat_rect = hat_surface.get_bounding_rect(min_alpha=10)
        hat_center_x = hat_rect.centerx if hat_rect.width else hat_surface.get_width() // 2
        canvas.blit(
            hat_surface,
            (origin_x + body_center_x - hat_center_x, origin_y + shift_y + HAT_SHIFT_Y),
        )
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
    draw_shadow: bool = True,
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
    if draw_shadow:
        shadow = pygame.Surface((max(10, int(sprite.get_width() * 0.72)), max(4, int(4 * max(0.5, float(scale))))), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (*SHADOW, SHADOW_ALPHA), shadow.get_rect())
        target.blit(shadow, shadow.get_rect(center=(center[0] + 1, center[1] + int(12 * max(0.5, float(scale))))))
    if local_ring is not None:
        pygame.draw.circle(target, local_ring, center, max(16, int(18 * max(0.5, float(scale)))), width=2)
    _outline(target, sprite, rect)
    target.blit(sprite, rect)
    return rect
