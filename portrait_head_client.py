from __future__ import annotations

"""Login portrait/head selector layered onto the existing Open Night client.

Selected portrait IDs are encoded into legacy appearance fields that the current
server already validates, persists, and replicates. Older clients therefore fall
back to a compatible directional head; clients with this module also draw the
selected portrait over the head position.

The selector intentionally does not decode an embedded PNG at runtime. This keeps
startup independent of libpng and prevents a damaged/corrupt portrait atlas from
crashing the desktop client before login.
"""

import asyncio
import math
from functools import lru_cache

import pygame

import client as game_client
from portrait_head_asset import HEAD_RECTS

HEAD_FALLBACKS = [
    "curly_short", "fade_mask", "baseball_cap", "fade_mask", "fade_mask",
    "motorcycle_helmet", "motorcycle_helmet", "ponytail_shades", "curly_short", "curly_short",
    "ponytail_shades", "baseball_cap", "baseball_cap", "curly_short", "ponytail_shades",
    "fade_mask", "curly_short",
]
HEAD_NAMES = tuple(f"Head {i:02d}" for i in range(1, len(HEAD_RECTS) + 1))
PORTRAIT_SENTINEL = 7

# Lightweight built-in previews. These are deliberately generated with pygame
# primitives so the launcher has no image-decoding dependency at startup.
_SKIN = (
    (244, 202, 168), (222, 174, 139), (198, 143, 105),
    (158, 105, 75), (116, 75, 55),
)
_HAIR = (
    (36, 28, 24), (77, 50, 32), (132, 91, 55), (205, 174, 108),
    (22, 22, 24), (96, 42, 34),
)
_ACCENT = (
    (64, 92, 142), (124, 72, 112), (74, 116, 82), (148, 94, 54),
    (70, 70, 74), (150, 52, 52),
)


@lru_cache(maxsize=64)
def portrait(index: int, size: int = 72) -> pygame.Surface:
    index = max(0, min(len(HEAD_RECTS) - 1, int(index)))
    size = max(8, int(size))
    base = pygame.Surface((72, 72), pygame.SRCALPHA)

    skin = _SKIN[(index // 4) % len(_SKIN)]
    hair = _HAIR[index % len(_HAIR)]
    accent = _ACCENT[(index * 3) % len(_ACCENT)]

    # Neck + face.
    pygame.draw.rect(base, skin, pygame.Rect(29, 49, 14, 12), border_radius=4)
    pygame.draw.ellipse(base, skin, pygame.Rect(18, 13, 36, 44))

    style = index % 6
    if style == 0:  # short/curly
        pygame.draw.ellipse(base, hair, pygame.Rect(17, 8, 38, 24))
        for x in (21, 29, 37, 45):
            pygame.draw.circle(base, hair, (x, 14 + ((x // 8) % 2) * 3), 7)
    elif style == 1:  # fade
        pygame.draw.arc(base, hair, pygame.Rect(18, 9, 36, 27), math.pi, math.tau, 7)
        pygame.draw.rect(base, hair, pygame.Rect(19, 16, 34, 7), border_radius=3)
    elif style == 2:  # cap
        pygame.draw.ellipse(base, accent, pygame.Rect(16, 7, 40, 21))
        pygame.draw.rect(base, accent, pygame.Rect(33, 21, 28, 5), border_radius=2)
    elif style == 3:  # helmet
        pygame.draw.arc(base, accent, pygame.Rect(14, 6, 44, 42), math.pi, math.tau, 9)
        pygame.draw.rect(base, accent, pygame.Rect(14, 19, 8, 25), border_radius=3)
        pygame.draw.rect(base, accent, pygame.Rect(50, 19, 8, 25), border_radius=3)
    elif style == 4:  # ponytail
        pygame.draw.ellipse(base, hair, pygame.Rect(17, 8, 38, 25))
        pygame.draw.ellipse(base, hair, pygame.Rect(48, 23, 15, 29))
    else:  # swept hair
        pygame.draw.polygon(base, hair, [(17, 28), (19, 10), (51, 8), (55, 23), (40, 17), (30, 24)])

    # Eyes / brows.
    eye_y = 33
    pygame.draw.line(base, (55, 42, 38), (25, eye_y - 4), (31, eye_y - 5), 2)
    pygame.draw.line(base, (55, 42, 38), (41, eye_y - 5), (47, eye_y - 4), 2)
    pygame.draw.circle(base, (30, 30, 32), (28, eye_y), 2)
    pygame.draw.circle(base, (30, 30, 32), (44, eye_y), 2)

    # A few selector-specific details make the 17 options visually distinct.
    variant = index % 5
    if variant == 1:  # shades
        pygame.draw.rect(base, (24, 28, 34), pygame.Rect(22, 29, 12, 7), border_radius=2)
        pygame.draw.rect(base, (24, 28, 34), pygame.Rect(38, 29, 12, 7), border_radius=2)
        pygame.draw.line(base, (24, 28, 34), (34, 32), (38, 32), 2)
    elif variant == 2:  # mask
        pygame.draw.polygon(base, accent, [(22, 38), (50, 38), (47, 50), (36, 54), (25, 50)])
    elif variant == 3:  # beard
        pygame.draw.polygon(base, hair, [(23, 42), (49, 42), (45, 56), (36, 61), (27, 56)])
    elif variant == 4:  # earring
        pygame.draw.circle(base, accent, (53, 42), 3, 1)

    # Mouth.
    pygame.draw.line(base, (115, 60, 58), (31, 45), (41, 45), 2)

    if size == 72:
        return base
    return pygame.transform.smoothscale(base, (size, size))


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
    result["skin_tone"] = index // 5
    result["hair_style"] = index % 5
    result["top_color"] = PORTRAIT_SENTINEL
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
    icon_size = max(12, int(round(16 * max(0.65, float(scale)))))
    icon = portrait(index, icon_size)
    lift = int(round(8 * max(0.65, float(scale))))
    icon_rect = icon.get_rect(center=(int(center[0]), int(center[1]) - lift))
    target.blit(icon, icon_rect)
    return rect


def _install() -> None:
    game_client.Launcher = HeadSelectLauncher
    game_client.draw_character = draw_character_with_portrait
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