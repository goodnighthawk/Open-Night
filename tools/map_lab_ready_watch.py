#!/usr/bin/env python3
"""Watch v1.0-art-overlay and beep when a new Map Lab iteration is locally testable.

The watcher intentionally uses git rather than GitHub Actions as its readiness gate:
when a new relevant remote commit appears, it fast-forwards the local branch, runs
the real Map Lab renderer/validator in a fresh process, and only beeps after that
render succeeds.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "v1.0-art-overlay"
POLL_SECONDS = max(15, int(os.getenv("OPEN_NIGHT_MAP_LAB_WATCH_SECONDS", "60")))
STATE_PATH = ROOT / "artifacts" / "map_lab" / "watch_state.json"
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


def _system_beep(count: int = 3) -> None:
    """Play through the Windows default playback device when possible.

    MessageBeep uses the configured Windows system sound, so it follows the
    active/default playback path (for example HDMI/DisplayPort monitor audio or
    motherboard/onboard audio). winsound.Beep and the console bell are fallbacks.
    """
    try:
        import winsound

        for _ in range(max(1, count)):
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            time.sleep(0.22)
        return
    except Exception:
        pass

    try:
        import winsound

        for frequency in (880, 1175, 1568)[: max(1, count)]:
            winsound.Beep(frequency, 180)
            time.sleep(0.08)
        return
    except Exception:
        pass

    print("\a" * max(1, count), end="", flush=True)


def _beep_ready() -> None:
    _system_beep(3)


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
    _beep_ready()
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
    if "--test-beep" in sys.argv:
        print("[Map Lab Watch] Testing Windows default playback device...")
        _system_beep(1)
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

    print("Open Night — Map Lab Ready Watch")
    print(f"Branch: {BRANCH}")
    print(f"Checking origin every {POLL_SECONDS} seconds.")
    print("TRIPLE SYSTEM BEEP = a new relevant version was pulled and Map Lab proof passed.")
    print("The beep follows the Windows default playback device.")
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
