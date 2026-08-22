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
    character_art = read("character_art.py")
    character_catalog = read("character_catalog.py")

    # main is the only supported player-update branch. Development branches may
    # remain in GitHub history, but normal players must never depend on them.
    assert 'CURRENT_BRANCH!"=="main"' in updater, "updater does not require main"
    assert "+main:refs/remotes/origin/main" in updater, "updater does not refresh origin/main"
    assert "UPDATE_TIMEOUT_SECONDS=30" in updater and "WaitForExit" in updater, "updater network check has no timeout"
    assert "merge --ff-only --quiet origin/main" in updater, "updater does not fast-forward main"
    for stale in ("v1.0-art-overlay", "v1.1-bug-review", "v0.9.0-consolidation"):
        assert stale not in updater, f"player updater still references development branch {stale}"
    assert "open_night_player_launcher.py" in launcher, "player entry does not open the canonical launcher"
    assert "UPDATE TO LATEST VERSION" in player_launcher, "launcher lacks the prominent update action"
    assert "self.launch_update" in player_launcher, "launcher update action is not wired"
    assert not (ROOT / "RUN_MAP_GENERATOR.bat").exists(), "public Map Generator launcher still ships"

    # The promoted main build keeps one exact wire version so stale clients
    # remain incompatible rather than silently connecting across protocol changes.
    assert version_txt, "VERSION.txt is empty"
    assert f'GAME_VERSION = "{version_txt}"' in versioning, "VERSION.txt/versioning.py authority diverged"

    # Every public launch surface must enter the same tested v1.1 adapters.
    assert "from v100_client import main" in client_entry, "web entry bypasses canonical client"
    assert "from v100_server import main as run_v100_server" in railway_entry, "Railway bypasses canonical server"
    assert "v100_client.py" in run_client, "desktop client bypasses canonical client"
    assert "v100_server.py" in run_server, "desktop server bypasses canonical server"

    # v2.0 replaces the live paper doll with the approved grungy 90-degree
    # character sheet. The cleaned master and every extracted runtime layer
    # must ship together; the renderer may not silently use the retired pack.
    character_pack = ROOT / "assets" / "characters" / "grunge_topdown"
    assert (character_pack / "master_8x10_v2_clean.png").is_file(), "v2.0 master character sheet is missing"
    assert len(list((character_pack / "hats").glob("hat_*.png"))) == 8, "v2.0 hat layers are incomplete"
    assert len(list((character_pack / "heads").glob("head_*.png"))) == 8, "v2.0 head layers are incomplete"
    assert len(list((character_pack / "bodies").glob("body_*.png"))) == 64, "v2.0 movement layers are incomplete"
    assert "grunge_topdown" in character_catalog, "character catalog does not select the v2.0 pack"
    assert "pygame.transform.rotate" in character_art, "v2.0 renderer does not rotate the 90-degree art"
    assert "def _composed_frame" in character_art, "v2.0 layered character composer is missing"

    print(f"main release audit passed: main-only updater + canonical v{version_txt} runtime")


if __name__ == "__main__":
    main()
