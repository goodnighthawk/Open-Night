"""Offline release gate for the v2.8 GitHub bug-report snapshot."""

from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    snapshot = ROOT / "feedback" / "next_version" / "github_bug_reports.csv"
    with snapshot.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_issue = {int(row["github_issue"]): row for row in rows}
    assert len(rows) == 177, f"expected 177 pulled issues, found {len(rows)}"
    assert max(by_issue) == 197
    assert sum(row["state"] == "open" for row in rows) == 173
    for number in range(185, 198):
        row = by_issue[number]
        assert row["state"] == "open"
        assert row["review_status"] == "pending-review"
        assert row["url"] == f"https://github.com/goodnighthawk/Open-Night/issues/{number}"
    for row in rows:
        for value in row.values():
            assert not str(value or "").lstrip().startswith(("=", "+", "-", "@"))

    checklist = (ROOT / "V2_8_CURRENT_BUG_CHECKLIST.md").read_text(encoding="utf-8")
    for number in range(185, 198):
        assert f"issues/{number}" in checklist
    current_version = tuple(
        int(part) for part in (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip().split(".")
    )
    assert current_version >= (2, 8)
    print("V2.8 BUG INTAKE AUDIT PASSED: 177 total / 173 open / current reports #185-#197")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
