"""Offline release gate for the v2.3 bug-report intake baseline."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    snapshot = ROOT / "feedback" / "next_version" / "github_bug_reports.csv"
    with snapshot.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_issue = {int(row["github_issue"]): row for row in rows}
    assert len(rows) == 140, f"expected 140 pulled issues, found {len(rows)}"
    assert max(by_issue) == 160
    assert sum(row["state"] == "open" for row in rows) == 136
    for number in range(150, 161):
        row = by_issue[number]
        assert row["state"] == "open"
        assert row["review_status"] == "pending-review"
        assert row["url"].endswith(f"/issues/{number}")
    for row in rows:
        for value in row.values():
            assert not str(value or "").lstrip().startswith(("=", "+", "-", "@"))

    checklist = (ROOT / "V2_3_CURRENT_BUG_CHECKLIST.md").read_text(encoding="utf-8")
    for number in range(150, 161):
        assert f"issues/{number}" in checklist
    assert (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip() == "2.3"
    print("V2.3 BUG INTAKE AUDIT PASSED: 140 total / 136 open / current reports #150-#160")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
