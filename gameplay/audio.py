from __future__ import annotations

"""Fail-soft desktop sound layer backed by the approved SFX source pack."""

import math
from pathlib import Path
import sys
import time

import pygame


SFX_ROOT = Path(__file__).resolve().parents[1] / "assets" / "source_packs" / "SFX"


class GameAudio:
    def __init__(self) -> None:
        self.enabled = False
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self.engine_channel: pygame.mixer.Channel | None = None
        self.last_step = 0.0
        self.last_horn: dict[str, float] = {}
        self.previous_in_vehicle = False
        self.previous_speed = 0.0
        if sys.platform == "emscripten":
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.set_num_channels(max(16, pygame.mixer.get_num_channels()))
            files = {
                "ui_move": "GUI/SFX_FE_DOWN_STEREO.wav",
                "ui_accept": "GUI/SFX_FE_RETURN_STEREO.wav",
                "ui_back": "GUI/SFX_FE_ESCAPE_STEREO.wav",
                "step_concrete_1": "FOOTSTEP/SFX_FOOTSEP_CONCRETE_1.wav",
                "step_concrete_2": "FOOTSTEP/SFX_FOOTSEP_CONCRETE_2.wav",
                "step_grass_1": "FOOTSTEP/SFX_FOOTSEP_GRASS_1.wav",
                "step_grass_2": "FOOTSTEP/SFX_FOOTSEP_GRASS_2.wav",
                "engine": "SFX_STANDARD_SALOON_ENGINE.wav",
                "horn": "SFX_STANDARD_HORN.wav",
                "door_open": "SFX_CAR_DOOR_OPEN_1.wav",
                "door_close": "SFX_CAR_DOOR_CLOSE_1.wav",
                "skid": "SFX_SKIDDING_ROAD_1.wav",
                "collision_soft": "SFX_COLLISION_CAR_CAR_SOFT.wav",
                "collision_hard": "SFX_COLLISION_CAR_CAR_HARD.wav",
            }
            for key, relative in files.items():
                path = SFX_ROOT / relative
                if path.is_file():
                    self.sounds[key] = pygame.mixer.Sound(path)
            self.enabled = len(self.sounds) == len(files)
        except (OSError, pygame.error):
            self.enabled = False

    def _play(self, key: str, volume: float = 1.0) -> pygame.mixer.Channel | None:
        if not self.enabled or key not in self.sounds:
            return None
        try:
            channel = self.sounds[key].play()
            if channel is not None:
                channel.set_volume(max(0.0, min(1.0, volume)))
            return channel
        except pygame.error:
            return None

    def ui_key(self, key: int) -> None:
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_e, pygame.K_t):
            self._play("ui_accept", 0.28)
        elif key == pygame.K_ESCAPE:
            self._play("ui_back", 0.25)
        elif key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_TAB):
            self._play("ui_move", 0.18)

    @staticmethod
    def _distance_volume(local, x: float, y: float, radius: float = 1500.0) -> float:
        distance = math.hypot(float(local.render_x) - x, float(local.render_y) - y)
        return max(0.0, min(0.75, (1.0 - distance / radius) * 0.75))

    def update(self, game) -> None:
        if not self.enabled:
            return
        local = game.players.get(game.local_id or "")
        if local is None:
            return
        now = time.monotonic()
        in_vehicle = bool(getattr(local, "in_vehicle", False))
        vehicle = game.vehicles.get(str(getattr(local, "vehicle_id", ""))) if in_vehicle else None
        speed = abs(float(getattr(vehicle, "speed", 0.0))) if vehicle is not None else 0.0

        if in_vehicle != self.previous_in_vehicle:
            self._play("door_close" if in_vehicle else "door_open", 0.65)
            self.previous_in_vehicle = in_vehicle

        if in_vehicle:
            if self.engine_channel is None or not self.engine_channel.get_busy():
                self.engine_channel = self.sounds["engine"].play(loops=-1, fade_ms=120)
            if self.engine_channel is not None:
                self.engine_channel.set_volume(min(0.52, 0.16 + speed / 520.0))
            drop = self.previous_speed - speed
            if self.previous_speed > 95.0 and drop > 80.0:
                self._play("collision_hard" if drop > 150.0 else "collision_soft", 0.72)
            keys = pygame.key.get_pressed()
            if speed > 90.0 and (keys[pygame.K_a] or keys[pygame.K_d]) and now - self.last_step > 0.8:
                self._play("skid", min(0.5, speed / 400.0))
                self.last_step = now
        else:
            if self.engine_channel is not None:
                self.engine_channel.fadeout(180)
                self.engine_channel = None
            moving = now < float(getattr(local, "moving_until", 0.0))
            if moving and now - self.last_step >= 0.30:
                surface = "sidewalk"
                if game.grid_world is not None:
                    surface = game.grid_world.collision_at("ground", local.render_x, local.render_y)
                variant = 1 + (int(now * 10.0) & 1)
                material = "grass" if surface in {"grass", "park"} else "concrete"
                self._play(f"step_{material}_{variant}", 0.32)
                self.last_step = now

        self.previous_speed = speed
        for car in game.vehicles.values():
            if not bool(getattr(car, "horn", False)) or now - self.last_horn.get(car.id, 0.0) < 0.8:
                continue
            volume = self._distance_volume(local, car.render_x, car.render_y)
            if volume > 0.02:
                self._play("horn", volume)
            self.last_horn[car.id] = now
