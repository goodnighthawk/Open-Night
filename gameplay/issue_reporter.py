from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

import pygame

from portable_paths import shared_issue_reports_root

REPORT_FIELDS = [
    "report_id",
    "timestamp_utc",
    "build_version",
    "status",
    "source",
    "reporter",
    "category",
    "description",
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


def _append_csv(csv_path: Path, fields: list[str], row: dict[str, Any]) -> None:
    exists = csv_path.exists() and csv_path.stat().st_size > 0
    with csv_path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({field: _clean(row.get(field, "")) for field in fields})


def save_issue_report(
    screen: pygame.Surface,
    payload: dict[str, Any],
) -> tuple[Path, Path]:
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
    safe_chunk = re.sub(r"[^A-Za-z0-9_-]+", "-", chunk_id).strip("-") or "UNK"
    safe_category = re.sub(r"[^a-z0-9_-]+", "-", category).strip("-") or "other"
    report_id = f"ON-{stamp}"
    shot_name = f"{stamp}_{safe_chunk}_{safe_category}.png"
    shot_path = shots / shot_name
    pygame.image.save(screen, str(shot_path))

    csv_path = root / "issue_reports.csv"
    row = dict(payload)
    row["report_id"] = report_id
    row["timestamp_utc"] = now.isoformat().replace("+00:00", "Z")
    # This file is a private/local safety copy. It is deliberately not mirrored
    # into a Git-tracked feedback directory: internet reports must be reviewed
    # by a human before an agent can see or act on them.
    row.setdefault("status", "pending_server_review")
    row["screenshot"] = f"screenshots/{shot_name}"
    _append_csv(csv_path, REPORT_FIELDS, row)
    return csv_path, shot_path
