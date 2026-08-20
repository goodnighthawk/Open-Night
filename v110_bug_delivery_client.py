from __future__ import annotations

"""Reliable local-outbox -> server acknowledgement delivery for Open Night v1.1."""

import base64
from pathlib import Path
import re
import time

from gameplay.issue_reporter import (
    get_issue_report,
    mark_issue_report_attempt,
    mark_issue_report_error,
    mark_issue_report_submitted,
    migrate_issue_report_csv,
    pending_issue_reports,
    save_issue_report,
)
from portable_paths import shared_issue_reports_root

MAX_SCREENSHOT_BYTES = 1_500_000
ACK_TIMEOUT_SECONDS = 20.0
OUTBOX_SCAN_SECONDS = 2.0
RECONNECT_RETRY_DELAY_SECONDS = 10.0
UNAVAILABLE_RETRY_SECONDS = 60.0


class _ObservedQueue:
    """Delegate Queue API while observing every message consumed by the game."""

    def __init__(self, inner, observer):
        self._inner = inner
        self._observer = observer

    def get_nowait(self):
        item = self._inner.get_nowait()
        self._observer(item)
        return item

    def put(self, item, *args, **kwargs):
        return self._inner.put(item, *args, **kwargs)

    def put_nowait(self, item):
        return self._inner.put_nowait(item)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _retry_delay(text: str) -> float:
    match = re.search(r"(?:wait|in)\s+(\d+)\s+seconds?", str(text), re.IGNORECASE)
    if match:
        return max(2.0, float(match.group(1)) + 1.0)
    lower = str(text).lower()
    if "session report limit" in lower:
        return float("inf")
    if "unavailable" in lower or "storage failed" in lower or "upload failed" in lower:
        return UNAVAILABLE_RETRY_SECONDS
    return 30.0


def _retryable_error(text: str) -> bool:
    lower = str(text).lower()
    nonretryable = (
        "at least 5 characters",
        "invalid screenshot",
        "unsupported screenshot",
        "screenshot is too large",
    )
    return not any(token in lower for token in nonretryable)


def _submission_from_row(row: dict[str, str]) -> dict:
    screenshot_base64 = ""
    relative = str(row.get("screenshot", "")).strip().replace("\\", "/")
    if relative:
        shot = shared_issue_reports_root() / Path(relative)
        try:
            data = shot.read_bytes()
            if len(data) <= MAX_SCREENSHOT_BYTES:
                screenshot_base64 = base64.b64encode(data).decode("ascii")
        except OSError:
            pass
    context_keys = (
        "camera_rotation_deg", "camera_zoom", "chunk_id", "chunk_x", "chunk_y",
        "local_x", "local_y", "nearest_ai_distance", "nearest_ai_id", "nearest_ai_kind",
    )
    context = {key: row.get(key, "") for key in context_keys}
    context["client_report_id"] = str(row.get("report_id", ""))
    context["local_report_timestamp_utc"] = str(row.get("timestamp_utc", ""))
    return {
        "type": "bug_report_submit",
        "source": str(row.get("source", "chat_/bug"))[:32],
        "category": str(row.get("category", "bug"))[:32],
        "description": str(row.get("description") or row.get("note") or "bug report")[:400],
        "build_version": str(row.get("build_version", ""))[:160],
        "screenshot_base64": screenshot_base64,
        "context": context,
    }


def _send_row(game, row: dict[str, str], *, announce: bool = False) -> bool:
    report_id = str(row.get("report_id", "")).strip()
    if not report_id or getattr(game, "_bug_delivery_inflight", None):
        return False
    if not bool(getattr(game, "connected", False)):
        if announce:
            game.notice = "Bug saved locally — it will send when a v1.1 review server is available"
            game.notice_until = time.monotonic() + 5.0
        return False
    game.network.send(_submission_from_row(row))
    mark_issue_report_attempt(report_id)
    game._bug_delivery_inflight = report_id
    game._bug_delivery_inflight_sent_at = time.monotonic()
    if announce:
        game.notice = "Bug saved locally — sending to server..."
        game.notice_until = time.monotonic() + 4.0
    return True


def _observe_server_message(game, message) -> None:
    if not isinstance(message, dict):
        return
    kind = str(message.get("type", ""))
    now = time.monotonic()
    if kind == "connection":
        connected = bool(message.get("connected"))
        if not connected and getattr(game, "_bug_delivery_inflight", None):
            mark_issue_report_error(
                game._bug_delivery_inflight,
                "connection lost before server acknowledgement",
                retryable=True,
            )
            game._bug_delivery_inflight = None
            game._bug_delivery_inflight_sent_at = 0.0
        if connected:
            game._bug_delivery_retry_at = now + RECONNECT_RETRY_DELAY_SECONDS
        return
    if kind == "welcome":
        game._bug_delivery_retry_at = now + RECONNECT_RETRY_DELAY_SECONDS
        return
    report_id = getattr(game, "_bug_delivery_inflight", None)
    if kind == "bug_report_receipt":
        if report_id:
            mark_issue_report_submitted(
                report_id,
                int(message.get("report_id", 0) or 0),
                str(message.get("status", "pending")),
            )
        game._bug_delivery_inflight = None
        game._bug_delivery_inflight_sent_at = 0.0
        game._bug_delivery_retry_at = now + 1.0
    elif kind == "bug_report_error":
        text = str(message.get("text", "server upload failed"))
        retryable = _retryable_error(text)
        if report_id:
            mark_issue_report_error(report_id, text, retryable=retryable)
        game._bug_delivery_inflight = None
        game._bug_delivery_inflight_sent_at = 0.0
        game._bug_delivery_retry_at = now + _retry_delay(text) if retryable else float("inf")


