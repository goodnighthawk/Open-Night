from __future__ import annotations

"""Capture the canonical v1.0 minimap and M-map with legacy-independence checks."""

import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYMMO_ART_REVIEW_LOCAL", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

import v100_client  # noqa: F401 - canonical import installs the v1.0 patches
import client as game_client
import grid_client_entry
from grid_renderer import GridRenderer
from grid_runtime import load_ground_grid


OUTPUT_DIR = ROOT / "assets" / "grid_v100"
MINIMAP_PATH = OUTPUT_DIR / "GRID_MINIMAP_RUNTIME_PROOF_1280x720.png"
WORLD_MAP_PATH = OUTPUT_DIR / "GRID_WORLD_MAP_RUNTIME_PROOF_1280x720.png"
REPORT_PATH = OUTPUT_DIR / "GRID_UI_LEGACY_INDEPENDENCE.json"


def _legacy_fixture(variant: int, supplier_pos: tuple[float, float], customer_pos: tuple[float, float]) -> dict:
    """Return deliberately incompatible retired geometry with stable gameplay markers."""
    if variant == 0:
        return {
            "id": "retired-sentinel-a",
            "name": "LEGACY SENTINEL A",
            "world_w": 777,
            "world_h": 555,
            "chunk_size": 31,
            "chunk_cols": 26,
            "chunk_rows": 18,
            "supplier_pos": supplier_pos,
            "customer_pos": customer_pos,
            "roads": [{"name": "OLD ROAD A", "width": 500, "points": [[0, 0], [777, 555]]}],
            "water_polygons": [[[0, 0], [777, 0], [777, 555], [0, 555]]],
            "street_props": [{"kind": "edge_tunnel", "pos": [1, 1], "rotation": 13, "scale": 9}],
            "bike_lanes": [{"points": [[0, 555], [777, 0]]}],
            "buildings": [{"rect": [0, 0, 777, 555]}],
            "landmarks": [{"name": "OLD LANDMARK A", "pos": [5, 7]}],
            "districts": [{"name": "OLD DISTRICT A", "pos": [700, 500]}],
        }
    return {
        "id": "retired-sentinel-b",
        "name": "LEGACY SENTINEL B",
        "world_w": 99999,
        "world_h": 12345,
        "chunk_size": 4096,
        "chunk_cols": 25,
        "chunk_rows": 4,
        "supplier_pos": supplier_pos,
        "customer_pos": customer_pos,
        "roads": [{"name": "OLD ROAD B", "width": 1, "points": [[99999, 0], [0, 12345]]}],
        "water_polygons": [[[40000, 100], [99999, 12345], [1, 12000]]],
        "street_props": [{"kind": "edge_tunnel", "pos": [90000, 12000], "rotation": 271, "scale": 1}],
        "bike_lanes": [{"points": [[1, 1], [50000, 6000], [99998, 12344]]}],
        "buildings": [{"rect": [80000, 9000, 100, 100]}],
        "landmarks": [{"name": "OLD LANDMARK B", "pos": [88888, 11111]}],
        "districts": [{"name": "OLD DISTRICT B", "pos": [22222, 3333]}],
    }


def _frame_hash(surface: pygame.Surface) -> str:
    return hashlib.sha256(pygame.image.tobytes(surface, "RGBA")).hexdigest()


