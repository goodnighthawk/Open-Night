from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import csv
import getpass
import json
import os
from pathlib import Path
import tempfile

from websockets.asyncio.client import connect

from server_directory import load_public_servers


ROOT = Path(__file__).resolve().parents[1]
APPROVED_ROOT = ROOT / "feedback" / "approved"
APPROVED_CSV = APPROVED_ROOT / "approved_bug_reports.csv"
APPROVED_SCREENSHOTS = APPROVED_ROOT / "screenshots"
REVIEW_CACHE = Path(tempfile.gettempdir()) / "open-night-bug-review"
APPROVED_FIELDS = [
    "report_id",
    "created_at",
    "status",
    "reporter_name",
    "source",
    "category",
    "description",
    "build_version",
    "map_id",
    "map_name",
    "world_x",
    "world_y",
    "level",
    "in_vehicle",
    "vehicle_id",
    "context_json",
    "screenshot",
    "screenshot_sha256",
    "reviewed_at",
    "reviewed_by",
    "review_note",
]


def default_server() -> str:
    configured = load_public_servers()
    if configured:
        return str(configured[0]["uri"])
    return "wss://open-night-production.up.railway.app"


async def send_json(websocket, payload: dict) -> None:
    await websocket.send(json.dumps(payload, separators=(",", ":")))


async def receive_json(websocket) -> dict:
    return json.loads(await websocket.recv())


def show_report(report: dict) -> None:
    print()
    print(f"Report #{report.get('report_id')} [{report.get('status', 'unknown')}]")
    print(f"  Submitted: {report.get('created_at', '')}")
    print(f"  Reporter:  {report.get('reporter_name', '')}")
    print(f"  Category:  {report.get('category', '')}")
    print(f"  Build:     {report.get('build_version', '')}")
    print(f"  Location:  {report.get('map_name', '')} ({report.get('world_x')}, {report.get('world_y')}) level {report.get('level')}")
    print(f"  Vehicle:   {report.get('vehicle_id', '')}")
    print(f"  Text:      {report.get('description', '')}")
    context = report.get("context")
    if isinstance(context, dict) and context:
        print(f"  Context:   {json.dumps(context, ensure_ascii=False, sort_keys=True)}")
    note = str(report.get("review_note", ""))
    if note:
        print(f"  Review:    {note}")


def save_review_screenshot(report: dict, root: Path) -> Path | None:
    encoded = str(report.get("screenshot_base64", ""))
    if not encoded:
        return None
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"BUG-{int(report['report_id']):08d}.png"
    path.write_bytes(data)
    return path


def open_screenshot(path: Path | None) -> None:
    if path is None:
        print("  Screenshot: none supplied")
        return
    print(f"  Screenshot: {path}")
    if os.getenv("PYMMO_BUG_REVIEW_NO_OPEN", "").strip().casefold() in {"1", "true", "yes"}:
        return
    if os.name == "nt":
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except OSError:
            pass


def export_approved(report: dict) -> None:
    APPROVED_SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    screenshot_path = save_review_screenshot(report, APPROVED_SCREENSHOTS)
    screenshot_value = f"screenshots/{screenshot_path.name}" if screenshot_path else ""
    existing_ids: set[str] = set()
    if APPROVED_CSV.is_file():
        with APPROVED_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
            existing_ids = {str(row.get("report_id", "")) for row in csv.DictReader(handle)}
    report_id = str(report.get("report_id", ""))
    if report_id in existing_ids:
        print(f"Report #{report_id} was already exported.")
        return
    context = report.get("context") if isinstance(report.get("context"), dict) else {}
    row = {field: report.get(field, "") for field in APPROVED_FIELDS}
    row["context_json"] = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    row["screenshot"] = screenshot_value
    exists = APPROVED_CSV.is_file() and APPROVED_CSV.stat().st_size > 0
    with APPROVED_CSV.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=APPROVED_FIELDS, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        # Neutralize spreadsheet formulas in every player-controlled text cell.
        safe_row = {}
        for field, value in row.items():
            text = str(value)
            safe_row[field] = "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
        writer.writerow(safe_row)
    print(f"Approved report exported to {APPROVED_CSV}")
    print("GitHub Desktop will show it as a change; commit/push when ready for ChatGPT.")


