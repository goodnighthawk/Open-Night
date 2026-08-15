from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
import sys
import time

# Art review must show the version-local files being edited, not stale shared assets.
os.environ.setdefault("PYMMO_ART_REVIEW_LOCAL", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

from environment_art import EnvironmentRenderer, _approved_env_tile, _approved_prop
from mapfiles.loader import load_map_folder
from mapfiles.grid import chunk_label

MAP_DIR = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"
VIEWS_CSV = ROOT / "config" / "art_review_views.csv"
TARGET_DIR = ROOT / "assets" / "art_review_targets"
OUTPUT_DIR = ROOT / "art_review"


def _views() -> list[dict]:
    with VIEWS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in ("center_x", "center_y", "width", "height"):
            row[key] = int(float(row[key]))
    return rows


def _fit_target(path: Path, size: tuple[int, int]) -> pygame.Surface | None:
    if not path.exists():
        return None
    try:
        img = pygame.image.load(str(path)).convert()
    except pygame.error:
        return None
    if img.get_size() != size:
        img = pygame.transform.smoothscale(img, size)
    return img


def _label(surface: pygame.Surface, text: str, pos: tuple[int, int]) -> None:
    font = pygame.font.Font(None, 28)
    fg = font.render(text, True, (245, 244, 237))
    bg = pygame.Surface((fg.get_width() + 16, fg.get_height() + 10), pygame.SRCALPHA)
    bg.fill((18, 20, 20, 205))
    surface.blit(bg, pos)
    surface.blit(fg, (pos[0] + 8, pos[1] + 5))


def _absolute_difference(a: pygame.Surface, b: pygame.Surface) -> pygame.Surface:
    # RGB absolute difference without numpy: max(a-b,0)+max(b-a,0).
    d1 = a.copy()
    d1.blit(b, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
    d2 = b.copy()
    d2.blit(a, (0, 0), special_flags=pygame.BLEND_RGB_SUB)
    d1.blit(d2, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    return d1


def _comparison(current: pygame.Surface, target: pygame.Surface, view_id: str) -> tuple[pygame.Surface, pygame.Surface]:
    w, h = current.get_size()
    panel = pygame.Surface((w * 2, h)).convert()
    panel.blit(target, (0, 0))
    panel.blit(current, (w, 0))
    _label(panel, "APPROVED TARGET", (12, 12))
    _label(panel, f"v1.5.1 CURRENT — {view_id}", (w + 12, 12))
    return panel, _absolute_difference(current, target)


def render_all(selected: set[str] | None = None) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = load_map_folder(MAP_DIR)
    renderer = EnvironmentRenderer(cfg)
    for row in _views():
        view_id = row["view_id"]
        if selected and view_id not in selected:
            continue
        size = (row["width"], row["height"])
        surface = pygame.Surface(size).convert()
        cam_x = row["center_x"] - size[0] / 2
        cam_y = row["center_y"] - size[1] / 2
        renderer.draw_view(surface, (cam_x, cam_y))
        chunk_size = max(1, int(cfg.get("chunk_size", 1024)))
        cx = int(max(0, row["center_x"]) // chunk_size)
        cy = int(max(0, row["center_y"]) // chunk_size)
        grid_id = chunk_label(cx, cy)
        current_path = OUTPUT_DIR / f"{grid_id}_{view_id}_current.png"
        pygame.image.save(surface, str(current_path))
        # Stable alias retained for tools/scripts that predate A1 labels.
        pygame.image.save(surface, str(OUTPUT_DIR / f"{view_id}_current.png"))
        target_name = str(row.get("target", "")).strip()
        if target_name:
            target = _fit_target(TARGET_DIR / target_name, size)
            if target is not None:
                compare, diff = _comparison(surface, target, view_id)
                pygame.image.save(compare, str(OUTPUT_DIR / f"{grid_id}_{view_id}_comparison.png"))
                pygame.image.save(diff, str(OUTPUT_DIR / f"{grid_id}_{view_id}_difference.png"))
                pygame.image.save(compare, str(OUTPUT_DIR / f"{view_id}_comparison.png"))
                pygame.image.save(diff, str(OUTPUT_DIR / f"{view_id}_difference.png"))
        print(f"rendered {view_id} [{grid_id}]: {current_path.relative_to(ROOT)}")


def _watch_paths() -> list[Path]:
    paths = [
        ROOT / "environment_art.py",
        ROOT / "art_style.py",
        ROOT / "config" / "art_style.csv",
        ROOT / "config" / "art_review_views.csv",
        MAP_DIR / "roads.csv",
        MAP_DIR / "road_points.csv",
        MAP_DIR / "buildings.csv",
        MAP_DIR / "building_visuals.csv",
        MAP_DIR / "street_props.csv",
        MAP_DIR / "crosswalks.csv",
    ]
    paths += list((ROOT / "assets" / "environment" / "approved").glob("*.png"))
    paths += list((ROOT / "assets" / "street_props").glob("*.png"))
    return paths


def _stamp() -> tuple:
    out = []
    for path in _watch_paths():
        try:
            out.append((str(path), path.stat().st_mtime_ns, path.stat().st_size))
        except OSError:
            out.append((str(path), 0, 0))
    return tuple(out)


def clear_runtime_caches() -> None:
    _approved_env_tile.cache_clear()
    _approved_prop.cache_clear()


def main() -> int:
    parser = argparse.ArgumentParser(description="Serverless fixed-camera approved-art review renderer")
    parser.add_argument("--watch", action="store_true", help="re-render when art/map files change")
    parser.add_argument("--view", action="append", help="render only one view_id; repeat as needed")
    args = parser.parse_args()

    pygame.init()
    pygame.display.set_mode((1, 1))
    selected = set(args.view or []) or None
    render_all(selected)
    if not args.watch:
        pygame.quit()
        return 0

    print("Watching art/map files. Ctrl+C to stop.")
    previous = _stamp()
    try:
        while True:
            time.sleep(0.7)
            current = _stamp()
            if current != previous:
                previous = current
                clear_runtime_caches()
                try:
                    render_all(selected)
                except Exception as exc:
                    print(f"review render failed: {exc}")
    except KeyboardInterrupt:
        pass
    finally:
        pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
