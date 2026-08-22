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
    client = (ROOT / "client.py").read_text(encoding="utf-8")
    assert "self.audio.ui_key(event.key)" in client and "self.audio.update(self)" in client
    print(f"V120_AUDIO_OK loaded={len(audio.sounds)} source_wavs={len(list(SFX_ROOT.rglob('*.wav')))} jam_horn_burst=1")


if __name__ == "__main__":
    main()
