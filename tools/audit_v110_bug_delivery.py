#!/usr/bin/env python3
from __future__ import annotations

import csv
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gameplay import issue_reporter
import v110_bug_delivery_client
import v110_bug_delivery_server


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def exercise_real_mixed_schema_fixture() -> dict:
    fixture = os.getenv("OPEN_NIGHT_BUG_FIXTURE", "").strip()
    if not fixture:
        return {"fixture": "not supplied"}
    source = Path(fixture)
    require(source.is_file(), f"fixture missing: {source}")
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "issue_reports.csv"
        shutil.copy2(source, target)
        before = list(csv.reader(target.open("r", encoding="utf-8-sig", newline="")))
        rows = issue_reporter.migrate_issue_report_csv(target)
        after = list(csv.reader(target.open("r", encoding="utf-8-sig", newline="")))
        require(len(after) == len(before), "mixed-schema migration changed row count")
        require(after[0] == issue_reporter.REPORT_FIELDS, "mixed-schema migration did not install canonical header")
        require(all(len(row) == len(issue_reporter.REPORT_FIELDS) for row in after[1:]), "mixed-schema rows remain malformed")
        pending = [row for row in rows if row.get("status") in {"pending_server_review", "retry_pending"}]
        require(any(str(row.get("report_id", "")).startswith("ON-") for row in pending), "newer pending reports lost report IDs")
        return {"rows": len(rows), "pending": len(pending), "columns": len(issue_reporter.REPORT_FIELDS)}


def exercise_synthetic_mixed_schema() -> dict:
    legacy = list(issue_reporter.LEGACY_REPORT_FIELDS)
    old_row = [""] * len(legacy)
    old_row[0] = "2026-08-13T15:03:47Z"
    old_row[2] = "open"
    old_row[4] = "legacy bug"
    old_row[-1] = "screenshots/legacy.png"

    base = list(issue_reporter.BASE_REPORT_FIELDS)
    new_row = [""] * len(base)
    values = {
        "report_id": "ON-20260820T004555_000000Z",
        "timestamp_utc": "2026-08-20T00:45:55Z",
        "build_version": "Open Night v1.1",
        "status": "pending_server_review",
        "source": "chat_/bug",
        "reporter": "Player402",
        "category": "bug",
        "description": "pedestrians are stuck",
        "note": "pedestrians are stuck",
        "screenshot": "screenshots/current.png",
    }
    for key, value in values.items():
        new_row[base.index(key)] = value

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "issue_reports.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(legacy)
            writer.writerow(old_row)
            writer.writerow(new_row)
        rows = issue_reporter.migrate_issue_report_csv(path)
        require(len(rows) == 2, "synthetic migration lost rows")
        require(rows[0]["report_id"].startswith("LEGACY-"), "legacy report did not receive stable ID")
        require(rows[1]["report_id"] == values["report_id"], "26-column row was misaligned")
        require(issue_reporter.pending_issue_reports(10, path)[0]["report_id"] == values["report_id"], "pending outbox not recovered")
        issue_reporter.mark_issue_report_attempt(values["report_id"], csv_path=path)
        attempt = issue_reporter.get_issue_report(values["report_id"], path)
        require(attempt and attempt["attempt_count"] == "1", "attempt count was not persisted")
        issue_reporter.mark_issue_report_submitted(values["report_id"], 77, "pending", path)
        done = issue_reporter.get_issue_report(values["report_id"], path)
        require(done and done["status"] == "submitted", "receipt did not close local outbox row")
        require(done["server_report_id"] == "77", "server receipt ID was not persisted")
        require(not issue_reporter.pending_issue_reports(10, path), "submitted row still appears in outbox")
        return {"synthetic_rows": len(rows), "submitted_server_id": 77}


def exercise_server_idempotency() -> dict:
    calls = []

    class FakeDB:
        pass

    def original(_db, **kwargs):
        calls.append(kwargs)
        return 123

    saved_lookup = v110_bug_delivery_server._lookup_existing_client_report
    try:
        v110_bug_delivery_server._lookup_existing_client_report = lambda db, client_id: 42
        kwargs = {"context": {"client_report_id": "ON-20260820T004555_000000Z"}, "description": "x"}
        result = v110_bug_delivery_server._create_idempotent(FakeDB(), original, **kwargs)
        require(result == 42, "retry did not return existing server report")
        require(not calls, "retry called original create and would duplicate report")
        v110_bug_delivery_server._lookup_existing_client_report = lambda db, client_id: None
        result = v110_bug_delivery_server._create_idempotent(FakeDB(), original, **kwargs)
        require(result == 123 and len(calls) == 1, "new report did not reach original create")
    finally:
        v110_bug_delivery_server._lookup_existing_client_report = saved_lookup
    return {"dedupe_existing_id": 42, "new_create_id": 123}


def exercise_client_acknowledgement() -> dict:
    class FakeNetwork:
        def __init__(self):
            self.sent = []
        def send(self, payload):
            self.sent.append(payload)

    class FakeGame:
        def __init__(self):
            self.connected = True
            self.network = FakeNetwork()
            self._bug_delivery_inflight = None
            self._bug_delivery_inflight_sent_at = 0.0
            self._bug_delivery_retry_at = 0.0
            self.notice = ""
            self.notice_until = 0.0
        def _build_version(self):
            return "Open Night v1.1 - bug review / GridWorld population"

    with tempfile.TemporaryDirectory() as tmp:
        old_root = os.environ.get("PYMMO_SHARED_DATA")
        os.environ["PYMMO_SHARED_DATA"] = tmp
        try:
            path = Path(tmp) / "issue_reports" / "issue_reports.csv"
            row = {field: "" for field in issue_reporter.REPORT_FIELDS}
            row.update({
                "report_id": "ON-20260820T004901_000000Z",
                "timestamp_utc": "2026-08-20T00:49:01Z",
                "build_version": "Open Night v1.1 - bug review / GridWorld population",
                "status": "pending_server_review",
                "source": "chat_/bug",
                "category": "bug",
                "description": "building overlap",
                "note": "building overlap",
                "screenshot": "",
            })
            issue_reporter._write_rows_atomic(path, [row])
            game = FakeGame()
            require(v110_bug_delivery_client._send_row(game, row), "client did not send pending report")
            require(game.network.sent, "client send payload missing")
            sent = game.network.sent[-1]
            require(sent["context"]["client_report_id"] == row["report_id"], "client correlation ID missing")
            v110_bug_delivery_client._observe_server_message(game, {"type": "bug_report_receipt", "report_id": 91, "status": "pending"})
            stored = issue_reporter.get_issue_report(row["report_id"], path)
            require(stored and stored["status"] == "submitted", "server receipt did not close outbox")
            require(stored["server_report_id"] == "91", "server receipt ID missing locally")
            return {"sent_client_id": row["report_id"], "server_report_id": 91}
        finally:
            if old_root is None:
                os.environ.pop("PYMMO_SHARED_DATA", None)
            else:
                os.environ["PYMMO_SHARED_DATA"] = old_root


def main() -> None:
    print({
        "synthetic": exercise_synthetic_mixed_schema(),
        "server": exercise_server_idempotency(),
        "client": exercise_client_acknowledgement(),
        "uploaded_fixture": exercise_real_mixed_schema_fixture(),
    })


if __name__ == "__main__":
    main()
