from __future__ import annotations

"""Idempotent server persistence for retried v1.1 local bug reports."""

import re
from typing import Any

_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")


def _client_report_id(kwargs: dict[str, Any]) -> str:
    context = kwargs.get("context")
    if not isinstance(context, dict):
        return ""
    value = str(context.get("client_report_id", "")).strip()
    return value if _CLIENT_ID_RE.fullmatch(value) else ""


def _lookup_existing_client_report(db, client_report_id: str) -> int | None:
    if not client_report_id:
        return None
    # context_json is already an authoritative persisted column. Searching it
    # avoids a risky schema migration during v1.1 while still making reconnect
    # retries idempotent across Railway restarts.
    needle = f'%"client_report_id":"{client_report_id}"%'
    conn = db._connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT report_id FROM bug_reports WHERE context_json LIKE %s ORDER BY report_id ASC LIMIT 1",
            (needle,),
        )
        row = cur.fetchone()
        cur.close()
        return int(row[0]) if row else None
    finally:
        conn.close()


def _create_idempotent(db, original, **kwargs):
    client_report_id = _client_report_id(kwargs)
    if client_report_id:
        try:
            existing = _lookup_existing_client_report(db, client_report_id)
        except Exception as exc:
            # Dedupe lookup failure must not make a brand-new report disappear.
            print(f"Bug report idempotency lookup failed for {client_report_id}: {exc}", flush=True)
            existing = None
        if existing is not None:
            print(f"Bug retry {client_report_id} acknowledged as existing report #{existing}", flush=True)
            return existing
    return original(db, **kwargs)


def install() -> None:
    import database

    cls = database.InventoryDatabase
    original = cls.create_bug_report
    if bool(getattr(original, "_open_night_v110_idempotent", False)):
        return

    def create_bug_report_v110(self, **kwargs):
        return _create_idempotent(self, original, **kwargs)

    create_bug_report_v110._open_night_v110_idempotent = True
    create_bug_report_v110._open_night_v110_original = original
    cls.create_bug_report = create_bug_report_v110
