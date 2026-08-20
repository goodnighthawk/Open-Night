from __future__ import annotations

"""Idempotent server persistence and retry acknowledgement for v1.1 bug reports."""

import re
from typing import Any

_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")


def _client_report_id(kwargs: dict[str, Any]) -> str:
    context = kwargs.get("context")
    if not isinstance(context, dict):
        return ""
    value = str(context.get("client_report_id", "")).strip()
    return value if _CLIENT_ID_RE.fullmatch(value) else ""


def _message_client_report_id(message: dict[str, Any]) -> str:
    context = message.get("context")
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


async def _process_bug_report_idempotent(server_module, original, session, message: dict) -> None:
    """Acknowledge an already-stored retry before normal cooldown checks run."""
    client_report_id = _message_client_report_id(message)
    db = getattr(server_module, "DB", None)
    if client_report_id and bool(getattr(server_module, "USE_MYSQL", False)) and db is not None:
        try:
            existing = await server_module.asyncio.to_thread(
                _lookup_existing_client_report, db, client_report_id,
            )
        except Exception as exc:
            print(f"Bug retry lookup failed for {client_report_id}: {exc}", flush=True)
            existing = None
        if existing is not None:
            await server_module.send_json(session.websocket, {
                "type": "bug_report_receipt",
                "report_id": int(existing),
                "status": "pending",
                "duplicate_retry": True,
                "client_report_id": client_report_id,
            })
            return
    await original(session, message)


def install(server_module=None) -> None:
    import database

    cls = database.InventoryDatabase
    original_create = cls.create_bug_report
    if not bool(getattr(original_create, "_open_night_v110_idempotent", False)):
        def create_bug_report_v110(self, **kwargs):
            return _create_idempotent(self, original_create, **kwargs)

        create_bug_report_v110._open_night_v110_idempotent = True
        create_bug_report_v110._open_night_v110_original = original_create
        cls.create_bug_report = create_bug_report_v110

    if server_module is None:
        return
    original_process = server_module.process_bug_report
    if bool(getattr(original_process, "_open_night_v110_idempotent", False)):
        return

    async def process_bug_report_v110(session, message):
        await _process_bug_report_idempotent(server_module, original_process, session, message)

    process_bug_report_v110._open_night_v110_idempotent = True
    process_bug_report_v110._open_night_v110_original = original_process
    server_module.process_bug_report = process_bug_report_v110
