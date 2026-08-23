"""Carried release gate for the v2.6 character-art archive and map authority."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pygame


ROOT = Path(__file__).resolve().parents[1]
CHARACTER_ROOT = ROOT / "assets" / "characters" / "grunge_topdown"
GROUND_PATH = "mapfiles/data/map_001_gwb_corridor/grid_v100/ground_generated_objects.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _committed_ground_data() -> dict:
    raw = subprocess.check_output(
        ["git", "show", f"HEAD:{GROUND_PATH}"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    )
    return json.loads(raw)


def main() -> int:
    release = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
    assert tuple(int(part) for part in release.split(".")) >= (2, 6)
    assert f'GAME_VERSION = "{release}"' in (ROOT / "versioning.py").read_text(encoding="utf-8")
    assert f'SERVER_NAME = "Open Night v{release}"' in (ROOT / "server.py").read_text(encoding="utf-8")
    assert f"server_name,Open Night v{release}" in (ROOT / "server_config.csv").read_text(encoding="utf-8")
    assert f"open-night-v{release}" in (ROOT / "railway.toml").read_text(encoding="utf-8")
    assert f"OPEN NIGHT v{release}" in (ROOT / "RUN_CLIENT.bat").read_text(encoding="utf-8")
    assert f"OPEN NIGHT v{release}" in (ROOT / "RUN_SERVER.bat").read_text(encoding="utf-8")

    source_names = ("master_8x10.png", "master_8x10_v2.png")
    runtime_name = "master_8x10_v2_clean.png"
    paths = [CHARACTER_ROOT / name for name in (*source_names, runtime_name)]
    assert all(path.is_file() for path in paths)
    assert len({_sha256(path) for path in paths}) == len(paths)

    pygame.init()
    source_surfaces = [pygame.image.load(CHARACTER_ROOT / name) for name in source_names]
    runtime_surface = pygame.image.load(CHARACTER_ROOT / runtime_name)
    assert all(surface.get_size() == (1254, 1254) for surface in source_surfaces)
    assert runtime_surface.get_size() == (1280, 1280)
    assert all(surface.get_at((0, 0)).a == 255 for surface in source_surfaces)
    assert runtime_surface.get_at((0, 0)).a == 0

    art_code = (ROOT / "character_art.py").read_text(encoding="utf-8")
    assert f'pack_root() / "{runtime_name}"' in art_code
    assert 'pack_root() / "master_8x10.png"' not in art_code
    assert 'pack_root() / "master_8x10_v2.png"' not in art_code

    committed = _committed_ground_data()
    objects = committed["objects"]
    lane_dividers = [obj for obj in objects if str(obj.get("street_marking", "")).startswith("lane_divider_")]
    crossings = [obj for obj in objects if str(obj.get("street_marking", "")).startswith("zebra_")]
    assert len(lane_dividers) == 464
    assert all(obj.get("asset") == "mark_white_repeating_single" for obj in lane_dividers)
    assert len(crossings) == 384
    assert all(obj.get("asset") == "mark_white_crossing_piece" for obj in crossings)

    print(
        "V2.6 RELEASE AUDIT PASSED: 2 source sheets archived / transparent runtime master canonical / "
        "464 lane dividers and 384 crossing pieces remain distinct"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
