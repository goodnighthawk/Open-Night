from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import threading
from typing import Any

from portable_paths import shared_issue_reports_root

# The original reporter shipped with a 22-column CSV. v1.0 added four columns
# without migrating an existing header, which is why old shared folders can now
# contain 22-column and 26-column rows under the same 22-column header.
LEGACY_REPORT_FIELDS = [
    "timestamp_utc", "build_version", "status", "category", "note",
    "map_id", "map_name", "chunk_id", "chunk_x", "chunk_y", "world_x",
    "world_y", "local_x", "local_y", "camera_rotation_deg", "camera_zoom",
    "in_vehicle", "vehicle_id", "nearest_ai_kind", "nearest_ai_id",
    "nearest_ai_distance", "screenshot",
]

BASE_REPORT_FIELDS = [
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

REPORT_FIELDS = BASE_REPORT_FIELDS + [
    "server_report_id",
    "server_status",
    "submitted_at_utc",
    "attempt_count",
    "last_attempt_utc",
    "last_error",
]

_PENDING_STATUSES = {"pending_server_review", "retry_pending"}
_CSV_LOCK = threading.RLock()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_legacy_id(row: dict[str, Any]) -> str:
    seed = "|".join(
        str(row.get(key, ""))
        for key in ("timestamp_utc", "screenshot", "note", "world_x", "world_y")
    )
    digest = hashlib.sha1(seed.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"LEGACY-{digest}"


def _canonical_row(raw: dict[str, Any]) -> dict[str, str]:
    row = {field: _clean(raw.get(field, "")) for field in REPORT_FIELDS}
    if not row["report_id"]:
        row["report_id"] = _stable_legacy_id(row)
    if not row["description"]:
        row["description"] = row["note"]
    if not row["note"]:
        row["note"] = row["description"]
    if not row["source"]:
        row["source"] = "legacy_local"
    if not row["status"]:
        row["status"] = "open"
    try:
        row["attempt_count"] = str(max(0, int(row["attempt_count"] or 0)))
    except (TypeError, ValueError):
        row["attempt_count"] = "0"
    return row


def _decode_mixed_row(header: list[str], values: list[str]) -> dict[str, Any]:
    # Most important recovery case: v1.0 appended a 26-field row even when the
    # existing file still had the original 22-field header.
    if len(values) == len(REPORT_FIELDS):
        return dict(zip(REPORT_FIELDS, values))
    if len(values) == len(BASE_REPORT_FIELDS):
        return dict(zip(BASE_REPORT_FIELDS, values))
    if len(values) == len(LEGACY_REPORT_FIELDS):
        return dict(zip(LEGACY_REPORT_FIELDS, values))
    if header:
        return dict(zip(header, values))
    return {}


def _write_rows_atomic(csv_path: Path, rows: list[dict[str, Any]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _clean(row.get(field, "")) for field in REPORT_FIELDS})
    tmp.replace(csv_path)


def migrate_issue_report_csv(csv_path: Path | None = None) -> list[dict[str, str]]:
    """Normalize every historical local report into the current durable schema.

    This is intentionally idempotent. It repairs the mixed 22/26-column files
    produced by older builds without discarding old rows or screenshots.
    """
    path = csv_path or (shared_issue_reports_root() / "issue_reports.csv")
    with _CSV_LOCK:
        if not path.exists() or path.stat().st_size <= 0:
            return []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                raw_rows = list(csv.reader(handle))
        except OSError:
            return []
        if not raw_rows:
            return []
        header = [str(value) for value in raw_rows[0]]
        rows = [_canonical_row(_decode_mixed_row(header, values)) for values in raw_rows[1:] if values]
        needs_rewrite = header != REPORT_FIELDS or any(len(values) != len(REPORT_FIELDS) for values in raw_rows[1:])
        if needs_rewrite:
            _write_rows_atomic(path, rows)
        return rows


def _append_csv(csv_path: Path, row: dict[str, Any]) -> None:
    with _CSV_LOCK:
        migrate_issue_report_csv(csv_path)
        exists = csv_path.exists() and csv_path.stat().st_size > 0
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        encoding = "utf-8" if exists else "utf-8-sig"
        with csv_path.open("a", encoding=encoding, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS, extrasaction="ignore")
            if not exists:
                writer.writeheader()
            writer.writerow({field: _clean(row.get(field, "")) for field in REPORT_FIELDS})


def get_issue_report(report_id: str, csv_path: Path | None = None) -> dict[str, str] | None:
    clean_id = str(report_id).strip()
    if not clean_id:
        return None
    for row in migrate_issue_report_csv(csv_path):
        if row.get("report_id") == clean_id:
            return row
    return None


def pending_issue_reports(limit: int = 20, csv_path: Path | None = None) -> list[dict[str, str]]:
    rows = [row for row in migrate_issue_report_csv(csv_path) if row.get("status") in _PENDING_STATUSES]
    rows.sort(key=lambda row: (row.get("timestamp_utc", ""), row.get("report_id", "")))
    return rows[: max(0, int(limit))]


def update_issue_report(report_id: str, csv_path: Path | None = None, **changes: Any) -> bool:
    path = csv_path or (shared_issue_reports_root() / "issue_reports.csv")
    clean_id = str(report_id).strip()
    if not clean_id:
        return False
    with _CSV_LOCK:
        rows = migrate_issue_report_csv(path)
        changed = False
        for row in rows:
            if row.get("report_id") != clean_id:
                continue
            for key, value in changes.items():
                if key in REPORT_FIELDS:
                    row[key] = _clean(value)
            changed = True
            break
        if changed:
            _write_rows_atomic(path, rows)
        return changed


def mark_issue_report_attempt(report_id: str, error: str = "", csv_path: Path | None = None) -> bool:
    row = get_issue_report(report_id, csv_path)
    if row is None:
        return False
    try:
        attempts = int(row.get("attempt_count", "0") or 0) + 1
    except ValueError:
        attempts = 1
    return update_issue_report(
        report_id,
        csv_path,
        status="retry_pending" if row.get("status") in _PENDING_STATUSES else row.get("status", "pending_server_review"),
        attempt_count=attempts,
        last_attempt_utc=_utc_now(),
        last_error=error,
    )


def mark_issue_report_error(report_id: str, error: str, *, retryable: bool = True, csv_path: Path | None = None) -> bool:
    row = get_issue_report(report_id, csv_path)
    if row is None:
        return False
    status = "retry_pending" if retryable else "needs_attention"
    return update_issue_report(report_id, csv_path, status=status, last_error=str(error)[:500])


def mark_issue_report_submitted(
    report_id: str,
    server_report_id: int | str,
    server_status: str = "pending",
    csv_path: Path | None = None,
) -> bool:
    return update_issue_report(
        report_id,
        csv_path,
        status="submitted",
        server_report_id=str(server_report_id),
        server_status=str(server_status),
        submitted_at_utc=_utc_now(),
        last_error="",
    )


def save_issue_report(screen: Any, payload: dict[str, Any]) -> tuple[Path, Path]:
    """Append a persistent CSV issue marker and capture the current game frame.

    Reports live under ``PythonMMO_SharedData/issue_reports`` so they survive
    replacing the game folder with later versions. The payload is updated with
    its generated ``report_id`` so the network delivery layer can correlate the
    local safety copy with the server acknowledgement.
    """
    import pygame

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
    payload["report_id"] = report_id
    row = dict(payload)
    row["timestamp_utc"] = now.isoformat().replace("+00:00", "Z")
    row.setdefault("status", "pending_server_review")
    row.setdefault("attempt_count", 0)
    row["screenshot"] = f"screenshots/{shot_name}"
    _append_csv(csv_path, _canonical_row(row))
    return csv_path, shot_path
