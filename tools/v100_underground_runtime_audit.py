#!/usr/bin/env python3
"""Headless audit for v1.0 Ground/Underground runtime composition switching.

Run after ``wire_v100_underground_runtime.py``. The test intentionally exercises
EnvironmentRenderer with the production Map 001 configuration and the committed
Ground/Underground composition ZIPs. It also checks that the client isolates
negative-level dynamic entities instead of merely swapping background art.
"""
from __future__ import annotations

import csv
import hashlib
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

from environment_art import EnvironmentRenderer
from mapfiles.loader import load_map_folder

MAP_DIR = ROOT / "mapfiles/data/map_001_gwb_corridor"
MAP_CSV = MAP_DIR / "map.csv"
GROUND_ARCHIVE = ROOT / "assets/environment/approved/map_001_gwb_corridor/composition_tiles_v100_ground.zip"
UNDERGROUND_ARCHIVE = ROOT / "assets/environment/approved/map_001_gwb_corridor/composition_tiles_v100_underground.zip"


def fail(message: str) -> None:
    raise SystemExit(message)


def digest_surface(surface: pygame.Surface) -> str:
    payload = pygame.image.tostring(surface, "RGB")
    return hashlib.sha256(payload).hexdigest()


def read_cfg() -> dict[str, str]:
    with MAP_CSV.open(encoding="utf-8-sig", newline="") as f:
        return {row["key"]: row["value"] for row in csv.DictReader(f)}


def source_contract_checks() -> None:
    env_text = (ROOT / "environment_art.py").read_text(encoding="utf-8")
    client_text = (ROOT / "client.py").read_text(encoding="utf-8")

    env_required = (
        "def _uses_underground_composition",
        "def set_active_level",
        "underground_composition_archive",
        "_composition_source_settings",
        "key = (int(self.active_level), mode, int(tile_x), int(tile_y))",
        "int(self.active_level))\n        cached = self.chunk_cache.get(key)",
    )
    for marker in env_required:
        if marker not in env_text:
            fail(f"Environment runtime marker missing: {marker}")

    client_required = (
        "self.environment.set_active_level(active_world_level)",
        "if active_world_level < 0:\n            return",
        "if int(getattr(player, \"level\", 0)) == 0",
        "if int(getattr(player, \"level\", 0)) == active_world_level",
        "if active_world_level >= 0:\n                        positive_levels = sorted",
        "if active_world_level < 0 and player_level != active_world_level",
        "if active_world_level >= 0 and player_level < 0",
    )
    for marker in client_required:
        if marker not in client_text:
            fail(f"Client level-isolation marker missing: {marker}")

    # Ground-only traffic/state must be skipped before those draw calls execute.
    draw_world_anchor = client_text.find("def draw_world(self)")
    if draw_world_anchor < 0:
        fail("client draw_world() missing")
    draw_world_end = client_text.find("\n    def ", draw_world_anchor + 10)
    block = client_text[draw_world_anchor:draw_world_end if draw_world_end > 0 else None]
    early_return = block.find("if active_world_level < 0")
    hydrants = block.find("self.draw_hydrant_effects()")
    traffic = block.find("for signal in self.map_config.get(\"traffic_signals\", [])")
    if min(early_return, hydrants, traffic) < 0 or not (early_return < hydrants < traffic):
        fail("Underground draw_world isolation is not ordered before Ground dynamic features")


def renderer_smoke_checks() -> None:
    cfg = read_cfg()
    if cfg.get("underground_runtime_wired", "").strip().lower() != "true":
        fail("Map 001 does not declare underground_runtime_wired=true")
    if int(float(cfg.get("underground_level_id", "0"))) != -1:
        fail("Map 001 Underground level is not -1")
    if not GROUND_ARCHIVE.is_file():
        fail(f"Ground runtime archive missing: {GROUND_ARCHIVE}")
    if not UNDERGROUND_ARCHIVE.is_file():
        fail(f"Underground runtime archive missing: {UNDERGROUND_ARCHIVE}")

    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        m = load_map_folder(MAP_DIR)
        renderer = EnvironmentRenderer(m)

        renderer.set_active_level(0)
        ground_path = renderer._composition_archive_path()
        if ground_path is None or ground_path.resolve() != GROUND_ARCHIVE.resolve():
            fail(f"Level 0 selected wrong archive: {ground_path}")
        ground = renderer._render_chunk(11, 4).copy()
        ground_hash = digest_surface(ground)

        renderer.set_active_level(-1)
        underground_path = renderer._composition_archive_path()
        if underground_path is None or underground_path.resolve() != UNDERGROUND_ARCHIVE.resolve():
            fail(f"Level -1 selected wrong archive: {underground_path}")
        underground = renderer._render_chunk(11, 4).copy()
        underground_hash = digest_surface(underground)
        if underground_hash == ground_hash:
            fail("Level 0 and -1 rendered identical production chunk pixels")

        # Positive levels retain the Ground composition; elevated decks remain a
        # separate existing occlusion pass rather than a third baked world ZIP.
        renderer.set_active_level(1)
        positive_path = renderer._composition_archive_path()
        if positive_path is None or positive_path.resolve() != GROUND_ARCHIVE.resolve():
            fail(f"Positive level selected wrong base archive: {positive_path}")
        positive = renderer._render_chunk(11, 4).copy()
        positive_hash = digest_surface(positive)
        if positive_hash != ground_hash:
            fail("Positive-level base composition diverged from Ground")

        # Switching back must not leave the previous ZIP or chunk cached under
        # reused coordinates.
        renderer.set_active_level(-1)
        underground_again_hash = digest_surface(renderer._render_chunk(11, 4))
        if underground_again_hash != underground_hash:
            fail("Underground composition is not deterministic after level switching")
        if renderer._composition_zip_path and Path(renderer._composition_zip_path).resolve() != UNDERGROUND_ARCHIVE.resolve():
            fail("Composition ZIP state did not follow active Underground level")
    finally:
        pygame.quit()

    print(
        "V100_UNDERGROUND_RUNTIME_OK "
        f"ground={ground_hash[:12]} underground={underground_hash[:12]} "
        "positive_base=ground negative_isolation=source_checked"
    )


def main() -> None:
    source_contract_checks()
    renderer_smoke_checks()


if __name__ == "__main__":
    main()
