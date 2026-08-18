#!/usr/bin/env python3
"""Run the Map Lab watcher with a repeating ready alarm.

Normal ready notifications repeat through the watcher-selected dedicated playback
device until the user presses Space in the watcher console. Startup audio tests
remain short single beeps. Readiness uses the building-scale Map Lab renderer.
"""
from __future__ import annotations

import sys
import time

import map_lab_ready_watch as base

# The watcher must validate the same preview the user will actually inspect.
base.RENDER_SCRIPT = base.ROOT / "tools" / "map_lab_render_zoomed.py"


def _drain_console_keys() -> None:
    """Discard stale console keypresses before a new ready alarm starts."""
    if sys.platform != "win32":
        return
    import msvcrt

    while msvcrt.kbhit():
        char = msvcrt.getwch()
        if char in {"\x00", "\xe0"} and msvcrt.kbhit():
            msvcrt.getwch()


def _space_pressed() -> bool:
    if sys.platform != "win32":
        return False
    import msvcrt

    pressed = False
    while msvcrt.kbhit():
        char = msvcrt.getwch()
        if char == " ":
            pressed = True
        elif char in {"\x00", "\xe0"} and msvcrt.kbhit():
            msvcrt.getwch()
    return pressed


def _wait_with_space_check(seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if _space_pressed():
            return True
        time.sleep(0.015)
    return _space_pressed()


def _continuous_ready_alarm(_count: int = 3) -> None:
    """Repeat an audible alarm until Space is pressed in the watcher window."""
    import pygame

    device = base._configure_audio(force=False)
    current = base._playback_devices()
    if device not in current:
        print(f"[Map Lab Watch] Saved audio device is unavailable: {device}")
        device = base._configure_audio(force=True)

    pygame.mixer.quit()
    pygame.mixer.init(
        frequency=44100,
        size=-16,
        channels=1,
        buffer=512,
        devicename=device,
    )

    sounds = [
        pygame.mixer.Sound(buffer=base._tone_samples(740.0, 0.28)),
        pygame.mixer.Sound(buffer=base._tone_samples(1046.5, 0.28)),
        pygame.mixer.Sound(buffer=base._tone_samples(1396.9, 0.28)),
    ]
    _drain_console_keys()

    print("[Map Lab Watch] READY ALARM — press SPACE in this window to silence it.")
    print(f"[Map Lab Watch] Alarm output: {device}")

    try:
        while True:
            for sound in sounds:
                if _space_pressed():
                    return
                channel = sound.play()
                if channel is not None:
                    while channel.get_busy():
                        if _space_pressed():
                            channel.stop()
                            return
                        time.sleep(0.015)
                if _wait_with_space_check(0.055):
                    return
            if _wait_with_space_check(0.14):
                return
    finally:
        pygame.mixer.stop()
        pygame.mixer.quit()
        print("[Map Lab Watch] Alert silenced — monitoring resumed.")


def main() -> None:
    # Keep startup/configuration checks short. Only real ready notifications use
    # the repeating acknowledgement alarm.
    if "--test-beep" not in sys.argv and "--configure-audio" not in sys.argv:
        base._play_ready_sound = _continuous_ready_alarm
    base.main()


if __name__ == "__main__":
    main()
