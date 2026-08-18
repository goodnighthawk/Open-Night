#!/usr/bin/env python3
"""Watch v1.0-art-overlay and beep when a new Map Lab iteration is locally testable.

A dedicated playback device is selected once and stored locally, so the ready
alert does not follow the Windows default device (for example headphones).
"""
from __future__ import annotations

from array import array
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "v1.0-art-overlay"
POLL_SECONDS = max(15, int(os.getenv("OPEN_NIGHT_MAP_LAB_WATCH_SECONDS", "60")))
STATE_PATH = ROOT / "artifacts" / "map_lab" / "watch_state.json"
AUDIO_CONFIG_PATH = ROOT / "artifacts" / "map_lab" / "audio_device.json"
RENDER_SCRIPT = ROOT / "tools" / "map_lab_render.py"

RELEVANT_EXACT = {
    "grid_world.py",
    "grid_renderer.py",
    "grid_runtime.py",
    "MAP_LAB.bat",
    "MAP_LAB_READY_WATCH.bat",
    "tools/generate_v100_ground_roof_layers.py",
    "tools/build_v100_grid_seed.py",
    "tools/map_lab.py",
    "tools/map_lab_render.py",
    "tools/map_lab_ready_watch.py",
}
RELEVANT_PREFIXES = (
    "mapfiles/data/map_001_gwb_corridor/grid_v100/",
    "assets/grid_v100/",
    "assets/source_packs/city_block/",
)


