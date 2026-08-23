from __future__ import annotations

"""Open Night HUD 3.0 presentation shell.

This module deliberately owns presentation state only.  It does not replace the
server-authoritative inventory/economy models in ``common.py``.  The empty grid,
equipment sockets, hotbar, statistics and magazine are integration points for
those systems as they are implemented.
"""

from dataclasses import dataclass
import math

import pygame


HUD_VERSION = "3.0"
HOTBAR_KEYS = ("`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=")
HOTBAR_PYGAME_KEYS = (
    pygame.K_BACKQUOTE,
    pygame.K_1,
    pygame.K_2,
    pygame.K_3,
    pygame.K_4,
    pygame.K_5,
    pygame.K_6,
    pygame.K_7,
    pygame.K_8,
    pygame.K_9,
    pygame.K_0,
    pygame.K_MINUS,
    pygame.K_EQUALS,
)

CYAN = (37, 226, 255)
MAGENTA = (255, 47, 217)
RED = (255, 72, 62)
AMBER = (255, 164, 43)
GREEN = (76, 230, 104)
BLUE = (62, 112, 255)
PURPLE = (185, 66, 255)
WHITE = (238, 247, 255)
MUTED = (126, 153, 164)
GRID = (41, 121, 137)
BLACK_GLASS = (3, 8, 13, 72)


@dataclass
class InventoryFootprint:
    """A future inventory item footprint; the shell starts with no instances."""

    label: str
    col: int
    row: int
    width: int
    height: int
    color: tuple[int, int, int] = CYAN


