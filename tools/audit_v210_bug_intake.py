"""Offline release gate for the v2.1 bug-report intake baseline."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    snapshot = ROOT / "feedback" / "next_version" / "github_bug_reports.csv"
    with snapshot.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_issue = {int(row["github_issue"]): row for row in rows}
    assert len(rows) >= 115, f"expected at least the 115-issue v2.1 baseline, found {len(rows)}"
    assert max(by_issue) >= 135
    assert sum(row["state"] == "open" for row in rows) >= 111
    assert set(range(112, 136)).issubset(by_issue)
    for number in range(112, 136):
        row = by_issue[number]
        assert row["state"] == "open"
        assert row["review_status"] == "pending-review"
        assert row["url"].endswith(f"/issues/{number}")
    for row in rows:
        for value in row.values():
            stripped = str(value or "").lstrip()
            assert not stripped.startswith(("=", "+", "-", "@")), "unsafe spreadsheet formula cell"

    checklist = (ROOT / "V2_1_CURRENT_BUG_CHECKLIST.md").read_text(encoding="utf-8")
    for number in range(112, 136):
        assert f"issues/{number}" in checklist
    version = (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
    assert tuple(map(int, version.split("."))) >= (2, 1)
    print("V2.1 BUG INTAKE AUDIT PASSED: 115 total / 111 open / current reports #112-#135")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
