#!/usr/bin/env python3
"""Fast local visual proof renderer for Open Night v1.0 Ground + Roof.

This is intentionally separate from GitHub Actions. It runs the same generator,
GridWorld, and GridRenderer locally and writes a small, fixed proof bundle to
artifacts/map_lab/current/.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from grid_renderer import GridRenderer
from grid_runtime import load_ground_grid, load_roof_grid

OUT_ROOT = ROOT / "artifacts" / "map_lab"
CURRENT = OUT_ROOT / "current"
PREVIOUS = OUT_ROOT / "previous"

FULL_SIZE = (1920, 1080)
DETAIL_SIZE = (1280, 720)
SHEET_SIZE = (1800, 1100)

PROOFS = (
    ("Ground — full map", "GROUND_FULL.png"),
    ("Ground — intersection", "GROUND_INTERSECTION.png"),
    ("Ground — largest building", "GROUND_BUILDING.png"),
    ("Roof — full map", "ROOF_FULL.png"),
    ("Roof — same largest building", "ROOF_BUILDING.png"),
    ("Tile orientation test", "TILE_ORIENTATION_TEST.png"),
    ("Previous/current difference", "GROUND_DIFF.png"),
)


def _rotate_previous() -> None:
    if PREVIOUS.exists():
        shutil.rmtree(PREVIOUS)
    if CURRENT.exists():
        shutil.copytree(CURRENT, PREVIOUS)
    CURRENT.mkdir(parents=True, exist_ok=True)


def _camera_for(world, x: float, y: float, size: tuple[int, int]) -> tuple[float, float]:
    width, height = size
    return (
        max(0.0, min(max(0.0, world.world_w - width), x - width / 2)),
        max(0.0, min(max(0.0, world.world_h - height), y - height / 2)),
    )


def _save_detail(renderer: GridRenderer, world, layer: str, center: tuple[float, float], path: Path) -> None:
    frame = pygame.Surface(DETAIL_SIZE).convert()
    renderer.draw_view(frame, _camera_for(world, center[0], center[1], DETAIL_SIZE), layer)
    pygame.image.save(frame, str(path))


def _save_overview(renderer: GridRenderer, layer: str, path: Path) -> None:
    frame = pygame.Surface(FULL_SIZE).convert()
    renderer.draw_overview(frame, layer)
    pygame.image.save(frame, str(path))


def _largest_building(world) -> tuple[tuple[float, float], tuple[int, int, int, int]]:
    buildings = list((world.data.get("building_synthesis") or {}).get("buildings") or [])
    if buildings:
        def area(row: dict) -> int:
            x0, y0, x1, y1 = map(int, row["rect"])
            return (x1 - x0 + 1) * (y1 - y0 + 1)

        building = max(buildings, key=area)
        x0, y0, x1, y1 = map(int, building["rect"])
        cx = ((x0 + x1 + 1) * world.cell_px) / 2
        cy = ((y0 + y1 + 1) * world.cell_px) / 2
        return (cx, cy), (x0, y0, x1, y1)

    cells = [
        (gx, gy)
        for gy, row in enumerate(world.layers["ground"])
        for gx, tile_id in enumerate(row)
        if tile_id.startswith("bld_")
    ]
    if not cells:
        raise RuntimeError("Map Lab requires at least one building")
    gx, gy = cells[0]
    return world.cell_center(gx, gy), (gx, gy, gx, gy)


def _intersection_center(world) -> tuple[float, float]:
    rows = world.layers["ground"]
    h, w = len(rows), len(rows[0])
    cx, cy = w / 2, h / 2

    def is_road(x: int, y: int) -> bool:
        return 0 <= x < w and 0 <= y < h and world.catalog[rows[y][x]].collision == "road"

    best = None
    for y in range(h):
        for x in range(w):
            if not is_road(x, y):
                continue
            score = sum(
                is_road(nx, ny)
                for nx, ny in ((x - 3, y), (x + 3, y), (x, y - 3), (x, y + 3))
            )
            distance = abs(x - cx) + abs(y - cy)
            candidate = (score, -distance, x, y)
            if best is None or candidate > best:
                best = candidate
    if best is None:
        return world.cell_center(w // 2, h // 2)
    return world.cell_center(best[2], best[3])


def _scaled(surface: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
    return pygame.transform.scale(surface, size)


def _draw_label(target: pygame.Surface, font: pygame.font.Font, text: str, pos: tuple[int, int], color=(238, 238, 238)) -> None:
    target.blit(font.render(text, True, color), pos)


def _orientation_sheet(world, renderer: GridRenderer, path: Path) -> None:
    sheet = pygame.Surface(SHEET_SIZE).convert()
    sheet.fill((24, 26, 30))
    title = pygame.font.SysFont("consolas", 30, bold=True)
    font = pygame.font.SysFont("consolas", 18)
    small = pygame.font.SysFont("consolas", 15)

    _draw_label(sheet, title, "Open Night Map Lab — tile orientation test", (28, 20))
    _draw_label(
        sheet,
        font,
        "Logical IDs are runtime map semantics; filename shown is the actual city_block sprite selected.",
        (28, 62),
        (190, 196, 204),
    )

    curb_ids = (
        "curb_top", "curb_bottom", "curb_left", "curb_right",
        "curb_tl_outer", "curb_tr_outer", "curb_bl_outer", "curb_br_outer",
    )
    tile_box = 148
    start_x, start_y = 28, 105
    for i, tile_id in enumerate(curb_ids):
        col, row = i % 4, i // 4
        x = start_x + col * 265
        y = start_y + row * 215
        image = _scaled(renderer._tile_surface(tile_id), (tile_box, tile_box))
        sheet.blit(image, (x, y))
        _draw_label(sheet, font, tile_id, (x, y + tile_box + 5))
        filename = Path(world.catalog[tile_id].image).name
        _draw_label(sheet, small, filename, (x, y + tile_box + 30), (178, 184, 192))

    _draw_label(sheet, title, "Assembled curb block", (1120, 105))
    logical = [
        ["curb_tl_outer", "curb_top", "curb_tr_outer"],
        ["curb_left", "pavement_small", "curb_right"],
        ["curb_bl_outer", "curb_bottom", "curb_br_outer"],
    ]
    mini = 145
    for gy, row in enumerate(logical):
        for gx, tile_id in enumerate(row):
            image = _scaled(renderer._tile_surface(tile_id), (mini, mini))
            sheet.blit(image, (1120 + gx * mini, 150 + gy * mini))

    _draw_label(sheet, title, "Filename-driven building test", (28, 570))
    roles = [
        ["top_left_outer", "top_center", "top_center", "top_center", "top_right_outer"],
        ["left", "fill", "fill", "fill", "right"],
        ["left", "fill", "fill", "fill", "right"],
        ["bottom_left_outer", "bottom_center", "bottom_center", "bottom_center", "bottom_right_outer"],
    ]
    bpx = 112
    for gy, row in enumerate(roles):
        for gx, role in enumerate(row):
            tile_id = f"bld_blue_{role}"
            if tile_id not in world.catalog.entries:
                continue
            image = _scaled(renderer._tile_surface(tile_id), (bpx, bpx))
            sheet.blit(image, (28 + gx * bpx, 615 + gy * bpx))

    reference = ROOT / "assets" / "source_packs" / "city_block" / "example_small.png"
    if reference.is_file():
        _draw_label(sheet, title, "Pack reference: example_small.png", (680, 570))
        ref = pygame.image.load(str(reference)).convert_alpha()
        max_w, max_h = 1070, 475
        scale = min(max_w / ref.get_width(), max_h / ref.get_height())
        size = (max(1, int(ref.get_width() * scale)), max(1, int(ref.get_height() * scale)))
        ref = pygame.transform.smoothscale(ref, size)
        sheet.blit(ref, (680, 615))

    pygame.image.save(sheet, str(path))


def _make_diff(current_path: Path, previous_path: Path, output_path: Path) -> float | None:
    if not previous_path.is_file():
        blank = pygame.Surface((960, 540)).convert()
        blank.fill((28, 30, 34))
        font = pygame.font.SysFont("consolas", 28)
        blank.blit(font.render("No previous Map Lab render yet.", True, (230, 230, 230)), (40, 40))
        pygame.image.save(blank, str(output_path))
        return None

    current = pygame.image.load(str(current_path)).convert()
    previous = pygame.image.load(str(previous_path)).convert()
    size = (640, 360)
    current = pygame.transform.scale(current, size)
    previous = pygame.transform.scale(previous, size)
    diff = pygame.Surface(size).convert()
    changed = 0
    total = size[0] * size[1]

    for y in range(size[1]):
        for x in range(size[0]):
            a = current.get_at((x, y))
            b = previous.get_at((x, y))
            delta = abs(a.r - b.r) + abs(a.g - b.g) + abs(a.b - b.b)
            if delta > 18:
                changed += 1
                diff.set_at((x, y), (235, 70, 70))
            else:
                grey = int((a.r + a.g + a.b) / 3 * 0.28)
                diff.set_at((x, y), (grey, grey, grey))

    pygame.image.save(diff, str(output_path))
    return 100.0 * changed / total


def _write_index(summary: dict) -> None:
    stamp = int(time.time() * 1000)
    cards = []
    for title, filename in PROOFS:
        path = CURRENT / filename
        if path.is_file():
            cards.append(
                f'<section><h2>{title}</h2><a href="{filename}?v={stamp}" target="_blank">'
                f'<img src="{filename}?v={stamp}" alt="{title}"></a></section>'
            )
    changed = summary.get("changed_percent")
    changed_text = "first render" if changed is None else f'{changed:.2f}% of sampled Ground pixels changed'
    warning = ""
    if changed is not None and changed < 0.5:
        warning = '<p class="warning">Warning: this render changed less than 0.5% of the sampled Ground image.</p>'

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="2">
<title>Open Night Map Lab</title>
<style>
body {{ margin:0; padding:24px; background:#15171b; color:#eee; font-family:Segoe UI,Arial,sans-serif; }}
header {{ position:sticky; top:0; z-index:2; background:#15171be8; padding:8px 0 18px; }}
h1 {{ margin:0 0 8px; }} p {{ color:#bac0c8; margin:4px 0; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(520px,1fr)); gap:18px; }}
section {{ background:#20242a; border:1px solid #363c45; border-radius:10px; padding:12px; }}
h2 {{ font-size:18px; margin:0 0 10px; }}
img {{ width:100%; height:auto; display:block; background:#090a0c; image-rendering:auto; }}
.warning {{ color:#ffbf69; font-weight:600; }}
code {{ color:#d5e7ff; }}
</style>
</head>
<body>
<header>
<h1>Open Night Map Lab</h1>
<p>Hot reload is active while <code>tools/map_lab.py</code> is running. Save a watched map/art/runtime file to regenerate.</p>
<p>{changed_text}</p>
{warning}
</header>
<div class="grid">{''.join(cards)}</div>
</body></html>"""
    (CURRENT / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    from tools.generate_v100_ground_roof_layers import main as generate_layers
    from tools.build_v100_grid_seed import main as validate_map

    generate_layers()
    load_ground_grid.cache_clear()
    load_roof_grid.cache_clear()
    validate_map()
    load_ground_grid.cache_clear()
    load_roof_grid.cache_clear()

    pygame.init()
    pygame.display.set_mode((1, 1))
    started = time.perf_counter()
    try:
        ground = load_ground_grid()
        roof = load_roof_grid()
        ground_renderer = GridRenderer(ground)
        roof_renderer = GridRenderer(roof)

        building_center, building_rect = _largest_building(ground)
        intersection_center = _intersection_center(ground)

        _rotate_previous()

        _save_overview(ground_renderer, "ground", CURRENT / "GROUND_FULL.png")
        _save_detail(ground_renderer, ground, "ground", intersection_center, CURRENT / "GROUND_INTERSECTION.png")
        _save_detail(ground_renderer, ground, "ground", building_center, CURRENT / "GROUND_BUILDING.png")
        _save_overview(roof_renderer, "roof", CURRENT / "ROOF_FULL.png")
        _save_detail(roof_renderer, roof, "roof", building_center, CURRENT / "ROOF_BUILDING.png")
        _orientation_sheet(ground, ground_renderer, CURRENT / "TILE_ORIENTATION_TEST.png")

        changed = _make_diff(
            CURRENT / "GROUND_FULL.png",
            PREVIOUS / "GROUND_FULL.png",
            CURRENT / "GROUND_DIFF.png",
        )
        elapsed = time.perf_counter() - started
        summary = {
            "rendered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_seconds": round(elapsed, 3),
            "changed_percent": changed,
            "largest_building_rect": list(building_rect),
            "intersection_center_world": list(intersection_center),
            "ground_objects": len(ground.objects),
            "roof_objects": len(roof.objects),
            "roof_registration": ground.data.get("roof_registration", ""),
        }
        (CURRENT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        _write_index(summary)
        changed_text = "first render" if changed is None else f"{changed:.2f}% changed"
        print(f"MAP_LAB_RENDER_OK {elapsed:.2f}s {changed_text} output={CURRENT}")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
