from __future__ import annotations

import csv
import os
import shutil
import time
from copy import deepcopy
from pathlib import Path

from portable_paths import APP_DIR, ensure_shared_layout, shared_art_style_path

LOCAL_TEMPLATE = APP_DIR / "config" / "art_style.csv"

DEFAULTS = {
    "environment": {
        "land": (70, 76, 69), "land_grain": (82, 86, 77),
        "water": (47, 72, 84), "water_line": (63, 92, 103),
        "park": (70, 94, 68), "park_dark": (54, 77, 55),
        "road": (44, 47, 47), "road_grain": (55, 58, 56),
        "lane": (205, 190, 135), "curb": (126, 125, 116),
        "sidewalk": (103, 104, 99), "building_edge": (54, 53, 49),
        "building_shadow": (28, 30, 29), "roof_1": (124, 116, 103),
        "roof_2": (107, 112, 108), "roof_3": (129, 103, 89),
        "roof_4": (94, 104, 96), "roof_detail": (151, 143, 125),
        "crosswalk": (217, 214, 202),
        "tree_dark": (41, 67, 48), "tree_mid": (59, 91, 62),
        "tree_light": (84, 112, 77), "tree_trunk": (85, 67, 49),
        "bridge_edge": (139, 139, 129), "bridge_tower": (111, 115, 111),
    },
    "ui": {
        "text": (239, 238, 231), "muted": (158, 160, 157),
        "panel": (28, 31, 31), "panel_2": (38, 41, 40),
        "accent": (223, 202, 111), "local": (242, 213, 99),
        "remote": (112, 181, 211), "supplier": (109, 190, 127),
        "customer": (205, 110, 105), "panel_edge": (92, 92, 84),
    },
    "sprite": {"outline": (26, 25, 24), "shadow": (0, 0, 0), "outline_px": 1, "shadow_alpha": 105},
    "vehicle": {"shadow": (0, 0, 0), "outline": (24, 24, 22), "outline_px": 1, "shadow_alpha": 100, "pixelated": True},
    "hot_reload": {"enabled": True, "poll_seconds": 0.5},
}


def ensure_style_file() -> Path:
    ensure_shared_layout()
    dst = shared_art_style_path()
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        if LOCAL_TEMPLATE.exists():
            shutil.copy2(LOCAL_TEMPLATE, dst)
    return dst


def _color(raw: str, fallback):
    try:
        parts = [int(float(p.strip())) for p in str(raw).replace(",", ";").split(";") if p.strip()]
        if len(parts) != 3:
            return fallback
        return tuple(max(0, min(255, p)) for p in parts)
    except Exception:
        return fallback


def _typed(raw: str, kind: str, fallback):
    kind = str(kind or "str").strip().lower()
    try:
        if kind == "color":
            return _color(raw, fallback)
        if kind == "bool":
            return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}
        if kind == "int":
            return int(float(raw))
        if kind == "float":
            return float(raw)
        return str(raw)
    except Exception:
        return fallback


def load_art_style(path: Path | None = None) -> dict:
    settings = deepcopy(DEFAULTS)
    if path is None and os.environ.get("PYMMO_ART_REVIEW_LOCAL", "").strip().lower() in {"1", "true", "yes", "on"}:
        path = LOCAL_TEMPLATE
    else:
        path = Path(path) if path else ensure_style_file()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                section = str(row.get("section", "")).strip()
                key = str(row.get("key", "")).strip()
                if not section or not key:
                    continue
                fallback = settings.get(section, {}).get(key, str(row.get("value", "")))
                settings.setdefault(section, {})[key] = _typed(row.get("value", ""), row.get("type", "str"), fallback)
    except OSError:
        pass
    return settings


class StyleWatcher:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else ensure_style_file()
        self.last_mtime_ns = self._mtime()
        self.last_poll = 0.0

    def _mtime(self) -> int:
        try:
            return self.path.stat().st_mtime_ns
        except OSError:
            return 0

    def changed(self, interval: float = 0.5) -> bool:
        now = time.monotonic()
        if now - self.last_poll < max(0.05, float(interval)):
            return False
        self.last_poll = now
        current = self._mtime()
        if current and current != self.last_mtime_ns:
            self.last_mtime_ns = current
            return True
        return False

    def reset(self) -> None:
        self.last_mtime_ns = self._mtime()


def set_art_style_value(section: str, key: str, value, path: Path | None = None) -> None:
    path = Path(path) if path else ensure_style_file()
    rows = []
    fields = ["section", "key", "value", "type", "notes"]
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames:
                fields = list(reader.fieldnames)
            rows = [dict(r) for r in reader]
    except OSError:
        pass
    found = False
    for row in rows:
        if str(row.get("section", "")).strip() == section and str(row.get("key", "")).strip() == key:
            row["value"] = str(value).lower() if isinstance(value, bool) else str(value)
            found = True
            break
    if not found:
        kind = "bool" if isinstance(value, bool) else ("float" if isinstance(value, float) else "str")
        rows.append({"section":section,"key":key,"value":str(value).lower() if isinstance(value,bool) else str(value),"type":kind,"notes":"Updated from in-game settings"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fields})
