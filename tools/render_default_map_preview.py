from __future__ import annotations

import os
import zipfile
import io
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from PIL import Image, ImageChops, ImageStat

try:
    import pygame
except ModuleNotFoundError:
    pygame = None


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mapfiles.loader import load_map_folder

MAP = ROOT / "mapfiles" / "data" / "map_001_gwb_corridor"
MASTER = ROOT / "dev_tools" / "map_generator" / "profiles" / "gwb_gameplay" / "unified_composition"
OUT = ROOT / "build_previews"


def render(mode: str) -> tuple[Path, float]:
    cfg = load_map_folder(MAP)
    cfg["default_render_mode"] = mode
    path = OUT / f"open_night_v0_8_0_default_map_{mode}.png"
    master_path = MASTER / f"unified_composition_{mode}.png"
    # Release clones intentionally omit the very large generator workspace. In
    # that case the committed approved preview is the stable comparison target;
    # read it before replacing it with the newly rendered runtime preview.
    approved_path = master_path if master_path.exists() else path
    if not approved_path.exists():
        raise FileNotFoundError(
            f"Missing approved comparison image: {master_path} or {path}"
        )
    approved = Image.open(approved_path).convert("RGB").copy()
    if pygame is not None:
        from environment_art import EnvironmentRenderer
        renderer = EnvironmentRenderer(cfg)
        preview = pygame.Surface((4096, 2048)).convert()
        for cy in range(2, 10):
            for cx in range(16):
                chunk = renderer._render_chunk(cx, cy)
                small = pygame.transform.smoothscale(chunk, (256, 256))
                preview.blit(small, (cx * 256, (cy - 2) * 256))
        pygame.image.save(preview, path)
    else:
        # Dependency-free CI fallback validates the same archive/chunk mapping.
        preview = Image.new("RGB", (4096, 2048))
        archive_path = ROOT / str(cfg["baked_composition_archive"])
        with zipfile.ZipFile(archive_path, "r") as archive:
            for tile_y in range(4):
                for tile_x in range(8):
                    name = f"{mode}/tile_{tile_x:02d}_{tile_y:02d}.png"
                    tile = Image.open(io.BytesIO(archive.read(name))).convert("RGB")
                    tile = tile.resize((512, 512), Image.Resampling.LANCZOS)
                    preview.paste(tile, (tile_x * 512, tile_y * 512))
        preview.save(path)

    runtime = Image.open(path).convert("RGB")
    approved = approved.resize(runtime.size, Image.Resampling.LANCZOS)
    diff = ImageChops.difference(runtime, approved)
    stat = ImageStat.Stat(diff)
    mean_error = sum(stat.mean) / 3.0
    return path, mean_error


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if pygame is not None:
        pygame.init()
        pygame.display.set_mode((1, 1))
    results = [render(mode) for mode in ("day", "night")]
    if pygame is not None:
        pygame.quit()
    for path, error in results:
        renderer = "pygame_chunks" if pygame is not None else "archive_contract_fallback"
        print(f"PREVIEW={path} renderer={renderer} mean_rgb_error_vs_approved={error:.4f}")


if __name__ == "__main__":
    main()
