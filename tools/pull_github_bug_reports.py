"""Download the GitHub issue mirror as inert next-version planning data."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "feedback" / "next_version" / "github_bug_reports.csv"
API = "https://api.github.com/repos/goodnighthawk/Open-Night/issues"
FIELDS = (
    "github_issue", "state", "title", "database_bug_id", "review_status", "build",
    "map", "position", "description", "screenshot_sha256", "created_at", "updated_at", "url",
)


def _field(body: str, label: str) -> str:
    match = re.search(rf"^\*\*{re.escape(label)}:\*\*\s*(.+?)\s*$", body, re.MULTILINE)
    return match.group(1).strip().rstrip("  ") if match else ""


def _description(body: str) -> str:
    match = re.search(r"^### Description\s*\n(.*?)(?:\n<details>|\Z)", body, re.MULTILINE | re.DOTALL)
    return " ".join(match.group(1).split()) if match else ""


def _spreadsheet_safe(value: object) -> str:
    text = str(value or "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def _fetch() -> list[dict]:
    issues: list[dict] = []
    page = 1
    while True:
        request = Request(
            f"{API}?state=all&per_page=100&page={page}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Open-Night-Codex"},
        )
        with urlopen(request, timeout=20) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise RuntimeError("GitHub returned an unexpected issue payload")
        issues.extend(item for item in batch if isinstance(item, dict) and "pull_request" not in item)
        if len(batch) < 100:
            return issues
        page += 1


def main() -> int:
    issues = sorted(_fetch(), key=lambda item: int(item.get("number", 0)))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for issue in issues:
            body = str(issue.get("body") or "")
            row = {
                "github_issue": issue.get("number", ""),
                "state": issue.get("state", ""),
                "title": issue.get("title", ""),
                "database_bug_id": _field(body, "Database bug ID").lstrip("#"),
                "review_status": _field(body, "Review status"),
                "build": _field(body, "Build"),
                "map": _field(body, "Map"),
                "position": _field(body, "Position"),
                "description": _description(body),
                "screenshot_sha256": _field(body, "Screenshot SHA-256").strip("`"),
                "created_at": issue.get("created_at", ""),
                "updated_at": issue.get("updated_at", ""),
                "url": issue.get("html_url", ""),
            }
            writer.writerow({key: _spreadsheet_safe(value) for key, value in row.items()})
    open_count = sum(str(issue.get("state")) == "open" for issue in issues)
    latest = max((int(issue.get("number", 0)) for issue in issues), default=0)
    print(f"Pulled {len(issues)} GitHub issues ({open_count} open); latest #{latest}")
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
