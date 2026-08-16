from __future__ import annotations

"""Login portrait/head selector layered onto the existing Open Night client.

Selected portrait IDs are encoded into legacy appearance fields that the current
server already validates, persists, and replicates. Older clients therefore fall
back to a compatible directional head; clients with this module also draw the
selected portrait over the head position.
"""

import asyncio
import base64
import io
import math
from functools import lru_cache

import pygame

import client as game_client
from portrait_head_asset import HEAD_ATLAS_B64, HEAD_RECTS

HEAD_FALLBACKS = [
    "curly_short", "fade_mask", "baseball_cap", "fade_mask", "fade_mask",
    "motorcycle_helmet", "motorcycle_helmet", "ponytail_shades", "curly_short", "curly_short",
    "ponytail_shades", "baseball_cap", "baseball_cap", "curly_short", "ponytail_shades",
    "fade_mask", "curly_short",
]
HEAD_NAMES = tuple(f"Head {i:02d}" for i in range(1, len(HEAD_RECTS) + 1))
PORTRAIT_SENTINEL = 7


@lru_cache(maxsize=1)
def _atlas() -> pygame.Surface:
    raw = base64.b64decode(HEAD_ATLAS_B64)
    return pygame.image.load(io.BytesIO(raw)).convert_alpha()


@lru_cache(maxsize=64)
def portrait(index: int, size: int = 72) -> pygame.Surface:
    index = max(0, min(len(HEAD_RECTS) - 1, int(index)))
    x, y, w, h = HEAD_RECTS[index]
    raw = _atlas().subsurface(pygame.Rect(x, y, w, h)).copy()
    try:
        bounds = raw.get_bounding_rect(min_alpha=8)
    except TypeError:
        bounds = raw.get_bounding_rect()
    if bounds.width > 0 and bounds.height > 0:
        raw = raw.subsurface(bounds).copy()
    size = max(8, int(size))
    factor = min(size / max(1, raw.get_width()), size / max(1, raw.get_height()))
    target = (
        max(1, int(round(raw.get_width() * factor))),
        max(1, int(round(raw.get_height() * factor))),
    )
    return pygame.transform.scale(raw, target)


def selected_index(appearance: dict | None) -> int | None:
    if not isinstance(appearance, dict):
        return None
    try:
        if int(appearance.get("top_color", -1)) != PORTRAIT_SENTINEL:
            return None
        index = int(appearance.get("skin_tone", 0)) * 5 + int(appearance.get("hair_style", 0))
    except (TypeError, ValueError):
        return None
    return index if 0 <= index < len(HEAD_RECTS) else None


def apply_selection(appearance: dict | None, index: int) -> dict:
    index = max(0, min(len(HEAD_RECTS) - 1, int(index)))
    result = dict(appearance or game_client.CHARACTER_DEFAULT)
    # Existing server normalization preserves these bounded legacy fields.
    result["skin_tone"] = index // 5
    result["hair_style"] = index % 5
    result["top_color"] = PORTRAIT_SENTINEL
    # Directional fallback for older clients and action sheets.
    result["head"] = HEAD_FALLBACKS[index]
    result["profile"] = "custom"
    return game_client.normalize_character(result)


