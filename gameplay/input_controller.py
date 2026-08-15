from __future__ import annotations

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