def _fixture_hash(fixture: dict) -> str:
    encoded = json.dumps(fixture, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assert_visual_frame(surface: pygame.Surface, label: str) -> None:
    pixels = pygame.image.tobytes(surface, "RGB")
    colors = {pixels[index:index + 3] for index in range(0, len(pixels), 3)}
    if len(colors) < 12:
        raise AssertionError(f"{label} is visually empty: only {len(colors)} colors")


def _make_game(world, renderer, level: int, map_config: dict):
    game = game_client.Game.__new__(game_client.Game)
    game.screen = pygame.display.get_surface()
    game.font = pygame.font.SysFont("consolas", 19)
    game.small_font = pygame.font.SysFont("consolas", 15)
    game.tiny_font = pygame.font.SysFont("consolas", 12)
    game.big_font = pygame.font.SysFont("consolas", 28, bold=True)
    game.grid_world = world
    game.grid_renderer = renderer
    game.art_style = {"ui": {}, "environment": {}}
    game.map_config = map_config
    game.local_id = "local"
    spawn_x, spawn_y = world.choose_spawn("ground", 18.0)
    local = SimpleNamespace(
        render_x=spawn_x,
        render_y=spawn_y,
        level=level,
        in_vehicle=False,
        aim=-0.45,
    )
    game.players = {"local": local}
    game.map_players = {
        "friend": {"name": "Grid Friend", "x": spawn_x + 320, "y": spawn_y - 180, "level": 0},
        "remote": {"name": "Grid Player", "x": spawn_x - 430, "y": spawn_y + 250, "level": 1},
    }
    game.friend_names = {"grid friend": "Grid Friend"}
    game._world_map_cache = None
    game._world_map_cache_key = None
    game._world_map_last_error = ""
    game.map_open = True
    return game


def _render_pair(world, renderer, level: int, fixture: dict, save: bool) -> tuple[str, str]:
    game = _make_game(world, renderer, level, fixture)

    game.screen.fill((9, 11, 14))
    game.draw_local_minimap()
    _assert_visual_frame(game.screen, "circular minimap")
    minimap_hash = _frame_hash(game.screen)
    if save:
        pygame.image.save(game.screen, MINIMAP_PATH)

    game.screen.fill((9, 11, 14))
    game._world_map_cache = None
    game._world_map_cache_key = None
    game.draw_world_map()
    if not game.map_open or game._world_map_last_error:
        raise AssertionError(f"expanded map failed safely instead of rendering: {game._world_map_last_error}")
    _assert_visual_frame(game.screen, "expanded world map")
    world_map_hash = _frame_hash(game.screen)
    if save:
        pygame.image.save(game.screen, WORLD_MAP_PATH)
    return minimap_hash, world_map_hash


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1280, 720))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if game_client.Game.draw_local_minimap is not grid_client_entry._draw_grid_local_minimap:
        raise AssertionError("canonical client did not install the GridWorld minimap")
    if game_client.Game._draw_world_map_impl is not grid_client_entry._draw_grid_world_map_impl:
        raise AssertionError("canonical client did not install the GridWorld M-map")
    if game_client.Game._build_world_map_cache is not grid_client_entry._build_grid_world_map_cache:
        raise AssertionError("canonical client did not install the GridWorld M-map cache")

    world = load_ground_grid()
    if world is None:
        raise AssertionError("committed v1.0 Ground grid did not load")
    renderer = GridRenderer(world)
    spawn_x, spawn_y = world.choose_spawn("ground", 18.0)
    supplier_pos = (spawn_x + 500.0, spawn_y + 80.0)
    customer_pos = (spawn_x - 520.0, spawn_y - 120.0)
    fixtures = [_legacy_fixture(0, supplier_pos, customer_pos), _legacy_fixture(1, supplier_pos, customer_pos)]
    fixture_hashes = [_fixture_hash(fixture) for fixture in fixtures]
    if fixture_hashes[0] == fixture_hashes[1]:
        raise AssertionError("legacy sentinels must be materially different")

    reference = _render_pair(world, renderer, 0, fixtures[0], save=True)
    comparisons: dict[str, dict[str, str]] = {}
    for level in (0, 1, -1):
        for variant, fixture in enumerate(fixtures):
            result = _render_pair(world, renderer, level, fixture, save=False)
            comparisons[f"level_{level}_fixture_{variant}"] = {
                "minimap_sha256": result[0],
                "world_map_sha256": result[1],
            }
            if result != reference:
                raise AssertionError(
                    f"Grid UI changed for retired geometry fixture {variant} at level {level}: {result} != {reference}"
                )

    report = {
        "authority": "GridWorld",
        "resolution": [1280, 720],
        "grid": {"width": world.width, "height": world.height, "cell_px": world.cell_px},
        "minimap_sha256": reference[0],
        "world_map_sha256": reference[1],
        "legacy_fixture_sha256": fixture_hashes,
        "comparisons": comparisons,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "v1.0 grid UI runtime proof OK: "
        f"minimap={reference[0][:12]} world_map={reference[1][:12]} "
        "legacy fixtures and levels 0/1/-1 are pixel-identical"
    )
    pygame.quit()


if __name__ == "__main__":
    main()