def _current_build_family(game) -> str:
    build = str(game._build_version())
    match = re.search(r"Open Night v\d+(?:\.\d+)+", build, re.IGNORECASE)
    return match.group(0).casefold() if match else build.casefold()


def _pump_outbox(game) -> None:
    now = time.monotonic()
    inflight = getattr(game, "_bug_delivery_inflight", None)
    if inflight:
        sent_at = float(getattr(game, "_bug_delivery_inflight_sent_at", 0.0) or 0.0)
        if sent_at and now - sent_at >= ACK_TIMEOUT_SECONDS:
            mark_issue_report_error(inflight, "server acknowledgement timed out", retryable=True)
            game._bug_delivery_inflight = None
            game._bug_delivery_inflight_sent_at = 0.0
            game._bug_delivery_retry_at = now + 15.0
        return
    if not bool(getattr(game, "connected", False)):
        return
    if now < float(getattr(game, "_bug_delivery_retry_at", 0.0) or 0.0):
        return
    if now < float(getattr(game, "_bug_delivery_next_scan", 0.0) or 0.0):
        return
    game._bug_delivery_next_scan = now + OUTBOX_SCAN_SECONDS
    family = _current_build_family(game)
    rows = [
        row for row in pending_issue_reports(limit=100)
        if family and family in str(row.get("build_version", "")).casefold()
    ]
    if not rows:
        return
    _send_row(game, rows[0], announce=False)


def install(game_client) -> None:
    game = game_client.Game
    if bool(getattr(game, "_v110_bug_delivery_installed", False)):
        return

    original_init = game.__init__
    original_process_network = game.process_network

    def init_v110(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            migrate_issue_report_csv()
        except Exception as exc:
            print(f"Bug outbox migration warning: {exc}", flush=True)
        self._bug_delivery_inflight = None
        self._bug_delivery_inflight_sent_at = 0.0
        self._bug_delivery_retry_at = time.monotonic() + RECONNECT_RETRY_DELAY_SECONDS
        self._bug_delivery_next_scan = 0.0
        incoming = getattr(self.network, "incoming", None)
        if incoming is not None and not isinstance(incoming, _ObservedQueue):
            self.network.incoming = _ObservedQueue(incoming, lambda message: _observe_server_message(self, message))

    def save_current_issue_report_v110(self, source: str = "f10") -> None:
        local = self.players.get(self.local_id or "")
        if local is None:
            self.notice = "Cannot report yet — local player position unavailable"
            self.notice_until = time.monotonic() + 2.0
            return
        x, y = float(local.render_x), float(local.render_y)
        cx, cy = game_client.world_to_chunk(x, y, self.map_config)
        chunk_size = max(1, int(self.map_config.get("chunk_size", 1024)))
        local_x = x - cx * chunk_size
        local_y = y - cy * chunk_size
        ai_kind, ai_id, ai_distance = self._nearest_ai_context(x, y)
        description = self.issue_report_note.strip()
        if not description:
            description = f"{self.issue_report_category.replace('_', ' ')} issue reported with F10 in {game_client.chunk_label(cx, cy)}"
        payload = {
            "source": source,
            "reporter": str(getattr(self.network, "name", ""))[:24],
            "description": description,
            "target_version": "next",
            "duplicate_of": "",
            "build_version": self._build_version(),
            "status": "pending_server_review",
            "category": self.issue_report_category,
            "note": description,
            "map_id": str(self.map_config.get("id", "")),
            "map_name": str(self.map_config.get("name", "")),
            "chunk_id": game_client.chunk_label(cx, cy),
            "chunk_x": cx,
            "chunk_y": cy,
            "world_x": x,
            "world_y": y,
            "local_x": local_x,
            "local_y": local_y,
            "camera_rotation_deg": float(self.camera_rotation_degrees % 360.0),
            "camera_zoom": float(self.camera_zoom),
            "in_vehicle": bool(getattr(local, "in_vehicle", False)),
            "vehicle_id": str(getattr(local, "vehicle_id", "")),
            "nearest_ai_kind": ai_kind,
            "nearest_ai_id": ai_id,
            "nearest_ai_distance": ai_distance if ai_distance >= 0 else "",
        }
        try:
            capture = self.issue_report_snapshot if self.issue_report_snapshot is not None else self.screen
            _, shot_path = save_issue_report(capture, payload)
            row = get_issue_report(str(payload.get("report_id", "")))
        except Exception as exc:
            self.notice = f"Issue report failed: {exc}"
            self.notice_until = time.monotonic() + 4.0
            return

        self.issue_report_open = False
        self.issue_report_note = ""
        self.issue_report_select_all = False
        self.issue_report_snapshot = None
        if row is not None:
            _send_row(self, row, announce=True)
        else:
            self.notice = f"Bug saved locally as {shot_path.name}; outbox index unavailable"
            self.notice_until = time.monotonic() + 5.0

    def process_network_v110(self) -> None:
        original_process_network(self)
        _pump_outbox(self)

    game.__init__ = init_v110
    game.save_current_issue_report = save_current_issue_report_v110
    game.process_network = process_network_v110
    game._v110_bug_delivery_installed = True
