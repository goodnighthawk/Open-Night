#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from contextlib import contextmanager
import csv
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gameplay import issue_reporter
import v110_bug_delivery_client
import v110_bug_delivery_server
import v110_bug_railway_relay_client
import v110_bug_railway_relay_server
from versioning import GAME_VERSION


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


@contextmanager
def audit_directory(name: str):
    """Use an ordinary workspace directory; Windows temp ACLs can block CI."""
    path = ROOT / "work" / "audit_v110_bug_delivery" / name
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


def exercise_real_mixed_schema_fixture() -> dict:
    fixture = os.getenv("OPEN_NIGHT_BUG_FIXTURE", "").strip()
    if not fixture:
        return {"fixture": "not supplied"}
    source = Path(fixture)
    require(source.is_file(), f"fixture missing: {source}")
    with audit_directory("real_fixture") as tmp:
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

    with audit_directory("synthetic_schema") as tmp:
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


async def _exercise_pre_cooldown_retry_async() -> dict:
    receipts = []
    original_calls = []

    class FakeDB:
        pass

    async def send_json(_websocket, payload):
        receipts.append(payload)

    async def original(_session, _message):
        original_calls.append(True)

    server = SimpleNamespace(asyncio=asyncio, DB=FakeDB(), USE_MYSQL=True, send_json=send_json)
    session = SimpleNamespace(websocket=object())
    message = {"context": {"client_report_id": "ON-20260820T004555_000000Z"}}
    saved_lookup = v110_bug_delivery_server._lookup_existing_client_report
    try:
        v110_bug_delivery_server._lookup_existing_client_report = lambda db, client_id: 55
        await v110_bug_delivery_server._process_bug_report_idempotent(server, original, session, message)
    finally:
        v110_bug_delivery_server._lookup_existing_client_report = saved_lookup
    require(not original_calls, "known retry fell through to cooldown/storage path")
    require(receipts and receipts[0].get("report_id") == 55, "known retry did not receive existing report receipt")
    require(receipts[0].get("duplicate_retry") is True, "retry receipt is not marked duplicate_retry")
    return {"pre_cooldown_receipt": 55}


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
            self._bug_delivery_notice_override = None
            self.notice = ""
            self.notice_until = 0.0
        def _build_version(self):
            return "Open Night v1.1 - bug review / GridWorld population"

    with audit_directory("client_ack") as tmp:
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
            require(v110_bug_delivery_client._send_row(game, row), "legacy acknowledged outbox send failed")
            require(game.network.sent, "legacy client send payload missing")
            sent = game.network.sent[-1]
            require(sent["context"]["client_report_id"] == row["report_id"], "client correlation ID missing")
            v110_bug_delivery_client._observe_server_message(game, {"type": "bug_report_receipt", "report_id": 91, "status": "pending"})
            stored = issue_reporter.get_issue_report(row["report_id"], path)
            require(stored and stored["status"] == "submitted", "server receipt did not close outbox")
            require(stored["server_report_id"] == "91", "server receipt ID missing locally")

            retry = dict(row)
            retry["report_id"] = "ON-20260820T005001_000000Z"
            retry["status"] = "pending_server_review"
            issue_reporter._write_rows_atomic(path, [retry])
            game._bug_delivery_inflight = retry["report_id"]
            v110_bug_delivery_client._observe_server_message(game, {"type": "bug_report_error", "text": "the server review queue is unavailable"})
            failed = issue_reporter.get_issue_report(retry["report_id"], path)
            require(failed and failed["status"] == "retry_pending", "temporary server failure was not queued for retry")
            return {"sent_client_id": row["report_id"], "server_report_id": 91, "retry_status": failed["status"]}
        finally:
            if old_root is None:
                os.environ.pop("PYMMO_SHARED_DATA", None)
            else:
                os.environ["PYMMO_SHARED_DATA"] = old_root