def _run(*args: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=str(ROOT),
        text=True,
        check=check,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def _git(*args: str) -> str:
    result = _run("git", *args, capture=True)
    return result.stdout.strip()


def _playback_devices() -> list[str]:
    import pygame
    from pygame._sdl2 import get_audio_device_names

    pygame.init()
    try:
        names = [str(name) for name in get_audio_device_names(False)]
    finally:
        pygame.mixer.quit()
        pygame.display.quit()
    # Keep order but remove duplicate names.
    return list(dict.fromkeys(names))


def _saved_audio_device() -> str | None:
    try:
        raw = json.loads(AUDIO_CONFIG_PATH.read_text(encoding="utf-8"))
        name = str(raw.get("device_name", "")).strip()
        return name or None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _save_audio_device(name: str) -> None:
    AUDIO_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIO_CONFIG_PATH.write_text(
        json.dumps({"device_name": name}, indent=2) + "\n",
        encoding="utf-8",
    )


def _configure_audio(force: bool = False) -> str:
    devices = _playback_devices()
    if not devices:
        raise RuntimeError("Windows/SDL reported no playback devices.")

    saved = _saved_audio_device()
    if saved and saved in devices and not force:
        return saved

    print("\nMap Lab alert playback devices:")
    for index, name in enumerate(devices, start=1):
        print(f"  {index}. {name}")
    print("Choose the MONITOR/HDMI/DisplayPort or motherboard speaker output you can hear without headphones.")

    while True:
        answer = input("Playback device number: ").strip()
        try:
            selected = devices[int(answer) - 1]
        except (ValueError, IndexError):
            print("Enter one of the numbers shown above.")
            continue
        _save_audio_device(selected)
        print(f"Saved Map Lab alert device: {selected}")
        return selected


def _tone_samples(frequency: float, duration: float, sample_rate: int = 44100) -> bytes:
    count = max(1, int(sample_rate * duration))
    amplitude = int(32767 * 0.45)
    samples = array(
        "h",
        (
            int(amplitude * math.sin(2.0 * math.pi * frequency * i / sample_rate))
            for i in range(count)
        ),
    )
    return samples.tobytes()


def _play_ready_sound(count: int = 3) -> None:
    """Play directly through the saved output device, not the Windows default."""
    import pygame

    device = _configure_audio(force=False)
    current = _playback_devices()
    if device not in current:
        print(f"[Map Lab Watch] Saved audio device is unavailable: {device}")
        device = _configure_audio(force=True)

    pygame.mixer.quit()
    pygame.mixer.init(
        frequency=44100,
        size=-16,
        channels=1,
        buffer=512,
        devicename=device,
    )
    try:
        frequencies = (880.0, 1175.0, 1568.0)
        for index in range(max(1, count)):
            frequency = frequencies[min(index, len(frequencies) - 1)]
            sound = pygame.mixer.Sound(buffer=_tone_samples(frequency, 0.20))
            channel = sound.play()
            if channel is not None:
                while channel.get_busy():
                    time.sleep(0.01)
            time.sleep(0.08)
    finally:
        pygame.mixer.quit()


def _is_relevant(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized in RELEVANT_EXACT or normalized.startswith(RELEVANT_PREFIXES)


def _working_tree_clean() -> bool:
    return not _git("status", "--porcelain")


def _current_branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD")


def _fetch_remote_head() -> str:
    _run("git", "fetch", "--quiet", "origin", BRANCH)
    return _git("rev-parse", f"origin/{BRANCH}")


def _local_head() -> str:
    return _git("rev-parse", "HEAD")


def _changed_paths(old_sha: str, new_sha: str) -> list[str]:
    if old_sha == new_sha:
        return []
    return [line for line in _git("diff", "--name-only", old_sha, new_sha).splitlines() if line.strip()]


def _save_state(sha: str, status: str) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "branch": BRANCH,
        "sha": sha,
        "status": status,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    STATE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _render_and_beep(sha: str, paths: list[str]) -> bool:
    print("[Map Lab Watch] Relevant map/runtime change detected:")
    for path in paths:
        if _is_relevant(path):
            print(f"  - {path}")
    print("[Map Lab Watch] Running local generator + validator + runtime proofs...")
    result = subprocess.run([sys.executable, str(RENDER_SCRIPT)], cwd=str(ROOT))
    if result.returncode:
        _save_state(sha, "render_failed")
        print("[Map Lab Watch] New commit pulled, but Map Lab validation/render failed. No ready beep.")
        return False

    _save_state(sha, "ready")
    print("\n============================================================")
    print("CHECK MAP_LAB — new visual iteration passed local proof")
    print(f"commit {sha[:12]}")
    print("============================================================\n")
    try:
        _play_ready_sound(3)
    except Exception as exc:
        print(f"[Map Lab Watch] READY, but dedicated audio alert failed: {exc}")
        print("[Map Lab Watch] Run MAP_LAB_READY_WATCH.bat again to reselect/test the playback device.")
    return True


def _process_remote(remote_sha: str) -> str:
    local_sha = _local_head()
    if remote_sha == local_sha:
        return local_sha

    if not _working_tree_clean():
        print("[Map Lab Watch] New remote version exists, but your working tree has local changes.")
        print("[Map Lab Watch] Commit/stash/revert them; I will retry automatically. No ready beep yet.")
        return local_sha

    paths = _changed_paths(local_sha, remote_sha)
    relevant = [path for path in paths if _is_relevant(path)]

    print(f"[Map Lab Watch] Updating {local_sha[:8]} -> {remote_sha[:8]}...")
    pull = _run("git", "pull", "--ff-only", "origin", BRANCH, check=False)
    if pull.returncode:
        print("[Map Lab Watch] Could not fast-forward automatically. Resolve the git state, then leave this watcher running.")
        return local_sha

    new_local = _local_head()
    if relevant:
        _render_and_beep(new_local, relevant)
    else:
        _save_state(new_local, "non_visual_update")
        print("[Map Lab Watch] Pulled a non-visual update; no Map Lab beep.")
    return new_local


def main() -> None:
    if "--configure-audio" in sys.argv:
        device = _configure_audio(force=True)
        print(f"Testing dedicated device: {device}")
        _play_ready_sound(1)
        return

    if "--test-beep" in sys.argv:
        device = _configure_audio(force=False)
        print(f"Testing dedicated device: {device}")
        _play_ready_sound(1)
        return

    if not (ROOT / ".git").exists():
        raise SystemExit("Run this from the cloned Open Night repository.")
    if not RENDER_SCRIPT.is_file():
        raise SystemExit(f"Missing {RENDER_SCRIPT}")

    branch = _current_branch()
    if branch != BRANCH:
        raise SystemExit(
            f"Map Lab Watch requires branch {BRANCH!r}. Current branch is {branch!r}. "
            "Switch branches in GitHub Desktop, then run the watcher again."
        )

    device = _configure_audio(force=False)
    print("Open Night — Map Lab Ready Watch")
    print(f"Branch: {BRANCH}")
    print(f"Dedicated alert device: {device}")
    print(f"Checking origin every {POLL_SECONDS} seconds.")
    print("TRIPLE BEEP = a new relevant version was pulled and Map Lab proof passed.")
    print("Headphones may remain the Windows default; this alert uses the saved device directly.")
    print("Leave this window open; press Ctrl+C to stop.\n")

    try:
        while True:
            try:
                remote_sha = _fetch_remote_head()
                _process_remote(remote_sha)
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or "").strip()
                print(f"[Map Lab Watch] Git check failed; retrying. {detail}")
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\n[Map Lab Watch] Stopped.")


if __name__ == "__main__":
    main()
