from __future__ import annotations

"""Mirror persisted Open Night bug reports to GitHub Issues.

The MySQL bug_reports table remains authoritative. This module is deliberately
best-effort: a GitHub outage or missing token must never make /bug fail after the
report has already been stored in MySQL.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any


TOKEN_ENV = "PYMMO_BUG_GITHUB_TOKEN"
REPO_ENV = "PYMMO_BUG_GITHUB_REPO"
DEFAULT_REPO = "goodnighthawk/Open-Night"


def _clean(value: Any, limit: int = 500) -> str:
    text = " ".join(str(value or "").replace("\x00", "").split())
    return text[:limit]


def mirror_bug_report(report_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
    """Create one GitHub issue for a newly persisted report.

    Returns the decoded GitHub response on success, otherwise None. Failure is
    logged and swallowed so database persistence remains the source of truth.
    """
    token = os.getenv(TOKEN_ENV, "").strip()
    if not token:
        print(f"Bug #{int(report_id)} stored; GitHub mirror disabled ({TOKEN_ENV} is not set).", flush=True)
        return None

    repo = os.getenv(REPO_ENV, DEFAULT_REPO).strip() or DEFAULT_REPO
    if "/" not in repo:
        print(f"Bug #{int(report_id)} stored; invalid {REPO_ENV}={repo!r}.", flush=True)
        return None

    category = _clean(fields.get("category"), 32) or "bug"
    description = _clean(fields.get("description"), 500)
    reporter_name = _clean(fields.get("reporter_name"), 32) or "unknown"
    build_version = _clean(fields.get("build_version"), 160)
    map_id = _clean(fields.get("map_id"), 96)
    map_name = _clean(fields.get("map_name"), 160)
    source = _clean(fields.get("source"), 32)
    vehicle_id = _clean(fields.get("vehicle_id"), 96)
    screenshot_sha256 = _clean(fields.get("screenshot_sha256"), 64)

    try:
        world_x = float(fields.get("world_x", 0.0))
        world_y = float(fields.get("world_y", 0.0))
    except (TypeError, ValueError):
        world_x = world_y = 0.0
    try:
        level = int(fields.get("level", 0))
    except (TypeError, ValueError):
        level = 0

    in_vehicle = bool(fields.get("in_vehicle", False))
    context = fields.get("context")
    if isinstance(context, dict):
        context_text = json.dumps(context, ensure_ascii=False, sort_keys=True, indent=2)[:4000]
    else:
        context_text = "{}"

    title_description = description[:90] if description else "player report"
    title = f"[Player Bug #{int(report_id)}] {title_description}"
    body = "\n".join([
        f"<!-- open-night-bug-report:{int(report_id)} -->",
        "## Player bug report",
        "",
        f"**Database bug ID:** #{int(report_id)}  ",
        "**Review status:** pending-review  ",
        f"**Category:** {category}  ",
        f"**Reporter:** {reporter_name}  ",
        f"**Source:** {source or 'unknown'}  ",
        f"**Build:** {build_version or 'unknown'}  ",
        f"**Map:** {map_name or 'unknown'} (`{map_id or 'unknown'}`)  ",
        f"**Position:** ({world_x:.1f}, {world_y:.1f}), level {level}  ",
        f"**Vehicle:** {'yes' if in_vehicle else 'no'}{(' — ' + vehicle_id) if vehicle_id else ''}  ",
        f"**Screenshot SHA-256:** `{screenshot_sha256}`" if screenshot_sha256 else "**Screenshot:** none",
        "",
        "### Description",
        description or "(empty)",
        "",
        "<details><summary>Captured context</summary>",
        "",
        "```json",
        context_text,
        "```",
        "</details>",
        "",
        "_Mirrored automatically after successful storage in the Railway/MySQL bug queue. The database record remains authoritative._",
    ])

    payload = json.dumps({"title": title, "body": body}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=payload,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "open-night-bug-mirror",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            result = json.loads(response.read().decode("utf-8"))
        print(f"Bug #{int(report_id)} mirrored to GitHub issue #{result.get('number', '?')}", flush=True)
        return result
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        detail = ""
        if isinstance(exc, urllib.error.HTTPError):
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                detail = ""
        print(f"Bug #{int(report_id)} stored but GitHub mirror failed: {exc} {detail}".strip(), flush=True)
        return None


def install_database_bug_mirror() -> None:
    """Patch InventoryDatabase.create_bug_report before the v1.1 server installs dedupe."""
    import database

    original = database.InventoryDatabase.create_bug_report
    if getattr(original, "_open_night_github_mirror", False):
        return

    def create_bug_report_with_mirror(self, **kwargs):
        report_id = original(self, **kwargs)
        result = None
        try:
            result = mirror_bug_report(report_id, kwargs)
        except Exception as exc:
            print(f"Bug #{int(report_id)} stored but GitHub mirror raised unexpectedly: {exc}", flush=True)
        # The Railway relay can now distinguish "stored" from "stored + visible
        # in GitHub" and show the exact GitHub issue number to the player.
        self._open_night_last_bug_github_mirror = {
            "report_id": int(report_id),
            "issue_number": int(result.get("number", 0) or 0) if isinstance(result, dict) else 0,
            "issue_url": str(result.get("html_url", "")) if isinstance(result, dict) else "",
        }
        return report_id

    create_bug_report_with_mirror._open_night_github_mirror = True
    database.InventoryDatabase.create_bug_report = create_bug_report_with_mirror
