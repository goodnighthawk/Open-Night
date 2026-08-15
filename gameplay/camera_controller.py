from __future__ import annotations

import math


class LookAheadCamera:
    """Smooth camera with bounded mouse look-ahead.

    The mouse can reveal more of the world in the direction the player is aiming,
    but only up to a configured cap. Walking/driving remains entirely independent
    of aim direction.
    """

    def __init__(self, tuning: dict):
        self.tuning = dict(tuning or {})
        self.x = 0.0
        self.y = 0.0
        self.look_x = 0.0
        self.look_y = 0.0
        self.initialized = False

    @staticmethod
    def _exp_lerp(current: float, target: float, strength: float, dt: float) -> float:
        if dt <= 0.0:
            return current
        t = 1.0 - math.exp(-max(0.01, strength) * dt)
        return current + (target - current) * t

    def _desired_look(self, mouse_pos: tuple[int, int], screen_size: tuple[int, int], driving: bool) -> tuple[float, float]:
        if not bool(self.tuning.get("lookahead_enabled", True)):
            return 0.0, 0.0
        sw, sh = screen_size
        mx, my = mouse_pos
        vx = float(mx) - sw * 0.5
        vy = float(my) - sh * 0.5
        dist = math.hypot(vx, vy)
        deadzone = max(0.0, float(self.tuning.get("deadzone_px", 70.0)))
        full_dist = max(deadzone + 1.0, float(self.tuning.get("full_lookahead_mouse_distance_px", 480.0)))
        if dist <= deadzone or dist <= 1e-6:
            return 0.0, 0.0
        max_px = float(self.tuning.get("driving_max_px" if driving else "walking_max_px", 320.0 if driving else 220.0))
        fraction = max(0.0, min(1.0, (dist - deadzone) / (full_dist - deadzone)))
        # Smoothstep avoids a sharp camera jump as the mouse crosses the deadzone.
        fraction = fraction * fraction * (3.0 - 2.0 * fraction)
        return vx / dist * max_px * fraction, vy / dist * max_px * fraction

    def update(
        self,
        player_pos: tuple[float, float],
        mouse_pos: tuple[int, int],
        screen_size: tuple[int, int],
        world_size: tuple[float, float],
        dt: float,
        *,
        driving: bool = False,
        view_rotation_degrees: float = 0.0,
        force_center: bool = False,
    ) -> None:
        px, py = player_pos
        sw, sh = screen_size
        world_w, world_h = world_size
        desired_x, desired_y = self._desired_look(mouse_pos, screen_size, driving)
        if force_center:
            desired_x = desired_y = 0.0
            self.look_x = self.look_y = 0.0
        # Mouse look-ahead is expressed in screen space. When the camera view is
        # rotated, convert that vector back into world axes before moving the camera.
        theta = math.radians(float(view_rotation_degrees))
        c, sn = math.cos(theta), math.sin(theta)
        desired_x, desired_y = (c * desired_x - sn * desired_y, sn * desired_x + c * desired_y)
        returning = abs(desired_x) < abs(self.look_x) or abs(desired_y) < abs(self.look_y)
        strength = float(self.tuning.get("return_smoothing_per_second" if returning else "smoothing_per_second", 10.0 if returning else 8.5))
        self.look_x = self._exp_lerp(self.look_x, desired_x, strength, dt)
        self.look_y = self._exp_lerp(self.look_y, desired_y, strength, dt)

        target_x = px - sw * 0.5 + self.look_x
        target_y = py - sh * 0.5 + self.look_y
        max_x = max(0.0, float(world_w) - sw)
        max_y = max(0.0, float(world_h) - sh)
        target_x = max(0.0, min(max_x, target_x))
        target_y = max(0.0, min(max_y, target_y))

        if force_center:
            # Rotation is a view transform around the local player. Do not let
            # look-ahead or camera smoothing move the pivot away from screen center.
            self.x, self.y = target_x, target_y
            self.initialized = True
        elif not self.initialized:
            self.x, self.y = target_x, target_y
            self.initialized = True
        else:
            self.x = self._exp_lerp(self.x, target_x, strength, dt)
            self.y = self._exp_lerp(self.y, target_y, strength, dt)
            self.x = max(0.0, min(max_x, self.x))
            self.y = max(0.0, min(max_y, self.y))

    def position(self) -> tuple[float, float]:
        return self.x, self.y

    def center(self, view_size: tuple[int, int]) -> tuple[float, float]:
        sw, sh = view_size
        return self.x + sw * 0.5, self.y + sh * 0.5

    def world_to_screen(self, x: float, y: float) -> tuple[int, int]:
        return int(x - self.x), int(y - self.y)

    def screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        return float(x) + self.x, float(y) + self.y

    def reset(self) -> None:
        self.initialized = False
        self.look_x = self.look_y = 0.0
