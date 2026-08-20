from __future__ import annotations

"""Sessionless v1.1 bug relay endpoint for the public Railway server.

Normal gameplay may be connected to a local/LAN server.  The bug reporter should
still deliver to the public Railway/MySQL moderation queue, where railway_entry.py
mirrors accepted reports to GitHub Issues.  This module adds a narrow first-frame
WebSocket command without changing the mature gameplay session protocol.
"""

import asyncio
import base64
import binascii
import hashlib
import json
import math
import time
from typing import Any

import v110_bug_delivery_server


RELAY_TYPE = "bug_relay_submit"


class _ReplayConnection:
    """Put one already-read frame back in front of the mature client handler."""

    def __init__(self, inner, first_raw):
        self._inner = inner
        self._first_raw = first_raw

    def __getattr__(self, name):
        return getattr(self._inner, name)

    @property
    def remote_address(self):
        return getattr(self._inner, "remote_address", None)

    async def recv(self, *args, **kwargs):
        if self._first_raw is not None:
            raw = self._first_raw
            self._first_raw = None
            return raw
        return await self._inner.recv(*args, **kwargs)

    async def send(self, *args, **kwargs):
        return await self._inner.send(*args, **kwargs)

    async def close(self, *args, **kwargs):
        return await self._inner.close(*args, **kwargs)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.recv()
        except Exception as exc:
            # websockets raises ConnectionClosed when iteration is complete.
            if exc.__class__.__name__.startswith("ConnectionClosed"):
                raise StopAsyncIteration from exc
            raise


def _clean(server, value: Any, limit: int) -> str:
    return server._clean_report_text(value, limit)


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    return result if math.isfinite(result) else float(default)


async def _send_error(server, websocket, text: str) -> None:
    await server.send_json(websocket, {"type": "bug_report_error", "text": str(text)[:240], "relay": "railway"})


