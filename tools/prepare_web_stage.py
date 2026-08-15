from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TOP_LEVEL_FILES = [
    "main.py",
    "client.py",
    "common.py",
    "art_style.py",
    "character_art.py",
    "character_catalog.py",
    "vehicle_art.py",
    "vehicle_catalog.py",
    "environment_art.py",
    "interior_art.py",
    "bicycle_art.py",
    "portable_paths.py",
    "server_directory.py",
    "versioning.py",
    "VERSION.txt",
    "pygbag.toml",
]
DIRECTORIES = ["assets", "config", "gameplay", "mapfiles"]


def _ignore(_directory: str, names: list[str]) -> set[str]:
    ignored = {name for name in names if name == "__pycache__" or name.endswith((".pyc", ".pyo"))}
    return ignored


def prepare(destination: Path) -> None:
    destination = destination.resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise SystemExit("Web staging directory must be outside the game folder.")
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    for name in TOP_LEVEL_FILES:
        source = ROOT / name
        if source.exists():
            shutil.copy2(source, destination / name)
    for name in DIRECTORIES:
        source = ROOT / name
        if source.exists():
            shutil.copytree(source, destination / name, ignore=_ignore)
    print(f"Prepared clean pygbag source: {destination}")
    print("Excluded: .venv, build caches, server/database code, reports, docs, and stale web viewer.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a clean Pygbag staging tree without the desktop .venv.")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    prepare(args.destination)


if __name__ == "__main__":
    main()