class HudV3Shell:
    inventory_cols = 10
    inventory_rows = 6
    magazine_capacity = 10
    minimap_shape = "square"

    def __init__(self) -> None:
        self.active_hotbar = 2
        self.health = 6
        self.max_health = 6
        self.armor = 3
        self.max_armor = 3
        self.energy_percent = 88
        self.fatigue_percent = 20

        # HUD-only demonstration state.  Server item state is intentionally not
        # consumed until the inventory/weapon milestones are implemented.
        self.magazine_rounds = 7
        self.loose_rounds = 0
        self.inventory_shapes: list[InventoryFootprint] = []
        self.reload_active = False
        self.reload_progress = 0.0
        self.reload_seconds = 2.5
        self.drag_kind: str | None = None

        # Contributions are base, equipment, rings, consumables.  The approved
        # design starts at a true 0/10; these structures are ready for live data.
        self.stats: dict[str, tuple[int, int, int, int]] = {
            "Strength": (0, 0, 0, 0),
            "Dexterity": (0, 0, 0, 0),
            "Agility": (0, 0, 0, 0),
            "Stamina": (0, 0, 0, 0),
            "Charisma": (0, 0, 0, 0),
            "Firearm": (0, 0, 0, 0),
            "Blades": (0, 0, 0, 0),
        }

        self._font_cache: dict[tuple[int, bool], pygame.font.Font] = {}
        self.hotbar_rects: list[pygame.Rect] = []
        self.character_rects: list[pygame.Rect] = []
        self.ring_rects: list[pygame.Rect] = []
        self.inventory_cells: list[pygame.Rect] = []
        self.magazine_rect = pygame.Rect(0, 0, 0, 0)
        self.magazine_round_rects: list[pygame.Rect] = []
        self.loose_round_rect = pygame.Rect(0, 0, 0, 0)
        self.resource_rects: dict[str, pygame.Rect] = {}
        self.navigation_rects: dict[str, pygame.Rect] = {}
        self.stats_rect = pygame.Rect(0, 0, 0, 0)
        self.inventory_rect = pygame.Rect(0, 0, 0, 0)
        self.fatigue_icon_rect = pygame.Rect(0, 0, 0, 0)
        self.fatigue_icon_orientation = "side_profile"

    def _font(self, size: int, bold: bool = False) -> pygame.font.Font:
        key = (int(size), bool(bold))
        cached = self._font_cache.get(key)
        if cached is not None:
            return cached
        path = None
        for family in ("CMU Serif", "Latin Modern Roman", "Computer Modern", "DejaVu Serif"):
            path = pygame.font.match_font(family, bold=bold)
            if path:
                break
        font = pygame.font.Font(path, size) if path else pygame.font.SysFont("serif", size, bold=bold)
        self._font_cache[key] = font
        return font

    @staticmethod
    def _alpha_rect(
        target: pygame.Surface,
        rect: pygame.Rect,
        fill: tuple[int, int, int, int],
        edge: tuple[int, int, int],
        width: int = 1,
        radius: int = 3,
    ) -> None:
        pygame.draw.rect(target, fill, rect, border_radius=radius)
        pygame.draw.rect(target, (*edge, 230), rect, width=width, border_radius=radius)

    @staticmethod
    def _glow_line(
        target: pygame.Surface,
        color: tuple[int, int, int],
        start: tuple[int, int],
        end: tuple[int, int],
        width: int = 1,
    ) -> None:
        pygame.draw.line(target, (*color, 48), start, end, width + 5)
        pygame.draw.line(target, (*color, 112), start, end, width + 2)
        pygame.draw.line(target, (*color, 245), start, end, width)

    @staticmethod
    def _heart(target: pygame.Surface, center: tuple[int, int], size: int, filled: bool) -> pygame.Rect:
        x, y = center
        color = RED if filled else (70, 37, 39)
        radius = max(3, size // 4)
        pygame.draw.circle(target, (*color, 245), (x - radius, y - radius // 2), radius)
        pygame.draw.circle(target, (*color, 245), (x + radius, y - radius // 2), radius)
        pygame.draw.polygon(
            target,
            (*color, 245),
            [(x - radius * 2, y - radius // 3), (x + radius * 2, y - radius // 3), (x, y + radius * 2)],
        )
        pygame.draw.lines(
            target,
            (*WHITE, 210),
            True,
            [(x - radius * 2, y - radius // 3), (x - radius, y - radius * 3 // 2),
             (x, y - radius // 2), (x + radius, y - radius * 3 // 2),
             (x + radius * 2, y - radius // 3), (x, y + radius * 2)],
            1,
        )
        return pygame.Rect(x - radius * 2 - 2, y - radius * 2, radius * 4 + 4, radius * 4 + 2)

    @staticmethod
    def _shield(target: pygame.Surface, center: tuple[int, int], size: int, filled: bool) -> pygame.Rect:
        x, y = center
        half = max(5, size // 3)
        color = BLUE if filled else (34, 43, 76)
        points = [(x - half, y - half), (x + half, y - half), (x + half, y + half // 2),
                  (x, y + half * 3 // 2), (x - half, y + half // 2)]
        pygame.draw.polygon(target, (*color, 245), points)
        pygame.draw.lines(target, (*WHITE, 210), True, points, 1)
        return pygame.Rect(x - half - 2, y - half - 2, half * 2 + 4, half * 5 // 2 + 4)

    @staticmethod
    def _draw_fist(target: pygame.Surface, rect: pygame.Rect, color: tuple[int, int, int]) -> None:
        palm = pygame.Rect(rect.centerx - 8, rect.centery - 2, 16, 12)
        pygame.draw.rect(target, (*color, 220), palm, border_radius=4)
        for offset in (-9, -3, 3, 9):
            pygame.draw.circle(target, (*color, 225), (rect.centerx + offset, rect.centery - 7), 4)

    @staticmethod
    def _draw_knife(target: pygame.Surface, rect: pygame.Rect, color: tuple[int, int, int]) -> None:
        a = (rect.centerx - 12, rect.centery + 10)
        b = (rect.centerx + 13, rect.centery - 11)
        pygame.draw.line(target, (*color, 240), a, b, 5)
        pygame.draw.line(target, (*WHITE, 220), (rect.centerx - 1, rect.centery), b, 2)
        pygame.draw.line(target, (79, 50, 35, 245), (a[0] - 3, a[1] + 3), (a[0] + 5, a[1] - 5), 5)

    @staticmethod
    def _draw_pistol(target: pygame.Surface, rect: pygame.Rect, color: tuple[int, int, int]) -> None:
        body = pygame.Rect(rect.centerx - 13, rect.centery - 9, 24, 10)
        grip = pygame.Rect(rect.centerx + 2, rect.centery - 1, 8, 17)
        pygame.draw.rect(target, (*color, 235), body, border_radius=2)
        pygame.draw.polygon(target, (*color, 225), [grip.topleft, grip.topright, (grip.right - 2, grip.bottom), (grip.left - 3, grip.bottom)])
        pygame.draw.line(target, (*WHITE, 180), body.topleft, body.topright, 1)

    @staticmethod
    def _draw_grenade(target: pygame.Surface, rect: pygame.Rect, color: tuple[int, int, int]) -> None:
        pygame.draw.circle(target, (*color, 230), rect.center, 10)
        pygame.draw.rect(target, (*AMBER, 235), (rect.centerx - 4, rect.centery - 15, 8, 6), border_radius=2)
        pygame.draw.arc(target, (*WHITE, 210), (rect.centerx + 1, rect.centery - 19, 11, 12), 0.0, math.pi * 1.35, 2)

    def handle_keydown(self, event: pygame.event.Event, *, overlay_open: bool) -> bool:
        if event.key == pygame.K_r and self.active_hotbar == 2:
            if self.magazine_rounds >= self.magazine_capacity:
                return True
            if not self.reload_active:
                self.reload_progress = 0.0
            self.reload_active = True
            return True
        if not overlay_open and event.key in HOTBAR_PYGAME_KEYS:
            self.active_hotbar = HOTBAR_PYGAME_KEYS.index(event.key)
            return True
        return False

    def handle_keyup(self, event: pygame.event.Event) -> bool:
        if event.key != pygame.K_r:
            return False
        if self.reload_active and self.reload_progress < 1.0:
            self.reload_progress = 0.0
        self.reload_active = False
        return True

    def handle_mouse_down(self, pos: tuple[int, int]) -> bool:
        if self.loose_rounds > 0 and self.loose_round_rect.collidepoint(pos):
            self.drag_kind = "round"
            return True
        for index, rect in enumerate(self.hotbar_rects):
            if rect.collidepoint(pos):
                self.active_hotbar = index
                return True
        return any(rect.collidepoint(pos) for rect in self.inventory_cells + self.character_rects + self.ring_rects)

    def handle_mouse_up(self, pos: tuple[int, int]) -> bool:
        if self.drag_kind == "round":
            accepted = self.magazine_rect.collidepoint(pos) and self.magazine_rounds < self.magazine_capacity
            if accepted:
                self.magazine_rounds += 1
                self.loose_rounds -= 1
            self.drag_kind = None
            return True
        return False

    def navigation_at(self, pos: tuple[int, int]) -> str | None:
        return next((action for action, rect in self.navigation_rects.items() if rect.collidepoint(pos)), None)

    def update(self, dt: float) -> None:
        if not self.reload_active or self.active_hotbar != 2:
            return
        self.reload_progress = min(1.0, self.reload_progress + max(0.0, float(dt)) / self.reload_seconds)
        if self.reload_progress >= 1.0:
            self.magazine_rounds = self.magazine_capacity
            self.reload_active = False

    def minimap_diameter(self, screen_size: tuple[int, int]) -> int:
        width, height = screen_size
        return max(142, min(194, width // 7, height // 3))

    def minimap_origin(self, screen_size: tuple[int, int], diameter: int) -> tuple[int, int]:
        width, height = screen_size
        return width - diameter - 18, height - diameter - 58

    def chat_input_rect(self, screen_size: tuple[int, int]) -> pygame.Rect:
        """Place active chat in the lower gap between hotbar and minimap."""
        width, height = screen_size
        diameter = self.minimap_diameter(screen_size)
        minimap_x, _minimap_y = self.minimap_origin(screen_size, diameter)
        hotbar_right = self.hotbar_rects[-1].right if self.hotbar_rects else min(width // 2, 664)
        resource_right = max((rect.right for rect in self.resource_rects.values()), default=hotbar_right)
        left = max(hotbar_right, resource_right) + 16
        # Location text may be wider than the map itself, so reserve a small
        # label overhang to keep the two neon frames visibly separate.
        right = minimap_x - max(24, diameter // 4)
        if right - left < 220:
            right = width - 18
            left = max(18, right - min(420, width - 36))
            return pygame.Rect(left, max(18, height - 122), right - left, 44)
        return pygame.Rect(left, height - 62, right - left, 44)

    def _draw_stat_ribbon(self, target: pygame.Surface, bounds: pygame.Rect) -> None:
        self.stats_rect = bounds.copy()
        names = list(self.stats)
        gap = 4
        module_w = max(110, (bounds.width - gap * (len(names) - 1)) // len(names))
        font = self._font(12)
        tiny = self._font(9)
        for index, name in enumerate(names):
            rect = pygame.Rect(bounds.x + index * (module_w + gap), bounds.y, module_w, bounds.height)
            edge = (MAGENTA, CYAN, GREEN, BLUE, PURPLE, MAGENTA, AMBER)[index]
            self._alpha_rect(target, rect, (2, 8, 13, 80), edge, radius=2)
            target.blit(font.render(name, True, (*edge, 245)), (rect.x + 5, rect.y + 4))
            segment_x = rect.x + max(51, font.size(name)[0] + 9)
            available = rect.right - segment_x - 5
            segment_gap = 2
            segment_w = max(3, (available - segment_gap * 9) // 10)
            contributions = self.stats[name]
            colors: list[tuple[int, int, int]] = []
            for amount, color in zip(contributions, (AMBER, CYAN, PURPLE, GREEN)):
                colors.extend([color] * max(0, int(amount)))
            colors = colors[:10]
            for slot in range(10):
                segment = pygame.Rect(segment_x + slot * (segment_w + segment_gap), rect.y + 9, segment_w, 9)
                if slot < len(colors):
                    pygame.draw.rect(target, (*colors[slot], 235), segment)
                else:
                    pygame.draw.rect(target, (6, 15, 21, 75), segment)
                pygame.draw.rect(target, (*MUTED, 150), segment, width=1)
            if available < 62:
                target.blit(tiny.render("0", True, (*MUTED, 170)), (rect.right - 7, rect.y + 3))

    def _draw_character_slots(self, target: pygame.Surface, area: pygame.Rect, ring_y: int) -> None:
        labels = (
            "HEAD", "OUTFIT", "BACK", "SHOULDERS", "OFF HAND", "BOOT KNIFE", "POCKET 1", "POCKET 2", "POCKET 3", "POCKET 4",
            "POCKET 5", "SAFE 1", "SAFE 2", "SAFE 3", "SAFE 4", "SAFE 5", "GEAR", "GEAR", "GEAR", "GEAR",
        )
        columns = 5
        gap = 6
        slot = 42
        font = self._font(7)
        self.character_rects = []
        for index, label in enumerate(labels):
            row, col = divmod(index, columns)
            rect = pygame.Rect(area.x + col * (slot + gap), area.y + row * (slot + gap), slot, slot)
            self.character_rects.append(rect)
            edge = CYAN if index < 6 else AMBER
            self._alpha_rect(target, rect, (2, 9, 13, 44), edge, radius=2)
            caption = font.render(label, True, (*edge, 215))
            target.blit(caption, caption.get_rect(midtop=(rect.centerx, rect.y + 3)))
            # A faint connector emphasizes that this is an empty socket, not an item.
            pygame.draw.line(target, (*edge, 62), (rect.x + 8, rect.bottom - 9), (rect.right - 8, rect.bottom - 9), 1)

        self.loose_round_rect = pygame.Rect(0, 0, 0, 0)
        if self.loose_rounds > 0:
            self.loose_round_rect = self.character_rects[6]
            for offset in (-5, 0, 5):
                pygame.draw.rect(
                    target,
                    (*AMBER, 230),
                    (self.loose_round_rect.centerx + offset - 1, self.loose_round_rect.centery - 5, 3, 13),
                    border_radius=1,
                )
            count = self._font(9, True).render(f"×{self.loose_rounds}", True, (*WHITE, 235))
            target.blit(count, count.get_rect(bottomright=(self.loose_round_rect.right - 3, self.loose_round_rect.bottom - 3)))

        ring_slot = 42
        ring_gap = 8
        ring_x = 14
        self.ring_rects = []
        for index in range(10):
            outer = pygame.Rect(ring_x + index * (ring_slot + ring_gap), ring_y, ring_slot, ring_slot)
            self.ring_rects.append(outer)
            center = outer.center
            radius = ring_slot // 2 - 4
            pygame.draw.circle(target, (*PURPLE, 38), center, radius)
            pygame.draw.circle(target, (*PURPLE, 230), center, radius, width=1)
            pygame.draw.circle(target, (*CYAN, 105), center, max(3, radius - 5), width=1)
            n = self._font(9).render(str(index + 1), True, (*MUTED, 220))
            target.blit(n, n.get_rect(midtop=(center[0], outer.y - 1)))

    def _draw_inventory_grid(self, target: pygame.Surface, area: pygame.Rect) -> None:
        self.inventory_rect = area.copy()
        header_h = 32
        font = self._font(15, True)
        tiny = self._font(10)
        self._alpha_rect(target, area, (2, 7, 12, 54), MAGENTA, radius=3)
        target.blit(font.render("INVENTORY", True, (*CYAN, 245)), (area.x + 10, area.y + 7))
        cells_text = tiny.render("0 / 60 CELLS", True, (*MAGENTA, 245))
        target.blit(cells_text, (area.right - cells_text.get_width() - 10, area.y + 10))
        self._glow_line(target, MAGENTA, (area.x + 4, area.y + header_h), (area.right - 4, area.y + header_h))

        gap = 0
        cell = min((area.width - 12) // self.inventory_cols, (area.height - header_h - 10) // self.inventory_rows)
        grid_w = cell * self.inventory_cols
        grid_h = cell * self.inventory_rows
        start_x = area.x + (area.width - grid_w) // 2
        start_y = area.y + header_h + (area.height - header_h - grid_h) // 2
        self.inventory_cells = []
        for row in range(self.inventory_rows):
            for col in range(self.inventory_cols):
                rect = pygame.Rect(start_x + col * (cell + gap), start_y + row * (cell + gap), cell, cell)
                self.inventory_cells.append(rect)
                pygame.draw.rect(target, (1, 10, 14, 28), rect)
                pygame.draw.rect(target, (*GRID, 158), rect, width=1)

        for shape in self.inventory_shapes:
            if not (0 <= shape.col < self.inventory_cols and 0 <= shape.row < self.inventory_rows):
                continue
            if shape.col + shape.width > self.inventory_cols or shape.row + shape.height > self.inventory_rows:
                continue
            first = self.inventory_cells[shape.row * self.inventory_cols + shape.col]
            last = self.inventory_cells[(shape.row + shape.height - 1) * self.inventory_cols + shape.col + shape.width - 1]
            footprint = first.union(last).inflate(-4, -4)
            self._alpha_rect(target, footprint, (*shape.color, 24), shape.color, radius=2)
            text = tiny.render(shape.label, True, (*shape.color, 230))
            target.blit(text, text.get_rect(center=footprint.center))

    def _draw_navigation(self, target: pygame.Surface, width: int) -> None:
        tabs = (
            ("resume", "RESUME [ESC]", GREEN),
            ("settings", "OPTIONS [O]", CYAN),
            ("radio", "RADIO STATIONS [J]", MAGENTA),
            ("controls", "CONTROLS [C]", BLUE),
            ("friends", "FRIENDS [F]", PURPLE),
            ("messages", "MESSAGES [F2]", AMBER),
            ("quit", "QUIT [Q]", RED),
        )
        gap = 5
        available = width - 28 - gap * (len(tabs) - 1)
        weights = [max(72, self._font(10, True).size(label)[0] + 18) for _action, label, _color in tabs]
        total = sum(weights)
        scale = min(1.0, available / max(1, total))
        widths = [max(62, int(value * scale)) for value in weights]
        # Absorb rounding so the strip always remains inside the screen.
        excess = sum(widths) - available
        for index in range(len(widths) - 1, -1, -1):
            if excess <= 0:
                break
            reduction = min(excess, max(0, widths[index] - 62))
            widths[index] -= reduction
            excess -= reduction

        font = self._font(10, True)
        x = 14
        self.navigation_rects = {}
        for (action, label, color), tab_width in zip(tabs, widths):
            rect = pygame.Rect(x, 10, tab_width, 31)
            self.navigation_rects[action] = rect
            self._alpha_rect(target, rect, (2, 8, 13, 116), color, radius=3)
            caption = font.render(label, True, (*color, 245))
            if caption.get_width() > rect.width - 8:
                caption = self._font(8, True).render(label, True, (*color, 245))
            target.blit(caption, caption.get_rect(center=rect.center))
            x = rect.right + gap

    def _draw_magazine(self, target: pygame.Surface, rect: pygame.Rect) -> None:
        self.magazine_rect = rect
        caliber = f"9x19MM  •  {self.magazine_rounds}/{self.magazine_capacity}"
        target.blit(self._font(10, True).render(caliber, True, (*RED, 240)), (rect.x - 4, rect.y - 18))
        # Intentionally no outer panel: the magazine remains isolated beside the player.
        pygame.draw.rect(target, (8, 12, 17, 205), rect, border_radius=8)
        pygame.draw.rect(target, (*RED, 235), rect, width=2, border_radius=8)
        inset = rect.inflate(-14, -14)
        slot_h = max(8, inset.height // self.magazine_capacity)
        self.magazine_round_rects = []
        for index in range(self.magazine_capacity):
            round_rect = pygame.Rect(inset.x + 2, inset.bottom - (index + 1) * slot_h + 2, inset.width - 4, slot_h - 4)
            self.magazine_round_rects.append(round_rect)
            loaded = index < self.magazine_rounds
            pygame.draw.rect(target, (*AMBER, 235) if loaded else (11, 20, 26, 100), round_rect, border_radius=round_rect.height // 2)
            pygame.draw.rect(target, (*WHITE, 145) if loaded else (*MUTED, 85), round_rect, width=1, border_radius=round_rect.height // 2)
        count = self._font(11, True).render(f"{self.magazine_rounds}/{self.magazine_capacity}", True, (*WHITE, 240))
        target.blit(count, count.get_rect(midtop=(rect.centerx, rect.bottom + 4)))

        meter = pygame.Rect(rect.x - 4, rect.bottom + 22, rect.width + 8, 7)
        pygame.draw.rect(target, (3, 12, 17, 160), meter)
        if self.reload_progress > 0 or self.reload_active:
            fill = meter.copy()
            fill.width = int(meter.width * self.reload_progress)
            pygame.draw.rect(target, (*MAGENTA, 235), fill)
        pygame.draw.rect(target, (*CYAN, 180), meter, width=1)
        hint = self._font(9).render("HOLD R", True, (*MAGENTA, 235))
        target.blit(hint, hint.get_rect(midtop=(meter.centerx, meter.bottom + 2)))

    def _draw_hotbar(self, target: pygame.Surface, screen_size: tuple[int, int]) -> None:
        width, height = screen_size
        gap = 4
        slot = max(34, min(46, (min(width - 36, 690) - gap * 12) // 13))
        x = 18
        y = height - slot - 60
        font = self._font(11, True)
        self.hotbar_rects = []
        categories = (AMBER, AMBER, RED, GREEN) + (CYAN,) * 9
        for index, label in enumerate(HOTBAR_KEYS):
            rect = pygame.Rect(x + index * (slot + gap), y, slot, slot)
            self.hotbar_rects.append(rect)
            color = categories[index]
            selected = index == self.active_hotbar
            self._alpha_rect(target, rect, (*color, 34 if selected else 18), color, width=2 if selected else 1, radius=2)
            target.blit(font.render(label, True, (*CYAN, 245)), (rect.x + 4, rect.y + 2))
            icon_rect = rect.inflate(-10, -10)
            if index == 0:
                self._draw_fist(target, icon_rect, AMBER)
            elif index == 1:
                self._draw_knife(target, icon_rect, AMBER)
            elif index == 2:
                self._draw_pistol(target, icon_rect, RED)
            elif index == 3:
                self._draw_grenade(target, icon_rect, GREEN)

    def _draw_resources(self, target: pygame.Surface, screen_size: tuple[int, int]) -> None:
        _width, height = screen_size
        y = height - 31
        heart_rects = [self._heart(target, (30 + i * 25, y - 2), 20, i < self.health) for i in range(self.max_health)]
        shield_rects = [self._shield(target, (195 + i * 27, y - 3), 20, i < self.armor) for i in range(self.max_armor)]
        self.resource_rects = {
            "Health": heart_rects[0].unionall(heart_rects[1:]) if heart_rects else pygame.Rect(0, 0, 0, 0),
            "Armor": shield_rects[0].unionall(shield_rects[1:]) if shield_rects else pygame.Rect(0, 0, 0, 0),
        }

        energy_icon = pygame.Rect(274, y - 14, 19, 26)
        energy = pygame.Rect(300, y - 10, 170, 12)
        self.fatigue_icon_rect = pygame.Rect(518, y - 14, 25, 24)
        fatigue = pygame.Rect(552, y - 10, 130, 12)
        for name, rect, value, color in (
            ("Energy", energy, self.energy_percent, BLUE),
            ("Fatigue", fatigue, self.fatigue_percent, MAGENTA),
        ):
            pygame.draw.rect(target, (2, 9, 13, 140), rect, border_radius=2)
            fill = rect.inflate(-2, -2)
            fill.width = max(0, int(fill.width * max(0, min(100, value)) / 100.0))
            pygame.draw.rect(target, (*color, 225), fill, border_radius=2)
            pygame.draw.rect(target, (*color, 220), rect, width=1, border_radius=2)
            pct = self._font(11).render(f"{value}%", True, (*WHITE, 225))
            target.blit(pct, (rect.right + 6, rect.y - 1))
            icon_rect = energy_icon if name == "Energy" else self.fatigue_icon_rect
            self.resource_rects[name] = rect.union(pct.get_rect(topleft=(rect.right + 6, rect.y - 1))).union(icon_rect)

        # Minimal symbols, with no extra labels or enclosing resource boxes.
        bolt = [(282, y - 12), (275, y), (282, y), (277, y + 11), (291, y - 3), (284, y - 3)]
        pygame.draw.polygon(target, (*BLUE, 235), bolt)
        # Fatigue uses a right-facing side-profile brain silhouette.
        brain = self.fatigue_icon_rect
        brain_color = (*MAGENTA, 235)
        brain_fill = (*PURPLE, 88)
        profile = [
            (brain.x + 3, brain.y + 9), (brain.x + 5, brain.y + 4),
            (brain.x + 10, brain.y + 2), (brain.x + 17, brain.y + 3),
            (brain.x + 21, brain.y + 7), (brain.x + 22, brain.y + 12),
            (brain.x + 19, brain.y + 16), (brain.x + 15, brain.y + 17),
            (brain.x + 17, brain.y + 22), (brain.x + 13, brain.y + 23),
            (brain.x + 10, brain.y + 18), (brain.x + 5, brain.y + 16),
            (brain.x + 2, brain.y + 13),
        ]
        pygame.draw.polygon(target, brain_fill, profile)
        pygame.draw.lines(target, brain_color, True, profile, 2)
        pygame.draw.lines(
            target,
            (*WHITE, 155),
            False,
            [(brain.x + 6, brain.y + 8), (brain.x + 10, brain.y + 6),
             (brain.x + 13, brain.y + 9), (brain.x + 10, brain.y + 12),
             (brain.x + 14, brain.y + 14)],
            1,
        )
        pygame.draw.arc(target, (*WHITE, 145), (brain.x + 12, brain.y + 5, 8, 8), 0.6, 3.9, 1)

    def _draw_hover_tooltip(self, target: pygame.Surface, screen_size: tuple[int, int]) -> None:
        mouse = pygame.mouse.get_pos()
        hovered = next((name for name, rect in self.resource_rects.items() if rect.collidepoint(mouse)), None)
        if not hovered:
            return
        sources = {
            "Health": ("Stamina 50%", "Strength 30%", "Outfit 20%"),
            "Armor": ("Outfit 70%", "Back 20%", "Rings 10%"),
            "Energy": ("Stamina 65%", "Agility 25%", "Consumables 10%"),
            "Fatigue": ("Activity 60%", "Stamina 25%", "Rest 15%"),
        }[hovered]
        font = self._font(11)
        title = self._font(12, True).render(hovered.upper(), True, (*CYAN, 245))
        lines = [font.render(source, True, (*WHITE, 230)) for source in sources]
        width = max([title.get_width()] + [line.get_width() for line in lines]) + 18
        height = 14 + title.get_height() + sum(line.get_height() + 2 for line in lines)
        box = pygame.Rect(mouse[0] + 14, mouse[1] - height - 8, width, height)
        box.clamp_ip(pygame.Rect((0, 0), screen_size))
        self._alpha_rect(target, box, (2, 8, 13, 225), CYAN, radius=3)
        target.blit(title, (box.x + 9, box.y + 6))
        y = box.y + 8 + title.get_height()
        for line in lines:
            target.blit(line, (box.x + 9, y))
            y += line.get_height() + 2

    def draw(self, game, *, overlay_open: bool) -> None:
        screen = game.screen
        width, height = screen.get_size()
        if width < 640 or height < 420:
            return
        target = pygame.Surface((width, height), pygame.SRCALPHA)

        if overlay_open:
            self._draw_navigation(target, width)
            self._draw_stat_ribbon(target, pygame.Rect(14, 56, width - 28, 28))

            # The 20 non-ring sockets stay square in a compact center-left 5x4
            # block. Rings remain a separate row immediately above the hotbar.
            hotbar_gap = 4
            hotbar_slot = max(34, min(46, (min(width - 36, 690) - hotbar_gap * 12) // 13))
            hotbar_y = height - hotbar_slot - 60
            ring_y = hotbar_y - 42 - 20
            equipment_width = 5 * 42 + 4 * 6
            equipment_height = 4 * 42 + 3 * 6
            equipment_x = max(36, width // 24)
            equipment_y = max(103, height // 2 - equipment_height // 2)
            self._draw_character_slots(
                target,
                pygame.Rect(equipment_x, equipment_y, equipment_width, equipment_height),
                ring_y,
            )

            inventory_width = min(500, max(340, int(width * 0.39)))
            inventory_height = min(340, max(240, int(height * 0.47)))
            inventory_area = pygame.Rect(width - inventory_width - 14, 103, inventory_width, inventory_height)
            self._draw_inventory_grid(target, inventory_area)

            mag_width = max(42, min(54, width // 24))
            mag_height = max(210, min(286, height // 2 - 48))
            mag_x = width // 2 - max(74, width // 11)
            mag_y = max(164, (height - mag_height) // 2 + 14)
            self._draw_magazine(target, pygame.Rect(mag_x, mag_y, mag_width, mag_height))
        else:
            self.navigation_rects = {}
            self.stats_rect = pygame.Rect(0, 0, 0, 0)
            self.inventory_rect = pygame.Rect(0, 0, 0, 0)
            self.character_rects = []
            self.ring_rects = []
            self.inventory_cells = []
            self.magazine_rect = pygame.Rect(0, 0, 0, 0)

        self._draw_hotbar(target, (width, height))
        self._draw_resources(target, (width, height))
        self._draw_hover_tooltip(target, (width, height))

        if self.drag_kind == "round":
            pygame.draw.circle(target, (*AMBER, 235), pygame.mouse.get_pos(), 5)
        screen.blit(target, (0, 0))


__all__ = ["HUD_VERSION", "HOTBAR_KEYS", "HudV3Shell", "InventoryFootprint"]