class HeadSelectLauncher(game_client.Launcher):
    """Open the visual head picker before the ordinary server-login screen."""

    def __init__(self, initial_name: str | None = None, initial_phone: str | None = None):
        super().__init__(initial_name, initial_phone)
        existing = selected_index(self.appearance)
        self._portrait_index = existing if existing is not None else 0
        if existing is None:
            # Make Head 01 a saved choice even if the player simply presses Enter.
            self._choose(self._portrait_index)
        self.customizing = True

    def _choose(self, index: int) -> None:
        self._portrait_index = max(0, min(len(HEAD_RECTS) - 1, int(index)))
        self.appearance = apply_selection(self.appearance, self._portrait_index)
        self.appearance_changed = True

    def _character_modal(self, event: pygame.event.Event | None = None) -> bool:
        w, h = self.screen.get_size()
        panel_w = min(930, max(720, w - 40))
        panel_h = min(700, max(560, h - 40))
        panel = pygame.Rect((w - panel_w) // 2, (h - panel_h) // 2, panel_w, panel_h)

        cols = 5
        cell = 94
        gap = 10
        grid_x = panel.x + 34
        grid_y = panel.y + 112
        cells: list[pygame.Rect] = []
        for index in range(len(HEAD_RECTS)):
            col = index % cols
            row = index // cols
            cells.append(pygame.Rect(grid_x + col * (cell + gap), grid_y + row * (cell + gap), cell, cell))

        done = pygame.Rect(panel.right - 164, panel.bottom - 60, 128, 38)
        default = pygame.Rect(panel.x + 36, panel.bottom - 60, 150, 38)

        if event is not None:
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                    self.customizing = False
                    return True
                if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                    delta = {
                        pygame.K_LEFT: -1,
                        pygame.K_RIGHT: 1,
                        pygame.K_UP: -cols,
                        pygame.K_DOWN: cols,
                    }[event.key]
                    self._choose((self._portrait_index + delta) % len(HEAD_RECTS))
                    return True
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if done.collidepoint(event.pos):
                    self.customizing = False
                    return True
                if default.collidepoint(event.pos):
                    self._choose(0)
                    return True
                for index, rect in enumerate(cells):
                    if rect.collidepoint(event.pos):
                        self._choose(index)
                        return True
            return False

        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 190))
        self.screen.blit(shade, (0, 0))
        pygame.draw.rect(self.screen, (22, 24, 26), panel, border_radius=10)
        pygame.draw.rect(self.screen, (112, 115, 118), panel, width=2, border_radius=10)

        title = self.modal_title.render("CHOOSE YOUR HEAD", True, game_client.TEXT_COLOR)
        self.screen.blit(title, (panel.x + 34, panel.y + 25))
        note = self.small.render(
            "Pick a portrait before login — the choice is saved and replicated with your character.",
            True,
            game_client.MUTED_TEXT,
        )
        self.screen.blit(note, (panel.x + 36, panel.y + 66))

        for index, rect in enumerate(cells):
            selected = index == self._portrait_index
            hovered = rect.collidepoint(pygame.mouse.get_pos())
            fill = (54, 58, 61) if (selected or hovered) else (31, 34, 36)
            edge = (235, 210, 92) if selected else ((150, 153, 156) if hovered else (72, 75, 78))
            pygame.draw.rect(self.screen, fill, rect, border_radius=7)
            pygame.draw.rect(self.screen, edge, rect, width=3 if selected else 1, border_radius=7)
            icon = portrait(index, 70)
            self.screen.blit(icon, icon.get_rect(center=(rect.centerx, rect.centery - 6)))
            label = self.small.render(str(index + 1), True, game_client.TEXT_COLOR)
            self.screen.blit(label, (rect.x + 7, rect.bottom - 20))

        info_x = grid_x + cols * (cell + gap) + 8
        preview_rect = pygame.Rect(info_x, grid_y, max(170, panel.right - info_x - 32), 310)
        pygame.draw.rect(self.screen, (16, 18, 20), preview_rect, border_radius=8)
        pygame.draw.rect(self.screen, (72, 75, 78), preview_rect, width=2, border_radius=8)
        big = portrait(self._portrait_index, min(170, preview_rect.width - 24))
        self.screen.blit(big, big.get_rect(center=(preview_rect.centerx, preview_rect.y + 118)))
        label = self.font.render(HEAD_NAMES[self._portrait_index].upper(), True, game_client.TEXT_COLOR)
        self.screen.blit(label, label.get_rect(center=(preview_rect.centerx, preview_rect.y + 224)))
        help1 = self.small.render("Click a head or use arrow keys.", True, game_client.MUTED_TEXT)
        help2 = self.small.render("Enter confirms the selection.", True, game_client.MUTED_TEXT)
        self.screen.blit(help1, help1.get_rect(center=(preview_rect.centerx, preview_rect.y + 262)))
        self.screen.blit(help2, help2.get_rect(center=(preview_rect.centerx, preview_rect.y + 284)))

        self._button(self.screen, default, "HEAD 01", self.small)
        self._button(self.screen, done, "DONE", self.small)
        return False


_ORIGINAL_DRAW_CHARACTER = game_client.draw_character


def draw_character_with_portrait(
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
    rect = _ORIGINAL_DRAW_CHARACTER(
        target,
        center,
        aim_radians,
        appearance,
        scale=scale,
        local_ring=local_ring,
        moving=moving,
        animation=animation,
        anim_time=anim_time,
        mode=mode,
        action=action,
        action_phase=action_phase,
        weapon_id=weapon_id,
    )
    index = selected_index(appearance)
    if index is None:
        return rect
    # The supplied atlas is frontal rather than eight-direction art. Keep the
    # portrait small and anchored to the existing directional head so movement,
    # collision and action poses stay authoritative.
    icon_size = max(12, int(round(16 * max(0.65, float(scale)))))
    icon = portrait(index, icon_size)
    lift = int(round(8 * max(0.65, float(scale))))
    icon_rect = icon.get_rect(center=(int(center[0]), int(center[1]) - lift))
    target.blit(icon, icon_rect)
    return rect


def _install() -> None:
    game_client.Launcher = HeadSelectLauncher
    game_client.draw_character = draw_character_with_portrait
    # These modules import draw_character by name, so update their bound symbol
    # too when present. This keeps selected heads visible indoors/on bicycles.
    for module_name in ("interior_art", "bicycle_art"):
        try:
            module = __import__(module_name)
            if hasattr(module, "draw_character"):
                setattr(module, "draw_character", draw_character_with_portrait)
        except Exception:
            pass


if __name__ == "__main__":
    _install()
    asyncio.run(game_client.main())
