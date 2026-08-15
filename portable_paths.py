from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DEFAULT_SHARED_ROOT = Path.home() / "Documents" / "PythonMMO_SharedData"

def shared_root() -> Path:
    raw = os.getenv("PYMMO_SHARED_DATA", "").strip()
    return Path(raw).expanduser().resolve() if raw else DEFAULT_SHARED_ROOT

def ensure_shared_layout() -> dict[str, Path]:
    root = shared_root()
    paths = {
        "root": root,
        "assets": root / "assets",
        "config": root / "config",
        "stress_results": root / "stress_results",
        "saves": root / "saves",
        "backups": root / "backups",
        "logs": root / "logs",
        "style": root / "style",
        "issue_reports": root / "issue_reports",
        "mysql": root / "mysql",
        "gis": root / "gis",
        "maps": root / "maps",
    }
    for path in paths.values(): path.mkdir(parents=True, exist_ok=True)
    return paths

def shared_assets_root() -> Path: return ensure_shared_layout()["assets"]
def shared_style_root() -> Path: return ensure_shared_layout()["style"]
def shared_art_style_path() -> Path: return shared_style_root() / "art_style.csv"
def shared_issue_reports_root() -> Path: return ensure_shared_layout()["issue_reports"]
def describe() -> str: return str(shared_root())
