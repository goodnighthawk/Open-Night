from __future__ import annotations

import os
from pathlib import Path
import sys

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
    client = (ROOT / "client.py").read_text(encoding="utf-8")
    assert "self.audio.ui_key(event.key)" in client and "self.audio.update(self)" in client
    print(f"V120_AUDIO_OK loaded={len(audio.sounds)} source_wavs={len(list(SFX_ROOT.rglob('*.wav')))}")


if __name__ == "__main__":
    main()
