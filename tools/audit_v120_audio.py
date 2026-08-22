from __future__ import annotations

import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame

from gameplay.audio import GameAudio, SFX_ROOT


def main() -> None:
    expected = {
        "GUI/SFX_FE_DOWN_STEREO.wav",
        "GUI/SFX_FE_RETURN_STEREO.wav",
        "GUI/SFX_FE_ESCAPE_STEREO.wav",
        "FOOTSTEP/SFX_FOOTSEP_CONCRETE_1.wav",
        "FOOTSTEP/SFX_FOOTSEP_GRASS_1.wav",
        "SFX_STANDARD_SALOON_ENGINE.wav",
        "SFX_STANDARD_HORN.wav",
        "SFX_CAR_DOOR_OPEN_1.wav",
        "SFX_COLLISION_CAR_CAR_HARD.wav",
        "SFX_SKIDDING_ROAD_1.wav",
    }
    assert all((SFX_ROOT / path).is_file() for path in expected)
    pygame.init()
    audio = GameAudio()
    assert audio.enabled and len(audio.sounds) == 14
    played = []
    audio._play = lambda key, volume=1.0: played.append((key, volume))  # type: ignore[method-assign]
    audio.last_any_horn = time.monotonic() - 2.0
    local = SimpleNamespace(render_x=0.0, render_y=0.0, in_vehicle=False, vehicle_id="", moving_until=0.0)
    jam = {
        f"car{index}": SimpleNamespace(
            id=f"car{index}", horn=True, render_x=80.0 + index * 4.0, render_y=0.0,
        )
        for index in range(20)
    }
    game = SimpleNamespace(players={"local": local}, local_id="local", vehicles=jam, grid_world=None)
    audio.update(game)
    audio.update(game)
    assert [key for key, _volume in played].count("horn") == 1, played
    original_keys = pygame.key.get_pressed
    try:
        class Keys:
            def __init__(self, steering=False): self.steering = steering
            def __getitem__(self, key): return self.steering and key == pygame.K_a
        local.in_vehicle = True
        local.vehicle_id = "player-car"
        game.vehicles = {"player-car": SimpleNamespace(speed=220.0)}
        pygame.key.get_pressed = lambda: Keys(False)  # type: ignore[assignment]
        audio.update(game)
        assert not any(key == "skid" for key, _volume in played), played
        pygame.key.get_pressed = lambda: Keys(True)  # type: ignore[assignment]
        audio.steering_since = time.monotonic() - 1.0
        audio.last_skid = time.monotonic() - 5.0
        audio.update(game)
        assert [key for key, _volume in played].count("skid") == 1, played
        audio.update(game)
        assert [key for key, _volume in played].count("skid") == 1, played
    finally:
        pygame.key.get_pressed = original_keys  # type: ignore[assignment]
    client = (ROOT / "client.py").read_text(encoding="utf-8")
    assert "self.audio.ui_key(event.key)" in client and "self.audio.update(self)" in client
    print(f"V120_AUDIO_OK loaded={len(audio.sounds)} source_wavs={len(list(SFX_ROOT.rglob('*.wav')))} jam_horn_burst=1 sustained_turn_skid=1")


if __name__ == "__main__":
    main()
