from __future__ import annotations

import csv
from datetime import datetime, timezone
import os
from pathlib import Path
import re
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

FEEDBACK_FIELDS = [
    "report_id",
    "timestamp_utc",
    "source",
    "reporter",
    "category",
    "summary",
    "description",
    "screenshot",
    "status",
    "target_version",
    "duplicate_of",
    "build_version",
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
]

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def feedback_root() -> Path:
    """Return the reviewable feedback folder inside the current game checkout."""
    configured = os.environ.get("OPEN_NIGHT_FEEDBACK_ROOT", "").strip()
    return Path(configured).expanduser() if configured else PROJECT_ROOT / "feedback" / "next_version"


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
) -> tuple[Path, Path, Path | None, Path | None]:
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
    row.setdefault("status", "open")
    row["screenshot"] = f"screenshots/{shot_name}"
    _append_csv(csv_path, REPORT_FIELDS, row)

    # Mirror the report into the game checkout. When this checkout is a GitHub
    # Desktop repository, the CSV and PNG become ordinary reviewable changes
    # that the player can intentionally commit and push for the next build.
    feedback_csv: Path | None = None
    feedback_shot: Path | None = None
    try:
        review_root = feedback_root()
        review_shots = review_root / "screenshots"
        review_shots.mkdir(parents=True, exist_ok=True)
        feedback_shot = review_shots / shot_name
        pygame.image.save(screen, str(feedback_shot))
        description = str(row.get("description") or row.get("note") or "").strip()
        row.setdefault("source", "f10")
        row.setdefault("reporter", "")
        row.setdefault("summary", description.splitlines()[0][:160] if description else safe_category.replace("_", " "))
        row["description"] = description
        row.setdefault("target_version", "next")
        row.setdefault("duplicate_of", "")
        row["screenshot"] = f"screenshots/{shot_name}"
        feedback_csv = review_root / "next_version_feedback.csv"
        _append_csv(feedback_csv, FEEDBACK_FIELDS, row)
    except (OSError, pygame.error):
        # The browser build may expose only a virtual/read-only filesystem. Its
        # shared-data report still succeeds; desktop checkouts receive both.
        feedback_csv = None
        feedback_shot = None

    return csv_path, shot_path, feedback_csv, feedback_shot
