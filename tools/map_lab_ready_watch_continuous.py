#!/usr/bin/env python3
"""Run the Map Lab watcher with a repeating ready alarm and manual GPT nudge.

Normal ready notifications repeat through the watcher-selected dedicated playback
device until the user presses Space in the watcher console. Pressing Enter while
monitoring creates a concise continuation prompt for the current Open Night
Ground pass, copies it to the Windows clipboard, and opens ChatGPT so the user
can paste/send the nudge if the active assistant has gone quiet or off-task.
Startup audio tests remain short single beeps. Readiness uses the building-scale
Map Lab renderer.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import webbrowser

import map_lab_ready_watch as base

# The watcher must validate the same preview the user will actually inspect.
base.RENDER_SCRIPT = base.ROOT / "tools" / "map_lab_render_zoomed.py"

_SPACE_EVENT = threading.Event()
_STOP_EVENT = threading.Event()
_PING_LOCK = threading.Lock()
NUDGE_PATH = base.ROOT / "artifacts" / "map_lab" / "gpt_nudge.txt"
NUDGE_STATE_PATH = base.ROOT / "artifacts" / "map_lab" / "gpt_nudge.json"
CHATGPT_URL = "https://chatgpt.com/"


def _space_pressed() -> bool:
    if _SPACE_EVENT.is_set():
        _SPACE_EVENT.clear()
        return True
    return False


def _wait_with_space_check(seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if _space_pressed():
            return True
        time.sleep(0.015)
    return _space_pressed()


def _current_nudge_prompt() -> tuple[str, str, str]:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        sha = base._local_head()
        subject = base._git("show", "-s", "--format=%s", sha)
    except Exception:
        sha = "unknown"
        subject = "unable to read local commit"

    prompt = f"""Open Night watcher manual nudge — {timestamp}

Continue the Open Night Ground pass on branch v1.0-art-overlay from the current repository state.
Current local HEAD: {sha[:12]} — {subject}

Stay focused on the next meaningful Ground visual improvement and commit/push it when ready for Map Lab validation. Use the city_block reference example_small.png for building/sidewalk/road proportions and detail density. The sidewalk alignment and the four straight curb directions are already considered correct and should stay locked; only curb outer corners should be changed if visual proof shows they are wrong. Keep the building-scale Map Lab preview as the visual authority, keep Ground/Roof footprint registration exact, and do not divert effort into unrelated layers or launcher cosmetics until the Ground pass is materially improved.

Check the current repo/PR state first so you continue from the newest work rather than repeating an older step. Then make the next concrete implementation update."""
    return timestamp, sha, prompt


def _copy_to_clipboard(text: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        result = subprocess.run(
            ["clip.exe"],
            input=text,
            text=True,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except OSError:
        return False


def _manual_gpt_ping() -> None:
    if not _PING_LOCK.acquire(blocking=False):
        print("[Map Lab Watch] GPT nudge is already being prepared.")
        return
    try:
        timestamp, sha, prompt = _current_nudge_prompt()
        NUDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        NUDGE_PATH.write_text(prompt + "\n", encoding="utf-8")
        NUDGE_STATE_PATH.write_text(
            json.dumps(
                {
                    "timestamp": timestamp,
                    "head": sha,
                    "branch": base.BRANCH,
                    "prompt_file": str(NUDGE_PATH),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        copied = _copy_to_clipboard(prompt)
        print("\n============================================================")
        print(f"[Map Lab Watch] GPT NUDGE — {timestamp}")
        print(f"[Map Lab Watch] HEAD {sha[:12]}")
        if copied:
            print("[Map Lab Watch] Continuation prompt copied to clipboard.")
        else:
            print(f"[Map Lab Watch] Clipboard copy unavailable; prompt saved to {NUDGE_PATH}")
        print("[Map Lab Watch] Opening ChatGPT. Paste/send the prompt in the active Open Night conversation.")
        print("============================================================\n")
        try:
            webbrowser.open(CHATGPT_URL, new=2)
        except Exception as exc:
            print(f"[Map Lab Watch] Could not open ChatGPT automatically: {exc}")
    finally:
        _PING_LOCK.release()


def _keyboard_loop() -> None:
    """Central Windows console key reader: Space acknowledges, Enter nudges GPT."""
    if sys.platform != "win32":
        return
    import msvcrt

    while not _STOP_EVENT.is_set():
        if not msvcrt.kbhit():
            time.sleep(0.025)
            continue
        char = msvcrt.getwch()
        if char == " ":
            _SPACE_EVENT.set()
        elif char in {"\r", "\n"}:
            threading.Thread(target=_manual_gpt_ping, daemon=True).start()
        elif char in {"\x00", "\xe0"} and msvcrt.kbhit():
            msvcrt.getwch()


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
    _SPACE_EVENT.clear()

    alarm_started = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[Map Lab Watch] READY ALARM STARTED — {alarm_started}")
    print("[Map Lab Watch] Press SPACE in this window to silence it.")
    print("[Map Lab Watch] Press ENTER at any time to prepare a GPT continuation nudge.")
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
    if "--test-beep" in sys.argv or "--configure-audio" in sys.argv:
        base.main()
        return

    # Configure before the keyboard thread starts so first-run numeric input is
    # not consumed by the non-blocking Enter/Space reader.
    base._configure_audio(force=False)

    keyboard_thread: threading.Thread | None = None
    if sys.platform == "win32":
        keyboard_thread = threading.Thread(target=_keyboard_loop, daemon=True)
        keyboard_thread.start()

    base._play_ready_sound = _continuous_ready_alarm
    try:
        base.main()
    finally:
        _STOP_EVENT.set()
        if keyboard_thread is not None:
            keyboard_thread.join(timeout=0.2)


if __name__ == "__main__":
    main()
