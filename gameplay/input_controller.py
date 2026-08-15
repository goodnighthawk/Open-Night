from __future__ import annotations

import math
import pygame


def movement_vector(blocked: bool = False) -> tuple[float, float]:
    """Return WASD/arrow intent only. Mouse position never changes movement."""
    if blocked:
        return 0.0, 0.0
    keys = pygame.key.get_pressed()
    x = float(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - float(keys[pygame.K_a] or keys[pygame.K_LEFT])
    y = float(keys[pygame.K_s] or keys[pygame.K_DOWN]) - float(keys[pygame.K_w] or keys[pygame.K_UP])
    mag = math.hypot(x, y)
    if mag > 1.0:
        x, y = x / mag, y / mag
    return x, y


def aim_angle(player_world: tuple[float, float], mouse_world: tuple[float, float], fallback: float = 0.0) -> float:
    dx = mouse_world[0] - player_world[0]
    dy = mouse_world[1] - player_world[1]
    if abs(dx) + abs(dy) < 1e-6:
        return fallback
    return math.atan2(dy, dx)
