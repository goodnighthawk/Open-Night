#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    version_txt = read("VERSION.txt").strip()
    versioning = read("versioning.py")
    updater = read("UPDATE_OPEN_NIGHT.bat")
    launcher = read("START_OPEN_NIGHT.bat")
    player_launcher = read("open_night_player_launcher.py")
    client_entry = read("main.py")
    railway_entry = read("railway_entry.py")
    run_client = read("RUN_CLIENT.bat")
    run_server = read("RUN_SERVER.bat")

    # main is the only supported player-update branch. Development branches may
    # remain in GitHub history, but normal players must never depend on them.
    assert 'CURRENT_BRANCH!"=="main"' in updater, "updater does not require main"
    assert "fetch --quiet origin main" in updater, "updater does not fetch main"
    assert "pull --ff-only --quiet origin main" in updater, "updater does not fast-forward main"
    for stale in ("v1.0-art-overlay", "v1.1-bug-review", "v0.9.0-consolidation"):
        assert stale not in updater, f"player updater still references development branch {stale}"
    assert "open_night_player_launcher.py" in launcher, "player entry does not open the canonical launcher"
    assert "UPDATE TO LATEST VERSION" in player_launcher, "launcher lacks the prominent update action"
    assert "self.launch_update" in player_launcher, "launcher update action is not wired"

    # The promoted main build keeps one exact wire version so stale clients
    # remain incompatible rather than silently connecting across protocol changes.
    assert version_txt, "VERSION.txt is empty"
    assert f'GAME_VERSION = "{version_txt}"' in versioning, "VERSION.txt/versioning.py authority diverged"

    # Every public launch surface must enter the same tested v1.1 adapters.
    assert "from v100_client import main" in client_entry, "web entry bypasses canonical client"
    assert "from v100_server import main as run_v100_server" in railway_entry, "Railway bypasses canonical server"
    assert "v100_client.py" in run_client, "desktop client bypasses canonical client"
    assert "v100_server.py" in run_server, "desktop server bypasses canonical server"

    print(f"main release audit passed: main-only updater + canonical v{version_txt} runtime")


if __name__ == "__main__":
    main()