def exercise_railway_client_route() -> dict:
    class FakeGameplayNetwork:
        phone = "+15550000023"
        name = "LocalPlayer"
        def __init__(self):
            self.sent = []
        def send(self, payload):
            self.sent.append(payload)

    class FakeRelay:
        uri = "wss://open-night-production.up.railway.app"
        def __init__(self):
            self.sent = []
            self.incoming = __import__("queue").Queue()
        def send(self, report_id, payload):
            self.sent.append((report_id, payload))
            return True

    class FakeGame:
        def __init__(self):
            self.network = FakeGameplayNetwork()
            self._railway_bug_relay = FakeRelay()
            self._bug_delivery_inflight = None
            self._bug_delivery_inflight_sent_at = 0.0
            self._bug_delivery_retry_at = 0.0
            self.notice = ""
            self.notice_until = 0.0

    with audit_directory("railway_relay") as tmp:
        old_root = os.environ.get("PYMMO_SHARED_DATA")
        os.environ["PYMMO_SHARED_DATA"] = tmp
        try:
            path = Path(tmp) / "issue_reports" / "issue_reports.csv"
            row = {field: "" for field in issue_reporter.REPORT_FIELDS}
            row.update({
                "report_id": "ON-20260820T011500_000000Z",
                "timestamp_utc": "2026-08-20T01:15:00Z",
                "build_version": "Open Night v1.1 - playable",
                "status": "pending_server_review",
                "source": "chat_/bug",
                "category": "bug",
                "description": "traffic light is floating",
                "note": "traffic light is floating",
                "map_id": "map_001_gwb_corridor",
                "map_name": "Fort Lee / GWB / Washington Heights",
                "world_x": "1234.5",
                "world_y": "2345.5",
                "level": "0",
                "screenshot": "",
            })
            issue_reporter._write_rows_atomic(path, [row])
            game = FakeGame()
            require(v110_bug_railway_relay_client._send_row_to_railway(game, row, announce=True), "Railway relay did not accept local report")
            require(not game.network.sent, "bug leaked to the local gameplay server")
            require(len(game._railway_bug_relay.sent) == 1, "Railway relay did not receive report")
            local_id, payload = game._railway_bug_relay.sent[0]
            require(local_id == row["report_id"], "Railway relay lost local correlation ID")
            require(payload["type"] == "bug_relay_submit", "Railway relay protocol type missing")
            require(payload["client_version"] == GAME_VERSION, "Railway relay version authority missing")
            require(payload["reporter_phone"] == FakeGameplayNetwork.phone, "Railway relay reporter identity missing")
            require(float(payload["world_x"]) == 1234.5, "Railway relay lost gameplay coordinates")

            game._railway_bug_relay.incoming.put({
                "type": "bug_report_receipt",
                "local_report_id": row["report_id"],
                "report_id": 144,
                "status": "pending",
                "relay": "railway",
                "github_issue_number": 52,
            })
            v110_bug_railway_relay_client._drain_relay(game)
            stored = issue_reporter.get_issue_report(row["report_id"], path)
            require(stored and stored["status"] == "submitted", "Railway receipt did not close local outbox")
            require(stored["server_report_id"] == "144", "Railway DB report ID not persisted")
            require("GitHub issue #52" in game.notice, "player did not receive GitHub-readable acknowledgement")
            uri = v110_bug_railway_relay_client._public_relay_uri()
            require(
                uri == "wss://open-night-production.up.railway.app",
                f"configured relay is not the canonical production Railway endpoint: {uri!r}",
            )
            require("open-night-v1-1" not in uri, "configured relay still targets retired staging")
            return {"railway_db_id": 144, "github_issue": 52, "relay_uri": uri}
        finally:
            if old_root is None:
                os.environ.pop("PYMMO_SHARED_DATA", None)
            else:
                os.environ["PYMMO_SHARED_DATA"] = old_root


async def _exercise_railway_server_route_async() -> dict:
    calls = []
    receipts = []

    class FakeDB:
        def create_bug_report(self, **kwargs):
            calls.append(kwargs)
            self._open_night_last_bug_github_mirror = {
                "report_id": 211,
                "issue_number": 61,
                "issue_url": "https://github.com/goodnighthawk/Open-Night/issues/61",
            }
            return 211

    class FakeWebSocket:
        remote_address = ("203.0.113.20", 45678)
        def __init__(self):
            self.closed = None
        async def close(self, code=1000, reason=""):
            self.closed = (code, reason)

    async def send_json(_ws, payload):
        receipts.append(payload)

    def normalize_phone(value):
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        return digits if 7 <= len(digits) <= 15 else None

    server = SimpleNamespace(
        SERVER_VERSION=GAME_VERSION,
        USE_MYSQL=True,
        DB=FakeDB(),
        normalize_phone=normalize_phone,
        safe_name=lambda value: str(value or "Player")[:24],
        _clean_report_text=lambda value, limit: " ".join(str(value or "").split())[:limit],
        send_json=send_json,
        BUG_REPORT_SALT="test-salt",
        BUG_REPORT_SOURCE_COOLDOWN_SECONDS=15.0,
        bug_report_source_times={},
        _sanitize_bug_screenshot=lambda data: data,
        mysql_error_text=lambda exc: str(exc),
    )
    websocket = FakeWebSocket()
    message = {
        "type": "bug_relay_submit",
        "client_version": GAME_VERSION,
        "reporter_phone": "+1 555 000 0023",
        "reporter_name": "LocalPlayer",
        "source": "chat_/bug",
        "category": "bug",
        "description": "door collision is offset",
        "build_version": "Open Night v1.1 - playable",
        "map_id": "map_001_gwb_corridor",
        "map_name": "Fort Lee / GWB / Washington Heights",
        "world_x": 1400.0,
        "world_y": 900.0,
        "level": 0,
        "in_vehicle": False,
        "vehicle_id": "",
        "screenshot_base64": "",
        "context": {"client_report_id": "ON-20260820T011700_000000Z", "chunk_id": "B4"},
    }
    saved_lookup = v110_bug_delivery_server._lookup_existing_client_report
    try:
        v110_bug_delivery_server._lookup_existing_client_report = lambda db, client_id: None
        await v110_bug_railway_relay_server._handle_relay(server, websocket, message)
    finally:
        v110_bug_delivery_server._lookup_existing_client_report = saved_lookup
    require(len(calls) == 1, "Railway relay did not persist exactly one DB report")
    require(calls[0]["context"]["delivery_route"] == "railway_bug_relay", "Railway delivery route not persisted")
    require(calls[0]["world_x"] == 1400.0 and calls[0]["world_y"] == 900.0, "Railway relay lost reported world position")
    require(receipts and receipts[-1].get("report_id") == 211, "Railway relay receipt missing DB ID")
    require(receipts[-1].get("github_issue_number") == 61, "Railway relay receipt missing GitHub issue ID")
    require(websocket.closed and websocket.closed[0] == 1000, "Railway relay did not close cleanly")
    return {"railway_db_id": 211, "github_issue": 61}


def main() -> None:
    print({
        "synthetic": exercise_synthetic_mixed_schema(),
        "server": exercise_server_idempotency(),
        "pre_cooldown": asyncio.run(_exercise_pre_cooldown_retry_async()),
        "client": exercise_client_acknowledgement(),
        "railway_client": exercise_railway_client_route(),
        "railway_server": asyncio.run(_exercise_railway_server_route_async()),
        "uploaded_fixture": exercise_real_mixed_schema_fixture(),
    })


if __name__ == "__main__":
    main()
