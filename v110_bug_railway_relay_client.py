from __future__ import annotations

"""Route v1.1 /bug delivery to Railway even while gameplay is local/LAN."""

import asyncio
import json
import queue
import sys
import threading
import time
from typing import Any

from gameplay.issue_reporter import mark_issue_report_attempt, mark_issue_report_error, mark_issue_report_submitted
from server_directory import load_public_servers
from versioning import GAME_VERSION
import v110_bug_delivery_client as delivery


RELAY_TIMEOUT_SECONDS = 20.0


def _public_relay_uri() -> str:
    try:
        rows = load_public_servers()
    except Exception:
        rows = []
    for row in rows:
        uri = str(row.get("uri", "")).strip()
        if uri.startswith(("ws://", "wss://")):
            return uri
    return ""


class RailwayBugRelay:
    def __init__(self, uri: str):
        self.uri = str(uri)
        self.outgoing: queue.Queue[tuple[str, dict]] = queue.Queue(maxsize=32)
        self.incoming: queue.Queue[dict] = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._thread_main, daemon=True)

    def start(self) -> None:
        if self.uri and not self.thread.is_alive():
            self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def send(self, local_report_id: str, payload: dict) -> bool:
        if not self.uri or self.stop_event.is_set():
            return False
        try:
            self.outgoing.put_nowait((str(local_report_id), dict(payload)))
            return True
        except queue.Full:
            return False

    def _thread_main(self) -> None:
        while not self.stop_event.is_set():
            try:
                local_report_id, payload = self.outgoing.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                message = asyncio.run(self._submit(payload))
            except Exception as exc:
                message = {
                    "type": "bug_report_error",
                    "text": f"Railway bug relay unavailable: {type(exc).__name__}: {exc}",
                    "relay": "railway",
                }
            message["local_report_id"] = local_report_id
            self.incoming.put(message)

    async def _submit(self, payload: dict) -> dict:
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosed

        async with asyncio.timeout(RELAY_TIMEOUT_SECONDS):
            async with connect(self.uri, ping_interval=20, ping_timeout=20, max_size=3 * 1024 * 1024) as websocket:
                await websocket.send(json.dumps(payload, separators=(",", ":")))
                while True:
                    try:
                        raw = await websocket.recv()
                    except ConnectionClosed as exc:
                        raise RuntimeError("Railway relay closed before acknowledgement") from exc
                    message = json.loads(raw)
                    if str(message.get("type", "")) in {"bug_report_receipt", "bug_report_error"}:
                        return message


def _relay_payload(game, row: dict[str, str]) -> dict[str, Any]:
    payload = delivery._submission_from_row(row)
    payload["type"] = "bug_relay_submit"
    payload["client_version"] = GAME_VERSION
    payload["reporter_phone"] = str(getattr(game.network, "phone", ""))
    payload["reporter_name"] = str(getattr(game.network, "name", ""))[:24]
    payload["map_id"] = str(row.get("map_id", ""))[:96]
    payload["map_name"] = str(row.get("map_name", ""))[:160]
    payload["world_x"] = row.get("world_x", "0")
    payload["world_y"] = row.get("world_y", "0")
    payload["level"] = row.get("level", "0")
    payload["in_vehicle"] = str(row.get("in_vehicle", "")).strip().lower() in {"1", "true", "yes", "on"}
    payload["vehicle_id"] = str(row.get("vehicle_id", ""))[:96]
    return payload


def _send_row_to_railway(game, row: dict[str, str], *, announce: bool = False) -> bool:
    report_id = str(row.get("report_id", "")).strip()
    if not report_id or getattr(game, "_bug_delivery_inflight", None):
        return False
    relay = getattr(game, "_railway_bug_relay", None)
    if relay is None or not relay.uri:
        mark_issue_report_error(report_id, "Railway bug relay is not configured", retryable=True)
        if announce:
            game.notice = "Bug saved locally — Railway relay unavailable; automatic retry is queued"
            game.notice_until = time.monotonic() + 5.0
        return False
    if not relay.send(report_id, _relay_payload(game, row)):
        mark_issue_report_error(report_id, "Railway bug relay queue is busy", retryable=True)
        if announce:
            game.notice = "Bug saved locally — Railway relay busy; automatic retry is queued"
            game.notice_until = time.monotonic() + 5.0
        return False
    mark_issue_report_attempt(report_id)
    game._bug_delivery_inflight = report_id
    game._bug_delivery_inflight_sent_at = time.monotonic()
    if announce:
        game.notice = "Bug saved locally — sending to Railway / GitHub..."
        game.notice_until = time.monotonic() + 5.0
    return True


def _drain_relay(game) -> None:
    relay = getattr(game, "_railway_bug_relay", None)
    if relay is None:
        return
    while True:
        try:
            message = relay.incoming.get_nowait()
        except queue.Empty:
            break
        local_report_id = str(message.get("local_report_id", "") or getattr(game, "_bug_delivery_inflight", ""))
        kind = str(message.get("type", ""))
        now = time.monotonic()
        if kind == "bug_report_receipt":
            server_report_id = int(message.get("report_id", 0) or 0)
            mark_issue_report_submitted(local_report_id, server_report_id, str(message.get("status", "pending")))
            game._bug_delivery_inflight = None
            game._bug_delivery_inflight_sent_at = 0.0
            game._bug_delivery_retry_at = now + 1.0
            issue_number = int(message.get("github_issue_number", 0) or 0)
            if issue_number:
                game.notice = f"Bug #{server_report_id} sent to Railway + GitHub issue #{issue_number}"
            else:
                game.notice = f"Bug #{server_report_id} sent to Railway; GitHub mirror requested"
            game.notice_until = now + 6.0
        elif kind == "bug_report_error":
            text = str(message.get("text", "Railway bug relay failed"))
            retryable = delivery._retryable_error(text)
            mark_issue_report_error(local_report_id, text, retryable=retryable)
            game._bug_delivery_inflight = None
            game._bug_delivery_inflight_sent_at = 0.0
            game._bug_delivery_retry_at = now + delivery._retry_delay(text) if retryable else float("inf")
            game.notice = "Bug saved locally — " + text + ("; automatic retry queued" if retryable else "")
            game.notice_until = now + 6.0


def install(game_client) -> None:
    game = game_client.Game
    if bool(getattr(game, "_v110_bug_railway_relay_installed", False)):
        return

    original_init = game.__init__
    original_process_network = game.process_network
    original_run = game.run

    def init_v110(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        uri = _public_relay_uri()
        self._railway_bug_relay = RailwayBugRelay(uri) if sys.platform != "emscripten" else None
        if self._railway_bug_relay is not None:
            self._railway_bug_relay.start()

    def process_network_v110(self) -> None:
        original_process_network(self)
        _drain_relay(self)

    async def run_v110(self, *args, **kwargs):
        try:
            return await original_run(self, *args, **kwargs)
        finally:
            relay = getattr(self, "_railway_bug_relay", None)
            if relay is not None:
                relay.stop()

    game.__init__ = init_v110
    game.process_network = process_network_v110
    game.run = run_v110
    # Both the immediate F10 path and the existing durable outbox pump resolve
    # this module global at call time, so replacing it routes every v1.1 report
    # to Railway rather than to the current gameplay server.
    delivery._send_row = _send_row_to_railway
    game._v110_bug_railway_relay_installed = True
