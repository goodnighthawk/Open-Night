#!/usr/bin/env python3
"""Build a portable, GWB-focused Map Workbench review bundle."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "build" / "gwb_map_previewer"

CORE_FILES = (
    "MAP_WORKBENCH.bat",
    "MAP_WORKBENCH.md",
    "map_workbench.py",
    "grid_runtime.py",
    "grid_renderer.py",
    "grid_world.py",
    "building_morphology.py",
    "road_morphology.py",
    "procedural_block_props.py",
)

CORE_TREES = (
    "dev_tools/map_generator/working_cosmetics/approved_v4_layout",
    "mapfiles/data/map_001_gwb_corridor/grid_v100",
    "assets/source_packs/city_block",
    "assets/source_packs/free_assets/Grass/Grass_04",
    "assets/source_packs/gen_vehicles",
    "assets/source_packs/block_props",
    "assets/street_props",
    "cosmetic_packs/nyc_gta2_callback",
)


def copy_file(relative: str, output: Path) -> None:
    source = ROOT / relative
    if not source.is_file():
        raise FileNotFoundError(source)
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def catalog_images(catalog_path: Path) -> set[str]:
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    images: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            image = value.get("image")
            if isinstance(image, str) and image and not image.startswith("city_block://"):
                images.add(image)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return images


def build(output: Path, *, include_previews: bool = True) -> dict[str, object]:
    output = output.resolve()
    if output == ROOT or ROOT in output.parents and output.relative_to(ROOT).parts[:1] not in {("build",), ("dist",)}:
        raise ValueError("Repository-local bundles must be written under build/ or dist/.")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for relative in CORE_FILES:
        copy_file(relative, output)
    for relative in CORE_TREES:
        source = ROOT / relative
        if not source.is_dir():
            raise FileNotFoundError(source)
        shutil.copytree(source, output / relative)

    catalog_dir = ROOT / "assets" / "grid_v100"
    catalogs = sorted(catalog_dir.glob("*.json"))
    image_paths: set[str] = set()
    for catalog in catalogs:
        relative = catalog.relative_to(ROOT).as_posix()
        copy_file(relative, output)
        image_paths.update(catalog_images(catalog))
    for relative in sorted(image_paths):
        source = ROOT / relative
        if source.is_file():
            copy_file(relative, output)

    previews = (
        "artifacts/map_workbench/gwb_full_updated_map.png",
        "artifacts/map_workbench/gwb_full_updated_roof.png",
        "artifacts/map_workbench/gwb_approved_transition_area.png",
        "artifacts/map_workbench/gwb_approved_transition_roof.png",
    )
    if include_previews:
        for relative in previews:
            if (ROOT / relative).is_file():
                copy_file(relative, output)

    notice = (
        "OPEN NIGHT — GWB NEXT-MAP PREVIEW\n\n"
        "Double-click MAP_WORKBENCH.bat. Press G for Ground, R for Roof, and F "
        "to fit the complete GWB/Hudson map. This is an art/map preview and does "
        "not change the game v4.0 release marker.\n"
    )
    (output / "START_HERE.txt").write_text(notice, encoding="utf-8")

    files = [path for path in output.rglob("*") if path.is_file()]
    manifest = {
        "format": "open-night-gwb-map-previewer-v1",
        "entrypoint": "MAP_WORKBENCH.bat",
        "map": "existing Fort Lee / Hudson / Manhattan GWB workbench layout",
        "release_marker_changed": False,
        "file_count": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "catalog_count": len(catalogs),
        "catalog_image_count": len(image_paths),
    }
    (output / "PREVIEW_BUNDLE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--without-previews", action="store_true")
    args = parser.parse_args()
    manifest = build(args.output, include_previews=not args.without_previews)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
