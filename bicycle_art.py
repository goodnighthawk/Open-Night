from __future__ import annotations

import math
import pygame

from character_art import draw_character

BIKE_COLORS = [
    (47, 53, 57), (157, 53, 51), (53, 104, 142), (185, 153, 55),
    (55, 119, 77), (116, 73, 132), (190, 191, 183),
]


def _rotate_for_heading(surface: pygame.Surface, degrees: float) -> pygame.Surface:
    quarter_turn = abs((float(degrees) / 90.0) - round(float(degrees) / 90.0)) < 1e-4
    if quarter_turn:
        return pygame.transform.rotate(surface, degrees)
    return pygame.transform.rotozoom(surface, degrees, 1.0)


def _draw_bike_body(target: pygame.Surface, center: tuple[int, int], angle: float, color_index: int = 0, bike_scale: float = 1.0) -> pygame.Rect:
    """Draw a compact original top-down bicycle, front pointing along angle."""
    # Local sprite points east (+X), matching vehicle conventions.
    surf = pygame.Surface((58, 34), pygame.SRCALPHA)
    color = BIKE_COLORS[int(color_index) % len(BIKE_COLORS)]
    dark = (25, 27, 28)
    metal = (185, 188, 181)

    # Wheels viewed from above: narrow elongated outlines.
    pygame.draw.ellipse(surf, dark, pygame.Rect(4, 8, 16, 18), width=3)
    pygame.draw.ellipse(surf, dark, pygame.Rect(38, 8, 16, 18), width=3)
    rear = (12, 17)
    front = (46, 17)
    crank = (29, 17)
    seat = (24, 17)
    # Frame triangle / fork.
    pygame.draw.line(surf, color, rear, crank, 3)
    pygame.draw.line(surf, color, crank, front, 3)
    pygame.draw.line(surf, color, rear, seat, 3)
    pygame.draw.line(surf, color, seat, crank, 3)
    pygame.draw.line(surf, metal, seat, (31, 11), 2)
    pygame.draw.line(surf, metal, (31, 11), front, 2)
    pygame.draw.line(surf, dark, (29, 10), (35, 10), 2)  # handlebars
    pygame.draw.line(surf, dark, (21, 15), (27, 15), 3)  # seat
    pygame.draw.circle(surf, metal, crank, 3, width=1)

    scale = max(0.25, float(bike_scale))
    if abs(scale - 1.0) > 1e-6:
        surf = pygame.transform.scale(surf, (max(1, int(round(surf.get_width()*scale))), max(1, int(round(surf.get_height()*scale)))))
    rotated = _rotate_for_heading(surf, -math.degrees(angle))
    rect = rotated.get_rect(center=center)
    target.blit(rotated, rect)
    return rect


def draw_bicycle(
    target: pygame.Surface,
    center: tuple[int, int],
    angle: float,
    *,
    color_index: int = 0,
    rider_appearance: dict | None = None,
    moving: bool = False,
    anim_time: float = 0.0,
    local_ring: tuple[int, int, int] | None = None,
    rider_scale: int = 1,
    bike_scale: float = 1.0,
) -> pygame.Rect:
    # Ground shadow is deliberately lighter than a car shadow.
    bike_scale = max(0.25, float(bike_scale))
    shadow = pygame.Surface((max(1, int(round(44*bike_scale))), max(1, int(round(14*bike_scale)))), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (0, 0, 0, 75), shadow.get_rect())
    target.blit(shadow, shadow.get_rect(center=(center[0] + int(round(2*bike_scale)), center[1] + int(round(5*bike_scale)))))
    rect = _draw_bike_body(target, center, angle, color_index, bike_scale=bike_scale)

    if rider_appearance is not None:
        # Reuse the same player/NPC sprite system so cyclists belong to the same
        # visual population. The body is slightly offset toward the rear wheel.
        rider_center = (
            int(center[0] - math.cos(angle) * 2 * bike_scale),
            int(center[1] - math.sin(angle) * 2 * bike_scale - 2),
        )
        draw_character(
            target, rider_center, angle, rider_appearance, scale=max(1, int(rider_scale)),
            local_ring=local_ring, moving=moving, anim_time=anim_time,
        )
    elif local_ring is not None:
        pygame.draw.circle(target, local_ring, center, max(22, int(round(22*bike_scale))), width=2)
    return rect
