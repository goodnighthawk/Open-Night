from __future__ import annotations

import math


def directional_jump_velocity(input_x: float, input_y: float, speed: float, *, deadzone: float = 0.05) -> tuple[float, float]:
    """Return jump impulse from movement held on the jump frame only.

    A stationary jump has no horizontal/world-plane impulse. Aim/facing is never
    used as a fallback direction; this keeps Space-only jumps vertical and leaves
    stationary interaction jumps (for example a fire escape) free to use their
    own transition logic.
    """
    try:
        x = float(input_x)
        y = float(input_y)
        magnitude = math.hypot(x, y)
        jump_speed = max(0.0, float(speed))
        threshold = max(0.0, float(deadzone))
    except (TypeError, ValueError):
        return 0.0, 0.0
    if jump_speed <= 0.0 or magnitude <= threshold:
        return 0.0, 0.0
    return x / magnitude * jump_speed, y / magnitude * jump_speed