async def _handle_relay(server, websocket, message: dict) -> None:
    client_version = str(message.get("client_version", "")).strip()
    if client_version != server.SERVER_VERSION:
        await _send_error(server, websocket, f"Railway bug relay requires v{server.SERVER_VERSION}; client reported v{client_version or '?'}")
        await websocket.close(code=1008, reason="bug relay version mismatch")
        return
    if not server.USE_MYSQL or server.DB is None:
        await _send_error(server, websocket, "Railway review queue is unavailable")
        await websocket.close(code=1011, reason="bug relay storage unavailable")
        return

    phone = server.normalize_phone(message.get("reporter_phone"))
    if phone is None:
        await _send_error(server, websocket, "bug relay requires a valid reporter account")
        await websocket.close(code=1008, reason="invalid bug reporter")
        return
    reporter_name = server.safe_name(message.get("reporter_name"))
    description = _clean(server, message.get("description"), 400)
    if len(description) < 5:
        await _send_error(server, websocket, "describe the problem with at least 5 characters")
        await websocket.close(code=1008, reason="invalid bug description")
        return

    category = _clean(server, message.get("category"), 32).lower() or "bug"
    allowed = {"bug", "map_art", "art", "ai", "collision_nav", "other"}
    if category not in allowed:
        category = "other"
    source = _clean(server, message.get("source"), 32) or "railway_relay"
    context = message.get("context") if isinstance(message.get("context"), dict) else {}
    context = {str(k)[:64]: v for k, v in context.items()}
    context["delivery_route"] = "railway_bug_relay"
    client_report_id = str(context.get("client_report_id", "")).strip()

    # Lost acknowledgements must be cheap and idempotent.  Check before any
    # source cooldown so a retry can receive the existing Railway/GitHub ID.
    if client_report_id:
        try:
            existing = await asyncio.to_thread(
                v110_bug_delivery_server._lookup_existing_client_report,
                server.DB,
                client_report_id,
            )
        except Exception:
            existing = None
        if existing is not None:
            await server.send_json(websocket, {
                "type": "bug_report_receipt",
                "report_id": int(existing),
                "status": "pending",
                "relay": "railway",
                "existing": True,
            })
            await websocket.close(code=1000, reason="bug relay duplicate acknowledged")
            return

    remote_address = getattr(websocket, "remote_address", None)
    remote_host = str(remote_address[0]) if isinstance(remote_address, tuple) and remote_address else "unknown"
    rate_key = hashlib.sha256(f"{server.BUG_REPORT_SALT}:{remote_host}".encode("utf-8")).hexdigest()
    now = time.monotonic()
    source_last = server.bug_report_source_times.get(rate_key, -10_000.0)
    remaining = server.BUG_REPORT_SOURCE_COOLDOWN_SECONDS - (now - source_last)
    if remaining > 0.0:
        await _send_error(server, websocket, f"network report limit: wait {max(1, int(math.ceil(remaining)))} seconds")
        await websocket.close(code=1008, reason="bug relay rate limit")
        return

    screenshot = None
    screenshot_sha256 = ""
    screenshot_text = str(message.get("screenshot_base64", ""))
    if screenshot_text:
        try:
            screenshot = base64.b64decode(screenshot_text, validate=True)
        except (binascii.Error, ValueError):
            await _send_error(server, websocket, "invalid screenshot data")
            await websocket.close(code=1008, reason="invalid bug screenshot")
            return
        try:
            screenshot = server._sanitize_bug_screenshot(screenshot)
        except ValueError as exc:
            await _send_error(server, websocket, str(exc))
            await websocket.close(code=1008, reason="invalid bug screenshot")
            return
        screenshot_sha256 = hashlib.sha256(screenshot).hexdigest()

    world_x = _finite_float(message.get("world_x"))
    world_y = _finite_float(message.get("world_y"))
    try:
        level = int(float(message.get("level", 0) or 0))
    except (TypeError, ValueError):
        level = 0
    reporter_hash = hashlib.sha256(f"{server.BUG_REPORT_SALT}:{phone}".encode("utf-8")).hexdigest()

    try:
        report_id = await asyncio.to_thread(
            server.DB.create_bug_report,
            reporter_account_hash=reporter_hash,
            reporter_name=reporter_name,
            source=source,
            category=category,
            description=description,
            build_version=_clean(server, message.get("build_version"), 160),
            map_id=_clean(server, message.get("map_id"), 96),
            map_name=_clean(server, message.get("map_name"), 160),
            world_x=world_x,
            world_y=world_y,
            level=level,
            in_vehicle=bool(message.get("in_vehicle", False)),
            vehicle_id=_clean(server, message.get("vehicle_id"), 96),
            context=context,
            screenshot=screenshot,
            screenshot_sha256=screenshot_sha256,
        )
    except Exception as exc:
        print(f"Railway bug relay storage failed: {server.mysql_error_text(exc)}", flush=True)
        await _send_error(server, websocket, "Railway storage failed; local backup retained")
        await websocket.close(code=1011, reason="bug relay storage failed")
        return

    server.bug_report_source_times[rate_key] = now
    receipt = {
        "type": "bug_report_receipt",
        "report_id": int(report_id),
        "status": "pending",
        "relay": "railway",
    }
    mirror = getattr(server.DB, "_open_night_last_bug_github_mirror", None)
    if isinstance(mirror, dict) and int(mirror.get("report_id", -1)) == int(report_id):
        issue_number = int(mirror.get("issue_number", 0) or 0)
        if issue_number > 0:
            receipt["github_issue_number"] = issue_number
            receipt["github_issue_url"] = str(mirror.get("issue_url", ""))
    await server.send_json(websocket, receipt)
    await websocket.close(code=1000, reason="bug relay complete")


def install(server) -> None:
    if bool(getattr(server, "_v110_bug_railway_relay_installed", False)):
        return
    original = server.client_handler

    async def client_handler_v110(websocket):
        try:
            first_raw = await asyncio.wait_for(websocket.recv(), timeout=8.0)
        except Exception:
            return
        try:
            first = json.loads(first_raw)
        except (json.JSONDecodeError, TypeError):
            first = None
        if isinstance(first, dict) and first.get("type") == RELAY_TYPE:
            await _handle_relay(server, websocket, first)
            return
        await original(_ReplayConnection(websocket, first_raw))

    server.client_handler = client_handler_v110
    server._v110_bug_railway_relay_installed = True
