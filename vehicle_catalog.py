from __future__ import annotations

import csv
import random
from functools import lru_cache
from pathlib import Path

from portable_paths import APP_DIR, shared_assets_root

LOCAL_CSV = APP_DIR / "assets" / "cars" / "vehicle_manifest.csv"


def _bool(v) -> bool:
    return str(v).strip().lower() in {"1","true","yes","y","on"}


def _convert(row: dict) -> dict:
    out = dict(row)
    for key in ("index","render_length","render_width"):
        if key in out:
            try: out[key]=int(float(out[key]))
            except Exception: pass
    for key in ("collision_length","collision_width","speed_factor","spawn_weight"):
        if key in out:
            try: out[key]=float(out[key])
            except Exception: pass
    if "traffic_eligible" in out:
        out["traffic_eligible"]=_bool(out["traffic_eligible"])
    return out


def _csv_catalog(path: Path) -> tuple[dict,...]:
    try:
        with path.open("r",encoding="utf-8-sig",newline="") as f:
            return tuple(_convert(dict(r)) for r in csv.DictReader(f))
    except OSError:
        return tuple()


@lru_cache(maxsize=1)
def load_vehicle_catalog() -> tuple[dict, ...]:
    # Release-local art is authoritative. This prevents an older shared manifest
    # from silently replacing the v1.2 81-sprite approved fleet.
    rows = _csv_catalog(LOCAL_CSV)
    if rows:
        return rows
    shared_csv = shared_assets_root() / "cars" / "vehicle_manifest.csv"
    rows = _csv_catalog(shared_csv)
    if rows:
        return rows
    return tuple()


def vehicle_asset_path(filename: str) -> Path:
    local = APP_DIR / "assets" / "cars" / str(filename)
    if local.exists():
        return local
    shared = shared_assets_root() / "cars" / str(filename)
    if shared.exists():
        return shared
    return local


def reload_vehicle_catalog() -> None:
    load_vehicle_catalog.cache_clear()


def vehicle_count() -> int:
    return len(load_vehicle_catalog())


def vehicle_meta(index: int) -> dict:
    catalog = load_vehicle_catalog()
    if not catalog:
        return {
            "index": 0, "category": "sedan", "render_length": 48, "render_width": 22,
            "collision_length": 42, "collision_width": 18, "speed_factor": 1.0,
            "spawn_weight": 1.0, "traffic_eligible": True,
        }
    return catalog[int(index) % len(catalog)]


def choose_traffic_vehicle(rng: random.Random) -> dict:
    catalog = [row for row in load_vehicle_catalog() if row.get("traffic_eligible")]
    if not catalog:
        return vehicle_meta(0)
    weights = [max(0.0, float(row.get("spawn_weight", 1.0))) for row in catalog]
    return rng.choices(catalog, weights=weights, k=1)[0]
