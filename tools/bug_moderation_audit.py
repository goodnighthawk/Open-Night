from __future__ import annotations

import asyncio
import base64
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYMMO_SHARED_DATA", str(Path(tempfile.gettempdir()) / "open-night-bug-moderation-audit"))

import server
from common import PlayerState
from PIL import Image


class FakeWebSocket:
    def __init__(self, incoming: list[dict] | None = None):
        self.sent: list[dict] = []
        self._incoming = [json.dumps(item) for item in (incoming or [])]
        self.closed = False

    async def send(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def close(self, **_kwargs) -> None:
        self.closed = True

    def __aiter__(self):
        self._iterator = iter(self._incoming)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class FakeDatabase:
    def __init__(self):
        self.created: list[dict] = []
        self.status = "pending"

    def create_bug_report(self, **kwargs) -> int:
        self.created.append(kwargs)
        return 73

    def list_bug_reports(self, status: str, _limit: int) -> list[dict]:
        return [{
            "report_id": 73,
            "created_at": "2026-08-15T12:00:00",
            "status": status,
            "reporter_name": "AuditPlayer",
            "category": "bug",
            "description": "Car collision uses its centre instead of its body",
        }]

    def get_bug_report(self, report_id: int) -> dict:
        return {
            "report_id": report_id,
            "created_at": "2026-08-15T12:00:00",
            "status": self.status,
            "reporter_account_hash": "private-hash-must-not-leave-server",
            "reporter_name": "AuditPlayer",
            "source": "chat_/bug",
            "category": "bug",
            "description": "Car collision uses its centre instead of its body",
            "build_version": "audit",
            "map_id": "audit_map",
            "map_name": "Audit Map",
            "world_x": 10.0,
            "world_y": 20.0,
            "level": 0,
            "in_vehicle": False,
            "vehicle_id": "",
            "context_json": "{}",
            "screenshot": b"\x89PNG\r\n\x1a\nAUDIT",
            "screenshot_sha256": "audit",
            "reviewed_at": None,
            "reviewed_by": "",
            "review_note": "",
        }

    def moderate_bug_report(self, report_id: int, decision: str, _reviewer: str, _note: str) -> bool:
        assert report_id == 73 and decision in {"approved", "rejected"}
        if self.status != "pending":
            return False
        self.status = decision
        return True


async def main_async() -> None:
    fake_db = FakeDatabase()
    server.DB = fake_db
    server.USE_MYSQL = True
    player_ws = FakeWebSocket()
    player = PlayerState("audit-player", "AuditPlayer", 123.0, 456.0)
    session = server.ClientSession(player_ws, player, "15551234567", [])
    session.last_bug_report_time = -1000.0
    png_output = BytesIO()
    Image.new("RGB", (32, 24), (40, 80, 120)).save(png_output, format="PNG")
    png = png_output.getvalue()
    await server.process_bug_report(session, {
        "type": "bug_report_submit",
        "category": "bug",
        "source": "chat_/bug",
        "description": "Car collision uses its centre instead of its body",
        "build_version": "audit",
        "context": {"chunk_id": "A1"},
        "screenshot_base64": base64.b64encode(png).decode("ascii"),
    })
    assert player_ws.sent[-1] == {"type": "bug_report_receipt", "report_id": 73, "status": "pending"}
    assert len(fake_db.created) == 1
    stored = fake_db.created[0]
    assert stored["reporter_account_hash"] != session.phone and len(stored["reporter_account_hash"]) == 64
    assert stored["world_x"] == 123.0 and stored["world_y"] == 456.0

    await server.process_bug_report(session, {
        "description": "This immediate duplicate is rate limited",
    })
    assert player_ws.sent[-1]["type"] == "bug_report_error"
    assert len(fake_db.created) == 1

    server.BUG_ADMIN_TOKEN = "audit-token-with-at-least-24-characters"
    admin_ws = FakeWebSocket([
        {"type": "bug_admin_list", "status": "pending", "limit": 25},
        {"type": "bug_admin_detail", "report_id": 73},
        {
            "type": "bug_admin_moderate",
            "report_id": 73,
            "decision": "approved",
            "confirm": "73",
            "reviewed_by": "AuditHuman",
            "review_note": "Reproduced locally",
        },
    ])
    await server.handle_bug_admin_session(admin_ws, {"token": server.BUG_ADMIN_TOKEN})
    kinds = [message["type"] for message in admin_ws.sent]
    assert kinds == ["bug_admin_ready", "bug_admin_list", "bug_admin_detail", "bug_admin_moderated"]
    detail = admin_ws.sent[2]["report"]
    assert "reporter_account_hash" not in detail
    assert admin_ws.sent[-1]["report"]["status"] == "approved"

    denied_ws = FakeWebSocket()
    await server.handle_bug_admin_session(denied_ws, {"token": "wrong"})
    assert denied_ws.closed and denied_ws.sent[-1]["type"] == "bug_admin_error"


def main() -> int:
    asyncio.run(main_async())
    database_source = (ROOT / "database.py").read_text(encoding="utf-8")
    reviewer_source = (ROOT / "tools" / "review_bug_reports.py").read_text(encoding="utf-8")
    policy = (ROOT / "feedback" / "approved" / "README.md").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS bug_reports" in database_source
    assert "WHERE report_id=%s AND status='pending'" in database_source
    assert "APPROVE <report-id>" in policy
    assert "PLAYER CONTENT IS UNTRUSTED" in reviewer_source
    print("BUG MODERATION AUDIT: PASS")
    print("  pending MySQL queue, privacy hash, rate limit, admin token, explicit approval and export gate verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