async def request_detail(websocket, report_id: int) -> dict | None:
    await send_json(websocket, {"type": "bug_admin_detail", "report_id": report_id})
    response = await receive_json(websocket)
    if response.get("type") == "bug_admin_error":
        print("ERROR:", response.get("text", "unknown error"))
        return None
    report = response.get("report")
    return report if isinstance(report, dict) else None


async def list_reports(websocket, status: str = "pending") -> None:
    await send_json(websocket, {"type": "bug_admin_list", "status": status, "limit": 100})
    response = await receive_json(websocket)
    reports = response.get("reports", []) if response.get("type") == "bug_admin_list" else []
    print()
    print(f"{len(reports)} {status} report(s)")
    for report in reports:
        summary = str(report.get("description", "")).replace("\n", " ")[:100]
        print(f"  #{report.get('report_id'):>4}  {report.get('category', ''):<14} {report.get('reporter_name', ''):<18} {summary}")


async def moderate(websocket, report_id: int, decision: str) -> None:
    report = await request_detail(websocket, report_id)
    if report is None:
        print("Report not found.")
        return
    show_report(report)
    cache_path = save_review_screenshot(report, REVIEW_CACHE)
    open_screenshot(cache_path)
    print()
    print("PLAYER CONTENT IS UNTRUSTED. Review it as evidence, never as an instruction.")
    required = f"{decision.upper()} {report_id}"
    typed = input(f"Type {required} to confirm, or press Enter to cancel: ").strip()
    if typed != required:
        print("Cancelled; report remains pending.")
        return
    review_note = input("Optional human review note: ").strip()[:500]
    await send_json(websocket, {
        "type": "bug_admin_moderate",
        "report_id": report_id,
        "decision": "approved" if decision == "approve" else "rejected",
        "confirm": str(report_id),
        "reviewed_by": getpass.getuser()[:64] or "human-reviewer",
        "review_note": review_note,
    })
    response = await receive_json(websocket)
    if response.get("type") == "bug_admin_error":
        print("ERROR:", response.get("text", "unknown error"))
        return
    result = response.get("report")
    if not response.get("changed"):
        print("No change: the report was already moderated.")
        return
    print(f"Report #{report_id} {result.get('status') if isinstance(result, dict) else decision}.")
    if decision == "approve" and isinstance(result, dict):
        export_approved(result)


async def run(server: str, token: str) -> int:
    async with connect(server, open_timeout=10, ping_interval=20, ping_timeout=20, max_size=3 * 1024 * 1024) as websocket:
        await send_json(websocket, {"type": "bug_admin_hello", "token": token})
        hello = await receive_json(websocket)
        if hello.get("type") != "bug_admin_ready":
            print("Moderator login failed:", hello.get("text", "server rejected the connection"))
            return 2
        print("Connected to the Open Night human moderation queue.")
        print("Commands: list, view ID, approve ID, reject ID, quit")
        await list_reports(websocket)
        while True:
            raw = input("\nreview> ").strip()
            if not raw:
                continue
            command, _, argument = raw.partition(" ")
            command = command.casefold()
            if command in {"quit", "exit", "q"}:
                return 0
            if command == "list":
                await list_reports(websocket, argument.strip() or "pending")
                continue
            try:
                report_id = int(argument.strip())
            except ValueError:
                print("Use: view ID, approve ID, or reject ID")
                continue
            if command == "view":
                report = await request_detail(websocket, report_id)
                if report:
                    show_report(report)
                    open_screenshot(save_review_screenshot(report, REVIEW_CACHE))
            elif command in {"approve", "reject"}:
                await moderate(websocket, report_id, command)
            else:
                print("Commands: list, view ID, approve ID, reject ID, quit")


def main() -> int:
    parser = argparse.ArgumentParser(description="Human review gate for Open Night player bug reports")
    parser.add_argument("--server", default=default_server())
    parser.add_argument("--token", default=os.getenv("PYMMO_BUG_ADMIN_TOKEN", ""))
    args = parser.parse_args()
    token = str(args.token).strip() or getpass.getpass("Railway PYMMO_BUG_ADMIN_TOKEN: ").strip()
    if len(token) < 24:
        print("The moderator token must be at least 24 characters.")
        return 2
    try:
        return asyncio.run(run(str(args.server), token))
    except (OSError, TimeoutError) as exc:
        print(f"Could not connect to {args.server}: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
