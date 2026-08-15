from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pygame

from portable_paths import shared_issue_reports_root

REPORT_FIELDS = [
    "timestamp_utc",
    "build_version",
    "status",
    "category",
    "note",
    "map_id",
    "map_name",
    "chunk_id",
    "chunk_x",
    "chunk_y",
    "world_x",
    "world_y",
    "local_x",
    "local_y",
    "camera_rotation_deg",
    "camera_zoom",
    "in_vehicle",
    "vehicle_id",
    "nearest_ai_kind",
    "nearest_ai_id",
    "nearest_ai_distance",
    "screenshot",
]


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def save_issue_report(screen: pygame.Surface, payload: dict[str, Any]) -> tuple[Path, Path]:
    """Append a persistent CSV issue marker and capture the current game frame.

    Reports live under ``PythonMMO_SharedData/issue_reports`` so they survive
    replacing the game folder with later versions.
    """
    root = shared_issue_reports_root()
    shots = root / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S_%fZ")
    chunk_id = str(payload.get("chunk_id", "UNK"))
    category = str(payload.get("category", "other")).lower()
    shot_name = f"{stamp}_{chunk_id}_{category}.png"
    shot_path = shots / shot_name
    pygame.image.save(screen, str(shot_path))

    csv_path = root / "issue_reports.csv"
    row = dict(payload)
    row["timestamp_utc"] = now.isoformat().replace("+00:00", "Z")
    row.setdefault("status", "open")
    row["screenshot"] = f"screenshots/{shot_name}"

    exists = csv_path.exists() and csv_path.stat().st_size > 0
    with csv_path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({field: _clean(row.get(field, "")) for field in REPORT_FIELDS})

    return csv_path, shot_path
